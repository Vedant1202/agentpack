# Spec: Corpus Concept Graph (graph.yml)

> Status: **APPROVED — ready for implementation** (open questions §10 resolved 2026-08-11: proposed defaults accepted, exposed as user-tunable config — see §4a)
> Owner: Vedant
> Created: 2026-08-11
> Prior art: a code-level study of the `graphify` knowledge-graph tool (patterns and failure modes only — no code is copied from it)
> Relates to: `SPEC.md` (Knowledge Map — `graph.yml` builds *on top of* `map.yml`, never changes it), `docs/specs/0001-parsing-and-retrieval-overhaul.md` (retrieval Boundaries govern the deferred Phase C), `docs/specs/0002-ingestion-trust-layer.md` (structure/tone template; the never-raise posture is reused here)
>
> **Implementer note:** this spec is written to be executed without re-deriving context. Every fact in §2 was verified against the live repo/venv when this spec was written. Do not re-litigate them; if one turns out to be false in practice, stop and report rather than improvising around it.

## 1. Objective

`map.yml` is a strict per-document tree: corpus → document → section → `chunk_ids`. It has **zero cross-document edges**. An agent can drill into one document but can never discover that section 4 of filing A discusses the same restructuring as section 7 of filing B — the current architecture cannot answer "what elsewhere in this corpus relates to X?" without brute-force retrieval.

This spec adds a deterministic, LLM-free, cross-document **concept graph** — a sibling `graph.yml` — built entirely from artifacts AgentPack already computes:

- **YAKE keyphrases** per section (already in `map.yml`, from `enrich.py`)
- **markdown links** (present verbatim inside chunk text on disk)
- **fastembed chunk vectors** (already computed at index time, L3-cached) — Phase B only

The prior-art study that motivated this found that graphify — a tool built around exactly this kind of graph — requires an LLM pass to get concept nodes and similarity edges for documents, has no structural model for PDFs at all, and stores no document text. AgentPack already has the stronger halves of all three (deterministic keyphrases, Docling section/page structure, full-text chunks with citations). The missing piece is only the cross-document edge layer, and every input it needs already exists on disk.

**Primary consumer:** the same agentic-RAG orchestrator that consumes `map.yml` — the graph answers "what relates to X across documents?" the way the map answers "where inside this document is X?". **Secondary:** humans reading `reports/graph_report.md` for corpus themes and coverage gaps.

### Success criteria (testable)
- Packing a multi-document corpus where two documents share a section keyphrase produces a concept node with `mentions` edges spanning both documents.
- A markdown document linking to another packed document produces a `references` edge; external URLs and unresolved link targets produce nothing.
- A single-document pack produces **no** `graph.yml` (auto-skip, one-line stderr note, not a warning).
- Two packs of the same corpus produce byte-identical `graph.yml` except `generated_at`.
- `agentpack graph <pack_dir>` rebuilds `graph.yml` byte-identically (modulo `generated_at`) to the pack-time output — same code path, not a lossy approximation.
- Zero new dependencies. Zero changes to `manifest.yml`/`map.yml` schema or any existing consumer. `agentpack eval` numbers unchanged **by construction** (retrieval code untouched in Phases A/B).
- Full existing test suite passes unchanged.

## 2. Verified facts (do not re-derive; grounds every design decision below)

| Fact | Where verified | Consequence |
|---|---|---|
| Embeddings are built at **index** time, not pack time: `build_vector_index` ([retrieve.py:132](../../src/agentpack/retrieve.py)) reads `manifest.yml` + chunk files from an already-written pack; L3 cache keyed `sha256(chunk_text)+model_id` at retrieve.py:166-198 | live read | `similar_to` edges **cannot** be a pack-time feature → they are Phase B, hooked where vectors exist |
| The markdown parser ([parsers/markdown_parser.py](../../src/agentpack/parsers/markdown_parser.py)) does **not** extract links; paragraph blocks retain raw markdown (`[x](y.md)`) and that text flows into `chunks/*.md` on disk | live read | doc→doc `references` edges are regex-extracted from **chunk text** at graph-build time — zero parser changes |
| `map.yml` section nodes already carry `node_id` (deterministic ordinal path, e.g. `s_002_0007`), `keyphrases`, `chunk_ids` — `SectionNode` at [models.py:33-42](../../src/agentpack/models.py) | live read | graph nodes **reuse these exact ids** (single-identity rule, §8) |
| `networkx>=3.0` and `yake` are already core deps; installed networkx 3.6.1 `louvain_communities(G, seed=42)` returns identical results across runs | live run | zero new dependencies; seeded Louvain is the community algorithm |
| `search_hybrid`'s RRF fusion ([retrieve.py:359-390](../../src/agentpack/retrieve.py)) fuses by **rank**, so a graph-derived ranked list composes with no score normalization — but 0001's Boundaries make retrieval changes ask-first | live read | retrieval integration is **Phase C, deferred**, never bundled into A/B |
| The repo's own recorded lesson ([tasks/todo.md](../../tasks/todo.md), Phase B note): synthesized doc/corpus topic lists were dropped because aggregation biases toward boilerplate | repo history | concept promotion **requires** a document-frequency cap (§4) |
| Pack-time integration point: the `if not no_map:` block at [pack.py:255-266](../../src/agentpack/pack.py); flag pattern at [cli.py:35](../../src/agentpack/cli.py) (`--no-map`); rebuild-command pattern at cli.py:175 (`map_cmd`); map validation pattern at [validate.py:76-100](../../src/agentpack/validate.py) | live read | each Phase-A wiring task has a named, existing pattern to mirror |

