import json
import shutil
import yaml
try:
    import requests
except ImportError:
    requests = None
from pathlib import Path
from typing import List, Dict, Optional

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

DOCBENCH_DRIVE_URL = "https://drive.google.com/drive/folders/1yxhF1lFF2gKeTNc8Wh0EyBdMT3M4pDYr"


def _resolve_docbench_data(data_dir: Optional[str]) -> Optional[Path]:
    """
    Locate the raw DocBench `data/` directory (downloaded from Google Drive).

    Resolution order:
      1. Explicit `data_dir` argument
      2. $DOCBENCH_DATA_DIR environment variable
      3. ./benchmarks/docbench_raw/data  (and ./benchmarks/docbench_raw)

    A valid directory contains one sub-folder per document, each holding a
    `<folder>_qa.jsonl` and a single `*.pdf`. Returns None if not found.
    """
    import os

    candidates = []
    if data_dir:
        candidates.append(Path(data_dir))
    if os.environ.get("DOCBENCH_DATA_DIR"):
        candidates.append(Path(os.environ["DOCBENCH_DATA_DIR"]))
    candidates.append(Path("benchmarks/docbench_raw/data"))
    candidates.append(Path("benchmarks/docbench_raw"))

    for cand in candidates:
        if not cand.is_dir():
            continue
        # A "data" root has document sub-folders containing *_qa.jsonl files.
        has_doc_folders = any(
            (sub / f"{sub.name}_qa.jsonl").exists()
            for sub in cand.iterdir() if sub.is_dir()
        )
        if has_doc_folders:
            return cand
    return None


def slice_docbench(output_dir: str, sample_size: int = 30, data_dir: str = None):
    """
    Slices the DocBench dataset (Zou et al., 2024) into the AgentPack eval format.

    DocBench is a heterogeneous, multi-domain corpus (Academia, Finance,
    Government, Law, News) of real PDFs with gold answers — a better stress test
    for FTS AND-precision and hybrid fusion than the homogeneous FinanceBench.

    Unlike FinanceBench, DocBench is distributed via Google Drive rather than
    HuggingFace, so this reads a locally-downloaded `data/` directory. Download
    it once from the Drive link below, then point this slicer at it via the
    `data_dir` argument or the $DOCBENCH_DATA_DIR environment variable.

    To mirror FinanceBench (one question per document), we take the first QA
    pair from each sampled document. Documents are sampled evenly across the
    folder listing to spread coverage across whatever domain ordering exists.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    corpus_dir = out_path / "corpus"
    corpus_dir.mkdir(exist_ok=True)

    data_root = _resolve_docbench_data(data_dir)
    if data_root is None:
        print(
            "Error: DocBench raw data not found.\n"
            f"  1. Download the dataset from: {DOCBENCH_DRIVE_URL}\n"
            "  2. Unzip it so document folders live under ./benchmarks/docbench_raw/data/\n"
            "     (each folder must contain a <folder>_qa.jsonl and one *.pdf), or\n"
            "  3. Pass --data-dir / set $DOCBENCH_DATA_DIR to that directory."
        )
        return

    # One sub-folder per document; sort numerically when folder names are ints.
    def _sort_key(p: Path):
        return (0, int(p.name)) if p.name.isdigit() else (1, p.name)

    folders = sorted(
        [d for d in data_root.iterdir() if d.is_dir()
         and (d / f"{d.name}_qa.jsonl").exists() and list(d.glob("*.pdf"))],
        key=_sort_key,
    )

    if not folders:
        print(f"Error: No valid DocBench document folders found in {data_root}.")
        return

    # Sample evenly across the listing to avoid clustering on a single domain.
    if len(folders) <= sample_size:
        selected = folders
    else:
        step = len(folders) / sample_size
        selected = [folders[int(i * step)] for i in range(sample_size)]

    print(f"Slicing {len(selected)} documents from DocBench ({data_root})...")

    queries: Dict[str, str] = {}
    gold_evidence: Dict[str, list] = {}
    gold_answers: Dict[str, str] = {}

    for folder in selected:
        qa_file = folder / f"{folder.name}_qa.jsonl"
        pdf_src = list(folder.glob("*.pdf"))[0]

        # First non-empty QA line (mirror FinanceBench: one question per doc).
        first_qa = None
        with open(qa_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    first_qa = json.loads(line)
                    break
        if not first_qa or not first_qa.get("question"):
            continue

        # Copy the PDF into the corpus under a collision-free name; the same
        # basename is recorded in gold_evidence so Hit@k file-matching works.
        dest_name = f"{folder.name}_{pdf_src.name}"
        shutil.copy(pdf_src, corpus_dir / dest_name)

        q_id = f"db_{folder.name}"
        queries[q_id] = first_qa["question"]
        gold_evidence[q_id] = [{"file": dest_name, "section": None}]
        gold_answers[q_id] = first_qa.get("answer", "")

    with open(out_path / "queries.yml", "w", encoding="utf-8") as f:
        yaml.dump(queries, f, allow_unicode=True)
    with open(out_path / "gold_evidence.yml", "w", encoding="utf-8") as f:
        yaml.dump(gold_evidence, f, allow_unicode=True)
    # DocBench ships real gold answers; persist them for generative eval.
    with open(out_path / "gold_answers.yml", "w", encoding="utf-8") as f:
        yaml.dump(gold_answers, f, allow_unicode=True)

    print(f"DocBench slicing complete: {len(queries)} queries over {len(queries)} documents.")


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
