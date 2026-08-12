import yaml
import pytest
from pathlib import Path
from agentpack.validate import validate_pack

def test_validate_pack_missing_manifest(tmp_path):
    errors = validate_pack(str(tmp_path))
    assert len(errors) == 1
    assert "Manifest not found" in errors[0]

def test_validate_pack_invalid_yaml(tmp_path):
    manifest_path = tmp_path / "manifest.yml"
    manifest_path.write_text("invalid: [yaml: content")
    errors = validate_pack(str(tmp_path))
    assert len(errors) == 1
    assert "Failed to parse manifest YAML" in errors[0]

def test_validate_pack_empty_manifest(tmp_path):
    manifest_path = tmp_path / "manifest.yml"
    manifest_path.write_text("")
    errors = validate_pack(str(tmp_path))
    assert len(errors) == 1
    assert "Manifest is empty." in errors[0]

def test_validate_pack_missing_keys(tmp_path):
    manifest_path = tmp_path / "manifest.yml"
    with open(manifest_path, "w") as f:
        yaml.dump({"pack": "some_pack"}, f)
    
    errors = validate_pack(str(tmp_path))
    assert any("missing top-level key: 'sources'" in e for e in errors)
    assert any("missing top-level key: 'chunks'" in e for e in errors)
    assert any("missing top-level key: 'tables'" in e for e in errors)

def test_validate_pack_chunk_errors(tmp_path):
    manifest_path = tmp_path / "manifest.yml"
    
    data = {
        "pack": {"name": "test"},
        "sources": [{"id": "src1"}],
        "chunks": [
            {"id": "c1", "source_id": "src2", "path": "c1.json"}, # Unknown source
            {"id": "c2", "source_id": "src1"}, # Missing path
            {"id": "c3", "source_id": "src1", "path": "c3.json"}, # Missing file
            {"id": "c4", "source_id": "src1", "path": "c4.json", "token_count": 5000} # Exceeds tokens
        ],
        "tables": []
    }
    
    with open(manifest_path, "w") as f:
        yaml.dump(data, f)
        
    # Create the c4 file so it doesn't fail on missing file
    (tmp_path / "c4.json").write_text("{}")
        
    errors = validate_pack(str(tmp_path))
    
    assert any("unknown source_id 'src2'" in e for e in errors)
    assert any("missing path attribute" in e for e in errors)
    assert any("Chunk file missing" in e for e in errors)
    assert any("exceeds safe token limit" in e for e in errors)

def test_validate_pack_table_errors(tmp_path):
    manifest_path = tmp_path / "manifest.yml"
    
    data = {
        "pack": {"name": "test"},
        "sources": [{"id": "src1"}],
        "chunks": [],
        "tables": [
            {"id": "t1", "source_id": "src2", "path": "t1.csv"}, # Unknown source
            {"id": "t2", "source_id": "src1", "path": "t2.csv"}  # Missing file
        ]
    }
    
    with open(manifest_path, "w") as f:
        yaml.dump(data, f)
        
    errors = validate_pack(str(tmp_path))
    assert any("unknown source_id 'src2'" in e for e in errors)
    assert any("Table file missing" in e for e in errors)

def test_validate_pack_valid(tmp_path):
    manifest_path = tmp_path / "manifest.yml"

    data = {
        "pack": {"name": "test"},
        "sources": [{"id": "src1"}],
        "chunks": [
            {"id": "c1", "source_id": "src1", "path": "c1.json", "token_count": 100}
        ],
        "tables": [
            {"id": "t1", "source_id": "src1", "path": "t1.csv"}
        ]
    }

    with open(manifest_path, "w") as f:
        yaml.dump(data, f)

    (tmp_path / "c1.json").write_text("{}")
    (tmp_path / "t1.csv").write_text("a,b")

    errors = validate_pack(str(tmp_path))
    assert len(errors) == 0


def _write_minimal_manifest(tmp_path, sources=("src1", "src2")):
    manifest_path = tmp_path / "manifest.yml"
    data = {
        "pack": {"name": "test"},
        "sources": [{"id": sid} for sid in sources],
        "chunks": [],
        "tables": [],
    }
    with open(manifest_path, "w") as f:
        yaml.dump(data, f)


