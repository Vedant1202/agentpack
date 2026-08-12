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

    # Validate the optional knowledge map (map.yml). Its absence is not an error.
    map_path = base_path / "map.yml"
    if map_path.exists():
        chunk_ids = {c.get("id") for c in manifest.get("chunks", []) if c.get("id")}
        errors.extend(_validate_map(map_path, source_ids, chunk_ids))

    # Validate the optional corpus concept graph (graph.yml). Its absence is not an error.
    graph_path = base_path / "graph.yml"
    if graph_path.exists():
        map_node_ids = _collect_map_node_ids(map_path)
        errors.extend(_validate_graph(graph_path, source_ids, map_node_ids))

    return errors


def _validate_map(map_path: Path, source_ids: set, chunk_ids: set) -> List[str]:
    """Validate map.yml referential integrity against the manifest."""
    errors: List[str] = []
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            kmap = yaml.safe_load(f)
    except Exception as e:
        return [f"Failed to parse map.yml: {e}"]
    if not kmap:
        return ["map.yml is empty."]

    def walk(nodes):
        for node in nodes or []:
            node_id = node.get("node_id", "<unknown>")
            for cid in node.get("chunk_ids", []) or []:
                if cid not in chunk_ids:
                    errors.append(f"Map node '{node_id}' references unknown chunk_id '{cid}'")
            walk(node.get("nodes", []))

    for doc in kmap.get("documents", []) or []:
        sid = doc.get("source_id")
        if sid not in source_ids:
            errors.append(f"Map document refers to unknown source_id '{sid}'")
        walk(doc.get("sections", []))
    return errors


def _collect_map_node_ids(map_path: Path) -> set:
    """All node_ids appearing anywhere in map.yml's section trees, at any
    depth. Mirrors _validate_map's own recursive walk, but collects ids
    instead of checking chunk_id references -- used by _validate_graph to
    confirm graph.yml's section nodes resolve to real map.yml nodes.
    A missing or corrupt map.yml yields an empty set rather than raising;
    graph.yml built without a map.yml present has no section nodes to
    begin with (grapher.py degrades to document-only nodes), so this
    never produces a false FK violation on a genuinely valid graph.
    """
    if not map_path.exists():
        return set()
    try:
        with open(map_path, "r", encoding="utf-8") as f:
            kmap = yaml.safe_load(f)
    except Exception:
        return set()
    if not kmap:
        return set()

    ids: set = set()

    def walk(nodes):
        for node in nodes or []:
            node_id = node.get("node_id")
            if node_id:
                ids.add(node_id)
            walk(node.get("nodes", []))

    for doc in kmap.get("documents", []) or []:
        walk(doc.get("sections", []))
    return ids


def _validate_graph(graph_path: Path, source_ids: set, map_node_ids: set) -> List[str]:
    """Validate graph.yml referential integrity (spec §3): every node's
    `doc` ref resolves to a real manifest source_id; every section node's
    id is a real map.yml node_id; every edge endpoint is a node in this
    same graph; every node's `community` is a real community id."""
    errors: List[str] = []
    try:
        with open(graph_path, "r", encoding="utf-8") as f:
            graph = yaml.safe_load(f)
    except Exception as e:
        return [f"Failed to parse graph.yml: {e}"]
    if not graph:
        return ["graph.yml is empty."]

    nodes = graph.get("nodes", []) or []
    node_ids = {n.get("id") for n in nodes if n.get("id")}
    community_ids = {
        c.get("id") for c in (graph.get("communities", []) or []) if c.get("id") is not None
    }

    for node in nodes:
        node_id = node.get("id", "<unknown>")
        doc_ref = node.get("doc")
        if doc_ref is not None and doc_ref not in source_ids:
            errors.append(f"Graph node '{node_id}' refers to unknown source_id '{doc_ref}'")
        if node.get("kind") == "section" and node_id not in map_node_ids:
            errors.append(f"Graph section node '{node_id}' has no matching map.yml node_id")
        community = node.get("community")
        if community is not None and community not in community_ids:
            errors.append(f"Graph node '{node_id}' refers to unknown community id '{community}'")

    for edge in graph.get("edges", []) or []:
        source = edge.get("source")
        target = edge.get("target")
        if source not in node_ids:
            errors.append(f"Graph edge references unknown source node '{source}'")
        if target not in node_ids:
            errors.append(f"Graph edge references unknown target node '{target}'")

    return errors
