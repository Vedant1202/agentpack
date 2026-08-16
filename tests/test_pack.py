import os
import pytest
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


def test_write_pack_html_end_to_end(tmp_path):
    """An .html file must be scanned, parsed via DoclingParser, chunked, and recorded with type 'html'."""
    pytest.importorskip("docling")

    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "guide.html").write_text(
        "<html><body>"
        "<h1>User Guide</h1>"
        "<p>This guide explains how to install and configure the product.</p>"
        "<h2>Installation</h2>"
        "<p>Run the installer and follow the prompts to complete setup.</p>"
        "</body></html>"
    )
    out_dir = tmp_path / "out"

    write_pack(str(in_dir), str(out_dir), quiet=True)

    with open(out_dir / "manifest.yml") as f:
        manifest = yaml.safe_load(f)

    assert len(manifest["sources"]) == 1
    source = manifest["sources"][0]
    assert source["type"] == "html"
    assert source["status"] == "success"

    html_chunks = [c for c in manifest["chunks"] if c["source_id"] == source["id"]]
    assert len(html_chunks) > 0
    for chunk in html_chunks:
        assert (out_dir / chunk["path"]).exists()


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


def test_failed_parse_marked_in_manifest(tmp_path):
    """A file whose parser returns a parse_error warning must appear as 'failed' in the manifest."""
    from agentpack.parsers.text_parser import TextParser
    from agentpack.models import SourceDocument, ExtractionWarning

    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "bad.txt").write_text("irrelevant")
    out_dir = tmp_path / "out"

    def broken_parse(self, file_path, source_id):
        return SourceDocument(
            source_id=source_id,
            path=file_path.name,
            type="txt",
            checksum="abc",
            blocks=[],
            warnings=[ExtractionWarning(source_id=source_id, type="parse_error", message="simulated failure")],
        )

    with patch.object(TextParser, "parse", broken_parse):
        write_pack(str(in_dir), str(out_dir), quiet=True)

    with open(out_dir / "manifest.yml") as f:
        manifest = yaml.safe_load(f)

    source = manifest["sources"][0]
    assert source["status"] == "failed"
    assert any(w["type"] == "parse_error" for w in source["warnings"])


def test_failed_parse_not_cached(tmp_path):
    """A file whose parser returns a parse_error must not be cached so the next pack retries it."""
    from agentpack.parsers.text_parser import TextParser
    from agentpack.models import SourceDocument, ExtractionWarning

    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "flaky.txt").write_text("hello")
    out_dir = tmp_path / "out"

    call_count = [0]
    original_parse = TextParser.parse

    def flaky_parse(self, file_path, source_id):
        call_count[0] += 1
        if call_count[0] == 1:
            return SourceDocument(
                source_id=source_id,
                path=file_path.name,
                type="txt",
                checksum="abc",
                blocks=[],
                warnings=[ExtractionWarning(source_id=source_id, type="parse_error", message="transient error")],
            )
        return original_parse(self, file_path, source_id)

    with patch.object(TextParser, "parse", flaky_parse):
        write_pack(str(in_dir), str(out_dir), quiet=True)   # first: fails, must not cache
        write_pack(str(in_dir), str(out_dir), quiet=True)   # second: retries, succeeds

    assert call_count[0] == 2, (
        f"parser.parse called {call_count[0]} times; expected 2 (failed result must not be cached)"
    )

    with open(out_dir / "manifest.yml") as f:
        manifest = yaml.safe_load(f)

    assert manifest["sources"][0]["status"] == "success"


