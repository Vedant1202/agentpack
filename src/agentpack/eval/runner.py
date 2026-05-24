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
        "AgentPack": {"hits_at_3": 0, "mrr": 0.0, "citation_prec": 0.0, "total_tokens": 0},
    }
    
    num_queries = len(queries)
    if num_queries == 0:
        return "Error: No queries found."
    
    for q_id, q_text in queries.items():
        expected = gold.get(q_id, [])
        
        # Raw File
        raw_res = raw_file_search(corpus_dir, q_text, top_k=3)
        results["Raw File"]["hits_at_3"] += int(calculate_hit_at_k(raw_res, expected, 3))
        results["Raw File"]["mrr"] += calculate_mrr(raw_res, expected)
        results["Raw File"]["citation_prec"] += calculate_citation_precision(raw_res, expected)
        results["Raw File"]["total_tokens"] += sum(r.get("token_count", 0) for r in raw_res)
        
        # Naive Chunk
        naive_res = naive_chunk_search(corpus_dir, q_text, top_k=3)
        results["Naive Chunk"]["hits_at_3"] += int(calculate_hit_at_k(naive_res, expected, 3))
        results["Naive Chunk"]["mrr"] += calculate_mrr(naive_res, expected)
        results["Naive Chunk"]["citation_prec"] += calculate_citation_precision(naive_res, expected)
        results["Naive Chunk"]["total_tokens"] += sum(r.get("token_count", 0) for r in naive_res)
        
        # AgentPack
        ap_res = search_pack(str(pack_dir), q_text, top_k=3)
        results["AgentPack"]["hits_at_3"] += int(calculate_hit_at_k(ap_res, expected, 3))
        results["AgentPack"]["mrr"] += calculate_mrr(ap_res, expected)
        results["AgentPack"]["citation_prec"] += calculate_citation_precision(ap_res, expected)
        results["AgentPack"]["total_tokens"] += sum(r.get("token_count", 0) for r in ap_res)
        
    # Format report
    report = [
        f"# AgentPack Deterministic Eval: {base.name}",
        f"Queries: {num_queries}\n",
        "| Mode | Hit@3 | MRR | Citation Prec | Context Tokens |",
        "|---|---|---|---|---|"
    ]
    
    for mode, metrics in results.items():
        hit3 = metrics["hits_at_3"] / num_queries
        mrr = metrics["mrr"] / num_queries
        prec = metrics["citation_prec"] / num_queries
        tok = metrics["total_tokens"] / num_queries
        report.append(f"| {mode} | {hit3:.2f} | {mrr:.2f} | {prec:.2f} | {tok:.1f} |")
        
    report_text = "\n".join(report)
    with open(base / "retrieval_report.md", "w", encoding="utf-8") as f:
        f.write(report_text)
        
    return report_text
