import json
import yaml
try:
    import requests
except ImportError:
    requests = None
from pathlib import Path
from typing import List, Dict

def slice_financebench(output_dir: str, sample_size: int = 10):
    """
    Slices the FinanceBench dataset into a format usable by AgentPack eval.
    """
    try:
        from datasets import load_dataset
    except ImportError:
        print("Please install datasets: pip install datasets")
        return
        
    if not requests:
        print("Please install requests: pip install requests")
        return
        
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    corpus_dir = out_path / "corpus"
    corpus_dir.mkdir(exist_ok=True)
    
    queries = {}
    gold_evidence = {}
    
    print(f"Loading PatronusAI/financebench dataset...")
    ds = load_dataset("PatronusAI/financebench", split="train")
    
    # We want unique documents to avoid downloading the same PDF multiple times
    # and to ensure a diverse haystack.
    selected_indices = []
    seen_docs = set()
    
    for i, row in enumerate(ds):
        doc_name = row.get("doc_name", "")
        if doc_name not in seen_docs:
            seen_docs.add(doc_name)
            selected_indices.append(i)
        if len(selected_indices) >= sample_size:
            break
            
    print(f"Slicing {sample_size} examples from FinanceBench...")
    
    for i in selected_indices:
        row = ds[i]
        q_id = f"fb_{i}"
        doc_name = row["doc_name"]
        doc_link = row["doc_link"]
        question = row["question"]
        evidence_list = row.get("evidence", [])
        evidence_text = evidence_list[0].get("evidence_text", "") if evidence_list else ""
        
        # Download the PDF if it doesn't exist
        pdf_path = corpus_dir / f"{doc_name}.pdf"
        if not pdf_path.exists():
            print(f"Downloading {doc_name}.pdf...")
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                response = requests.get(doc_link, headers=headers, timeout=20)
                if response.status_code == 200:
                    with open(pdf_path, "wb") as f:
                        f.write(response.content)
                else:
                    print(f"Failed to download {doc_link} (Status {response.status_code})")
                    continue
            except Exception as e:
                print(f"Failed to download {doc_link}: {e}")
                continue
                
        # Save query and gold evidence
        queries[q_id] = question
        gold_evidence[q_id] = [{
            "file": f"{doc_name}.pdf",
            "section": None # We don't have exact section mapping easily, so we match on file
        }]
        
    with open(out_path / "queries.yml", "w") as f:
        yaml.dump(queries, f)
        
    with open(out_path / "gold_evidence.yml", "w") as f:
        yaml.dump(gold_evidence, f)
        
    print("FinanceBench slicing complete.")

def slice_tatqa(output_dir: str, sample_size: int = 10):
    """
    Slices the TAT-QA dataset for tabular testing.
    """
    pass

def slice_qasper(output_dir: str, sample_size: int = 10):
    """
    Slices the QASPER dataset for long academic paper retrieval.
    """
    pass
