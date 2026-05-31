import hashlib
import fitz
from pathlib import Path
from agentpack.models import SourceDocument, DocumentBlock, ExtractionWarning
from agentpack.parsers.base import Parser

# Module-level singleton: DocumentConverter is expensive to construct (loads ML models).
# Shared across all PDFParser instances in the same process.
_converter = None


def _get_converter():
    global _converter
    if _converter is None:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat

        opts = PdfPipelineOptions()
        # Avoid MPS float64 crash on Apple Silicon; CPU is fine for batch PDF work.
        opts.accelerator_options.device = "cpu"
        _converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )
    return _converter


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
                    message="PDF file has no pages.",
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
                        page=page_num + 1,
                    ))
                else:
                    warnings.append(ExtractionWarning(
                        source_id=source_id,
                        page=page_num + 1,
                        type="low_text_density",
                        message=f"Page {page_num + 1} has little or no text.",
                    ))
        except Exception as e:
            warnings.append(ExtractionWarning(
                source_id=source_id,
                type="parse_error",
                message=f"Failed to parse PDF (fast mode): {str(e)}",
            ))

        return SourceDocument(
            source_id=source_id,
            path=file_path.name,
            type="pdf",
            checksum=checksum,
            blocks=blocks,
            warnings=warnings,
        )

    def _parse_semantic(self, file_path: Path, source_id: str) -> SourceDocument:
        with open(file_path, "rb") as f:
            content = f.read()
        checksum = hashlib.sha256(content).hexdigest()

        blocks = []
        warnings = []

        try:
            from docling.document_converter import ConversionStatus
            from docling.datamodel.document import SectionHeaderItem, TextItem, TableItem

            converter = _get_converter()
            result = converter.convert(file_path)

            if result.status != ConversionStatus.SUCCESS:
                raise RuntimeError(f"Docling conversion status: {result.status}")

            section_path: list[str] = []

            for item, _level in result.document.iterate_items():
                page = None
                if hasattr(item, "prov") and item.prov:
                    page = item.prov[0].page_no

                if isinstance(item, SectionHeaderItem):
                    # Maintain section_path stack based on heading level
                    level = getattr(item, "level", 1)
                    # Truncate stack to current level then push
                    section_path = section_path[:level - 1]
                    section_path.append(item.text)
                    blocks.append(DocumentBlock(
                        block_id=f"{source_id}_h{len(blocks)}",
                        source_id=source_id,
                        type="heading",
                        text=item.text,
                        page=page,
                        section_path=list(section_path),
                    ))

                elif isinstance(item, TextItem):
                    if not item.text.strip():
                        continue
                    blocks.append(DocumentBlock(
                        block_id=f"{source_id}_p{len(blocks)}",
                        source_id=source_id,
                        type="paragraph",
                        text=item.text.strip(),
                        page=page,
                        section_path=list(section_path),
                    ))

                elif isinstance(item, TableItem):
                    try:
                        table_md = item.export_to_markdown(doc=result.document)
                    except Exception:
                        table_md = str(item)
                    if table_md.strip():
                        blocks.append(DocumentBlock(
                            block_id=f"{source_id}_t{len(blocks)}",
                            source_id=source_id,
                            type="table",
                            text=table_md.strip(),
                            page=page,
                            section_path=list(section_path),
                        ))

        except Exception as e:
            warnings.append(ExtractionWarning(
                source_id=source_id,
                type="parse_error",
                message=f"Failed to parse PDF with Docling: {str(e)}",
            ))

        return SourceDocument(
            source_id=source_id,
            path=file_path.name,
            type="pdf",
            checksum=checksum,
            blocks=blocks,
            warnings=warnings,
        )

    def parse(self, file_path: Path, source_id: str) -> SourceDocument:
        if self.fast_pdf:
            return self._parse_fast_spatial(file_path, source_id)

        try:
            import docling  # noqa: F401
        except ImportError:
            doc = self._parse_fast_spatial(file_path, source_id)
            doc.warnings.append(ExtractionWarning(
                source_id=source_id,
                type="import_error",
                message="docling is not installed. Falling back to fast_pdf mode.",
            ))
            return doc

        return self._parse_semantic(file_path, source_id)
