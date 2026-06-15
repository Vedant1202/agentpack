# SPEC: Hierarchical Knowledge Map for AgentPack

> Status: **Phase A + B shipped** on `feat/hierarchical-map` (based on `dev`). Phase C (opt-in LLM) and the `[ner]` extra deferred. · Owner: Vedant · Target package: `agent-context-packager`
> Spec covers three phases (A → B → C) delivered as separate PRs against one shared schema.

## 1. Objective

Today a pack's `manifest.yml` encodes chunk **addresses** (`source_path`, `page`, leaf `section`) as a flat list. An agent cannot answer *"where in this corpus is X discussed?"* without reading chunks, because the manifest carries location but not **structure** or **aboutness**.

Add a **hierarchical, compact knowledge map** — `corpus → document → section → chunk` — that an **agentic-RAG system** consults to locate relevant information by drilling top-down, then pulls only the leaf chunks it needs.

**Primary consumer:** an agent / agentic-RAG orchestrator navigating the corpus. **Secondary:** humans debugging packs (and the existing Corpus Explorer UI).

**Key enabling fact:** the section hierarchy is *already parsed* (Docling/markdown produce `DocumentBlock.section_path` + `page`) and then **discarded** at chunk time ([`chunker.py:61-62`](src/agentpack/chunker.py) keeps only `section_path[-1]`). Phase A largely *stops the discard* and reassembles the tree — not new information, just retained structure. (Bonus: [`ui/server.py:78`](src/agentpack/ui/server.py) already reads `citation['section_path']`, which is never written today — this fixes that dead path.)

### Success criteria
- An agent can go `map.yml` top tier → one document → its section tree → specific `chunk_ids` **without ever loading the flat chunk list**.
- The map stays compact at scale (thousands of chunks): descriptors live at section/document tier; leaves are *references*, not copies.
- **Deterministic and offline by default** (no runtime API); fully **additive** (existing `manifest.yml` and all consumers untouched).

## 2. Resolved decisions

| Decision | Choice | Rationale |
|---|---|---|
| Map location | **Sibling `map.yml`** next to `manifest.yml` | Keeps the retriever's manifest lean (41k+ lines on financebench); versions independently; additive. |
| Trigger | **On by default**; `--no-map` to skip; `--enrich-llm` for the LLM tier | A+B are cheap & deterministic; C is opt-in. |
| Phase-B deps | **Core deps**: declare `yake` + `networkx` (pulls `segtok`/`jellyfish`; `numpy`/`tabulate` already declared) | Net-new ≈ a few MB in a clean install (networkx ~3MB + yake/segtok/jellyfish), negligible vs the base's torch (436M). Avoid `nltk`/`sumy` (runtime data downloads break offline determinism). |
| Chunk→node mapping | Write full `section_path` list into chunk metadata (1-line chunker change) | Exact leaf→node mapping instead of fuzzy leaf-name+page matching; also fixes UI. |
| Descriptor granularity | **Section/document/corpus tier**, not per-chunk | Compactness + bounded pack-time cost. |

### Open for reviewer
- ~~`doc_type` / entity extraction depth in Phase B~~ — **Resolved: general-purpose packer → no domain heuristics.** Drop `doc_type` (format already lives in `manifest.sources[].type`); aboutness stays domain-agnostic (YAKE keyphrases + TextRank gist + structural stats). Typed `entities` via NER move to an **opt-in `[ner]` extra**, never in the default path.
- ~~Standalone `agentpack map <pack_dir>` rebuild command~~ — **Resolved: yes** (mirrors `index`).

## 3. The `map.yml` schema (shared across all phases)

