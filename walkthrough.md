# Parsing & Retrieval Overhaul — Walkthrough

Covers the work done across spec `docs/specs/0001-parsing-and-retrieval-overhaul.md` and tasks
`docs/specs/0001-tasks.md` (Phases 0–4, commits `420cc1e`–`ab92720` on the `dev` branch).

---

## What Changed and Why

The original AgentPack v0.2.0 had five categories of gaps identified in a code review:

| Category | Root Problem |
|---|---|
| Parsing fidelity | Docling path did a markdown round-trip; lost page numbers and table structure |
| Retrieval correctness | No index invalidation; re-pack could silently serve stale results |
| Chunking | Single block >max_tokens was passed whole; no splitting |
| Build performance | `DocumentConverter` constructed per file; no caching; sequential |
| Retrieval quality | Min-max hybrid scoring; no metadata filtering; brute-force vectors |

---

## Phase 0 — Foundations & Safety Net (`420cc1e`)

Created the test infrastructure and baseline numbers before touching any production code.

**Files created:**
- `tests/fixtures/sample.pdf` — 2-page fixture PDF: heading on p1, paragraph on p1/p2, table on p2
- `tests/fixtures/create_sample_pdf.py` — generator script (PyMuPDF)
- `tests/fixtures/sample.md` — minimal markdown fixture
- `tests/conftest.py` — `FIXTURES_DIR` and `sample_pdf_path` pytest fixtures
- `tests/test_e2e.py` — full `pack → retrieve` round-trip test (initially `xfail(strict=True)`)
- `benchmarks/run.py` — harness measuring cold-pack, re-pack, FTS p50/recall
- `benchmarks/BASELINE.md` — recorded baseline: cold 0.101s, re-pack 0.004s, FTS p50 1.7ms

---

## Phase 1 — Correctness (`a1f5fc9`)

### PDF parser rewrite (`src/agentpack/parsers/pdf_parser.py`)

Replaced markdown round-trip with Docling structured-tree iteration:

- `_get_converter()` — module-level singleton; `DocumentConverter` built once per process with
  `PdfPipelineOptions().accelerator_options.device = "cpu"` (MPS float64 crash fix on Apple Silicon)
- `_parse_semantic()` — iterates `result.document.iterate_items()`; maps:
  - `SectionHeaderItem` → `type="heading"`, preserves `page` and `section_path`
  - `TextItem` → `type="paragraph"`, preserves `page`
  - `TableItem` → `type="table"`, exports to Markdown
- `_parse_fast_spatial()` — unchanged PyMuPDF path; dispatched when `fast_pdf=True`

### New Docling parser (`src/agentpack/parsers/docling_parser.py`)

`DoclingParser` handles `.docx`, `.pptx`, `.xlsx`, `.html`, `.htm` using the same structured-tree
path. Registered in `pack.py` alongside the PDF parser.

### Orchestrator changes (`src/agentpack/pack.py`)

- `_get_pack_version()` — reads version from `importlib.metadata` (was hardcoded `"0.1.0"`)
- `_parse_one()` — top-level function so it is picklable for `ThreadPoolExecutor`
- `DoclingParser` registered for office/HTML extensions
- `ThreadPoolExecutor(max_workers=4)` for parallel parsing; `docs_by_index` dict preserves output order
- Table blocks written as `.md` (was `.csv`)
- `manifest.tables` populated (was always `[]`)

### Chunker oversized-block splitting (`src/agentpack/chunker.py`)

Blocks exceeding `max_tokens` are now split with `overlap`:

```
overlap = int(max_tokens * overlap_percent)
start = 0
while start < block_tokens:
    end = min(start + max_tokens, block_tokens)
    sub_tokens = tokens[start:end]
    ...
    start = end - overlap if end < block_tokens else end
```

`page` and `section` metadata carried on every sub-block.

### Index invalidation (`src/agentpack/retrieve.py`)

