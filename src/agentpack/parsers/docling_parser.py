"""
DoclingParser: handle docx, pptx, xlsx, and html via Docling's structured tree.
Reuses the module-level DocumentConverter singleton from pdf_parser.
"""
import hashlib
from pathlib import Path

from agentpack.models import SourceDocument, DocumentBlock, ExtractionWarning
from agentpack.parsers.base import Parser

_SUPPORTED = {".docx", ".pptx", ".xlsx", ".html", ".htm"}


class DoclingParser(Parser):
    def parse(self, file_path: Path, source_id: str) -> SourceDocument:
        with open(file_path, "rb") as f:
            content = f.read()
        checksum = hashlib.sha256(content).hexdigest()

        blocks = []
        warnings = []

        try:
            import docling  # noqa: F401
        except ImportError:
            warnings.append(ExtractionWarning(
                source_id=source_id,
                type="import_error",
                message="docling is not installed; cannot parse office/html files.",
            ))
            return SourceDocument(
                source_id=source_id,
                path=file_path.name,
                type=file_path.suffix.lstrip(".").lower(),
                checksum=checksum,
                blocks=blocks,
                warnings=warnings,
            )

        try:
            from agentpack.parsers.pdf_parser import _get_converter
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
                    level = getattr(item, "level", 1)
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
                message=f"Failed to parse {file_path.suffix} with Docling: {str(e)}",
            ))

        doc_type = file_path.suffix.lstrip(".").lower()
        return SourceDocument(
            source_id=source_id,
            path=file_path.name,
            type=doc_type,
            checksum=checksum,
            blocks=blocks,
            warnings=warnings,
        )
