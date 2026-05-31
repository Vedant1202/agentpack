import json
import sqlite3
import os
import threading
import tiktoken
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Callable

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

def _extract_text_timed(file_path: Path, timeout: int = 45) -> str:
    """Extract text with a hard timeout; returns "" if extraction hangs."""
    result: List[str] = [None]

    def _run():
        result[0] = _extract_text(file_path)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        import sys
        print(f"\n  [WARN] _extract_text timed out after {timeout}s for {file_path.name} — skipping",
              file=sys.stderr)
        return ""
    return result[0] or ""


_raw_conn_cache = None
_naive_conn_cache = None
_last_corpus_dir = None

def _get_raw_conn(corpus_dir: Path):
    global _raw_conn_cache, _last_corpus_dir
    if _raw_conn_cache is not None and _last_corpus_dir == corpus_dir:
        return _raw_conn_cache
        
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute('CREATE VIRTUAL TABLE files_fts USING fts5(path UNINDEXED, content)')
    
    from tqdm import tqdm
    all_files = []
    for root, _, files in os.walk(corpus_dir):
        for file in files:
            p = Path(root) / file
            if p.suffix in [".txt", ".md", ".csv", ".pdf"]:
                all_files.append(p)
                
    for p in tqdm(all_files, desc="Building Raw File Baseline Index"):
        content = _extract_text(p)
        cur.execute("INSERT INTO files_fts (path, content) VALUES (?, ?)", (p.name, content))
        
    _raw_conn_cache = conn
    _last_corpus_dir = corpus_dir
    return conn

def _get_naive_conn(corpus_dir: Path, chunk_size: int = 4000):
    global _naive_conn_cache
    if _naive_conn_cache is not None and _last_corpus_dir == corpus_dir:
        return _naive_conn_cache
        
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute('CREATE VIRTUAL TABLE chunks_fts USING fts5(path UNINDEXED, chunk_id UNINDEXED, content)')
    
    chunk_id = 0
    
    from tqdm import tqdm
    all_files = []
    for root, _, files in os.walk(corpus_dir):
        for file in files:
            p = Path(root) / file
            if p.suffix in [".txt", ".md", ".csv", ".pdf"]:
                all_files.append(p)
                
    for p in tqdm(all_files, desc="Building Naive Chunk Baseline Index"):
        content = _extract_text(p)
        for i in range(0, len(content), chunk_size):
            chunk_text = content[i:i+chunk_size]
            cur.execute("INSERT INTO chunks_fts (path, chunk_id, content) VALUES (?, ?, ?)", (p.name, chunk_id, chunk_text))
            chunk_id += 1
            
    _naive_conn_cache = conn
    return conn

def raw_file_search(corpus_dir: Path, query: str, top_k: int = 5) -> List[Dict]:
    conn = _get_raw_conn(corpus_dir)
    cur = conn.cursor()
    
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
            "score": rank,
            "content": content
        })
    return results

def naive_chunk_search(corpus_dir: Path, query: str, top_k: int = 5, chunk_size: int = 4000) -> List[Dict]:
    conn = _get_naive_conn(corpus_dir, chunk_size)
    cur = conn.cursor()
    
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
    for path, chunk_id, rank, content in cur.fetchall():
        results.append({
            "chunk_id": chunk_id,
            "path": path,
            "token_count": len(encoder.encode(content)),
            "score": rank,
            "content": content
        })
    return results


# ---------------------------------------------------------------------------
# Extra baselines (dense / reranking / LLM-in-retrieval)
#
# All of these reuse AgentPack's own embedding model (fastembed
# BAAI/bge-small-en-v1.5) so that comparisons isolate the variable under test
# (chunking strategy, reranking, query expansion) rather than the embedder.
#
# Each baseline is a function (corpus_dir, query, top_k) -> List[Dict] with the
# same result shape the eval harness expects: keys `path`, `content`, `score`,
# `token_count`. Vector indexes are built once per (strategy, corpus_dir) and
# cached at module level so we never re-embed the corpus per query.
# ---------------------------------------------------------------------------

# Set by the eval harness before running the gated LLM baselines
# (Contextual Retrieval, HyDE). Default mirrors the gen-eval generation model.
LLM_BASELINE_MODEL = "gemini-3.1-flash-lite"

_encoder = None


