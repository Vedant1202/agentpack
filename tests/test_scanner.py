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

def test_scanner_includes_docling_formats():
    """Office/HTML formats handled by DoclingParser must survive the extension filter."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        for name in ["a.docx", "b.pptx", "c.xlsx", "d.html", "e.htm", "f.exe"]:
            (temp_path / name).touch()

        names = [f.name for f in scan_directory(temp_dir)]

        assert "a.docx" in names
        assert "b.pptx" in names
        assert "c.xlsx" in names
        assert "d.html" in names
        assert "e.htm" in names
        assert "f.exe" not in names

def test_scanner_sorts_despite_reversed_os_walk_order(monkeypatch, tmp_path):
    """F13: forces a non-alphabetical order directly from os.walk (rather than relying on a
    particular filesystem's natural order, which may already happen to look sorted) -- this
    makes the test meaningful on any filesystem. os.walk yields each directory's own files
    before recursing into subdirectories, so the canonical order isn't a naive lexicographic
    sort of full relative paths -- it's whatever the scanner's OWN sort produces. Assert
    invariance instead: reversing os.walk's input order must not change the output at all."""
    for name in ["c.md", "a.md", "b.md"]:
        (tmp_path / name).write_text("x")
    (tmp_path / "zdir").mkdir()
    (tmp_path / "zdir" / "z.md").write_text("x")
    (tmp_path / "adir").mkdir()
    (tmp_path / "adir" / "y.md").write_text("x")

    canonical = [f.relative_to(tmp_path).as_posix() for f in scan_directory(str(tmp_path))]

    real_walk = os.walk

    def reversed_walk(top, *args, **kwargs):
        for root, dirs, files in real_walk(top, *args, **kwargs):
            dirs.sort(reverse=True)  # mutate in place -- os.walk reads this for descent order
            yield root, dirs, sorted(files, reverse=True)

    monkeypatch.setattr("agentpack.scanner.os.walk", reversed_walk)
    reversed_order_result = [f.relative_to(tmp_path).as_posix() for f in scan_directory(str(tmp_path))]

    assert reversed_order_result == canonical, (
        f"scan_directory output changed when the underlying os.walk order was reversed: "
        f"{reversed_order_result} != {canonical}"
    )


def test_scanner_output_is_deterministic():
    """Straight determinism check: two scans of the same tree must return an identical list."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        for name in ["z.md", "a.md", "m.txt"]:
            (temp_path / name).write_text("x")
        sub = temp_path / "sub"
        sub.mkdir()
        (sub / "nested.md").write_text("x")

        first = [f.relative_to(temp_path).as_posix() for f in scan_directory(temp_dir)]
        second = [f.relative_to(temp_path).as_posix() for f in scan_directory(temp_dir)]

        assert first == second


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
