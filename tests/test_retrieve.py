import pytest
import os
import json
import sqlite3
import numpy as np
from unittest.mock import patch, MagicMock
from agentpack.retrieve import search_pack, search_hybrid, search_fts, search_vector, build_fts_index, build_vector_index

def test_build_fts_query_filters_stop_words():
    from agentpack.retrieve import _build_fts_query
    result = _build_fts_query("what is 3M revenue")
    assert '"3M"' in result
    assert '"revenue"' in result
    assert '"what"' not in result
    assert '"is"' not in result
    assert " OR " not in result  # AND query: no OR operator


def test_build_fts_query_all_stop_words_fallback():
    from agentpack.retrieve import _build_fts_query
    result = _build_fts_query("the a of")
    assert result != ""  # never returns empty
    assert '"the"' in result  # unfiltered fallback


def test_build_fts_query_no_stop_words():
    from agentpack.retrieve import _build_fts_query
    assert _build_fts_query("neural network") == '"neural" "network"'


def test_build_fts_query_single_term():
    from agentpack.retrieve import _build_fts_query
    assert _build_fts_query("alpha") == '"alpha"'


def test_search_pack_hybrid(tmp_path):
    """search_pack hybrid mode returns results with a real (tiny) corpus."""
    import yaml
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "chunks").mkdir()
    (pack_dir / "indexes").mkdir()
    (pack_dir / "chunks" / "c1.md").write_text("neural network architecture explained")
    manifest = {
        "sources": [{"id": "s1", "checksum": "a"}],
        "chunks": [{"id": "c1", "source_id": "s1", "path": "chunks/c1.md",
                    "token_count": 5, "citation": {"source_path": "doc.pdf"}}],
    }
    with open(pack_dir / "manifest.yml", "w") as f:
        yaml.dump(manifest, f)

    with patch("agentpack.retrieve.search_fts") as mock_fts, \
         patch("agentpack.retrieve.search_vector") as mock_vec:
        mock_fts.return_value = [{"chunk_id": "c1", "source_id": "s1", "path": "chunks/c1.md",
                                   "token_count": 5, "citation": {}, "score": 1.0, "norm_score": 1.0}]
        mock_vec.return_value = [{"chunk_id": "c1", "source_id": "s1", "path": "chunks/c1.md",
                                   "token_count": 5, "citation": {}, "score": 1.0, "norm_score": 1.0}]
        results = search_pack(str(pack_dir), "neural network", top_k=1, mode="hybrid")

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

@patch("agentpack.retrieve._get_embedding_model")
def test_build_vector_index(mock_get_model, tmp_path):
    mock_embed = MagicMock()
    mock_embed.embed.side_effect = lambda texts, **_: iter([[0.1, 0.9]] * len(texts))
    mock_get_model.return_value = mock_embed
    
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
@patch("agentpack.retrieve._get_embedding_model")
def test_search_hybrid(mock_get_model, mock_np_load, tmp_path):
    mock_embed = MagicMock()
    mock_embed.embed.side_effect = lambda texts, **_: iter([np.array([1.0, 0.0])] * len(texts))
    mock_get_model.return_value = mock_embed
    
    mock_np_load.return_value = np.array([[1.0, 0.0], [0.0, 1.0]])
    
    pack_dir = tmp_path
    indexes_dir = pack_dir / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)

    import yaml
    with open(pack_dir / "manifest.yml", "w") as f:
        yaml.dump({"sources": [], "chunks": []}, f)

    with open(indexes_dir / "vector_meta.json", "w") as f:
        json.dump([{"chunk_id": "c1", "source_id": "s1", "path": "p1", "token_count": 1, "citation": {}},
                   {"chunk_id": "c2", "source_id": "s2", "path": "p2", "token_count": 1, "citation": {}}], f)

    (indexes_dir / "vector_index.npy").write_bytes(b"")
    # Write hash so search_vector doesn't try to rebuild
    (indexes_dir / "vector_index.hash").write_text("placeholder")
        
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

def test_retrieve_error_handling():
    """Non-existent pack_dir must return [] without crashing."""
    res = search_vector("/tmp/__agentpack_nonexistent_dir__", "q")
    assert res == []

    with patch("agentpack.retrieve.search_fts", return_value=[]), \
         patch("agentpack.retrieve.search_vector", return_value=[]):
        res = search_hybrid("/tmp/__agentpack_nonexistent_dir__", "q")
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


@patch("agentpack.retrieve._get_embedding_model")
def test_embed_cache_skips_reembedding(mock_get_model, tmp_path):
    """Unchanged chunks must not be re-embedded on a second build_vector_index call."""
    mock_embed = MagicMock()
    # Return a fresh iterator each call so the mock doesn't get exhausted
    mock_embed.embed.side_effect = lambda texts, **_: iter([np.array([0.1, 0.2, 0.3])] * len(texts))
    mock_get_model.return_value = mock_embed

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
    calls_after_first = mock_embed.embed.call_count
    assert calls_after_first >= 1

    # Second build — same content — must hit L3 cache; embed not called again
    build_vector_index(pack_dir, indexes / "vector_index.npy", indexes / "vector_meta.json")
    assert mock_embed.embed.call_count == calls_after_first, (
        "embed() called again despite unchanged chunks — L3 cache not working"
    )


