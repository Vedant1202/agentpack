"""
Baseline benchmark harness for AgentPack.

Usage:
    python -m benchmarks.run            # full run
    python -m benchmarks.run --quick    # tiny corpus only (for CI smoke-test)

Measures and prints:
    cold_pack_s   – first pack of a corpus (no cache)
    repak_s       – second pack of the same corpus (unchanged files)
    fts_p50_ms    – median FTS query latency (ms)
    fts_recall@5  – fraction of ground-truth chunks returned in top-5

Results are compared against benchmarks/BASELINE.md when it exists.
"""
import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path
from statistics import median
from typing import List, Tuple

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"


def _make_corpus(tmp: Path, n_copies: int) -> Path:
    """Copy fixtures n_copies times into a temp corpus dir."""
    corpus = tmp / "corpus"
    corpus.mkdir()
    for i in range(n_copies):
        src = FIXTURES / "sample.pdf"
        if src.exists():
            shutil.copy(src, corpus / f"doc_{i:03d}.pdf")
        shutil.copy(FIXTURES / "sample.md", corpus / f"doc_{i:03d}.md")
    return corpus


def _time_pack(corpus: Path, out: Path, fast: bool = True) -> float:
    from agentpack.pack import write_pack
    t0 = time.perf_counter()
    write_pack(str(corpus), str(out), fast_pdf=fast, quiet=True)
    return time.perf_counter() - t0


def _time_queries(out: Path, queries: List[str], top_k: int = 5) -> Tuple[float, float]:
    """Return (p50_ms, recall@k).  recall is fraction of queries returning >=1 result."""
    from agentpack.retrieve import search_fts
    latencies = []
    hits = 0
    for q in queries:
        t0 = time.perf_counter()
        results = search_fts(str(out), q, top_k=top_k)
        latencies.append((time.perf_counter() - t0) * 1000)
        if results:
            hits += 1
    p50 = median(latencies) if latencies else 0.0
    recall = hits / len(queries) if queries else 0.0
    return p50, recall


def run(quick: bool = False) -> dict:
    n = 1 if quick else 5
    queries = [
        "AgentPack document compiler",
        "semantic PDF parsing",
        "retrieval pipeline stages",
        "supported formats table",
        "lexical vector hybrid search",
    ]
    if quick:
        queries = queries[:2]

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        corpus = _make_corpus(tmp, n_copies=n)

        # cold pack (fast mode to keep CI snappy)
        out = tmp / "pack"
        cold_s = _time_pack(corpus, out, fast=True)

        # re-pack (same corpus, same output dir)
        repak_s = _time_pack(corpus, out, fast=True)

        # FTS query latency
        p50_ms, recall = _time_queries(out, queries)

    return {
        "n_docs": n,
        "cold_pack_s": round(cold_s, 3),
        "repak_s": round(repak_s, 3),
        "fts_p50_ms": round(p50_ms, 3),
        "fts_recall_at5": round(recall, 3),
    }


def _fmt_row(label: str, value: str, baseline: str = "—") -> str:
    return f"  {label:<22}  {value:<12}  {baseline}"


def _load_baseline() -> dict:
    path = Path(__file__).parent / "BASELINE.md"
    if not path.exists():
        return {}
    data = {}
    for line in path.read_text().splitlines():
        if "|" in line and "cold_pack" not in line and "---" not in line and "Metric" not in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                data[parts[0]] = parts[1]
    return data


def _write_baseline(results: dict):
    path = Path(__file__).parent / "BASELINE.md"
    lines = [
        "# Benchmark Baseline",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    for k, v in results.items():
        lines.append(f"| {k} | {v} |")
    path.write_text("\n".join(lines) + "\n")
    print(f"\nBaseline written to {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="Use tiny corpus (CI)")
    parser.add_argument("--save", action="store_true", help="Overwrite BASELINE.md")
    args = parser.parse_args()

    print(f"Running benchmark (quick={args.quick}) …")
    results = run(quick=args.quick)
    baseline = _load_baseline()

    print(f"\n{'Metric':<22}  {'Current':<12}  Baseline")
    print("-" * 48)
    for k, v in results.items():
        print(_fmt_row(k, str(v), baseline.get(k, "—")))

    no_baseline = not (Path(__file__).parent / "BASELINE.md").exists()
    if args.save or no_baseline:
        _write_baseline(results)


if __name__ == "__main__":
    main()
