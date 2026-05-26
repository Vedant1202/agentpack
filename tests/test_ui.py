import pytest
import os
import json
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agentpack.cli import app as cli_app
from agentpack.ui.server import app as fastapi_app

runner = CliRunner()
client = TestClient(fastapi_app)

def test_ui_command_help():
    """Test that the UI command is registered in the CLI."""
    result = runner.invoke(cli_app, ["ui", "--help"])
    assert result.exit_code == 0
    assert "Launch a local web UI to inspect your compiled context pack" in result.stdout

def test_api_manifest_not_found(monkeypatch, tmp_path):
    """Test the /api/manifest endpoint handles missing data gracefully."""
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", tmp_path)
    response = client.get("/api/manifest")
    assert response.status_code == 404
    assert "Manifest not found" in response.json()["detail"]

def test_api_manifest_valid(monkeypatch, tmp_path):
    """Test the /api/manifest endpoint with valid data."""
    pack_dir = tmp_path / "valid_pack"
    pack_dir.mkdir()
    manifest_file = pack_dir / "manifest.yml"
    manifest_file.write_text("pack:\n  name: test_pack\nsources: []\nchunks: []", encoding="utf-8")
    
    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", pack_dir)
    
    response = client.get("/api/manifest")
    assert response.status_code == 200
    assert response.json()["pack"]["name"] == "test_pack"

def test_api_chunks_includes_file_paths(monkeypatch, tmp_path):
    """Test that chunk metadata includes inspectable pack and source paths."""
    pack_dir = tmp_path / "agentpack_output"
    indexes_dir = pack_dir / "indexes"
    chunks_dir = pack_dir / "chunks"
    corpus_dir = tmp_path / "corpus"
    indexes_dir.mkdir(parents=True)
    chunks_dir.mkdir()
    corpus_dir.mkdir()

    source_file = corpus_dir / "sample.md"
    source_file.write_text("Source text", encoding="utf-8")
    chunk_file = chunks_dir / "src_000_chunk_000.md"
    chunk_file.write_text("Chunk text", encoding="utf-8")

    conn = sqlite3.connect(indexes_dir / "lexical_index.db")
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE chunks_fts USING fts5(
                chunk_id UNINDEXED,
                source_id UNINDEXED,
                path UNINDEXED,
                token_count UNINDEXED,
                citation UNINDEXED,
                content
            )
            """
        )
        conn.execute(
            "INSERT INTO chunks_fts (chunk_id, source_id, path, token_count, citation, content) VALUES (?, ?, ?, ?, ?, ?)",
            (
                "src_000_chunk_000",
                "src_000",
                "chunks/src_000_chunk_000.md",
                2,
                json.dumps({"source_path": "sample.md"}),
                "Chunk text",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    import agentpack.ui.server as server
    monkeypatch.setattr(server, "PACK_DIR", pack_dir)

    response = client.get("/api/chunks")
    assert response.status_code == 200
    chunk = response.json()["chunks"][0]
    assert chunk["path"] == "chunks/src_000_chunk_000.md"
    assert chunk["absolute_path"] == str(chunk_file.resolve())
    assert chunk["source_file_path"] == str(source_file.resolve())
