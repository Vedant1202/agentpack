import hashlib
import fitz
from pathlib import Path
from agentpack.models import SourceDocument, DocumentBlock, ExtractionWarning
from agentpack.parsers.base import Parser
from agentpack.parsers.markdown_parser import MarkdownParser

class PDFParser(Parser):
    def __init__(self, fast_pdf: bool = False):
        self.fast_pdf = fast_pdf

    def _parse_fast_spatial(self, file_path: Path, source_id: str) -> SourceDocument:
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
                message=f"Failed to parse PDF (fast mode): {str(e)}"
            ))
            
        return SourceDocument(
            source_id=source_id,
            path=file_path.name,
            type="pdf",
            checksum=checksum,
            blocks=blocks,
            warnings=warnings
        )

    def parse(self, file_path: Path, source_id: str) -> SourceDocument:
        if self.fast_pdf:
            return self._parse_fast_spatial(file_path, source_id)
            
        try:
            from docling.document_converter import DocumentConverter
        except ImportError:
            warnings = [ExtractionWarning(
                source_id=source_id,
                type="import_error",
                message="docling is not installed. Falling back to fast_pdf mode."
            )]
            doc = self._parse_fast_spatial(file_path, source_id)
            doc.warnings.extend(warnings)
            return doc
            
        with open(file_path, "rb") as f:
            content = f.read()
        checksum = hashlib.sha256(content).hexdigest()
        
        try:
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.datamodel.base_models import InputFormat
            from docling.document_converter import PdfFormatOption

            _opts = PdfPipelineOptions()
            _opts.accelerator_options.device = "cpu"
            converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=_opts)}
            )
            docling_result = converter.convert(file_path)
            markdown_text = docling_result.document.export_to_markdown()
            
            # Use MarkdownParser to parse the resulting semantic markdown
            md_parser = MarkdownParser()
            if hasattr(self, 'remove_empty_lines'):
                md_parser.remove_empty_lines = self.remove_empty_lines
                
            md_doc = md_parser.parse_string(markdown_text, file_path, source_id)
            
            # The type is "pdf", not "markdown", so we override it
            return SourceDocument(
                source_id=source_id,
                path=file_path.name,
                type="pdf",
                checksum=checksum,
                blocks=md_doc.blocks,
                warnings=md_doc.warnings
            )
            
        except Exception as e:
            warnings = [ExtractionWarning(
                source_id=source_id,
                type="parse_error",
                message=f"Failed to parse PDF with Docling: {str(e)}"
            )]
            return SourceDocument(
                source_id=source_id,
                path=file_path.name,
                type="pdf",
                checksum=checksum,
                blocks=[],
                warnings=warnings
            )
