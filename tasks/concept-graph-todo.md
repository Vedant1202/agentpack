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

### T1 · Walking skeleton: documents + sections + `contains`, end-to-end ✅ DONE
- [x] New `src/agentpack/grapher.py`: `build_graph(pack_dir, params=None) -> Optional[dict]` reads `map.yml` + `manifest.yml` off disk only (no parser/pipeline imports — verified by inspection of its own import block). Document nodes for **every** manifest source (including failed ones — spec §4 "documents always get a node"; a failed doc naturally ends up isolated with zero edges, which is itself a useful signal for T5's report). Section nodes for top-level entries in each doc's `map.yml` `sections` list only (not descending into nested `nodes`) + one `contains` edge per doc→section. `params:` recorded verbatim (falls back to `config._GRAPH_DEFAULTS` when the caller passes none — real values arrive via `cli.py`/`load_config` in T6, not yet wired). `pack:` block mirrors `CorpusMap`'s shape (`name`/`generated_at`/`manifest`); `graph_version` stays top-level per the model T0.2 already defined (matching `map_version`'s actual placement in `CorpusMap`, not nested under `pack:` — the todo's own parenthetical was shorthand, corrected against the real map.yml shape).
- [x] **`_MIN_SUCCESSFUL_SOURCES = 2` is a separate, non-configurable constant from `params["min_docs"]`** — documented explicitly in the module docstring and inline, since they share a default value (2) but mean different things (pack-level "is there any cross-doc value at all" vs. T2's per-concept promotion gate) and future maintainers must not conflate them.
- [x] `write_graph(pack_dir, params=None) -> bool`: calls `build_graph`, writes `graph.yml` only on a non-`None` result. The **build** (data assembly, the part touching unpredictable pack content) is wrapped in one outer try/except in `build_graph` itself; the **file write** in `write_graph` is deliberately left unwrapped, matching the existing precedent that `map.yml`'s own write in `pack.py` isn't defensively wrapped either — by the time this hook runs, `manifest.yml`/`map.yml` were just written successfully to the same directory, so a disk failure would already have surfaced there first.
- [x] `pack.py`: `no_graph: bool = False` + `graph_params: Optional[Dict] = None` added to `write_pack`'s signature; hook added immediately after the existing `if not no_map:` block, same shape, calling `write_graph(str(out_path), graph_params)`.
- [x] Serialization: `yaml.dump(..., default_flow_style=False, sort_keys=False)`; nodes sorted `(kind, id)`, edges sorted `(source, target, relation)` — plain lexical tuple sort on the pydantic model instances directly, no dict conversion needed first.
- [x] Tests (`tests/test_grapher.py`, 8 total, fixtures built in-test): skeleton shape + contains-edge reachability; sort-order determinism; single-doc auto-skip; `no_graph=True` suppression; corrupt-`map.yml` graceful degradation (asserts `write_graph` returns `False`, no file written, exactly one stderr warning); never-raises on missing manifest; manifest/map.yml byte-identical (modulo `generated_at`) whether or not the graph is built — the purely-additive guarantee; build-twice determinism.
- [x] **Real-corpus smoke test beyond the in-test fixtures**: packed `demo_corpus/` (4 real sources — markdown, a real SEC-filing PDF, CSV, another markdown) and read the actual `graph.yml` output by eye, not just narrow assertions. Found one section title that's a wall of markdown badge/shield-link syntax (`src_000_s00`, React's README) — traced it back to confirm this is `map.yml`'s own pre-existing content (React's actual README H1, verbatim) via `grep` on `map.yml` and the raw source file, **not** something T1 introduced. Correctly out of scope to fix (mapper.py/parser territory, on the do-not-touch list) — noted here rather than silently ignored.

**Acceptance:** ✅ all 8 tests pass; full suite = baseline + 8; `manifest.yml`/`map.yml` provably byte-identical (modulo `generated_at`) with vs. without the graph, via a dedicated test — graph confirmed purely additive, not just assumed.
**Verify:** ✅ RED confirmed first (7 of 8 new tests failed on `ModuleNotFoundError`/`TypeError` against the pre-implementation tree; the 8th passed vacuously for the wrong reason and was re-checked post-implementation). `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_grapher.py -v` → **8 passed**. Full suite: `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/ -q` → **221 passed, 1 pre-existing failure** (`test_run_eval`) — exactly 213 (T0.2 baseline) + 8 new, zero regressions.
**Commit:** `4df7d94`.

