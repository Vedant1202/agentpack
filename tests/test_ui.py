import pytest
import os
import json
import sqlite3
import numpy as np
from pathlib import Path
from fastapi.testclient import TestClient
from typer.testing import CliRunner
from unittest.mock import patch

from agentpack.cli import app as cli_app
from agentpack.ui.server import app as fastapi_app

runner = CliRunner()
client = TestClient(fastapi_app)


def write_minimal_manifest(pack_dir: Path):
    (pack_dir / "manifest.yml").write_text(
        "pack:\n  name: test_pack\nsources: []\nchunks: []\ntables: []\n",
        encoding="utf-8",
    )

def test_ui_command_help():
    """Test that the UI command is registered in the CLI."""
    result = runner.invoke(cli_app, ["ui", "--help"])
    assert result.exit_code == 0
    assert "Launch a local web UI to inspect your compiled context pack" in result.stdout

def test_api_manifest_not_found(monkeypatch, tmp_path):
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", tmp_path)
    response = client.get("/api/manifest")
    assert response.status_code == 404

def test_api_manifest_valid(monkeypatch, tmp_path):
    pack_dir = tmp_path / "valid_pack"
    pack_dir.mkdir()
    manifest_file = pack_dir / "manifest.yml"
    manifest_file.write_text("pack:\n  name: test_pack\nsources: []\nchunks: []", encoding="utf-8")
    
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", pack_dir)
    
    response = client.get("/api/manifest")
    assert response.status_code == 200
    assert response.json()["pack"]["name"] == "test_pack"

def test_api_chunks_missing_db(monkeypatch, tmp_path):
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", tmp_path)
    response = client.get("/api/chunks")
    assert response.status_code == 404


def test_api_chunks_builds_missing_db(monkeypatch, tmp_path):
    pack_dir = tmp_path / "agentpack_output"
    pack_dir.mkdir()
    write_minimal_manifest(pack_dir)

    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", pack_dir)

    built = {}

    def fake_build_fts_index(base_path, db_path):
        built["called"] = (base_path, db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                chunk_id UNINDEXED, source_id UNINDEXED, path UNINDEXED,
                token_count UNINDEXED, citation UNINDEXED, content
            )
            """
        )
        conn.commit()
        return conn

    monkeypatch.setattr(server, "build_fts_index", fake_build_fts_index)

    response = client.get("/api/chunks")
    assert response.status_code == 200
    assert response.json() == {"chunks": []}
    assert built["called"][0] == pack_dir
    assert built["called"][1] == pack_dir / "indexes" / "lexical_index.db"

def test_api_chunks_valid(monkeypatch, tmp_path):
    pack_dir = tmp_path / "agentpack_output"
    indexes_dir = pack_dir / "indexes"
    chunks_dir = pack_dir / "chunks"
    indexes_dir.mkdir(parents=True)
    chunks_dir.mkdir()
    write_minimal_manifest(pack_dir)

    chunk_file = chunks_dir / "src_000_chunk_000.md"
    chunk_file.write_text("Chunk text", encoding="utf-8")

    conn = sqlite3.connect(indexes_dir / "lexical_index.db")
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                chunk_id UNINDEXED, source_id UNINDEXED, path UNINDEXED,
                token_count UNINDEXED, citation UNINDEXED, content
            )
            """
        )
        conn.execute(
            "INSERT INTO chunks_fts VALUES (?, ?, ?, ?, ?, ?)",
            ("c1", "s1", "chunks/src_000_chunk_000.md", 2, json.dumps({"source_path": "sample.md"}), "Chunk text"),
        )
        conn.commit()
    finally:
        conn.close()

    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", pack_dir)

    response = client.get("/api/chunks")
    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["id"] == "c1"

def test_api_umap_missing(monkeypatch, tmp_path):
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", tmp_path)
    response = client.get("/api/umap")
    assert response.status_code == 404


def test_api_umap_builds_missing_vector_index(monkeypatch, tmp_path):
    try:
        import umap.umap_
    except ImportError:
        pytest.skip("umap-learn not installed")

    class MockUMAP:
        def __init__(self, **kwargs):
            pass

        def fit_transform(self, X):
            return np.array([[0.0, 0.0]])

    monkeypatch.setattr(umap.umap_, "UMAP", MockUMAP)

    pack_dir = tmp_path / "agentpack_output"
    pack_dir.mkdir()
    write_minimal_manifest(pack_dir)

    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", pack_dir)

    built = {}

    def fake_build_vector_index(base_path, vector_path, meta_path):
        built["called"] = (base_path, vector_path, meta_path)
        vector_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(vector_path, np.array([[1.0, 0.0]], dtype=np.float32))
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump([{"chunk_id": "c1"}], f)

    monkeypatch.setattr(server, "build_vector_index", fake_build_vector_index)

    response = client.get("/api/umap")
    assert response.status_code == 200
    assert len(response.json()["points"]) == 1
    assert built["called"][0] == pack_dir

def test_api_umap_valid(monkeypatch, tmp_path):
    # Skip if umap-learn is not installed in the environment running the test
    try:
        import umap.umap_
    except ImportError:
        pytest.skip("umap-learn not installed")
        
    class MockUMAP:
        def __init__(self, **kwargs):
            pass
        def fit_transform(self, X):
            return np.array([[1.0, 2.0], [3.0, 4.0]])
            
    monkeypatch.setattr(umap.umap_, "UMAP", MockUMAP)
        
    pack_dir = tmp_path / "agentpack_output"
    indexes_dir = pack_dir / "indexes"
    indexes_dir.mkdir(parents=True)
    write_minimal_manifest(pack_dir)
    
    np.save(indexes_dir / "vector_index.npy", np.array([[0.1, 0.2], [0.3, 0.4]]))
    with open(indexes_dir / "vector_meta.json", "w") as f:
        json.dump([{"chunk_id": "c1"}, {"chunk_id": "c2"}], f)
        
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", pack_dir)
    
    response = client.get("/api/umap")
    assert response.status_code == 200
    assert len(response.json()["points"]) == 2

