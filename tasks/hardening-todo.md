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

### T0.5 · Pin embedding model name (spec §4 T0.5, F12) — ✅ DONE
- [x] RED: assert `TextEmbedding` called with `model_name="BAAI/bge-small-en-v1.5"` (reset the singleton first). Fix: pass it.
**Acceptance:** construction pinned; mocked-embedding tests unaffected.
**Verify:** targeted + full suite.

**Evidence:**
- Confirmed location: `retrieve.py:59`, `_embedding_model = TextEmbedding()` (spec cited `:58`; 1-line
  drift from T0.3's `import sys` addition, trivial).
- **Patch-target deviation (verified before writing the test):** spec suggests patching
  `fastembed.TextEmbedding`; live-verified in `./venv/bin/python` that this does NOT intercept the
  call — `retrieve.py` does `from fastembed import TextEmbedding` (a direct name binding at import
  time), so patching the origin module `fastembed.TextEmbedding` afterward leaves
  `agentpack.retrieve.TextEmbedding` (the name actually called) untouched. `mock_te.called` was
  `False` under `patch("fastembed.TextEmbedding")` vs. `True` under
  `patch("agentpack.retrieve.TextEmbedding")` — same class of footgun as F22/T0.1. Used the
  verified-working target.
- RED: `test_embedding_model_pinned_by_name` (resets the `_embedding_model` singleton, calls
  `_get_embedding_model()`) → `TextEmbedding()` called with `{}`, expected
  `{'model_name': 'BAAI/bge-small-en-v1.5'}`.
- Fix: `TextEmbedding(model_name=_EMBED_MODEL_ID)` at the singleton construction site.
- GREEN (targeted): `tests/test_retrieve.py -v` → **19 passed**, incl. the new test; the three
  existing `@patch("agentpack.retrieve._get_embedding_model")` tests (which bypass this code path
  entirely) unaffected.
- GREEN (full suite): **301 passed, 0 failed** in 23.73s (300 + this 1 new test).

### T0.6 · Warn on descriptor-less map in `agentpack graph` (spec §4 T0.6, F28) — ✅ DONE
- [x] RED: graph on an `agentpack map`-rebuilt (keyphrase-less) map prints no warning today. Fix: recursive keyphrase check in `graph_cmd`, yellow warning, behavior otherwise unchanged. Second test: normal map → no warning.
**Acceptance:** warning text on descriptor-less maps only; exit 0 both ways.
**Verify:** targeted (`tests/test_graph_cli.py`) + full suite.

**Evidence:**
- Confirmed F28 location: `mapper.py:261` (the `agentpack map` rebuild's hardcoded `enrich=False`)
  and `cli.py::graph_cmd`, which had no map.yml/keyphrase awareness at all.
- RED: `test_graph_warns_on_descriptor_less_map` (pack a real corpus, strip all `keyphrases`
  recursively from `map.yml` to simulate an `agentpack map` rebuild's shape, run `graph`) →
  warning text absent from output. `test_graph_no_warning_on_full_fidelity_map` (normal pack-time
  map) passed trivially pre-fix since nothing warns yet — expected for a stay-green guard test,
  not itself a RED case.
- Fix: added `_map_has_any_keyphrases` (recursive walk over nested `nodes`, mirrors the
  `map.yml` section-tree shape) and wired it into `graph_cmd` right after the `manifest.yml`
  existence check — reads `map.yml` (if present), warns in yellow (unconditional, not gated by
  `--quiet`, matching this function's existing warning/error conventions) when no section in any
  document carries a non-empty `keyphrases` list. A missing or unparseable `map.yml` is swallowed
  silently here — `write_graph` immediately below already owns reporting that case (existing
  "graph.yml skipped … missing map.yml" message), so no duplicate/conflicting output.
- GREEN (targeted): `tests/test_graph_cli.py -v` → **13 passed**, incl.
  `test_graph_rebuild_parity_with_pack_time` (byte-identical `graph.yml` output — confirms the new
  check is warn-only, no behavior change) and both new tests.
- GREEN (full suite): **303 passed, 0 failed** in 23.74s (301 + these 2 new tests).

### T0.7 · Remove dead `alpha` param (spec §4 T0.7, F30) — ✅ DONE
- [x] Grep first for any caller passing `alpha` (STOP if found). Fix: delete from `search_hybrid` signature.
**Acceptance/Verify:** full suite green.

**Human decision:** given the choice between (a) drop `alpha=0.5` from the one test call and
delete the parameter, or (b) skip T0.7 for now — chose (a), matching F30's original intent.

**Findings (per spec's own instruction: STOP and report instead of proceeding):**
- Confirmed independently that `alpha` is dead in the implementation: `search_hybrid`
  (`retrieve.py:379-405`) does pure RRF fusion (`_rrf_score`); the parameter is never read anywhere
  in the function body. F30's core claim holds.
- `grep -rn "search_hybrid(" src/ tests/` found **4** call sites, not 0:
  - `retrieve.py:462` (internal, from `search_pack`'s hybrid mode) — no `alpha`.
  - `ui/server.py:261` — no `alpha`.
  - `tests/test_retrieve.py:215` (`test_retrieve_error_handling`) — no `alpha`.
  - `tests/test_retrieve.py:201` (`test_search_hybrid`) — **`alpha=0.5`**. This is the one the
    spec's stop condition is for.
- Per spec §4 T0.7 verbatim: "if ANY call site passes alpha, STOP and report instead." This is a
  test-only call (production code never passes it), and since `alpha` is confirmed unread, the
  value `0.5` is a no-op today either way — but deleting the parameter as written would break this
  one test with `TypeError: unexpected keyword argument 'alpha'`.
- **Not proceeding without a decision.** The obvious fix (drop `alpha=0.5` from the
  `tests/test_retrieve.py:201` call alongside the signature change) is low-risk, but the spec
  explicitly carved this exact scenario out for human review rather than pre-authorizing it, so
  T0.7 is paused here rather than improvised past.

**Resolution:**
- Dropped `alpha=0.5` from `tests/test_retrieve.py:201`'s `search_hybrid(...)` call (now
  `search_hybrid(str(pack_dir), "query", top_k=2)`).
- Deleted `alpha: float = 0.5` from `search_hybrid`'s signature (`retrieve.py`).
- GREEN (targeted): `tests/test_retrieve.py -v` → **19 passed**.
- GREEN (full suite): **303 passed, 0 failed** in 24.09s — unchanged count from T0.6 (pure
  deletion + one call-site edit, no new tests).

**▣ CHECKPOINT 0 — ✅ reviewed and approved 2026-08-16.** Evidence posted (per-task RED/GREEN,
303 passed/0 failed final). T0.7's alpha-param stop condition resolved per human decision (drop
the test's `alpha=0.5`, delete the parameter). Proceeding to Phase A.

---

## Phase A — Pack correctness

### TA.1 · Chunk-boundary citation bug (spec §4 TA.1, F1) — ✅ DONE
- [x] RED: two-block page-1/page-2 fixture → first chunk cites page 2 today. Fix: flush with the OLD metadata before adopting the incoming block's. Section-path variant test too.
**Acceptance:** boundary chunks cite the content actually inside them.
**Verify:** targeted + full suite + demo_corpus re-pack spot-check (record a citation before/after).

**Evidence:**
- Read the whole `chunk_document` loop (95 lines) before editing, per spec instruction. Confirmed
  F1 exactly: `current_metadata` was updated from the incoming block unconditionally at the top of
  the loop, BEFORE the flush-decision that uses it — so a chunk flushed because the NEXT block
  overflowed capacity got stamped with the NEXT block's page/section, not its own content's.
- RED: `test_chunker_boundary_chunk_cites_its_own_content_not_next_block` (block1=700tok/page1,
  block2=700tok/page2, max_tokens=800 — block1 alone fits, block1+block2 overflows, forcing a
  flush exactly at the boundary) → first chunk's content was pure block1 text but stamped
  `page=2`. `test_chunker_boundary_chunk_cites_its_own_section_not_next_block` (same shape, section
  axis) → `AssertionError: first chunk is pure Introduction content but was stamped
  section='Usage'`. Both match F1 exactly.
- Fix: reordered the loop so the flush-if-needed check runs BEFORE the metadata update (using
  `fits = block_tokens <= max_tokens` once instead of duplicating the comparison), then the
  metadata update runs once, then the append/oversized-split logic — preserving the original
  "sub-blocks carry correct page/section" behavior for the oversized-split path (verified
  `test_chunker_oversize_block` still passes) while fixing the flush-of-prior-content case.
- Verified the overlap-retention path (`:44-51`, unchanged) doesn't need a separate fix: it only
  *reads* `current_metadata` (via `.copy()` inside `create_chunk`) and never mutates it, so
  retained-overlap content flushed on a later call now correctly inherits whatever metadata was
  current AT THAT FLUSH — the same fix covers both paths through one shared mechanism. Traced a
  small-block scenario by hand (page-1 A+B retained as overlap, then flushed alongside page-2 C) —
  the dominant/newest content's page wins for a mixed chunk, matching the spec's "acceptable" case.
- GREEN (targeted): `tests/test_chunker.py -v` → **6 passed**, incl. the 2 new tests and all 4
  pre-existing ones (`test_chunker_oversize_block`, `test_chunker_metadata` unaffected).
- GREEN (full suite): **305 passed, 0 failed** in 24.82s (303 + these 2 new tests).
- **demo_corpus before/after (real 10-K PDF, `--fast`):** stashed just `chunker.py`'s uncommitted
  fix to get a true A/B, packed twice (identical 260 chunks both times — chunk boundaries
  unchanged, confirming the fix is metadata-only). **55 of 260 chunks** had their page citation
  corrected, every single one shifted down by exactly 1 (e.g. `page: 3 -> 2`, `9 -> 8`, `23 -> 22`)
  — the exact F1 signature. Spot-checked `src_001_chunk_002`: its content starts "Table of
  Contents / 3M COMPANY / FORM 10-K…", unambiguously page-2 content (right after `chunk_001`'s
  page-1 cover-page boilerplate) — cited `page: 3` before the fix, `page: 2` after. Temp dirs
  removed after inspection.

### TA.2 · Oversize-split token accounting (spec §4 TA.2, F14) — ✅ DONE
- [x] RED: normal block + oversized block → one chunk is 901 real tokens recorded as 800. Fix per spec; acceptance property is absolute: EVERY emitted chunk has real tokenized length ≤ max_tokens AND `token_count` == that length.
**Verify:** targeted + full suite.

**Evidence:**
- RED: `test_chunker_oversized_split_accounts_for_retained_overlap` (100-tok block — under the
  ~120-tok overlap target for max_tokens=800/0.15, so it's retained WHOLE — followed by a
  2000-tok oversized block) → `src_oversize2_chunk_001: real length 901 exceeds max_tokens=800`.
  Matches the spec's own predicted number (901 recorded as 800) exactly. Note: the spec's
  suggested test used a "~200 tok" normal block, but 200 > the 120-tok overlap target, so nothing
  would actually be retained with that number (retention is whole-block, all-or-nothing) — used
  100 tokens instead to genuinely trigger the retained-overlap-into-oversized-split path; the
  reproduced number confirms this was the right scenario.
- Fix, part 1 (spec's suggested `+=` option): `current_tokens = len(sub_tokens)` →
  `current_tokens += len(sub_tokens)`, and each slice's size is now
  `max_tokens - current_tokens` (leaving room for already-retained content) instead of a flat
  `max_tokens`. This alone reduced the failure from 901/800 to **801/800** — closer, not exact.
- **Extra finding beyond the spec's two suggested options:** the residual 1-token gap is a real
  BPE effect, not a logic bug — `create_chunk` joins multiple blocks' pre-decoded text with
  `"\n\n"`, and that separator (plus rare merge effects at the join boundary) costs a token or two
  that a sum-of-per-block-token-counts can't predict in advance. Since the spec's acceptance
  property is stated unconditionally ("EVERY emitted chunk... ≤ max_tokens AND token_count ==
  actual tokenized length of the chunk's TEXT" — the real, joined text), fixed this exactly rather
  than papering over it with a margin: (a) `create_chunk` now computes `token_count` from
  `len(encoder.encode(content_str))` directly (the real joined text) instead of the incrementally
  summed `current_tokens` — makes property 2 exact everywhere, unconditionally; (b) the oversized-
  split loop now measures the real candidate joined length and shrinks the slice by 1 token at a
  time until it actually fits — bounded, converges in 1-2 steps since the overage is always tiny.
- GREEN (targeted, first pass): `tests/test_chunker.py -v` → **7 passed**.
- Bonus real-corpus check (not required by this task's Verify line, ran anyway given the "absolute
  property" framing): full-precision (non-`--fast`) re-pack of all of `demo_corpus` (incl. the
  real 10-K PDF), validating both properties across every emitted chunk → **7 of 242 real chunks
  violated the size property** (`token_count` matched `real_len` exactly every time — property 2
  held — but 7 chunks' real length exceeded 800, e.g. `('src_001_chunk_000', 826, 826)`,
  `('src_001_chunk_028', 857, 857)`). All from the SAME join-separator mechanism, but via the
  **normal** (non-oversized) multi-block accumulation path, which TA.2/F14 didn't originally
  describe — the flush decision there summed per-block token counts too, with the identical blind
  spot.
- Fix, part 2: normal-path flush decision now also measures the real joined length (existing
  `current_blocks` + the incoming block, joined with `"\n\n"`) before deciding whether to flush,
  instead of comparing summed integers. Re-ran the real-corpus check: **1 of 244 chunks** still
  violated (`('src_001_chunk_124', 855, 855)`) — down from 7, not yet 0.
- Investigated the remaining case directly (kept the pack output, inspected the offending chunk):
  a 3-block chunk ending in a table. Root cause: after a flush-and-retain, the *new* block is
  appended to `current_blocks` unconditionally, with no re-check that the (small) retained
  remainder plus the new block still fits — e.g. a 60-token retained tail immediately followed by
  a 780-token block that fits alone (≤800) but not combined with the tail (840+ real tokens).
  Reproduced deterministically: `test_chunker_drops_retention_when_it_still_wont_fit_next_block`
  (700-tok block1 flushes on block2's arrival, too big to retain itself; 60-tok block2 accumulates
  with block1 first, then gets retained whole; 780-tok block3 then doesn't fit with the retained
  60) — confirmed RED against the pre-this-fix code via `git stash` (same discipline as prior
  tasks): failed on the FIRST chunk's `token_count` mismatch, confirming the old code path.
- Fix, part 3: `create_chunk` gained an `allow_retention` parameter; the normal-path flush now
  double-checks after the first flush+retain — if the retained remainder still doesn't fit the
  incoming block, flushes again with `allow_retention=False` (forces `current_blocks`/
  `current_tokens` to empty) rather than silently accumulate an oversized chunk. Bounded (at most
  one extra flush), no infinite loop, no duplicate chunk beyond the one legitimate small
  transitional chunk this produces (consistent with how overlap already duplicates content by
  design elsewhere in this chunker).
- GREEN (targeted, final): `tests/test_chunker.py -v` → **9 passed** — all 3 new TA.2 tests plus
  all 6 pre-existing ones (`test_chunker_oversize_block` unaffected: no join occurs for a
  standalone oversized block, so its behavior is unchanged; TA.1 boundary tests unaffected).
- GREEN (full suite): **308 passed, 0 failed** in 23.21s (306 + these 2 additional new tests).
- Real-corpus check, final: full-precision re-pack of `demo_corpus` → **245 chunks, 0 violations**
  of the absolute property. Temp dirs removed after each inspection.

### TA.3 · Per-file error boundary (spec §4 TA.3, F2) — ✅ DONE
- [x] RED: dangling-symlink corpus aborts the whole pack today. Fix: catch-all inside the submitted per-file callable → failed source + `parse_error` warning, pack continues. PermissionError variant (monkeypatched for determinism).
**Acceptance:** one bad file can no longer lose the run; good files' output intact; audit shows the warning.
**Verify:** targeted + full suite.

**Evidence:**
- Read the whole per-file path before editing: `_parse_one` (submitted directly to
  `pool.submit(...)`) does two `open()` calls outside any try block (zip-safety checksum, main
  checksum) plus `parser.parse(...)`; `future.result()` at the gather point had no guard at all.
  Confirmed the note about `SourceDocument.type` being a restricted `Literal` — a naive
  `suffix.lstrip(".").lower()` (the pattern the existing zip-safety branch already uses, safe only
  because it's scoped to docx/pptx/xlsx) would produce `"md"` for a markdown file, which isn't a
  valid Literal value (`"markdown"` is) — added `_doc_type_for_suffix` to map correctly for a
  catch-all covering ANY of the 5 parser types, not just zip-based ones.
- RED: `test_dangling_symlink_does_not_abort_the_pack` (symlink to a never-created target) →
  `FileNotFoundError` propagated out of `write_pack` entirely, matching F2 exactly.
  `test_unreadable_file_does_not_abort_the_pack` (monkeypatched `builtins.open` to raise
  `PermissionError` for one specific path — chosen over real `chmod 0` per the spec's own
  determinism note, since root/CI environments often ignore permission bits) → same crash.
- Fix: wrapped `_parse_one`'s body (everything after the parser-resolution early-return) in
  `try/except Exception`, returning `_failed_doc(file_path, source_id, str(e))` — a
  `SourceDocument` with `blocks=[]` and one `ExtractionWarning(type="parse_error", message=str(e))`
  — mirroring the EXISTING zip-safety failure branch's shape (kept that branch's own construction
  untouched, just now inside the try so IT also degrades gracefully if `check_zip_safety`/its
  `open()` raises). No changes needed to `future.result()` itself or to `write_pack`'s downstream
  status/warning logic — both already handle a `parse_error`-flagged doc correctly (verified via
  the pre-existing `test_failed_parse_marked_in_manifest`), confirming the spec's framing that this
  is a submission-level fix, self-contained to `_parse_one`.
- GREEN (targeted): `tests/test_pack.py -v` → **9 passed**, incl. both new tests and all 7
  pre-existing ones (`test_failed_parse_not_cached`, `test_trust_warnings_correct_source_id_on_cache_hit`
  unaffected).
- GREEN (full suite): **310 passed, 0 failed** in 21.91s (308 + these 2 new tests).
- Real `agentpack audit` check (spec-required): packed a 2-file corpus (one good `.md`, one
  dangling symlink) → pack exit 0, `manifest.yml` lists both sources. `agentpack audit` output:
  `### parse_error (1)` / `- Source src_001: [Errno 2] No such file or directory:
  '.../ghost.md'` — warning surfaces exactly as expected; good file's chunk present and correct
  (1 chunk, 11 tokens). Temp dir removed after inspection.

### TA.4 · L1 cache-hit remap of `doc.path` + block ids (spec §4 TA.4, F3) — ✅ DONE
- [x] RED: rename-same-content re-pack cites the OLD filename today. Fix: remap path + regenerate block ids under current source_id (find the parser's id-formatting logic first). Must still be a cache HIT (assert via hit-count pattern).
**Acceptance:** citations name the current file; table ids in the current namespace; cache still hit.
**Verify:** targeted + full suite.

**Evidence:**
- Confirmed the id-formatting logic first (`grep -rn "block_id\|_table_" src/agentpack/parsers/`):
  every parser formats `block_id=f"{source_id}_<type-suffix>"` — the source_id is ALWAYS a plain
  prefix, so remapping is a generic prefix-swap (strip the old source_id, prepend the new one),
  not something that needs per-parser-type reimplementation.
- RED: `test_cache_hit_remaps_path_and_block_ids` (mirrors the existing
  `test_trust_warnings_correct_source_id_on_cache_hit` precedent exactly: calls `_parse_one`
  directly with two different `source_id`s on the same `cache_dir` and same-content-different-name
  files, sidestepping scan-order concerns entirely) → cache-hit doc's `path` stayed
  `'report_a.csv'` instead of updating to `'report_b.csv'`. Matches F3 exactly (only
  `doc.source_id` was remapped).
- Fix: on cache HIT, also set `doc.path = file_path.name` and rewrite every block's `block_id`
  (prefix-swap from the old to the new source_id) + `block.source_id`.
- GREEN (targeted): `tests/test_pack.py -v` → **10 passed**, incl. `test_incremental_pack_skips_unchanged`
  (confirms the fix remaps, not bypasses, the cache — `parser.parse` still called exactly once
  across two packs) and the pre-existing trust-warning precedent test, both unaffected.
- GREEN (full suite): **311 passed, 0 failed** in 21.52s (310 + this 1 new test).
- Real end-to-end check (write_pack/CLI level, not just the `_parse_one` unit): packed
  `report_a.csv`, then packed a renamed `report_b.csv` (same bytes, plus a filler file to shift
  scan order) into the SAME output dir (shared `.cache/`) → second manifest:
  `source: src_000 report_b.csv` (current filename, not stale) and
  `table: src_000_table_0 src_000` (table block_id/source_id self-consistent with the source's own
  id). Temp dir removed after inspection.

### TA.5 · Deterministic scan order (spec §4 TA.5, F13) — ✅ DONE
- [x] Fix: `dirs.sort()` + `sorted(files)` in `scanner.py`. Test via monkeypatched reversed `os.walk` + straight determinism test. OQ1 accepted: note the one-time id-shift in the PR description.
**Verify:** targeted + full suite.

**Evidence:**
- Confirmed F13's location matches spec exactly: `scanner.py:64`, `for root, dirs, files in
  os.walk(dir_path):`, with no sorting anywhere in the loop.
- RED (test 1, meaningful on any filesystem): `test_scanner_sorts_despite_reversed_os_walk_order`
  monkeypatches `os.walk` to yield `dirs`/`files` in reverse order at every level, then compares
  against the SAME scan without the monkeypatch. Note: `os.walk` yields a directory's own files
  before recursing into subdirectories, so the canonical order is NOT a naive lexicographic sort
  of full relative paths (e.g. `'adir/y.md'` sorts before `'zdir/z.md'`, but both come after
  top-level `.md` files) — the meaningful assertion is invariance: reversing the input order must
  not change the output. First version of this test asserted a naive `names == sorted(names)`,
  which is wrong for multi-level trees; corrected before committing.
- RED (test 2, "RED-ish" per spec's own framing): `test_scanner_output_is_deterministic` — two
  scans of the same tree, assert identical lists. This one actually PASSED even pre-fix on this
  filesystem (macOS APFS returns a stable order across repeated `os.walk` calls in the same
  process) — expected and consistent with the spec calling it "RED-ish," not guaranteed red;
  test 1 is the one that's reliably meaningful.
- Confirmed test 1 IS genuinely RED pre-fix via `git stash` (same discipline as prior tasks):
  `['c.md', 'b.md', 'a.md', ...] != ['b.md', 'c.md', 'a.md', ...]` — output changed when the
  underlying os.walk order was reversed, confirming the bug is real, not just theoretical.
- Fix: `valid_dirs.sort()` before `dirs[:] = valid_dirs` (equivalent to spec's suggested in-place
  `dirs.sort()`, applied to the already-filtered list), and iterate `sorted(files)` instead of
  `files`.
- GREEN (targeted): `tests/test_scanner.py -v` → **5 passed**, incl. both new tests and all 3
  pre-existing ones.
- GREEN (full suite): **313 passed, 0 failed** in 23.02s (311 + these 2 new tests).
- **OQ1 / migration note for the PR description:** re-packing an existing corpus after this change
  may assign different `src_NNN` ids ONE TIME (if the filesystem's natural `os.walk` order
  happened to differ from sorted order for that corpus) — a one-time id shift, accepted per OQ1.

### TA.6 · Stop output-dir self-ingestion (spec §4 TA.6, F15) — ✅ DONE
- [x] RED: `write_pack(corpus, corpus/pack)` twice ingests its own output today. Fix: resolved-path exclusion of out_path from the scan.
**Verify:** targeted + full suite.

**Evidence:**
- Confirmed F15's location: `pack.py` — `out_path.mkdir(...)` creates the (nested) output dir
  before `scan_directory(input_dir, ...)` scans it; on a second run the first run's own chunks/
  manifest/report are indistinguishable from real input.
- RED: `test_output_dir_nested_in_input_is_not_self_ingested` (`write_pack(corpus, corpus/pack)`
  twice) → second manifest's sources included stray entries beyond `{"doc.md"}`. Confirmed
  genuinely RED pre-fix via `git stash` (same discipline as prior tasks).
- Fix: filtered the scanner's result in `write_pack` (not a new `scan_directory` parameter — this
  exclusion is specific to "don't ingest my own output," a concept `write_pack` owns, not a
  general scanning concern) using `Path.resolve()` + `is_relative_to`, per spec's explicit "real
  path, not string prefix" instruction — catches a symlinked or relative `out_path` too.
- GREEN (targeted): `tests/test_pack.py -v` → **11 passed**, incl. the new test and all 10
  pre-existing ones.
- GREEN (full suite): **314 passed, 0 failed** in 21.53s (313 + this 1 new test).

### TA.7 · Encoding: BOM + decode warnings (spec §4 TA.7, F16) — ✅ DONE
- [x] RED pair: BOM markdown loses its heading; UTF-16 txt packs with zero warnings. Fix: `utf-8-sig` + `decode_error` ExtractionWarning when replacement chars present (status stays success).
**Verify:** targeted + full suite.

**Evidence:**
- Confirmed F16's two locations: `text_parser.py` and `markdown_parser.py::parse` both opened
  with `encoding="utf-8"` (not `utf-8-sig`) + `errors="replace"`, with no post-decode check at all.
- RED (a): `test_markdown_parser_strips_utf8_bom_and_recognizes_heading` (real UTF-8-BOM-encoded
  file, `"# Title\n\nbody text here".encode("utf-8-sig")`) → `doc.blocks[0].type` was `'paragraph'`
  not `'heading'` — the BOM glued onto `# Title`, so `line.startswith("#")` never matched.
- RED (b): `test_text_parser_flags_wrong_encoding_with_decode_error_warning` (real UTF-16-encoded
  `.txt` file) → zero warnings; content silently decoded to replacement-character mojibake.
- Fix (both parsers): `encoding="utf-8"` → `encoding="utf-8-sig"` (strips a BOM when present,
  behaves identically to plain `utf-8` when absent — strictly additive, no regression for
  BOM-less files, verified by the pre-existing `test_markdown_parser`/`test_text_parser` still
  passing unchanged). After decode, `if "�" in content:` appends
  `ExtractionWarning(type="decode_error", ...)`, mirroring each parser's existing
  `empty_file`-warning pattern; `status` stays `"success"` (unchanged — nothing else sets it to
  `"failed"` here) per spec.
- GREEN (targeted): `tests/test_parsers.py -v` → **9 passed**, incl. both new tests and all 7
  pre-existing ones (`test_markdown_parser`, `test_text_parser`, etc. unaffected).
- GREEN (full suite): **316 passed, 0 failed** in 21.47s (314 + these 2 new tests).

### TA.8 · Close the fitz document (spec §4 TA.8, F29) — ✅ DONE
- [x] Live-verify fitz context-manager support, then `with fitz.open(...)`.
**Verify:** full suite (e2e PDF test green).

**Evidence:**
- Live-verified in `./venv/bin/python` (fitz/pymupdf 1.27.2.3): `fitz.Document` has both
  `__enter__`/`__exit__`, and exiting a `with fitz.open(...)` block genuinely closes the document
  (`doc.is_closed == True` after exit) — unlike sqlite3's context manager (T0.3), which only
  manages the transaction, not the connection. No gotcha here.
- Fix: `doc = fitz.open(file_path)` → `with fitz.open(file_path) as doc:`, keeping the whole body
  (page-count check + per-page loop) inside the `with`, still nested in the existing `try/except`
  so a failure to even open the file still degrades to a `parse_error` warning as before.
- Found and fixed a REQUIRED test update while running the suite (not a new test — spec says "no
  direct test" for this task): `test_pdf_parser_fast`'s `MagicMock` didn't configure `__enter__`,
  so `with fitz.open(...) as doc:` bound `doc` to an unconfigured auto-generated MagicMock instead
  of the test's carefully-set-up `mock_doc` — `doc.page_count` resolved to a fresh MagicMock,
  `range(MagicMock())` raised, caught by the existing broad `except Exception`, and the test
  silently got 0 blocks instead of 2. Added `mock_doc.__enter__.return_value = mock_doc` and
  `mock_doc.__exit__.return_value = False` to match real `fitz.Document`'s behavior.
- GREEN (targeted): `tests/test_parsers.py -v` → **9 passed**, incl. the corrected
  `test_pdf_parser_fast` and the real-Docling `test_pdf_parser_semantic` (no mocks, unaffected).
- GREEN (full suite): **316 passed, 0 failed** in 21.68s (unchanged count — no new test, per spec).
- Live end-to-end sanity check (unmocked): real fast-mode parse of `demo_corpus`'s 160-page 10-K
  PDF → 160 blocks (one per page with text), 0 warnings, matching the live page-count check above.

**▣ CHECKPOINT A — ✅ reviewed and approved 2026-08-16.** Evidence posted (per-task RED/GREEN,
TA.1 before/after citation, TA.2's beyond-scope discovery, TA.5's OQ1 note). Final Phase A suite:
316 passed, 0 failed. Proceeding to Phase B.

---

## Phase B — Invalidation & retrieval robustness

### TB.0 · Ranking snapshot guard — FIRST, before any B change (spec §4 TB.0) — ✅ DONE
- [x] Snapshot ordered chunk-id results for 2 fixed hybrid queries on a small real pack (mocked embeddings). This test must pass unchanged through every remaining task.
**Verify:** test green pre-change; referenced in every B/C task's evidence.

**Evidence:**
- `test_hybrid_ranking_snapshot_tb0`: real 3-doc markdown corpus (ML ops / Kubernetes / DB
  migrations — chosen so FTS keyword overlap differs meaningfully per query), packed via a real
  `write_pack` (`no_map=True, no_graph=True` to keep the test focused/fast), with a deterministic
  md5-hash-derived mock embedding (purely a function of chunk text, no real ML model — stable
  across runs and machines). `search_pack(..., mode="hybrid")` for 2 fixed queries
  ("rollback strategies", "container orchestration") produces meaningfully DIFFERENT orderings
  per query (confirmed both queries don't just return docs in the same order), snapshotted as
  literal chunk-id lists.
- Verified determinism directly (not just trusting the mock): ran the discovery script twice in
  one process and the full test 3 additional times → identical ordered results every time.
- GREEN: `tests/test_retrieve.py::test_hybrid_ranking_snapshot_tb0` → **1 passed** (~1-1.5s).
- GREEN (full suite): **317 passed, 0 failed** in 24.84s (316 + this 1 new test).
- This test's snapshot values must stay byte-identical through TB.1–TB.7; will be re-run and
  cited in every subsequent B/C task's evidence per the spec's instruction.

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