### T2 · Concept promotion + `mentions` edges ✅ DONE
- [x] `_slug()` (spec §4 recipe, verbatim): `re.sub(r"_+", "_", re.sub(r"[^\w]+", "_", phrase.casefold())).strip("_")`; concept id `c_<slug>`. The only place a slug is minted. Verified live: `"Balance Sheet"` and `"balance-sheet"` both slug to `"balance_sheet"`.
- [x] Three promotion gates, ALL required: slug present in sections from ≥ `params["min_docs"]` distinct documents; ≤ `params["df_cap"]` fraction of **all** sections in the pack (walked recursively — see next bullet, not just top-level, since a boilerplate phrase can just as easily recur in nested subsections); slug ≥4 chars and not purely numeric/underscore (`stripped.isdigit()` after removing underscores).
- [x] **Walks the full section tree, not just top-level** — a real design point beyond T1's scope, since a concept can be mentioned by a deeply nested section that T1 never gave a node to (nested sections get no `contains` edge, top-level-only per T1). `_promote_concepts` mutates the T1 loop's `existing_section_ids` set in place: a top-level section with a promoted concept just gains a `mentions` edge (node already exists); a nested section with one gains **both** a new node and the edge. A section mentioning multiple promoted concepts is only added once.
- [x] Concept label = most frequent surface-form keyphrase text among contributors, ties broken lexically ascending (`sorted(items, key=lambda kv: (-count, text))[0]`) — deterministic regardless of collection order.

**Acceptance:** ✅ every gate has a test proving both sides of its boundary — not just the rejection side. Notably the df_cap test proves rejection AND, on the *same* synthetic corpus with a looser cap, promotion — confirming the rejection was really the gate and not some other silent failure.
**Verify:** ✅ RED confirmed first (8 of 10 new tests failed — `ImportError` for `_slug`, empty concept lists elsewhere; the other 2 passed vacuously on empty-list equality and were re-checked post-implementation). `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_grapher.py -v -k "concept or slug"` → **10 passed**; full file → **18 passed** (8 T1 + 10 T2). Full suite: **231 passed, 1 pre-existing failure** (`test_run_eval`) — exactly 221 (T1 baseline) + 10 new, zero regressions.
- **Testing approach, worth recording:** gate-boundary tests write a synthetic `manifest.yml`+`map.yml` directly to `tmp_path` (mirroring `test_audit.py`'s `_write_manifest` pattern) and call `build_graph()` — the real public entry point — rather than reaching into private helpers or depending on real YAKE output, which can't reliably guarantee an exact section/document count for boundary testing. One dedicated end-to-end test still uses real `write_pack()` + real YAKE, on "accounts receivable" — verified live beforehand (`enrich.keyphrases()`) to survive extraction unchanged in both source texts, so the assertion isn't a guess about model behavior.
- **Real-corpus sanity check, and a real finding worth recording:** `demo_corpus` (4 topically-unrelated documents: React README, SEC filing, CSV, benchmark doc — deliberately format-diverse, not topic-related) promotes **zero** concepts at default params. Did not take that at face value — re-ran with `df_cap` fully loosened to `1.0` and confirmed still zero, proving the result is a correct "no real cross-document overlap exists" outcome, not a silently-misfiring gate. A meaningful multi-document check (42 real, genuinely related SEC filings in `benchmarks/financebench_sample/corpus`, 86MB) was attempted but exceeds reasonable time for a mid-task check even in `--fast` mode — correctly deferred to the dedicated **▣ CHECKPOINT** after T8, which is what that step exists for.
**Commit:** `edd2ed6`.

### T3 · `references` edges from markdown links ✅ DONE
- [x] Extracts from the doc's **chunk text on disk** (spec §2: raw markdown survives unchanged into `chunks/*.md` — confirmed by this task's own tests, which go through the real `write_pack()` pipeline, not synthetic fixtures). Three regexes, each **verified live** before implementation, including the trickier edge cases: inline `\[[^\]]*\]\(([^)#?\s]+)[^)]*\)` (capture group already excludes trailing anchors/titles/queries by construction); reference-style `^\s*\[[^\]]+\]:\s*(\S+)` (multiline); wikilink `\[\[([^\]|]+)(?:\|[^\]]*)?\]\]` (excludes `|display text`). External-link detection via `urllib.parse.urlparse(target).scheme` (truthy) rather than a hand-rolled scheme list — verified live that relative paths/bare filenames give `scheme=''` while real URLs and `mailto:` give a real scheme.
- [x] Resolution: target basename matched against manifest source `path` values (already bare filenames, confirmed from T1). Anchor/query stripped **defensively for all three forms** in `_resolve_target`, not just relied on the inline regex's own exclusion — the reference-style and wikilink capture groups don't have that exclusion built in. External and unresolved targets dropped silently (both are the expected common case, not an error). No self-loops (`target_source_id == source_id` check). Deduped per **ordered** `(source_doc, target_doc)` pair via a `seen_targets` set scoped per source — so A→B and B→A (mutual references) are two edges, not deduped against each other, matching the spec's directional edge model.
- [x] Tests: all 5 todo-required cases, plus 2 direct unit tests for the pure extraction/resolution helpers (mirroring T2's `test_slug_normalization` pattern) and a reference-style+wikilink-specific test the todo didn't explicitly enumerate but the spec's edge table required supporting.

**Acceptance:** ✅ all 5 required cases pass (inline link → edge; external → nothing; unresolved → nothing; 3 links same target → 1 edge; self-link → nothing), plus reference-style/wikilink resolution and determinism, each with its own test.
**Verify:** ✅ RED confirmed first (5 of 9 new tests failed — `ImportError` for the two new helpers, `assert 0 == 1` for the dedup case; the other 4 passed vacuously since "zero references edges" was trivially true before any references logic existed, and were re-checked post-implementation). `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_grapher.py -v -k "reference or extract_link or is_external"` → **9 passed**; full file → **27 passed** (18 T1+T2 + 9 T3). Full suite: **240 passed, 1 pre-existing failure** (`test_run_eval`) — exactly 231 (T2 baseline) + 9 new, zero regressions.
- **Real-corpus check, verified not assumed:** `demo_corpus` produces zero `references` edges. Didn't take that at face value — grepped the raw markdown source directly and confirmed all 33 markdown links across both `.md` files in that corpus are external `http(s)://` URLs (React's real README links to react.dev/npm/GitHub/badges; none of them point at another file in the corpus). Zero is the correct, verified result, not a silent extraction failure.
**Commit:** `d1eed5c`.