- `_manifest_hash(pack_dir)` — sha256 of sorted chunk IDs + source checksums
- `_fts_stored_hash(conn)` / `_fts_write_hash(conn, h)` — hash stored in `_pack_meta` SQLite table
- FTS and vector indexes both stamp the hash at build time; `search_fts` / `search_vector` rebuild
  on hash mismatch instead of relying on file existence

### `agentpack index` command (`src/agentpack/cli.py`)

New CLI command that builds both FTS and vector indexes eagerly so the first query pays no build
cost. Fallback warning printed if `fastembed` is absent.

**Test changes:**
- `tests/test_parsers.py` — `test_pdf_parser_semantic` replaced: real Docling parse on `sample.pdf`
- `tests/test_e2e.py` — flipped from `xfail` to expected-pass
- `tests/test_chunker.py` — `test_chunker_oversize_block`
- `tests/test_pack.py` — `test_pack_version_in_manifest`, `test_incremental_pack_skips_unchanged`,
  table glob updated from `*.csv` → `*.md`

---

## Phase 2 — Caching & Build Performance (`64516cc`)

### Content-addressed cache (`src/agentpack/cache.py`)

New module; SQLite-backed with pickle serialization:

- `make_key(*parts)` — sha256 of joined parts (versioned keys: parser_version, model_id, etc.)
- `cache_get(cache_dir, key)` → deserialized value or `None`
- `cache_set(cache_dir, key, value)` — upsert; silently swallows exceptions

Stored in `<pack_dir>/.cache/cache.db`.

### L1 parse cache (`src/agentpack/pack.py`)

Key: `sha256(file_bytes) + parser_version + fast_flag`. On a hit, `SourceDocument` is deserialized
from cache; Docling is never invoked. Realizes incremental packing — re-pack of an unchanged corpus
performs zero Docling conversions.

### L3 embedding cache (`src/agentpack/retrieve.py`)

Key: `sha256(chunk_text) + model_id`. Unchanged chunks are never re-embedded; only cache-miss
chunks are batched through `embedding_model.embed()`.

### Dependencies (`pyproject.toml`)

Added `hnswlib>=0.7.0` as a core dependency.

**Test changes:**
- `tests/test_cache.py` — new file: round-trip, version-change miss, overwrite, db-created tests
- `tests/test_retrieve.py` — `test_embed_cache_skips_reembedding`

---

## Phase 3 — Retrieval Quality & Query Performance (`584352e`)

### Embedding model singleton (`src/agentpack/retrieve.py`)

`_embedding_model` global + `_get_embedding_model()` accessor. Model loaded once per process;
shared between index build and query time.

### Pre-normalized vectors

Vectors normalized at build time (`raw / norms`). Query similarity becomes a plain `np.dot`
(no per-query `linalg.norm` over the full matrix).

### HNSW vector backend

`hnswlib.Index(space="ip", dim=dim)` — inner-product space on pre-normalized vectors equals
cosine similarity. Built with `ef_construction=200, M=16`. Falls back to brute-force `np.dot`
when `hnswlib` is absent or index file doesn't exist.

### RRF fusion (`search_hybrid`)

Replaced min-max score normalization with Reciprocal Rank Fusion:

```python
def _rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank)
```

Summed across FTS and vector rank lists. Rank-stable across heterogeneous score scales.

### Metadata filtering

`_matches_filters()` helper; `search_pack()` accepts `source_filter`, `section_filter`,
`page_filter`. CLI `retrieve` command gains `--source`, `--section`, `--page` flags.

### L5 query cache

Key: `sha256(query) + mode + top_k + filters + pack_hash`. Memoizes repeated queries (useful for
UI and repeated evals). Stored in the same `.cache/cache.db`.

**Test changes:**
- `tests/test_retrieve.py` — RRF ordering, metadata filter, embed-cache, HNSW path, invalidation,
  unchanged-pack reuse tests; patch target changed from `TextEmbedding` to `_get_embedding_model`

---

## Phase 4 — Product Surface (`c9c8806`)

### Config file (`src/agentpack/config.py`)

New module:

