import os
import json
import yaml
from pathlib import Path
from tqdm import tqdm
try:
    from google import genai
except ImportError:
    genai = None
from pydantic import BaseModel, Field

from agentpack.eval import baselines as _baselines
from agentpack.eval.spinner import StepLogger
from agentpack.retrieve import search_pack

class JudgeScore(BaseModel):
    correctness_score: int = Field(description="0-5. How well the answer matches the facts of the gold standard.")
    faithfulness_score: int = Field(description="0-5. Did the model rely ONLY on the provided context? 5 means no hallucinations.")
    answer_relevance_score: int = Field(description="0-5. Does the answer directly address the user's specific question?")
    context_relevance_score: int = Field(description="0-5. Did the retrieved context actually contain the answer to the question?")
    reasoning: str = Field(description="Brief explanation of the scores.")

def run_generation_eval(benchmark_dir: str, generation_model: str, judge_model: str, limit: int = None, skip_baselines: bool = False, include_llm_baselines: bool = False, verbose: bool = False, skip_raw_file: bool = False):
    if not genai:
        return "Error: google-genai package is not installed. Please install it to use gen-eval."

    if not os.environ.get("GEMINI_API_KEY"):
        return "Error: GEMINI_API_KEY environment variable is not set."

    client = genai.Client() # Uses GEMINI_API_KEY automatically

    # Phases: load → generate+judge → write report
    log = StepLogger(total_phases=3, verbose=verbose)
    log.phase("Loading benchmark queries, gold answers, and retrieval modes")

    base = Path(benchmark_dir)
    queries_path = base / "queries.yml"
    gold_path = base / "gold_evidence.yml"
    gold_answers_path = base / "gold_answers.yml"
    corpus_dir = base / "corpus"
    pack_dir = base / "agentpack_output"

    if not all(p.exists() for p in [queries_path, gold_path, corpus_dir, pack_dir]):
        return "Error: Missing required benchmark files. Please run 'agentpack eval' first to ensure vectors exist."

    with open(queries_path, "r", encoding="utf-8") as f:
        queries = yaml.safe_load(f)
    with open(gold_path, "r", encoding="utf-8") as f:
        gold = yaml.safe_load(f)
    gold_answers = {}
    if gold_answers_path.exists():
        with open(gold_answers_path, "r", encoding="utf-8") as f:
            gold_answers = yaml.safe_load(f) or {}

    results_out = {}

    # LLM-in-retrieval baselines reuse the generation model for their internal calls.
    _baselines.LLM_BASELINE_MODEL = generation_model

    baseline_modes = [] if skip_baselines else list(_baselines.get_baselines(include_llm=include_llm_baselines, skip_raw_file=skip_raw_file))
    agentpack_modes = [
        ("AgentPack (Vector)", lambda c, q, k: search_pack(str(pack_dir), q, top_k=k, mode="vector")),
        ("AgentPack (Hybrid)", lambda c, q, k: search_pack(str(pack_dir), q, top_k=k, mode="hybrid")),
    ]
    modes = baseline_modes + agentpack_modes

    judgments = {m[0]: {"correctness": 0, "faithfulness": 0, "answer_rel": 0, "context_rel": 0, "count": 0, "tokens": 0} for m in modes}

    query_items = list(queries.items())
    if limit is not None:
        query_items = query_items[:limit]

    log.detail(f"Generation model: {generation_model}  |  Judge model: {judge_model}")
    log.detail(f"Queries: {len(query_items)}" + (f" (limited from {len(queries)})" if limit is not None else ""))
    log.detail("Modes: " + ", ".join(name for name, _ in modes))

    import tiktoken
    encoder = tiktoken.get_encoding("cl100k_base")

    # One progress step per (query, mode); tqdm shows elapsed/ETA and rate.
    n_queries = len(query_items)
    log.phase(f"Generating answers and judging — {len(modes)} modes × {n_queries} queries (each step = 2 LLM calls)")
    pbar = tqdm(total=n_queries * len(modes), desc="Generating & Judging", unit="step")

    for q_idx, (q_id, q_text) in enumerate(query_items, start=1):
        expected = gold_answers.get(q_id) or str(gold.get(q_id, ["No gold answer."])[0])
        results_out[q_id] = {"question": q_text, "expected": expected, "modes": {}}

        for mode_name, search_func in modes:
            pbar.set_postfix_str(f"q{q_idx}/{n_queries} · {mode_name[:22]}")
            # 1. Retrieve Context
            if mode_name.startswith("AgentPack"):
                chunks = search_func(corpus_dir, q_text, 3)
            else:
                chunks = search_func(corpus_dir, q_text, top_k=3)
                
            context_text = "\n\n---\n\n".join([c.get("content", "") for c in chunks])
            
            # Count Tokens
            token_count = len(encoder.encode(context_text))
            judgments[mode_name]["tokens"] += token_count
            
            # 2. Generate Answer
            prompt = f"Answer the following question based ONLY on the provided context.\n\nContext:\n{context_text}\n\nQuestion:\n{q_text}"
            try:
                gen_response = client.models.generate_content(
                    model=generation_model,
                    contents=prompt
                )
                answer = gen_response.text
            except Exception as e:
                answer = f"Error generating answer: {e}"
                
            # 3. Judge Answer
            judge_prompt = f"You are an expert RAG evaluation system. Grade the provided answer across 4 metrics (0-5).\n\nQuestion: {q_text}\nGold Standard: {expected}\n\nRetrieved Context: {context_text}\n\nGenerated Answer: {answer}"
            try:
                judge_response = client.models.generate_content(
                    model=judge_model,
                    contents=judge_prompt,
                    config={"response_mime_type": "application/json", "response_schema": JudgeScore}
                )
                score_data = json.loads(judge_response.text)
                c_score = score_data.get("correctness_score", 0)
                f_score = score_data.get("faithfulness_score", 0)
                ar_score = score_data.get("answer_relevance_score", 0)
                cr_score = score_data.get("context_relevance_score", 0)
                reasoning = score_data.get("reasoning", "")
            except Exception as e:
                c_score = f_score = ar_score = cr_score = 0
                reasoning = f"Error judging: {e}"
                
            results_out[q_id]["modes"][mode_name] = {
                "answer": answer,
                "scores": {
                    "correctness": c_score,
                    "faithfulness": f_score,
                    "answer_relevance": ar_score,
                    "context_relevance": cr_score
                },
                "tokens": token_count,
                "judge_reasoning": reasoning
            }
            judgments[mode_name]["correctness"] += c_score
            judgments[mode_name]["faithfulness"] += f_score
            judgments[mode_name]["answer_rel"] += ar_score
            judgments[mode_name]["context_rel"] += cr_score
            judgments[mode_name]["count"] += 1

            if verbose:
                preview = " ".join(str(answer).split())[:70]
                pbar.write(
                    f"    · [q{q_idx:>3}/{n_queries}] {mode_name:<26} "
                    f"C{c_score} F{f_score} AR{ar_score} CR{cr_score} "
                    f"tok={token_count:<6} ans=\"{preview}…\""
                )
            pbar.update(1)

    pbar.close()

    log.phase("Writing report and per-query results JSON")

    # Output JSON
    with open(base / "generation_results.json", "w", encoding="utf-8") as f:
        json.dump(results_out, f, indent=2)
        
    # Output Report
    report = [
        f"# AgentPack Generative Eval: {base.name}",
        f"Queries: {len(query_items)}",
        f"Generation Model: {generation_model}",
        f"Judge Model: {judge_model}\n",
        "| Mode | Correctness (0-5) | Faithfulness (0-5) | Answer Relevance (0-5) | Context Relevance (0-5) | Avg Context Tokens | Avg LLM Cost ($) |",
        "|---|---|---|---|---|---|---|"
    ]
    
    for mode in judgments:
        count = judgments[mode]["count"]
        if count > 0:
            avg_c = judgments[mode]["correctness"] / count
            avg_f = judgments[mode]["faithfulness"] / count
            avg_ar = judgments[mode]["answer_rel"] / count
            avg_cr = judgments[mode]["context_rel"] / count
            avg_tokens = judgments[mode]["tokens"] / count
            avg_cost = avg_tokens * (0.25 / 1_000_000)
        else:
            avg_c = avg_f = avg_ar = avg_cr = avg_tokens = avg_cost = 0
            
        report.append(f"| {mode} | {avg_c:.2f} | {avg_f:.2f} | {avg_ar:.2f} | {avg_cr:.2f} | {avg_tokens:.1f} | ${avg_cost:.6f} |")
        
    report_text = "\n".join(report)
    with open(base / "generation_report.md", "w", encoding="utf-8") as f:
        f.write(report_text)
        
    return report_text
