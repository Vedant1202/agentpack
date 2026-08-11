# TODO — Corpus Concept Graph (graph.yml)

Companion to [concept-graph-plan.md](concept-graph-plan.md). Implements [docs/specs/0003-corpus-concept-graph.md](../docs/specs/0003-corpus-concept-graph.md). Check off acceptance boxes only when the verification command actually passes; update each task's section with evidence (test counts, output snippets) as you complete it — see `trust-layer-todo.md` for the expected style.

---

## ⚠️ READ THIS FIRST (handoff header for the implementing agent)

**Required reading, in order, before writing any code:**
1. [docs/specs/0003-corpus-concept-graph.md](../docs/specs/0003-corpus-concept-graph.md) — the source of truth. §2 is a table of facts **verified live against this repo** (embeddings only exist at index time; markdown links survive into chunk text; map.yml ids; seeded Louvain determinism). Do **not** re-litigate them. If one contradicts what you observe, stop and report — do not improvise.
2. [tasks/trust-layer-todo.md](trust-layer-todo.md) — the previous feature's todo, as an example of the expected working style: verify APIs live before implementing against them, run the named test selector *and* the full suite after every task, check off with evidence, and record any real bug you find along the way in the todo entry itself.
3. [SPEC.md](../SPEC.md) §3 — the `map.yml` schema you are consuming (section `node_id`, `keyphrases`, `chunk_ids`).

**Test invocation (this exact form, always):**
```bash
PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/ -q
```
Bare `python -m pytest` hits the anaconda base environment (old fastapi/starlette, no umap) and fails spuriously. Always prefix `PYTHONPATH="$PWD/src"` and use `./venv/bin/python`.

**Green baseline:** `202 passed, 1 failed` — the failure is `tests/test_eval.py::test_run_eval` (`FileNotFoundError: Manifest not found`), **pre-existing on clean dev, not yours to fix**. Any run with more than that one failure means you broke something; stop and fix before proceeding.

**Process rules (non-negotiable):**
- Branch `feat/corpus-concept-graph` off `dev`. PR into `dev`, **never** `main`.
- Full suite after every task; todo updated with evidence after every task.
- **Stop at the ▣ CHECKPOINT below and wait for human review.** Do not start Phase B without an explicit go.
- Commit per task or per coherent pair of tasks; conventional-commit style matching the repo's history (`feat(graph): …`, `chore: …`).

**Do-not-touch list** (spec §8 boundaries, restated as filenames): `src/agentpack/retrieve.py` (until Phase B, and then only the append-only hook B1 describes), `src/agentpack/parsers/*`, `chunker.py`, `cache.py`, `trust.py`, `audit.py`, `enrich.py`, `mapper.py`, and the `manifest.yml`/`map.yml` schemas. The graph reads pack **output** artifacts only. If a task seems to require touching any of these, the task is being done wrong — re-read the spec, then ask.

**Two recurring requirements** (every task from T1 on): (1) **determinism** — no dict/set iteration order may reach `graph.yml` or the report; nodes sorted by (kind, id), edges by (source, target, relation); the build-twice test must stay green in every task, and (2) **never-raise** — `grapher` failures degrade to "no graph.yml + one warning line", never a crashed pack (mirror `trust.py`'s posture and `scan_for_hidden_content`'s single outer try/except).

---

## Phase 0 — Independent leaves

### T0.1 · `[graph]` config section ✅ DONE
- [x] `config.py`: added `_GRAPH_DEFAULTS = {"enabled": True, "df_cap": 0.30, "min_docs": 2, "similarity_threshold": 0.80}` and a `[graph]` section read parallel to `[pack]`. Returned dict gets a `"graph"` sub-dict; existing `[pack]` top-level keys untouched (verified by a dedicated namespace-independence test).
- [x] Range validation via `_validate_graph_settings` + `_is_number` (excludes `bool`, since `bool` subclasses `int` in Python and TOML `true`/`false` must not silently pass a numeric range check — caught this before it became a bug, not after): `df_cap` ∈ (0,1], `min_docs` ≥ 1 (real int, not bool), `similarity_threshold` ∈ (0,1]. Out-of-range/wrong-type → one stderr warning naming the key + offending value, falls back to default, never raises. `min_docs = 1` explicitly tested as **valid**, not an error.

