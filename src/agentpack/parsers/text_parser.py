import hashlib
from pathlib import Path
from agentpack.models import SourceDocument, DocumentBlock, ExtractionWarning
from agentpack.parsers.base import Parser

class TextParser(Parser):
    def parse(self, file_path: Path, source_id: str) -> SourceDocument:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        
        blocks = []
        warnings = []
        
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        
        if not paragraphs:
            warnings.append(ExtractionWarning(
                source_id=source_id,
                type="empty_file",
                message="Text file contained no meaningful paragraphs."
            ))
            
        for i, para in enumerate(paragraphs):
            blocks.append(DocumentBlock(
                block_id=f"{source_id}_p{i}",
                source_id=source_id,
                type="paragraph",
                text=para
            ))

        return SourceDocument(
            source_id=source_id,
            path=file_path.name,
            type="txt",
            checksum=checksum,
            blocks=blocks,
            warnings=warnings
        )
