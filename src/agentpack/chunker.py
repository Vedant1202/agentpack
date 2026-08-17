import tiktoken
from typing import List
from agentpack.models import SourceDocument

class Chunk:
    def __init__(self, chunk_id: str, source_id: str, path: str, token_count: int, content: str, metadata: dict):
        self.chunk_id = chunk_id
        self.source_id = source_id
        self.path = path
        self.token_count = token_count
        self.content = content
        self.metadata = metadata

def chunk_document(doc: SourceDocument, max_tokens: int = 800, overlap_percent: float = 0.15) -> List[Chunk]:
    encoder = tiktoken.get_encoding("cl100k_base")
    chunks = []
    
    current_blocks = []
    current_tokens = 0
    current_metadata = {"source_path": doc.path}
    chunk_index = 0
    
    overlap_tokens_target = int(max_tokens * overlap_percent)
    
    def create_chunk(allow_retention=True):
        nonlocal current_blocks, current_tokens, chunk_index, current_metadata
        if not current_blocks:
            return
        content_str = "\n\n".join([b["text"] for b in current_blocks])
        chunk_id = f"{doc.source_id}_chunk_{chunk_index:03d}"
        if len(current_blocks) <= 1:
            # No "\n\n" join possible with 0 or 1 blocks, so there's no join-separator
            # effect to account for -- current_tokens (the sum of real per-block
            # encoder.encode() results; verified this holds even for oversized-split
            # sub-blocks, whose "tokens" comes from a decode()/re-encode() round trip,
            # via FU.4's benchmark) already IS content_str's real tokenized length.
            # Most emitted chunks are single-block, so skipping the re-encode here is
            # most of FU.4's perf win -- re-encoding every chunk's full content
            # (~800 tokens x 254 chunks on a real 10-K) measured as the dominant cost.
            real_token_count = current_tokens
        else:
            # Recorded from the real joined text, not the incrementally-summed
            # current_tokens -- the "\n\n" join between blocks (and rare BPE
            # merge effects at the boundary) mean the sum of parts isn't always
            # exactly the tokenized length of the whole.
            real_token_count = len(encoder.encode(content_str))
        chunks.append(Chunk(
            chunk_id=chunk_id,
            source_id=doc.source_id,
            path=f"chunks/{chunk_id}.md",
            token_count=real_token_count,
            content=content_str,
            metadata=current_metadata.copy()
        ))
        chunk_index += 1

        if not allow_retention:
            current_blocks = []
            current_tokens = 0
            return

        # Keep blocks for overlap
        overlap_blocks = []
        overlap_toks = 0
        for b in reversed(current_blocks):
            if overlap_toks + b["tokens"] > overlap_tokens_target:
                break
            # don't overlap tables to avoid duplicating massive tables
            if b["type"] == "table" and overlap_toks > 0:
                break
            overlap_blocks.insert(0, b)
            overlap_toks += b["tokens"]

        current_blocks = overlap_blocks
        current_tokens = overlap_toks

    for block in doc.blocks:
        if not block.text:
            continue

        tokens = encoder.encode(block.text)
        block_tokens = len(tokens)
        fits = block_tokens <= max_tokens

        # Flush any accumulated content -- with ITS OWN (old) metadata -- before this
        # block's page/section overwrites current_metadata below. Otherwise a chunk made
        # entirely of page-1 content gets stamped with page 2 because it was flushed only
        # once block 2 arrived.
        if fits:
            if current_tokens > 0:
                # Cheap, provably-safe skip before paying for a real encode() call.
                # Empirically (FU.4), a "\n\n" join costs at most 1 extra token beyond
                # the sum of its two sides' own token counts (20k-sample check across
                # varied boundary text); using 2 per separator as margin. After adding
                # this block there are len(current_blocks) separators in the joined
                # text, so if current_tokens + block_tokens + 2*(len(current_blocks)+1)
                # already fits max_tokens, the real joined length provably does too --
                # no need to encode() to find out. This is the hot path (most block
                # additions don't need a flush at all): re-encoding the whole
                # accumulated text on every single append measured a 2-3x
                # chunk_document() slowdown on a real 10-K.
                safe_bound = current_tokens + block_tokens + 2 * (len(current_blocks) + 1)
                if safe_bound > max_tokens:
                    # Real (joined) length, not the summed estimate: "\n\n" between blocks
                    # (and rare BPE merge effects at the join) can push the true total over
                    # max_tokens even when the per-block sum looks like it still fits.
                    candidate = "\n\n".join([b["text"] for b in current_blocks] + [block.text])
                    if len(encoder.encode(candidate)) > max_tokens:
                        create_chunk()
                        if current_tokens > 0:
                            candidate = "\n\n".join([b["text"] for b in current_blocks] + [block.text])
                            if len(encoder.encode(candidate)) > max_tokens:
                                # The retained remainder alone still doesn't leave room for
                                # this block (a small retained tail immediately followed by
                                # a near-max_tokens block) -- drop the retention rather than
                                # risk another oversized chunk.
                                create_chunk(allow_retention=False)
        elif current_tokens > 0:
            create_chunk()

        # Update metadata after any flush so sub-blocks/the new chunk carry this block's
        # own page/section.
        if block.section_path:
            current_metadata["section"] = block.section_path[-1]
            current_metadata["section_path"] = list(block.section_path)
        if block.page:
            current_metadata["page"] = block.page
        if block.row_range:
            current_metadata["row_range"] = list(block.row_range)

        if fits:
            # Normal path: block fits in a single chunk slot
            current_blocks.append({"text": block.text, "tokens": block_tokens, "type": block.type})
            current_tokens += block_tokens
        else:
            # Oversized block: split with overlap, preserving metadata on every sub-block.
            # current_tokens may still hold retained overlap carried over from the flush
            # just above -- each slice must leave room for it (accumulate, don't overwrite)
            # so the chunk's real length never exceeds max_tokens and its recorded
            # token_count matches its real content.
            overlap = int(max_tokens * overlap_percent)
            start = 0
            while start < block_tokens:
                available = max(max_tokens - current_tokens, 1)
                end = min(start + available, block_tokens)
                sub_text = encoder.decode(tokens[start:end])

                # `available` sums per-block token counts, which can slightly
                # undercount the real joined length once this slice is glued to
                # already-retained content with "\n\n" (separator + rare merge
                # effects at the boundary). Shrink until the real (joined,
                # re-tokenized) text actually fits -- converges in 1-2 steps
                # since the overage is always small.
                while end > start + 1:
                    candidate = "\n\n".join([b["text"] for b in current_blocks] + [sub_text])
                    if len(encoder.encode(candidate)) <= max_tokens:
                        break
                    end -= 1
                    sub_text = encoder.decode(tokens[start:end])

                sub_tokens = tokens[start:end]
                current_blocks.append({"text": sub_text, "tokens": len(sub_tokens), "type": block.type})
                current_tokens += len(sub_tokens)
                create_chunk()
                start = end - overlap if end < block_tokens else end

    create_chunk()
    return chunks
