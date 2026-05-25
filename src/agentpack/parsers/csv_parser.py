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
                # Break CSV into 50-row chunks to preserve headers and avoid massive blocks
                chunk_size = 50
                for start_row in range(0, len(df), chunk_size):
                    end_row = min(start_row + chunk_size, len(df))
                    df_chunk = df.iloc[start_row:end_row]
                    table_text = df_chunk.to_markdown(index=False)
                    blocks.append(DocumentBlock(
                        block_id=f"{source_id}_table_{start_row}",
                        source_id=source_id,
                        type="table",
                        text=table_text,
                        row_range=(start_row + 1, end_row)
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
