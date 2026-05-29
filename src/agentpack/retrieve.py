import hashlib
import sqlite3
import yaml
import json
import numpy as np
from pathlib import Path
from typing import List, Dict
import re
try:
    from fastembed import TextEmbedding
except ImportError:
    TextEmbedding = None

try:
    import hnswlib as _hnswlib
except ImportError:
    _hnswlib = None

from agentpack.cache import cache_get, cache_set, make_key

_EMBED_MODEL_ID = "BAAI/bge-small-en-v1.5"  # default fastembed model

_FTS_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "what", "which", "who", "how",
    "when", "where", "why", "all", "any", "both", "each", "more",
    "other", "some", "such", "no", "not", "only", "so", "than",
    "too", "very", "just", "as", "up", "out", "about", "into", "over",
    "after", "i", "we", "you", "he", "she", "they", "their", "our",
    "your", "his", "her",
})


def _build_fts_query(query: str) -> str:
    """AND query for FTS5: strip stop words, return space-separated quoted terms.

    FTS5 treats space-separated quoted terms as AND. Falls back to the full
    unfiltered term list when every term is a stop word (e.g. a bare 'the').
    """
    clean = re.sub(r'[^a-zA-Z0-9\-\s]', ' ', query)
    all_terms = [w for w in clean.split() if w]
    content_terms = [w for w in all_terms if w.lower() not in _FTS_STOP_WORDS]
    terms = content_terms if content_terms else all_terms
    return " ".join(f'"{w}"' for w in terms)

# Module-level singleton: loading TextEmbedding downloads ONNX weights (~30 MB).
# Shared across build_vector_index calls and query-time embedding.
_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None and TextEmbedding is not None:
        _embedding_model = TextEmbedding()
    return _embedding_model


def _manifest_hash(pack_dir: Path) -> str:
    """Stable hash of the pack's content: sorted chunk ids + source checksums."""
    manifest_path = pack_dir / "manifest.yml"
    if not manifest_path.exists():
        return ""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
    # Use chunk ids (ordering-stable) + source checksums as the content fingerprint
    chunk_ids = sorted(c.get("id", "") for c in manifest.get("chunks", []))
    src_checksums = sorted(s.get("checksum", "") for s in manifest.get("sources", []))
    fingerprint = "|".join(chunk_ids) + "||" + "|".join(src_checksums)
    return hashlib.sha256(fingerprint.encode()).hexdigest()


def _fts_stored_hash(conn: sqlite3.Connection) -> str:
    try:
        row = conn.execute("SELECT value FROM _pack_meta WHERE key='content_hash'").fetchone()
        return row[0] if row else ""
    except sqlite3.OperationalError:
        return ""


def _fts_write_hash(conn: sqlite3.Connection, h: str):
    conn.execute("CREATE TABLE IF NOT EXISTS _pack_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT OR REPLACE INTO _pack_meta (key, value) VALUES ('content_hash', ?)", (h,))
    conn.commit()

