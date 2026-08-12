from pydantic import BaseModel
from typing import Literal, Optional, List, Tuple, Dict

class ExtractionWarning(BaseModel):
    """Represents a warning encountered during parsing (e.g. unreadable PDF page)."""
    source_id: str
    page: Optional[int] = None
    type: str
    message: str


class DocumentBlock(BaseModel):
    """Represents a unified contiguous block of semantic information from a document."""
    block_id: str
    source_id: str
    type: Literal["heading", "paragraph", "table", "page"]
    text: Optional[str] = None
    page: Optional[int] = None
    section_path: List[str] = []
    row_range: Optional[Tuple[int, int]] = None


class SourceDocument(BaseModel):
    """Represents a fully parsed document normalized into the Canonical Document Model."""
    source_id: str
    path: str
    type: Literal["pdf", "markdown", "txt", "csv", "docx", "pptx", "xlsx", "html", "htm"]
    checksum: str
    blocks: List[DocumentBlock]
    warnings: List[ExtractionWarning]


class SectionNode(BaseModel):
    """A node in a document's hierarchical section tree (the knowledge map)."""
    node_id: str
    title: str
    pages: Optional[List[int]] = None          # [start_page, end_page]
    has_tables: bool = False
    keyphrases: List[str] = []                  # [B] YAKE keyphrases for this section's text
    gist: Optional[str] = None                  # [B] one-line extractive (TextRank) summary
    chunk_ids: List[str] = []
    nodes: List["SectionNode"] = []            # child sections (recursive; flat in Phase A1)


class DocumentMap(BaseModel):
    """A single source document's entry in the map: metadata + its section tree."""
    source_id: str
    path: str
    title: str
    status: str = "success"            # "failed" when the source did not parse / produced no chunks
    pages: Optional[List[int]] = None
    summary: Optional[str] = None       # [B] document-level extractive summary
    stats: Dict[str, int] = {}
    sections: List[SectionNode] = []


class CorpusMap(BaseModel):
    """Top-level hierarchical knowledge map written to map.yml."""
    map_version: int = 1
    pack: Dict
    corpus: Dict
    documents: List[DocumentMap] = []


class GraphNode(BaseModel):
    """A node in the corpus concept graph (graph.yml) — a document, a top-level
    section, or a promoted concept. id reuses an existing identity (manifest
    source_id for documents, map.yml node_id for sections) rather than minting
    a new one; only concepts (id: c_<slug>) are a new id namespace."""
    id: str
    kind: Literal["document", "section", "concept"]
    label: str
    doc: Optional[str] = None          # owning document's source_id (section/concept nodes)
    community: Optional[int] = None    # set once communities are computed


class GraphEdge(BaseModel):
    """A directed edge in the corpus concept graph, tagged with how it was derived."""
    source: str
    target: str
    relation: str                      # contains | mentions | references | similar_to
    basis: Literal["structural", "keyphrase", "embedding"]


class CorpusGraph(BaseModel):
    """Top-level corpus concept graph written to graph.yml."""
    graph_version: int = 1
    pack: Dict
    params: Dict                       # effective [graph] config this graph was built with
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    communities: List[Dict] = []       # [{id, label, size}, ...]


SectionNode.model_rebuild()
