# AgentPack

**AgentPack** is a document-to-agent-context compiler. 

Instead of forcing AI agents to parse messy, disparate file formats (PDFs, CSVs, Markdown, text) at runtime, AgentPack pre-compiles your unstructured knowledge base into a **Canonical Document Model**. It chunks, indexes, and surfaces highly accurate citation metadata so your agents can focus on reasoning, not parsing.

## Philosophy

Most RAG systems fail because they extract text naively. AgentPack introduces:
1. **Canonical Document Model**: A unified standard output format regardless of whether the source was a 100-page PDF or a 2-column CSV.
2. **Deterministic Metadata Tracking**: Source paths, page numbers, and semantic markdown sections are preserved into every chunk. When the agent cites "Eligibility Criteria", it's because AgentPack proved that chunk lived under `## Eligibility Criteria`.
3. **Observability**: Before an agent ever sees the context, you can `validate` the pack for integrity, `audit` it for extraction warnings, and `eval` it deterministically.

## Installation

```bash
git clone https://github.com/yourusername/agentpack.git
cd agentpack
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Quick Start

### 1. Compile a Pack
Point AgentPack at any folder containing your documents (`.txt`, `.md`, `.csv`, `.pdf`).

```bash
python3 -m agentpack pack ./my_docs --out ./agentpack-output
```
This generates the `agentpack-output` folder containing chunked markdown, raw tables, and the crucial `manifest.yml`.

### 2. Audit the Pack
Check for extraction warnings (e.g., empty files, PDFs with no readable text) and view statistics.

```bash
python3 -m agentpack audit ./agentpack-output
```

### 3. Retrieve
AgentPack comes with a built-in lightning-fast SQLite FTS5 lexical search engine to test your chunks instantly.

```bash
python3 -m agentpack retrieve ./agentpack-output "eligibility criteria" --top-k 5
```

### 4. Deterministic Eval
Benchmark AgentPack against naive chunking and raw file baselines using our evaluation harness. 
You provide a `queries.yml` and a `gold_evidence.yml`. AgentPack calculates Hit@K, MRR, and Citation Precision.

```bash
python3 -m agentpack eval ./benchmarks/my_dataset
```

## Supported Parsers
- **TXT**: Paragraph-aware splitting.
- **Markdown**: Semantic heading-aware section path tracking.
- **CSV**: Converts tabular data to Markdown tables.
- **PDF**: Accurate page-by-page PyMuPDF extraction.

## Architecture

The output pack directory looks like this:
```
agentpack-output/
├── manifest.yml           # The brain of the pack. Contains schema, sources, chunks.
├── chunks/                # Safe, agent-ready markdown files.
├── tables/                # Extracted CSV tables in standalone format.
├── indexes/               # Cached SQLite FTS5 lexical indexes.
└── reports/               # Generated audit and validation reports.
```

---
*Built with ❤️ for Agents.*
