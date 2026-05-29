"""
End-to-end round-trip regression test.

Asserts that the pack→index→retrieve pipeline preserves page citations
and that PDF table blocks are written to tables/.
"""
import json
import pytest
import tempfile
from pathlib import Path

from agentpack.pack import write_pack
from agentpack.retrieve import search_fts

FIXTURES = Path(__file__).parent / "fixtures"


def test_pack_retrieve_round_trip(tmp_path):
    """Pack the PDF+Markdown fixtures then retrieve and assert page + table citations."""
    pytest.importorskip("docling", reason="docling not installed")

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    out_dir = tmp_path / "pack"

    # Copy fixtures into the temp corpus
    import shutil
    shutil.copy(FIXTURES / "sample.pdf", corpus_dir / "sample.pdf")
    shutil.copy(FIXTURES / "sample.md", corpus_dir / "sample.md")

    write_pack(
        input_dir=str(corpus_dir),
        output_dir=str(out_dir),
        fast_pdf=False,
        quiet=True,
    )

    # 1. At least one chunk from the PDF carries a page citation.
    results = search_fts(str(out_dir), "AgentPack", top_k=10)
    assert results, "FTS returned no results"
    pages = [r["citation"].get("page") for r in results if r["citation"].get("page")]
    assert pages, (
        "No result has citation.page set — page numbers were lost during parsing. "
        "This should be fixed by Task 1.1 (structured-tree parse)."
    )

    # 2. At least one table file should be present from the PDF's table on page 2.
    table_files = list((out_dir / "tables").glob("*"))
    assert table_files, (
        "tables/ directory is empty — PDF table blocks not emitted. "
        "This should be fixed by Task 1.2 (emit table blocks + populate manifest)."
    )
