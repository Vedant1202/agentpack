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


def _section(node_id, title="Section", keyphrases=None, nodes=None, chunk_ids=None):
    return {
        "node_id": node_id,
        "title": title,
        "keyphrases": keyphrases or [],
        "chunk_ids": chunk_ids or [],
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


# --- T3: references edges from markdown links ------------------------------
#
# Unlike T2's gate tests, these go through the real write_pack() pipeline --
# the whole point of T3 is that link syntax survives verbatim into chunk
# text on disk (spec §2), so testing against real parsed/chunked output is
# the natural, direct way to prove that, not an approximation of it.


def test_extract_link_targets_all_three_forms():
    from agentpack.grapher import _extract_link_targets
    text = (
        "[inline](./b.md) and [ref][1] and [[wiki.md]]\n\n"
        "[1]: ./ref-target.md\n"
    )
    targets = _extract_link_targets(text)
    assert "./b.md" in targets
    assert "./ref-target.md" in targets
    assert "wiki.md" in targets


def test_is_external():
    from agentpack.grapher import _is_external
    assert _is_external("https://example.com") is True
    assert _is_external("mailto:x@y.com") is True
    assert _is_external("./b.md") is False
    assert _is_external("b.md") is False


def test_reference_inline_link_creates_edge(tmp_path):
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "a.md").write_text(
        "# Doc A\n\nSee [the other doc](./b.md) for more details on this topic.\n"
    )
    (in_dir / "b.md").write_text("# Doc B\n\nSome unrelated content lives here instead.\n")
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)

    with open(out_dir / "manifest.yml") as f:
        manifest = yaml.safe_load(f)
    id_by_path = {s["path"]: s["id"] for s in manifest["sources"]}

    with open(out_dir / "graph.yml") as f:
        graph = yaml.safe_load(f)
    refs = [e for e in graph["edges"] if e["relation"] == "references"]
    assert len(refs) == 1
    assert refs[0]["source"] == id_by_path["a.md"]
    assert refs[0]["target"] == id_by_path["b.md"]
    assert refs[0]["basis"] == "structural"


def test_reference_style_and_wikilink_forms_resolved(tmp_path):
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "a.md").write_text(
        "# Doc A\n\n"
        "See [the reference link][ref] for background context on this topic.\n\n"
        "[ref]: ./b.md\n"
    )
    (in_dir / "c.md").write_text(
        "# Doc C\n\nAlso see [[b.md]] using wikilink syntax for cross-referencing.\n"
    )
    (in_dir / "b.md").write_text("# Doc B\n\nSome unrelated content lives here instead.\n")
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)

    with open(out_dir / "manifest.yml") as f:
        manifest = yaml.safe_load(f)
    id_by_path = {s["path"]: s["id"] for s in manifest["sources"]}

    with open(out_dir / "graph.yml") as f:
        graph = yaml.safe_load(f)
    ref_pairs = {(e["source"], e["target"]) for e in graph["edges"] if e["relation"] == "references"}
    assert (id_by_path["a.md"], id_by_path["b.md"]) in ref_pairs
    assert (id_by_path["c.md"], id_by_path["b.md"]) in ref_pairs


def test_reference_external_url_dropped(tmp_path):
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "a.md").write_text(
        "# Doc A\n\nCheck out [this external site](https://example.com/page) for context.\n"
    )
    (in_dir / "b.md").write_text("# Doc B\n\nSome unrelated content lives here instead.\n")
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)
    with open(out_dir / "graph.yml") as f:
        graph = yaml.safe_load(f)
    assert [e for e in graph["edges"] if e["relation"] == "references"] == []


def test_reference_unresolved_target_dropped(tmp_path):
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "a.md").write_text(
        "# Doc A\n\nSee [something](./not_in_this_corpus.md) for background reading.\n"
    )
    (in_dir / "b.md").write_text("# Doc B\n\nSome unrelated content lives here instead.\n")
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)
    with open(out_dir / "graph.yml") as f:
        graph = yaml.safe_load(f)
    assert [e for e in graph["edges"] if e["relation"] == "references"] == []


