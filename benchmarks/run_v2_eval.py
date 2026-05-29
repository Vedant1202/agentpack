import os
import yaml
import time
from pathlib import Path
import google.generativeai as genai
from agentpack.retrieve import search_pack

def setup_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable is not set.")
        print("Please run: export GEMINI_API_KEY='your_api_key_here'")
        exit(1)
    genai.configure(api_key=api_key)
    # Use gemini-3.1-flash-lite for fast, latest-generation evaluation
    return genai.GenerativeModel('gemini-3.1-flash-lite')

def generate_answer(model, query, retrieved_chunks):
    """Asks Gemini to answer the query based strictly on the retrieved chunks."""
    context = "\n\n---\n\n".join([f"Source: {c['path']}\n{c.get('content', '')}" for c in retrieved_chunks])
    # Note: search_pack currently doesn't return 'content' in the dict in retrieve.py, it returns path and citation.
    # We will read the actual content from the disk to give to the LLM.
    
    prompt = f"""You are a helpful AI assistant. Answer the user's question based ONLY on the provided context chunks.
If the context does not contain the answer, reply with 'I cannot answer this based on the provided context.'

Context:
{context}

Question: {query}
Answer:"""
    
    response = model.generate_content(prompt)
    return response.text.strip()

def evaluate_correctness(model, query, generated_answer, gold_answer):
    """LLM-as-a-Judge: Asks Gemini to score if the generated answer is factually equivalent to the gold answer."""
    prompt = f"""You are an expert evaluator grading an AI's answer.
Compare the Generated Answer to the Expected (Gold) Answer.
Are they factually equivalent and correct regarding the user's query?
Ignore minor wording differences. The Generated Answer must contain the core facts of the Expected Answer.

Query: {query}
Expected Answer: {gold_answer}
Generated Answer: {generated_answer}

Respond with exactly one character: '1' if correct, '0' if incorrect."""
    
    response = model.generate_content(prompt)
    score_text = response.text.strip()
    return 1 if score_text == '1' else 0

def get_raw_file_content(base_dir):
    """Reads all raw text from the corpus directory to simulate a raw-file baseline."""
    corpus_dir = Path(base_dir) / "corpus"
    full_text = ""
    for file_path in corpus_dir.glob("*"):
        if file_path.is_file() and file_path.suffix in ['.txt', '.csv']:
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    full_text += f"\n--- {file_path.name} ---\n" + f.read()
            except Exception:
                pass
    return [{"path": "raw_corpus", "content": full_text}]

def run_v2_eval(benchmark_dir):
    base = Path(benchmark_dir)
    queries_path = base / "queries.yml"
    gold_path = base / "gold_answers.yml"
    
    with open(queries_path, "r") as f:
        queries = yaml.safe_load(f)
    with open(gold_path, "r") as f:
        gold = yaml.safe_load(f)
        
    model = setup_gemini()
    
    print(f"Starting V2 Generative Evaluation on {base.name}...\n")
    
    total_queries = len(queries)
    ap_correct = 0
    ap_latency = 0.0
    base_correct = 0
    base_latency = 0.0
    
    results_log = []
    
    # Pre-load raw file content for baseline
    raw_baseline_chunks = get_raw_file_content(base)
    
    for q_id, q_text in queries.items():
        print("--------------------------------------------------")
        print(f"[{q_id}] Query: {q_text}")
        
        expected = gold.get(q_id, "")
        
        # --- BASELINE RUN ---
        print("  [BASELINE] Requesting generation with full raw files...")
        b_start = time.time()
        base_ans = generate_answer(model, q_text, raw_baseline_chunks)
        b_lat = time.time() - b_start
        base_latency += b_lat
        base_score = evaluate_correctness(model, q_text, base_ans, expected)
        base_correct += base_score
        print(f"    -> Score: {base_score} (Latency: {b_lat:.2f}s)")
        time.sleep(8) # rate limit buffer
        
        # --- AGENTPACK RUN ---
        print("  [AGENTPACK] Retrieving chunks and generating...")
        ap_start = time.time()
        
        # 1. Retrieve
        raw_results = search_pack(str(base / "agentpack_output"), q_text, top_k=3)
        
        # Hydrate chunks with actual content for the LLM
        hydrated_chunks = []
        for res in raw_results:
            chunk_file = base / "agentpack_output" / res['path']
            if chunk_file.exists():
                with open(chunk_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    hydrated_chunks.append({"path": res['path'], "content": content})
                    
        # 2. Generate
        ap_ans = generate_answer(model, q_text, hydrated_chunks)
        a_lat = time.time() - ap_start
        ap_latency += a_lat
        
        # 3. Evaluate
        ap_score = evaluate_correctness(model, q_text, ap_ans, expected)
        ap_correct += ap_score
        
        print(f"    -> Score: {ap_score} (Latency: {a_lat:.2f}s)")
        
        results_log.append(f"### Query: {q_text}\n**Baseline:** {base_ans} (Score: {base_score})\n**AgentPack:** {ap_ans} (Score: {ap_score})\n**Expected:** {expected}\n")
        
        print("  -> [Rate Limit Buffer] Sleeping for 15 seconds...\n")
        time.sleep(15)
        
    ap_acc = ap_correct / total_queries if total_queries > 0 else 0
    ap_avg_lat = ap_latency / total_queries if total_queries > 0 else 0
    base_acc = base_correct / total_queries if total_queries > 0 else 0
    base_avg_lat = base_latency / total_queries if total_queries > 0 else 0
    
    report = f"# AgentPack V2 Generative Evaluation (Side-by-Side)\n\n"
    report += f"- **Dataset:** {base.name}\n"
    report += f"- **Queries:** {total_queries}\n\n"
    report += f"| Mode | Accuracy | Avg Latency |\n"
    report += f"|---|---|---|\n"
    report += f"| Raw Baseline | {base_acc:.2f} | {base_avg_lat:.2f}s |\n"
    report += f"| AgentPack | {ap_acc:.2f} | {ap_avg_lat:.2f}s |\n\n"
    report += "## Query Details\n" + "\n".join(results_log)
    
    report_path = base / "generative_report.md"
    with open(report_path, "w") as f:
        f.write(report)
        
    print(f"Evaluation complete. AgentPack Accuracy: {ap_acc:.2f} | Baseline Accuracy: {base_acc:.2f}. Full report saved to {report_path}")

if __name__ == "__main__":
    run_v2_eval("benchmarks/test_benchmark/unified_benchmark")
