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
    
    def create_chunk():
        nonlocal current_blocks, current_tokens, chunk_index, current_metadata
        if not current_blocks:
            return
        content_str = "\n\n".join([b["text"] for b in current_blocks])
        chunk_id = f"{doc.source_id}_chunk_{chunk_index:03d}"
        chunks.append(Chunk(
            chunk_id=chunk_id,
            source_id=doc.source_id,
            path=f"chunks/{chunk_id}.md",
            token_count=current_tokens,
            content=content_str,
            metadata=current_metadata.copy()
        ))
        chunk_index += 1
        
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
            
        block_tokens = len(encoder.encode(block.text))
        
        # Update metadata
        if block.section_path:
            current_metadata["section"] = block.section_path[-1]
        if block.page:
            current_metadata["page"] = block.page
            
        if block.row_range:
            current_metadata["row_range"] = list(block.row_range)
            
        # Very large blocks might exceed max_tokens, in a full implementation we'd split the block itself.
        # For this MVP, we will just start a new chunk if adding this block pushes us over, unless we are empty.
        if current_tokens + block_tokens > max_tokens and current_tokens > 0:
            create_chunk()
            
        current_blocks.append({"text": block.text, "tokens": block_tokens, "type": block.type})
        current_tokens += block_tokens
        
    create_chunk()
    return chunks
