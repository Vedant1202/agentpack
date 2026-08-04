from unittest.mock import patch

from typer.testing import CliRunner

from agentpack.cli import app
from agentpack.ui.server import build_human_readable_title

runner = CliRunner()


@patch("agentpack.retrieve.search_pack")
def test_cli_retrieve_csv_citation_shows_row_range(mock_search_pack):
    mock_search_pack.return_value = [
        {
            "path": "chunks/src_002_chunk_000.md",
            "token_count": 800,
            "score": 0.9,
            "source_id": "src_002",
            "citation": {"source_path": "payments.csv", "row_range": [1, 50]},
        }
    ]
    result = runner.invoke(app, ["retrieve", "fake_dir", "query"])
    assert result.exit_code == 0
    assert "payments.csv, rows 1-50" in result.stdout


@patch("agentpack.retrieve.search_pack")
def test_cli_retrieve_pdf_citation_unchanged(mock_search_pack):
    mock_search_pack.return_value = [
        {
            "path": "chunks/src_000_chunk_000.md",
            "token_count": 500,
            "score": 0.9,
            "source_id": "src_000",
            "citation": {"source_path": "guide.pdf", "page": 12, "section": "Billing"},
        }
    ]
    result = runner.invoke(app, ["retrieve", "fake_dir", "query"])
    assert result.exit_code == 0
    assert "guide.pdf, page 12, Billing" in result.stdout


def test_ui_title_includes_row_range():
    title = build_human_readable_title(
        "src_002", {"source_path": "payments.csv", "row_range": [51, 100]}
    )
    assert title == "payments.csv > rows 51-100"


def test_ui_title_without_row_range_unchanged():
    title = build_human_readable_title(
        "src_000", {"source_path": "guide.pdf", "section_path": ["A", "B"]}
    )
    assert title == "guide.pdf > A > B"