def test_reference_three_links_same_target_dedupe_to_one_edge(tmp_path):
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "a.md").write_text(
        "# Doc A\n\n"
        "First mention [here](./b.md) in the introduction section.\n\n"
        "Second mention [again](./b.md) later on in this document.\n\n"
        "Third mention [once more](./b.md#specific-section) near the end.\n"
    )
    (in_dir / "b.md").write_text("# Doc B\n\nSome unrelated content lives here instead.\n")
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)
    with open(out_dir / "graph.yml") as f:
        graph = yaml.safe_load(f)
    refs = [e for e in graph["edges"] if e["relation"] == "references"]
    assert len(refs) == 1


def test_reference_self_link_no_self_loop(tmp_path):
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "a.md").write_text(
        "# Doc A\n\nSee [this same document](./a.md) for the full table of contents.\n"
    )
    (in_dir / "b.md").write_text("# Doc B\n\nSome unrelated content lives here instead.\n")
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)
    with open(out_dir / "graph.yml") as f:
        graph = yaml.safe_load(f)
    assert [e for e in graph["edges"] if e["relation"] == "references"] == []


def test_reference_edges_deterministic(tmp_path):
    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "a.md").write_text("# Doc A\n\nSee [other](./b.md) and [third](./c.md) docs for more.\n")
    (in_dir / "b.md").write_text("# Doc B\n\nSome content lives here for this test.\n")
    (in_dir / "c.md").write_text("# Doc C\n\nSome other content lives here too.\n")
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)

    from agentpack.grapher import build_graph
    a = build_graph(str(out_dir))
    b = build_graph(str(out_dir))
    a["pack"]["generated_at"] = "REDACTED"
    b["pack"]["generated_at"] = "REDACTED"
    assert yaml.dump(a, sort_keys=False) == yaml.dump(b, sort_keys=False)


# --- T4: communities (seeded Louvain + determinism hardening) --------------


def _two_cluster_pack(pack_dir):
    """4 docs, 2 structurally disconnected clusters -- A/B share a concept,
    C/D share a different concept, nothing connects the two pairs. A
    disconnected component can never split across communities regardless
    of modularity optimization, so this is a safe, unambiguous fixture."""
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
        {"id": "src_002", "path": "c.md", "status": "success"},
        {"id": "src_003", "path": "d.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": [_section("src_000_s00", "A", ["cluster one topic"])]},
        {"source_id": "src_001", "sections": [_section("src_001_s00", "B", ["cluster one topic"])]},
        {"source_id": "src_002", "sections": [_section("src_002_s00", "C", ["cluster two topic"])]},
        {"source_id": "src_003", "sections": [_section("src_003_s00", "D", ["cluster two topic"])]},
    ]
    _write_synthetic_pack(pack_dir, sources, map_documents)


def test_disconnected_clusters_land_in_different_communities(tmp_path):
    _two_cluster_pack(tmp_path)
    from agentpack.grapher import build_graph
    graph = build_graph(str(tmp_path), params=_DEFAULT_PARAMS)

    community_by_id = {n["id"]: n["community"] for n in graph["nodes"]}
    assert all(cid is not None for cid in community_by_id.values())
    assert community_by_id["src_000"] == community_by_id["src_001"]
    assert community_by_id["src_002"] == community_by_id["src_003"]
    assert community_by_id["src_000"] != community_by_id["src_002"]
    assert len(graph["communities"]) >= 2
    # communities: block ordered by id, sizes match actual membership counts
    ids = [c["id"] for c in graph["communities"]]
    assert ids == sorted(ids)
    for c in graph["communities"]:
        assert c["size"] == sum(1 for cid in community_by_id.values() if cid == c["id"])


