import yaml
import time
from pathlib import Path
from agentpack.pack import write_pack
from agentpack.retrieve import search_pack
from agentpack.eval.metrics import calculate_hit_at_k, calculate_mrr, calculate_citation_precision
from agentpack.eval import baselines as _baselines
from agentpack.eval.spinner import spinner, StepLogger

def run_eval(benchmark_dir: str, include_llm_baselines: bool = False, llm_model: str = None, verbose: bool = False, skip_raw_file: bool = False):
    base = Path(benchmark_dir)
    queries_path = base / "queries.yml"
    gold_path = base / "gold_evidence.yml"
    corpus_dir = base / "corpus"

    if not all(p.exists() for p in [queries_path, gold_path, corpus_dir]):
        return "Error: Missing queries.yml, gold_evidence.yml, or corpus/ directory."

    # Phases: load → build pack → run retrieval → aggregate/report
    log = StepLogger(total_phases=4, verbose=verbose)

    log.phase("Loading benchmark queries and gold evidence")
    with open(queries_path, "r", encoding="utf-8") as f:
        queries = yaml.safe_load(f)
    with open(gold_path, "r", encoding="utf-8") as f:
        gold = yaml.safe_load(f)
    num_queries = len(queries) if queries else 0
    log.detail(f"Benchmark dir : {base}")
    log.detail(f"Corpus dir    : {corpus_dir}")
    log.detail(f"Loaded {num_queries} queries / {len(gold) if gold else 0} gold entries")
    if num_queries == 0:
        return "Error: No queries found."

    if llm_model:
        _baselines.LLM_BASELINE_MODEL = llm_model
        log.detail(f"LLM-in-retrieval model: {llm_model}")

    log.phase("Building AgentPack pack (parsing + chunking + indexing)")
    pack_dir = base / "agentpack_output"
    if not pack_dir.exists():
        log.detail("No existing pack found — running a full Docling parse (can take minutes on large PDFs).")
        with spinner(f"Packing corpus → {pack_dir.name}"):
            write_pack(str(corpus_dir), str(pack_dir))
    else:
        log.detail(f"Reusing existing pack at {pack_dir} (delete it to force a rebuild).")

    # Baseline strategies (registry) + AgentPack's own retrieval modes.
    baseline_modes = [
        (name, lambda q, fn=fn: fn(corpus_dir, q, top_k=3))
        for name, fn in _baselines.get_baselines(include_llm=include_llm_baselines, skip_raw_file=skip_raw_file)
    ]
    agentpack_modes = [
        (f"AgentPack ({label})", lambda q, flag=flag: search_pack(str(pack_dir), q, top_k=3, mode=flag))
        for label, flag in [("FTS", "fts"), ("Vector", "vector"), ("Hybrid", "hybrid")]
    ]
    all_modes = baseline_modes + agentpack_modes

    results = {
        name: {"hits_at_3": 0, "mrr": 0.0, "citation_prec": 0.0, "total_tokens": 0}
        for name, _ in all_modes
    }

    log.phase(f"Running retrieval — {len(all_modes)} modes × {num_queries} queries")
    log.detail("Modes: " + ", ".join(name for name, _ in all_modes))
    log.detail("Dense/reranker/LLM indexes build lazily on first use — watch for 'Building … index' bars.")

    query_items = list(queries.items())
    # One progress step per (query, mode); tqdm shows elapsed/ETA and rate.
    total_steps = num_queries * len(all_modes)
    try:
        from tqdm import tqdm
        pbar = tqdm(total=total_steps, desc="Evaluating", unit="step")
    except ImportError:
        pbar = None

    def _emit(msg):
        if pbar is not None:
            pbar.write(msg)
        else:
            print(msg)

    for q_idx, (q_id, q_text) in enumerate(query_items, start=1):
        expected = gold.get(q_id, [])

        for mode_name, search_fn in all_modes:
            if pbar is not None:
                pbar.set_postfix_str(f"q{q_idx}/{num_queries} · {mode_name[:22]}")
            t0 = time.time()
            res = search_fn(q_text)
            dt = time.time() - t0

            hit = calculate_hit_at_k(res, expected, 3)
            mrr = calculate_mrr(res, expected)
            prec = calculate_citation_precision(res, expected)
            toks = sum(r.get("token_count", 0) for r in res)

            results[mode_name]["hits_at_3"] += int(hit)
            results[mode_name]["mrr"] += mrr
            results[mode_name]["citation_prec"] += prec
            results[mode_name]["total_tokens"] += toks

            if verbose:
                top = res[0] if res else {}
                top_file = top.get("path") or (top.get("citation", {}) or {}).get("source_path", "—")
                _emit(
                    f"    · [q{q_idx:>3}/{num_queries}] {mode_name:<26} "
                    f"{'HIT ' if hit else 'miss'} top={str(top_file)[:34]:<34} "
                    f"mrr={mrr:.2f} tok={toks:<6} {dt:5.2f}s"
                )
            if pbar is not None:
                pbar.update(1)

    if pbar is not None:
        pbar.close()

    log.phase("Aggregating metrics and writing report")

    # Format report
    report = [
        f"# AgentPack Deterministic Eval: {base.name}",
        f"Queries: {num_queries}\n",
        "| Mode | Hit@3 | MRR | Citation Prec | Avg Context Tokens | Avg LLM Cost ($) |",
        "|---|---|---|---|---|---|"
    ]
    
    # Cost formula based on Gemini 3.1 Flash-Lite input cost ($0.25 per 1M tokens)
    COST_PER_MILLION = 0.25
    
    for mode, metrics in results.items():
        hit3 = metrics["hits_at_3"] / num_queries
        mrr = metrics["mrr"] / num_queries
        prec = metrics["citation_prec"] / num_queries
        avg_tok = metrics["total_tokens"] / num_queries
        avg_cost = (avg_tok / 1_000_000) * COST_PER_MILLION
        
        report.append(f"| {mode} | {hit3:.2f} | {mrr:.2f} | {prec:.2f} | {avg_tok:.1f} | ${avg_cost:.6f} |")
        
    report_text = "\n".join(report)
    with open(base / "retrieval_report.md", "w", encoding="utf-8") as f:
        f.write(report_text)
        
    return report_text