```python
_DEFAULTS = {
    "chunk_max_tokens": 800, "chunk_overlap": 0.15,
    "fast": False, "remove_empty_lines": False,
    "include": [], "exclude": [],
}
def load_config(directory) -> Dict[str, Any]:  # reads agentpack.toml [pack] section
```

CLI `pack` command now reads `agentpack.toml` from `input_dir` before applying CLI overrides.

### `--fast` flag unification (`src/agentpack/cli.py`)

`--fast` replaces `--fast-pdf`. `--fast-pdf` kept as a hidden, deprecated alias (emits a yellow
warning). Both still work.

**Test changes:**
- `tests/test_config.py` — new file: defaults, toml overrides, partial toml

---

## Test Bug Fixes (`ab92720`)

Five pre-existing test failures repaired:

| Test | Root Cause | Fix |
|---|---|---|
| `test_search_pack_hybrid` | Patched `TextEmbedding` (bypassed by singleton); `vector_meta.json` missing `path`/`token_count` | Rewrote with real corpus + mock at search function level |
| `test_search_hybrid` | No `manifest.yml` → `_manifest_hash` returned `""` → stale rebuild triggered on empty dir | Added `manifest.yml` + `vector_index.hash` to test setup |
| `test_retrieve_error_handling` | `search_vector` crashed on missing manifest; `mkdir` lacked `parents=True` | Added `manifest.yml` existence guard; `mkdir(parents=True)` |
| `test_run_eval` | Called `run_eval(pack_dir=..., dataset_dir=..., model=...)` but actual signature is `run_eval(benchmark_dir)` | Rewrote to match actual API |
| `test_slice_financebench` | Patched `agentpack.eval.benchmarks.load_dataset` but it's a local import inside the function | Changed patch to `@patch("datasets.load_dataset")` |

Final suite: **59 passed, 0 failed.**

---

## Deferred Items (not implemented)

These were explicitly cut from this spec and left for future work:

| ID | Description | Status |
|---|---|---|
| G-D2 / Task 3.7 | FTS AND/BM25 precision — would reorder existing results | Needs Q2 decision; OR+RRF left as default |
| G-G3 / Task 4.2 | Secret/PII wiring — `detect-secrets` into scan path | Intent unclear (flag vs redact); Open Q3 |
| G-F2, G-F3 / Task 4.4 | SQLite as chunk-metadata source-of-truth; slim YAML manifest | Follow-up spec `0002-sqlite-source-of-truth.md` |
| G-D4 | Cross-encoder reranker hook | Deferred to v2 spec |
| G-G2 | Character-offset provenance | Deferred to v2 spec |

---

## Documentation Changes: Made vs. Not Yet Made

### Made
| File | What changed |
|---|---|
| `docs/specs/0001-parsing-and-retrieval-overhaul.md` | Created: the spec itself |
| `docs/specs/0001-tasks.md` | Created: phased task breakdown |
| `benchmarks/BASELINE.md` | Created: Phase 0 baseline numbers (fast mode, 1 doc) |

### Not yet made (stale docs)

| File | What's stale |
|---|---|
| `docs/cli-reference.md` | Missing: `--fast` flag on `pack`; `--source`/`--section`/`--page` on `retrieve`; entire `agentpack index` command; `--fast-pdf` deprecation note |
| `docs/architecture.md` | Outdated: still says PyMuPDF is the PDF parser; no mention of Docling, HNSW, content-addressed cache, or the 5-layer cache model; tables shown as CSV not MD; data-flow diagram missing vector index write path |
| `CHANGELOG.md` | Does not include this overhaul (v0.2.0 entry predates it) |
| `docs/api/parsers.md` | Missing `DoclingParser` entry |
| `README.md` | Supported-formats list and CLI examples predate `--fast`, `--source`/`--section`/`--page`, `agentpack index`, `agentpack.toml` |
| `BENCHMARK.md` | Results use the old Naive Chunk / AgentPack (Vector) comparison; no hybrid RRF numbers; would benefit from a re-run with the overhaul in place |
