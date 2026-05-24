import yaml
from pathlib import Path
from typing import List

def validate_pack(pack_dir: str) -> List[str]:
    """Validates the integrity of an agentpack output directory."""
    errors = []
    base_path = Path(pack_dir)
    manifest_path = base_path / "manifest.yml"
    
    if not manifest_path.exists():
        return [f"Manifest not found at {manifest_path}"]
        
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = yaml.safe_load(f)
    except Exception as e:
        return [f"Failed to parse manifest YAML: {e}"]
        
    if not manifest:
        return ["Manifest is empty."]
        
    # Check basic schema
    for key in ["pack", "sources", "chunks", "tables"]:
        if key not in manifest:
            errors.append(f"Manifest missing top-level key: '{key}'")
            
    if errors:
        return errors
        
    source_ids = {s.get("id") for s in manifest.get("sources", []) if s.get("id")}
    
    # Validate chunks
    for i, chunk in enumerate(manifest.get("chunks", [])):
        chunk_id = chunk.get("id", f"unknown_index_{i}")
        source_id = chunk.get("source_id")
        
        if source_id not in source_ids:
            errors.append(f"Chunk '{chunk_id}' refers to unknown source_id '{source_id}'")
            
        chunk_path = chunk.get("path")
        if not chunk_path:
            errors.append(f"Chunk '{chunk_id}' missing path attribute")
        else:
            full_path = base_path / chunk_path
            if not full_path.exists():
                errors.append(f"Chunk file missing: {full_path}")
                
        # Token validation (MVP arbitrary safe limit check)
        if chunk.get("token_count", 0) > 4000:
            errors.append(f"Chunk '{chunk_id}' exceeds safe token limit: {chunk.get('token_count')}")

    # Validate tables
    for i, table in enumerate(manifest.get("tables", [])):
        table_id = table.get("id", f"unknown_index_{i}")
        source_id = table.get("source_id")
        
        if source_id not in source_ids:
            errors.append(f"Table '{table_id}' refers to unknown source_id '{source_id}'")
            
        table_path = table.get("path")
        if table_path:
            full_path = base_path / table_path
            if not full_path.exists():
                errors.append(f"Table file missing: {full_path}")

    return errors