def test_community_ids_stable_across_repeated_builds(tmp_path):
    _two_cluster_pack(tmp_path)
    from agentpack.grapher import build_graph
    a = build_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    b = build_graph(str(tmp_path), params=_DEFAULT_PARAMS)

    a_by_id = {n["id"]: n["community"] for n in a["nodes"]}
    b_by_id = {n["id"]: n["community"] for n in b["nodes"]}
    assert a_by_id == b_by_id
    assert a["communities"] == b["communities"]


def test_community_label_prefers_highest_degree_concept():
    from agentpack.grapher import _community_label
    from agentpack.models import GraphNode
    node_by_id = {
        "c_low": GraphNode(id="c_low", kind="concept", label="low degree concept"),
        "c_high": GraphNode(id="c_high", kind="concept", label="high degree concept"),
        "s_1": GraphNode(id="s_1", kind="section", label="Some Section", doc="src_000"),
    }
    # s_1 has the highest RAW degree, but the label rule prefers the
    # highest-degree CONCEPT specifically -- c_high, not s_1.
    degrees = {"c_low": 1, "c_high": 5, "s_1": 10}
    label = _community_label({"c_low", "c_high", "s_1"}, node_by_id, degrees)
    assert label == "high degree concept"


def test_community_label_falls_back_to_highest_degree_node_when_no_concept():
    from agentpack.grapher import _community_label
    from agentpack.models import GraphNode
    node_by_id = {
        "src_000": GraphNode(id="src_000", kind="document", label="a.md"),
        "s_1": GraphNode(id="s_1", kind="section", label="Some Section", doc="src_000"),
    }
    degrees = {"src_000": 3, "s_1": 1}
    label = _community_label({"src_000", "s_1"}, node_by_id, degrees)
    assert label == "a.md"


def test_community_label_ties_broken_by_node_id():
    from agentpack.grapher import _community_label
    from agentpack.models import GraphNode
    node_by_id = {
        "c_zebra": GraphNode(id="c_zebra", kind="concept", label="Zebra Concept"),
        "c_alpha": GraphNode(id="c_alpha", kind="concept", label="Alpha Concept"),
    }
    degrees = {"c_zebra": 2, "c_alpha": 2}  # tied degree -> tie-break by id
    label = _community_label({"c_zebra", "c_alpha"}, node_by_id, degrees)
    assert label == "Alpha Concept"  # "c_alpha" < "c_zebra"


def test_isolated_node_forms_singleton_community(tmp_path):
    """A document with zero sections -- zero edges of any kind, a genuinely
    isolated node, not merely a small disconnected component -- must still
    land in a community of its own, not be left unassigned."""
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": []},  # no sections -> no contains edge -> truly isolated
        {"source_id": "src_001", "sections": [_section("src_001_s00", "B", [])]},
    ]
    _write_synthetic_pack(tmp_path, sources, map_documents)
    from agentpack.grapher import build_graph
    graph = build_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    community_by_id = {n["id"]: n["community"] for n in graph["nodes"]}
    assert community_by_id["src_000"] is not None
    assert community_by_id["src_001"] is not None
    assert community_by_id["src_000"] != community_by_id["src_001"]

    singleton = next(c for c in graph["communities"] if c["id"] == community_by_id["src_000"])
    assert singleton["size"] == 1
    assert singleton["label"] == "a.md"  # no concept members -> falls back to its own label


# --- T5: reports/graph_report.md --------------------------------------------
#
# _top_concepts/_bridge_concepts/_isolated_documents are tested directly with
# hand-built node/edge dicts (matching graph.yml's already-serialized plain-
# dict shape, not pydantic objects -- write_graph derives the report from
# build_graph()'s dict return, not from live GraphNode/GraphEdge instances).
# Bridge concepts specifically need exact community assignments to test
# precisely, which depending on Louvain's actual clustering choices on a
# real fixture would make the test probabilistic rather than exact.


