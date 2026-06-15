"""Phase A3/A4 — CLI surface (`--no-map`, `agentpack map`) and validate-on-map."""
import yaml
from pathlib import Path
from typer.testing import CliRunner

from agentpack.cli import app

runner = CliRunner()


def _md_corpus(tmp_path: Path) -> Path:
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "guide.md").write_text(
        "# Guide\n\n" + ("Intro paragraph here. " * 20) +
        "\n\n## Setup\n\n" + ("Setup steps here. " * 20)
    )
    return in_dir


# --- A3: CLI ---

def test_pack_no_map_cli_flag(tmp_path):
    in_dir = _md_corpus(tmp_path)
    out = tmp_path / "out"
    res = runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--no-map", "--quiet"])
    assert res.exit_code == 0, res.output
    assert (out / "manifest.yml").exists()
    assert not (out / "map.yml").exists()


def test_map_command_rebuilds_from_existing_pack(tmp_path):
    in_dir = _md_corpus(tmp_path)
    out = tmp_path / "out"
    runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--quiet"])

    map_path = out / "map.yml"
    assert map_path.exists()
    map_path.unlink()

    res = runner.invoke(app, ["map", str(out), "--quiet"])
    assert res.exit_code == 0, res.output
    assert map_path.exists()

    m = yaml.safe_load(map_path.read_text())
    assert m["map_version"] == 1
    assert m["documents"][0]["source_id"] == "src_000"


def test_map_command_missing_manifest_errors(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    res = runner.invoke(app, ["map", str(empty), "--quiet"])
    assert res.exit_code != 0


# --- A4: validate-on-map ---

def test_validate_accepts_pack_with_map(tmp_path):
    from agentpack.validate import validate_pack
    in_dir = _md_corpus(tmp_path)
    out = tmp_path / "out"
    runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--quiet"])
    assert (out / "map.yml").exists()
    errors = validate_pack(str(out))
    assert errors == [], f"valid pack+map should have no errors, got: {errors}"


def test_validate_flags_bad_map_chunk_ref(tmp_path):
    from agentpack.validate import validate_pack
    in_dir = _md_corpus(tmp_path)
    out = tmp_path / "out"
    runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--quiet"])

    # Corrupt the map: reference a chunk_id that isn't in the manifest.
    m = yaml.safe_load((out / "map.yml").read_text())
    m["documents"][0]["sections"][0]["chunk_ids"].append("src_999_chunk_999")
    (out / "map.yml").write_text(yaml.dump(m, sort_keys=False))

    errors = validate_pack(str(out))
    assert any("src_999_chunk_999" in e for e in errors), errors


def test_validate_ok_without_map(tmp_path):
    from agentpack.validate import validate_pack
    in_dir = _md_corpus(tmp_path)
    out = tmp_path / "out"
    runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--no-map", "--quiet"])
    assert not (out / "map.yml").exists()
    errors = validate_pack(str(out))
    assert errors == [], f"absent map.yml must not be an error, got: {errors}"


def test_audit_unaffected_by_map(tmp_path):
    """Regression guard: audit_pack works unchanged on a pack that now has map.yml."""
    from agentpack.audit import audit_pack
    in_dir = _md_corpus(tmp_path)
    out = tmp_path / "out"
    runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--quiet"])
    assert (out / "map.yml").exists()
    report = audit_pack(str(out))
    assert not report.startswith("Error"), report
