import os
import json
import yaml
import sqlite3
import numpy as np
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from agentpack.retrieve import build_fts_index, build_vector_index, search_hybrid

app = FastAPI(title="AgentPack Corpus Intelligence API")

# Setup CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PACK_DIR = os.environ.get("AGENTPACK_DIR", ".")

def get_base_path():
    return Path(PACK_DIR)


def ensure_manifest_exists(base_path: Path):
    manifest_path = base_path / "manifest.yml"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")


def ensure_lexical_index(base_path: Path) -> Path:
    ensure_manifest_exists(base_path)
    indexes_dir = base_path / "indexes"
    indexes_dir.mkdir(exist_ok=True)
    db_path = indexes_dir / "lexical_index.db"
    if not db_path.exists():
        build_fts_index(base_path, db_path)
    return db_path


def ensure_vector_index_artifacts(base_path: Path):
    ensure_manifest_exists(base_path)
    indexes_dir = base_path / "indexes"
    indexes_dir.mkdir(exist_ok=True)
    vector_path = indexes_dir / "vector_index.npy"
    meta_path = indexes_dir / "vector_meta.json"
    if not vector_path.exists() or not meta_path.exists():
        try:
            build_vector_index(base_path, vector_path, meta_path)
        except ImportError as exc:
            raise HTTPException(
                status_code=500,
                detail="fastembed is not installed. Run pip install agentpack[ui]",
            ) from exc
    if not vector_path.exists() or not meta_path.exists():
        raise HTTPException(status_code=404, detail="Vector index not found")
    return vector_path, meta_path

