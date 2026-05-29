# Implementation Plan: Parsing & Retrieval Overhaul

> Companion to `0001-parsing-and-retrieval-overhaul.md` (Phase 3 — Tasks).
> Status: **awaiting human approval before implementation.**
> Task IDs map to spec gap IDs (`G-*`). Sizes: XS=1 file, S=1–2, M=3–5, L=5–8.

## Overview
Break the approved spec into small, verifiable tasks. Ordered by dependency: a safety net first
(so correctness fixes are provable), then correctness, then caching/build perf, then retrieval
quality/query perf, then deferrable product surface.

## Architecture Decisions (locked in Phase 1)
- Consume Docling's **structured document tree**, not a markdown round-trip (preserves page + tables).
- **HNSW (`hnswlib`)** is the default vector backend (core dep); brute-force `np.dot` is the fallback.
- A single **`--fast`** mode = PyMuPDF + `sqlite-vec` (replaces `--fast-pdf`, kept as deprecated alias).
- **Content-addressed cache** in one `cache.db`; keys carry a version component for self-invalidation.
- Perf acceptance is **directional** + a baseline benchmark; numeric gates may come later from data.

---

## Phase 0 — Foundations & Safety Net

### Task 0.1: Make Docling installable & add fixture PDF
**Description:** Ensure `pip install -e ".[test]"` yields an importable `docling`; add a tiny
committed fixture PDF containing a heading, a paragraph spanning a known page, and a table.
**Acceptance criteria:**
- [ ] `python -c "import docling"` succeeds in a clean install.
- [ ] `tests/fixtures/sample.pdf` exists with ≥2 pages and one table.
**Verification:**
- [ ] `pip install -e ".[test]" && python -c "import docling"`
- [ ] Manual: open fixture, confirm a known string is on a known page.
**Dependencies:** None
**Files:** `pyproject.toml`, `tests/fixtures/sample.pdf`, `tests/conftest.py`
**Scope:** S

### Task 0.2: Replace brittle semantic PDF test with a real-fixture test
**Description:** Rewrite `test_pdf_parser_semantic` to run the real Docling path on the fixture
(no module-patch mock), asserting it returns blocks (G-A1, G-A5).
**Acceptance criteria:**
- [ ] Test parses `sample.pdf` via `PDFParser(fast_pdf=False)` with Docling actually installed.
- [ ] Asserts ≥1 heading block and ≥1 paragraph block returned.
**Verification:**
- [ ] `python -m pytest tests/test_parsers.py::test_pdf_parser_semantic -q`
**Dependencies:** 0.1
**Files:** `tests/test_parsers.py`
**Scope:** S

### Task 0.3: Add failing end-to-end round-trip regression test
**Description:** Build a fixture corpus (the PDF + 1 `.md` + 1 `.csv`) and a `pack → index →
retrieve` test asserting page, section, and table citations survive end-to-end. Expected to
**fail** initially — it is the regression net for Phase 1.
**Acceptance criteria:**
- [ ] Test packs the fixture corpus to a temp dir and runs a retrieve query.
- [ ] Asserts a result carries `citation.page` and a table appears in `tables/`.
- [ ] Marked `xfail(strict=True)` until Phase 1 closes it (then flip to expected-pass).
**Verification:**
- [ ] `python -m pytest tests/test_e2e.py -q` (xfails cleanly now).
**Dependencies:** 0.1
**Files:** `tests/test_e2e.py`, `tests/fixtures/`
**Scope:** M

### Task 0.4: Baseline benchmark harness (G-E7)
**Description:** A repeatable script measuring cold-pack time, re-pack time, and query p50/recall
across a couple of corpus sizes; prints a comparison table. Records today's numbers.
**Acceptance criteria:**
- [ ] `python -m benchmarks.run` prints pack/re-pack/query timings.
- [ ] Baseline numbers committed to `benchmarks/BASELINE.md`.
**Verification:**
- [ ] `python -m benchmarks.run --quick` completes and prints a table.
**Dependencies:** None
**Files:** `benchmarks/run.py`, `benchmarks/BASELINE.md`
**Scope:** M

### ✅ Checkpoint: Foundations
- [ ] CI runs Docling for real; 0.2 passes; 0.3 xfails as designed; baseline table committed.
- [ ] Review with human before Phase 1.

---

## Phase 1 — Correctness *(Tracks 1.1/1.2/1.3 parallelizable)*

