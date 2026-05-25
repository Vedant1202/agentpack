import pytest
from unittest.mock import patch, MagicMock
from agentpack.retrieve import search_pack

@patch("agentpack.retrieve.sqlite3")
@patch("agentpack.retrieve.TextEmbedding")
def test_search_pack_hybrid(mock_TextEmbedding, mock_sqlite3, tmp_path):
    # Setup mock fastembed
    mock_model = MagicMock()
    mock_model.embed.return_value = [[0.1, 0.2, 0.3]]
    mock_TextEmbedding.return_value = mock_model
    
    # Setup mock sqlite
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    
    # We just want to mock the two main queries:
    # 1. vector_meta.json loading
    # 2. SQLite fetchall
    
    # Let's mock vector_meta.json and manifest.yml
    pack_dir = tmp_path
    
    with open(pack_dir / "manifest.yml", "w") as f:
        f.write("test: true")
        
    with open(pack_dir / "vector_meta.json", "w") as f:
        f.write('[{"chunk_id": "c1"}, {"chunk_id": "c2"}]')
        
    with open(pack_dir / "embeddings.npy", "wb") as f:
        # Just needs to exist for the open() call, numpy load will be mocked or fail
        pass
        
    # It's easier to mock numpy.load
    with patch("agentpack.retrieve.np.load") as mock_np_load:
        import numpy as np
        mock_np_load.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        
        # Mock SQLite returns
        # FTS search returns: [(chunk_id, source_id, path, token_count, citation, rank)]
        mock_cur.fetchall.side_effect = [
            [("c1", "src1", "test.txt", 100, "{}", 0.99)], # FTS query
            [("content 1", "{}", "test.txt", 100)] # Content fetch query
        ]
        mock_conn.cursor.return_value = mock_cur
        mock_sqlite3.connect.return_value = mock_conn
        
        results = search_pack(str(pack_dir), "test query", top_k=1, mode="hybrid")
        
        assert len(results) == 1
        assert results[0]["chunk_id"] == "c1"
        assert results[0]["score"] > 0
        assert results[0]["path"] == "test.txt"

@patch("agentpack.retrieve.sqlite3")
def test_search_pack_fts(mock_sqlite3, tmp_path):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    
    pack_dir = tmp_path
    with open(pack_dir / "manifest.yml", "w") as f:
        f.write("test: true")
        
    mock_cur.fetchall.side_effect = [
        [("c1", "src1", "test.txt", 100, "{}", 0.99)],
        [("content 1", "{}", "test.txt", 100)]
    ]
    mock_conn.cursor.return_value = mock_cur
    mock_sqlite3.connect.return_value = mock_conn
    
    results = search_pack(str(tmp_path), "test query", top_k=1, mode="fts")
    
    assert len(results) == 1
    assert results[0]["chunk_id"] == "c1"
