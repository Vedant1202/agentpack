# A Worked Example

Every output on this page is real. It comes from packing the four Markdown files in
[`examples/docs_example_corpus/`](https://github.com/Vedant1202/agentpack/tree/main/examples/docs_example_corpus),
which ship with the repository so you can reproduce all of it:

```bash
git clone https://github.com/Vedant1202/agentpack.git
cd agentpack && pip install -e .
agentpack pack ./examples/docs_example_corpus --out ./out
agentpack index ./out
agentpack retrieve ./out "what should I do about a bad release during an incident" --top-k 3
```

The corpus is a small engineering handbook: `onboarding.md`, `incident-response.md`,
`api-gateway.md`, and `alerting.md`. It is deliberately tiny — small enough that you can
hold the whole thing in your head while reading what AgentPack did to it.

> **Note — This corpus is all Markdown**
>
> Markdown has no page numbers and no embedded tables, so this walkthrough cannot show those. [Citations from other formats](#citations-from-pdfs-and-csvs) at the end of this page shows what a PDF- or CSV-sourced citation looks like instead.

---

## 1. What goes in

Four files, about 2,600 words total:

```text
examples/docs_example_corpus/
├── agentpack.toml         # optional; the defaults written out explicitly
├── alerting.md            # how alerts are defined, routed, tuned
├── api-gateway.md         # routing, rate limiting, auth, timeouts
├── incident-response.md   # severity levels, what to do when an alert fires
└── onboarding.md          # access, deployment basics, first week
```

Two of them link to each other. `onboarding.md` contains:

```markdown
Read [the incident response runbook](incident-response.md) before your first
on-call shift.
```

and `incident-response.md` links back. That detail matters later — it becomes a
`references` edge in the concept graph.

## 2. Compiling the pack

```bash
$ agentpack pack ./examples/docs_example_corpus --out ./out
Packing ./examples/docs_example_corpus into ./out...
Pack generated at ./out
Done.
```

That is the entire output on success. Warnings (unreadable PDFs, empty files) would appear
here; this corpus produces none.

## 3. What lands on disk

```text
out/
├── manifest.yml                    # every chunk, with its citation
├── map.yml                         # corpus → document → section → chunk tree
├── graph.yml                       # how the four documents relate to each other
├── chunks/
│   ├── src_000_chunk_000.md        # alerting.md
│   ├── src_001_chunk_000.md        # api-gateway.md
│   ├── src_002_chunk_000.md        # incident-response.md
│   ├── src_002_chunk_001.md
│   ├── src_003_chunk_000.md        # onboarding.md
│   └── src_003_chunk_001.md
├── .cache/
│   └── cache.db                    # so a re-pack only pays for what changed
└── reports/
    ├── pack_report.md
    └── graph_report.md
```

Four documents became **six chunks**. `tables/` and `indexes/` are absent here — this
corpus has no tables, and indexes are built by `agentpack index` in step 6.

## 4. What a chunk looks like

A chunk is a plain Markdown file. No front matter, no wrapper, no JSON envelope — just the
text, ready to drop into a prompt. Here is `chunks/src_003_chunk_001.md` in full
(326 tokens, from `onboarding.md`):

```markdown
Your First Week

Pick a starter issue labelled `good-first-issue`. Ship it through the full
deployment pipeline end to end, even though it is small. The point is to see
every stage run once while someone is sitting next to you, so that the first
time you watch the pipeline is not during an incident.

Pair with your onboarding buddy for the first review. Code review here is
blocking and is expected to take a day, not an hour. A review that comes back
in ten minutes usually means the reviewer skimmed it.

Do not spend your first week reading the entire codebase. Read the service you
are shipping to, read its tests, and read the runbook for the alert it owns.
Breadth comes later and comes faster once you have shipped something.

Where Things Live

Service code lives in the `platform` org, one repository per service. There is
no monorepo, and attempts to create one have been abandoned twice.

Infrastructure is defined in the `infra` repository as Terraform modules.
Changes there go through the same deployment pipeline as service code, with an
additional manual approval gate before the apply step.

The API gateway configuration is the one exception: it lives in its own
repository because its release cadence is different from everything else and
because a bad gateway config affects every service at once rather than one.

Documentation lives next to the code it describes. A runbook that lives in a
wiki drifts from reality within two quarters; a runbook in the repository at
least shows up in the diff when the behaviour it documents changes.
```

Note that this one chunk spans **two** sections — "Your First Week" and "Where Things
Live". Chunks are filled up to the token budget across section boundaries; they are not
one-per-section. This is worth remembering when you read the citation in the next step.

## 5. Where a chunk came from: `manifest.yml`

The manifest is the registry that makes every chunk traceable. Here it is in full — six
chunks is small enough to show the whole file:

```yaml
pack:
  name: docs_example_corpus
  version: 0.5.1
  generated_at: '2026-09-21T22:16:10.891275+00:00'
sources:
- id: src_000
  path: alerting.md
  type: markdown
  checksum: 8dc7a90e2687822222f8d5c62f90d85e7aa3ef8f4fb676be37780e4242ff6f10
  status: success
  warnings: []
- id: src_001
  path: api-gateway.md
  type: markdown
  checksum: f0694c703e6747ed82b3e8d7019f3528271590e640499124ac65dbeb5e812fe3
  status: success
  warnings: []
- id: src_002
  path: incident-response.md
  type: markdown
  checksum: e5402e0890698c500cf2ed573ab7c11bbf9d6a917638f45d966ebf30b66659e3
  status: success
  warnings: []
- id: src_003
  path: onboarding.md
  type: markdown
  checksum: de64e0494b83384408a225d8c115768c12548970e05ec19479a7d63523589b3e
  status: success
  warnings: []
chunks:
- id: src_000_chunk_000
  source_id: src_000
  path: chunks/src_000_chunk_000.md
  token_count: 601
  citation:
    source_path: alerting.md
    section: Tuning
    section_path:
    - Alerting
    - Tuning
- id: src_001_chunk_000
  source_id: src_001
  path: chunks/src_001_chunk_000.md
  token_count: 706
  citation:
    source_path: api-gateway.md
    section: Observability
    section_path:
    - API Gateway Architecture
    - Observability
- id: src_002_chunk_000
  source_id: src_002
  path: chunks/src_002_chunk_000.md
  token_count: 797
  citation:
    source_path: incident-response.md
    section: Closing An Incident
    section_path:
    - Incident Response Runbook
    - Closing An Incident
- id: src_002_chunk_001
  source_id: src_002
  path: chunks/src_002_chunk_001.md
  token_count: 233
  citation:
    source_path: incident-response.md
    section: Closing An Incident
    section_path:
    - Incident Response Runbook
    - Closing An Incident
- id: src_003_chunk_000
  source_id: src_003
  path: chunks/src_003_chunk_000.md
  token_count: 772
  citation:
    source_path: onboarding.md
    section: Your First Week
    section_path:
    - Engineering Onboarding
    - Your First Week
- id: src_003_chunk_001
  source_id: src_003
  path: chunks/src_003_chunk_001.md
  token_count: 326
  citation:
    source_path: onboarding.md
    section: Where Things Live
    section_path:
    - Engineering Onboarding
    - Where Things Live
tables: []
agent:
  instructions:
  - Use citations when answering.
  - Prefer raw chunks over summaries.
  - Say not found when the corpus does not contain the answer.
```

Three things are worth pointing out.

**`section` is where the chunk ends, not where it starts.** The chunk shown in step 4
opens under "Your First Week" and its citation reads `Where Things Live`. A chunk carries
the metadata of the last block it absorbed. On a corpus like this one — short sections,
800-token chunks — a chunk routinely spans several sections, and the citation names the
last of them. Expect this when you read retrieval output.

**`checksum` is what makes re-packing cheap.** It is a SHA-256 of the file's bytes and it
keys the L1 parse cache, so an unchanged file is never re-parsed on a second run.

**`agent.instructions` ships inside the pack.** These are the ground rules intended for
whatever model consumes the pack, carried alongside the content rather than pasted into
each prompt by hand.

## 6. Building the indexes

```bash
$ agentpack index ./out
Building FTS index…
Building vector index…
[agentpack] Warning: similarity edge build failed, graph.yml left unchanged ('src_000_s00-02').
Index build complete.
```

> **Heads up — That warning is a known bug, not something you did**
>
> `agentpack index` also refreshes the `similar_to` edges in `graph.yml`. That step currently fails on packs where a similar section is not already a graph node, so no `similar_to` edges are written. Everything else — both indexes, and the rest of `graph.yml` — is built normally, and retrieval is unaffected. It is tracked as a bug; the [Concept Graph](concept-graph.md#similarity-edges) page describes how similarity edges are meant to behave.

Which produces:

```text
out/indexes/
├── lexical_index.db       # SQLite FTS5
├── vector_index.npy       # pre-normalized float32 vectors
├── vector_meta.json       # per-vector chunk metadata
├── hnsw_index.bin         # approximate nearest-neighbour index
└── vector_index.hash      # content hash, for invalidation
```

This step is optional. Skipping it just means the first `retrieve` pays the build cost
instead.

## 7. What a retrieval looks like

This is the output most people want to see before installing anything.

```bash
$ agentpack retrieve ./out "what should I do about a bad release during an incident" --top-k 3
Searching for 'what should I do about a bad release during an incident' in ./out using hybrid mode...

1. incident-response.md, Closing An Incident
   chunk: chunks/src_002_chunk_000.md
   tokens: 797
   score: 0.03

2. onboarding.md, Where Things Live
   chunk: chunks/src_003_chunk_001.md
   tokens: 326
   score: 0.03

3. incident-response.md, Closing An Incident
   chunk: chunks/src_002_chunk_001.md
   tokens: 233
   score: 0.02
```

Read a result line by line:

| Line | Meaning |
|---|---|
| `incident-response.md, Closing An Incident` | The citation: source file, then the chunk's section. Add `, page 12` for paged formats and `, rows 1-50` for CSVs. |
| `chunk: chunks/src_002_chunk_000.md` | Where the text is. Open this file, or pull it from `manifest.yml`. |
| `tokens: 797` | What it costs to put in a prompt. Sum these to get the context budget for the whole answer — 1,356 tokens here, against roughly 3,400 for the entire corpus. |
| `score: 0.03` | Ranking only. See the note below. |

**The CLI prints citations, not text.** It is a debugging tool for checking *which*
chunks come back, not a way to read them. To get the text, open the `chunk:` path or use
[the Python API](#8-calling-it-from-python).

**Hybrid scores are small and clustered, and that is normal.** Hybrid mode fuses the
lexical and vector rankings with Reciprocal Rank Fusion, where a result's contribution is
`1 / (60 + rank)`. A first-place result scores about `0.016` from one ranker. These numbers
are ordinal — they say which result ranked higher, not how good it is. Do not threshold on
them, and do not compare them against scores from another mode.

### The same query in each mode

`--mode fts` is keyword matching over SQLite FTS5, with BM25-derived scores. It first tries
all terms as an `AND`; if that matches nothing it retries as an `OR` to preserve recall:

```bash
$ agentpack retrieve ./out "escalation unacknowledged page" --top-k 2 --mode fts
Searching for 'escalation unacknowledged page' in ./out using fts mode...

1. alerting.md, Tuning
   chunk: chunks/src_000_chunk_000.md
   tokens: 601
   score: 3.15
```

One result, not the two requested — nothing else in the corpus contains these terms. Asking
for `--top-k 5` would not manufacture five results.

`--mode vector` is embedding similarity, scored as cosine in `[0, 1]`:

```bash
$ agentpack retrieve ./out "how do I get VPN access" --top-k 2 --mode vector
Searching for 'how do I get VPN access' in ./out using vector mode...

1. onboarding.md, Your First Week
   chunk: chunks/src_003_chunk_000.md
   tokens: 772
   score: 0.62

2. onboarding.md, Where Things Live
   chunk: chunks/src_003_chunk_001.md
   tokens: 326
   score: 0.56
```

The phrase "VPN access" never appears as a unit in the corpus — the text says "a VPN
certificate". Vector search finds the right chunk anyway, because it matches on meaning
rather than on the literal terms.

FTS can answer this query too, but for a different reason and less reliably. Its query is
OR-of-terms, so it matches on the common words in the question:

```bash
$ agentpack retrieve ./out "how do I get VPN access" --top-k 2 --mode fts
Searching for 'how do I get VPN access' in ./out using fts mode...

1. onboarding.md, Your First Week
   chunk: chunks/src_003_chunk_000.md
   tokens: 772
   score: 3.69

2. incident-response.md, Closing An Incident
   chunk: chunks/src_002_chunk_000.md
   tokens: 797
   score: 0.00
```

The right chunk ranks first, and a `0.00`-scoring chunk that merely shares a word like
"get" comes along with it. Hybrid mode is the default because fusing the two lists keeps
the lexical precision where terms match exactly and the semantic recall where they do not.

### Filtering

`--source`, `--section`, and `--page` narrow results by substring match on the citation:

```bash
$ agentpack retrieve ./out "routing" --top-k 2 --source alerting
Searching for 'routing' in ./out using hybrid mode...

1. alerting.md, Tuning
   chunk: chunks/src_000_chunk_000.md
   tokens: 601
   score: 0.03
```

Without the filter, `api-gateway.md` ranks first — it has its own "Routing" section, and
on this query it beats the one in `alerting.md`.

### When nothing matches

```bash
$ agentpack retrieve ./out "kubernetes helm chart" --top-k 3 --mode fts
Searching for 'kubernetes helm chart' in ./out using fts mode...
No results found.
```

Empty is a real answer, and the exit code is still `0`.

## 8. Calling it from Python

`search_pack` returns a list of dicts, and unlike the CLI it includes the chunk text in
`content`:

```python
from agentpack.retrieve import search_pack

results = search_pack(
    "./out",
    "what should I do about a bad release during an incident",
    top_k=2,
    mode="hybrid",          # "hybrid" | "vector" | "fts"
    source_filter=None,     # substring match on the source file name
    section_filter=None,    # substring match on citation.section
    page_filter=None,       # exact page number
)

for r in results:
    print(r["citation"]["source_path"], "→", r["token_count"], "tokens")
    print(r["content"][:200])
```

One result, verbatim:

```json
{
  "chunk_id": "src_002_chunk_000",
  "source_id": "src_002",
  "path": "chunks/src_002_chunk_000.md",
  "token_count": 797,
  "citation": {
    "source_path": "incident-response.md",
    "section": "Closing An Incident",
    "section_path": [
      "Incident Response Runbook",
      "Closing An Incident"
    ]
  },
  "score": 0.03225806451612903,
  "norm_score": 0.0,
  "content": "Incident Response Runbook\n\nThis runbook covers what to do between the moment an alert fires and the moment\nthe incident is closed. It assumes you are the primary on-call engineer and\nthat you have never run an incident before.\n\nSeverity Levels\n\n..."
}
```

`score` is the raw fusion score that the CLI rounds to two places.

`norm_score` means something different in each mode, so read it carefully:

| Mode | What `norm_score` is |
|---|---|
| `fts` | The BM25 score min-max rescaled across the FTS results, so the best is `1.0`. |
| `vector` | The cosine score itself — identical to `score`. |
| `hybrid` | Carried over from whichever ranker produced the row, and **not** recomputed after fusion. It does not track the fused ranking. |

In the result above, the rank-1 chunk has `norm_score` `0.0` while the rank-2 chunk has
`1.0`. That is not a display quirk — in hybrid mode the field mixes two incomparable
scales and should be ignored. Rank by position in the list, or by `score` within a single
mode.

## 9. The knowledge map

`map.yml` is the navigation tree: `corpus → document → section → chunk`. An agent reads it
to decide *where* to look before pulling any chunk. Here is the `alerting.md` portion,
verbatim:

```yaml
map_version: 1
pack:
  name: docs_example_corpus
  generated_at: '2026-09-21T22:16:10.891275+00:00'
  manifest: manifest.yml
corpus:
  summary: An unowned alert is a bug in the service definition, and Routing The API
    gateway matches an incoming request against a route table and forwards If a bad
    release is the cause, roll it back through the deployment pipeline.
  stats:
    documents: 4
    sections: 21
    tables: 0
    chunks: 6
documents:
- source_id: src_000
  path: alerting.md
  title: Alerting
  status: success
  pages: null
  summary: An unowned alert is a bug in the service definition, and
  stats:
    sections: 4
    tables: 0
    chunks: 1
  sections:
  - node_id: src_000_s00
    title: Alerting
    pages: null
    has_tables: false
    keyphrases:
    - Alerting This document
    - document describes
    - routed
    - alerts are defined
    - Alerting
    - defined
    gist: Alerting This document describes how alerts are defined, routed, and tuned.
    chunk_ids: []
    nodes:
    - node_id: src_000_s00-01
      title: Routing
      pages: null
      has_tables: false
      keyphrases:
      - alerting system
      - alerting system routes
      - alerting system notifies
      - Routing The alerting
      - alerting system stops
      - service ownership
      gist: An unowned alert is a bug in the service definition, and
      chunk_ids: []
      nodes: []
    - node_id: src_000_s00-02
      title: Tuning
      # ...
      chunk_ids:
      - src_000_chunk_000
      nodes: []
```

`pages: null` throughout because Markdown has no pages. `chunk_ids` is empty on most
sections and populated on the one where the chunk ended — the same "chunk ends here"
rule from step 5, seen from the other side.

The `summary` and `gist` fields are extractive: TextRank picks the most central existing
sentence rather than writing a new one, which is why they sometimes break mid-clause
(`"...service definition, and"`). No LLM is involved, and the same corpus always produces
the same map. See [Knowledge Map](knowledge-map.md).

## 10. The concept graph

`graph.yml` describes how the four documents relate to each other. The full file for this
corpus:

```yaml
graph_version: 1
pack:
  name: docs_example_corpus
  generated_at: '2026-09-21T22:16:11.223796+00:00'
  manifest: manifest.yml
params:
  enabled: true
  df_cap: 0.3
  min_docs: 2
  similarity_threshold: 0.8
nodes:
- { id: c_alerting_system,     kind: concept,  label: alerting system,          doc: null,    community: 1 }
- { id: c_deployment_pipeline, kind: concept,  label: Deployment Pipeline,      doc: null,    community: 2 }
- { id: src_000,               kind: document, label: alerting.md,              doc: null,    community: 3 }
- { id: src_001,               kind: document, label: api-gateway.md,           doc: null,    community: 4 }
- { id: src_002,               kind: document, label: incident-response.md,     doc: null,    community: 0 }
- { id: src_003,               kind: document, label: onboarding.md,            doc: null,    community: 0 }
- { id: src_000_s00,           kind: section,  label: Alerting,                 doc: src_000, community: 3 }
- { id: src_000_s00-01,        kind: section,  label: Routing,                  doc: src_000, community: 1 }
- { id: src_001_s00,           kind: section,  label: API Gateway Architecture, doc: src_001, community: 4 }
- { id: src_002_s00,           kind: section,  label: Incident Response Runbook, doc: src_002, community: 0 }
- { id: src_002_s00-01,        kind: section,  label: When An Alert Fires,      doc: src_002, community: 1 }
- { id: src_002_s00-02,        kind: section,  label: The Deployment Pipeline,  doc: src_002, community: 2 }
- { id: src_003_s00,           kind: section,  label: Engineering Onboarding,   doc: src_003, community: 0 }
- { id: src_003_s00-01,        kind: section,  label: Deployment Basics,        doc: src_003, community: 2 }
edges:
- { source: src_000,        target: src_000_s00,           relation: contains,   basis: structural }
- { source: src_000_s00-01, target: c_alerting_system,     relation: mentions,   basis: keyphrase }
- { source: src_001,        target: src_001_s00,           relation: contains,   basis: structural }
- { source: src_002,        target: src_002_s00,           relation: contains,   basis: structural }
- { source: src_002,        target: src_003,               relation: references, basis: structural }
- { source: src_002_s00-01, target: c_alerting_system,     relation: mentions,   basis: keyphrase }
- { source: src_002_s00-02, target: c_deployment_pipeline, relation: mentions,   basis: keyphrase }
- { source: src_003,        target: src_002,               relation: references, basis: structural }
- { source: src_003,        target: src_003_s00,           relation: contains,   basis: structural }
- { source: src_003_s00-01, target: c_deployment_pipeline, relation: mentions,   basis: keyphrase }
communities:
- { id: 0, label: incident-response.md, size: 4 }
- { id: 1, label: alerting system,      size: 3 }
- { id: 2, label: Deployment Pipeline,  size: 3 }
- { id: 3, label: alerting.md,          size: 2 }
- { id: 4, label: api-gateway.md,       size: 2 }
```

(The node, edge, and community entries are shown in YAML flow style for width; the file on
disk writes them as block lists.)

Two concepts were promoted out of every keyphrase in `map.yml`. The two `references` edges
are the Markdown links from step 1, one in each direction. `api-gateway.md` has a
`contains` edge and nothing else — no concept it shares, no document linking to it.

And the report, rendered from the same data:

```bash
$ cat out/reports/graph_report.md
```

```markdown
# Corpus Concept Graph Report for 'docs_example_corpus'
Generated at: 2026-09-21T22:16:11.223796+00:00

## Statistics
- **Documents:** 4
- **Concepts:** 2
- **Communities:** 5

## Top Concepts
- **alerting system** (2 mention(s))
- **Deployment Pipeline** (2 mention(s))

## Bridge Concepts
- No bridge concepts found.

## Isolated Documents
- api-gateway.md
```

**`api-gateway.md` is isolated, and that is the interesting result.** The corpus discusses
the API gateway constantly, but every discussion is inside `api-gateway.md` itself. No
other document links to it and no promoted concept reaches it. For a four-file handbook
that is fine. For a corpus you are about to hand an agent, an isolated document is the
cheapest available signal that something is off-topic or that the document connecting it
to everything else is missing.

Why "API gateway" itself did not become a concept — a document repeating its own title is
not evidence of a corpus-wide topic — is worked through in
[Concept Graph](concept-graph.md#why-api-gateway-is-not-a-concept).

## 11. Audit and validate

`audit` reports extraction problems and size statistics:

```bash
$ agentpack audit ./out
Auditing pack at ./out...
# AgentPack Audit Report for 'docs_example_corpus'
Generated at: 2026-09-21T22:16:10.891275+00:00

## Statistics
- **Files Processed:** 4
- **Total Chunks:** 6
- **Total Tables:** 0
- **Total Tokens:** 3435
- **Largest Chunk:** 797 tokens (ID: src_002_chunk_000)

## Extraction Warnings
- No extraction warnings.

Audit report generated.
```

On a corpus with scanned PDFs or empty files, "Extraction Warnings" is where they surface.

`validate` checks structural integrity — every chunk file exists, every id in `map.yml`
and `graph.yml` resolves:

```bash
$ agentpack validate ./out
Validating pack at ./out...
Pack validation successful.
```

A failure lists each problem and exits `1`:

```text
Validation failed with errors:
- Chunk file missing: chunks/src_002_chunk_001.md
```

## Citations from PDFs and CSVs

This corpus is all Markdown, so its citations carry no page numbers. Formats that have
them add the field automatically. A chunk from a PDF:

```yaml
- id: src_004_chunk_001
  source_id: src_004
  path: chunks/src_004_chunk_001.md
  token_count: 800
  citation:
    source_path: carc-claim-adjustment-reason-codes.pdf
    section: Claim Adjustment Reason Codes (CARC)
    section_path:
    - Claim Adjustment Reason Codes (CARC)
    page: 1
```

and a chunk from a CSV, which carries a row range instead of a page:

```yaml
- id: src_002_chunk_000
  source_id: src_002
  path: chunks/src_002_chunk_000.md
  token_count: 800
  citation:
    source_path: medicare-payment-value-of-care-IL.csv
    row_range:
    - 1
    - 50
```

Those extra fields flow straight through to the CLI, which renders them as
`report.pdf, page 12, Balance Sheets` and `data.csv, rows 1-50`.

PDFs also produce a `tables/` directory that this corpus does not have — each extracted
table written out as a standalone Markdown file, so a table never gets sliced in half by a
chunk boundary.

## Where to go next

- [CLI Reference](cli-reference.md) — every command and flag
- [Architecture & Internals](architecture.md) — how parsing, chunking, and indexing work
- [Knowledge Map](knowledge-map.md) — the full `map.yml` schema
- [Concept Graph](concept-graph.md) — concept promotion, communities, tuning
- [Corpus Explorer UI](corpus-explorer-ui.md) — the same pack, explored visually