def test_top_concepts_ranks_by_degree_then_id():
    from agentpack.grapher import _top_concepts
    nodes = [
        {"id": "c_mid", "kind": "concept", "label": "mid"},
        {"id": "c_high", "kind": "concept", "label": "high"},
        {"id": "c_tie_b", "kind": "concept", "label": "tie b"},
        {"id": "c_tie_a", "kind": "concept", "label": "tie a"},
    ]
    edges = (
        [{"source": f"s{i}", "target": "c_high", "relation": "mentions"} for i in range(3)]
        + [{"source": "s10", "target": "c_mid", "relation": "mentions"}]
        + [{"source": f"s{i}", "target": "c_tie_a", "relation": "mentions"} for i in range(20, 22)]
        + [{"source": f"s{i}", "target": "c_tie_b", "relation": "mentions"} for i in range(30, 32)]
    )
    top = _top_concepts(nodes, edges, top_n=10)
    assert [c["id"] for c, _ in top] == ["c_high", "c_tie_a", "c_tie_b", "c_mid"]
    assert [d for _, d in top] == [3, 2, 2, 1]


def test_top_concepts_respects_top_n_limit():
    from agentpack.grapher import _top_concepts
    nodes = [{"id": f"c_{i}", "kind": "concept", "label": f"concept {i}"} for i in range(15)]
    edges = [{"source": "s0", "target": f"c_{i}", "relation": "mentions"} for i in range(15)]
    top = _top_concepts(nodes, edges, top_n=10)
    assert len(top) == 10


def test_bridge_concepts_identifies_cross_community_concept():
    from agentpack.grapher import _bridge_concepts
    nodes = [
        {"id": "c_bridge", "kind": "concept", "label": "bridge topic"},
        {"id": "c_local", "kind": "concept", "label": "local topic"},
        {"id": "s_a", "kind": "section", "label": "A", "community": 0},
        {"id": "s_b", "kind": "section", "label": "B", "community": 1},
        {"id": "s_c", "kind": "section", "label": "C", "community": 0},
    ]
    edges = [
        {"source": "s_a", "target": "c_bridge", "relation": "mentions"},
        {"source": "s_b", "target": "c_bridge", "relation": "mentions"},  # different community -> bridge
        {"source": "s_c", "target": "c_local", "relation": "mentions"},  # only community 0 -> not a bridge
    ]
    bridges = _bridge_concepts(nodes, edges)
    assert [c["id"] for c, _comms in bridges] == ["c_bridge"]


def test_bridge_concepts_empty_when_no_concept_spans_multiple_communities():
    from agentpack.grapher import _bridge_concepts
    nodes = [
        {"id": "c_local", "kind": "concept", "label": "local topic"},
        {"id": "s_a", "kind": "section", "label": "A", "community": 0},
        {"id": "s_c", "kind": "section", "label": "C", "community": 0},
    ]
    edges = [
        {"source": "s_a", "target": "c_local", "relation": "mentions"},
        {"source": "s_c", "target": "c_local", "relation": "mentions"},
    ]
    assert _bridge_concepts(nodes, edges) == []


def test_isolated_documents_identifies_disconnected_doc():
    from agentpack.grapher import _isolated_documents
    nodes = [
        {"id": "src_000", "kind": "document", "label": "a.md"},
        {"id": "src_001", "kind": "document", "label": "b.md"},
        {"id": "src_002", "kind": "document", "label": "isolated.md"},
    ]
    edges = [
        {"source": "src_000", "target": "src_001", "relation": "references"},
    ]
    isolated = _isolated_documents(nodes, edges)
    assert [d["id"] for d in isolated] == ["src_002"]


