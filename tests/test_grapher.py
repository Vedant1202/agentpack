"""Phase A T1 -- walking skeleton for the corpus concept graph (graph.yml).

Tests document + section nodes and `contains` edges only -- concepts (T2),
references (T3), and communities (T4) land in later tasks.
"""
import yaml
from agentpack.pack import write_pack


def _two_doc_corpus(tmp_path):
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "intro.md").write_text(
        "# Introduction\n\nThis guide explains how the system works overall.\n\n"
        "## Setup\n\nInstall dependencies before running anything else here.\n"
    )
    (in_dir / "usage.md").write_text(
        "# Usage\n\nThis section covers day to day commands and flags.\n\n"
        "## Advanced\n\nAdvanced flags for power users and CI pipelines.\n"
    )
    return in_dir


def test_graph_skeleton_documents_and_sections(tmp_path):
    in_dir = _two_doc_corpus(tmp_path)
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)

    graph_path = out_dir / "graph.yml"
    assert graph_path.exists()
    with open(graph_path) as f:
        graph = yaml.safe_load(f)

    assert graph["graph_version"] == 1
    assert graph["params"]  # recorded even though unused until T2/B1
    assert graph["pack"]["manifest"] == "manifest.yml"

    doc_nodes = [n for n in graph["nodes"] if n["kind"] == "document"]
    section_nodes = [n for n in graph["nodes"] if n["kind"] == "section"]
    assert len(doc_nodes) == 2
    assert len(section_nodes) >= 2  # at least one top-level section per doc

    contains_edges = [e for e in graph["edges"] if e["relation"] == "contains"]
    assert contains_edges
    assert all(e["basis"] == "structural" for e in contains_edges)

    doc_ids = {n["id"] for n in doc_nodes}
    section_ids = {n["id"] for n in section_nodes}
    for e in contains_edges:
        assert e["source"] in doc_ids
        assert e["target"] in section_ids
    # every section node is reachable via exactly one contains edge
    assert {e["target"] for e in contains_edges} == section_ids
    # section nodes carry their owning document
    for n in section_nodes:
        assert n["doc"] in doc_ids


def test_graph_nodes_and_edges_sorted_deterministically(tmp_path):
    in_dir = _two_doc_corpus(tmp_path)
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)
    with open(out_dir / "graph.yml") as f:
        graph = yaml.safe_load(f)

    node_keys = [(n["kind"], n["id"]) for n in graph["nodes"]]
    assert node_keys == sorted(node_keys)
    edge_keys = [(e["source"], e["target"], e["relation"]) for e in graph["edges"]]
    assert edge_keys == sorted(edge_keys)


def test_graph_single_doc_corpus_skips(tmp_path):
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "only.md").write_text(
        "# Only\n\nJust one document here, nothing to cross-reference against.\n"
    )
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)

    assert (out_dir / "manifest.yml").exists()  # pack still succeeds
    assert not (out_dir / "graph.yml").exists()


def test_graph_no_graph_flag_suppresses(tmp_path):
    in_dir = _two_doc_corpus(tmp_path)
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True, no_graph=True)
    assert not (out_dir / "graph.yml").exists()


def test_graph_corrupt_map_yml_degrades_gracefully(tmp_path, capsys):
    in_dir = _two_doc_corpus(tmp_path)
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)
    assert (out_dir / "graph.yml").exists()  # sanity: builds the first time

    (out_dir / "map.yml").write_text(":\n  - not: [valid, yaml")
    (out_dir / "graph.yml").unlink()

    from agentpack.grapher import write_graph
    result = write_graph(str(out_dir))
    assert result is False
    assert not (out_dir / "graph.yml").exists()
    assert capsys.readouterr().err  # exactly one warning printed, pack itself never raised


def test_graph_never_raises_on_missing_manifest(tmp_path):
    from agentpack.grapher import build_graph
    assert build_graph(str(tmp_path)) is None


def test_graph_manifest_and_map_unaffected(tmp_path):
    """The graph is purely additive -- manifest.yml/map.yml content identical
    (modulo generated_at) whether or not the graph is built."""
    in_dir = _two_doc_corpus(tmp_path)
    out_with = tmp_path / "out_with"
    out_without = tmp_path / "out_without"
    write_pack(str(in_dir), str(out_with), quiet=True)
    write_pack(str(in_dir), str(out_without), quiet=True, no_graph=True)

    def _normalized(path):
        with open(path) as f:
            data = yaml.safe_load(f)
        data["pack"]["generated_at"] = "REDACTED"
        return data

    assert _normalized(out_with / "manifest.yml") == _normalized(out_without / "manifest.yml")
    assert _normalized(out_with / "map.yml") == _normalized(out_without / "map.yml")


def test_graph_build_twice_deterministic(tmp_path):
    in_dir = _two_doc_corpus(tmp_path)
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)

    from agentpack.grapher import build_graph
    a = build_graph(str(out_dir))
    b = build_graph(str(out_dir))
    assert a is not None and b is not None
    a["pack"]["generated_at"] = "REDACTED"
    b["pack"]["generated_at"] = "REDACTED"
    assert yaml.dump(a, sort_keys=False) == yaml.dump(b, sort_keys=False)
