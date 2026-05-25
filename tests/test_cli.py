from typer.testing import CliRunner
from agentpack.cli import app
import tempfile
from pathlib import Path

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
