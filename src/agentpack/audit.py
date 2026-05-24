import yaml
from pathlib import Path

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
            
    warnings = []
    for source in sources:
        for warning in source.get("warnings", []):
            warnings.append(f"Source {source.get('id')}: [{warning.get('type')}] {warning.get('message')}")
            
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
    
    if warnings:
        for warning in warnings:
            report.append(f"- {warning}")
    else:
        report.append("- No extraction warnings.")
        
    # Write report
    report_text = "\n".join(report)
    report_path = base_path / "reports" / "validation_report.md"
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
        
    return report_text