### Task 1.1: Parse Docling structured tree & preserve page numbers (G-A2)
**Description:** Replace the markdown round-trip in `PDFParser.parse` with iteration over
`docling_result.document` items, emitting `DocumentBlock`s with `page` populated for headings and
paragraphs.
**Acceptance criteria:**
- [ ] Semantic-mode blocks carry the correct `page` for the fixture.
- [ ] Section hierarchy preserved in `section_path`.
**Verification:**
- [ ] `python -m pytest tests/test_parsers.py -q -k semantic`
- [ ] New unit test asserts a known string's block has the expected `page`.
**Dependencies:** 0.2
**Files:** `src/agentpack/parsers/pdf_parser.py`, `tests/test_parsers.py`
**Scope:** M

### Task 1.2: Emit `type="table"` blocks + record tables in manifest (G-A3)
**Description:** Map Docling table items to `DocumentBlock(type="table")`; ensure `pack.py` writes
them to `tables/` and populates the manifest `tables` list (currently always empty).
**Acceptance criteria:**
- [ ] Fixture table becomes a `table` block, written to `tables/*.csv|md`.
- [ ] `manifest.tables` is non-empty and references the table block id.
- [ ] Table block is excluded from overlap duplication (chunker already guards this).
**Verification:**
- [ ] `python -m pytest tests/test_parsers.py -q -k table`
- [ ] Manual: `agentpack pack tests/fixtures --out /tmp/p && ls /tmp/p/tables`
**Dependencies:** 1.1
**Files:** `src/agentpack/parsers/pdf_parser.py`, `src/agentpack/pack.py`
**Scope:** M

### Task 1.3: Reuse a single DocumentConverter per process (G-A4)
**Description:** Lift `DocumentConverter()` out of per-file `parse()` into a cached/shared instance.
**Acceptance criteria:**
- [ ] Converter constructed at most once across a multi-PDF pack.
**Verification:**
- [ ] Unit test with a spy asserts one construction for a 2-PDF pack.
**Dependencies:** 1.1
**Files:** `src/agentpack/parsers/pdf_parser.py`
**Scope:** S

### Task 1.4: Fix manifest version (G-F1)
**Description:** Read pack version from package metadata instead of hardcoded `"0.1.0"`.
**Acceptance criteria:**
- [ ] `manifest.pack.version` equals the installed package version.
**Verification:**
- [ ] `python -m pytest tests/test_pack.py -q -k version`
**Dependencies:** None
**Files:** `src/agentpack/pack.py`
**Scope:** XS

### Task 1.5: Index invalidation via pack content hash (G-B1)
**Description:** Stamp a pack content hash into the FTS and vector indexes; on search, rebuild when
the stored hash ≠ current manifest hash instead of trusting file existence.
**Acceptance criteria:**
- [ ] Re-packing new content into an existing dir → next retrieve reflects new content.
- [ ] Unchanged pack → index reused (no rebuild).
**Verification:**
- [ ] `python -m pytest tests/test_retrieve.py -q -k invalidat`
**Dependencies:** None
**Files:** `src/agentpack/retrieve.py`, `tests/test_retrieve.py`
**Scope:** M

### Task 1.6: `agentpack index` command (G-B2)
**Description:** Add a CLI command that builds both indexes up front; `pack` optionally invokes it.
**Acceptance criteria:**
- [ ] `agentpack index <pack_dir>` builds FTS + vector indexes idempotently.
- [ ] First retrieve after `index` performs no build.
**Verification:**
- [ ] Manual: `agentpack index /tmp/p && agentpack retrieve /tmp/p "q"`
**Dependencies:** 1.5
**Files:** `src/agentpack/cli.py`, `src/agentpack/retrieve.py`
**Scope:** S

### Task 1.7: Split oversized blocks in chunker (G-C1)
**Description:** When a single block exceeds `max_tokens`, split it (with overlap) so no chunk
exceeds the limit; preserve metadata (page/section) across splits.
**Acceptance criteria:**
- [ ] A synthetic ~5k-token block yields multiple chunks, each ≤ `max_tokens`.
- [ ] Page/section metadata carried on each split chunk.
**Verification:**
- [ ] `python -m pytest tests/test_chunker.py -q -k oversize`
**Dependencies:** None
**Files:** `src/agentpack/chunker.py`, `tests/test_chunker.py`
**Scope:** M

### ✅ Checkpoint: Correctness
- [ ] Flip Task 0.3 from xfail → expected pass (pages + tables cited end-to-end).
- [ ] No chunk exceeds `max_tokens`; re-pack never serves stale results.
- [ ] Full suite green. Review with human.

---

## Phase 2 — Caching & Build Performance

