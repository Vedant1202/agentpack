import os
import json
import yaml
from pathlib import Path
from tqdm import tqdm
from google import genai
from pydantic import BaseModel, Field

from agentpack.eval.baselines import raw_file_search, naive_chunk_search
from agentpack.retrieve import search_pack

class JudgeScore(BaseModel):
    correctness_score: int = Field(description="0-5. How well the answer matches the facts of the gold standard.")
    faithfulness_score: int = Field(description="0-5. Did the model rely ONLY on the provided context? 5 means no hallucinations.")
    answer_relevance_score: int = Field(description="0-5. Does the answer directly address the user's specific question?")
    context_relevance_score: int = Field(description="0-5. Did the retrieved context actually contain the answer to the question?")
    reasoning: str = Field(description="Brief explanation of the scores.")

def run_generation_eval(benchmark_dir: str, generation_model: str, judge_model: str):
    if not os.environ.get("GEMINI_API_KEY"):
        return "Error: GEMINI_API_KEY environment variable is not set."
        
    client = genai.Client() # Uses GEMINI_API_KEY automatically
    
    base = Path(benchmark_dir)
    queries_path = base / "queries.yml"
    gold_path = base / "gold_evidence.yml"
    corpus_dir = base / "corpus"
    pack_dir = base / "agentpack_output"
    
    if not all(p.exists() for p in [queries_path, gold_path, corpus_dir, pack_dir]):
        return "Error: Missing required benchmark files. Please run 'agentpack eval' first to ensure vectors exist."
    
    with open(queries_path, "r", encoding="utf-8") as f:
        queries = yaml.safe_load(f)
    with open(gold_path, "r", encoding="utf-8") as f:
        gold = yaml.safe_load(f)
        
    results_out = {}
    
    modes = [
        ("Raw File", raw_file_search),
        ("Naive Chunk", naive_chunk_search),
        ("AgentPack (Vector)", lambda c, q, k: search_pack(str(pack_dir), q, top_k=k, mode="vector"))
    ]
    
    judgments = {m[0]: {"correctness": 0, "faithfulness": 0, "answer_rel": 0, "context_rel": 0, "count": 0} for m in modes}
    
    for q_id, q_text in tqdm(queries.items(), desc="Generating & Judging Answers"):
        expected_list = gold.get(q_id, [])
        expected = expected_list[0] if expected_list else "No gold answer."
        results_out[q_id] = {"question": q_text, "expected": expected, "modes": {}}
        
        for mode_name, search_func in modes:
            # 1. Retrieve Context
            if mode_name == "AgentPack (Vector)":
                chunks = search_func(corpus_dir, q_text, 3)
            else:
                chunks = search_func(corpus_dir, q_text, top_k=3)
                
            context_text = "\n\n---\n\n".join([c.get("content", "") for c in chunks])
            
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
                "judge_reasoning": reasoning
            }
            judgments[mode_name]["correctness"] += c_score
            judgments[mode_name]["faithfulness"] += f_score
            judgments[mode_name]["answer_rel"] += ar_score
            judgments[mode_name]["context_rel"] += cr_score
            judgments[mode_name]["count"] += 1
            
    # Output JSON
    with open(base / "generation_results.json", "w", encoding="utf-8") as f:
        json.dump(results_out, f, indent=2)
        
    # Output Report
    report = [
        f"# AgentPack Generative Eval: {base.name}",
        f"Queries: {len(queries)}",
        f"Generation Model: {generation_model}",
        f"Judge Model: {judge_model}\n",
        "| Mode | Correctness (0-5) | Faithfulness (0-5) | Answer Relevance (0-5) | Context Relevance (0-5) |",
        "|---|---|---|---|---|"
    ]
    
    for mode in judgments:
        count = judgments[mode]["count"]
        if count > 0:
            avg_c = judgments[mode]["correctness"] / count
            avg_f = judgments[mode]["faithfulness"] / count
            avg_ar = judgments[mode]["answer_rel"] / count
            avg_cr = judgments[mode]["context_rel"] / count
        else:
            avg_c = avg_f = avg_ar = avg_cr = 0
            
        report.append(f"| {mode} | {avg_c:.2f} | {avg_f:.2f} | {avg_ar:.2f} | {avg_cr:.2f} |")
        
    report_text = "\n".join(report)
    with open(base / "generation_report.md", "w", encoding="utf-8") as f:
        f.write(report_text)
        
    return report_text
