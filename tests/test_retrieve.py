import pytest
import os
import json
import sqlite3
import numpy as np
from unittest.mock import patch, MagicMock
from agentpack.retrieve import search_pack, search_hybrid, search_fts, search_vector, build_fts_index, build_vector_index

@patch("agentpack.retrieve.sqlite3")
@patch("agentpack.retrieve.TextEmbedding")
def test_search_pack_hybrid(mock_TextEmbedding, mock_sqlite3, tmp_path):
    mock_model = MagicMock()
    mock_model.embed.return_value = [[0.1, 0.2, 0.3]]
    mock_TextEmbedding.return_value = mock_model
    
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    
    pack_dir = tmp_path
    
    with open(pack_dir / "manifest.yml", "w") as f:
        f.write("test: true")
        
    indexes_dir = pack_dir / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
        
    with open(indexes_dir / "vector_meta.json", "w") as f:
        f.write('[{"chunk_id": "c1", "source_id": "src1"}, {"chunk_id": "c2", "source_id": "src2"}]')
        
    with open(indexes_dir / "vector_index.npy", "wb") as f:
        pass
        
    with patch("agentpack.retrieve.np.load") as mock_np_load:
        import numpy as np
        mock_np_load.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        
        mock_cur.fetchall.side_effect = [
            [("c1", "src1", "test.txt", 100, "{}", -0.99)], 
            [("content 1", "{}", "test.txt", 100)] 
        ]
        mock_conn.cursor.return_value = mock_cur
        mock_sqlite3.connect.return_value = mock_conn
        
        results = search_pack(str(pack_dir), "test query", top_k=1, mode="hybrid")
        
        assert len(results) == 1
        assert results[0]["chunk_id"] == "c1"

def test_build_fts_index_and_search(tmp_path):
    pack_dir = tmp_path
    indexes_dir = pack_dir / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    db_path = indexes_dir / "lexical_index.db"
    
    with open(pack_dir / "manifest.yml", "w") as f:
        yaml_content = """
        chunks:
          - id: "c1"
            source_id: "s1"
            path: "chunks/c1.json"
            token_count: 10
        """
        f.write(yaml_content)
        
    chunks_dir = pack_dir / "chunks"
    chunks_dir.mkdir()
    
    with open(chunks_dir / "c1.json", "w") as f:
        json.dump({"content": "Hello world"}, f)
        
    build_fts_index(pack_dir, db_path)
    
    # Test FTS search
    res = search_fts(str(pack_dir), "world", top_k=1)
    assert len(res) == 1
    assert res[0]["chunk_id"] == "c1"

@patch("agentpack.retrieve.TextEmbedding")
def test_build_vector_index(mock_embed_cls, tmp_path):
    mock_embed = MagicMock()
    mock_embed.embed.return_value = iter([[0.1, 0.9]])
    mock_embed_cls.return_value = mock_embed
    
    pack_dir = tmp_path
    indexes_dir = pack_dir / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    
    with open(pack_dir / "manifest.yml", "w") as f:
        yaml_content = """
        chunks:
          - id: "c1"
            source_id: "s1"
            path: "chunks/c1.json"
            token_count: 10
        """
        f.write(yaml_content)
        
    chunks_dir = pack_dir / "chunks"
    chunks_dir.mkdir()
    
    with open(chunks_dir / "c1.json", "w") as f:
        json.dump({"content": "A"}, f)
        
    build_vector_index(pack_dir, indexes_dir / "vector_index.npy", indexes_dir / "vector_meta.json")
    
    assert (indexes_dir / "vector_index.npy").exists()
    assert (indexes_dir / "vector_meta.json").exists()

@patch("agentpack.retrieve.np.load")
@patch("agentpack.retrieve.TextEmbedding")
def test_search_hybrid(mock_embed_cls, mock_np_load, tmp_path):
    mock_embed = MagicMock()
    mock_embed.embed.return_value = iter([np.array([1.0, 0.0])])
    mock_embed_cls.return_value = mock_embed
    
    mock_np_load.return_value = np.array([[1.0, 0.0], [0.0, 1.0]])
    
    pack_dir = tmp_path
    indexes_dir = pack_dir / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    
    with open(indexes_dir / "vector_meta.json", "w") as f:
        json.dump([{"chunk_id": "c1", "source_id": "s1"}, {"chunk_id": "c2", "source_id": "s2"}], f)
        
    (indexes_dir / "vector_index.npy").write_bytes(b"")
        
    with patch("agentpack.retrieve.search_fts") as mock_search_fts:
        # Mock FTS returning c2
        mock_search_fts.return_value = [{"chunk_id": "c2", "score": 1.0, "path": "p", "token_count": 10, "citation": {}}]
        
        # Vector should prefer c1 (score 1.0) over c2 (score 0.0)
        # Hybrid should combine them
        results = search_hybrid(str(pack_dir), "query", top_k=2, alpha=0.5)
        
        assert len(results) == 2
        ids = [r["chunk_id"] for r in results]
        assert "c1" in ids
        assert "c2" in ids