### Task 2.1: `cache.db` scaffold + versioned key helpers (G-H5)
**Description:** Create a SQLite-backed cache store with helpers that build keys carrying
`parser_version` / `chunker_version` / `model_id`.
**Acceptance criteria:**
- [ ] Cache get/set round-trips; changing a version component misses the cache.
**Verification:**
- [ ] `python -m pytest tests/test_cache.py -q`
**Dependencies:** None
**Files:** `src/agentpack/cache.py`, `tests/test_cache.py`
**Scope:** S

### Task 2.2: L1 parse cache → incremental packing (G-H1, G-E3)
**Description:** Key serialized `SourceDocument` by `sha256(file_bytes)+parser_version+opts`; skip
Docling on cache hits. Realizes incremental packing.
**Acceptance criteria:**
- [ ] Re-pack of an unchanged corpus performs zero Docling conversions.
- [ ] Re-pack with 1/N changed reprocesses ~1 file.
**Verification:**
- [ ] `python -m pytest tests/test_pack.py -q -k incremental`
- [ ] Benchmark (0.4) shows re-pack speedup.
**Dependencies:** 2.1, 1.1
**Files:** `src/agentpack/pack.py`, `src/agentpack/cache.py`
**Scope:** M

### Task 2.3: L3 embedding cache (G-H2)
**Description:** Key vectors by `sha256(chunk_text)+model_id`; unchanged chunks are never re-embedded.
**Acceptance criteria:**
- [ ] Editing one paragraph re-embeds only the affected chunk(s).
**Verification:**
- [ ] `python -m pytest tests/test_retrieve.py -q -k embed_cache`
**Dependencies:** 2.1
**Files:** `src/agentpack/retrieve.py`, `src/agentpack/cache.py`
**Scope:** M

### Task 2.4: Parallel parsing across files (G-E4)
**Description:** Parse files via a process pool; keep output order stable and cache access safe.
**Acceptance criteria:**
- [ ] Manifest is identical to the sequential run.
- [ ] Wall-clock speedup on a multi-file corpus.
**Verification:**
- [ ] `python -m pytest tests/test_pack.py -q -k parallel`
- [ ] Benchmark (0.4) shows cold-pack speedup.
**Dependencies:** 2.2
**Files:** `src/agentpack/pack.py`
**Scope:** M

### ✅ Checkpoint: Caching & Build Perf
- [ ] Unchanged re-pack does zero Docling work; benchmark deltas recorded. Review with human.

---

## Phase 3 — Retrieval Quality & Query Performance *(parallelizable)*

### Task 3.1: Embedding-model singleton (G-E1)
**Description:** Load `TextEmbedding` once per process; share between index build and query.
**Acceptance criteria:** [ ] Model constructed once across a build + multiple queries.
**Verification:** [ ] Unit test with a spy asserts single construction.
**Dependencies:** None | **Files:** `src/agentpack/retrieve.py` | **Scope:** S

### Task 3.2: Pre-normalized vectors + dot-product query (G-E2)
**Description:** Normalize vectors at build time; query similarity becomes a plain dot product.
**Acceptance criteria:** [ ] No per-query `linalg.norm` over the matrix; results unchanged within tolerance.
**Verification:** [ ] `python -m pytest tests/test_retrieve.py -q -k normaliz`
**Dependencies:** 3.1 | **Files:** `src/agentpack/retrieve.py` | **Scope:** S

### Task 3.3: Vector-backend abstraction + HNSW default (G-E5)
**Description:** Introduce a backend interface; implement `hnswlib` HNSW as default; keep
brute-force as fallback when no extension/empty corpus.
**Acceptance criteria:**
- [ ] Vector search on ~10k-chunk fixture returns top-k via HNSW with >0.95 recall@10 vs exact.
- [ ] Falls back to brute-force when hnswlib index absent.
**Verification:** [ ] `python -m pytest tests/test_retrieve.py -q -k hnsw`
**Dependencies:** 3.2 | **Files:** `src/agentpack/retrieve.py`, `pyproject.toml` | **Scope:** M

### Task 3.4: `sqlite-vec` backend + `--fast` generalization (G-E6)
**Description:** Add `sqlite-vec` backend; generalize `--fast-pdf` → `--fast` (PyMuPDF + sqlite-vec),
keeping `--fast-pdf` as a deprecated alias.
**Acceptance criteria:**
- [ ] `--fast` selects PyMuPDF + sqlite-vec; default selects Docling + HNSW.
- [ ] `--fast-pdf` still works and warns it's deprecated; no standalone vector-backend flag.
**Verification:** [ ] `python -m pytest tests/test_cli.py -q -k fast`
**Dependencies:** 3.3 | **Files:** `src/agentpack/cli.py`, `src/agentpack/pack.py`, `src/agentpack/retrieve.py` | **Scope:** M

