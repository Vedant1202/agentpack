# Core API Reference

## Quick start

The two calls most people need. `write_pack` compiles a directory into a pack;
`search_pack` queries one and, unlike the CLI, returns the chunk text inline.

```python
from agentpack.pack import write_pack
from agentpack.retrieve import search_pack

write_pack(input_dir="./examples/docs_example_corpus", output_dir="./out")

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
    cite = r["citation"]
    print(f"{cite['source_path']} — {cite.get('section', '')} ({r['token_count']} tokens)")
    print(r["content"][:200])
```

`search_pack` returns a list of dicts shaped like this:

```json
{
  "chunk_id": "src_002_chunk_000",
  "source_id": "src_002",
  "path": "chunks/src_002_chunk_000.md",
  "token_count": 797,
  "citation": {
    "source_path": "incident-response.md",
    "section": "Closing An Incident",
    "section_path": ["Incident Response Runbook", "Closing An Incident"]
  },
  "score": 0.03225806451612903,
  "norm_score": 0.0,
  "content": "Incident Response Runbook\n\nThis runbook covers what to do between..."
}
```

`citation` gains `page` for paged formats and `row_range` for CSVs. `score` is
mode-dependent (RRF sum, BM25, or cosine) and ordinal only. `norm_score` is meaningful in
`fts` and `vector` mode but not in `hybrid` — see
[A Worked Example](../worked-example.md#8-calling-it-from-python).

An empty list means no match; it is not an error.

## Pack
::: agentpack.pack

## Retrieve
::: agentpack.retrieve

## Chunker
::: agentpack.chunker

## Mapper
::: agentpack.mapper

## Enrich
::: agentpack.enrich

## Models
::: agentpack.models

## Audit & Validate
::: agentpack.audit
::: agentpack.validate

## Scanner
::: agentpack.scanner