**Acceptance:** ✅ defaults when no toml/no `[graph]` section; overrides honored (including partial sections — unset keys keep their default); boundary values tested precisely (`df_cap=1.0` valid, `df_cap=0` invalid); bool-as-int rejected for `min_docs`; `[pack]` keys provably independent of `[graph]`.
**Verify:** ✅ TDD — 11 new tests written first and confirmed RED (`KeyError: 'graph'`) against the pre-change `config.py`, then GREEN after implementation. `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_config.py -v` → **14 passed** (3 pre-existing + 11 new). Full suite: `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/ -q` → **213 passed, 1 pre-existing failure** (`test_run_eval`) — exactly baseline (202) + 11 new, zero regressions. Module import + `agentpack --version` sanity-checked directly.
**Commits:** `df688ef` (spec/plan/todo docs), `99efeb5` (implementation).

### T0.2 · Graph pydantic models ✅ DONE
- [x] `models.py`: added `GraphNode` (`id`, `kind: Literal["document","section","concept"]`, `label`, `doc: Optional[str]`, `community: Optional[int]`), `GraphEdge` (`source`, `target`, `relation: str`, `basis: Literal["structural","keyphrase","embedding"]`), `CorpusGraph` (`graph_version: int = 1`, `pack: Dict`, `params: Dict`, `nodes`, `edges`, `communities: List[Dict]`). Placed after `CorpusMap`, mirroring its style exactly. **`relation` deliberately left as plain `str`, not a `Literal`** (unlike `basis`) — `basis` is a fixed 3-value set the spec already closes (structural/keyphrase/embedding); `relation` values arrive incrementally as T1 (`contains`) → T2 (`mentions`) → T3 (`references`) → B1 (`similar_to`) land, and constraining it now would mean editing `models.py` again every phase — which the task itself says not to do ("additive only — touch nothing else"). Zero changes to any existing class.

