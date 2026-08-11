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


# --- T2: concept promotion -------------------------------------------------
#
# Gate-boundary tests need EXACT control over section/document/keyphrase
# counts, which real YAKE output can't reliably guarantee -- so these write
# a synthetic manifest.yml + map.yml directly (mirroring test_audit.py's
# _write_manifest pattern) and call build_graph(), the real public entry
# point, rather than reaching into private helpers. One true end-to-end
# test at the bottom proves the real pipeline (write_pack -> real YAKE)
# wires up correctly, using a phrase verified live to survive YAKE
# extraction unchanged: keyphrases("...accounts receivable...") includes
# the exact string "accounts receivable" in both source texts.

_DEFAULT_PARAMS = {"enabled": True, "df_cap": 1.0, "min_docs": 2, "similarity_threshold": 0.8}


def _write_synthetic_pack(pack_dir, sources, map_documents):
    pack_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "pack": {"name": "test_pack", "generated_at": "2026-01-01T00:00:00Z"},
        "sources": sources,
        "chunks": [],
        "tables": [],
    }
    with open(pack_dir / "manifest.yml", "w") as f:
        yaml.dump(manifest, f)
    map_obj = {
        "map_version": 1,
        "pack": {"name": "test_pack", "generated_at": "2026-01-01T00:00:00Z", "manifest": "manifest.yml"},
        "corpus": {},
        "documents": map_documents,
    }
    with open(pack_dir / "map.yml", "w") as f:
        yaml.dump(map_obj, f)


def _section(node_id, title="Section", keyphrases=None, nodes=None):
    return {
        "node_id": node_id,
        "title": title,
        "keyphrases": keyphrases or [],
        "chunk_ids": [],
        "nodes": nodes or [],
    }


def test_slug_normalization():
    from agentpack.grapher import _slug
    assert _slug("Balance Sheet") == "balance_sheet"
    assert _slug("balance-sheet") == "balance_sheet"
    assert _slug("Accounts  Receivable!!") == "accounts_receivable"
    assert _slug("___leading_and_trailing___") == "leading_and_trailing"


def test_concept_promoted_across_two_documents(tmp_path):
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": [_section("src_000_s00", "Intro", ["accounts receivable"])]},
        {"source_id": "src_001", "sections": [_section("src_001_s00", "Overview", ["accounts receivable"])]},
    ]
    _write_synthetic_pack(tmp_path, sources, map_documents)

    from agentpack.grapher import build_graph
    graph = build_graph(str(tmp_path), params=_DEFAULT_PARAMS)

    concept_nodes = [n for n in graph["nodes"] if n["kind"] == "concept"]
    assert len(concept_nodes) == 1
    assert concept_nodes[0]["id"] == "c_accounts_receivable"
    assert concept_nodes[0]["label"] == "accounts receivable"

    mentions = [e for e in graph["edges"] if e["relation"] == "mentions"]
    assert {e["source"] for e in mentions} == {"src_000_s00", "src_001_s00"}
    assert all(e["target"] == "c_accounts_receivable" and e["basis"] == "keyphrase" for e in mentions)


def test_concept_not_promoted_single_document(tmp_path):
    """Same keyphrase in two sections of the SAME document -- only 1 distinct
    document, min_docs=2 not met."""
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": [
            _section("src_000_s00", "Intro", ["accounts receivable"]),
            _section("src_000_s01", "More", ["accounts receivable"]),
        ]},
        {"source_id": "src_001", "sections": [_section("src_001_s00", "Overview", ["unrelated topic"])]},
    ]
    _write_synthetic_pack(tmp_path, sources, map_documents)

    from agentpack.grapher import build_graph
    graph = build_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    assert [n for n in graph["nodes"] if n["kind"] == "concept"] == []


def test_concept_not_promoted_above_df_cap(tmp_path):
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": [
            _section("src_000_s00", "One", ["boilerplate phrase"]),
            _section("src_000_s01", "Two", ["boilerplate phrase"]),
        ]},
        {"source_id": "src_001", "sections": [
            _section("src_001_s00", "Three", ["boilerplate phrase"]),
            _section("src_001_s01", "Four", ["something else"]),
        ]},
    ]
    _write_synthetic_pack(tmp_path, sources, map_documents)
    from agentpack.grapher import build_graph

    # 3 of 4 sections carry the phrase (0.75 fraction); a 0.5 cap must reject it.
    rejected = build_graph(str(tmp_path), params={**_DEFAULT_PARAMS, "df_cap": 0.5})
    assert [n for n in rejected["nodes"] if n["kind"] == "concept"] == []

    # Same corpus, looser cap DOES promote it -- proves the rejection above
    # was really the df_cap gate, not something else silently failing.
    promoted = build_graph(str(tmp_path), params={**_DEFAULT_PARAMS, "df_cap": 0.8})
    assert len([n for n in promoted["nodes"] if n["kind"] == "concept"]) == 1


