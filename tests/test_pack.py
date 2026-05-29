import os
import yaml
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from agentpack.pack import write_pack

def test_write_pack(mock_txt_file, mock_md_file, mock_csv_file):
    # Instead of scanning the whole repo, we point it to the temp folder 
    # where the fixtures live. But the fixtures are in different temp paths.
    # Let's create a specific temp folder and copy our mocks in there.
    with tempfile.TemporaryDirectory() as temp_in, tempfile.TemporaryDirectory() as temp_out:
        in_path = Path(temp_in)
        out_path = Path(temp_out)
        
        # Copy mock contents
        with open(in_path / "doc1.txt", "w") as f:
            f.write(mock_txt_file.read_text())
        with open(in_path / "doc2.md", "w") as f:
            f.write(mock_md_file.read_text())
        with open(in_path / "doc3.csv", "w") as f:
            f.write(mock_csv_file.read_text())
            
        write_pack(input_dir=str(in_path), output_dir=str(out_path), quiet=True)
        
        # Assert directory structure
        assert (out_path / "manifest.yml").exists()
        assert (out_path / "chunks").is_dir()
        assert (out_path / "tables").is_dir()
        assert (out_path / "reports" / "pack_report.md").exists()
        
        # Assert manifest contents
        with open(out_path / "manifest.yml") as f:
            manifest = yaml.safe_load(f)
            
        assert "sources" in manifest
        assert len(manifest["sources"]) == 3
        
        assert "chunks" in manifest
        assert len(manifest["chunks"]) > 0
        
        # Assert tables were written (stored as .md — content is markdown table format)
        tables = list((out_path / "tables").glob("*.md"))
        assert len(tables) == 1


def test_pack_version_in_manifest(tmp_path):
    """manifest.pack.version must equal the installed package version, not '0.1.0'."""
    from importlib.metadata import version as pkg_version
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "doc.txt").write_text("hello world")
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)
    with open(out_dir / "manifest.yml") as f:
        manifest = yaml.safe_load(f)
    assert manifest["pack"]["version"] == pkg_version("agent-context-packager")


def test_incremental_pack_skips_unchanged(tmp_path):
    """Re-packing an unchanged file must hit L1 cache (parser.parse not called twice)."""
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "doc.txt").write_text("hello world unchanged")
    out_dir = tmp_path / "out"

    call_count = [0]
    real_parse = None

    from agentpack.parsers.text_parser import TextParser

    original_parse = TextParser.parse

    def counting_parse(self, *args, **kwargs):
        call_count[0] += 1
        return original_parse(self, *args, **kwargs)

    with patch.object(TextParser, "parse", counting_parse):
        write_pack(str(in_dir), str(out_dir), quiet=True)  # first pack
        write_pack(str(in_dir), str(out_dir), quiet=True)  # second pack (unchanged)

    assert call_count[0] == 1, (
        f"parser.parse called {call_count[0]} times; expected 1 (cache hit on second pack)"
    )
