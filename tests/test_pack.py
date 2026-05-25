import os
import yaml
import tempfile
from pathlib import Path
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
        
        # Assert tables were written
        tables = list((out_path / "tables").glob("*.csv"))
        assert len(tables) == 1