def test_isolated_documents_excludes_concept_connected_doc():
    from agentpack.grapher import _isolated_documents
    nodes = [
        {"id": "src_000", "kind": "document", "label": "a.md"},
        {"id": "src_001", "kind": "document", "label": "b.md"},
        {"id": "s_a", "kind": "section", "label": "A", "doc": "src_000"},
        {"id": "s_b", "kind": "section", "label": "B", "doc": "src_001"},
        {"id": "c_shared", "kind": "concept", "label": "shared topic"},
    ]
    edges = [
        {"source": "s_a", "target": "c_shared", "relation": "mentions"},
        {"source": "s_b", "target": "c_shared", "relation": "mentions"},
    ]
    assert _isolated_documents(nodes, edges) == []  # both docs share a concept -> neither isolated


def test_isolated_documents_concept_mentioned_by_only_one_doc_stays_isolated():
    """A concept mentioned only by sections of ONE document doesn't connect
    that document to anyone else -- shouldn't arise post-gates (min_docs>=1
    can make this legitimate, per spec Q4), but the report's own logic must
    not silently assume a >=2-document invariant it doesn't itself enforce."""
    from agentpack.grapher import _isolated_documents
    nodes = [
        {"id": "src_000", "kind": "document", "label": "a.md"},
        {"id": "s_a1", "kind": "section", "label": "A1", "doc": "src_000"},
        {"id": "s_a2", "kind": "section", "label": "A2", "doc": "src_000"},
        {"id": "c_solo", "kind": "concept", "label": "solo topic"},
    ]
    edges = [
        {"source": "s_a1", "target": "c_solo", "relation": "mentions"},
        {"source": "s_a2", "target": "c_solo", "relation": "mentions"},
    ]
    assert [d["id"] for d in _isolated_documents(nodes, edges)] == ["src_000"]


def test_graph_report_written_with_all_sections(tmp_path):
    _two_cluster_pack(tmp_path)
    from agentpack.grapher import write_graph
    assert write_graph(str(tmp_path), params=_DEFAULT_PARAMS) is True
    report_path = tmp_path / "reports" / "graph_report.md"
    assert report_path.exists()
    text = report_path.read_text()
    for header in ("## Top Concepts", "## Bridge Concepts", "## Isolated Documents", "## Communities"):
        assert header in text


def test_graph_report_lists_promoted_concept(tmp_path):
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": [_section("src_000_s00", "One", ["accounts receivable"])]},
        {"source_id": "src_001", "sections": [_section("src_001_s00", "Two", ["accounts receivable"])]},
    ]
    _write_synthetic_pack(tmp_path, sources, map_documents)
    from agentpack.grapher import write_graph
    write_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    text = (tmp_path / "reports" / "graph_report.md").read_text()
    assert "accounts receivable" in text


def test_graph_report_lists_isolated_document(tmp_path):
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
        {"id": "src_002", "path": "lonely.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": [_section("src_000_s00", "One", ["shared topic"])]},
        {"source_id": "src_001", "sections": [_section("src_001_s00", "Two", ["shared topic"])]},
        {"source_id": "src_002", "sections": [_section("src_002_s00", "Three", ["nobody else has this"])]},
    ]
    _write_synthetic_pack(tmp_path, sources, map_documents)
    from agentpack.grapher import write_graph
    write_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    text = (tmp_path / "reports" / "graph_report.md").read_text()
    isolated_section = text.split("## Isolated Documents")[1].split("##")[0]
    assert "lonely.md" in isolated_section
    assert "a.md" not in isolated_section
    assert "b.md" not in isolated_section


def test_graph_report_deterministic_modulo_generated_at(tmp_path):
    _two_cluster_pack(tmp_path)
    from agentpack.grapher import write_graph

    write_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    first = (tmp_path / "reports" / "graph_report.md").read_text()
    write_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    second = (tmp_path / "reports" / "graph_report.md").read_text()

    def _strip_generated_at(text):
        return "\n".join(line for line in text.splitlines() if not line.startswith("Generated at:"))

    assert _strip_generated_at(first) == _strip_generated_at(second)