def _enc():
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def _walk_corpus(corpus_dir: Path) -> List[Path]:
    files = []
    for root, _, names in os.walk(corpus_dir):
        for name in names:
            p = Path(root) / name
            if p.suffix.lower() in (".txt", ".md", ".csv", ".pdf"):
                files.append(p)
    return files


def _normalize(vec: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(vec)
    return vec / n if n > 0 else vec


# --- Chunking strategies -----------------------------------------------------

def _fixed_chunks(text: str, size: int = 4000) -> List[Dict]:
    """Fixed-width character chunks (same splitting as Naive Chunk baseline)."""
    return [{"content": text[i:i + size]} for i in range(0, len(text), size) if text[i:i + size].strip()]


def _recursive_chunks(text: str, size: int = 1000, overlap: int = 200) -> List[Dict]:
    """Industry-default recursive splitter (LangChain-style) without the dep.

    Greedily packs text up to `size` characters, splitting on progressively
    finer separators, then stitches a small overlap between adjacent chunks.
    """
    separators = ["\n\n", "\n", ". ", " "]

    def _split(t: str, seps: List[str]) -> List[str]:
        if len(t) <= size or not seps:
            return [t]
        sep = seps[0]
        parts = t.split(sep)
        out, cur = [], ""
        for part in parts:
            piece = part + sep
            if len(cur) + len(piece) <= size:
                cur += piece
            else:
                if cur:
                    out.append(cur)
                if len(piece) > size:
                    out.extend(_split(part, seps[1:]))
                    cur = ""
                else:
                    cur = piece
        if cur:
            out.append(cur)
        return out

    raw = [c.strip() for c in _split(text, separators) if c.strip()]
    chunks: List[Dict] = []
    for c in raw:
        if overlap and chunks:
            tail = chunks[-1]["content"][-overlap:]
            chunks.append({"content": f"{tail} {c}"})
        else:
            chunks.append({"content": c})
    return chunks


def _parent_child_chunks(text: str, parent_size: int = 2000, child_size: int = 400) -> List[Dict]:
    """Small child chunks (for matching) each carrying their parent block (for context)."""
    out: List[Dict] = []
    for i in range(0, len(text), parent_size):
        parent = text[i:i + parent_size]
        if not parent.strip():
            continue
        for j in range(0, len(parent), child_size):
            child = parent[j:j + child_size]
            if child.strip():
                out.append({"content": child, "parent": parent})
    return out


# --- Shared cached dense index ----------------------------------------------

# key: (strategy_name, str(corpus_dir)) -> {"emb": np.ndarray, "chunks": List[Dict]}
_vector_index_cache: Dict[tuple, dict] = {}

# Bump this whenever the index format or chunking logic changes to invalidate old caches.
_CACHE_VERSION = 1


def _build_dense_index(
    corpus_dir: Path,
    strategy: str,
    chunk_fn: Callable[[str], List[Dict]],
    transform_fn: Optional[Callable[[Dict, Path], str]] = None,
) -> Optional[dict]:
    """Chunk the corpus, embed every chunk once, and cache the matrix.

    `transform_fn(chunk, file_path) -> str` lets a baseline change the text that
    gets embedded (e.g. Contextual Retrieval prepends an LLM blurb) while still
    storing the original chunk for display.
    """
    key = (strategy, str(corpus_dir))
    if key in _vector_index_cache:
        return _vector_index_cache[key]

    # --- disk cache -----------------------------------------------------------
    cache_dir = Path(corpus_dir).parent / ".baseline_cache"
    cache_dir.mkdir(exist_ok=True)
    emb_path = cache_dir / f"{strategy}_v{_CACHE_VERSION}_emb.npy"
    chunks_path = cache_dir / f"{strategy}_v{_CACHE_VERSION}_chunks.json"

    if emb_path.exists() and chunks_path.exists():
        try:
            emb = np.load(str(emb_path))
            with open(chunks_path, "r", encoding="utf-8") as f:
                chunks = json.load(f)
            index = {"emb": emb, "chunks": chunks}
            _vector_index_cache[key] = index
            return index
        except Exception:
            pass  # fall through to rebuild

    # --- build from scratch ---------------------------------------------------
    from agentpack.retrieve import _get_embedding_model
    model = _get_embedding_model()
    if model is None:
        return None

    chunks: List[Dict] = []
    embed_texts: List[str] = []
    from tqdm import tqdm
    for p in tqdm(_walk_corpus(corpus_dir), desc=f"Building {strategy} index"):
        text = _extract_text_timed(p, timeout=45)
        for ch in chunk_fn(text):
            ch = {**ch, "path": p.name}
            chunks.append(ch)
            embed_texts.append(transform_fn(ch, p) if transform_fn else ch["content"])

    if not chunks:
        return None

    batch_size = 32
    all_embs: List = []
    for i in tqdm(range(0, len(embed_texts), batch_size),
                  total=(len(embed_texts) + batch_size - 1) // batch_size,
                  desc=f"Embedding {strategy}"):
        all_embs.extend(list(model.embed(embed_texts[i:i + batch_size])))

    raw = np.array(all_embs, dtype=np.float32)
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    index = {"emb": raw / norms, "chunks": chunks}

    # --- persist to disk (non-fatal) ------------------------------------------
    try:
        np.save(str(emb_path), index["emb"])
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(index["chunks"], f)
    except Exception:
        pass

    _vector_index_cache[key] = index
    return index


def _dense_query(index: dict, query_vec: np.ndarray, top_k: int, use_parent: bool = False) -> List[Dict]:
    sims = index["emb"] @ query_vec
    order = np.argsort(sims)[::-1]
    results: List[Dict] = []
    seen_parents = set()
    for i in order:
        ch = index["chunks"][int(i)]
        if use_parent:
            parent = ch.get("parent", ch["content"])
            pid = (ch["path"], parent[:64])
            if pid in seen_parents:
                continue
            seen_parents.add(pid)
            content = parent
        else:
            content = ch["content"]
        results.append({
            "path": ch["path"],
            "content": content,
            "score": float(sims[int(i)]),
            "token_count": len(_enc().encode(content)),
        })
        if len(results) >= top_k:
            break
    return results


def _embed_query(text: str) -> Optional[np.ndarray]:
    from agentpack.retrieve import _get_embedding_model
    model = _get_embedding_model()
    if model is None:
        return None
    return _normalize(np.array(list(model.embed([text]))[0], dtype=np.float32))


# --- No-LLM baselines --------------------------------------------------------

def naive_vector_search(corpus_dir: Path, query: str, top_k: int = 5) -> List[Dict]:
    """Ablation: fixed 4K chunks + dense retrieval (same embedder as AgentPack).

    Holds retrieval constant (vector) and varies only chunking, isolating
    whether AgentPack's structure-aware chunking beats blind fixed-width splits.
    """
    index = _build_dense_index(Path(corpus_dir), "naive_vector", _fixed_chunks)
    if index is None:
        return []
    qv = _embed_query(query)
    if qv is None:
        return []
    return _dense_query(index, qv, top_k)


def recursive_vector_search(corpus_dir: Path, query: str, top_k: int = 5) -> List[Dict]:
    """Industry-default recursive-character chunking + dense retrieval."""
    index = _build_dense_index(Path(corpus_dir), "recursive_vector", _recursive_chunks)
    if index is None:
        return []
    qv = _embed_query(query)
    if qv is None:
        return []
    return _dense_query(index, qv, top_k)


def parent_document_search(corpus_dir: Path, query: str, top_k: int = 5) -> List[Dict]:
    """Small-to-big: match small child chunks, return their parent block."""
    index = _build_dense_index(Path(corpus_dir), "parent_doc", _parent_child_chunks)
    if index is None:
        return []
    qv = _embed_query(query)
    if qv is None:
        return []
    return _dense_query(index, qv, top_k, use_parent=True)


_cross_encoder = None
_cross_encoder_failed = False


def _get_cross_encoder():
    global _cross_encoder, _cross_encoder_failed
    if _cross_encoder is not None or _cross_encoder_failed:
        return _cross_encoder
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        _cross_encoder = TextCrossEncoder("Xenova/ms-marco-MiniLM-L-6-v2")
    except Exception:
        _cross_encoder_failed = True
        _cross_encoder = None
    return _cross_encoder


def reranked_search(corpus_dir: Path, query: str, top_k: int = 5) -> List[Dict]:
    """AgentPack hybrid candidates re-scored by a cross-encoder reranker.

    Pulls a wide candidate pool from AgentPack's hybrid retriever, then reorders
    with a local cross-encoder. Falls back to the hybrid order if the reranker
    model is unavailable.
    """
    from agentpack.retrieve import search_pack
    pack_dir = Path(corpus_dir).parent / "agentpack_output"
    candidates = search_pack(str(pack_dir), query, top_k=max(top_k * 7, 20), mode="hybrid")
    if not candidates:
        return []

    ce = _get_cross_encoder()
    if ce is None:
        return candidates[:top_k]

    docs = [c.get("content", "") for c in candidates]
    try:
        scores = list(ce.rerank(query, docs))
    except Exception:
        return candidates[:top_k]
    for c, s in zip(candidates, scores):
        c["score"] = float(s)
    candidates.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return candidates[:top_k]


# --- LLM-in-retrieval baselines (gated) -------------------------------------

_genai_client = None


def _get_genai_client():
    global _genai_client
    if _genai_client is not None:
        return _genai_client
    try:
        from google import genai
    except ImportError:
        return None
    if not os.environ.get("GEMINI_API_KEY"):
        return None
    _genai_client = genai.Client()
    return _genai_client


def _llm_generate(prompt: str) -> str:
    client = _get_genai_client()
    if client is None:
        return ""
    try:
        resp = client.models.generate_content(model=LLM_BASELINE_MODEL, contents=prompt)
        return resp.text or ""
    except Exception:
        return ""


def _contextual_transform(chunk: Dict, file_path: Path) -> str:
    """Prepend a short LLM-generated situating blurb to a chunk before embedding.

    Anthropic's Contextual Retrieval: the blurb is cached per chunk so the index
    is built once. Falls back to the bare chunk if the LLM is unavailable.
    """
    doc_window = _extract_text(file_path)[:6000]
    prompt = (
        "Here is a document excerpt:\n<document>\n" + doc_window + "\n</document>\n\n"
        "Here is a chunk from that document:\n<chunk>\n" + chunk["content"] + "\n</chunk>\n\n"
        "Give a short (1-2 sentence) context situating this chunk within the document, "
        "to improve search retrieval. Answer with the context only."
    )
    blurb = _llm_generate(prompt)
    return f"{blurb}\n\n{chunk['content']}" if blurb else chunk["content"]


def contextual_retrieval_search(corpus_dir: Path, query: str, top_k: int = 5) -> List[Dict]:
    """Contextual Retrieval (Anthropic): chunk context blurb prepended pre-embedding."""
    index = _build_dense_index(
        Path(corpus_dir), "contextual", _recursive_chunks, transform_fn=_contextual_transform
    )
    if index is None:
        return []
    qv = _embed_query(query)
    if qv is None:
        return []
    return _dense_query(index, qv, top_k)


def hyde_search(corpus_dir: Path, query: str, top_k: int = 5) -> List[Dict]:
    """HyDE: embed an LLM-generated hypothetical answer instead of the raw query."""
    index = _build_dense_index(Path(corpus_dir), "recursive_vector", _recursive_chunks)
    if index is None:
        return []
    hypo = _llm_generate(
        f"Write a short, factual passage (3-5 sentences) that would answer this question:\n{query}"
    )
    qv = _embed_query(hypo or query)
    if qv is None:
        return []
    return _dense_query(index, qv, top_k)


# --- Registry ----------------------------------------------------------------

def get_baselines(include_llm: bool = False, skip_raw_file: bool = False) -> List[tuple]:
    """Return (name, search_fn) pairs for every baseline retrieval strategy.

    `search_fn(corpus_dir, query, top_k) -> List[Dict]`. The two LLM-in-retrieval
    baselines (Contextual Retrieval, HyDE) are only included when `include_llm`
    is True, since they incur API cost even in the deterministic pipeline.
    `skip_raw_file` omits Raw File, which returns entire documents and is
    prohibitively expensive in generative eval.
    """
    baselines = [
        ("Raw File", raw_file_search),
        ("Naive Chunk", naive_chunk_search),
        ("Naive Chunk + Vector", naive_vector_search),
        ("Recursive Chunk + Vector", recursive_vector_search),
        ("Parent-Document", parent_document_search),
        ("Cross-Encoder Rerank", reranked_search),
    ]
    if skip_raw_file:
        baselines = [(name, fn) for name, fn in baselines if name != "Raw File"]
    if include_llm:
        baselines += [
            ("Contextual Retrieval", contextual_retrieval_search),
            ("HyDE", hyde_search),
        ]
    return baselines
