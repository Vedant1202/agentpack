from typing import List, Dict

def check_evidence_match(result: Dict, gold_evidence: List[Dict]) -> bool:
    """Checks if a retrieval result matches ANY of the gold evidence criteria."""
    if not gold_evidence:
        return False
        
    for gold in gold_evidence:
        gold_file = gold.get("file")
        gold_section = gold.get("section")
        
        # Determine the file path of the retrieved result.
        # Baselines will just return 'path', AgentPack returns it inside 'citation'.
        res_file = result.get("path")
        if "citation" in result:
            res_file = result["citation"].get("source_path", result.get("path"))
            
        if gold_file and res_file and gold_file != res_file:
            continue
            
        if gold_section and "citation" in result:
            res_section = result["citation"].get("section")
            if res_section != gold_section:
                continue
                
        # If it reached here, it matches the file and section (if provided)
        return True
        
    return False

def calculate_mrr(results: List[Dict], gold_evidence: List[Dict]) -> float:
    for i, res in enumerate(results):
        if check_evidence_match(res, gold_evidence):
            return 1.0 / (i + 1)
    return 0.0

def calculate_hit_at_k(results: List[Dict], gold_evidence: List[Dict], k: int) -> bool:
    for res in results[:k]:
        if check_evidence_match(res, gold_evidence):
            return True
    return False

def calculate_citation_precision(results: List[Dict], gold_evidence: List[Dict]) -> float:
    if not results:
        return 0.0
    correct = sum(1 for res in results if check_evidence_match(res, gold_evidence))
    return correct / len(results)
