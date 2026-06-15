# TODO — Hierarchical Knowledge Map

Companion to [plan.md](plan.md). Phase A is actionable now. **B and C are gated** — do not start until the preceding checkpoint passes. Check off acceptance boxes only when the verification step passes.

---

## Phase A — Structural TOC tree

### A1 · Walking skeleton (end-to-end on a simple corpus) ✅ DONE
*Goal: prove the whole pipe before adding any richness.*
- [x] `models.py`: add `SectionNode` (node_id, title, pages, has_tables, chunk_ids, nodes), `DocumentMap`, `CorpusMap` pydantic models.
- [x] `chunker.py`: persist full path — `current_metadata["section_path"] = list(block.section_path)` (keep existing `section` leaf for back-compat).
- [x] `mapper.py`: `build_map(pack_meta, docs, chunks)` producing corpus → document → **flat** section list → `chunk_ids` (nesting comes in A2).
- [x] `pack.py`: call `build_map`, write sibling `map.yml` (`yaml.dump(..., default_flow_style=False, sort_keys=False)`), on by default; `no_map` kwarg to suppress.
- [x] `tests/test_mapper.py`: 6 tests — chunker section_path, build_map structure/integrity, determinism, pack writes map, `no_map` suppresses.

**Acceptance:** ✅ `map.yml` written by default; every `chunk_ids` entry ∈ `manifest.chunks`; deterministic.
**Verify:** ✅ `pytest tests/test_mapper.py -q` → 6 passed; `test_e2e` (real PDF pack) → passed; smoke pack inspected.
**Note:** A1 groups chunks by their recorded `section_path` (flat). Small docs collapse to one chunk → one leaf; the full nested tree across all headings lands in **A2**.

### A2 · Real hierarchy ✅ DONE
- [x] Recursive nested `sections` reconstructed from `section_path` (built from `doc.blocks`, not chunk grouping → sections whose prose merged into a neighbour chunk are still represented).
- [x] Orphan chunks (no `section_path`) collected under a synthetic `__root__` node (`{source_id}_root`).
- [x] `has_tables` set from block `type == "table"` (local to each node); `pages` rolled up over each node's subtree (null when parser emits no page, e.g. txt/md).
- [x] `node_id` deterministic ordinal path (`{source_id}_sII[-JJ...]`); document/section order follows document order via `OrderedDict`.

**Acceptance:** ✅ chunks reachable across the tree; nesting matches source headings (H2 under H1); `__root__` holds orphans.
**Verify:** ✅ `pytest tests/test_mapper.py -q` → 10 passed (nested md, PDF pages, `.txt`→`__root__`, has_tables, page rollup); `test_e2e` (real PDF) → passed; smoke pack shows all 4 PDF sections + `has_tables`/`pages`.

### A3 · CLI surface ✅ DONE
- [x] `pack` gains `--no-map` (suppress map generation).
- [x] New `agentpack map <pack_dir>` command to (re)build `map.yml` from an existing pack's manifest (mirrors `index`; lazy imports per `cli.py` convention). Reconstruction is chunk-driven (no `has_tables` / chunkless sections — documented in help + stderr note).
- [x] `tests/test_map_cli.py`: `--no-map` → no `map.yml`; `agentpack map` rebuilds it; missing manifest errors.

**Acceptance:** ✅ `agentpack pack … --no-map` → no `map.yml`; `agentpack map <dir>` → `map.yml` present.
**Verify:** ✅ `pytest tests/test_map_cli.py -q`.

### A4 · Integrity (validation + regression + determinism) ✅ DONE
- [x] `validate.py`: when `map.yml` present, check FK (`chunk_ids`/`source_id` exist) recursively; **manifest checks unchanged**; absent `map.yml` is not an error.
- [x] Golden-snapshot test: committed `tests/fixtures/expected_map.yml`, diffed on every run.
- [x] Determinism test: build twice, assert equal (`test_build_map_is_deterministic`).
- [x] Regression guard: `validate_pack` (valid+bad map), `audit_pack`, and `search_pack` (via `test_e2e`) all behave correctly with the sibling file present.

**Acceptance:** ✅ all checks green; existing suite green except **3 pre-existing failures** unrelated to this work (`test_cli` ×4 lazy-import patches, `test_ui` httpx TestClient, `test_eval::test_run_eval` — all proven untouched by these commits).
**Verify:** ✅ `pytest tests/ --ignore=tests/test_ui.py -q` → 80 passed, 5 pre-existing fails.

### A5 · Prototype on a real pack → ▣ CHECKPOINT 1
- [ ] Generate `map.yml` for `benchmarks/financebench_sample` (or `phase1-benchmarks`) and read it critically.
- [ ] Confirm **eval parity**: `agentpack eval benchmarks/phase1-benchmarks` → retrieval numbers unchanged.
- [ ] **STOP — present the real `map.yml` for human go/no-go before Phase B.**

**Acceptance:** human approves tree fidelity + section quality; eval numbers unchanged.

---

## Phase B — Domain-agnostic descriptors ✅ DONE *(pending CHECKPOINT 2)*
- [x] B0 · failed/empty sources annotated `status: failed` in the map.
- [x] B1 · `yake` + `networkx` added to `pyproject.toml` (core deps); `enrich.py` scaffolded. *(Enrichment `.cache` deferred — descriptors are deterministic and dwarfed by the Docling parse; revisit only if pack-time matters.)*
- [x] B2 · YAKE keyphrases at the **section** tier (the topic signal). Synthesized doc/corpus topic *lists* were dropped — see note.
- [x] B3 · TextRank (`networkx.pagerank`) extractive `gist` (section) + `summary` (document/corpus).
- [x] B4 · structural `stats` {sections, tables, chunks}; wired into mapper (`enrich=True` default, `enrich=False` skips); offline-guard test (`test_enrichment_works_offline`); pack-time overhead « Docling parse (enrichment ~seconds, parse ~minutes).
- [ ] ▣ CHECKPOINT 2 — review descriptor quality, overhead, install size.

**Resolved:** synthesized document/corpus `topics` were **dropped** (not aggregated). Rolling many sections into one list is lossy and biases toward whatever repeats (boilerplate) or comes first; a boilerplate blocklist would be domain-specific (against the general-purpose principle). The topic signal now lives only at the **section** tier (`keyphrases`); doc/corpus keep an extractive `summary`. The map descriptors never enter the retrieval index, so this is purely about what an agent sees when navigating.

## Phase C — Opt-in LLM enrichment  ⛔ *gated by CHECKPOINT 2*
- [ ] C1 · `--enrich-llm` flag; reuse `eval/baselines.py` LLM client; deterministic cache (node-text + model id, temperature 0).
- [ ] C2 · abstractive summaries replace `gist`; graceful fallback to extractive on error; cost report; assert **zero network when flag off**.
- [ ] ▣ CHECKPOINT 3 — review summaries, cost, cache reproducibility.

---

## Deferred (post-A/B/C) — not scheduled
- [ ] Optional `[ner]` extra (GLiNER/spaCy) populating the `entities` field — opt-in, outside the offline-deterministic guarantee.