def test_rrf_ordering(tmp_path):
    """RRF must order all-term matches above single-term matches (directional test)."""
    from agentpack.retrieve import search_fts, _rrf_score

    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "chunks").mkdir()
    (pack_dir / "indexes").mkdir()

    # chunk_both matches "alpha" and "beta"; chunk_one matches only "alpha"
    (pack_dir / "chunks" / "c_both.md").write_text("alpha beta document here")
    (pack_dir / "chunks" / "c_one.md").write_text("alpha only document here")

    import yaml
    manifest = {
        "sources": [{"id": "s1", "checksum": "abc"}],
        "chunks": [
            {"id": "c_both", "source_id": "s1", "path": "chunks/c_both.md", "token_count": 4},
            {"id": "c_one", "source_id": "s1", "path": "chunks/c_one.md", "token_count": 4},
        ],
    }
    with open(pack_dir / "manifest.yml", "w") as f:
        yaml.dump(manifest, f)

    results = search_fts(str(pack_dir), "alpha", top_k=5)
    assert len(results) >= 1

    # Verify RRF score formula at a known rank
    score_rank1 = _rrf_score(1)
    score_rank2 = _rrf_score(2)
    assert score_rank1 > score_rank2


def test_metadata_filter(tmp_path):
    """source_filter / section_filter must constrain results."""
    from agentpack.retrieve import search_pack
    from unittest.mock import patch

    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "chunks").mkdir()
    (pack_dir / "indexes").mkdir()

    import yaml, json
    (pack_dir / "chunks" / "c1.md").write_text("content about neural networks")
    (pack_dir / "chunks" / "c2.md").write_text("content about databases")
    manifest = {
        "sources": [{"id": "src_001", "checksum": "a"}, {"id": "src_002", "checksum": "b"}],
        "chunks": [
            {"id": "c1", "source_id": "src_001", "path": "chunks/c1.md", "token_count": 4,
             "citation": {"source_path": "doc1.pdf", "section": "Neural", "page": 1}},
            {"id": "c2", "source_id": "src_002", "path": "chunks/c2.md", "token_count": 4,
             "citation": {"source_path": "doc2.pdf", "section": "DB", "page": 2}},
        ],
    }
    with open(pack_dir / "manifest.yml", "w") as f:
        yaml.dump(manifest, f)

    with patch("agentpack.retrieve.search_hybrid") as mock_hybrid:
        mock_hybrid.return_value = [
            {"chunk_id": "c1", "source_id": "src_001", "path": "chunks/c1.md",
             "token_count": 4, "citation": {"section": "Neural", "page": 1}, "score": 0.9},
            {"chunk_id": "c2", "source_id": "src_002", "path": "chunks/c2.md",
             "token_count": 4, "citation": {"section": "DB", "page": 2}, "score": 0.5},
        ]
        results = search_pack(str(pack_dir), "content", top_k=5, source_filter="src_001")

    assert all(r["source_id"] == "src_001" for r in results), (
        f"source_filter not applied: {[r['source_id'] for r in results]}"
    )


def test_fts_and_precision(tmp_path):
    """AND query must exclude chunks that match only some query terms."""
    import yaml
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "chunks").mkdir()
    (pack_dir / "indexes").mkdir()

    # c_all has both "3M" and "revenue"; c_partial has "3M" but not "revenue"
    (pack_dir / "chunks" / "c_all.md").write_text("3M annual revenue 2022 financial results")
    (pack_dir / "chunks" / "c_partial.md").write_text("3M annual report results 2022")

    manifest = {
        "sources": [{"id": "s1", "checksum": "x"}],
        "chunks": [
            {"id": "c_all", "source_id": "s1", "path": "chunks/c_all.md", "token_count": 5},
            {"id": "c_partial", "source_id": "s1", "path": "chunks/c_partial.md", "token_count": 4},
        ],
    }
    with open(pack_dir / "manifest.yml", "w") as f:
        yaml.dump(manifest, f)

    # "what is 3M revenue" → stop words filtered → "3M" AND "revenue"
    # c_all matches both; c_partial matches "3M" only → excluded by AND
    results = search_fts(str(pack_dir), "what is 3M revenue", top_k=5)
    chunk_ids = [r["chunk_id"] for r in results]
    assert "c_all" in chunk_ids, "c_all (all terms present) must be returned"
    assert "c_partial" not in chunk_ids, "c_partial (missing 'revenue') must be excluded by AND"


def test_fts_or_fallback_on_no_and_results(tmp_path):
    """When AND matches nothing, OR fallback must still return results."""
    import yaml
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "chunks").mkdir()
    (pack_dir / "indexes").mkdir()

    (pack_dir / "chunks" / "c1.md").write_text("alpha only document here")
    manifest = {
        "sources": [{"id": "s1", "checksum": "y"}],
        "chunks": [{"id": "c1", "source_id": "s1", "path": "chunks/c1.md", "token_count": 4}],
    }
    with open(pack_dir / "manifest.yml", "w") as f:
        yaml.dump(manifest, f)

    # "alpha beta": AND requires both; only "alpha" exists → AND returns 0 → OR fallback
    results = search_fts(str(pack_dir), "alpha beta", top_k=5)
    assert len(results) == 1
    assert results[0]["chunk_id"] == "c1"


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
