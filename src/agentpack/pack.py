import hashlib
import os
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from importlib.metadata import version as _pkg_version, PackageNotFoundError
from pathlib import Path
from typing import List, Dict, Optional

from agentpack.scanner import scan_directory
from agentpack.parsers.text_parser import TextParser
from agentpack.parsers.markdown_parser import MarkdownParser
from agentpack.parsers.csv_parser import CSVParser
from agentpack.parsers.pdf_parser import PDFParser
from agentpack.parsers.docling_parser import DoclingParser
from agentpack.chunker import chunk_document, Chunk
from agentpack.models import SourceDocument
from agentpack.cache import cache_get, cache_set, make_key


def _get_pack_version() -> str:
    try:
        return _pkg_version("agent-context-packager")
    except PackageNotFoundError:
        return "dev"


def _parser_cache_version() -> str:
    """Version string for L1 parse cache keys — bump when parse output schema changes."""
    return f"parser_v{_get_pack_version()}"

def _parse_one(
    file_path: Path,
    source_id: str,
    fast_pdf: bool,
    remove_empty_lines: bool,
    cache_dir: Path,
) -> Optional["SourceDocument"]:
    """Parse one file, respecting the L1 parse cache. Returns None if unsupported."""
    parser = get_parser(file_path.suffix, fast_pdf=fast_pdf)
    if parser is None:
        return None
    if hasattr(parser, "remove_empty_lines"):
        parser.remove_empty_lines = remove_empty_lines
    with open(file_path, "rb") as _f:
        file_hash = hashlib.sha256(_f.read()).hexdigest()
    cache_key = make_key(file_hash, _parser_cache_version(), str(fast_pdf))
    doc = cache_get(cache_dir, cache_key)
    if doc is None:
        doc = parser.parse(file_path, source_id)
        has_parse_error = any(w.type == "parse_error" for w in doc.warnings)
        if not has_parse_error:
            cache_set(cache_dir, cache_key, doc)
    else:
        doc.source_id = source_id
    return doc


def get_parser(suffix: str, fast_pdf: bool = False):
    suffix = suffix.lower()
    if suffix == ".txt":
        return TextParser()
    elif suffix == ".md":
        return MarkdownParser()
    elif suffix == ".csv":
        return CSVParser()
    elif suffix == ".pdf":
        return PDFParser(fast_pdf=fast_pdf)
    elif suffix in {".docx", ".pptx", ".xlsx", ".html", ".htm"}:
        return DoclingParser()
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
    remove_empty_lines: bool = False,
    fast_pdf: bool = False
):
    """
    Scans an input directory, parses supported files, chunks them, and generates a context pack.
    
    This acts as the main orchestration engine for AgentPack, coordinating the Scanner, Parsers,
    and Chunker to produce a finalized `manifest.yml` and structured context directory.

    Args:
        input_dir (str): The root directory containing raw documents to scan.
        output_dir (str): The destination directory where the pack will be written.
        include_patterns (List[str], optional): Glob patterns of files to exclusively include.
        exclude_patterns (List[str], optional): Glob patterns of files to exclude.
        no_gitignore (bool, optional): If True, ignores `.gitignore` and `.agentpackignore` files.
        no_default_patterns (bool, optional): If True, disables built-in ignore rules (e.g. `.git/`).
        include_hidden (bool, optional): If True, includes hidden files and directories.
        verbose (bool, optional): If True, enables detailed progress logging.
        quiet (bool, optional): If True, suppresses all non-error output.
        remove_empty_lines (bool, optional): If True, strips empty lines from parsed text/markdown blocks to save tokens.
    """
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
    all_tables = []
    cache_dir = out_path / ".cache"

    # Dispatch parallel parses; results keyed by index to preserve manifest order.
    indexed_files = [(i, fp) for i, fp in enumerate(files)
                     if get_parser(fp.suffix, fast_pdf=fast_pdf) is not None]
    docs_by_index: dict = {}

    max_workers = min(4, len(indexed_files)) if indexed_files else 1
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _parse_one, fp, f"src_{i:03d}", fast_pdf, remove_empty_lines, cache_dir
            ): i
            for i, fp in indexed_files
        }
        for future in as_completed(futures):
            idx = futures[future]
            doc = future.result()
            if doc is not None:
                docs_by_index[idx] = doc

    for i, file_path in indexed_files:
        doc = docs_by_index.get(i)
        if doc is None:
            continue
        source_id = f"src_{i:03d}"

        if verbose and not quiet:
            print(f"Parsed: {file_path}")

        for block in doc.blocks:
            if block.type == "table":
                table_path = out_path / "tables" / f"{block.block_id}.md"
                with open(table_path, "w", encoding="utf-8") as f:
                    f.write(block.text)
                all_tables.append({
                    "block_id": block.block_id,
                    "source_id": source_id,
                    "page": block.page,
                    "path": f"tables/{block.block_id}.md",
                })

        doc_chunks = chunk_document(doc)
        all_chunks.extend(doc_chunks)

        has_parse_error = any(w.type == "parse_error" for w in doc.warnings)
        if has_parse_error or len(doc_chunks) == 0:
            status = "failed"
            reason = next((w.message for w in doc.warnings if w.type == "parse_error"), "produced 0 chunks")
            if not quiet:
                print(f"  WARNING: {file_path.name} failed to index ({reason})")
        else:
            status = "success"

        sources.append({
            "id": source_id,
            "path": file_path.name,
            "type": doc.type,
            "checksum": doc.checksum,
            "status": status,
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
            "version": _get_pack_version(),
            "generated_at": datetime.now(timezone.utc).isoformat()
        },
        "sources": sources,
        "chunks": chunks_meta,
        "tables": all_tables,
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
