import yaml
import time
from pathlib import Path
from agentpack.pack import write_pack
from agentpack.retrieve import search_pack
from agentpack.eval.metrics import calculate_hit_at_k, calculate_mrr, calculate_citation_precision
from agentpack.eval.baselines import raw_file_search, naive_chunk_search

def run_eval(benchmark_dir: str):
    base = Path(benchmark_dir)
    queries_path = base / "queries.yml"
    gold_path = base / "gold_evidence.yml"
    corpus_dir = base / "corpus"
    
    if not all(p.exists() for p in [queries_path, gold_path, corpus_dir]):
        return "Error: Missing queries.yml, gold_evidence.yml, or corpus/ directory."
        
    with open(queries_path, "r", encoding="utf-8") as f:
        queries = yaml.safe_load(f)
    with open(gold_path, "r", encoding="utf-8") as f:
        gold = yaml.safe_load(f)
        
    pack_dir = base / "agentpack_output"
    if not pack_dir.exists():
        write_pack(str(corpus_dir), str(pack_dir))
        
    results = {
        "Raw File": {"hits_at_3": 0, "mrr": 0.0, "citation_prec": 0.0, "total_tokens": 0},
        "Naive Chunk": {"hits_at_3": 0, "mrr": 0.0, "citation_prec": 0.0, "total_tokens": 0},
        "AgentPack (FTS)": {"hits_at_3": 0, "mrr": 0.0, "citation_prec": 0.0, "total_tokens": 0},
        "AgentPack (Vector)": {"hits_at_3": 0, "mrr": 0.0, "citation_prec": 0.0, "total_tokens": 0},
        "AgentPack (Hybrid)": {"hits_at_3": 0, "mrr": 0.0, "citation_prec": 0.0, "total_tokens": 0},
    }
    
    num_queries = len(queries)
    if num_queries == 0:
        return "Error: No queries found."
    
    try:
        from tqdm import tqdm
        query_items = list(tqdm(queries.items(), desc="Evaluating Queries", total=num_queries))
    except ImportError:
        query_items = list(queries.items())

    for q_id, q_text in query_items:
        expected = gold.get(q_id, [])
        
        # Baselines
        raw_res = raw_file_search(corpus_dir, q_text, top_k=3)
        results["Raw File"]["hits_at_3"] += int(calculate_hit_at_k(raw_res, expected, 3))
        results["Raw File"]["mrr"] += calculate_mrr(raw_res, expected)
        results["Raw File"]["citation_prec"] += calculate_citation_precision(raw_res, expected)
        results["Raw File"]["total_tokens"] += sum(r.get("token_count", 0) for r in raw_res)
        
        naive_res = naive_chunk_search(corpus_dir, q_text, top_k=3)
        results["Naive Chunk"]["hits_at_3"] += int(calculate_hit_at_k(naive_res, expected, 3))
        results["Naive Chunk"]["mrr"] += calculate_mrr(naive_res, expected)
        results["Naive Chunk"]["citation_prec"] += calculate_citation_precision(naive_res, expected)
        results["Naive Chunk"]["total_tokens"] += sum(r.get("token_count", 0) for r in naive_res)
        
        # AgentPack Modes
        for mode_name, mode_flag in [("AgentPack (FTS)", "fts"), ("AgentPack (Vector)", "vector"), ("AgentPack (Hybrid)", "hybrid")]:
            ap_res = search_pack(str(pack_dir), q_text, top_k=3, mode=mode_flag)
            results[mode_name]["hits_at_3"] += int(calculate_hit_at_k(ap_res, expected, 3))
            results[mode_name]["mrr"] += calculate_mrr(ap_res, expected)
            results[mode_name]["citation_prec"] += calculate_citation_precision(ap_res, expected)
            results[mode_name]["total_tokens"] += sum(r.get("token_count", 0) for r in ap_res)
            
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