def _write_minimal_map(tmp_path, source_id="src1", node_id="s1_sec0"):
    map_path = tmp_path / "map.yml"
    data = {
        "documents": [
            {"source_id": source_id, "sections": [{"node_id": node_id, "title": "Intro", "nodes": []}]}
        ]
    }
    with open(map_path, "w") as f:
        yaml.dump(data, f)


def _valid_graph_data():
    return {
        "graph_version": 1,
        "pack": {"name": "test"},
        "params": {},
        "nodes": [
            {"id": "src1", "kind": "document", "label": "doc1.md", "doc": None, "community": 0},
            {"id": "src2", "kind": "document", "label": "doc2.md", "doc": None, "community": 1},
            {"id": "s1_sec0", "kind": "section", "label": "Intro", "doc": "src1", "community": 0},
        ],
        "edges": [
            {"source": "src1", "target": "s1_sec0", "relation": "contains", "basis": "structural"},
        ],
        "communities": [
            {"id": 0, "label": "doc1.md", "size": 2},
            {"id": 1, "label": "doc2.md", "size": 1},
        ],
    }


def test_validate_pack_graph_missing_is_not_error(tmp_path):
    _write_minimal_manifest(tmp_path)
    _write_minimal_map(tmp_path)
    errors = validate_pack(str(tmp_path))
    assert len(errors) == 0


def test_validate_pack_graph_valid(tmp_path):
    _write_minimal_manifest(tmp_path)
    _write_minimal_map(tmp_path)
    with open(tmp_path / "graph.yml", "w") as f:
        yaml.dump(_valid_graph_data(), f)
    errors = validate_pack(str(tmp_path))
    assert len(errors) == 0


def test_validate_pack_graph_invalid_yaml(tmp_path):
    _write_minimal_manifest(tmp_path)
    (tmp_path / "graph.yml").write_text(":\n  - not: [valid, yaml")
    errors = validate_pack(str(tmp_path))
    assert any("Failed to parse graph.yml" in e for e in errors)


def test_validate_pack_graph_edge_unknown_node(tmp_path):
    _write_minimal_manifest(tmp_path)
    _write_minimal_map(tmp_path)
    data = _valid_graph_data()
    data["edges"].append({"source": "src1", "target": "ghost_node", "relation": "mentions", "basis": "keyphrase"})
    with open(tmp_path / "graph.yml", "w") as f:
        yaml.dump(data, f)
    errors = validate_pack(str(tmp_path))
    assert any("unknown target node 'ghost_node'" in e for e in errors)


def test_validate_pack_graph_section_unknown_map_id(tmp_path):
    _write_minimal_manifest(tmp_path)
    _write_minimal_map(tmp_path)  # only defines node_id "s1_sec0"
    data = _valid_graph_data()
    data["nodes"][2]["id"] = "s1_sec_FAKE"
    data["edges"][0]["target"] = "s1_sec_FAKE"
    with open(tmp_path / "graph.yml", "w") as f:
        yaml.dump(data, f)
    errors = validate_pack(str(tmp_path))
    assert any("s1_sec_FAKE" in e and "map.yml" in e for e in errors)


def test_validate_pack_graph_doc_ref_unknown_source(tmp_path):
    _write_minimal_manifest(tmp_path)
    _write_minimal_map(tmp_path)
    data = _valid_graph_data()
    data["nodes"].append({"id": "s2_sec0", "kind": "section", "label": "Ghost", "doc": "ghost_src", "community": None})
    with open(tmp_path / "graph.yml", "w") as f:
        yaml.dump(data, f)
    errors = validate_pack(str(tmp_path))
    assert any("unknown source_id 'ghost_src'" in e for e in errors)


def test_validate_pack_graph_community_unknown(tmp_path):
    _write_minimal_manifest(tmp_path)
    _write_minimal_map(tmp_path)
    data = _valid_graph_data()
    data["nodes"][0]["community"] = 99
    with open(tmp_path / "graph.yml", "w") as f:
        yaml.dump(data, f)
    errors = validate_pack(str(tmp_path))
    assert any("unknown community id '99'" in e for e in errors)