# --- B1: similar_to edges from already-built embeddings --------------------
#
# add_similarity_edges is a pure reader of whatever's already on disk: an
# existing graph.yml (to merge into) and an existing indexes/vector_index.npy
# + vector_meta.json (already-normalized per-chunk vectors, the exact
# contract build_vector_index writes -- retrieve.py:200-208, verified live).
# It never calls an embedding model itself, so these tests hand-write
# controlled vectors rather than depend on real fastembed output -- the
# same gate-boundary-precision rationale as T2's synthetic manifest/map.yml
# fixtures. One real end-to-end test at the bottom proves the actual
# build_vector_index wiring (the append-only hook), mirroring T2/T3's
# real-pipeline tests.

import json
import numpy as np


def _write_vector_index(pack_dir, chunk_vectors):
    """Write a synthetic indexes/vector_index.npy + vector_meta.json.
    chunk_vectors is {chunk_id: [already-normalized vector components]},
    mirroring build_vector_index's real on-disk contract exactly."""
    indexes_dir = pack_dir / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    chunk_ids = list(chunk_vectors.keys())
    embeddings = np.array([chunk_vectors[cid] for cid in chunk_ids], dtype=np.float32)
    np.save(indexes_dir / "vector_index.npy", embeddings)
    meta = [
        {"chunk_id": cid, "source_id": None, "path": None, "token_count": 0, "citation": {}}
        for cid in chunk_ids
    ]
    with open(indexes_dir / "vector_meta.json", "w") as f:
        json.dump(meta, f)


def _two_section_similarity_pack(tmp_path, vec_a, vec_b, same_doc=False):
    """Two sections (in different documents unless same_doc=True), one
    chunk each, with caller-supplied vectors -- lets each test dial in an
    exact, known cosine similarity rather than depending on real content."""
    if same_doc:
        # A second, unrelated document is required even though it plays no
        # part in the similarity check itself -- _MIN_SUCCESSFUL_SOURCES=2
        # (T1) refuses to build any graph at all for a single-document
        # corpus, structurally independent of this test's actual point.
        sources = [
            {"id": "src_000", "path": "a.md", "status": "success"},
            {"id": "src_001", "path": "b.md", "status": "success"},
        ]
        map_documents = [
            {"source_id": "src_000", "sections": [
                _section("src_000_s00", "One", chunk_ids=["c_a"]),
                _section("src_000_s01", "Two", chunk_ids=["c_b"]),
            ]},
            {"source_id": "src_001", "sections": [_section("src_001_s00", "Other", chunk_ids=[])]},
        ]
    else:
        sources = [
            {"id": "src_000", "path": "a.md", "status": "success"},
            {"id": "src_001", "path": "b.md", "status": "success"},
        ]
        map_documents = [
            {"source_id": "src_000", "sections": [_section("src_000_s00", "One", chunk_ids=["c_a"])]},
            {"source_id": "src_001", "sections": [_section("src_001_s00", "Two", chunk_ids=["c_b"])]},
        ]
    _write_synthetic_pack(tmp_path, sources, map_documents)
    _write_vector_index(tmp_path, {"c_a": vec_a, "c_b": vec_b})


def _similar_to_edges(graph):
    return [e for e in graph["edges"] if e["relation"] == "similar_to"]


def test_similarity_edge_created_for_near_identical_sections(tmp_path):
    from agentpack.grapher import write_graph, add_similarity_edges
    _two_section_similarity_pack(tmp_path, [1.0, 0.0], [1.0, 0.0])  # cosine = 1.0
    write_graph(str(tmp_path), params=_DEFAULT_PARAMS)

    assert add_similarity_edges(str(tmp_path), params=_DEFAULT_PARAMS) is True
    graph = yaml.safe_load((tmp_path / "graph.yml").read_text())
    edges = _similar_to_edges(graph)
    assert len(edges) == 1
    assert {edges[0]["source"], edges[0]["target"]} == {"src_000_s00", "src_001_s00"}
    assert edges[0]["basis"] == "embedding"


