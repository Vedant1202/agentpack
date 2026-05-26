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
