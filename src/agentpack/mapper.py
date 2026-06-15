"""Build the hierarchical knowledge map (map.yml) from parsed documents and chunks.

Phase A2: the section tree is reconstructed **from the document's blocks** (each block
carries the full ``section_path``), so sections whose prose merged into a neighbouring
chunk are still represented. Per node we capture nested children, page span (rolled up
over the subtree), and ``has_tables`` (from block types). Chunks are attached to the node
matching their recorded ``section_path``; chunks with no section land under a synthetic
``__root__`` node.

Phase B: when ``enrich`` is on (default), each node/document/corpus also gets deterministic,
offline descriptors — YAKE ``keyphrases`` and a TextRank ``gist``/``summary`` (see ``enrich.py``).
"""
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional, Tuple

from agentpack.models import SourceDocument, SectionNode, DocumentMap, CorpusMap
from agentpack.chunker import Chunk
from agentpack.enrich import keyphrases as _keyphrases, gist as _gist

# Cap text fed to document/corpus-level enrichment so pack-time stays bounded on huge filings.
_ENRICH_TEXT_CAP = 8000


class _TreeNode:
    """Mutable scratch node used while assembling a single document's section tree."""
    __slots__ = ("title", "children", "own_pages", "own_text", "has_tables", "chunk_ids")

    def __init__(self, title: str):
        self.title = title
        self.children: "OrderedDict[str, _TreeNode]" = OrderedDict()
        self.own_pages: List[int] = []
        self.own_text: List[str] = []
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

    # 1. Structure + page/table/text facts come from blocks (the authoritative hierarchy).
    for block in doc.blocks:
        path = tuple(block.section_path or [])
        if not path:
            target = root_orphan
            root_used = True
        else:
            target = ensure(path)
        if block.page:
            target.own_pages.append(block.page)
        if block.text:
            target.own_text.append(block.text)
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


def _to_section_node(title: str, tnode: _TreeNode, node_id: str, enrich: bool) -> SectionNode:
    """Convert a scratch node to a SectionNode: ordinal node_ids, rolled-up pages, descriptors."""
    children: List[SectionNode] = []
    for j, (ctitle, cnode) in enumerate(tnode.children.items()):
        children.append(_to_section_node(ctitle, cnode, f"{node_id}-{j:02d}", enrich))

    pages = list(tnode.own_pages)
    for child in children:
        if child.pages:
            pages.extend(child.pages)
    page_span = [min(pages), max(pages)] if pages else None

    node_text = " ".join(tnode.own_text).strip()
    return SectionNode(
        node_id=node_id,
        title=title,
        pages=page_span,
        has_tables=tnode.has_tables,
        keyphrases=_keyphrases(node_text) if enrich else [],
        gist=(_gist(node_text) or None) if enrich else None,
        chunk_ids=tnode.chunk_ids,
        nodes=children,
    )


def _count_nodes(nodes: List[SectionNode]) -> int:
    return sum(1 + _count_nodes(n.nodes) for n in nodes)


