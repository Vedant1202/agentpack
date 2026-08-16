# TODO — Engineering Hardening (spec 0004)

Companion to [hardening-plan.md](hardening-plan.md). Implements
[docs/specs/0004-engineering-hardening.md](../docs/specs/0004-engineering-hardening.md).
Check off only when the verification actually ran; update each task with evidence (RED failure
line, GREEN test counts, commands) as you complete it — see `tasks/concept-graph-todo.md` for the
expected style.

---

## ⚠️ READ THIS FIRST (handoff header for the implementing agent)

**Required reading, in order, before writing any code:**
1. [docs/specs/0004-engineering-hardening.md](../docs/specs/0004-engineering-hardening.md) — the
   source of truth. §0 has the hard process rules. §2 (facts F1–F30) is **pre-verified against
   this repo — do not re-derive, do not re-litigate**. §4 has the exact fix + RED test per task.
   If code at a cited location doesn't match the spec's description, **STOP and report**.
2. [tasks/concept-graph-todo.md](concept-graph-todo.md) — the previous feature's todo, as the
   working-style exemplar: verify live before implementing, RED before GREEN, full suite after
   every task, evidence with real numbers, findings recorded honestly.

**Test invocation (this exact form, always):**
```bash
PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/ -q
```
Bare `python -m pytest` hits the wrong environment and fails spuriously.

**Baseline:** ~~`296 passed, 1 failed` (`tests/test_eval.py::test_run_eval`)~~ → **`297 passed, 0
failed`** as of T0.1 (below). From here the suite is FULLY green and must stay fully green — there
is no "pre-existing failure" allowance anymore. Record the new count after every task.

**Process rules (non-negotiable):**
- Work on branch `fix/engineering-hardening` (already exists, off `dev`; this file is on it).
  Phases 0/A/B → PR into `dev` after ▣ Checkpoint B. Phase C waits for that PR to MERGE, then
  branch `fix/eval-integrity` off updated `dev` → its own PR. Never target `main`.
- One task at a time, in order. TDD: RED first (confirm it fails for the right reason — read the
  output), then fix, then targeted test, then full suite.
- **Stop at every ▣ CHECKPOINT and wait for human review.**
- Conventional commits per task: `fix(chunker): …`, `test(eval): …`, `docs: check off TX.Y`.
- Do-not-touch list and file whitelist: spec §0 + §6. A fix that seems to need any other file =
  stop and report.

---

## Phase 0 — Independent quick wins

### T0.1 · Fix `test_run_eval` (spec §4 T0.1, fact F22) — ✅ DONE
- [x] Verify the import shape first (`grep -n "get_baselines" src/agentpack/eval/runner.py`), then add the third `@patch` so the runner loop is unit-tested with zero real baselines.
**Acceptance:** test passes in ~2s; full suite **297 passed, 0 failed** — new permanent baseline.
**Verify:** `…pytest tests/test_eval.py -v`; full suite; update the baseline note above.

**Evidence:**
- Import shape verified: `grep -n "import baselines\|_baselines\|get_baselines" src/agentpack/eval/runner.py`
  → `from agentpack.eval import baselines as _baselines` (line 7) and
  `_baselines.get_baselines(...)` (line 50). Confirms spec's claimed patch target
  `agentpack.eval.runner._baselines.get_baselines` exactly.
- RED (before fix): `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/test_eval.py::test_run_eval -v`
  → `FAILED tests/test_eval.py::test_run_eval - FileNotFoundError: Manifest not fo...`, dying
  during the "Cross-Encoder Rerank" baseline step — matches F22 exactly (function-local
  `search_pack` import in the reranker baseline bypasses the mock on
  `agentpack.eval.runner.search_pack`).
- Fix applied: added `@patch("agentpack.eval.runner._baselines.get_baselines", return_value=[])`
  as the outermost decorator + `mock_baselines` param, per spec §4 T0.1.
- GREEN (targeted): `tests/test_eval.py -v` → `6 passed` in 1.82s (was building 6 real baseline
  indexes before; now unit-tests only the runner loop + AgentPack's own 3 modes via the existing
  `search_pack`/`write_pack` mocks).
- GREEN (full suite): `PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/ -q` →
  **297 passed, 0 failed** in 77.37s. New permanent baseline — no failures allowed from here on.

