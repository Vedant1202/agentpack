"""Build the hierarchical knowledge map (map.yml) from parsed documents and chunks.

Phase A2: the section tree is reconstructed **from the document's blocks** (each block
carries the full ``section_path``), so sections whose prose merged into a neighbouring
chunk are still represented. Per node we capture nested children, page span (rolled up
over the subtree), and ``has_tables`` (from block types). Chunks are attached to the node
matching their recorded ``section_path``; chunks with no section land under a synthetic
``__root__`` node. Output is a plain dict ready for ``yaml.dump``.
"""
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional, Tuple

from agentpack.models import SourceDocument, SectionNode, DocumentMap, CorpusMap
from agentpack.chunker import Chunk


class _TreeNode:
    """Mutable scratch node used while assembling a single document's section tree."""
    __slots__ = ("title", "children", "own_pages", "has_tables", "chunk_ids")

    def __init__(self, title: str):
        self.title = title
        self.children: "OrderedDict[str, _TreeNode]" = OrderedDict()
        self.own_pages: List[int] = []
        self.has_tables = False
        self.chunk_ids: List[str] = []


def _doc_title(doc: SourceDocument) -> str:
    """First heading in the document, falling back to a humanized filename stem."""
    for block in doc.blocks:
        if block.type == "heading" and block.text:
            return block.text.strip()
    return Path(doc.path).stem.replace("_", " ")


def _build_tree(doc: SourceDocument, doc_chunks: List[Chunk]):
    """Return ``(roots, root_orphan)`` scratch trees for one document.

    ``roots`` is an ordered title->_TreeNode map of top-level sections (document order).
    ``root_orphan`` holds content/chunks with no section_path, or None if there are none.
    """
    roots: "OrderedDict[str, _TreeNode]" = OrderedDict()
    root_orphan = _TreeNode("(root)")
    root_used = False

    def ensure(path: Tuple[str, ...]) -> _TreeNode:
        level = roots
        node: Optional[_TreeNode] = None
        for title in path:
            if title not in level:
                level[title] = _TreeNode(title)
            node = level[title]
            level = node.children
        return node

    def find(path: Tuple[str, ...]) -> Optional[_TreeNode]:
        level = roots
        node: Optional[_TreeNode] = None
        for title in path:
            if title not in level:
                return None
            node = level[title]
            level = node.children
        return node

    # 1. Structure + page/table facts come from blocks (the authoritative hierarchy).
    for block in doc.blocks:
        path = tuple(block.section_path or [])
        if not path:
            target = root_orphan
            root_used = True
        else:
            target = ensure(path)
        if block.page:
            target.own_pages.append(block.page)
        if block.type == "table":
            target.has_tables = True

    # 2. Attach chunks to the node matching their recorded section_path.
    for chunk in doc_chunks:
        path = tuple(chunk.metadata.get("section_path") or [])
        node = find(path) if path else None
        if node is None:
            root_orphan.chunk_ids.append(chunk.chunk_id)
            root_used = True
        else:
            node.chunk_ids.append(chunk.chunk_id)

    return roots, (root_orphan if root_used else None)


def _to_section_node(title: str, tnode: _TreeNode, node_id: str) -> SectionNode:
    """Convert a scratch node to a SectionNode, assigning ordinal node_ids and rolling up pages."""
    children: List[SectionNode] = []
    for j, (ctitle, cnode) in enumerate(tnode.children.items()):
        children.append(_to_section_node(ctitle, cnode, f"{node_id}-{j:02d}"))

    pages = list(tnode.own_pages)
    for child in children:
        if child.pages:
            pages.extend(child.pages)
    page_span = [min(pages), max(pages)] if pages else None

    return SectionNode(
        node_id=node_id,
        title=title,
        pages=page_span,
        has_tables=tnode.has_tables,   # local to this section (subsection tables sit on their own node)
        chunk_ids=tnode.chunk_ids,
        nodes=children,
    )


def _count_nodes(nodes: List[SectionNode]) -> int:
    return sum(1 + _count_nodes(n.nodes) for n in nodes)


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
        roots, orphan = _build_tree(doc, doc_chunks)

        sections: List[SectionNode] = []
        if orphan is not None:
            sections.append(_to_section_node("(root)", orphan, f"{doc.source_id}_root"))
        for i, (title, tnode) in enumerate(roots.items()):
            sections.append(_to_section_node(title, tnode, f"{doc.source_id}_s{i:02d}"))

        n_sections = _count_nodes(sections)
        total_sections += n_sections

        doc_pages = [p for s in sections if s.pages for p in s.pages]
        documents.append(DocumentMap(
            source_id=doc.source_id,
            path=doc.path,
            title=_doc_title(doc),
            pages=[min(doc_pages), max(doc_pages)] if doc_pages else None,
            stats={"sections": n_sections, "chunks": len(doc_chunks)},
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