def build_fts_index(pack_dir: Path, db_path: Path):
    manifest_path = pack_dir / "manifest.yml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found at {manifest_path}")
        
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
        
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            chunk_id UNINDEXED,
            source_id UNINDEXED,
            path UNINDEXED,
            token_count UNINDEXED,
            citation UNINDEXED,
            content
        )
    ''')
    cur.execute('DELETE FROM chunks_fts')
    
    for chunk in manifest.get("chunks", []):
        chunk_id = chunk.get("id")
        source_id = chunk.get("source_id")
        path = chunk.get("path")
        token_count = chunk.get("token_count", 0)
        citation = json.dumps(chunk.get("citation", {}))
        
        chunk_file = pack_dir / path
        if chunk_file.exists():
            with open(chunk_file, "r", encoding="utf-8") as f:
                content = f.read()
            cur.execute(
                "INSERT INTO chunks_fts (chunk_id, source_id, path, token_count, citation, content) VALUES (?, ?, ?, ?, ?, ?)",
                (chunk_id, source_id, path, token_count, citation, content)
            )
            
    conn.commit()
    _fts_write_hash(conn, _manifest_hash(pack_dir))
    return conn

def build_vector_index(pack_dir: Path, vector_path: Path, meta_path: Path):
    if TextEmbedding is None:
        raise ImportError("fastembed is required for vector search. Run `pip install agentpack[gpu]` or `pip install fastembed`")
        
    manifest_path = pack_dir / "manifest.yml"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
        
    chunks = manifest.get("chunks", [])
    if not chunks:
        return

    embedding_model = _get_embedding_model()
    cache_dir = pack_dir / ".cache"

    texts = []
    metadata = []
    embeddings_list = []

    for chunk in chunks:
        chunk_file = pack_dir / chunk.get("path")
        if not chunk_file.exists():
            continue
        with open(chunk_file, "r", encoding="utf-8") as f:
            content = f.read()
        texts.append(content)
        metadata.append({
            "chunk_id": chunk.get("id"),
            "source_id": chunk.get("source_id"),
            "path": chunk.get("path"),
            "token_count": chunk.get("token_count", 0),
            "citation": chunk.get("citation", {})
        })

        # L3 embedding cache: key = sha256(chunk_text) + model_id
        text_hash = hashlib.sha256(content.encode()).hexdigest()
        emb_key = make_key(text_hash, _EMBED_MODEL_ID)
        cached_emb = cache_get(cache_dir, emb_key)
        if cached_emb is not None:
            embeddings_list.append(cached_emb)
        else:
            embeddings_list.append(None)  # placeholder — will batch-embed below

    if not texts:
        return

    # Batch-embed only the cache misses
    miss_indices = [i for i, e in enumerate(embeddings_list) if e is None]
    if miss_indices:
        miss_texts = [texts[i] for i in miss_indices]
        try:
            from tqdm import tqdm
            miss_embs = list(tqdm(
                embedding_model.embed(miss_texts, batch_size=16),
                total=len(miss_texts),
                desc="Generating FastEmbed Vectors",
            ))
        except ImportError:
            miss_embs = list(embedding_model.embed(miss_texts, batch_size=16))

        for j, idx in enumerate(miss_indices):
            emb = miss_embs[j]
            embeddings_list[idx] = emb
            # store in cache for next run
            text_hash = hashlib.sha256(texts[idx].encode()).hexdigest()
            emb_key = make_key(text_hash, _EMBED_MODEL_ID)
            cache_set(cache_dir, emb_key, emb)

    raw = np.array(embeddings_list, dtype=np.float32)
    # Pre-normalize at build time so query similarity is a plain dot product (faster).
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = raw / norms

    np.save(vector_path, embeddings)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f)

    # Build HNSW index if hnswlib is available (default ANN backend).
    hnsw_path = vector_path.parent / "hnsw_index.bin"
    if _hnswlib is not None and len(embeddings) > 0:
        dim = embeddings.shape[1]
        index = _hnswlib.Index(space="ip", dim=dim)  # inner-product on normalised vectors = cosine
        index.init_index(max_elements=len(embeddings), ef_construction=200, M=16)
        index.add_items(embeddings, list(range(len(embeddings))))
        index.save_index(str(hnsw_path))

    hash_path = vector_path.parent / "vector_index.hash"
    hash_path.write_text(_manifest_hash(pack_dir))

def search_fts(pack_dir: str, query: str, top_k: int = 5) -> List[Dict]:
    base_path = Path(pack_dir)
    indexes_dir = base_path / "indexes"
    indexes_dir.mkdir(exist_ok=True)
    db_path = indexes_dir / "lexical_index.db"

    current_hash = _manifest_hash(base_path)
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        if _fts_stored_hash(conn) != current_hash:
            conn.close()
            db_path.unlink()
            conn = build_fts_index(base_path, db_path)
    else:
        conn = build_fts_index(base_path, db_path)

    cur = conn.cursor()

    and_query = _build_fts_query(query)
    if not and_query:
        return []

    def _run(q):
        try:
            cur.execute(
                "SELECT chunk_id, source_id, path, token_count, citation, rank "
                "FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?",
                (q, top_k),
            )
            return cur.fetchall()
        except sqlite3.OperationalError:
            return []

    rows = _run(and_query)
    if not rows:
        # AND matched nothing — fall back to OR to preserve recall
        clean_str = re.sub(r'[^a-zA-Z0-9\-\s]', ' ', query)
        or_query = " OR ".join(f'"{w}"' for w in clean_str.split() if w)
        rows = _run(or_query) if or_query else []

    results = []
    for row in rows:
        chunk_id, source_id, path, token_count, citation_str, rank = row
        results.append({
            "chunk_id": chunk_id,
            "source_id": source_id,
            "path": path,
            "token_count": token_count,
            "citation": json.loads(citation_str) if isinstance(citation_str, str) else citation_str,
            "score": abs(rank)
        })
        
    conn.close()
    
    if results:
        max_score = max(r["score"] for r in results)
        min_score = min(r["score"] for r in results)
        for r in results:
            if max_score > min_score:
                r["norm_score"] = (r["score"] - min_score) / (max_score - min_score)
            else:
                r["norm_score"] = 1.0
                
    results.sort(key=lambda x: x.get("norm_score", 0), reverse=True)
    return results

def search_vector(pack_dir: str, query: str, top_k: int = 5) -> List[Dict]:
    base_path = Path(pack_dir)
    indexes_dir = base_path / "indexes"
    try:
        indexes_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return []
    vector_path = indexes_dir / "vector_index.npy"
    meta_path = indexes_dir / "vector_meta.json"
    hash_path = indexes_dir / "vector_index.hash"

    if not (base_path / "manifest.yml").exists():
        return []

    current_hash = _manifest_hash(base_path)
    stale = (
        not vector_path.exists()
        or not meta_path.exists()
        or not hash_path.exists()
        or hash_path.read_text().strip() != current_hash
    )
    if stale:
        build_vector_index(base_path, vector_path, meta_path)

    if not vector_path.exists():
        return []
        
    embeddings = np.load(vector_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
        
    embedding_model = _get_embedding_model()
    raw_q = np.array(list(embedding_model.embed([query]))[0], dtype=np.float32)
    q_norm = np.linalg.norm(raw_q)
    query_emb = raw_q / q_norm if q_norm > 0 else raw_q

    k = min(top_k, len(embeddings))
    if k == 0:
        return []

    hnsw_path = indexes_dir / "hnsw_index.bin"
    if _hnswlib is not None and hnsw_path.exists():
        # HNSW ANN search (default backend)
        dim = embeddings.shape[1]
        index = _hnswlib.Index(space="ip", dim=dim)
        index.load_index(str(hnsw_path), max_elements=len(embeddings))
        index.set_ef(max(k * 2, 50))
        labels, distances = index.knn_query(query_emb, k=k)
        top_indices = labels[0]
        scores = 1.0 - distances[0]  # hnswlib ip returns 1-cosine for normalized vecs
    else:
        # Brute-force fallback
        similarities = np.dot(embeddings, query_emb)
        top_indices = np.argsort(similarities)[::-1][:k]
        scores = [float(similarities[i]) for i in top_indices]

    results = []
    for idx, score in zip(top_indices, scores):
        meta = metadata[int(idx)]
        results.append({
            "chunk_id": meta["chunk_id"],
            "source_id": meta["source_id"],
            "path": meta["path"],
            "token_count": meta["token_count"],
            "citation": meta["citation"],
            "score": float(score),
            "norm_score": float(score),
        })

    return results

def _rrf_score(rank: int, k: int = 60) -> float:
    """Reciprocal Rank Fusion score: 1 / (k + rank), 1-indexed."""
    return 1.0 / (k + rank)


def search_hybrid(pack_dir: str, query: str, top_k: int = 5, alpha: float = 0.5) -> List[Dict]:
    fts_results = search_fts(pack_dir, query, top_k=top_k * 2)
    vec_results = search_vector(pack_dir, query, top_k=top_k * 2)

    # RRF fusion: combine ranks from both sources instead of normalised scores.
    rrf: Dict[str, float] = {}
    metas: Dict[str, dict] = {}

    for rank, r in enumerate(fts_results, start=1):
        cid = r["chunk_id"]
        rrf[cid] = rrf.get(cid, 0.0) + _rrf_score(rank)
        metas[cid] = r

    for rank, r in enumerate(vec_results, start=1):
        cid = r["chunk_id"]
        rrf[cid] = rrf.get(cid, 0.0) + _rrf_score(rank)
        if cid not in metas:
            metas[cid] = r

    final_results = []
    for cid, score in rrf.items():
        meta = dict(metas[cid])
        meta["score"] = score
        final_results.append(meta)

    final_results.sort(key=lambda x: x["score"], reverse=True)
    return final_results[:top_k]

def _matches_filters(
    result: dict,
    source_filter: str = None,
    section_filter: str = None,
    page_filter: int = None,
) -> bool:
    citation = result.get("citation", {})
    if source_filter and source_filter.lower() not in result.get("source_id", "").lower():
        return False
    if section_filter:
        section = citation.get("section", "")
        if section_filter.lower() not in section.lower():
            return False
    if page_filter is not None:
        if citation.get("page") != page_filter:
            return False
    return True


def search_pack(
    pack_dir: str,
    query: str,
    top_k: int = 5,
    mode: str = "hybrid",
    source_filter: str = None,
    section_filter: str = None,
    page_filter: int = None,
) -> List[Dict]:
    base = Path(pack_dir)
    cache_dir = base / ".cache"
    pack_hash = _manifest_hash(base)
    q_cache_key = make_key(
        hashlib.sha256(query.encode()).hexdigest(),
        mode,
        str(top_k),
        str(source_filter),
        str(section_filter),
        str(page_filter),
        pack_hash,
    )
    cached = cache_get(cache_dir, q_cache_key)
    if cached is not None:
        return cached

    fetch_k = top_k * 4 if any([source_filter, section_filter, page_filter]) else top_k
    if mode == "fts":
        results = search_fts(pack_dir, query, fetch_k)
    elif mode == "vector":
        results = search_vector(pack_dir, query, fetch_k)
    else:
        results = search_hybrid(pack_dir, query, fetch_k)

    if source_filter or section_filter or page_filter is not None:
        results = [
            r for r in results
            if _matches_filters(r, source_filter, section_filter, page_filter)
        ][:top_k]
        
    # Attach actual text content for LLM generation
    db_path = base / "indexes" / "lexical_index.db"
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        for r in results:
            cur.execute("SELECT content FROM chunks_fts WHERE chunk_id = ?", (r["chunk_id"],))
            row = cur.fetchone()
            if row:
                r["content"] = row[0]
        conn.close()

    cache_set(cache_dir, q_cache_key, results)
    return results