### T0.2 · `gen-eval` exit code (spec §4 T0.2, F6) — ✅ DONE
- [x] RED: CliRunner test asserting exit 1 on an `"Error…"` report (copy `test_cli_eval_error`). Fix: `raise typer.Exit(code=1)` in the error branch.
**Acceptance:** exit code 1 on failure; success path unchanged.
**Verify:** targeted + full suite.

**Evidence:**
- Confirmed F6 location matches spec exactly: `cli.py:342-344`, `gen_eval`'s error branch had
  `typer.secho(report, fg=typer.colors.RED)` with no `Exit`, unlike `eval`'s branch at `:304-306`.
- RED: added `test_cli_gen_eval_error` (mirrors `test_cli_eval_error`, patches
  `agentpack.eval.generation.run_generation_eval`) → `assert 0 == 1`, confirming the missing exit.
- Fix: added `raise typer.Exit(code=1)` after the `typer.secho` in `gen_eval`'s error branch.
- GREEN (targeted): `tests/test_cli.py -v` → **13 passed** (includes pre-existing tests using
  patch targets `agentpack.retrieve.search_pack` / `agentpack.eval.runner.run_eval`, which were
  already corrected on disk from a prior in-flight edit unrelated to T0.2 — left untouched and
  unstaged; only the T0.2 hunks (`cli.py` Exit + new `test_cli_gen_eval_error`) were committed).
- GREEN (full suite): **298 passed, 0 failed** in 68.19s (297 + this 1 new test).

### T0.3 · Corrupt `lexical_index.db` self-heal (spec §4 T0.3, F4) — ✅ DONE
- [x] Live-verify `DatabaseError` vs `OperationalError` on a garbage file first. RED: truncate a real index → search crashes. Fix: widen catch, unlink, warn once, rebuild; close the probe conn on error paths.
**Acceptance:** corrupt db → transparent rebuild + stderr warning, results returned.
**Verify:** targeted (capsys asserts warning) + full suite.

