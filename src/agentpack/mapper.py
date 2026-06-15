"""Build the hierarchical knowledge map (map.yml) from parsed documents and chunks.

Phase A1 (walking skeleton): the section tree is a FLAT list per document, grouped by
each chunk's recorded section_path. Recursive nesting, orphan `__root__` handling, and
has_tables population come in Phase A2. Output is a plain dict ready for yaml.dump.
"""
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional

from agentpack.models import SourceDocument, SectionNode, DocumentMap, CorpusMap
from agentpack.chunker import Chunk


def _page_range(chunks: List[Chunk]) -> Optional[List[int]]:
    """[min, max] page across chunks, or None when no chunk carries a page (txt/md)."""
    pages = [c.metadata.get("page") for c in chunks if c.metadata.get("page")]
    if not pages:
        return None
    return [min(pages), max(pages)]


def _doc_title(doc: SourceDocument) -> str:
    """First heading in the document, falling back to a humanized filename stem."""
    for block in doc.blocks:
        if block.type == "heading" and block.text:
            return block.text.strip()
    return Path(doc.path).stem.replace("_", " ")


def build_map(pack_meta: dict, docs: List[SourceDocument], chunks: List[Chunk]) -> dict:
    """Assemble the corpus -> document -> section -> chunk map.

    Args:
        pack_meta: ``{"name", "generated_at", "manifest"}`` echoed into the map's ``pack`` block.
        docs: parsed source documents, in manifest order.
        chunks: every chunk produced for the pack (carry ``source_id`` + ``metadata.section_path``).

    Returns:
        A plain dict (validated via pydantic models) ready for ``yaml.dump``.
    """
    chunks_by_source: "OrderedDict[str, List[Chunk]]" = OrderedDict()
    for c in chunks:
        chunks_by_source.setdefault(c.source_id, []).append(c)

    documents: List[DocumentMap] = []
    total_sections = 0

    for doc in docs:
        doc_chunks = chunks_by_source.get(doc.source_id, [])

        # Group chunks by their section_path, preserving first-appearance order
        # so the emitted map is deterministic.
        groups: "OrderedDict[tuple, List[Chunk]]" = OrderedDict()
        for c in doc_chunks:
            key = tuple(c.metadata.get("section_path") or [])
            groups.setdefault(key, []).append(c)

        sections: List[SectionNode] = []
        for idx, (path, members) in enumerate(groups.items()):
            sections.append(SectionNode(
                node_id=f"{doc.source_id}_s{idx:04d}",
                title=path[-1] if path else "(root)",
                pages=_page_range(members),
                has_tables=False,  # populated in Phase A2 from block types
                chunk_ids=[m.chunk_id for m in members],
                nodes=[],
            ))
        total_sections += len(sections)

        documents.append(DocumentMap(
            source_id=doc.source_id,
            path=doc.path,
            title=_doc_title(doc),
            pages=_page_range(doc_chunks),
            stats={"sections": len(sections), "chunks": len(doc_chunks)},
            sections=sections,
        ))

    corpus_map = CorpusMap(
        map_version=1,
        pack=pack_meta,
        corpus={"stats": {
            "documents": len(documents),
            "sections": total_sections,
            "chunks": len(chunks),
        }},
        documents=documents,
    )
    return corpus_map.model_dump()
