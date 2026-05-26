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