@patch("agentpack.retrieve.build_vector_index")
def test_retrieve_error_handling(mock_build):
    res = search_vector("fake_dir", "q")
    assert res == []

    res = search_hybrid("fake_dir", "q")
    assert res == []


def _make_pack(pack_dir, chunk_id, text):
    """Helper: write a minimal pack with one chunk."""
    import yaml
    chunks_dir = pack_dir / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    chunk_file = f"chunks/{chunk_id}.md"
    (pack_dir / chunk_file).write_text(text)
    manifest = {
        "sources": [{"id": "s1", "checksum": chunk_id}],
        "chunks": [{"id": chunk_id, "source_id": "s1", "path": chunk_file, "token_count": 5}],
    }
    with open(pack_dir / "manifest.yml", "w") as f:
        yaml.dump(manifest, f)


def test_fts_invalidated_on_repack(tmp_path):
    """After re-packing with new content the FTS index must be rebuilt."""
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "indexes").mkdir()

    _make_pack(pack_dir, "chunk_v1", "first version content")
    results_v1 = search_fts(str(pack_dir), "first version", top_k=5)
    assert any(r["chunk_id"] == "chunk_v1" for r in results_v1), "v1 chunk not found"

    # Simulate re-pack: swap in different chunk
    _make_pack(pack_dir, "chunk_v2", "second version content")
    results_v2 = search_fts(str(pack_dir), "second version", top_k=5)
    assert any(r["chunk_id"] == "chunk_v2" for r in results_v2), (
        "v2 chunk not found — index not invalidated after re-pack"
    )
    chunk_ids = [r["chunk_id"] for r in results_v2]
    assert "chunk_v1" not in chunk_ids, "stale chunk_v1 still in index after re-pack"


@patch("agentpack.retrieve.TextEmbedding")
def test_embed_cache_skips_reembedding(mock_embed_cls, tmp_path):
    """Unchanged chunks must not be re-embedded on a second build_vector_index call."""
    mock_embed = MagicMock()
    mock_embed.embed.return_value = iter([np.array([0.1, 0.2, 0.3])])
    mock_embed_cls.return_value = mock_embed

    from agentpack.retrieve import build_vector_index
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "chunks").mkdir()
    (pack_dir / "chunks" / "c1.md").write_text("unique content for embedding test")
    import yaml
    manifest = {
        "sources": [{"id": "s1", "checksum": "abc"}],
        "chunks": [{"id": "c1", "source_id": "s1", "path": "chunks/c1.md", "token_count": 5}],
    }
    with open(pack_dir / "manifest.yml", "w") as f:
        yaml.dump(manifest, f)

    indexes = pack_dir / "indexes"
    indexes.mkdir()

    build_vector_index(pack_dir, indexes / "vector_index.npy", indexes / "vector_meta.json")
    assert mock_embed.embed.call_count == 1

    # Second build — same content — must hit L3 cache; embed not called again
    build_vector_index(pack_dir, indexes / "vector_index.npy", indexes / "vector_meta.json")
    assert mock_embed.embed.call_count == 1, (
        "embed() called again despite unchanged chunks — L3 cache not working"
    )


def test_fts_unchanged_pack_reuses_index(tmp_path):
    """Unchanged pack must NOT rebuild the FTS index (no extra work)."""
    import sqlite3 as _sqlite3
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "indexes").mkdir()

    _make_pack(pack_dir, "c1", "some content")
    search_fts(str(pack_dir), "some", top_k=5)  # build

    db_path = pack_dir / "indexes" / "lexical_index.db"
    mtime_before = db_path.stat().st_mtime

    search_fts(str(pack_dir), "content", top_k=5)  # should NOT rebuild
    assert db_path.stat().st_mtime == mtime_before, "index was unnecessarily rebuilt"