**Acceptance:** ✅ models import cleanly; `Literal` constraints verified live — a bad `kind` and a bad `basis` both correctly raise `pydantic.ValidationError`, not silently accepted; no existing test broken.
**Verify:** ✅ RED confirmed first (`ImportError: cannot import name 'GraphNode'` against the pre-change file) — no dedicated test file was added, per this task's own scope ("no tests of their own — exercised by T1") and matching the repo's existing convention (`SectionNode`/`DocumentMap`/`CorpusMap` have no dedicated test file either; they're validated indirectly through `test_mapper.py`, the same role `test_grapher.py` will play here). GREEN confirmed via direct construction + validation checks (shown above). Full suite: `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/ -q` → **213 passed, 1 pre-existing failure** (`test_run_eval`) — identical to the T0.1 count, zero new tests as expected, zero regressions.
**Commit:** `af615a9`.

---

**Phase 0 complete.** Both leaves land clean; `grapher.py` (T1) can now import validated config and models.

---

## Phase A — Structural graph, walking skeleton first

### T1 · Walking skeleton: documents + sections + `contains`, end-to-end
- [ ] New `src/agentpack/grapher.py`: `build_graph(pack_dir: str, params: dict) -> Optional[dict]` — read `map.yml` + `manifest.yml` from `pack_dir` (spec §3: post-processor over disk artifacts; **no** parser/pipeline imports), emit document nodes (id = manifest `source_id`, label = source path), section nodes (id = map `node_id`, label = title, `doc` = owning source_id) for **top-level sections only**, and `contains` edges (doc → top-level section, `basis: structural`). Include the `params:` block (spec §4a) and `pack:` meta (name, generated_at, graph_version) mirroring map.yml's meta shape.
- [ ] `write_graph(pack_dir, params)` wrapper: **auto-skip** with a one-line stderr note (not a warning) when manifest has <2 sources with `status: success` (spec §3 gating); single outer try/except so any internal failure prints one warning and writes nothing (never-raise).
- [ ] `pack.py`: hook after the map block (pack.py:255-266), same shape as the `if not no_map:` block, behind a new `no_graph: bool = False` kwarg on `write_pack`. Effective value combines the CLI flag and toml `enabled` in T6 — for now just the kwarg.
- [ ] Serialization: `yaml.dump(..., default_flow_style=False, sort_keys=False)`; nodes sorted by (kind, id), edges by (source, target, relation).
- [ ] Tests (`tests/test_grapher.py`, fixtures built in-test like `test_mapper.py` — no committed binaries): end-to-end pack of a 2-doc markdown corpus → `graph.yml` exists with doc+section nodes and contains edges; single-doc corpus → no `graph.yml`, pack succeeds; corrupt `map.yml` → pack succeeds, no `graph.yml`, one warning; build twice → byte-identical modulo `generated_at`.

**Acceptance:** all four tests pass; full suite = baseline; `manifest.yml`/`map.yml` byte-identical to pre-change output for the same corpus (graph is purely additive).
**Verify:** `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_grapher.py -v`; full suite.

### T2 · Concept promotion + `mentions` edges
- [ ] One slug function (the spec §4 recipe, verbatim): `re.sub(r"_+", "_", re.sub(r"[^\w]+", "_", phrase.casefold())).strip("_")`; concept id `c_<slug>`. This is the **only** place slugs are minted.
- [ ] Promotion gates, ALL must pass (spec §4): slug present in `keyphrases` of sections from ≥ `params["min_docs"]` distinct documents; slug in ≤ `params["df_cap"]` fraction of all sections; slug ≥4 chars and not purely numeric/underscore.
- [ ] Concept node label = most frequent surface form among the contributing keyphrases, ties broken lexically. `mentions` edges (section → concept, `basis: keyphrase`). Sections with an edge now also become nodes even if not top-level (spec §4 nodes rule).
- [ ] Tests: shared keyphrase across 2 docs → concept + mentions edges spanning both; keyphrase in 1 doc only → no concept; keyphrase above df_cap → no concept; `min_docs=3` via params → 2-doc keyphrase rejected (config effect); slug collision ("Balance Sheet"/"balance-sheet") → one concept; determinism still green.

**Acceptance:** every gate has a test proving both sides of its boundary; full suite = baseline.
**Verify:** `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_grapher.py -v -k concept`; full suite.

### T3 · `references` edges from markdown links
- [ ] Extract links from the doc's **chunk text on disk** (spec §2: raw markdown survives into `chunks/*.md` — zero parser changes): inline `[x](target)`, reference-style `[x]: target`, `[[wikilink]]`. Resolve target against manifest source paths by filename match; drop external URLs (scheme prefix) and unresolved targets **silently**; dedupe per (source_doc, target_doc); no self-loops. Edge: doc → doc, `relation: references`, `basis: structural`.
- [ ] Tests: `./b.md` link → one edge; `https://…` → nothing; link to un-packed file → nothing; three links to the same doc → one edge; link to self → nothing.

**Acceptance:** all five cases pass; determinism green; full suite = baseline.
**Verify:** `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_grapher.py -v -k reference`; full suite.

### T4 · Communities (seeded Louvain + determinism hardening)
- [ ] Copy the hardening recipe exactly (spec §3, verified on networkx 3.6.1): build a **fresh** `nx.Graph` with `add_nodes_from(sorted(ids))` then edges inserted in sorted order; `nx.community.louvain_communities(G, seed=42)`; re-index communities by size desc with `tuple(sorted(members))` tiebreak so ids never churn. Isolated nodes each form their own community.
- [ ] Labels: highest-degree **concept** member's phrase; ties by node id; a community with no concept members falls back to its highest-degree node's label. `community: <int>` on every node; top-level `communities:` list of `{id, label, size}` ordered by id.
- [ ] Tests: two clearly-separated topic clusters in a 4-doc fixture → ≥2 communities; run twice → identical community ids (the hardening test); label rule + fallback.

**Acceptance:** communities stable across repeated builds; full suite = baseline.
**Verify:** `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_grapher.py -v -k communit`; full suite.

### T5 · `reports/graph_report.md`
- [ ] Deterministic report (spec §4): Top concepts by degree (top 10), Bridge concepts (neighbors span ≥2 communities), Isolated documents (no cross-document edge), Communities (label + member counts). Written by the same builder call, standalone file, `audit` untouched.
- [ ] Tests: report exists and contains the four sections; a doc with no cross-doc edges appears under Isolated; byte-determinism modulo date.

**Acceptance:** report renders on the T2/T4 fixtures; full suite = baseline.
**Verify:** `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_grapher.py -v -k report`; full suite.

### T6 · CLI surface
- [ ] `pack`: `--no-graph` flag mirroring `--no-map` (cli.py:35); effective value = CLI flag OR NOT toml `enabled` (precedence per spec §4a, matching the `effective_fast` pattern at cli.py:47); thread through `write_pack(no_graph=…)`.
- [ ] New `agentpack graph <pack_dir>` command mirroring `map_cmd` (cli.py:175-199): lazy imports, red error + exit 1 when `manifest.yml` missing, green confirmation. Uses **recorded `params:`** from an existing `graph.yml` when present; falls back to defaults when absent. No `--config` override (deferred, spec §4a).
- [ ] Tests (`tests/test_graph_cli.py`, mirror `test_map_cli.py`): `--no-graph` → no graph.yml; toml `enabled=false` in input dir → no graph.yml; `--no-graph` beats toml `enabled=true`; rebuild parity — `agentpack graph` output byte-identical to pack-time modulo `generated_at`; rebuild with a **conflicting toml in CWD** still uses recorded params.

**Acceptance:** all five CLI tests pass; full suite = baseline.
**Verify:** `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_graph_cli.py -v`; full suite.

### T7 · Validation
- [ ] `validate.py`: when `graph.yml` present, FK-check — every node `doc` ref ∈ manifest source_ids; every section node id ∈ map node_ids; every edge endpoint ∈ graph node ids; every node `community` ∈ communities ids. Absent `graph.yml` is not an error. Mirror `_validate_map` (validate.py:76-100): separate `_validate_graph` helper, errors as strings.
- [ ] Tests (extend `tests/test_validate.py`): valid graph passes; edge to unknown node reported; section node with unknown map id reported; absent graph.yml → no error.

**Acceptance:** FK coverage per spec §3; full suite = baseline.
**Verify:** `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_validate.py -v`; full suite.

### T8 · Regression sweep + real-corpus smoke
- [ ] Full suite green at baseline (+ all new tests).
- [ ] Smoke: `PYTHONPATH="$PWD/src" ./venv/bin/python -m agentpack.cli pack demo_corpus --out /tmp/graph_smoke --fast` → graph.yml built (4 sources); inspect graph.yml + reports/graph_report.md by eye; `agentpack graph /tmp/graph_smoke` parity; `agentpack validate /tmp/graph_smoke` clean; a single-doc corpus skips.
- [ ] Confirm `retrieve`/`audit`/`validate` on a pre-existing pack **without** graph.yml behave identically (spec §1: additive).

**Acceptance:** smoke outputs recorded in this file as evidence (paste the graph_report.md sections for the checkpoint reviewer); zero regressions.
**Verify:** commands above.

---

## ▣ CHECKPOINT — STOP HERE FOR HUMAN REVIEW
- [ ] Pack `demo_corpus/` and `benchmarks/financebench_sample`; paste top concepts, community labels, and isolated-documents list into this file.
- [ ] Human reviews: are promoted concepts real topics or noise? Are communities coherent? Is `df_cap = 0.30` sane on real filings?
- [ ] **Do not begin Phase B without an explicit go.** (Threshold/gate tuning decided here lands in spec §10 notes, not silently in code.)

---

## Phase B — Similarity edges ⛔ *gated by checkpoint*

### B1 · `similar_to` edges at index time
- [ ] `grapher.py`: `add_similarity_edges(pack_dir, params)` — section centroid = mean of the section's chunks' **already-normalized** vectors (map.yml `chunk_ids` → index metadata order), cosine ≥ `params["similarity_threshold"]`, edges section ↔ section across **different documents** only, `basis: embedding`; merge into existing `graph.yml` keyed (source, target, relation) — **idempotent**; recompute communities after merge.
- [ ] Wiring: append-only call at the END of `build_vector_index` (retrieve.py:132) after the existing index write — this is the single permitted `retrieve.py` change, additive only, wrapped in the same never-raise posture; plus `agentpack graph --with-similarity` for explicit runs (reuses the L3 embedding cache via the index).
- [ ] Tests: two near-identical sections in different docs → edge at 0.80; unrelated sections → no edge; threshold from params honored (a lowered threshold admits an edge the default rejects); run index twice → no duplicate edges; graph.yml without similarity (pack-time) still validates; full suite = baseline.

**Acceptance:** idempotency proven; `retrieve.py` diff is append-only (show the diff in evidence); full suite = baseline.
**Verify:** `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_grapher.py -v -k similar`; full suite.

---

## Deferred (Phase C — not yours; see spec §5/§9)
- RRF third contributor in `search_hybrid` — retrieval behavior change, **ask-first**, gated on `agentpack eval` lift.
- LLM concept enrichment; UI rendering; PDF `cites` edges; chunk-level similarity.
