# TODO — Hardening follow-ups (spec 0004 deviation audit)

Companion to [hardening-followup-plan.md](hardening-followup-plan.md). Check off only when the
verification actually ran; record evidence (RED output, GREEN counts, commands) per task — see
[hardening-todo.md](hardening-todo.md) for the expected style.

---

## ⚠️ READ THIS FIRST (handoff header for the implementing agent)

**Required reading, in order, before writing any code:**
1. [hardening-followup-plan.md](hardening-followup-plan.md) — dependency graph, branch strategy,
   risks.
2. The **deviation evidence** sections of [hardening-todo.md](hardening-todo.md) for T0.3, T0.5,
   TA.2, TB.1, TB.5, TB.6, TB.7 — the context these follow-ups come from.
3. Spec 0004 §0 (process rules) still applies: RED first, full suite after every task, stop on
   mismatch between this doc and the code.

**Test invocation (this exact form, always):**
```bash
PYTHONPATH="$PWD/src" ./venv/bin/python -m pytest tests/ -q
```
Bare `python -m pytest` hits the wrong environment (anaconda base) and fails spuriously.

**Baseline:** working tree = `326 passed, 0 failed`, but ONLY because of an uncommitted
`tests/test_cli.py` diff. **A clean checkout of pushed HEAD `37f7155` = `324 passed, 2 failed`**
(verified 2026-08-16 via `git stash push -- tests/test_cli.py`). FU.1 fixes that. After FU.1 the
suite must be fully green **with no uncommitted diffs**, and stays that way.

