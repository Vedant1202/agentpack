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
    type: Literal["pdf", "markdown", "txt", "csv"]
    checksum: str
    blocks: List[DocumentBlock]
    warnings: List[ExtractionWarning]


class SectionNode(BaseModel):
    """A node in a document's hierarchical section tree (the knowledge map)."""
    node_id: str
    title: str
    pages: Optional[List[int]] = None          # [start_page, end_page]
    has_tables: bool = False
    chunk_ids: List[str] = []
    nodes: List["SectionNode"] = []            # child sections (recursive; flat in Phase A1)


class DocumentMap(BaseModel):
    """A single source document's entry in the map: metadata + its section tree."""
    source_id: str
    path: str
    title: str
    status: str = "success"            # "failed" when the source did not parse / produced no chunks
    pages: Optional[List[int]] = None
    stats: Dict[str, int] = {}
    sections: List[SectionNode] = []


class CorpusMap(BaseModel):
    """Top-level hierarchical knowledge map written to map.yml."""
    map_version: int = 1
    pack: Dict
    corpus: Dict
    documents: List[DocumentMap] = []


SectionNode.model_rebuild()
