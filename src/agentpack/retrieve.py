import sqlite3
import yaml
import json
from pathlib import Path
from typing import List, Dict

def build_index(pack_dir: Path, db_path: Path):
    manifest_path = pack_dir / "manifest.yml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found at {manifest_path}")
        
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
        
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Create FTS5 table
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
    
    # Insert chunks
    for chunk in manifest.get("chunks", []):
        chunk_id = chunk.get("id")
        source_id = chunk.get("source_id")
        path = chunk.get("path")
        token_count = chunk.get("token_count", 0)
        citation = json.dumps(chunk.get("citation", {}))
        
        # Read content
        chunk_file = pack_dir / path
        if chunk_file.exists():
            with open(chunk_file, "r", encoding="utf-8") as f:
                content = f.read()
            cur.execute(
                "INSERT INTO chunks_fts (chunk_id, source_id, path, token_count, citation, content) VALUES (?, ?, ?, ?, ?, ?)",
                (chunk_id, source_id, path, token_count, citation, content)
            )
            
    conn.commit()
    return conn

def search_pack(pack_dir: str, query: str, top_k: int = 5) -> List[Dict]:
    base_path = Path(pack_dir)
    indexes_dir = base_path / "indexes"
    indexes_dir.mkdir(exist_ok=True)
    db_path = indexes_dir / "lexical_index.db"
    
    if not db_path.exists():
        conn = build_index(base_path, db_path)
    else:
        conn = sqlite3.connect(db_path)
        
    cur = conn.cursor()
    
    import re
    # Strip non-alphanumeric characters (like '?' or '.') but keep spaces and hyphens
    clean_str = re.sub(r'[^a-zA-Z0-9\-\s]', ' ', query)
    # Split by whitespace, wrap each term in quotes for FTS, and join with OR
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
            # Fallback
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
            "citation": json.loads(citation_str),
            "score": rank
        })
        
    conn.close()
    return results
