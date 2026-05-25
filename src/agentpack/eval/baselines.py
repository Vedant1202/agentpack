import sqlite3
import os
import tiktoken
from pathlib import Path
from typing import List, Dict

def _extract_text(file_path: Path) -> str:
    if file_path.suffix.lower() == ".pdf":
        try:
            import fitz
            doc = fitz.open(file_path)
            text = []
            for page in doc:
                text.append(page.get_text("text"))
            return "\n".join(text)
        except Exception:
            return ""
    else:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return ""

def raw_file_search(corpus_dir: Path, query: str, top_k: int = 5) -> List[Dict]:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute('CREATE VIRTUAL TABLE files_fts USING fts5(path UNINDEXED, content)')
    
    for root, _, files in os.walk(corpus_dir):
        for file in files:
            p = Path(root) / file
            if p.suffix in [".txt", ".md", ".csv", ".pdf"]:
                content = _extract_text(p)
                cur.execute("INSERT INTO files_fts (path, content) VALUES (?, ?)", (p.name, content))
                
    clean_query = " OR ".join([f'"{w}"' for w in query.replace('"', '').split() if w])
    if not clean_query: return []
    
    try:
        cur.execute('SELECT path, rank, content FROM files_fts WHERE files_fts MATCH ? ORDER BY rank LIMIT ?', (clean_query, top_k))
    except sqlite3.OperationalError:
        try:
            cur.execute('SELECT path, rank, content FROM files_fts WHERE files_fts MATCH ? ORDER BY rank LIMIT ?', (query, top_k))
        except sqlite3.OperationalError:
            return []
            
    encoder = tiktoken.get_encoding("cl100k_base")
    results = []
    for path, rank, content in cur.fetchall():
        results.append({
            "path": path,
            "token_count": len(encoder.encode(content)),
            "score": rank
        })
    return results

def naive_chunk_search(corpus_dir: Path, query: str, top_k: int = 5, chunk_size: int = 4000) -> List[Dict]:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute('CREATE VIRTUAL TABLE chunks_fts USING fts5(path UNINDEXED, chunk_id UNINDEXED, content)')
    
    chunk_id = 0
    for root, _, files in os.walk(corpus_dir):
        for file in files:
            p = Path(root) / file
            if p.suffix in [".txt", ".md", ".csv", ".pdf"]:
                content = _extract_text(p)
                for i in range(0, len(content), chunk_size):
                    chunk_text = content[i:i+chunk_size]
                    cur.execute("INSERT INTO chunks_fts (path, chunk_id, content) VALUES (?, ?, ?)", (p.name, chunk_id, chunk_text))
                    chunk_id += 1
                    
    clean_query = " OR ".join([f'"{w}"' for w in query.replace('"', '').split() if w])
    if not clean_query: return []
    
    try:
        cur.execute('SELECT path, chunk_id, rank, content FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?', (clean_query, top_k))
    except sqlite3.OperationalError:
        try:
            cur.execute('SELECT path, chunk_id, rank, content FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?', (query, top_k))
        except sqlite3.OperationalError:
            return []
            
    encoder = tiktoken.get_encoding("cl100k_base")
    results = []
    for path, cid, rank, content in cur.fetchall():
        results.append({
            "path": path,
            "token_count": len(encoder.encode(content)),
            "score": rank
        })
    return results
