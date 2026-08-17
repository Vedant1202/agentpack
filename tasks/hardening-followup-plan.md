# Plan — Hardening follow-ups (spec 0004 deviation audit): implementation plan + Sonnet handoff

Companion checklist: [hardening-followup-todo.md](hardening-followup-todo.md). Named
`hardening-followup-*` per repo convention (`tasks/plan.md`/`todo.md` belong to the Knowledge Map
feature; `hardening-*` belongs to the original spec-0004 pass — do not overwrite either).

## What this is

The spec-0004 implementation (Phases 0/A/B, [PR #12](https://github.com/Vedant1202/agentpack/pull/12))
deliberately documented every place it deviated from the spec's literal text in
[hardening-todo.md](hardening-todo.md). A post-checkpoint audit of those deviations (2026-08-16,
each suspect **verified live**, not just reasoned about) found:

- **3 issues that need code fixes** (FU.1–FU.3) — one urgent (the pushed PR branch fails 2 tests
  on a clean checkout), one real correctness regression introduced by TB.1's fix, one
  spec-fidelity tighten.
- **1 optional, measure-gated item** (FU.4) — potential chunking-perf overhead from TA.2.
- **9 deviations that need no action** — listed with rationale in the todo so the audit scope is
  itself reviewable.

Every task carries the exact verified failure evidence, the exact fix, and the exact RED test —
same handoff discipline as spec 0004 §4. When the code doesn't match a task's description, STOP
and report; do not improvise.

## Dependency graph & slicing

```
FU.1 commit the run_eval patch-target fix ──► pushed branch green on a clean checkout
        │                                     (unblocks everything: all later evidence
        │                                      must be collected on a clean tree)
        ├── FU.2 remove search_vector's TB.1 fast path   (independent)
        └── FU.3 cache_get file-level miss guard          (independent)
        │
▣ Checkpoint FU → push to PR #12, full suite on a CLEAN checkout
        │
FU.4 (OPTIONAL, measure-first) chunker tokenization overhead — only if measurement
     shows a material regression; otherwise record numbers and close as no-action
```

Each task is one failing test + one fix + full suite — vertical, tree stays shippable after every
commit.

## Branch / PR strategy

- **FU.1–FU.3 land on `fix/engineering-hardening`** (PR #12's branch, already pushed). FU.1
  repairs that branch's own committed test state; FU.2/FU.3 harden code this same PR introduced
  (TB.1/TB.6), so the PR remains the single coherent review vehicle. Push after the checkpoint.
- **FU.4 is post-merge (or skipped)** — perf-only, gated on measurement, must not delay PR #12.
- `main` is release-only; never target it. Phase C still waits for PR #12 to merge (unchanged).

## Test-count bookkeeping

- Working tree today: **326 passed, 0 failed** — but this depends on an uncommitted
  `tests/test_cli.py` diff.
- **Clean checkout of pushed HEAD (37f7155): 324 passed, 2 failed** (verified via `git stash`) —
  this is what a reviewer or CI sees. FU.1 makes the clean checkout **326/0**.
- FU.2 adds 1 test → **327**. FU.3 adds 1 test → **328**. Record actuals in the todo per task.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| FU.2 touches `search_vector` → could affect ranking | TB.0 snapshot test must pass unchanged; cite it in FU.2's evidence |
| FU.2's fast-path removal re-breaks TB.1's ghost-results fix | TB.1's test (`test_search_vector_returns_empty_after_degenerate_rebuild`) must stay green — the degenerate path is handled by the flow *below* the fast path, verified in the audit |
| FU.3 breaks TB.3's corruption self-heal on read | File-level check only gates the *file-absent* case; corrupt-file-present still connects and heals — `test_corrupt_cache_db_self_heals` must stay green |
| FU.1 commit accidentally includes unrelated working-tree noise | The diff is exactly 2 decorator lines; stage `tests/test_cli.py` alone and review `git diff --cached` before committing |
| FU.4 "optimization" breaks TA.2's exact-token guarantee | Hard gate: all chunker tests green AND the absolute property re-verified on a full demo_corpus re-pack; if measurement shows no material regression, do nothing |

## Verification strategy

Per task: RED first (confirm the failure for the documented reason — FU.1's RED is the stash-clean
run) → fix → targeted test → full suite → evidence into the todo. FU.2 additionally re-runs the
TB.0 ranking snapshot. Checkpoint: full suite with `git status` showing **no modified tracked
files**, then push to PR #12.
