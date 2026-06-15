# Plan — Hierarchical Knowledge Map

> Implements [SPEC.md](../SPEC.md). Phase A is detailed (approved to start now); B and C are sketched and **gated behind checkpoints**. Vertical slicing: ship a thin end-to-end `map.yml` first, then deepen — never finish one layer across all components before the path works end-to-end.

## Dependency graph

```
            (leaf, foundational)        (hub)              (sink)
  models.py  ─────────────────┐
  (schema: SectionNode/        ├──►  mapper.py  ──►  pack.py  ──►  cli.py
   DocumentMap/CorpusMap)      │     (build tree    (write       (--no-map flag,
                               │      from blocks    map.yml,     `agentpack map`)
  chunker.py ──────────────────┘      + chunks)      thread flags)
  (+section_path into
   chunk metadata)                         │
                                           ├──►  validate.py  (optional map.yml checks)
                                           │
  ui/server.py: section_path breadcrumb    └──►  tests + golden snapshot
  becomes live for free once chunker lands       (depend on pack.py output)
```

**Ordering implications**
- `models.py` and the `chunker.py` one-liner are **independent leaves** — can land first / in parallel.
- `mapper.py` is the **hub**; everything downstream waits on it.
- `validate.py` depends only on the schema, so it can proceed in parallel with `pack.py` wiring.
- The UI breadcrumb ([`server.py:78`](../src/agentpack/ui/server.py)) lights up automatically once chunks carry `section_path` — no UI work required in Phase A.

## Slicing strategy (why these cuts)

Each Phase-A task is a **vertical slice** that leaves `main` green and produces something observable:
- **A1** proves the *entire pipe* (parse → tree → `map.yml` → CLI → test) on a trivial corpus before any richness exists.
- **A2–A4** deepen that same pipe (real nesting, CLI surface, validation/regression) rather than building isolated horizontal layers.
- **A5** is a *reality check* against a real Docling pack + a CHECKPOINT, so we learn whether section structure is good enough **before** investing in Phase B descriptors.

## Phase A — Structural TOC tree (deterministic, no new deps)

| # | Task | Touches |
|---|------|---------|
| A1 | Walking skeleton: minimal schema + `section_path` persist + flat tree → write `map.yml` for a simple markdown corpus, on by default | models, chunker, mapper, pack |
| A2 | Real hierarchy: recursive nested sections from `section_path`; `__root__` orphan bucket; `has_tables`; stable `node_id`; deterministic ordering | mapper |
| A3 | CLI surface: `--no-map` flag + standalone `agentpack map <pack_dir>` rebuild command | cli, pack |
| A4 | Integrity: optional `map.yml` validation; golden-snapshot + determinism + regression tests | validate, tests |
| A5 | Prototype on a real pack + **CHECKPOINT 1** | (no code) |

Acceptance criteria and per-task verification steps live in [todo.md](todo.md).

### ▣ CHECKPOINT 1 — after A5, before Phase B
Human review of a **real `map.yml`** generated from an existing pack (e.g. `benchmarks/financebench_sample`): Is the tree faithful to the documents? Are Docling section boundaries clean enough to hang descriptors on? Confirm **eval parity** (existing retrieval numbers unchanged). Go/no-go on Phase B.

## Phase B — Domain-agnostic descriptors *(gated by CHECKPOINT 1)*

| # | Task |
|---|------|
| B1 | Add core deps (`yake`, `networkx`); scaffold `enrich.py`; extend `.cache` namespace |
| B2 | YAKE keyphrases at section/doc/corpus tiers |
| B3 | `networkx`-PageRank (TextRank) extractive `gist`/`summary` |
| B4 | Structural `stats`; wire enrich into mapper; offline-guard test (no network/downloads); pack-time overhead check |

### ▣ CHECKPOINT 2 — after B4, before Phase C
Review descriptor quality on real corpora, measured pack-time overhead (target « parse time), and net install size. Go/no-go on Phase C.

## Phase C — Opt-in LLM enrichment *(gated by CHECKPOINT 2)*

| # | Task |
|---|------|
| C1 | `--enrich-llm` flag; reuse eval-side LLM client (`eval/baselines.py`); deterministic cache keyed on node-text + model |
| C2 | Abstractive summaries replace extractive `gist`; graceful fallback on error; cost report; assert zero network when flag off |

### ▣ CHECKPOINT 3 — after C2
Review summary quality, cost, and cache reproducibility.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Docling section quality varies by document | **A5 prototype validates before B** — that's the whole point of the checkpoint |
| Non-deterministic YAML emission (dict/set ordering) | Enforce ordered emission (`sort_keys=False` + sorted inputs); **golden snapshot + build-twice diff** in A4 |
| Some parsers (txt) emit no `section_path` | Tree degrades to a single `__root__` node per source; explicit test in A2 |
| Chunk→node mapping ambiguity | `section_path` (full list) makes mapping exact; unmatched chunks fall into `__root__` |
| A new sibling file breaks a consumer | Additive by design; **regression guard** asserts `validate`/`retrieve`/`audit`/`ui` unaffected (A4) |

## Verification harness (used across tasks)

```bash
# unit + regression (existing tests must stay green)
pytest tests/ -q

# end-to-end smoke on a tiny corpus
agentpack pack benchmarks/phase1-benchmarks/corpus --out /tmp/ap_smoke
agentpack validate /tmp/ap_smoke           # must pass with map.yml present
cat /tmp/ap_smoke/map.yml                   # eyeball the tree

# determinism: build twice, diff ignoring the timestamp
agentpack map /tmp/ap_smoke && cp /tmp/ap_smoke/map.yml /tmp/m1.yml
agentpack map /tmp/ap_smoke && diff <(grep -v generated_at /tmp/m1.yml) <(grep -v generated_at /tmp/ap_smoke/map.yml)

# eval parity (additive change → unchanged numbers)
agentpack eval benchmarks/phase1-benchmarks
```