**Process rules:**
- Work on branch `fix/engineering-hardening` (PR #12's branch, already pushed). One task at a
  time, in order. Conventional commits per task. Push only at the ▣ checkpoint.
- Every piece of "verified" evidence below was gathered live on 2026-08-16 at HEAD `37f7155` —
  re-confirm the RED before fixing (cheap), but do not re-litigate the diagnosis.
- **Stop at the ▣ CHECKPOINT and wait for human review.** FU.4 requires an explicit human go
  even after the checkpoint (it is optional and measure-gated).

---

## FU.1 · Commit the `run_eval` patch-target fix — the pushed branch fails on a clean checkout

**Priority: URGENT — do this first.** PR #12 as pushed fails 2 tests for any reviewer/CI running
a clean checkout.

- **Verified fact:** committed `tests/test_cli.py` (lines ~99/106) has
  `@patch("agentpack.cli.run_eval")`, but `cli.py` imports `run_eval` **function-locally** inside
  the `evaluate` command (`from agentpack.eval.runner import run_eval`, around `cli.py:296`) — a
  function-local import binds a local name, never a module attribute, so `agentpack.cli.run_eval`
  never exists and `unittest.mock.patch` raises at test setup:
  `AttributeError: <module 'agentpack.cli' ...> does not have the attribute 'run_eval'`.
  Confirmed live: `git stash push -- tests/test_cli.py` →
  `tests/test_cli.py::test_cli_eval` and `::test_cli_eval_error` both FAIL with exactly that
  error → `git stash pop` → both pass again.
- **Why it slipped:** the repair (rename both decorators to
  `@patch("agentpack.eval.runner.run_eval")`) has existed all session as a pre-existing
  **uncommitted** working-tree diff (it predates the spec-0004 work; see T0.2's and TB.6's "git
  hygiene" notes in hardening-todo.md). TB.6 folded the companion `search_pack` rename into its
  commit because its own tests required it, but deliberately left the `run_eval` hunk unstaged —
  correct scoping at the time, but it means every full-suite run this session silently depended
  on an uncommitted fix.
- [x] **Fix:** commit the working-tree `tests/test_cli.py` diff as its own commit (it is exactly
  2 decorator lines — verify with `git diff tests/test_cli.py` first; if anything else appears in
  the diff, STOP and report). Suggested message:
  `test(cli): patch run_eval where it resolves — lazy import means agentpack.cli.run_eval never exists`
  (note in the body that this commits a pre-existing repair, same bug class as F22/T0.1 and the
  TA.8/T0.5 patch-target findings).
- **Acceptance:** `git status` shows NO modified tracked files; full suite **326 passed, 0
  failed** with a clean tree.
- **Verify:** `git diff` (empty for tracked files) → full suite → record count.

**Evidence:**
- Re-confirmed RED via `git stash push -- tests/test_cli.py`: `test_cli_eval` and
  `test_cli_eval_error` both failed with `AttributeError: <module 'agentpack.cli' ...> does not
  have the attribute 'run_eval'` → `git stash pop` restored the fix.
- Diff staged and committed was exactly the 2 decorator lines, confirmed via
  `git diff --cached` before committing — nothing else included.
- GREEN (targeted): `test_cli_eval`/`test_cli_eval_error` → 2 passed.
- GREEN (full suite): **326 passed, 0 failed** on a clean tree (commit `4f8f28f`).

## FU.2 · Remove `search_vector`'s TB.1 fast path — it eats legitimate rebuilds

- **Verified fact:** TB.1 added a fast path to `search_vector` (retrieve.py, right after
  `current_hash = _manifest_hash(base_path)`): if `vector_index.npy` is absent AND
  `vector_index.hash` exists AND matches the current manifest, return `[]` without attempting a
  rebuild. Intent: skip pointless re-builds for a confirmed-empty pack. **Hole:** an absent npy +
  surviving matching hash also arises when the npy alone is deleted (manual cleanup, partial
  copy, crash between writes) on a pack that HAS chunks — the hash was written by the last FULL
  build and still matches because the manifest didn't change. Confirmed live: built a real
  1-chunk index (mocked embeddings), deleted only `vector_index.npy` → `search_vector` returned
  `[]` and did **not** rebuild. Pre-TB.1 behavior: the `stale` check (`not vector_path.exists()`)
  → rebuild → results.
- **Why removal (not a smarter marker) is the right fix:** the degenerate-rebuild case the fast
  path was protecting is already handled correctly by the flow beneath it — stale check → 
  `build_vector_index` → `_clear_vector_index` (no-op unlinks + hash write) →
  `if not vector_path.exists(): return []`. The fast path only saved a cheap no-op rebuild per
  query on an empty pack (reads the manifest, loops zero/missing chunks, rewrites the hash — 
  trivial, and empty packs are a dev-only edge). Delete the whole block; do not replace it.
- [x] **Test (RED first):** in `tests/test_retrieve.py`, next to
  `test_search_vector_returns_empty_after_degenerate_rebuild` (reuse its fixture pattern —
  mocked `_get_embedding_model`, real 1-chunk manifest + chunk file): build the index, assert npy
  exists, `vector_path.unlink()` ONLY (leave hash + meta), call `search_vector` → assert results
  are non-empty and cite `c1`, and assert `vector_path.exists()` again (rebuilt). RED today:
  returns `[]`, npy stays absent.
- **Acceptance:** new test green; `test_search_vector_returns_empty_after_degenerate_rebuild`
  still green (the degenerate case must still return `[]`); TB.0 snapshot
  (`test_hybrid_ranking_snapshot_tb0`) byte-identical; full suite green (expect **327**).
- **Verify:** targeted + TB.0 + full suite.

**Evidence:**
- RED: `test_search_vector_rebuilds_after_partial_npy_deletion` →
  `AssertionError: partial npy deletion must trigger a rebuild, not a silent empty result` —
  `assert []`, confirming the fast path swallowed a legitimate rebuild.
- Fix: deleted the whole fast-path block (the `current_hash = _manifest_hash(...)` line stays,
  still used by the `stale` check immediately below).
- GREEN (targeted): `tests/test_retrieve.py -v` → **24 passed**, incl. the new test AND
  `test_search_vector_returns_empty_after_degenerate_rebuild` (TB.1's own test — degenerate-empty
  case still correctly returns `[]` via the flow beneath the removed fast path).
- GREEN + TB.0: `test_hybrid_ranking_snapshot_tb0` → still passing, unchanged.
- GREEN (full suite): **327 passed, 0 failed** (commit `dd97cf1`) — matches the plan's predicted
  count exactly.

## FU.3 · `cache_get`: miss on absent db *file*, not just absent directory

- **Verified fact:** TB.6(c) implemented the no-mkdir-on-read guard at directory level
  (`cache.py::_connect`: `if not create and not cache_dir.exists(): return None`). The spec's
  literal text was "return a miss if the **db file** doesn't exist". Consequence, confirmed live:
  with an **existing** cache dir that has no `cache.db` (e.g. db manually removed, or a dir
  created by other tooling), `cache_get` correctly returns a miss but `sqlite3.connect` +
  `CREATE TABLE` **creates `cache.db` as a side effect of the read**. The F25 typo-path scenario
  is unaffected (the dir doesn't exist there), so this is a fidelity tighten, not a user-facing
  bug — but it is a one-line fix.
- [x] **Fix:** in `_connect`, change the read-path guard to file-level:
  `if not create and not (cache_dir / "cache.db").exists(): return None` — return **before** any
  `sqlite3.connect`. Keep `mkdir` under `create=True` only. Do NOT touch the corruption-heal
  branch: a *present-but-corrupt* db on a read path must still connect, fail, warn once, and
  self-heal (TB.3's guarantee — deleting/recreating a file that exists is not the side effect
  F25 is about; hardening-todo.md TB.6(c) records this rationale).
- [x] **Test (RED first):** in `tests/test_cache.py`: create the cache dir (empty), call
  `cache_get` → assert `None` AND `not (cache_dir / "cache.db").exists()`. RED today: the file
  exists after the read.
- **Acceptance:** new test green; `test_corrupt_cache_db_self_heals` and the round-trip tests
  still green; full suite green (expect **328**).
- **Verify:** targeted + full suite.

**Evidence:**
- RED: `test_cache_get_does_not_create_db_file_for_existing_empty_dir` (uses `tmp_path` directly
  as `cache_dir`, matching existing test conventions — pytest already creates it, with no
  `cache.db` inside) →
  `AssertionError: cache_get must not create cache.db as a side effect of a read` —
  `assert not True`.
- Fix: moved `db_path = cache_dir / "cache.db"` computation (pure, no filesystem I/O) before the
  guard, and checks `db_path.exists()` instead of `cache_dir.exists()`.
- GREEN (targeted): `tests/test_cache.py -v` → **6 passed**, incl. the new test and
  `test_corrupt_cache_db_self_heals` (corruption self-heal on a read path confirmed unaffected —
  a present-but-corrupt file still passes the file-level existence check and proceeds to
  connect/fail/heal).
- Also re-verified `test_cli_retrieve_missing_pack_dir_no_side_effects` (the original F25
  typo-path scenario TB.6 fixed) — still passing, confirming this tighten doesn't regress it.
- GREEN (full suite): **328 passed, 0 failed** (commit `ac849c3`) — matches the plan's predicted
  count exactly.

**▣ CHECKPOINT FU — evidence posted, gate passed, ready to push.**

FU.1–FU.3 complete across 3 commits (`4f8f28f`, `dd97cf1`, `ac849c3`). Final gate verified: `git
status` shows no modified tracked files; full suite **328 passed, 0 failed** on that clean tree —
matches the plan's predicted count exactly at every step (326 → 327 → 328).

---

## FU.4 · (OPTIONAL, measure-first) Chunker flush-check tokenization overhead

**Requires an explicit human go. Post-merge or never — must not delay PR #12.**

- **Context (not yet a verified problem):** TA.2 made chunk sizing exact by re-encoding real
  joined text: (a) `create_chunk` computes `token_count` via `encoder.encode(content_str)` once
  per chunk; (b) the normal-path flush check encodes the joined candidate
  (`current_blocks + [block.text]`) on **every** block append while `current_tokens > 0`. Both
  are bounded (≤ max_tokens per encode) — a constant-factor increase in tokenization work, not
  asymptotic. demo_corpus packs showed no noticeable wall-time change, but chunking is a small
  fraction of pack time there (Docling dominates); a text-heavy corpus might notice.
- [x] **Measure first:** benchmark `chunk_document` alone (not `write_pack`) on the parsed 10-K
  (`PDFParser(fast_pdf=True).parse(demo_corpus/3M_2018_10K.pdf, ...)` → time
  `chunk_document(doc)` over ~10 runs) at HEAD vs. pre-TA.2 chunker
  (`git show 897dc61:src/agentpack/chunker.py` — TA.1 applied, TA.2 not). Record both numbers in
  this file.
- [x] **Gate:** only if chunking wall-time regressed **>20%**, add the cheap skip: when
  `current_tokens + block_tokens + 2 * (len(current_blocks) + 1) <= max_tokens`, skip the flush
  check entirely (the joined text cannot overflow — each `"\n\n"` separator costs ≤2 tokens, so
  the bound is safe). Otherwise record the numbers and close this task as **no-action**.
- **Acceptance (if the fix is applied):** every TA.1/TA.2 chunker test still green, AND the
  absolute property (real tokenized length ≤ max_tokens AND `token_count` == real length for
  EVERY chunk) re-verified on a full-precision demo_corpus re-pack — 0 violations, same
  methodology as TA.2's evidence.
- **Verify:** benchmark numbers recorded either way; if changed: targeted chunker tests + full
  suite + re-pack check.

**Evidence:**
- **Measured (before any fix):** `chunk_document(doc)` on the parsed 10-K (160 blocks → 254
  chunks), 10 runs each: HEAD (TA.1+TA.2) mean=**197.36ms** median=182.24ms stdev=32.96ms;
  pre-TA.2 (TA.1 only) mean=**59.21ms** median=58.82ms stdev=1.28ms. **+233.3% mean / +209.8%
  median** — far past the 20% gate. Much larger than the plan's "constant-factor" expectation
  written when scoping this task.
- **Gate triggered** → profiled with `cProfile` (5 runs): 3195 `encoder.encode()` calls total
  (639/run), 0.785s of the 1.006s total (78%) — confirmed tokenization, not something else, is
  the cost.
- **Fix, part 1 (the plan's specified skip):** added the cheap `safe_bound` check before the
  per-block flush-check's real encode — empirically verified the safety margin first (20,000
  random boundary-text samples: max observed extra cost from one `"\n\n"` join was **1 token**,
  comfortably under the plan's 2-token margin). Re-measured: mean=174.18ms (+194.0%),
  median=165.31ms (+180.1%) — a real but partial improvement.
- **Fix, part 2 (found via re-profiling, not in the plan's original text):** re-profiled after
  part 1 — encode calls dropped to 1950/5runs (390/run) but `create_chunk`'s own
  `token_count=len(encoder.encode(content_str))` (line ~46, only 5 calls after part 1 since most
  chunks are single-block) wasn't the issue; the real remainder was 198/390 calls (~51%) in the
  oversized-split shrink-loop and 160/390 in the unavoidable per-source-block encode. Applied the
  same "no join, no extra cost" principle the plan's own fix relies on, one level up: for
  `create_chunk`, when `len(current_blocks) <= 1` there is no `"\n\n"` join at all, so
  `current_tokens` (sum of real per-block `encoder.encode()` results) already IS the exact real
  length — skip the re-encode entirely rather than approximate it. Verified this is exact (not
  approximate) for oversized-split sub-blocks too, whose `tokens` value comes from a
  `decode()`-then-implicit-re-encode round trip: checked 173 varied slice boundaries across
  ~24k tokens of realistic mixed text, **0 mismatches**.
- **Final measured:** mean=124.23ms (**+113.5%**), median=115.77ms (**+99.3%**). Re-profiled:
  encode calls down to 1950/5runs → wait, re-checked directly: 390/run at this point, remaining
  concentration is the oversized-split shrink-loop (`while end > start + 1` re-check,
  ~198 calls/run) — a third, more specialized optimization not attempted here. **Stopped at this
  point deliberately**: the plan's specified fix (part 1) plus one directly-analogous companion
  (part 2) closed most of the gap using the exact reasoning the plan itself established; going
  further into the oversized-split path trades more code complexity for a benefit that's already
  in the "imperceptible in absolute terms" range (~115ms total for a 254-chunk document, against
  a `pack` pipeline that takes single-digit seconds dominated by parsing). Flagging the remaining
  ~99-114% relative regression for a human call rather than continuing to optimize unprompted.
- GREEN (targeted, both fixes applied): `tests/test_chunker.py -v` → **9 passed**, unchanged.
- GREEN (full suite): **328 passed, 0 failed**.
- Real-corpus absolute-property re-verification (full-precision, not `--fast`, re-pack of all of
  `demo_corpus` incl. the real 10-K): **245 chunks, 0 violations** of "real tokenized length ≤
  max_tokens AND token_count == real length" — matches TA.2's own original evidence count (245)
  exactly, confirming both optimizations preserve the exact-token guarantee on real content, not
  just the synthetic slice-boundary check above.
- **Not closed as no-action** (the gate fired) but also not fully resolved to <20% — see the "why
  stopped here" note above. Recommend: accept as-is (~115ms is negligible in the real `pack`
  pipeline) unless a genuinely text-heavy, chunk-dense corpus reports a noticeable slowdown, at
  which point the oversized-split shrink-loop is the next, clearly-identified target.

---

## Deviations audited and cleared — NO action needed

Recorded so the audit scope is itself reviewable. Details for each live in
[hardening-todo.md](hardening-todo.md)'s evidence sections.

| Deviation | Why no action |
|---|---|
| T0.3 — try/except boundary moved from `_fts_stored_hash` to `search_fts` | Spec's literal fix text was self-contradictory (DatabaseError is OperationalError's *parent*); acceptance behavior matches every spec criterion; documented for the reviewer |
| T0.5 — patched `agentpack.retrieve.TextEmbedding`, not spec's `fastembed.TextEmbedding` | Spec's suggested target verifiably doesn't intercept (`from x import y` binding); same bug class as F22 |
| T0.7 — `alpha` removal paused at stop condition | Resolved by explicit human decision; landed cleanly |
| TA.2 — fix grew to 3 layers beyond F14's text | The extra bugs are already fixed and covered by tests + a 245/245-chunk real-corpus verification; only the perf question remains → FU.4 |
| TA.5 — RED test's assertion corrected pre-commit (invariance, not naive sort) | The corrected test is strictly more meaningful; OQ1 migration note already in the PR description |
| TB.2 — content-hash change invalidates existing packs once | OQ2, accepted in spec; migration note already in the PR description |
| TB.5 — found `remove_empty_lines` never worked at all (hasattr guard) | Deeper root cause fixed in the same commit, verified live through the real CLI |
| TB.6 — `search_pack` returns `[]` (not an exception) on missing manifest | CLI guards first with red exit-1 exactly as spec asks; library-level `[]` matches spec's own instruction for `search_pack` |
| TB.7 — kept the `pytest.skip` on `test_api_umap_builds_missing_vector_index` | That test monkeypatches the real `umap.umap_` module, so umap must be importable — matches spec's "keep skips only where umap itself must run" |
