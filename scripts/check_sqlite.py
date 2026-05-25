import sqlite3
import json
from pathlib import Path

pack_dir = Path("benchmarks/financebench_sample/agentpack_output")
with open(pack_dir / "vector_meta.json") as f:
    meta = json.load(f)
    print("Vector chunk_id type:", type(meta[0]["chunk_id"]), "value:", meta[0]["chunk_id"])

conn = sqlite3.connect(pack_dir / "lexical_index.db")
cur = conn.cursor()
cur.execute("SELECT chunk_id FROM chunks_fts LIMIT 1")
row = cur.fetchone()
print("SQLite chunk_id type:", type(row[0]), "value:", row[0])

# Test exact query from retrieve.py
cur.execute("SELECT content FROM chunks_fts WHERE chunk_id = ?", (meta[0]["chunk_id"],))
content_row = cur.fetchone()
print("Content fetched:", content_row is not None)
