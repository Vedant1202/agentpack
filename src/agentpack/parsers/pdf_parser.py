import hashlib
import fitz
from pathlib import Path
from agentpack.models import SourceDocument, DocumentBlock, ExtractionWarning
from agentpack.parsers.base import Parser

class PDFParser(Parser):
    def parse(self, file_path: Path, source_id: str) -> SourceDocument:
        with open(file_path, "rb") as f:
            content = f.read()
        checksum = hashlib.sha256(content).hexdigest()
        
        blocks = []
        warnings = []
        
        try:
            doc = fitz.open(file_path)
            if doc.page_count == 0:
                warnings.append(ExtractionWarning(
                    source_id=source_id,
                    type="empty_file",
                    message="PDF file has no pages."
                ))
            
            for page_num in range(doc.page_count):
                page = doc[page_num]
                text = page.get_text("text").strip()
                if text:
                    blocks.append(DocumentBlock(
                        block_id=f"{source_id}_p{page_num}",
                        source_id=source_id,
                        type="page",
                        text=text,
                        page=page_num + 1
                    ))
                else:
                    warnings.append(ExtractionWarning(
                        source_id=source_id,
                        page=page_num + 1,
                        type="low_text_density",
                        message=f"Page {page_num + 1} has little or no text."
                    ))
        except Exception as e:
            warnings.append(ExtractionWarning(
                source_id=source_id,
                type="parse_error",
                message=f"Failed to parse PDF: {str(e)}"
            ))
            
        return SourceDocument(
            source_id=source_id,
            path=file_path.name,
            type="pdf",
            checksum=checksum,
            blocks=blocks,
            warnings=warnings
        )