**Evidence:**
- Live-verified in `./venv/bin/python`: `sqlite3.connect()` on a garbage file succeeds (lazy open);
  the first real query raises `sqlite3.DatabaseError: file is not a database` — an instance of
  `DatabaseError` itself, NOT `OperationalError` (which is `DatabaseError`'s child), so
  `except sqlite3.OperationalError` cannot catch it. Matches F4 exactly.
- RED: added `test_search_fts_corrupt_db_self_heals` (builds a real tiny FTS index via
  `test_build_fts_index_and_search`'s fixture pattern, then `db_path.write_bytes(b"garbage...")`)
  → `sqlite3.DatabaseError: file is not a database` raised from `_fts_stored_hash` at
  `retrieve.py:78`, propagating out of `search_fts` uncaught. Matches spec's predicted RED exactly.
- **Design note (deviation from the most literal reading of the fix text):** the spec's fix
  paragraph reads as "catch `DatabaseError` inside `_fts_stored_hash`" AND "caller prints a
  warning distinct from ordinary hash-mismatch rebuilds." Implementing both literally is
  self-contradictory: `DatabaseError` is `OperationalError`'s *parent*, so an `except
  sqlite3.DatabaseError` inside `_fts_stored_hash` swallows the corruption there — nothing
  propagates for `search_fts` to catch, making a *distinct* corruption warning structurally
  impossible from the caller side (verified: `_fts_stored_hash` has exactly one call site, in
  `search_fts`; grepped to confirm). Tried a cheap pre-probe (`SELECT 1`) to detect corruption
  before calling `_fts_stored_hash` — live-verified it does NOT reproduce the fault (`SELECT 1` is
  a constant expression that never touches the file's real btree pages, so it succeeds even on
  total garbage). The only reliable signal is the real query itself. Resolution: `_fts_stored_hash`
  no longer catches anything (docstring notes why) and lets `DatabaseError` propagate; `search_fts`
  wraps its sole call in `try/except sqlite3.DatabaseError`, closing `conn`, printing the warning,
  `unlink(missing_ok=True)`, and rebuilding — while the *unchanged* hash-mismatch `else` branch
  (valid file, differing content) still silently rebuilds with no warning, exactly as before. Net
  behavior matches every line of the spec's Bug/Test/Acceptance sections; only the internal
  try/except boundary moved from the helper to its sole caller. Flagging for reviewer visibility
  rather than stopping, since this is a fix-text ambiguity, not a code/spec factual mismatch (spec
  §0's stop condition).
- GREEN (targeted): `tests/test_retrieve.py -v` → **18 passed**, incl. the new test (capsys
  confirms `"corrupt"` in stderr) and the two pre-existing invalidation tests
  (`test_fts_unchanged_pack_reuses_index`, `test_fts_invalidated_on_repack`) unaffected.
- GREEN (full suite): **299 passed, 0 failed** in 72.37s (298 + this 1 new test).

### T0.4 · Cap section-level enrichment — the OOM (spec §4 T0.4, F5) — ✅ DONE
- [x] RED: monkeypatched `_gist` captures >8000-char input today. Fix: `node_text[:_ENRICH_TEXT_CAP]` at the section call site (+ optional 400-sentence guard inside `gist`).
**Acceptance:** enrichment input capped; demo_corpus map still has keyphrases/gists.
**Verify:** targeted + full suite + `--fast` demo_corpus smoke.

**Evidence:**
- Confirmed line numbers match spec exactly: `mapper.py:22` (`_ENRICH_TEXT_CAP = 8000`), `:116`
  (`node_text = " ".join(tnode.own_text).strip()`), `:122-123` (uncapped `_keyphrases`/`_gist`
  calls), `:176` (existing doc-level cap pattern to mirror); `enrich.py:84-90` (the O(N²)
  sentence-pair graph).
- RED: added `test_section_enrichment_text_is_capped` (single section, one 11,207-char paragraph
  block, no nested subsections — mirrors a `--fast` PDF's one-root-section-is-the-whole-document
  shape) → monkeypatched `_gist` spy captured **11207 chars**, `assert 11207 <= 8000` failed.
- Fix: added `node_text = node_text[:_ENRICH_TEXT_CAP]` right after the existing `node_text = ...`
  line in `_to_section_node` (mirrors the doc-level `[:_ENRICH_TEXT_CAP]` slice at `:176`).
  Defense-in-depth: `enrich.py::gist` now also caps `sentences = sentences[:400]` after
  `_sentences()`, guarding any future uncapped caller of `gist()` directly.
- GREEN (targeted): `tests/test_mapper.py tests/test_enrich.py -v` → **28 passed**, incl.
  `test_golden_map_snapshot` (structural regression guard — cap didn't change normal-size output)
  and `test_map_nodes_carry_descriptors_by_default`.
- GREEN (full suite): **300 passed, 0 failed** in 23.76s (299 + this 1 new test).
- Real-world smoke (spec-required): `PYTHONPATH="$PWD/src" ./venv/bin/python -m agentpack.cli pack
  demo_corpus --out /tmp/hardening_t04 --fast --quiet` → exit 0. Inspected `map.yml`: all 4
  documents (incl. `3M_2018_10K.pdf`) still carry a doc-level summary; section nodes still carry
  keyphrases/gists (9 and 17 descriptor-bearing nodes on the two largest docs) — the cap does not
  blank enrichment on normal-sized docs. Temp output removed after inspection.

### T0.5 · Pin embedding model name (spec §4 T0.5, F12)
- [ ] RED: assert `TextEmbedding` called with `model_name="BAAI/bge-small-en-v1.5"` (reset the singleton first). Fix: pass it.
**Acceptance:** construction pinned; mocked-embedding tests unaffected.
**Verify:** targeted + full suite.

### T0.6 · Warn on descriptor-less map in `agentpack graph` (spec §4 T0.6, F28)
- [ ] RED: graph on an `agentpack map`-rebuilt (keyphrase-less) map prints no warning today. Fix: recursive keyphrase check in `graph_cmd`, yellow warning, behavior otherwise unchanged. Second test: normal map → no warning.
**Acceptance:** warning text on descriptor-less maps only; exit 0 both ways.
**Verify:** targeted (`tests/test_graph_cli.py`) + full suite.

### T0.7 · Remove dead `alpha` param (spec §4 T0.7, F30)
- [ ] Grep first for any caller passing `alpha` (STOP if found). Fix: delete from `search_hybrid` signature.
**Acceptance/Verify:** full suite green.

**▣ CHECKPOINT 0 — stop; post evidence; wait for human go.**

---

## Phase A — Pack correctness

### TA.1 · Chunk-boundary citation bug (spec §4 TA.1, F1)
- [ ] RED: two-block page-1/page-2 fixture → first chunk cites page 2 today. Fix: flush with the OLD metadata before adopting the incoming block's. Section-path variant test too.
**Acceptance:** boundary chunks cite the content actually inside them.
**Verify:** targeted + full suite + demo_corpus re-pack spot-check (record a citation before/after).

### TA.2 · Oversize-split token accounting (spec §4 TA.2, F14)
- [ ] RED: normal block + oversized block → one chunk is 901 real tokens recorded as 800. Fix per spec; acceptance property is absolute: EVERY emitted chunk has real tokenized length ≤ max_tokens AND `token_count` == that length.
**Verify:** targeted + full suite.

### TA.3 · Per-file error boundary (spec §4 TA.3, F2)
- [ ] RED: dangling-symlink corpus aborts the whole pack today. Fix: catch-all inside the submitted per-file callable → failed source + `parse_error` warning, pack continues. PermissionError variant (monkeypatched for determinism).
**Acceptance:** one bad file can no longer lose the run; good files' output intact; audit shows the warning.
**Verify:** targeted + full suite.

### TA.4 · L1 cache-hit remap of `doc.path` + block ids (spec §4 TA.4, F3)
- [ ] RED: rename-same-content re-pack cites the OLD filename today. Fix: remap path + regenerate block ids under current source_id (find the parser's id-formatting logic first). Must still be a cache HIT (assert via hit-count pattern).
**Acceptance:** citations name the current file; table ids in the current namespace; cache still hit.
**Verify:** targeted + full suite.

### TA.5 · Deterministic scan order (spec §4 TA.5, F13)
- [ ] Fix: `dirs.sort()` + `sorted(files)` in `scanner.py`. Test via monkeypatched reversed `os.walk` + straight determinism test. OQ1 accepted: note the one-time id-shift in the PR description.
**Verify:** targeted + full suite.

### TA.6 · Stop output-dir self-ingestion (spec §4 TA.6, F15)
- [ ] RED: `write_pack(corpus, corpus/pack)` twice ingests its own output today. Fix: resolved-path exclusion of out_path from the scan.
**Verify:** targeted + full suite.

### TA.7 · Encoding: BOM + decode warnings (spec §4 TA.7, F16)
- [ ] RED pair: BOM markdown loses its heading; UTF-16 txt packs with zero warnings. Fix: `utf-8-sig` + `decode_error` ExtractionWarning when replacement chars present (status stays success).
**Verify:** targeted + full suite.

### TA.8 · Close the fitz document (spec §4 TA.8, F29)
- [ ] Live-verify fitz context-manager support, then `with fitz.open(...)`.
**Verify:** full suite (e2e PDF test green).

**▣ CHECKPOINT A — stop; post evidence incl. the TA.1 before/after citation; wait for human go.**

---

## Phase B — Invalidation & retrieval robustness

### TB.0 · Ranking snapshot guard — FIRST, before any B change (spec §4 TB.0)
- [ ] Snapshot ordered chunk-id results for 2 fixed hybrid queries on a small real pack (mocked embeddings). This test must pass unchanged through every remaining task.
**Verify:** test green pre-change; referenced in every B/C task's evidence.

### TB.1 · Ghost results after degenerate rebuild (spec §4 TB.1, F7)
- [ ] RED: zero-chunk manifest still serves old vectors. Fix: delete npy/meta/hnsw + write new hash on early-return; `search_vector` returns `[]` cleanly. **Expected casualty:** `test_search_hybrid` (tests/test_retrieve.py:125-159) fails against the fix because it depends on the bug — rewrite its fixture to a consistent manifest+index pair and say so in the evidence.
**Verify:** targeted + TB.0 + full suite.

### TB.2 · Content-aware manifest hash (spec §4 TB.2, F8)
- [ ] RED: same ids, different token_counts → equal hashes today. Fix: fold `id:token_count` lines into the fingerprint. OQ2 accepted: note one-time rebuild/L5 invalidation in PR description.
**Verify:** targeted + TB.0 + full suite.

### TB.3 · Corrupt `cache.db` self-heal + conn hygiene (spec §4 TB.3, F9)
- [ ] RED: garbage cache.db → silent dead cache forever. Fix: try/finally everywhere in cache.py; on DatabaseError delete + warn once (module flag) + recreate.
**Verify:** targeted (capsys, round-trip after heal) + full suite.

### TB.4 · HNSW staleness (spec §4 TB.4, F10)
- [ ] RED: stale bin + fewer rows in meta → wrong/erroring results. Fix: delete bin when hnswlib unavailable at build; guard load/query with count-check (live-verify `get_current_count`) + fallback to brute force, warn, delete bin.
**Verify:** targeted + TB.0 + full suite.

### TB.5 · `remove_empty_lines` in the L1 key (spec §4 TB.5, F11)
- [ ] RED: flag toggle no-ops on cached corpus. Fix: add flag to key.
**Verify:** targeted + full suite.

### TB.6 · Conn hygiene + no mkdir-on-read + clean retrieve errors (spec §4 TB.6, F25/F27)
- [ ] RED: `retrieve <typo-dir>` tracebacks AND creates `.cache/` at the typo path. Fix: try/finally in `search_fts`/`search_pack`; close `build_fts_index`'s returned conn in `ensure_lexical_index`; `cache_get` never mkdirs; manifest pre-check + red exit-1 in retrieve.
**Acceptance:** typo path → exit 1, clean message, NO directories created.
**Verify:** targeted + full suite.

### TB.7 · UI: feedback atomicity, umap import order, chunks staleness (spec §4 TB.7, F23/F24)
- [ ] RED trio per spec. Fix: preserve-corrupt-then-fresh + tmp/os.replace + lock for feedback; umap import after manifest/artifact check (then DELETE the now-unneeded pytest.skips in tests/test_ui.py so the 404 path is really tested); hash-validate in `ensure_lexical_index`.
**Verify:** targeted + full suite.

**▣ CHECKPOINT B — stop; post evidence; open PR 1 (`fix/engineering-hardening` → `dev`); wait for merge before Phase C.**

---

## Phase C — Eval integrity (SEPARATE branch `fix/eval-integrity` off updated `dev`, own PR)

### TC.1 · Exclude-and-report failure policy (spec §4 TC.1, F17; OQ3 confirmed)
- [ ] RED: failure at query 2/3 averages a zero today. Fix: failed queries excluded from averages, never judged, `failures: N` per mode in the report, `n/a` when nothing scored.
**Verify:** targeted + full suite.

### TC.2 · Per-query isolation + incremental persistence (spec §4 TC.2, F20)
- [ ] RED pair: one raising query aborts the run; crash at q3/5 loses all results. Fix: try/except per query; atomic incremental writes of results JSON.
**Verify:** targeted + full suite.

### TC.3 · Baseline cache corpus fingerprint (spec §4 TC.3, F18)
- [ ] RED: corpus edit reuses stale baseline cache. Fix: (relpath,size,mtime_ns) fingerprint in the key; bump `_CACHE_VERSION`.
**Verify:** targeted + full suite.

### TC.4 · Loud LLM-baseline degradation (spec §4 TC.4, F19)
- [ ] RED: `""`-returning `_llm_generate` leaves a clean "HyDE" row. Fix: count failures, mark the row `[LLM UNAVAILABLE for N/M queries]`, warn once. Fallback behavior itself unchanged.
**Verify:** targeted + full suite.

### TC.5 · `_get_naive_conn` cache correctness (spec §4 TC.5, F21)
- [ ] RED pair: rebuilds every query with `--skip-raw-file`; can serve corpus A for corpus B. Fix: set `_last_corpus_dir` + include `chunk_size`, mirroring `_get_raw_conn`.
**Verify:** targeted + full suite.

### TC.6 · CLI/edge hygiene sweep (spec §4 TC.6, F26)
- [ ] RED tests per branch: `top_k < 1`, invalid `--mode`, `index <missing-dir>`, `audit` on empty manifest, None-guards in runner/generation, tatqa/qasper stubs → red exit 1 instead of fake success.
**Verify:** targeted + full suite.

**▣ CHECKPOINT C (final) — full-suite evidence; demo_corpus end-to-end smoke (`pack` → `retrieve` → `audit` → `validate`); one small real `eval` run showing the `failures` column; open PR 2; wait for human review.**
