from typer.testing import CliRunner
from agentpack.cli import app
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

runner = CliRunner()

def test_cli_pack_help():
    result = runner.invoke(app, ["pack", "--help"])
    assert result.exit_code == 0
    assert "include-hidden" in result.stdout
    assert "remove-empty-lin" in result.stdout

def test_cli_pack_execution(mock_txt_file):
    with tempfile.TemporaryDirectory() as temp_in, tempfile.TemporaryDirectory() as temp_out:
        in_path = Path(temp_in)
        out_path = Path(temp_out)
        
        with open(in_path / "doc1.txt", "w") as f:
            f.write(mock_txt_file.read_text())
            
        result = runner.invoke(app, ["pack", str(in_path), "--out", str(out_path), "--quiet"])
        
        assert result.exit_code == 0
        assert (out_path / "manifest.yml").exists()

def test_cli_audit_execution(mock_txt_file):
    with tempfile.TemporaryDirectory() as temp_in, tempfile.TemporaryDirectory() as temp_out:
        in_path = Path(temp_in)
        out_path = Path(temp_out)
        
        with open(in_path / "doc1.txt", "w") as f:
            f.write(mock_txt_file.read_text())
            
        # Pack first
        runner.invoke(app, ["pack", str(in_path), "--out", str(out_path), "--quiet"])
        
        # Then audit
        result = runner.invoke(app, ["audit", str(out_path)])
        
        assert result.exit_code == 0
        assert "Audit Report" in result.stdout

def test_cli_validate():
    with tempfile.TemporaryDirectory() as d:
        out_path = Path(d)
        result = runner.invoke(app, ["validate", str(out_path)])
        assert result.exit_code == 1 # Manifest not found
        
        # Write valid manifest
        with open(out_path / "manifest.yml", "w") as f:
            yaml.dump({
                "pack": {"name": "test"},
                "sources": [],
                "chunks": [],
                "tables": []
            }, f)
        result = runner.invoke(app, ["validate", str(out_path)])
        assert result.exit_code == 0
        assert "Pack validation successful" in result.stdout

@patch("agentpack.cli.search_pack")
def test_cli_retrieve(mock_search_pack):
    mock_search_pack.return_value = [
        {"path": "c1.json", "token_count": 10, "score": 0.9, "source_id": "s1", "citation": {"source_path": "a.txt"}}
    ]
    result = runner.invoke(app, ["retrieve", "fake_dir", "query"])
    assert result.exit_code == 0
    assert "c1.json" in result.stdout
    assert "a.txt" in result.stdout

@patch("agentpack.cli.search_pack")
def test_cli_retrieve_empty(mock_search_pack):
    mock_search_pack.return_value = []
    result = runner.invoke(app, ["retrieve", "fake_dir", "query"])
    assert result.exit_code == 0
    assert "No results found" in result.stdout

@patch("agentpack.cli.run_eval")
def test_cli_eval(mock_run_eval):
    mock_run_eval.return_value = "Eval Output"
    result = runner.invoke(app, ["eval", "fake_dir"])
    assert result.exit_code == 0
    assert "Eval Output" in result.stdout

@patch("agentpack.cli.run_eval")
def test_cli_eval_error(mock_run_eval):
    mock_run_eval.return_value = "Error: Something went wrong"
    result = runner.invoke(app, ["eval", "fake_dir"])
    assert result.exit_code == 1
    assert "Error:" in result.stdout

@patch("agentpack.eval.generation.run_generation_eval")
def test_cli_gen_eval(mock_run_gen):
    mock_run_gen.return_value = "Gen Eval Output"
    result = runner.invoke(app, ["gen-eval", "fake_dir"])
    assert result.exit_code == 0
    assert "Gen Eval Output" in result.stdout

@patch("agentpack.eval.benchmarks.slice_financebench")
def test_cli_prep_benchmark(mock_slice):
    result = runner.invoke(app, ["prep-benchmark", "--dataset", "financebench", "--sample-size", "5"])
    assert result.exit_code == 0
    assert "Preparation complete" in result.stdout
    mock_slice.assert_called_once()

def test_cli_prep_benchmark_unsupported():
    result = runner.invoke(app, ["prep-benchmark", "--dataset", "unknown"])
    assert result.exit_code == 1
    assert "Unsupported dataset: unknown" in result.stdout

@patch("uvicorn.run")
def test_cli_ui(mock_run):
    result = runner.invoke(app, ["ui", "fake_dir", "--port", "8080"])
    assert result.exit_code == 0
    assert "Starting AgentPack Corpus Intelligence" in result.stdout
    mock_run.assert_called_once()