### Task 3.5: RRF fusion (G-D1)
**Description:** Replace min-max hybrid scoring with Reciprocal Rank Fusion.
**Acceptance criteria:** [ ] Fusion is rank-based; unit test on known rankings matches expected RRF order.
**Verification:** [ ] `python -m pytest tests/test_retrieve.py -q -k rrf`
**Dependencies:** None | **Files:** `src/agentpack/retrieve.py` | **Scope:** S

### Task 3.6: Metadata filtering (G-D3)
**Description:** Allow `retrieve` to filter by `source_id` / `page` / `section` via CLI flags.
**Acceptance criteria:** [ ] `--source`/`--section` constrain results correctly.
**Verification:** [ ] `python -m pytest tests/test_retrieve.py -q -k filter`
**Dependencies:** None | **Files:** `src/agentpack/retrieve.py`, `src/agentpack/cli.py` | **Scope:** M

### Task 3.7: FTS precision — AND/BM25 *(GATED on Q2)*
**Description:** Move FTS off pure OR-of-terms toward AND/phrase + BM25 weighting. **Do not start
until Q2 is decided** (changes existing result ordering).
**Acceptance criteria:** [ ] Multi-term query ranks all-term matches above single-term matches.
**Verification:** [ ] `python -m pytest tests/test_retrieve.py -q -k fts_precision`
**Dependencies:** Q2 decision | **Files:** `src/agentpack/retrieve.py` | **Scope:** S

### Task 3.8: Query cache (optional, G-H4)
**Description:** Memoize results by `sha256(query+mode+top_k+pack_hash)`.
**Acceptance criteria:** [ ] Identical repeat query served without re-search.
**Verification:** [ ] `python -m pytest tests/test_retrieve.py -q -k query_cache`
**Dependencies:** 2.1, 1.5 | **Files:** `src/agentpack/retrieve.py`, `src/agentpack/cache.py` | **Scope:** S

### ✅ Checkpoint: Retrieval
- [ ] recall@10 >0.95 vs exact; hybrid ordering verified; resources loaded once. Review with human.

---

## Phase 4 — Product Surface *(deferrable; do per-item)*

### Task 4.1: Config file `agentpack.toml` (G-G4) — Scope S
Reproducible packs (chunk size, embedding model, included types). Deps: none.

### Task 4.2: Secret/PII handling in scan (G-G3) — Scope M
Wire `detect-secrets` into scan/parse; flag or redact before packing. Deps: none.
*Confirm intent: flag-only vs redact (Open Q3).*

### Task 4.3: New formats via Docling — docx/pptx/xlsx/html (G-G1) — Scope M
One parser registration each; reuse the structured-tree path from 1.1. Deps: 1.1.

### Task 4.4: SQLite as source of truth + chunk consolidation (G-F2/F3) — Scope L *(GATED on Q1)*
Migrate chunk metadata into SQLite; slim YAML manifest; consolidate chunk storage. **May split to
its own spec.** Deps: Q1 decision.

### ✅ Checkpoint: Complete
- [ ] All non-deferred acceptance criteria met; benchmark before/after recorded; ready for release.

---

## Risks and Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Docling structured-tree API varies by version | High | Pin Docling; cover with real-fixture test (0.2) before refactor (1.1) |
| HNSW recall non-determinism | Med | Keep brute-force as ground truth; assert recall threshold not equality (3.3) |
| Cache-key bug serves stale output | High | Versioned keys + invalidation tests are acceptance criteria (2.1, 1.5) |
| `--fast` rename breaks scripts | Low | Keep `--fast-pdf` as deprecated alias (3.4) |
| Phase 4 scope creep | Med | Gated behind Q1/Q2; can fork to v2 spec |

## Open Questions (blocking specific tasks only)
- **Q2 — FTS ranking (blocks 3.7):** AND/BM25 (reorders results) vs keep OR + RRF only?
- **Q1 — Format change (blocks 4.4):** SQLite source-of-truth in this spec or a follow-up?

## Parallelization Summary
- Sequential gates: Phase 0 → 1 → 2.
- Parallel: Phase 1 tracks (1.1/1.2/1.3 share files — coordinate; 1.4–1.7 independent); most of Phase 3.
- Phase 4 items mutually independent and individually deferrable.