def test_concept_min_docs_config_effect(tmp_path):
    """min_docs is user-tunable via params -- the same 2-document keyphrase
    promotes at min_docs=2 and is rejected at min_docs=3."""
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": [_section("src_000_s00", "One", ["shared topic"])]},
        {"source_id": "src_001", "sections": [_section("src_001_s00", "Two", ["shared topic"])]},
    ]
    _write_synthetic_pack(tmp_path, sources, map_documents)
    from agentpack.grapher import build_graph

    graph_2 = build_graph(str(tmp_path), params={**_DEFAULT_PARAMS, "min_docs": 2})
    assert len([n for n in graph_2["nodes"] if n["kind"] == "concept"]) == 1

    graph_3 = build_graph(str(tmp_path), params={**_DEFAULT_PARAMS, "min_docs": 3})
    assert [n for n in graph_3["nodes"] if n["kind"] == "concept"] == []


def test_concept_length_gate_rejects_short_and_numeric_slugs(tmp_path):
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": [_section("src_000_s00", "One", ["abc", "2024", "real concept here"])]},
        {"source_id": "src_001", "sections": [_section("src_001_s00", "Two", ["abc", "2024", "real concept here"])]},
    ]
    _write_synthetic_pack(tmp_path, sources, map_documents)
    from agentpack.grapher import build_graph
    graph = build_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    concept_ids = {n["id"] for n in graph["nodes"] if n["kind"] == "concept"}
    assert concept_ids == {"c_real_concept_here"}  # "abc" too short, "2024" purely numeric


def test_concept_slug_collision_merges_surface_forms(tmp_path):
    """'Balance Sheet' and 'balance-sheet' normalize to the same slug and
    must merge into ONE concept, not two."""
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": [_section("src_000_s00", "One", ["Balance Sheet"])]},
        {"source_id": "src_001", "sections": [_section("src_001_s00", "Two", ["balance-sheet"])]},
    ]
    _write_synthetic_pack(tmp_path, sources, map_documents)
    from agentpack.grapher import build_graph
    graph = build_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    concept_nodes = [n for n in graph["nodes"] if n["kind"] == "concept"]
    assert len(concept_nodes) == 1
    assert concept_nodes[0]["id"] == "c_balance_sheet"
    # Tied 1-1 occurrence count -- verified live: ASCII 'B' < 'b', so the
    # lexical tie-break picks "Balance Sheet" over "balance-sheet".
    assert concept_nodes[0]["label"] == "Balance Sheet"


def test_concept_creates_node_for_nested_section(tmp_path):
    """A concept mentioned only by a NESTED (non-top-level) section must
    still give that section a graph node -- nested sections get no `contains`
    edge (T1 scoped that to top-level only), so without this the section
    would carry a real mentions edge but be unreachable (spec §4 nodes rule).
    The top-level parent (no keyphrases of its own) still gets its node from
    the unconditional contains-edge pass, but no mentions edge."""
    nested = _section("src_000_s00-00", "Nested", ["deep topic"])
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": [
            _section("src_000_s00", "Top", [], nodes=[nested]),
        ]},
        {"source_id": "src_001", "sections": [_section("src_001_s00", "Other", ["deep topic"])]},
    ]
    _write_synthetic_pack(tmp_path, sources, map_documents)
    from agentpack.grapher import build_graph
    graph = build_graph(str(tmp_path), params=_DEFAULT_PARAMS)

    section_ids = {n["id"] for n in graph["nodes"] if n["kind"] == "section"}
    assert "src_000_s00-00" in section_ids  # nested section: node created via its mentions edge
    assert "src_000_s00" in section_ids     # top-level parent: node from the unconditional contains edge

    mentions_sources = {e["source"] for e in graph["edges"] if e["relation"] == "mentions"}
    assert "src_000_s00-00" in mentions_sources
    assert "src_000_s00" not in mentions_sources  # parent has no keyphrases of its own


def test_concept_promotion_deterministic(tmp_path):
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": [_section("src_000_s00", "One", ["shared topic", "another idea"])]},
        {"source_id": "src_001", "sections": [_section("src_001_s00", "Two", ["shared topic", "another idea"])]},
    ]
    _write_synthetic_pack(tmp_path, sources, map_documents)
    from agentpack.grapher import build_graph
    a = build_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    b = build_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    a["pack"]["generated_at"] = "REDACTED"
    b["pack"]["generated_at"] = "REDACTED"
    assert yaml.dump(a, sort_keys=False) == yaml.dump(b, sort_keys=False)


def test_concept_promotion_end_to_end_real_yake(tmp_path):
    """Real pipeline, real YAKE -- proves write_pack -> mapper enrichment ->
    concept promotion actually wires together, not just the isolated gate
    logic above. Phrase verified live to survive YAKE extraction unchanged
    in both source texts."""
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "a.md").write_text(
        "# Filing A\n\n"
        "This document discusses accounts receivable in detail. "
        "Accounts receivable balances grew significantly this quarter. "
        "Management reviewed accounts receivable aging schedules carefully.\n"
    )
    (in_dir / "b.md").write_text(
        "# Filing B\n\n"
        "The following section covers accounts receivable trends across the portfolio. "
        "Accounts receivable exposure remains a key risk factor for the business this year.\n"
    )
    out_dir = tmp_path / "out"
    from agentpack.pack import write_pack
    write_pack(str(in_dir), str(out_dir), quiet=True, graph_params={**_DEFAULT_PARAMS, "df_cap": 1.0})

    with open(out_dir / "graph.yml") as f:
        graph = yaml.safe_load(f)
    concept_ids = {n["id"] for n in graph["nodes"] if n["kind"] == "concept"}
    assert "c_accounts_receivable" in concept_ids
