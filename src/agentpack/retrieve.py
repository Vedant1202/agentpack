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
        
    embedding_model = TextEmbedding()
    
    texts = []
    metadata = []
    
    for chunk in chunks:
        chunk_file = pack_dir / chunk.get("path")
        if chunk_file.exists():
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
            
    if not texts:
        return

    # Embed in batches with tqdm progress
    try:
        from tqdm import tqdm
        embeddings = []
        # Use a small batch size to prevent freezing on low-RAM machines and update progress bar frequently
        for emb in tqdm(embedding_model.embed(texts, batch_size=16), total=len(texts), desc="Generating FastEmbed Vectors"):
            embeddings.append(emb)
        embeddings = np.array(embeddings)
    except ImportError:
        embeddings_iter = embedding_model.embed(texts, batch_size=16)
        embeddings = np.array(list(embeddings_iter))
    
    np.save(vector_path, embeddings)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f)
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
    
    clean_str = re.sub(r'[^a-zA-Z0-9\-\s]', ' ', query)
    clean_query = " OR ".join([f'"{w}"' for w in clean_str.split() if w])
    if not clean_query:
        return []
        
    try:
        cur.execute('''
            SELECT chunk_id, source_id, path, token_count, citation, rank 
            FROM chunks_fts 
            WHERE chunks_fts MATCH ? 
            ORDER BY rank 
            LIMIT ?
        ''', (clean_query, top_k))
    except sqlite3.OperationalError:
        try:
            cur.execute('''
                SELECT chunk_id, source_id, path, token_count, citation, rank 
                FROM chunks_fts 
                WHERE chunks_fts MATCH ? 
                ORDER BY rank 
                LIMIT ?
            ''', (query, top_k))
        except sqlite3.OperationalError:
            return []
            
    results = []
    for row in cur.fetchall():
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
    indexes_dir.mkdir(exist_ok=True)
    vector_path = indexes_dir / "vector_index.npy"
    meta_path = indexes_dir / "vector_meta.json"
    hash_path = indexes_dir / "vector_index.hash"

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
        
    embedding_model = TextEmbedding()
    query_emb = list(embedding_model.embed([query]))[0]
    
    similarities = np.dot(embeddings, query_emb) / (np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_emb))
    
    # get top k, handling case where there are fewer chunks than top_k
    k = min(top_k, len(similarities))
    if k == 0:
        return []
    top_indices = np.argsort(similarities)[::-1][:k]
    
    results = []
    for idx in top_indices:
        meta = metadata[idx]
        score = float(similarities[idx])
        results.append({
            "chunk_id": meta["chunk_id"],
            "source_id": meta["source_id"],
            "path": meta["path"],
            "token_count": meta["token_count"],
            "citation": meta["citation"],
            "score": score,
            "norm_score": score
        })
        
    return results

def search_hybrid(pack_dir: str, query: str, top_k: int = 5, alpha: float = 0.5) -> List[Dict]:
    fts_results = search_fts(pack_dir, query, top_k=top_k*2)
    vec_results = search_vector(pack_dir, query, top_k=top_k*2)
    
    combined = {}
    
    for r in fts_results:
        combined[r["chunk_id"]] = {"fts_score": r["norm_score"], "vec_score": 0.0, "meta": r}
        
    for r in vec_results:
        if r["chunk_id"] in combined:
            combined[r["chunk_id"]]["vec_score"] = r["norm_score"]
        else:
            combined[r["chunk_id"]] = {"fts_score": 0.0, "vec_score": r["norm_score"], "meta": r}
            
    final_results = []
    for chunk_id, data in combined.items():
        hybrid_score = (alpha * data["vec_score"]) + ((1 - alpha) * data["fts_score"])
        meta = data["meta"]
        meta["score"] = hybrid_score
        final_results.append(meta)
        
    final_results.sort(key=lambda x: x["score"], reverse=True)
    return final_results[:top_k]

def search_pack(pack_dir: str, query: str, top_k: int = 5, mode: str = "hybrid") -> List[Dict]:
    if mode == "fts":
        results = search_fts(pack_dir, query, top_k)
    elif mode == "vector":
        results = search_vector(pack_dir, query, top_k)
    else:
        results = search_hybrid(pack_dir, query, top_k)
        
    # Attach actual text content for LLM generation
    import sqlite3
    from pathlib import Path
    db_path = Path(pack_dir) / "indexes" / "lexical_index.db"
    if db_path.exists():
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        for r in results:
            cur.execute("SELECT content FROM chunks_fts WHERE chunk_id = ?", (r["chunk_id"],))
            row = cur.fetchone()
            if row:
                r["content"] = row[0]
        conn.close()
        
    return results