def test_dangling_symlink_does_not_abort_the_pack(tmp_path):
    """F2: a dangling symlink must not crash the whole pack -- it must be recorded as a failed
    source with a parse_error warning, and the good file's chunks must still exist."""
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "good.md").write_text("# Good\n\n" + ("Real content here. " * 20))
    (in_dir / "ghost.md").symlink_to(in_dir / "nope.md")  # target never created -- broken
    out_dir = tmp_path / "out"

    write_pack(str(in_dir), str(out_dir), quiet=True)  # RED today: raises FileNotFoundError

    with open(out_dir / "manifest.yml") as f:
        manifest = yaml.safe_load(f)

    sources_by_path = {s["path"]: s for s in manifest["sources"]}
    assert set(sources_by_path) == {"good.md", "ghost.md"}, "both sources must be listed"

    ghost = sources_by_path["ghost.md"]
    assert ghost["status"] == "failed"
    assert any(w["type"] == "parse_error" for w in ghost["warnings"])

    good = sources_by_path["good.md"]
    assert good["status"] == "success"
    good_chunks = [c for c in manifest["chunks"] if c["source_id"] == good["id"]]
    assert len(good_chunks) > 0
    for chunk in good_chunks:
        assert (out_dir / chunk["path"]).exists()


def test_unreadable_file_does_not_abort_the_pack(tmp_path):
    """F2, PermissionError variant: monkeypatched for determinism (real chmod-based permission
    tests are flaky when running as root, e.g. in CI containers)."""
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "good.md").write_text("# Good\n\n" + ("Real content here. " * 20))
    (in_dir / "locked.txt").write_text("unreadable")
    out_dir = tmp_path / "out"

    real_open = open
    locked_path = str(in_dir / "locked.txt")

    def guarded_open(file, *args, **kwargs):
        if str(file) == locked_path:
            raise PermissionError(f"[Errno 13] Permission denied: '{file}'")
        return real_open(file, *args, **kwargs)

    with patch("builtins.open", side_effect=guarded_open):
        write_pack(str(in_dir), str(out_dir), quiet=True)

    with open(out_dir / "manifest.yml") as f:
        manifest = yaml.safe_load(f)

    sources_by_path = {s["path"]: s for s in manifest["sources"]}
    assert sources_by_path["locked.txt"]["status"] == "failed"
    assert any(w["type"] == "parse_error" for w in sources_by_path["locked.txt"]["warnings"])
    assert sources_by_path["good.md"]["status"] == "success"