@app.get("/api/manifest")
def get_manifest():
    manifest_path = get_base_path() / "manifest.yml"
    ensure_manifest_exists(get_base_path())
    with open(manifest_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def build_human_readable_title(source_id: str, citation: dict) -> str:
    # Try to extract the real filename or a cleaner version of the source_id
    title = citation.get('source_path', source_id)
    if "/" in title:
        title = title.split("/")[-1]
        
    section_path = citation.get('section_path', [])
    if section_path:
        # Join the last two sections if possible, or just the last
        if len(section_path) > 1:
            title += f" > {section_path[-2]} > {section_path[-1]}"
        else:
            title += f" > {section_path[-1]}"
            
    return title

def resolve_source_file_path(base_path: Path, citation: dict) -> Optional[str]:
    source_path = citation.get("source_path")
    if not source_path:
        return None

    source = Path(source_path)
    if source.is_absolute():
        return str(source)

    candidates = [
        base_path / source,
        base_path.parent / "corpus" / source,
        base_path.parent / source,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())
    return None


def load_vector_artifacts(base_path: Path):
    vector_path, meta_path = ensure_vector_index_artifacts(base_path)

    embeddings = np.load(vector_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return embeddings, meta


def search_vector_artifacts(base_path: Path, query: str, top_k: int):
    try:
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="fastembed is not installed. Run pip install agentpack[ui]",
        ) from exc

    embeddings, meta = load_vector_artifacts(base_path)
    if len(embeddings) == 0 or not meta:
        return []

    model = TextEmbedding()
    raw_q = np.array(list(model.embed([query]))[0], dtype=np.float32)
    q_norm = np.linalg.norm(raw_q)
    query_emb = raw_q / q_norm if q_norm > 0 else raw_q

    k = min(max(top_k, 0), len(embeddings))
    if k == 0:
        return []

    similarities = np.dot(embeddings, query_emb)
    top_indices = np.argsort(similarities)[::-1][:k]
    results = []
    for idx in top_indices:
        item = meta[int(idx)]
        results.append(
            {
                "chunk_id": item["chunk_id"],
                "source_id": item.get("source_id", "Unknown"),
                "path": item.get("path"),
                "token_count": item.get("token_count", 0),
                "citation": item.get("citation", {}),
                "score": float(similarities[idx]),
            }
        )
    return results

@app.get("/api/chunks")
def get_chunks():
    base_path = get_base_path()
    db_path = ensure_lexical_index(base_path)
        
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT chunk_id, source_id, path, token_count, citation, content FROM chunks_fts")
        chunks = []
        for row in cur.fetchall():
            chunk_id, source_id, path, token_count, citation_str, content = row
            try:
                citation = json.loads(citation_str)
            except:
                citation = {}
                
            human_readable = build_human_readable_title(source_id, citation)
                
            chunks.append({
                "id": chunk_id,
                "source": source_id,
                "path": path,
                "absolute_path": str((base_path / path).resolve()),
                "source_file_path": resolve_source_file_path(base_path, citation),
                "title": human_readable,
                "tokens": token_count,
                "citation": citation,
                "content": content
            })
        return {"chunks": chunks}
    finally:
        conn.close()

@app.get("/api/umap")
def get_umap():
    try:
        import umap.umap_ as umap
    except ImportError:
        raise HTTPException(status_code=500, detail="umap-learn is not installed. Run pip install agentpack[ui]")
        
    embeddings, meta = load_vector_artifacts(get_base_path())
        
    # Compute UMAP
    reducer = umap.UMAP(n_components=2, metric='cosine', random_state=42)
    reduced = reducer.fit_transform(embeddings)
    
    points = []
    for i, m in enumerate(meta):
        points.append({
            "id": m["chunk_id"],
            "x": float(reduced[i][0]),
            "y": float(reduced[i][1]),
            "source": m.get("source_id", "Unknown"),
            "tokens": m.get("token_count", 0)
        })
        
    # Scale x/y to 0-100 for SVG plotting
    if points:
        xs = [p["x"] for p in points]
        ys = [p["y"] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        
        range_x = max_x - min_x if max_x != min_x else 1
        range_y = max_y - min_y if max_y != min_y else 1
        
        for p in points:
            # Scale to 10-90 to leave padding
            p["x"] = 10 + ((p["x"] - min_x) / range_x) * 80
            p["y"] = 10 + ((p["y"] - min_y) / range_y) * 80
            
    return {"points": points}

class SearchQuery(BaseModel):
    query: str
    top_k: int = 10

@app.post("/api/search")
def search(req: SearchQuery):
    base_path = get_base_path()
    try:
        ranked = search_hybrid(PACK_DIR, req.query, top_k=req.top_k)
    except FileNotFoundError:
        ranked = search_vector_artifacts(base_path, req.query, req.top_k)
    if not ranked:
        return {"results": []}

    # Enrich with content from the lexical index (search_hybrid doesn't return it)
    db_path = base_path / "indexes" / "lexical_index.db"
    content_map: dict = {}
    chunk_meta: dict = {}
    if db_path.exists():
        ids = [r["chunk_id"] for r in ranked]
        placeholders = ",".join("?" * len(ids))
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT chunk_id, source_id, path, token_count, citation, content "
                f"FROM chunks_fts WHERE chunk_id IN ({placeholders})",
                ids,
            )
            for chunk_id, source_id, path, token_count, citation_str, content in cur.fetchall():
                try:
                    citation = json.loads(citation_str)
                except Exception:
                    citation = {}
                content_map[chunk_id] = content
                chunk_meta[chunk_id] = {
                    "source": source_id,
                    "path": path,
                    "tokens": token_count,
                    "citation": citation,
                    "title": build_human_readable_title(source_id, citation),
                    "source_file_path": resolve_source_file_path(base_path, citation),
                }
        finally:
            conn.close()

    results = []
    for r in ranked:
        citation = r.get("citation", {})
        source_id = r.get("source_id", "Unknown")
        meta = chunk_meta.get(
            r["chunk_id"],
            {
                "source": source_id,
                "path": r.get("path"),
                "tokens": r.get("token_count", 0),
                "citation": citation,
                "title": build_human_readable_title(source_id, citation),
                "source_file_path": resolve_source_file_path(base_path, citation),
            },
        )
        results.append(
            {
                "id": r["chunk_id"],
                "fts": 0.0,
                "vector": r.get("score", 0.0),
                "hybrid": r["score"],
                "content": content_map.get(r["chunk_id"], ""),
                **meta,
            }
        )
    return {"results": results}

class NeighborQuery(BaseModel):
    chunk_id: str
    top_k: int = 5

@app.post("/api/neighbors")
def get_neighbors(req: NeighborQuery):
    base_path = get_base_path()
    try:
        embeddings, meta = load_vector_artifacts(base_path)
            
        # Find index of target chunk
        target_idx = None
        for i, m in enumerate(meta):
            if m["chunk_id"] == req.chunk_id:
                target_idx = i
                break
                
        if target_idx is None:
            raise HTTPException(status_code=404, detail="Chunk not found")
            
        target_emb = embeddings[target_idx]
        similarities = np.dot(embeddings, target_emb) / (np.linalg.norm(embeddings, axis=1) * np.linalg.norm(target_emb))
        
        # Get top_k + 1 (since the first one will be the target itself)
        top_indices = np.argsort(similarities)[::-1][:req.top_k + 1]
        
        neighbors = []
        for idx in top_indices:
            chunk_id = meta[idx]["chunk_id"]
            if chunk_id != req.chunk_id:
                neighbors.append({
                    "id": chunk_id,
                    "score": float(similarities[idx]),
                    "source": meta[idx].get("source_id", "Unknown"),
                    "title": build_human_readable_title(
                        meta[idx].get("source_id", "Unknown"),
                        meta[idx].get("citation", {}),
                    ),
                })
                
        return {"neighbors": neighbors[:req.top_k]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class Feedback(BaseModel):
    chunk_id: str
    query: str
    rating: int  # 1 for thumb up, -1 for thumb down, 2 for pinned

@app.post("/api/feedback")
def submit_feedback(fb: Feedback):
    fb_path = get_base_path() / "eval_feedback.json"
    data = []
    if fb_path.exists():
        try:
            with open(fb_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            pass
            
    data.append({
        "chunk_id": fb.chunk_id,
        "query": fb.query,
        "rating": fb.rating,
        "timestamp": __import__("time").time()
    })
    
    with open(fb_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    return {"status": "success"}

from fastapi.responses import FileResponse
import sys

# Try to find the dist directory robustly
possible_web_dirs = [
    Path(__file__).parent / "web" / "dist", # Installed package or local if editable
    Path(os.getcwd()) / "src" / "agentpack" / "ui" / "web" / "dist" # Local dev fallback
]

web_dir = None
for pwd in possible_web_dirs:
    if pwd.exists():
        web_dir = pwd
        break

if web_dir:
    app.mount("/assets", StaticFiles(directory=str(web_dir / "assets")), name="assets")
    
    @app.get("/")
    def serve_index():
        return FileResponse(str(web_dir / "index.html"))
    
    # Catch-all for React Router if needed, or other static files
    @app.get("/{file_path:path}")
    def serve_static(file_path: str):
        target = web_dir / file_path
        if target.exists() and target.is_file():
            return FileResponse(str(target))
        return FileResponse(str(web_dir / "index.html"))
else:
    @app.get("/")
    def no_ui_fallback():
        return {"detail": "UI assets not found. If developing locally, ensure you ran 'npm run build' in 'src/agentpack/ui/web'."}