def test_similarity_edge_not_created_for_unrelated_sections(tmp_path):
    from agentpack.grapher import write_graph, add_similarity_edges
    _two_section_similarity_pack(tmp_path, [1.0, 0.0], [0.0, 1.0])  # cosine = 0.0
    write_graph(str(tmp_path), params=_DEFAULT_PARAMS)

    add_similarity_edges(str(tmp_path), params=_DEFAULT_PARAMS)
    graph = yaml.safe_load((tmp_path / "graph.yml").read_text())
    assert _similar_to_edges(graph) == []


def test_similarity_threshold_from_params_honored(tmp_path):
    """cosine = 0.6 (verified live: dot([1,0], [0.6,0.8]) == 0.6) -- rejected
    at the default 0.8 threshold, admitted once params lowers it to 0.5."""
    from agentpack.grapher import write_graph, add_similarity_edges
    _two_section_similarity_pack(tmp_path, [1.0, 0.0], [0.6, 0.8])
    write_graph(str(tmp_path), params=_DEFAULT_PARAMS)

    add_similarity_edges(str(tmp_path), params=_DEFAULT_PARAMS)  # threshold 0.8
    graph = yaml.safe_load((tmp_path / "graph.yml").read_text())
    assert _similar_to_edges(graph) == []

    add_similarity_edges(str(tmp_path), params={**_DEFAULT_PARAMS, "similarity_threshold": 0.5})
    graph = yaml.safe_load((tmp_path / "graph.yml").read_text())
    assert len(_similar_to_edges(graph)) == 1


def test_similarity_excludes_same_document_sections(tmp_path):
    from agentpack.grapher import write_graph, add_similarity_edges
    _two_section_similarity_pack(tmp_path, [1.0, 0.0], [1.0, 0.0], same_doc=True)
    write_graph(str(tmp_path), params=_DEFAULT_PARAMS)

    add_similarity_edges(str(tmp_path), params=_DEFAULT_PARAMS)
    graph = yaml.safe_load((tmp_path / "graph.yml").read_text())
    assert _similar_to_edges(graph) == []


def test_similarity_idempotent_no_duplicate_edges_on_rerun(tmp_path):
    from agentpack.grapher import write_graph, add_similarity_edges
    _two_section_similarity_pack(tmp_path, [1.0, 0.0], [1.0, 0.0])
    write_graph(str(tmp_path), params=_DEFAULT_PARAMS)

    add_similarity_edges(str(tmp_path), params=_DEFAULT_PARAMS)
    first = yaml.safe_load((tmp_path / "graph.yml").read_text())
    add_similarity_edges(str(tmp_path), params=_DEFAULT_PARAMS)
    second = yaml.safe_load((tmp_path / "graph.yml").read_text())

    assert len(_similar_to_edges(first)) == 1
    assert len(_similar_to_edges(second)) == 1
    first["pack"]["generated_at"] = second["pack"]["generated_at"] = "REDACTED"
    assert first == second


def test_similarity_recomputes_communities_not_stale_passthrough(tmp_path):
    """Communities must be freshly recomputed from the CURRENT edge set, not
    carried over from whatever graph.yml already had -- proven by planting
    an obviously-stale communities block before merging, then confirming the
    output reflects the real topology instead of the stale stub.

    Deliberately not asserted here: that bridging two small components with
    one similar_to edge merges them into the same community. Verified live
    (networkx 3.6.1, seed=42) that Louvain keeps two 2-node pairs in
    SEPARATE communities even after a single edge connects them into one
    path graph -- a real resolution-limit effect on small graphs, not a bug
    in this feature, so asserting a specific merge outcome would be testing
    Louvain's optimization choice rather than this code."""
    from agentpack.grapher import write_graph, add_similarity_edges
    _two_section_similarity_pack(tmp_path, [1.0, 0.0], [0.0, 1.0])  # cosine 0 -> no new edge
    write_graph(str(tmp_path), params=_DEFAULT_PARAMS)

    graph_path = tmp_path / "graph.yml"
    corrupted = yaml.safe_load(graph_path.read_text())
    for n in corrupted["nodes"]:
        n["community"] = 99
    stale_block = [{"id": 99, "label": "STALE", "size": len(corrupted["nodes"])}]
    corrupted["communities"] = stale_block
    with open(graph_path, "w") as f:
        yaml.dump(corrupted, f)

    add_similarity_edges(str(tmp_path), params=_DEFAULT_PARAMS)
    after = yaml.safe_load(graph_path.read_text())
    assert after["communities"] != stale_block
    assert any(n["community"] != 99 for n in after["nodes"])