def build_map(pack_meta: dict, docs: List[SourceDocument], chunks: List[Chunk],
              enrich: bool = True) -> dict:
    """Assemble the corpus -> document -> section -> chunk map.

    Args:
        pack_meta: ``{"name", "generated_at", "manifest"}`` echoed into the map's ``pack`` block.
        docs: parsed source documents, in manifest order.
        chunks: every chunk produced for the pack (carry ``source_id`` + ``metadata.section_path``).
        enrich: when True (default), attach deterministic keyphrases/gist/summary descriptors.

    Returns:
        A plain dict (validated via pydantic models) ready for ``yaml.dump``.
    """
    chunks_by_source: "OrderedDict[str, List[Chunk]]" = OrderedDict()
    for c in chunks:
        chunks_by_source.setdefault(c.source_id, []).append(c)

    documents: List[DocumentMap] = []
    total_sections = 0
    total_tables = 0
    doc_summaries: List[str] = []

    for doc in docs:
        doc_chunks = chunks_by_source.get(doc.source_id, [])
        has_parse_error = any(w.type == "parse_error" for w in doc.warnings)
        status = "failed" if (has_parse_error or len(doc_chunks) == 0) else "success"
        roots, orphan = _build_tree(doc, doc_chunks)

        sections: List[SectionNode] = []
        if orphan is not None:
            sections.append(_to_section_node("(root)", orphan, f"{doc.source_id}_root", enrich))
        for i, (title, tnode) in enumerate(roots.items()):
            sections.append(_to_section_node(title, tnode, f"{doc.source_id}_s{i:02d}", enrich))

        n_sections = _count_nodes(sections)
        total_sections += n_sections
        n_tables = sum(1 for b in doc.blocks if b.type == "table")
        total_tables += n_tables

        doc_pages = [p for s in sections if s.pages for p in s.pages]

        summary = None
        if enrich and status == "success":
            doc_text = " ".join(b.text for b in doc.blocks if b.text)[:_ENRICH_TEXT_CAP]
            summary = _gist(doc_text) or None
            if summary:
                doc_summaries.append(summary)

        documents.append(DocumentMap(
            source_id=doc.source_id,
            path=doc.path,
            title=_doc_title(doc),
            status=status,
            pages=[min(doc_pages), max(doc_pages)] if doc_pages else None,
            summary=summary,
            stats={"sections": n_sections, "tables": n_tables, "chunks": len(doc_chunks)},
            sections=sections,
        ))

    corpus: dict = {}
    if enrich:
        corpus["summary"] = _gist(" ".join(doc_summaries)[:_ENRICH_TEXT_CAP]) or None
    corpus["stats"] = {
        "documents": len(documents),
        "sections": total_sections,
        "tables": total_tables,
        "chunks": len(chunks),
    }

    corpus_map = CorpusMap(
        map_version=1,
        pack=pack_meta,
        corpus=corpus,
        documents=documents,
    )
    return corpus_map.model_dump()


def build_map_from_manifest(pack_dir: str) -> dict:
    """Rebuild map.yml for an existing pack from its manifest alone (no re-parse).

    Lighter-weight than the during-pack map: the tree is reconstructed from chunk citations
    (``section_path`` + ``page``), so it cannot recover ``has_tables``, sections that contain
    no chunks, or text-derived descriptors. Run ``agentpack pack`` for the full-fidelity map.
    """
    import yaml
    from agentpack.models import SourceDocument, DocumentBlock, ExtractionWarning

    base = Path(pack_dir)
    with open(base / "manifest.yml", "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f) or {}

    metas_by_source: "OrderedDict[str, list]" = OrderedDict()
    for cm in manifest.get("chunks", []) or []:
        metas_by_source.setdefault(cm.get("source_id"), []).append(cm)

    docs: List[SourceDocument] = []
    chunks: List[Chunk] = []
    for src in manifest.get("sources", []) or []:
        sid = src.get("id")
        blocks: List[DocumentBlock] = []
        for i, cm in enumerate(metas_by_source.get(sid, [])):
            cit = cm.get("citation") or {}
            section_path = cit.get("section_path")
            if not section_path and cit.get("section"):
                section_path = [cit["section"]]
            blocks.append(DocumentBlock(
                block_id=f"{sid}_pb{i:04d}", source_id=sid, type="paragraph",
                text=" ", page=cit.get("page"), section_path=section_path or [],
            ))
            chunks.append(Chunk(
                chunk_id=cm.get("id"), source_id=sid, path=cm.get("path", ""),
                token_count=cm.get("token_count", 0), content="", metadata=cit,
            ))
        warnings = []
        if src.get("status") == "failed":
            warnings = [ExtractionWarning(source_id=sid, type="parse_error",
                                          message="source marked failed in manifest")]
        docs.append(SourceDocument(
            source_id=sid, path=src.get("path", sid), type=src.get("type", "txt"),
            checksum=src.get("checksum", ""), blocks=blocks, warnings=warnings,
        ))

    p = manifest.get("pack", {}) or {}
    pack_meta = {"name": p.get("name", "corpus"),
                 "generated_at": p.get("generated_at", ""),
                 "manifest": "manifest.yml"}
    # No real text in a manifest rebuild -> skip text-derived descriptors.
    return build_map(pack_meta, docs, chunks, enrich=False)