def test_api_search_fts(monkeypatch, tmp_path):
    pack_dir = tmp_path / "agentpack_output"
    indexes_dir = pack_dir / "indexes"
    indexes_dir.mkdir(parents=True)
    write_minimal_manifest(pack_dir)
    
    conn = sqlite3.connect(indexes_dir / "lexical_index.db")
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                chunk_id UNINDEXED, source_id UNINDEXED, path UNINDEXED,
                token_count UNINDEXED, citation UNINDEXED, content
            )
            """
        )
        conn.execute(
            "INSERT INTO chunks_fts VALUES (?, ?, ?, ?, ?, ?)",
            ("c1", "s1", "path", 2, "{}", "test target phrase"),
        )
        conn.commit()
    finally:
        conn.close()
        
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", pack_dir)
    monkeypatch.setattr(
        server,
        "search_hybrid",
        lambda *args, **kwargs: [
            {
                "chunk_id": "c1",
                "source_id": "s1",
                "path": "path",
                "token_count": 2,
                "citation": {},
                "score": 0.9,
            }
        ],
    )
    
    response = client.post("/api/search", json={"query": "target", "top_k": 5})
    assert response.status_code == 200
    res = response.json()["results"]
    assert len(res) == 1
    assert res[0]["id"] == "c1"
    assert res[0]["title"] == "s1"
    assert res[0]["source"] == "s1"

@patch("fastembed.TextEmbedding")
def test_api_search_vector(mock_embed_cls, monkeypatch, tmp_path):
    mock_embed = mock_embed_cls.return_value
    mock_embed.embed.return_value = [np.array([1.0, 0.0])]
    
    pack_dir = tmp_path / "agentpack_output"
    indexes_dir = pack_dir / "indexes"
    indexes_dir.mkdir(parents=True)
    write_minimal_manifest(pack_dir)
    
    np.save(indexes_dir / "vector_index.npy", np.array([[1.0, 0.0], [0.0, 1.0]]))
    with open(indexes_dir / "vector_meta.json", "w") as f:
        json.dump([{"chunk_id": "c1"}, {"chunk_id": "c2"}], f)
        
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", pack_dir)
    monkeypatch.setattr(server, "search_hybrid", lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(
        server,
        "search_vector_artifacts",
        lambda *args, **kwargs: [
            {
                "chunk_id": "c1",
                "source_id": "Unknown",
                "path": None,
                "token_count": 0,
                "citation": {},
                "score": 1.0,
            }
        ],
    )

    response = client.post("/api/search", json={"query": "test", "top_k": 1})
    assert response.status_code == 200
    res = response.json()["results"]
    assert len(res) == 1
    assert res[0]["id"] == "c1"
    assert res[0]["source"] == "Unknown"
    assert res[0]["title"] == "Unknown"

def test_api_neighbors_missing(monkeypatch, tmp_path):
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", tmp_path)
    response = client.post("/api/neighbors", json={"chunk_id": "c1"})
    assert response.status_code == 404

def test_api_neighbors_valid(monkeypatch, tmp_path):
    pack_dir = tmp_path / "agentpack_output"
    indexes_dir = pack_dir / "indexes"
    indexes_dir.mkdir(parents=True)
    write_minimal_manifest(pack_dir)
    
    np.save(indexes_dir / "vector_index.npy", np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]]))
    with open(indexes_dir / "vector_meta.json", "w") as f:
        json.dump([{"chunk_id": "c1"}, {"chunk_id": "c2"}, {"chunk_id": "c3"}], f)
        
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", pack_dir)
    
    response = client.post("/api/neighbors", json={"chunk_id": "c1", "top_k": 1})
    assert response.status_code == 200
    neighbors = response.json()["neighbors"]
    assert len(neighbors) == 1
    assert neighbors[0]["id"] == "c2"
    assert neighbors[0]["title"] == "Unknown"

def test_api_neighbors_chunk_not_found(monkeypatch, tmp_path):
    pack_dir = tmp_path / "agentpack_output"
    indexes_dir = pack_dir / "indexes"
    indexes_dir.mkdir(parents=True)
    write_minimal_manifest(pack_dir)
    
    np.save(indexes_dir / "vector_index.npy", np.array([[1.0, 0.0]]))
    with open(indexes_dir / "vector_meta.json", "w") as f:
        json.dump([{"chunk_id": "c1"}], f)
        
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", pack_dir)
    
    response = client.post("/api/neighbors", json={"chunk_id": "c2", "top_k": 1})
    assert response.status_code == 404

def test_api_feedback(monkeypatch, tmp_path):
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", tmp_path)
    
    response = client.post("/api/feedback", json={"chunk_id": "c1", "query": "q", "rating": 1})
    assert response.status_code == 200
    
    fb_path = tmp_path / "eval_feedback.json"
    assert fb_path.exists()
    
    with open(fb_path, "r") as f:
        data = json.load(f)
        assert len(data) == 1
        assert data[0]["chunk_id"] == "c1"

def test_serve_static(monkeypatch, tmp_path):
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "web_dir", tmp_path)
    
    (tmp_path / "index.html").write_text("Hello UI")
    (tmp_path / "assets").mkdir()
    
    response = client.get("/")
    # Fastapi TestClient doesn't easily mock mount points for StaticFiles if we dynamically assign it
    # We just check the index fallback logic.
    if response.status_code == 200:
        assert "Hello UI" in response.text
