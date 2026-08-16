# Plan — Engineering Hardening (spec 0004): implementation plan + Sonnet handoff

Implements [docs/specs/0004-engineering-hardening.md](../docs/specs/0004-engineering-hardening.md)
(**APPROVED**, all open questions resolved 2026-08-12). Companion checklist:
[hardening-todo.md](hardening-todo.md). Named `hardening-*` because `tasks/plan.md`/`todo.md`
belong to the completed Knowledge Map feature — do not overwrite them.

## What this is

26 bug fixes from the 2026-08 engineering audit, organized into four gated phases. **No features,
no schema changes, no retrieval-ranking changes.** The spec is unusually detailed on purpose —
every task carries the exact bug (pre-verified, §2 facts table F1–F30), the exact fix, and the
exact RED test — so the implementer's job is execution and verification, not diagnosis. When the
spec and the code disagree, STOP and report; do not improvise.

## Dependency graph & slicing rationale

```
T0.1 test_run_eval fix  ──► suite fully green (new baseline for everything after)
T0.2–T0.7 quick wins    ──► independent of each other and of all later phases
        │
Phase A (pack correctness)
  TA.1 chunk-boundary citations ─┐  independent fixes, but TA.5 (sorted scan)
  TA.2 oversize token accounting ─┤  changes source_id assignment → land it
  TA.3 per-file error boundary  ─┤  INSIDE this phase so its one-time id shift
  TA.4 L1 cache path/block remap ┤  is covered by the same checkpoint review
  TA.5 sorted scanner            ┤
  TA.6 output-dir self-ingestion ┤
  TA.7 encoding (BOM + warnings) ┤
  TA.8 fitz close               ─┘
        │
Phase B (invalidation) — TB.0 ranking-snapshot guard MUST land first;
  every other B task (TB.1–TB.7) is then independent, verified against TB.0
        │
▣ Checkpoint B → PR 1 (phases 0+A+B) into dev
        │
Phase C (eval integrity) — SEPARATE branch + PR after PR 1 merges (OQ4)
  TC.1 exclude-and-report ──► TC.2 isolation/persistence (same files, do in order)
  TC.3 baseline cache fingerprint, TC.4 loud LLM degradation,
  TC.5 naive-conn cache, TC.6 CLI hygiene — independent
```

Slicing is per-bug (each task = one failing test + one fix + full suite), which is already
vertical: every task leaves the tree shippable. Ordering within phases is risk-first — the two
chunker fixes (TA.1/TA.2) lead Phase A because they change pack *output* and the checkpoint
reviewer should see their effect on a real corpus early.

## Branch / PR strategy (per OQ4)

- **PR 1:** branch `fix/engineering-hardening` off `dev` (already created, spec+plan+todo are its
  first commit). Phases 0, A, B land here, one commit per task (or coherent pair). Open PR into
  `dev` after ▣ Checkpoint B review.
- **PR 2:** only after PR 1 merges — branch `fix/eval-integrity` off the updated `dev`. Phase C
  lands there. This keeps the eval-behavior changes (which alter reported numbers) reviewable in
  isolation.
- `main` is release-only; never target it.

## Test-count bookkeeping (update the todo after every task)

Start: **296 passed, 1 failed** (`test_run_eval`). After T0.1: **297 passed, 0 failed** — and the
"1 pre-existing failure is normal" allowance is permanently retired; any red after T0.1 means the
current task broke something. Each task's evidence entry records the new total.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Fix silently changes retrieval ranking | TB.0 snapshot test written BEFORE any Phase B change; re-run at every B/C task |
| Spec line numbers drift from `489dbe4` | Grep-first rule (spec §0.4): find the quoted code, STOP on mismatch |
| Chunker edits break overlap arithmetic (verified correct today) | TA.1/TA.2 tests assert token-count == real tokenized length for EVERY emitted chunk, not just the changed path |
| TA.4 remap accidentally bypasses the cache instead of fixing it | Its test asserts a cache HIT still occurs (existing hit-count pattern in test_pack.py) |
| TB.1 must rewrite an entrenched test (`test_search_hybrid` passes BECAUSE of the bug) | Spec pre-flags it: the rewrite's initial failure against the fix is expected and is the proof |
| Eval changes corrupt the published-numbers pipeline | Phase C isolated in PR 2; exclude-and-report policy keeps failed counts visible |
| Sonnet touches out-of-scope files "while in there" | Spec §6 whitelist + §0 do-not-touch; anything else = stop and report |

## Verification strategy

Per task: RED test first (failure output recorded in the todo) → fix → targeted test → full suite.
Per phase: ▣ checkpoint with evidence pasted into the todo; human go required.
End of PR 1: `demo_corpus` end-to-end smoke (`pack` → `retrieve` → `audit` → `validate`) recorded.
End of PR 2: same smoke + one real `eval` run on a small benchmark to see the new `failures`
column render.
