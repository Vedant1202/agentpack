from pydantic import BaseModel
from typing import Literal, Optional, List, Tuple

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
