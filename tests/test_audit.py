import yaml
from pathlib import Path

from agentpack.audit import audit_pack


def _write_manifest(pack_dir: Path, sources):
    (pack_dir / "reports").mkdir(exist_ok=True)
    manifest = {
        "pack": {"name": "test_pack", "generated_at": "2026-01-01T00:00:00Z"},
        "sources": sources,
        "chunks": [],
        "tables": [],
    }
    with open(pack_dir / "manifest.yml", "w") as f:
        yaml.dump(manifest, f)


def _warning(source_id, wtype, message="something happened"):
    return {"source_id": source_id, "type": wtype, "message": message}


def test_audit_missing_manifest(tmp_path):
    report = audit_pack(str(tmp_path))
    assert report.startswith("Error: Manifest not found")


def test_audit_no_warnings(tmp_path):
    _write_manifest(tmp_path, [{"id": "src_000", "warnings": []}])
    report = audit_pack(str(tmp_path))
    assert "No extraction warnings." in report
    assert "###" not in report  # no type sections when there's nothing to group


def test_audit_groups_by_type_with_counts(tmp_path):
    _write_manifest(tmp_path, [
        {"id": "src_000", "warnings": [
            _warning("src_000", "hidden_text", "Page 1 contains concealed content"),
            _warning("src_000", "hidden_text", "Page 3 contains concealed content"),
        ]},
        {"id": "src_001", "warnings": [
            _warning("src_001", "unicode_smuggling", "Block src_001_p0 contains a zero-width character"),
        ]},
    ])
    report = audit_pack(str(tmp_path))
    assert "### hidden_text (2)" in report
    assert "### unicode_smuggling (1)" in report
    assert "Source src_000: Page 1 contains concealed content" in report
    # The old `[type]` bracket is redundant now that type is the section header.
    assert "[hidden_text]" not in report


def test_audit_priority_types_listed_first(tmp_path):
    """parse_error/import_error must appear before other types in the report,
    regardless of what order sources/warnings appear in the manifest."""
    _write_manifest(tmp_path, [
        {"id": "src_000", "warnings": [
            _warning("src_000", "hidden_text"),
            _warning("src_000", "unicode_smuggling"),
        ]},
        {"id": "src_001", "warnings": [_warning("src_001", "parse_error", "Failed to parse")]},
    ])
    report = audit_pack(str(tmp_path))
    parse_error_pos = report.index("### parse_error")
    hidden_text_pos = report.index("### hidden_text")
    unicode_pos = report.index("### unicode_smuggling")
    assert parse_error_pos < hidden_text_pos
    assert parse_error_pos < unicode_pos


def test_audit_both_priority_types_ordered_before_others(tmp_path):
    _write_manifest(tmp_path, [
        {"id": "src_000", "warnings": [
            _warning("src_000", "hidden_text"),
            _warning("src_000", "import_error", "docling not installed"),
            _warning("src_000", "parse_error", "Failed to parse"),
        ]},
    ])
    report = audit_pack(str(tmp_path))
    parse_error_pos = report.index("### parse_error")
    import_error_pos = report.index("### import_error")
    hidden_text_pos = report.index("### hidden_text")
    assert parse_error_pos < hidden_text_pos
    assert import_error_pos < hidden_text_pos


def test_audit_non_priority_types_sorted_alphabetically(tmp_path):
    # Manifest order is deliberately reverse-alphabetical to prove the report
    # doesn't just preserve source/manifest order for non-priority types.
    _write_manifest(tmp_path, [
        {"id": "src_000", "warnings": [
            _warning("src_000", "unicode_smuggling"),
            _warning("src_000", "low_text_density"),
            _warning("src_000", "hidden_text"),
        ]},
    ])
    report = audit_pack(str(tmp_path))
    hidden_pos = report.index("### hidden_text")
    low_pos = report.index("### low_text_density")
    unicode_pos = report.index("### unicode_smuggling")
    assert hidden_pos < low_pos < unicode_pos


def test_audit_statistics_section_unaffected(tmp_path):
    """Regression guard: the grouping change only touches the warnings
    section — Statistics rendering must be exactly as before."""
    (tmp_path / "reports").mkdir(exist_ok=True)
    manifest = {
        "pack": {"name": "test_pack", "generated_at": "2026-01-01T00:00:00Z"},
        "sources": [{"id": "src_000", "warnings": []}],
        "chunks": [{"id": "c1", "token_count": 42}, {"id": "c2", "token_count": 100}],
        "tables": [{"id": "t1"}],
    }
    with open(tmp_path / "manifest.yml", "w") as f:
        yaml.dump(manifest, f)

    report = audit_pack(str(tmp_path))
    assert "**Files Processed:** 1" in report
    assert "**Total Chunks:** 2" in report
    assert "**Total Tables:** 1" in report
    assert "**Total Tokens:** 142" in report
    assert "**Largest Chunk:** 100 tokens (ID: c2)" in report


def test_audit_writes_report_file(tmp_path):
    _write_manifest(tmp_path, [{"id": "src_000", "warnings": [_warning("src_000", "hidden_text")]}])
    audit_pack(str(tmp_path))
    report_path = tmp_path / "reports" / "validation_report.md"
    assert report_path.exists()
    assert "### hidden_text (1)" in report_path.read_text()
