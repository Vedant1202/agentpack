import pytest
import os
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from agentpack.eval.benchmarks import slice_financebench
from agentpack.eval.metrics import check_evidence_match, calculate_mrr, calculate_hit_at_k, calculate_citation_precision

# --- METRICS TESTS ---

def test_metrics_check_evidence_match():
    gold = [{"file": "docA.pdf", "section": "sec1"}]
    
    assert check_evidence_match({"citation": {"source_path": "docA.pdf", "section": "sec1"}}, gold)
    assert not check_evidence_match({"citation": {"source_path": "docB.pdf", "section": "sec1"}}, gold)
    assert not check_evidence_match({"citation": {"source_path": "docA.pdf", "section": "sec2"}}, gold)

def test_metrics_calculate_mrr():
    gold = [{"file": "docA.pdf"}]
    # Match at rank 1
    assert calculate_mrr([{"path": "docA.pdf"}], gold) == 1.0
    # Match at rank 2
    assert calculate_mrr([{"path": "docB.pdf"}, {"path": "docA.pdf"}], gold) == 0.5
    # No match
    assert calculate_mrr([{"path": "docB.pdf"}], gold) == 0.0

def test_metrics_calculate_hit_at_k():
    gold = [{"file": "docA.pdf"}]
    res = [{"path": "docB.pdf"}, {"path": "docA.pdf"}]
    
    assert not calculate_hit_at_k(res, gold, k=1)
    assert calculate_hit_at_k(res, gold, k=2)

def test_metrics_calculate_citation_precision():
    gold = [{"file": "docA.pdf"}]
    assert calculate_citation_precision([], gold) == 0.0
    assert calculate_citation_precision([{"path": "docA.pdf"}], gold) == 1.0
    assert calculate_citation_precision([{"path": "docA.pdf"}, {"path": "docB.pdf"}], gold) == 0.5

# --- BENCHMARKS TESTS ---

@patch("datasets.load_dataset")
@patch("agentpack.eval.benchmarks.requests")
def test_slice_financebench(mock_requests, mock_load_dataset, tmp_path):
    mock_ds = [
        {"doc_name": "docA", "doc_link": "http://example.com/docA.pdf", "question": "Q1", "evidence": [{"evidence_text": "E1"}]},
        {"doc_name": "docB", "doc_link": "http://example.com/docB.pdf", "question": "Q2", "evidence": [{"evidence_text": "E2"}]},
    ]
    mock_load_dataset.return_value = mock_ds
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"fake pdf content"
    mock_requests.get.return_value = mock_response
    
    slice_financebench(str(tmp_path), sample_size=2)
    
    assert (tmp_path / "queries.yml").exists()
    assert (tmp_path / "gold_evidence.yml").exists()
    assert (tmp_path / "corpus" / "docA.pdf").exists()

# We will skip generation.py and runner.py tests as they likely use other unavailable classes.
# But let's add a basic test for runner.py if we can mock it simply.
@patch("agentpack.eval.runner.search_pack")
@patch("agentpack.eval.runner.write_pack")
def test_run_eval(mock_write_pack, mock_search, tmp_path):
    from agentpack.eval.runner import run_eval

    mock_search.return_value = [{"citation": {"source_path": "docA.pdf"}, "path": "c1.md", "token_count": 10}]

    bench_dir = tmp_path / "benchmark"
    bench_dir.mkdir()
    (bench_dir / "corpus").mkdir()
    (bench_dir / "corpus" / "docA.txt").write_text("some content")

    with open(bench_dir / "queries.yml", "w") as f:
        yaml.dump({"q1": "What is foo?"}, f)

    with open(bench_dir / "gold_evidence.yml", "w") as f:
        yaml.dump({"q1": [{"file": "docA.pdf"}]}, f)

    report = run_eval(str(bench_dir))

    assert report is not None
    assert not report.startswith("Error")
    assert (bench_dir / "retrieval_report.md").exists()