def test_output_dir_nested_in_input_is_not_self_ingested(tmp_path):
    """F15: an output dir nested inside the input dir (e.g. corpus/pack) must never be scanned
    as input -- otherwise a re-run ingests its own previous chunks/report and grows every time."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "doc.md").write_text("# Doc\n\n" + ("Real content here. " * 20))
    out_dir = corpus / "pack"

    write_pack(str(corpus), str(out_dir), quiet=True)  # first pack
    write_pack(str(corpus), str(out_dir), quiet=True)  # RED today: ingests its own output

    with open(out_dir / "manifest.yml") as f:
        manifest = yaml.safe_load(f)

    source_paths = {s["path"] for s in manifest["sources"]}
    assert source_paths == {"doc.md"}, (
        f"second pack's sources must be exactly the original corpus files: {source_paths}"
    )


def test_remove_empty_lines_flag_is_part_of_cache_key(tmp_path):
    """F11: the L1 cache key omitted remove_empty_lines, so toggling the flag on an
    already-cached file silently served the untransformed cached blocks."""
    from agentpack.pack import _parse_one

    doc_path = tmp_path / "doc.md"
    doc_path.write_text("# Title\n\nLine one.\n\nLine two.\n")
    cache_dir = tmp_path / ".cache"

    first = _parse_one(doc_path, "src_000", fast_pdf=False, remove_empty_lines=False, cache_dir=cache_dir)
    assert len(first.blocks) == 3, (
        "fixture must produce 3 separate blocks pre-fix (heading + 2 paragraphs)"
    )

    second = _parse_one(doc_path, "src_000", fast_pdf=False, remove_empty_lines=True, cache_dir=cache_dir)
    assert len(second.blocks) == 2, (
        f"remove_empty_lines=True served stale cached blocks ({len(second.blocks)}, "
        f"expected 2 after compression)"
    )


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


def test_cache_hit_remaps_path_and_block_ids(tmp_path):
    """F3: a cache HIT only remapped doc.source_id, leaving the doc's own `path` and its
    blocks' `block_id`s (which bake in source_id as a prefix, e.g. 'src_000_table_0') pointing
    at the OLD pack's identity when the corpus reshuffles between packs -- e.g. a file renamed
    but with identical bytes. Same precedent/pattern as test_trust_warnings_correct_source_id_on_cache_hit."""
    from agentpack.pack import _parse_one

    csv_content = "name,value\nfoo,1\nbar,2\n"
    dir_a = tmp_path / "corpus_a"
    dir_a.mkdir()
    (dir_a / "report_a.csv").write_text(csv_content)
    cache_dir = tmp_path / ".cache"

    first = _parse_one(dir_a / "report_a.csv", "src_000", fast_pdf=False,
                        remove_empty_lines=False, cache_dir=cache_dir)
    first_tables = [b for b in first.blocks if b.type == "table"]
    assert first_tables, "fixture must produce at least one table block"
    assert first.path == "report_a.csv"

    # Same bytes, renamed into a fresh dir -> same content hash -> cache HIT below.
    dir_b = tmp_path / "corpus_b"
    dir_b.mkdir()
    (dir_b / "report_b.csv").write_text(csv_content)

    second = _parse_one(dir_b / "report_b.csv", "src_005", fast_pdf=False,
                         remove_empty_lines=False, cache_dir=cache_dir)

    assert second.source_id == "src_005"
    assert second.path == "report_b.csv", (
        f"cache hit left a stale path: {second.path!r}, expected 'report_b.csv'"
    )
    second_tables = [b for b in second.blocks if b.type == "table"]
    assert second_tables, "cache hit must still carry the table block(s)"
    for b in second_tables:
        assert b.block_id.startswith("src_005"), (
            f"table block_id {b.block_id!r} carries a stale source_id namespace"
        )
        assert b.source_id == "src_005"


def test_trust_warnings_correct_source_id_on_cache_hit(tmp_path):
    """Regression guard for docs/specs/0002-ingestion-trust-layer.md §2: trust
    warnings must always carry the CURRENT source_id, even when the underlying
    SourceDocument is served from the L1 parse cache under a different index
    than the run that originally populated it — e.g. because the corpus
    changed shape between packs and this file's position shifted. This is the
    exact bug class pack.py:55's doc.source_id reassignment does NOT fully fix
    for warnings embedded before caching; trust warnings sidestep it entirely
    by being computed fresh, after the cache block, on every call."""
    import fitz
    from agentpack.pack import _parse_one

    pdf_path = tmp_path / "doc.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "hidden instruction", render_mode=3)
    doc.save(pdf_path)
    doc.close()

    cache_dir = tmp_path / ".cache"

    # First "pack": this file is assigned src_000 — cache miss, populates the cache.
    first = _parse_one(pdf_path, "src_000", fast_pdf=True, remove_empty_lines=False, cache_dir=cache_dir)
    first_hidden = [w for w in first.warnings if w.type == "hidden_text"]
    assert len(first_hidden) == 1
    assert first_hidden[0].source_id == "src_000"

    # Second "pack": same file (same content -> same cache key), but the
    # corpus reshuffled so it's now assigned a different index. Cache HIT.
    second = _parse_one(pdf_path, "src_005", fast_pdf=True, remove_empty_lines=False, cache_dir=cache_dir)
    second_hidden = [w for w in second.warnings if w.type == "hidden_text"]

    assert second.source_id == "src_005"
    assert len(second_hidden) == 1
    assert second_hidden[0].source_id == "src_005", (
        "trust warning carried a stale source_id from the cached run instead "
        "of the current one"
    )
    # Same underlying finding both times (deterministic, recomputed fresh).
    assert second_hidden[0].page == first_hidden[0].page
    assert second_hidden[0].message == first_hidden[0].message
