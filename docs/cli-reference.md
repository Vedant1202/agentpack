# AgentPack CLI Reference

The AgentPack CLI provides several commands to manage, validate, and query your context packs.

## Core Commands

### `agentpack pack`
Pack documents into an agent-friendly context pack.

```bash
agentpack pack <input_dir> --out <output_dir>
```
- `<input_dir>`: The directory containing your raw documents (`.txt`, `.md`, `.csv`, `.pdf`).
- `--out`: The output directory where the pack will be generated.

### `agentpack audit`
Generates an audit report for a context pack, highlighting extraction warnings (e.g., empty files, PDFs with no readable text) and statistics.

```bash
agentpack audit <pack_dir>
```

### `agentpack retrieve`
Retrieves top-k evidence chunks from a pack using the built-in SQLite FTS5 lexical search engine.

```bash
agentpack retrieve <pack_dir> "<query>" --top-k 5 --mode hybrid
```
- `<query>`: The search term.
- `--top-k`: Number of results to return (default: 5).
- `--mode`: Search mode to use (`hybrid`, `vector`, or `fts`. default: `hybrid`).

### `agentpack validate`
Validates the structural integrity of a context pack, ensuring all expected files and tables exist and are properly referenced in the manifest.

```bash
agentpack validate <pack_dir>
```

## Evaluation Commands

### `agentpack eval`
Runs a deterministic evaluation benchmark against your pack using `queries.yml` and `gold_evidence.yml`. Calculates Hit@K, MRR, Citation Precision, and Context Token Savings.

```bash
agentpack eval ./benchmarks/my_dataset
```

### `agentpack gen-eval`
Evaluates Generative QA using AgentPack. This acts as a smoke test / LLM judge to verify downstream generation behavior.

```bash
agentpack gen-eval ./benchmarks/my_dataset --gen-model gemini-1.5-flash --judge-model gemini-1.5-pro --limit 10
```
- `--gen-model`: The LLM used for generation (default: `gemini-1.5-flash`).
- `--judge-model`: The LLM used for judging the answer (default: `gemini-1.5-pro`).
- `--limit`: Limit the number of queries for a quick smoke test.

### `agentpack prep-benchmark`
Downloads and slices a public dataset into a benchmark format for testing AgentPack.

```bash
agentpack prep-benchmark --dataset financebench --sample-size 10
```
- `--dataset`: Dataset to slice (e.g., `financebench`, `tatqa`, `qasper`).
- `--sample-size`: Number of documents to sample.
