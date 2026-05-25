import tempfile
import os
from pathlib import Path
from agentpack.scanner import scan_directory

def test_scanner_ignores_hidden_and_defaults():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "valid.md").touch()
        (temp_path / ".hidden.md").touch()
        
        git_dir = temp_path / ".git"
        git_dir.mkdir()
        (git_dir / "secret.md").touch()
        
        venv_dir = temp_path / "venv"
        venv_dir.mkdir()
        (venv_dir / "lib.txt").touch()

        files = scan_directory(temp_dir)
        names = [f.name for f in files]
        
        assert "valid.md" in names
        assert ".hidden.md" not in names
        assert "secret.md" not in names
        assert "lib.txt" not in names

def test_scanner_includes_and_excludes():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        (temp_path / "app.md").touch()
        (temp_path / "docs.txt").touch()
        (temp_path / "ignore_me.md").touch()
        
        files = scan_directory(
            temp_dir,
            include_patterns=["*.md"],
            exclude_patterns=["ignore_me.md"]
        )
        names = [f.name for f in files]
        
        assert "app.md" in names
        assert "docs.txt" not in names
        assert "ignore_me.md" not in names

if __name__ == "__main__":
    test_scanner_ignores_hidden_and_defaults()
    test_scanner_includes_and_excludes()
    print("All tests passed.")
