import os
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict

from agentpack.scanner import scan_directory
from agentpack.parsers.text_parser import TextParser
from agentpack.parsers.markdown_parser import MarkdownParser
from agentpack.parsers.csv_parser import CSVParser
from agentpack.parsers.pdf_parser import PDFParser
from agentpack.chunker import chunk_document, Chunk
from agentpack.models import SourceDocument

def get_parser(suffix: str):
    suffix = suffix.lower()
    if suffix == ".txt":
        return TextParser()
    elif suffix == ".md":
        return MarkdownParser()
    elif suffix == ".csv":
        return CSVParser()
    elif suffix == ".pdf":
        return PDFParser()
    return None

def write_pack(
    input_dir: str, 
    output_dir: str,
    include_patterns: List[str] = None,
    exclude_patterns: List[str] = None,
    no_gitignore: bool = False,
    no_default_patterns: bool = False,
    include_hidden: bool = False,
    verbose: bool = False,
    quiet: bool = False,
    remove_empty_lines: bool = False
):
    in_path = Path(input_dir)
    out_path = Path(output_dir)
    
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "chunks").mkdir(exist_ok=True)
    (out_path / "tables").mkdir(exist_ok=True)
    (out_path / "reports").mkdir(exist_ok=True)
    
    files = scan_directory(
        input_dir,
        include_hidden=include_hidden,
        no_gitignore=no_gitignore,
        no_default_patterns=no_default_patterns,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns
    )
    
    if verbose and not quiet:
        print(f"Found {len(files)} files to pack.")
    
    sources = []
    all_chunks = []
    
    for i, file_path in enumerate(files):
        source_id = f"src_{i:03d}"
        parser = get_parser(file_path.suffix)
        if not parser:
            continue
            
        if verbose and not quiet:
            print(f"Parsing: {file_path}")
            
        if hasattr(parser, 'remove_empty_lines'):
            parser.remove_empty_lines = remove_empty_lines
            
        doc: SourceDocument = parser.parse(file_path, source_id)
        
        # Save table texts to tables dir if they are tables
        # For MVP, CSV tables are blocks with type 'table'
        for block in doc.blocks:
            if block.type == "table":
                # Write to tables dir
                table_path = out_path / "tables" / f"{block.block_id}.csv"
                with open(table_path, "w", encoding="utf-8") as f:
                    f.write(block.text)
        
        doc_chunks = chunk_document(doc)
        all_chunks.extend(doc_chunks)
        
        sources.append({
            "id": source_id,
            "path": file_path.name,
            "type": doc.type,
            "checksum": doc.checksum,
            "status": "success",
            "warnings": [w.dict() for w in doc.warnings]
        })

    # Write chunks to disk
    chunks_meta = []
    for chunk in all_chunks:
        chunk_file_path = out_path / chunk.path
        with open(chunk_file_path, "w", encoding="utf-8") as f:
            f.write(chunk.content)
            
        chunks_meta.append({
            "id": chunk.chunk_id,
            "source_id": chunk.source_id,
            "path": chunk.path,
            "token_count": chunk.token_count,
            "citation": chunk.metadata
        })
        
    manifest = {
        "pack": {
            "name": in_path.name,
            "version": "0.1.0",
            "generated_at": datetime.now(timezone.utc).isoformat()
        },
        "sources": sources,
        "chunks": chunks_meta,
        "tables": [],
        "agent": {
            "instructions": [
                "Use citations when answering.",
                "Prefer raw chunks over summaries.",
                "Say not found when the corpus does not contain the answer."
            ]
        }
    }
    
    with open(out_path / "manifest.yml", "w", encoding="utf-8") as f:
        yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)
        
    # Write a simple pack report
    with open(out_path / "reports" / "pack_report.md", "w", encoding="utf-8") as f:
        f.write(f"# Pack Report\n\nGenerated from {input_dir}\n")
        f.write(f"- Sources: {len(sources)}\n")
        f.write(f"- Chunks: {len(all_chunks)}\n")
        
    print(f"Pack generated at {out_path}")
