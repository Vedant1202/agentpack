"""T6 -- CLI surface (`--no-graph`, `agentpack graph`) for the corpus concept graph."""
import yaml
from pathlib import Path
from typer.testing import CliRunner

from agentpack.cli import app

runner = CliRunner()


def _two_doc_corpus(tmp_path: Path) -> Path:
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "a.md").write_text(
        "# Doc A\n\n" + ("Intro paragraph here. " * 20)
    )
    (in_dir / "b.md").write_text(
        "# Doc B\n\n" + ("Different content entirely. " * 20)
    )
    return in_dir


def test_pack_no_graph_cli_flag(tmp_path):
    in_dir = _two_doc_corpus(tmp_path)
    out = tmp_path / "out"
    res = runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--no-graph", "--quiet"])
    assert res.exit_code == 0, res.output
    assert (out / "manifest.yml").exists()
    assert not (out / "graph.yml").exists()


def test_pack_builds_graph_by_default(tmp_path):
    in_dir = _two_doc_corpus(tmp_path)
    out = tmp_path / "out"
    res = runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--quiet"])
    assert res.exit_code == 0, res.output
    assert (out / "graph.yml").exists()
    assert (out / "reports" / "graph_report.md").exists()


def test_toml_enabled_false_suppresses_graph(tmp_path):
    in_dir = _two_doc_corpus(tmp_path)
    (in_dir / "agentpack.toml").write_text("[graph]\nenabled = false\n")
    out = tmp_path / "out"
    res = runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--quiet"])
    assert res.exit_code == 0, res.output
    assert not (out / "graph.yml").exists()


def test_cli_flag_beats_toml_enabled_true(tmp_path):
    in_dir = _two_doc_corpus(tmp_path)
    (in_dir / "agentpack.toml").write_text("[graph]\nenabled = true\n")
    out = tmp_path / "out"
    res = runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--no-graph", "--quiet"])
    assert res.exit_code == 0, res.output
    assert not (out / "graph.yml").exists()


def test_graph_command_rebuilds_from_existing_pack(tmp_path):
    in_dir = _two_doc_corpus(tmp_path)
    out = tmp_path / "out"
    runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--quiet"])

    graph_path = out / "graph.yml"
    assert graph_path.exists()
    graph_path.unlink()

    res = runner.invoke(app, ["graph", str(out), "--quiet"])
    assert res.exit_code == 0, res.output
    assert graph_path.exists()

    g = yaml.safe_load(graph_path.read_text())
    assert g["graph_version"] == 1


def test_graph_command_missing_manifest_errors(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    res = runner.invoke(app, ["graph", str(empty), "--quiet"])
    assert res.exit_code != 0


def test_graph_rebuild_parity_with_pack_time(tmp_path):
    """agentpack graph's output must be byte-identical (modulo generated_at)
    to what pack-time produced -- same code path by construction (spec §3)."""
    in_dir = _two_doc_corpus(tmp_path)
    out = tmp_path / "out"
    runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--quiet"])
    original = yaml.safe_load((out / "graph.yml").read_text())

    res = runner.invoke(app, ["graph", str(out), "--quiet"])
    assert res.exit_code == 0, res.output
    rebuilt = yaml.safe_load((out / "graph.yml").read_text())

    original["pack"]["generated_at"] = "REDACTED"
    rebuilt["pack"]["generated_at"] = "REDACTED"
    assert original == rebuilt


def test_graph_rebuild_uses_recorded_params_not_any_toml(tmp_path):
    """A rebuild must use the params RECORDED in graph.yml, not any
    agentpack.toml -- even one sitting directly in the pack output
    directory, the most tempting place a buggy implementation might
    mistakenly look. The pack dir has no agentpack.toml of its own by
    convention (spec §4a); this proves the rebuild command doesn't
    accidentally introduce one."""
    in_dir = _two_doc_corpus(tmp_path)
    out = tmp_path / "out"
    (in_dir / "agentpack.toml").write_text("[graph]\ndf_cap = 1.0\nmin_docs = 2\n")
    runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--quiet"])
    original = yaml.safe_load((out / "graph.yml").read_text())
    assert original["params"]["df_cap"] == 1.0

    (out / "agentpack.toml").write_text("[graph]\ndf_cap = 0.01\nmin_docs = 99\n")

    res = runner.invoke(app, ["graph", str(out), "--quiet"])
    assert res.exit_code == 0, res.output
    rebuilt = yaml.safe_load((out / "graph.yml").read_text())
    assert rebuilt["params"]["df_cap"] == 1.0
    assert rebuilt["params"]["min_docs"] == 2


def test_graph_rebuild_falls_back_to_defaults_when_existing_graph_corrupt(tmp_path):
    in_dir = _two_doc_corpus(tmp_path)
    out = tmp_path / "out"
    runner.invoke(app, ["pack", str(in_dir), "--out", str(out), "--quiet"])
    (out / "graph.yml").write_text(":\n  - not: [valid, yaml")

    res = runner.invoke(app, ["graph", str(out), "--quiet"])
    assert res.exit_code == 0, res.output
    rebuilt = yaml.safe_load((out / "graph.yml").read_text())
    assert rebuilt["params"]["df_cap"] == 0.30  # fell back to defaults, didn't crash