## 3. Resolved decisions

| Decision | Choice | Rationale |
|---|---|---|
| Artifact | Sibling `graph.yml` next to `map.yml`/`manifest.yml`; `yaml.dump(..., default_flow_style=False, sort_keys=False)` | Mirrors the map.yml precedent exactly; additive; versions independently |
| Builder architecture | **Pure post-processor over pack artifacts on disk** (`map.yml` + `manifest.yml` + `chunks/*.md`). Never touches parsers or the parse loop | Makes `agentpack graph <pack_dir>` and the pack-time hook the *same code path* — unlike `agentpack map`'s lossy chunk-driven rebuild. Also means the trust layer, cache, and parsers are provably untouched |
| Node identity | Documents: manifest `source_id`. Sections: map.yml `node_id`. Concepts: `c_<slug>` (normalization recipe in §4) | **Single-identity rule.** The prior-art tool's costliest bug class was twin nodes from two id schemes for the same entity (its AST/semantic split needed a permanent reconciliation pass and produced a long tail of ghost/bloat bugs). Reusing existing ids makes that class unrepresentable |
| Edge provenance | Every edge carries `basis: structural \| keyphrase \| embedding` | The honest analogue of the prior art's EXTRACTED/INFERRED confidence tags — a consuming agent can decide how much to trust an edge |
| Communities | Seeded networkx Louvain (`seed=42`), with determinism hardening: rebuild the graph with sorted node + sorted edge insertion before partitioning; re-index communities by size desc with `tuple(sorted(members))` tiebreak | Prevents run-to-run community-id churn (a documented failure mode upstream: equal-sized communities permute under hash-seed variation unless a total order is imposed) |
| Community labels | Highest-degree **concept** member's phrase; ties by node id; LLM-free | Deterministic and readable; the prior art's hub-labeling pattern |
| Gating | Auto-skip (one-line stderr note) when the pack has <2 `status: success` sources; `--no-graph` flag mirrors `--no-map` | A single-document corpus gets zero cross-document value — the honest-tooling verdict pattern. Warning-level noise would be wrong for expected behavior |
| Failure mode | Builder wrapped so any internal failure degrades to "no `graph.yml`" + one warning line — never a crashed pack | Mirrors `trust.py`'s never-raise posture (0002 §8) and `cache.py`'s "never crash the main pipeline" |
| Rebuild command | `agentpack graph <pack_dir>`, mirroring `agentpack map` (cli.py:175), lazy imports per cli.py convention | Same surface users already know |
| Validation | `validate.py`: when `graph.yml` present, FK-check node ids against manifest `source_ids` + map `node_id`s + the concept-id set; edge endpoints against node ids. Absent `graph.yml` is not an error | Mirrors `_validate_map` (validate.py:76-100) exactly |
| Models | `GraphNode`, `GraphEdge`, `CorpusGraph` pydantic models in `models.py`, mirroring `SectionNode`/`DocumentMap`/`CorpusMap`; dict-assembly only at the YAML boundary | House style (0001 Code Style) |
| Tunable gates | The numeric gates (§4) are user-adjustable via a `[graph]` section in the **existing** `agentpack.toml` mechanism ([config.py](../../src/agentpack/config.py)) — no new config file. Effective values are recorded in `graph.yml`'s `params:` block; `agentpack graph <pack_dir>` rebuilds use the **recorded** params, not the toml | Deterministic gates replacing LLM judgment must be tunable per-corpus (a legal corpus and a filings corpus have different boilerplate profiles). Recording params in the artifact keeps the byte-determinism and rebuild-parity guarantees well-defined (identical *given identical params*) and makes every pack self-describing — a rebuild can never silently drift because the input dir's toml changed or is absent (the pack dir has no `agentpack.toml`) |

