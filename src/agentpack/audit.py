import yaml
from collections import defaultdict
from pathlib import Path

# Types that indicate a source failed to produce usable output at all —
# listed first/most prominent so they can't be lost in a scroll of lower-
# severity findings (e.g. many benign hidden_text warnings from OCR'd PDFs).
_PRIORITY_WARNING_TYPES = ["parse_error", "import_error"]


def _ordered_warning_types(present_types) -> list:
    """Priority types first (only if present), then everything else sorted
    alphabetically — deterministic regardless of file-scan order."""
    present = set(present_types)
    ordered = [t for t in _PRIORITY_WARNING_TYPES if t in present]
    remaining = sorted(present - set(_PRIORITY_WARNING_TYPES))
    return ordered + remaining


def audit_pack(pack_dir: str) -> str:
    """Generates an audit report for an agentpack output directory."""
    base_path = Path(pack_dir)
    manifest_path = base_path / "manifest.yml"
    
    if not manifest_path.exists():
        return f"Error: Manifest not found at {manifest_path}"
        
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
    except Exception as e:
        return f"Error: Failed to parse manifest YAML: {e}"
        
    sources = manifest.get("sources", [])
    chunks = manifest.get("chunks", [])
    tables = manifest.get("tables", [])
    
    files_processed = len(sources)
    total_chunks = len(chunks)
    total_tables = len(tables)
    total_tokens = sum(chunk.get("token_count", 0) for chunk in chunks)
    
    max_chunk_size = 0
    largest_chunk_id = None
    for chunk in chunks:
        if chunk.get("token_count", 0) > max_chunk_size:
            max_chunk_size = chunk.get("token_count", 0)
            largest_chunk_id = chunk.get("id")
            
    warnings_by_type = defaultdict(list)
    for source in sources:
        for warning in source.get("warnings", []):
            wtype = warning.get("type", "unknown")
            warnings_by_type[wtype].append(f"Source {source.get('id')}: {warning.get('message')}")

    # Format report
    report = [
        f"# AgentPack Audit Report for '{manifest.get('pack', {}).get('name', 'Unknown')}'",
        f"Generated at: {manifest.get('pack', {}).get('generated_at', 'Unknown')}\n",
        "## Statistics",
        f"- **Files Processed:** {files_processed}",
        f"- **Total Chunks:** {total_chunks}",
        f"- **Total Tables:** {total_tables}",
        f"- **Total Tokens:** {total_tokens}",
        f"- **Largest Chunk:** {max_chunk_size} tokens (ID: {largest_chunk_id})\n",
        "## Extraction Warnings",
    ]

    if warnings_by_type:
        for wtype in _ordered_warning_types(warnings_by_type.keys()):
            entries = warnings_by_type[wtype]
            report.append(f"\n### {wtype} ({len(entries)})")
            for entry in entries:
                report.append(f"- {entry}")
    else:
        report.append("- No extraction warnings.")
        
    # Write report
    report_text = "\n".join(report)
    report_path = base_path / "reports" / "validation_report.md"
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
        
    return report_text