### T4 · Communities (seeded Louvain + determinism hardening) ✅ DONE
- [x] Hardening recipe implemented exactly as specced: a **fresh** `nx.Graph` per call (`add_nodes_from(sorted(...))`, then edges inserted in sorted `(source, target, relation)` order — never reuses graph state from a prior computation); `nx.community.louvain_communities(G, seed=42)`; re-indexed by size desc with `tuple(sorted(members))` tiebreak so ids can't churn between otherwise-identical runs. Verified live (again, on the installed networkx 3.6.1, not assumed) that an isolated (zero-edge) node lands in its own singleton community automatically — no special-casing needed on this side for that case.
- [x] `_community_label`: highest-degree **concept** member's label (a section/document node can easily outrank a concept in raw degree, so this is a real, deliberate filter, not equivalent to "just take the highest-degree member"); ties broken by node id ascending; falls back to the highest-degree member of *any* kind when a community has no concept nodes at all — tested as three separate, direct unit tests against the pure function (mirroring T2's `_slug`/T3's `_extract_link_targets` pattern), not only indirectly through a full graph build.
- [x] `import networkx` kept **lazy**, inside the function — matches `enrich.py`'s existing, explicit "heavy-import-free" precedent for this exact pair of libraries (yake/networkx) in this codebase; not a new convention invented for this task.
- [x] Every node gets `community: <int>` by mutating the already-constructed `GraphNode` objects in place before they're passed into `CorpusGraph(...)` — verified live first that pydantic models here are plain mutable objects (not assumed), and separately verified that the mutation survives being passed through `CorpusGraph`'s own construction and `.model_dump()` (i.e. pydantic doesn't silently revalidate/reconstruct a fresh, unmutated copy from a passed-in instance).

**Acceptance:** ✅ communities stable across repeated builds (dedicated build-twice test comparing both the per-node `community` values and the `communities:` summary block); full suite = baseline + 6.
**Verify:** ✅ RED confirmed first (5 of 6 new tests failed outright; the determinism test passed vacuously since two all-`None` community assignments are trivially equal, and was re-checked post-implementation). `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_grapher.py -v -k "communit or isolated"` → **6 passed**; full file → **33 passed** (27 T1–T3 + 6 T4). Full suite: **246 passed, 1 pre-existing failure** (`test_run_eval`) — exactly 240 (T3 baseline) + 6 new, zero regressions.
- **Test fixture note:** used a *structurally disconnected* 2+2-document fixture for the cross-community test (two pairs sharing no concepts/edges between the pairs) rather than trying to coax a specific split out of modularity optimization on a connected graph — a disconnected component can never share a community with another regardless of how Louvain's objective function scores it, so this is an unambiguous, safe test, not a probabilistic one. Similarly the isolated-node test uses a document with **zero sections** (genuinely zero edges) rather than a small 2-node component, to precisely match what "isolated node" means in the spec rather than a nearby-but-different case.
- **Real-corpus check:** `demo_corpus` produces 4 communities, one per document, each labeled by fallback (its own document name — no concept members exist anywhere in this corpus, consistent with T2/T3's already-established findings that this corpus has zero shared concepts and zero cross-document references). Correct and expected given the underlying graph structure, not a new finding requiring investigation — a direct, verified consequence of the T2/T3 results.
**Commit:** `16c7bdb`.

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