## 4. The graph model (Phase A)

### Concept normalization recipe (the only one — used everywhere)
`slug = re.sub(r"_+", "_", re.sub(r"[^\w]+", "_", phrase.casefold())).strip("_")`; concept id = `f"c_{slug}"`. Two keyphrases with the same slug are the same concept.

### Concept promotion gates (ALL must pass)
1. The keyphrase's slug appears in the `keyphrases` of sections belonging to **≥2 distinct documents** (cross-document value is the point — Open Question 4).
2. It appears in **≤30% of all sections** in the pack (boilerplate cap — Open Question 1; motivated by the repo's own dropped-topic-lists lesson, §2).
3. Normalized slug is ≥4 characters and not purely numeric/underscore.

### Nodes
```yaml
nodes:
- id: src_000            # document — manifest source_id, label = source path
  kind: document
  label: AMCOR_2020_10K.pdf
- id: s_000_0007         # section — map.yml node_id, label = section title
  kind: section
  label: "Item 8 — Consolidated Balance Sheets"
  doc: src_000
- id: c_accounts_receivable   # concept — promoted keyphrase
  kind: concept
  label: accounts receivable  # the most frequent surface form, ties broken lexically
```
Only sections that carry ≥1 promoted concept (or an edge of any kind) become nodes — bare structural sections stay in `map.yml` where they already live. Documents always get a node.

### Edges
| relation | endpoints | basis | source |
|---|---|---|---|
| `contains` | doc → section | `structural` | map.yml tree, **top-level sections only** (keeps graph.yml lean; deep nesting stays map.yml's job) |
| `mentions` | section → concept | `keyphrase` | section's `keyphrases` list, slug-matched |
| `references` | doc → doc | `structural` | markdown links regex-extracted from that doc's chunk text (`\[[^\]]*\]\(([^)#?\s]+)[^)]*\)` plus reference-style and `[[wikilink]]` forms), resolved against manifest source paths by filename match; external URLs (scheme prefix) and unresolved targets **dropped silently**; deduped per (src_doc, tgt_doc) pair |

Determinism requirement on every list: nodes sorted by (kind, id); edges sorted by (source, target, relation). No dict/set iteration order may reach the YAML.

### Communities
Computed over the full node set; every node gets a `community: <int>` field; a top-level `communities:` block lists `{id, label, size}` per community, ordered by id.

### `reports/graph_report.md` (deterministic, no LLM)
- **Top concepts** by degree (corpus themes), top 10
- **Bridge concepts** — concepts whose neighbors span ≥2 communities
- **Isolated documents** — documents with no cross-document edge (no shared concept, no reference): a coverage signal
- **Communities** — per-community label + document/section/concept membership counts
- Standalone file; `audit` untouched (§10 Q3, resolved)

## 4a. Configuration (`[graph]` in `agentpack.toml`)

Extend the existing loader — a `[graph]` section beside `[pack]`, read by the same `load_config` pattern (config.py:31-42; add a parallel `_GRAPH_DEFAULTS` dict and section read — do **not** merge graph keys into the `[pack]` namespace):

```toml
[graph]
enabled = true                # false ≡ --no-graph on every pack from this input dir
df_cap = 0.30                 # Q1: skip keyphrases appearing in > this fraction of all sections
min_docs = 2                  # Q4: concept must span ≥ this many distinct documents
similarity_threshold = 0.80   # Q2 (Phase B): min cosine for a similar_to edge
```

Rules:
- **Precedence:** CLI `--no-graph` > toml `enabled` > default — matching the existing `effective_fast = fast or cfg["fast"]` pattern (cli.py:47). The numeric gates are **toml-only** (no CLI flags): they're stable per-project tuning, exactly what the config file exists for, and CLI surface stays clean.
- **Validation at load:** `df_cap` in (0, 1]; `min_docs` ≥ 1; `similarity_threshold` in (0, 1]. Out-of-range values → one warning naming the key, fall back to the default (never crash — same posture as the builder itself). Note `min_docs = 1` is a *legitimate* user choice (allows intra-document concepts, §10 Q4) — the default is 2, not the floor.
- **Recording:** the effective values land in `graph.yml` under a top-level `params:` block. `agentpack graph <pack_dir>` reuses recorded params, so rebuild parity holds regardless of what any toml says now. Changing params = re-pack (or Phase-C future: an explicit `--config` override on the rebuild command — **not** in scope now).
- Section-level similarity granularity and the concept slug recipe are **not** knobs — they're structural decisions (§4, §10 Q2), and exposing them would multiply the test matrix for no per-corpus benefit.

## 5. Phasing

Each phase is a separate PR with a human checkpoint between — the same A→checkpoint→B process the Knowledge Map used.

**Phase A — pack-time structural graph (this spec's main body).**
New `src/agentpack/grapher.py`; nodes + `contains`/`mentions`/`references` edges; Louvain communities; `graph.yml` + `reports/graph_report.md`; `--no-graph` flag + `agentpack graph` command; `validate.py` extension; tests (§7). Zero new data computed — reads only what packs already contain.
**▣ CHECKPOINT:** run on `demo_corpus/` and `benchmarks/financebench_sample`; human reviews concept quality (are promoted concepts real topics or noise?) and community coherence before Phase B starts.

**Phase B — index-time similarity edges.**
`similar_to` (section ↔ section, `basis: embedding`): section centroid = mean of its chunks' already-normalized vectors; cosine ≥ 0.80 (Open Question 2). Computed where vectors exist — hooked into `build_vector_index` (retrieve.py:132, additive append after the existing index write) or an explicit `agentpack graph --with-similarity`; reuses the L3 embedding cache; merges into `graph.yml` and recomputes communities. Must be **idempotent**: re-running index never duplicates edges (merge keyed on (source, target, relation)).

**Phase C — DEFERRED, deliberately not specced here.**
(a) RRF third contributor in `search_hybrid` — a retrieval behavior change, ask-first per 0001's Boundaries, and gated on demonstrated lift in `agentpack eval`. Explicitly **not** a token-reduction ratio: the prior art's benchmark framing (corpus size sometimes estimated from graph size; label-only subgraphs compared against full text) is documented as self-favorable and must not be copied. (b) Optional LLM concept enrichment behind the existing enrichment-flag pattern. (c) UI rendering (`umap-learn` already in the `[ui]` extra).

## 6. Commands / project structure / code style

| Command | Change |
|---|---|
| `agentpack pack <dir> --out <out>` | New flag `--no-graph` (suppress). Graph built by default when ≥2 successful sources |
| `agentpack graph <pack_dir>` | **New** — (re)build `graph.yml` from an existing pack; same code path as pack-time. `--with-similarity` arrives in Phase B |
| `agentpack validate <pack_dir>` | Extended: validates `graph.yml` **if present** |
| all others | **Unchanged** (retrieve/audit/index/ui/eval untouched in A/B) |

```
src/agentpack/
  grapher.py       # NEW — build_graph(pack_dir, params) -> dict: read map.yml/manifest.yml/chunks,
                   #        promote concepts, emit nodes/edges/communities/params, write graph.yml + report
  models.py        # +GraphNode/GraphEdge/CorpusGraph (additive)
  config.py        # +_GRAPH_DEFAULTS + [graph] section read + range validation (§4a)
  pack.py          # call grapher after the map block (pack.py:255-266), same shape, behind --no-graph
  cli.py           # --no-graph on pack; new `graph` command (lazy imports)
  validate.py      # optional graph.yml FK checks
tests/
  test_grapher.py  # NEW (§7)
  test_graph_cli.py# NEW — flag + rebuild-command tests, mirroring test_map_cli.py
  test_config.py   # +[graph] section: defaults, overrides, out-of-range fallback (extends existing file)
```

Code style: match the house rules (0001 §Code Style) — lazy imports in CLI commands, pydantic models with dict-assembly only at the YAML boundary, `yaml.dump(..., default_flow_style=False, sort_keys=False)`, deterministic ordering everywhere, no `print` from library code.

## 7. Testing strategy

Mirror `tests/test_mapper.py` / `test_map_cli.py` conventions: fixtures built in-test, no committed binaries, `CliRunner` for CLI. Required tests:

- **Cross-document concept:** two markdown docs sharing a keyphrase → concept node + `mentions` edges spanning both; keyphrase in one doc only → no concept node.
- **Boilerplate cap:** a keyphrase present in >30% of sections → **not** promoted.
- **References:** doc A links `./b.md` → `references` edge; `https://…` link → nothing; link to a file not in the pack → nothing; three links to the same doc → one edge.
- **Auto-skip:** single-document pack → no `graph.yml`, pack succeeds, stderr note present.
- **Determinism:** build twice → byte-identical modulo `generated_at`; includes community ids (the Louvain hardening test).
- **Rebuild parity:** `agentpack graph <pack_dir>` output byte-identical (modulo `generated_at`) to the pack-time artifact.
- **Never-raise:** corrupted `map.yml` → pack completes, no `graph.yml`, one warning.
- **Validation:** valid graph passes; edge to unknown node id and node with unknown `doc` ref are both reported; absent `graph.yml` is not an error.
- **Config:** `[graph]` toml overrides take effect (a corpus whose shared keyphrase spans 2 docs produces the concept at `min_docs = 2` but not at `min_docs = 3`); out-of-range value → warning + default, never a crash; effective params recorded in `graph.yml`'s `params:` block; `agentpack graph` rebuild uses **recorded** params even when a conflicting toml exists in CWD.
- **Regression:** full existing suite green; `validate`/`audit`/`retrieve` behavior on packs *without* graph.yml provably unchanged; existing `[pack]` config keys unaffected by the new section.

## 8. Boundaries

**Always**
- Reuse `map.yml`/`manifest.yml` ids for documents/sections; concepts are the only new id namespace, minted by exactly one normalization recipe (§4).
- Sorted iteration into every serialized list; the build-twice determinism test is required, not optional.
- Read only pack **output** artifacts — parsers, chunker, cache, trust layer untouched.
- Degrade to "no graph.yml + one warning" on any internal failure.

**Ask first**
- Any new dependency (target is zero).
- Any change to `manifest.yml`/`map.yml` schema or to `search_hybrid`/anything in `retrieve.py` (Phase A/B must not touch it; Phase C is its own ask).
- Raising graph scope beyond the promoted-concept model (e.g. per-chunk nodes) — graph.yml must stay small relative to the pack.

**Never**
- Mint a second id for an entity that already has one (the single-identity rule — the prior art's costliest bug class).
- Promote gists, sentences, or any text longer than a YAKE 3-gram to a node (sentence-shaped labels are a known failure mode; rationale-as-node was tried upstream and rejected).
- Call an LLM or the network in Phases A/B.
- Let a graph failure fail the pack.
- Copy the prior art's token-reduction benchmark framing; retrieval claims go through `agentpack eval` only.

## 9. Descoped / out of scope

- **PDF citation-graph edges** (`cites`) — no reliable deterministic extractor; would need reference-section parsing. Future work.
- **Chunk-level similarity edges** — section-level centroids only (Open Question 2 covers granularity); per-chunk edges would explode graph size.
- **Concept extraction beyond YAKE** (NER entities, LLM concepts) — Phase C / the existing `[ner]`-extra plan in `SPEC.md` §10.
- **UI rendering** — Phase C.
- **Retrieval integration** — Phase C, ask-first.

## 10. Open Questions — RESOLVED 2026-08-11 (defaults accepted; numeric gates made user-tunable per §4a)

1. **Boilerplate DF cap** — ✅ default **0.30**, exposed as `[graph] df_cap`. Sanity-check the default at the Phase-A checkpoint against financebench output; users with different corpus profiles tune per-project rather than waiting on a perfect global constant.
2. **Similarity threshold / granularity** — ✅ default **0.80**, exposed as `[graph] similarity_threshold` (Phase B). Granularity stays **section-level and fixed** (not a knob): chunk-level was rejected for graph size, and a granularity switch would multiply the test matrix.
3. **Report location** — ✅ **standalone** `reports/graph_report.md`; `audit` untouched (its warning grouping just shipped in 0.4.2 — don't churn it). Not configurable; it's a design decision, not a threshold.
4. **Concept minimum** — ✅ default **2 distinct documents**, exposed as `[graph] min_docs`. `min_docs = 1` is a legitimate opt-in for users who want intra-document concepts, but the default matches the cross-document motivation (intra-doc keyphrases already live in `map.yml`).

## 11. Success criteria (rollup)

- [ ] All §1 success criteria pass, including byte-determinism and rebuild parity.
- [ ] Concept gates (§4) enforced with tests for each gate.
- [ ] `basis` field on every edge; only `structural`/`keyphrase` appear in Phase A.
- [ ] Auto-skip on <2 successful sources; `--no-graph` works; never-raise verified.
- [ ] `validate.py` covers graph.yml FKs; absent file is not an error.
- [ ] `reports/graph_report.md` sections render deterministically (top concepts, bridges, isolated docs, communities).
- [ ] `[graph]` config section works per §4a: overrides honored, out-of-range → warning + default, params recorded in `graph.yml`, rebuild honors recorded params over any ambient toml.
- [ ] Zero new dependencies; zero retrieval changes; full suite green.
- [x] Open Questions 1–4 resolved (2026-08-11 — defaults accepted, numeric gates exposed via `agentpack.toml`).
- [ ] Phase-A checkpoint (concept quality + community coherence on a real corpus) passed before Phase B starts.
