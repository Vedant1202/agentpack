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

### A3 · CLI surface
- [ ] `pack` gains `--no-map` (suppress map generation).
- [ ] New `agentpack map <pack_dir>` command to (re)build `map.yml` for an existing pack (mirrors `index`; lazy imports per `cli.py` convention).
- [ ] `tests/test_map_cli.py`: `--no-map` produces no `map.yml`; `agentpack map` rebuilds it.

**Acceptance:** `agentpack pack … --no-map` → no `map.yml`; `agentpack map <dir>` → `map.yml` present.
**Verify:** `pytest tests/test_map_cli.py -q`.

### A4 · Integrity (validation + regression + determinism)
- [ ] `validate.py`: when `map.yml` present, check FK (`chunk_ids`/`source_id` exist) + reachability; **manifest checks unchanged**; absent `map.yml` is not an error.
- [ ] Golden-snapshot test: small fixture → committed `map.yml`, diffed on change.
- [ ] Determinism test: build twice, assert equal modulo `generated_at`.
- [ ] Regression guard: assert `validate_pack` / `search_pack` / `audit_pack` / UI loader all behave identically with the new sibling file present.

**Acceptance:** all four checks green; existing suite still passes.
**Verify:** `pytest tests/ -q` (full suite) + the build-twice diff from plan.md.

### A5 · Prototype on a real pack → ▣ CHECKPOINT 1
- [ ] Generate `map.yml` for `benchmarks/financebench_sample` (or `phase1-benchmarks`) and read it critically.
- [ ] Confirm **eval parity**: `agentpack eval benchmarks/phase1-benchmarks` → retrieval numbers unchanged.
- [ ] **STOP — present the real `map.yml` for human go/no-go before Phase B.**

**Acceptance:** human approves tree fidelity + section quality; eval numbers unchanged.

---

## Phase B — Domain-agnostic descriptors  ⛔ *gated by CHECKPOINT 1*
- [ ] B1 · add `yake` + `networkx` to `pyproject.toml`; scaffold `enrich.py`; extend `.cache` (versioned namespace, keyed on node-text hash).
- [ ] B2 · YAKE keyphrases at section/doc/corpus tiers.
- [ ] B3 · TextRank (`networkx.pagerank`) extractive `gist`/`summary`.
- [ ] B4 · structural `stats`; wire into mapper; **offline-guard test** (no network, no data download); pack-time overhead measured « parse time.
- [ ] ▣ CHECKPOINT 2 — review quality, overhead, install size.

## Phase C — Opt-in LLM enrichment  ⛔ *gated by CHECKPOINT 2*
- [ ] C1 · `--enrich-llm` flag; reuse `eval/baselines.py` LLM client; deterministic cache (node-text + model id, temperature 0).
- [ ] C2 · abstractive summaries replace `gist`; graceful fallback to extractive on error; cost report; assert **zero network when flag off**.
- [ ] ▣ CHECKPOINT 3 — review summaries, cost, cache reproducibility.

---

## Deferred (post-A/B/C) — not scheduled
- [ ] Optional `[ner]` extra (GLiNER/spaCy) populating the `entities` field — opt-in, outside the offline-deterministic guarantee.