Fields are tagged by the phase that produces them: **[A]** structure (deterministic), **[B]** deterministic descriptors, **[C]** LLM descriptors (opt-in, replaces B's `gist`/`summary`).

```yaml
map_version: 1                                   # [A]
pack:                                            # [A] link back to the manifest
  name: financebench_sample
  generated_at: '2026-06-14T...'
  manifest: manifest.yml
corpus:
  summary: "5 SEC filings (10-K/10-Q): JPMorgan, Amcor, 3M, CVS, AWK; FY2020–2023."  # [B]/[C] extractive
  stats: {documents: 5, sections: 312, tables: 110, chunks: 5825}                      # [A]
documents:
- source_id: src_002                             # [A] FK → manifest.sources[].id
  path: AMCOR_2020_10K.pdf                        # [A]
  title: "Amcor 2020 Annual Report"               # [A] from first heading / filename
  status: success                                 # [B] "failed" when the source did not parse
  pages: [1, 188]                                 # [A]
  summary: "Packaging operations, segment results, balance sheet, restructuring."     # [B]/[C] extractive (TextRank)
  stats: {sections: 64, tables: 31, chunks: 980}  # [A] domain-agnostic structural signal
  # entities: {ORG: [Amcor plc], DATE: ['2020']}  # [B-opt] only when the `[ner]` extra is installed
  sections:                                       # [A] recursive TOC tree
  - node_id: s_002_0007                           # [A] stable id
    title: "Item 8 — Consolidated Balance Sheets" # [A]
    pages: [96, 101]                              # [A]
    has_tables: true                              # [A] from block types
    keyphrases: [accounts receivable, inventory, current liabilities]                 # [B] YAKE — the topic signal
    gist: "Current assets incl. net trade receivables; current liabilities."          # [B]/[C] extractive (1 line)
    chunk_ids: [src_002_chunk_241, src_002_chunk_242]   # [A] leaves → manifest.chunks
    nodes: []                                     # [A] child sections (same shape, recursive)
```

Invariants:
- Every `chunk_ids` entry exists in `manifest.chunks`; every non-orphan chunk is reachable from exactly one node. Orphans (no section) are listed under a synthetic `__root__` node per document.
- `node_id` is stable & deterministic (derived from source_id + ordinal path), not content-hashed.
- Phase A emits the tree with all `[A]` fields; `[B]`/`[C]` fields are simply absent until those phases run.
- The topic signal lives at the **section** tier (`keyphrases`). Synthesized document/corpus topic *lists* are intentionally omitted: rolling many sections into one list is lossy and biases toward whatever repeats (boilerplate) or whatever comes first — so doc/corpus carry only an extractive `summary`. The agent reads section `keyphrases` on drill-down.

## 4. Phases, scope & acceptance criteria

### Phase A — Structural TOC tree (deterministic, no new deps)
**Scope:** new `src/agentpack/mapper.py` (build tree from `doc.blocks`); 1-line `chunker.py` change to persist `section_path`; `pack.py` hook to write `map.yml`; pydantic models in `models.py`; optional `map.yml` checks in `validate.py`; `--no-map` flag + `agentpack map` command in `cli.py`.

**Acceptance:**
- [ ] `agentpack pack` writes `map.yml` by default; `--no-map` suppresses it.
- [ ] Tree mirrors parsed section hierarchy; all schema `[A]` invariants hold (chunk reachability, FK integrity, `has_tables`).
- [ ] **Determinism:** two packs of the same corpus produce byte-identical `map.yml` except `pack.generated_at`.
- [ ] **No regression:** `validate`, `retrieve`, `audit`, `ui`, and `agentpack eval` behave identically (verified by re-running an existing benchmark's retrieval report → unchanged numbers).
- [ ] `manifest.yml` chunk citations now include `section_path`; UI breadcrumb populated.

### Phase B — Deterministic descriptors (core deps: yake, networkx)
**Scope:** new `src/agentpack/enrich.py` — YAKE keyphrases + `networkx`-PageRank extractive gist/summary; domain-agnostic structural stats (sections/tables/chunks). **No domain heuristics, no typed entities** — NER is deferred to an opt-in `[ner]` extra (§10). Reuse `.cache` (new namespace) keyed on node-text hash. Wire into `mapper.py`.

**Acceptance:**
- [ ] Corpus/doc nodes carry `summary`+`topics`; section nodes carry `gist`+`keyphrases`.
- [ ] **Deterministic** given pinned versions; re-pack hits cache (no recompute).
- [ ] Pack-time overhead from B is **< ~30s on financebench_sample** and a small fraction of total parse time.
- [ ] Net-new install footprint **≈ a few MB** (clean install: yake+networkx+segtok+jellyfish), negligible vs base torch.
- [ ] No `nltk`/`sumy`; no runtime downloads (asserted in test).

### Phase C — Opt-in LLM enrichment (`--enrich-llm`)
**Scope:** reuse the eval-side LLM call pattern ([`eval/baselines.py`](src/agentpack/eval/baselines.py), `LLM_BASELINE_MODEL`). Replace `[B]` `gist`/`summary` with abstractive (RAPTOR-style recursive / Contextual-Retrieval-style) summaries. Deterministic cache keyed on node text + model; cost reporting; graceful fallback to extractive on error.

**Acceptance:**
- [ ] Flag off ⇒ **zero network calls** (asserted). Flag on ⇒ abstractive summaries replace extractive ones.
- [ ] Results cached & reproducible (temperature 0, cache key includes model id).
- [ ] LLM failure falls back to the Phase-B extractive gist, never aborts the pack.

## 5. Commands (CLI surface)

| Command | Change |
|---|---|
| `agentpack pack <dir> --out <out>` | **New flags:** `--no-map` (skip map), `--enrich-llm` (Phase C). Map built by default. |
| `agentpack map <pack_dir>` | **New** — (re)build `map.yml` for an existing pack (mirrors `agentpack index`). Honors `--enrich-llm`. |
| `agentpack validate <pack_dir>` | Extended to validate `map.yml` **if present** (FK + reachability). Manifest checks unchanged. |
| all others (`retrieve`, `audit`, `index`, `ui`, `eval`, `gen-eval`) | **Unchanged.** |

## 6. Project structure

```
src/agentpack/
  mapper.py        # NEW [A] — build corpus→doc→section tree from doc.blocks + chunks
  enrich.py        # NEW [B] — YAKE keyphrases, TextRank gist/summary, structural stats (domain-agnostic)
  models.py        # +MapNode/DocumentMap/CorpusMap pydantic models
  chunker.py       # +1 line: persist full section_path into chunk metadata
  pack.py          # call mapper (+enrich), write map.yml; thread --no-map/--enrich-llm
  cli.py           # pack flags + new `map` command (lazy imports per existing pattern)
  validate.py      # optional map.yml validation
tests/
  test_mapper.py   # NEW — tree shape, reachability, has_tables, determinism
  test_enrich.py   # NEW — keyphrase/gist determinism, no-download assertion, no domain heuristics
  test_map_cli.py  # NEW — flags, `map` command, validate-on-map
  (existing tests must pass unchanged)
```

## 7. Code style

Match the existing codebase:
- **Lazy imports inside CLI commands** (keep `--help`/`--version` fast — see `cli.py` header note).
- **Pydantic models** for any structured output (mirror `models.py`); dict-assembly only at the YAML boundary (mirror `pack.py`).
- **`yaml.dump(..., default_flow_style=False, sort_keys=False)`** to match manifest formatting.
- Reuse the **`.cache` L1 pattern** (`cache.py: cache_get/cache_set/make_key`) for enrichment, with a versioned key namespace.
- Deterministic ordering everywhere (sources by index, sections by document order); no `set` iteration leaking into output.

## 8. Testing strategy

- **Unit:** tree construction, chunk→node mapping, `has_tables`, structural stats, YAKE/TextRank determinism.
- **Golden snapshot:** tiny fixture corpus (reuse `tests/fixtures/`) → committed `map.yml` snapshot; diff on change.
- **Determinism:** build twice, assert equal modulo `generated_at`.
- **Regression guard:** assert presence of an unknown sibling file / new manifest field does **not** break `validate_pack`, `search_pack`, `audit_pack`, or the UI loader.
- **Offline guard (B/C):** monkeypatch/network-block test asserting the default path makes no network calls and triggers no data downloads.
- **Eval parity:** re-run one benchmark's `retrieve` path; numbers unchanged (map is additive).

## 9. Boundaries

**Always**
- Keep changes **additive** — never remove/rename existing `manifest.yml` keys or chunk fields (only add `section_path`).
- **Deterministic & offline by default**; reuse existing cache/lazy-import/pydantic patterns.
- Descriptors at section/document tier; leaves reference chunks, never duplicate content.

**Ask first**
- Adding any core dependency beyond `yake` + `networkx` (which pull `segtok`/`jellyfish`).
- Any change to chunk identity/schema beyond adding `section_path`.
- Changing retrieval behavior or making the LLM tier default.

**Never**
- Call an external API in the default/deterministic path (Phase C is the *only* network path, strictly behind `--enrich-llm`).
- Download models/data at runtime (no `nltk punkt`, no `sumy`).
- Rewrite or alter the retrieval engine (FTS5 / HNSW / RRF).
- Break any existing consumer of `manifest.yml`.
- Bake domain-specific assumptions into the core path (no finance/legal/medical ontologies, regexes, or doc-type heuristics) — AgentPack is a general-purpose packer.

## 10. Out of scope
- Rewriting retrieval/ranking (FTS5/HNSW/RRF).
- Cross-encoder reranking (already roadmapped for v0.4).
- Online crawling / non-local sources.
- Making LLM enrichment the default.
- **Domain-specific extraction in the core path** (no finance/legal/etc. heuristics or ontologies).

### Deferred: optional `[ner]` extra (post-A/B/C)
Typed entities (`ORG`/`PERSON`/`DATE`/…) via a domain-agnostic NER model — **GLiNER** (zero-shot, reuses the torch already pulled by Docling) or **spaCy** (`en_core_web_sm`). Strictly opt-in (`pip install agent-context-packager[ner]`), populates the optional `entities` field, and lives **outside** the offline-deterministic guarantee (needs a one-time model download). YAKE keyphrases already cover most navigation value without it.