def test_similarity_no_op_when_no_graph_yml(tmp_path, capsys):
    from agentpack.grapher import add_similarity_edges
    _two_section_similarity_pack(tmp_path, [1.0, 0.0], [1.0, 0.0])
    # no write_graph() call -- graph.yml never created
    assert add_similarity_edges(str(tmp_path), params=_DEFAULT_PARAMS) is False
    assert not (tmp_path / "graph.yml").exists()
    assert capsys.readouterr().err


def test_similarity_no_op_when_no_vector_index(tmp_path, capsys):
    from agentpack.grapher import write_graph, add_similarity_edges
    sources = [
        {"id": "src_000", "path": "a.md", "status": "success"},
        {"id": "src_001", "path": "b.md", "status": "success"},
    ]
    map_documents = [
        {"source_id": "src_000", "sections": [_section("src_000_s00", "One", chunk_ids=["c_a"])]},
        {"source_id": "src_001", "sections": [_section("src_001_s00", "Two", chunk_ids=["c_b"])]},
    ]
    _write_synthetic_pack(tmp_path, sources, map_documents)
    write_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    before = (tmp_path / "graph.yml").read_text()

    assert add_similarity_edges(str(tmp_path), params=_DEFAULT_PARAMS) is False
    assert (tmp_path / "graph.yml").read_text() == before  # left untouched
    assert capsys.readouterr().err


def test_similarity_graph_without_similarity_still_validates(tmp_path):
    """graph.yml built at pack-time, never touched by add_similarity_edges,
    must still pass validate_pack -- the merge step is purely additive."""
    from agentpack.grapher import write_graph
    from agentpack.validate import validate_pack
    _two_cluster_pack(tmp_path)
    write_graph(str(tmp_path), params=_DEFAULT_PARAMS)
    assert validate_pack(str(tmp_path)) == []


def test_similarity_end_to_end_via_build_vector_index(tmp_path):
    """Real write_pack + real (mocked-embedding) build_vector_index -- proves
    the append-only hook at the end of build_vector_index (retrieve.py)
    actually calls into grapher.py, not just that the pure function works
    in isolation. A constant embedding vector for every chunk means every
    cross-document section pair comes out at cosine=1.0."""
    from unittest.mock import patch, MagicMock
    from agentpack.pack import write_pack
    from agentpack.retrieve import build_vector_index

    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "a.md").write_text("# Doc A\n\nSome real content for chunking and embedding here.\n")
    (in_dir / "b.md").write_text("# Doc B\n\nDifferent real content for this second document.\n")
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True, graph_params=_DEFAULT_PARAMS)
    assert (out_dir / "graph.yml").exists()

    mock_embed = MagicMock()
    mock_embed.embed.side_effect = lambda texts, **_: iter([[1.0, 0.0]] * len(texts))
    indexes_dir = out_dir / "indexes"
    indexes_dir.mkdir(exist_ok=True)
    with patch("agentpack.retrieve._get_embedding_model", return_value=mock_embed):
        build_vector_index(out_dir, indexes_dir / "vector_index.npy", indexes_dir / "vector_meta.json")

    graph = yaml.safe_load((out_dir / "graph.yml").read_text())
    edges = _similar_to_edges(graph)
    assert edges  # the hook ran and found at least the cross-doc section pair
    assert all(e["basis"] == "embedding" for e in edges)
