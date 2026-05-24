import hashlib
import pandas as pd
from pathlib import Path
from agentpack.models import SourceDocument, DocumentBlock, ExtractionWarning
from agentpack.parsers.base import Parser

class CSVParser(Parser):
    def parse(self, file_path: Path, source_id: str) -> SourceDocument:
        with open(file_path, "rb") as f:
            content = f.read()
        checksum = hashlib.sha256(content).hexdigest()
        
        blocks = []
        warnings = []
        
        try:
            df = pd.read_csv(file_path)
            if df.empty:
                warnings.append(ExtractionWarning(
                    source_id=source_id,
                    type="empty_file",
                    message="CSV file is empty."
                ))
            else:
                # Convert the entire CSV to a single markdown table text for the block for now
                table_text = df.to_markdown(index=False)
                blocks.append(DocumentBlock(
                    block_id=f"{source_id}_table0",
                    source_id=source_id,
                    type="table",
                    text=table_text,
                    row_range=(1, len(df))
                ))
        except Exception as e:
            warnings.append(ExtractionWarning(
                source_id=source_id,
                type="parse_error",
                message=f"Failed to parse CSV: {str(e)}"
            ))
            
        return SourceDocument(
            source_id=source_id,
            path=file_path.name,
            type="csv",
            checksum=checksum,
            blocks=blocks,
            warnings=warnings
        )
