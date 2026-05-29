# AgentPack CLI Reference

The AgentPack CLI provides several commands to manage, validate, and query your context packs.

## Core Commands

### `agentpack pack`
Pack documents into an agent-friendly context pack.

```bash
agentpack pack <input_dir> --out <output_dir> [OPTIONS]
```
- `<input_dir>`: The directory containing your raw documents (`.txt`, `.md`, `.csv`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`).
- `--out`: The output directory where the pack will be generated.
- `--include`: Include only files matching these glob patterns (comma-separated).
- `-i, --ignore, --exclude`: Additional glob patterns to exclude.
- `--no-gitignore`: Don't use `.gitignore` or `.agentpackignore` rules for filtering files.
- `--no-default-patterns`: Don't apply built-in ignore patterns (e.g. `.git`, `node_modules`).
- `--include-hidden`: Include hidden files and directories.
- `--remove-empty-lines`: Automatically strip blank lines from text and markdown files to save tokens.
- `--fast`: Fast mode — use PyMuPDF for PDFs instead of Docling, and skip HNSW index build. Best for quick iteration on small corpora.
- `--verbose`: Enable detailed debug logging.
- `--quiet`: Suppress all console output except errors.

> **Deprecated:** `--fast-pdf` is an alias for `--fast` and will be removed in a future release. Use `--fast` instead.

#### Config file (`agentpack.toml`)

Pack settings can be stored in an `agentpack.toml` file in `<input_dir>`. CLI flags take precedence over config values.

```toml
[pack]
chunk_max_tokens = 800    # max tokens per chunk (default: 800)
chunk_overlap    = 0.15   # overlap fraction between chunks (default: 0.15)
fast             = false  # use fast mode (default: false)
remove_empty_lines = false
include = []              # glob patterns to include
exclude = ["*.log"]       # glob patterns to exclude
```

### `agentpack index`
Pre-build FTS and vector indexes for a compiled pack. Running this before the first `retrieve` avoids paying the index-build cost at query time.

```bash
agentpack index <pack_dir>
```

The command is idempotent — if the pack content hasn't changed since the last build, both indexes are reused without rebuilding.

### `agentpack audit`
Generates an audit report for a context pack, highlighting extraction warnings (e.g., empty files, PDFs with no readable text) and statistics.

```bash
agentpack audit <pack_dir>
```

### `agentpack retrieve`
Retrieves top-k evidence chunks from a pack using hybrid search (SQLite FTS5 + HNSW vector index, fused with RRF).

```bash
agentpack retrieve <pack_dir> "<query>" --top-k 5 --mode hybrid
```
- `<query>`: The search term.
- `--top-k`: Number of results to return (default: 5).
- `--mode`: Search mode — `hybrid` (default), `vector`, or `fts`.
- `--source`: Filter results to chunks whose `source_id` contains this string (substring match).
- `--section`: Filter results to chunks whose `citation.section` contains this string (substring match).
- `--page`: Filter results to chunks from this page number.

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
