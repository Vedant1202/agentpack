# Plan — Corpus Concept Graph (graph.yml)

> Implements [docs/specs/0003-corpus-concept-graph.md](../docs/specs/0003-corpus-concept-graph.md) (**APPROVED** — open questions resolved, gates user-tunable via `agentpack.toml [graph]`). Vertical slicing, mirroring [trust-layer-plan.md](trust-layer-plan.md): walking skeleton end-to-end first, deepen edge-type-by-edge-type, human checkpoint before the index-time phase. Companion todo: [concept-graph-todo.md](concept-graph-todo.md) — **read its handoff header first if you are the implementing agent.**

## Dependency graph

```
config.py [graph] section ─────────┐  (leaf — T0.1, no dependents until T1 reads params)
models.py Graph* models ───────────┤  (leaf — T0.2)
                                   ▼
                    grapher.py  (hub — T1 skeleton, deepened by T2/T3/T4/T5)
                    build_graph(pack_dir, params) reads ONLY pack artifacts on disk:
                    map.yml + manifest.yml + chunks/*.md   →   graph.yml + reports/graph_report.md
                                   │
              ┌────────────────────┼─────────────────────────┐
              ▼                    ▼                         ▼
        pack.py hook          cli.py                    validate.py
        (T1: after the        (T6: --no-graph flag;     (T7: FK checks when
        map block at          `agentpack graph`         graph.yml present —
        pack.py:255-266,      rebuild cmd mirroring     mirrors _validate_map
        behind no_graph)      map_cmd cli.py:175-199)   validate.py:76-100)
                                   │
                                   ▼
                    tests/test_grapher.py + test_graph_cli.py
                    (+ extensions to test_config.py, test_validate.py)

  Phase B (gated on human checkpoint):
        retrieve.py build_vector_index (retrieve.py:132) ──► additive hook AFTER the
        existing index write → section centroids → similar_to edges merged into graph.yml.
        This is the ONLY permitted contact with retrieve.py, and it is append-only.
```

**Ordering implications**
- `config.py` and `models.py` changes are independent leaves — land first, in either order.
- `grapher.py` is the hub; every Phase-A slice after T1 modifies only it plus tests. That keeps blast radius flat: T2–T5 cannot break pack/cli/validate wiring because they don't touch it.
- `pack.py`/`cli.py`/`validate.py` are one-shot wirings (T1, T6, T7) against named, existing patterns — each has a template in the codebase to mirror, cited per task in the todo.
- The builder is a **pure post-processor over pack output artifacts**. This is the load-bearing architectural decision (spec §3): it makes `agentpack graph <pack_dir>` and the pack-time hook the *same code path* (rebuild parity is by construction, then verified by test), and it makes the do-not-touch list (§ below) enforceable — there is no reason for any task to open `parsers/`, `chunker.py`, `cache.py`, `trust.py`, or (until Phase B) `retrieve.py`.

## Verified facts — do not re-derive

Spec §2 carries a table of facts verified live against this repo/venv (embeddings exist only at index time; markdown links survive verbatim into chunk text; `map.yml` node ids/keyphrases per `SectionNode` at models.py:33-42; networkx 3.6.1 seeded `louvain_communities` is deterministic; RRF seam location; the repo's own boilerplate lesson). Treat them as ground truth. If one contradicts what you observe, **stop and report** — do not improvise around it.

## Slicing rationale

- **T1 proves the whole pipe** (pack → grapher → graph.yml → manifest-consumer safety → determinism test) on the two node kinds that need zero judgment (documents, sections) before any concept logic exists.
- **T2/T3/T4/T5 deepen the same pipe** one capability at a time — concepts, references, communities, report — each independently testable, each leaving the suite green.
- **T6/T7 are surface wirings** kept separate from graph logic so CLI/validation review is trivial.
- **The checkpoint is a hard stop**: concept quality on a real corpus (financebench) is the one thing tests cannot judge — a human looks before Phase B spends effort on similarity edges.

## Phases

| Phase | Tasks | Touches |
|---|---|---|
| 0 — leaves | T0.1 config `[graph]`; T0.2 models | config.py, models.py, test_config.py |
| A — structural graph | T1 skeleton → T2 concepts → T3 references → T4 communities → T5 report → T6 CLI → T7 validation → T8 regression sweep | grapher.py (new), pack.py, cli.py, validate.py, tests |
| ▣ | **CHECKPOINT — human go/no-go** (concept quality + community coherence on demo_corpus + financebench_sample; df_cap default sanity-check) | — |
| B — similarity (gated) | B1 `similar_to` edges at index time, idempotent merge | grapher.py, retrieve.py (append-only hook), cli.py (`--with-similarity`) |
| C — deferred | RRF retrieval integration (ask-first), LLM enrichment, UI | not planned here — see spec §5 |

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| dict/set iteration order leaking into graph.yml → non-deterministic artifact | Build-twice determinism test is **required in every task from T1 on**, not once at the end; sorted iteration is a spec §8 Always |
| YAKE keyphrases too noisy on real filings → junk concepts | Exactly what the checkpoint + user-tunable `df_cap`/`min_docs` exist for; do not hand-tune constants mid-implementation |
| Rebuild (`agentpack graph`) drifting from pack-time output | Same code path by construction; T6's byte-parity test proves it; recorded `params:` block prevents config drift (spec §4a) |
| Implementer "helpfully" wiring the graph into retrieval | Do-not-touch list in the todo header; spec §8 Never; Phase C is a separate ask-first decision that belongs to the human |
| Louvain community ids churning across runs despite seed | Determinism hardening specified in T4 (fresh graph, sorted node+edge insertion, size-desc + `tuple(sorted(members))` re-index) — copy the recipe, don't reinvent it |
