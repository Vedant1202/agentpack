"""Phase A1 — walking skeleton for the hierarchical knowledge map (map.yml).

Tests the deterministic structural tree: corpus -> document -> (flat) section -> chunk_ids,
plus the chunker change that persists the full section_path into chunk metadata.
"""
import yaml
from pathlib import Path
from agentpack.models import SourceDocument, DocumentBlock
from agentpack.chunker import chunk_document

# Two clearly-separated sections, each paragraph large enough to force its own chunk(s).
LONG_A = "Introduction content describing setup. " * 40
LONG_B = "Usage content covering commands and flags. " * 40


def _two_section_doc():
    return SourceDocument(
        source_id="src_000",
        path="guide.md",
        type="markdown",
        checksum="abc",
        blocks=[
            DocumentBlock(block_id="b0", source_id="src_000", type="heading",
                          text="Introduction", section_path=["Introduction"]),
            DocumentBlock(block_id="b1", source_id="src_000", type="paragraph",
                          text=LONG_A, section_path=["Introduction"]),
            DocumentBlock(block_id="b2", source_id="src_000", type="heading",
                          text="Usage", section_path=["Usage"]),
            DocumentBlock(block_id="b3", source_id="src_000", type="paragraph",
                          text=LONG_B, section_path=["Usage"]),
        ],
        warnings=[],
    )


def test_chunker_persists_full_section_path():
    """The chunker must keep the full section_path list, not just the leaf `section`."""
    chunks = chunk_document(_two_section_doc(), max_tokens=60)
    assert any(c.metadata.get("section_path") for c in chunks), "no chunk carried section_path"
    for c in chunks:
        sp = c.metadata.get("section_path")
        if sp is not None:
            assert isinstance(sp, list)
        # back-compat: leaf `section` is still present
        assert "section" in c.metadata


def test_build_map_structure_and_chunk_integrity():
    from agentpack.mapper import build_map

    doc = _two_section_doc()
    chunks = chunk_document(doc, max_tokens=60)
    m = build_map(
        {"name": "corpus", "generated_at": "t", "manifest": "manifest.yml"},
        [doc], chunks,
    )

    # Top-level shape
    assert m["map_version"] == 1
    assert m["pack"]["manifest"] == "manifest.yml"
    assert m["corpus"]["stats"]["documents"] == 1
    assert m["corpus"]["stats"]["chunks"] == len(chunks)

    docs = m["documents"]
    assert len(docs) == 1
    sections = docs[0]["sections"]
    assert len(sections) >= 2, "two distinct sections should produce >=2 nodes"

    # Every chunk_id in the map exists, and every chunk is reachable exactly once.
    all_ids = sorted(c.chunk_id for c in chunks)
    referenced = [cid for s in sections for cid in s["chunk_ids"]]
    assert set(referenced).issubset(set(all_ids))
    assert sorted(referenced) == all_ids, "every chunk must be reachable exactly once"

    # node_id is stable/deterministic and namespaced by source
    assert all(s["node_id"].startswith("src_000") for s in sections)


def test_build_map_is_deterministic():
    from agentpack.mapper import build_map
    doc = _two_section_doc()
    chunks = chunk_document(doc, max_tokens=60)
    meta = {"name": "corpus", "generated_at": "t", "manifest": "manifest.yml"}
    a = build_map(meta, [doc], chunks)
    b = build_map(meta, [doc], chunks)
    assert yaml.dump(a, sort_keys=False) == yaml.dump(b, sort_keys=False)


def test_pack_writes_map_yml(tmp_path):
    """`write_pack` emits a sibling map.yml by default whose chunk_ids match the manifest."""
    from agentpack.pack import write_pack

    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "guide.md").write_text(
        "# Introduction\n\n" + ("Intro paragraph. " * 30) +
        "\n\n## Usage\n\n" + ("Usage details. " * 30)
    )
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True)

    map_path = out_dir / "map.yml"
    assert map_path.exists(), "map.yml should be written by default"

    with open(map_path) as f:
        m = yaml.safe_load(f)
    with open(out_dir / "manifest.yml") as f:
        manifest = yaml.safe_load(f)

    manifest_ids = {c["id"] for c in manifest["chunks"]}
    referenced = [cid for d in m["documents"] for cid in _walk_chunk_ids(d["sections"])]
    assert referenced, "map must reference chunks"
    assert set(referenced).issubset(manifest_ids)


def test_pack_no_map_flag_suppresses_map(tmp_path):
    """write_pack(no_map=True) must not emit map.yml."""
    from agentpack.pack import write_pack

    in_dir = tmp_path / "corpus"
    in_dir.mkdir()
    (in_dir / "doc.txt").write_text("hello world")
    out_dir = tmp_path / "out"
    write_pack(str(in_dir), str(out_dir), quiet=True, no_map=True)

    assert not (out_dir / "map.yml").exists()
    assert (out_dir / "manifest.yml").exists()


# --- Phase A2: recursive hierarchy, __root__ orphans, has_tables, page rollup ---

LONG = "lorem ipsum dolor sit amet consectetur adipiscing elit " * 25


def _walk_chunk_ids(nodes):
    out = []
    for n in nodes:
        out += n["chunk_ids"]
        out += _walk_chunk_ids(n["nodes"])
    return out


def _nested_doc():
    return SourceDocument(
        source_id="src_000", path="guide.md", type="markdown", checksum="x",
        blocks=[
            DocumentBlock(block_id="b0", source_id="src_000", type="heading",
                          text="Guide", section_path=["Guide"]),
            DocumentBlock(block_id="b1", source_id="src_000", type="paragraph",
                          text=LONG, section_path=["Guide"]),
            DocumentBlock(block_id="b2", source_id="src_000", type="heading",
                          text="Setup", section_path=["Guide", "Setup"]),
            DocumentBlock(block_id="b3", source_id="src_000", type="paragraph",
                          text=LONG, section_path=["Guide", "Setup"]),
            DocumentBlock(block_id="b4", source_id="src_000", type="heading",
                          text="Usage", section_path=["Usage"]),
            DocumentBlock(block_id="b5", source_id="src_000", type="table",
                          text="| a | b |\n|---|---|\n| 1 | 2 |", section_path=["Usage"]),
            DocumentBlock(block_id="b6", source_id="src_000", type="paragraph",
                          text=LONG, section_path=["Usage"]),
        ],
        warnings=[],
    )


def test_nested_hierarchy_built_from_blocks():
    from agentpack.mapper import build_map
    doc = _nested_doc()
    chunks = chunk_document(doc, max_tokens=40)
    m = build_map({"name": "c", "generated_at": "t", "manifest": "manifest.yml"}, [doc], chunks)

    sections = m["documents"][0]["sections"]
    titles = [s["title"] for s in sections]
    assert "Guide" in titles and "Usage" in titles, "top-level sections from blocks"

    guide = next(s for s in sections if s["title"] == "Guide")
    assert any(c["title"] == "Setup" for c in guide["nodes"]), "Setup must nest under Guide"

    # child node_id encodes the ordinal path under its parent
    setup = next(c for c in guide["nodes"] if c["title"] == "Setup")
    assert setup["node_id"].startswith(guide["node_id"])


def test_has_tables_is_block_derived_and_local():
    from agentpack.mapper import build_map
    doc = _nested_doc()
    chunks = chunk_document(doc, max_tokens=40)
    m = build_map({"name": "c", "generated_at": "t", "manifest": "manifest.yml"}, [doc], chunks)
    sections = m["documents"][0]["sections"]
    usage = next(s for s in sections if s["title"] == "Usage")
    guide = next(s for s in sections if s["title"] == "Guide")
    assert usage["has_tables"] is True
    assert guide["has_tables"] is False


def test_recursive_chunk_reachability():
    from agentpack.mapper import build_map
    doc = _nested_doc()
    chunks = chunk_document(doc, max_tokens=40)
    m = build_map({"name": "c", "generated_at": "t", "manifest": "manifest.yml"}, [doc], chunks)
    referenced = _walk_chunk_ids(m["documents"][0]["sections"])
    all_ids = sorted(c.chunk_id for c in chunks)
    assert sorted(referenced) == all_ids, "every chunk reachable exactly once across the tree"


def test_orphan_chunks_under_synthetic_root():
    from agentpack.mapper import build_map
    doc = SourceDocument(
        source_id="src_txt", path="notes.txt", type="txt", checksum="x",
        blocks=[DocumentBlock(block_id="b0", source_id="src_txt", type="paragraph",
                              text="hello world with no headings at all here")],
        warnings=[],
    )
    chunks = chunk_document(doc, max_tokens=100)
    m = build_map({"name": "c", "generated_at": "t", "manifest": "manifest.yml"}, [doc], chunks)
    sections = m["documents"][0]["sections"]
    assert len(sections) == 1
    assert sections[0]["title"] == "(root)"
    assert sections[0]["node_id"] == "src_txt_root"
    assert set(sections[0]["chunk_ids"]) == {c.chunk_id for c in chunks}


def test_pages_roll_up_over_subtree():
    from agentpack.mapper import build_map
    doc = SourceDocument(
        source_id="src_pdf", path="doc.pdf", type="pdf", checksum="x",
        blocks=[
            DocumentBlock(block_id="b0", source_id="src_pdf", type="heading",
                          text="Chapter", section_path=["Chapter"], page=2),
            DocumentBlock(block_id="b1", source_id="src_pdf", type="paragraph",
                          text="intro text", section_path=["Chapter"], page=2),
            DocumentBlock(block_id="b2", source_id="src_pdf", type="heading",
                          text="Part", section_path=["Chapter", "Part"], page=5),
            DocumentBlock(block_id="b3", source_id="src_pdf", type="paragraph",
                          text="body text", section_path=["Chapter", "Part"], page=7),
        ],
        warnings=[],
    )
    chunks = chunk_document(doc, max_tokens=800)
    m = build_map({"name": "c", "generated_at": "t", "manifest": "manifest.yml"}, [doc], chunks)
    chapter = m["documents"][0]["sections"][0]
    assert chapter["title"] == "Chapter"
    assert chapter["pages"] == [2, 7], "parent page span must include its subtree"


def test_failed_source_annotated_with_status():
    """Sources that failed to parse / produced no chunks are kept but flagged status=failed."""
    from agentpack.mapper import build_map
    from agentpack.models import ExtractionWarning
    good = SourceDocument(
        source_id="src_000", path="ok.md", type="markdown", checksum="x",
        blocks=[
            DocumentBlock(block_id="b0", source_id="src_000", type="heading",
                          text="Title", section_path=["Title"]),
            DocumentBlock(block_id="b1", source_id="src_000", type="paragraph",
                          text="some content here", section_path=["Title"]),
        ],
        warnings=[],
    )
    bad = SourceDocument(
        source_id="src_001", path="broken.pdf", type="pdf", checksum="y",
        blocks=[],
        warnings=[ExtractionWarning(source_id="src_001", type="parse_error", message="boom")],
    )
    chunks = chunk_document(good, max_tokens=100)  # bad has no blocks -> no chunks
    m = build_map({"name": "c", "generated_at": "t", "manifest": "manifest.yml"}, [good, bad], chunks)

    docs = {d["source_id"]: d for d in m["documents"]}
    assert docs["src_000"]["status"] == "success"
    assert docs["src_001"]["status"] == "failed"
    assert docs["src_001"]["sections"] == [], "a failed/empty source has no sections"


def test_golden_map_snapshot():
    """Structural regression guard: emitted map must match the committed snapshot."""
    from agentpack.mapper import build_map
    doc = _nested_doc()
    chunks = chunk_document(doc, max_tokens=40)
    actual = yaml.dump(
        build_map({"name": "golden", "generated_at": "2026-01-01T00:00:00+00:00",
                   "manifest": "manifest.yml"}, [doc], chunks),
        default_flow_style=False, sort_keys=False,
    )
    snapshot = Path(__file__).parent / "fixtures" / "expected_map.yml"
    if not snapshot.exists():
        snapshot.write_text(actual)  # bootstrap once; commit the result
    assert actual == snapshot.read_text(), (
        "map structure changed vs tests/fixtures/expected_map.yml; "
        "if intentional, delete that file to regenerate."
    )


# --- Phase B: descriptors wired into the map ---

def _has_descriptor(nodes):
    for n in nodes:
        if n["keyphrases"] or n["gist"]:
            return True
        if _has_descriptor(n["nodes"]):
            return True
    return False


def _all_empty(nodes):
    return all(
        not n["keyphrases"] and not n["gist"] and _all_empty(n["nodes"])
        for n in nodes
    )


def test_map_nodes_carry_descriptors_by_default():
    from agentpack.mapper import build_map
    doc = _nested_doc()
    chunks = chunk_document(doc, max_tokens=40)
    m = build_map({"name": "c", "generated_at": "t", "manifest": "manifest.yml"}, [doc], chunks)

    d = m["documents"][0]
    assert "topics" not in d, "synthesized doc topics were intentionally dropped (rollup bias)"
    assert "topics" not in m["corpus"], "synthesized corpus topics were intentionally dropped"
    assert d["summary"], "document should carry an extractive summary"
    assert _has_descriptor(d["sections"]), "section nodes carry the keyphrase/gist signal"
    assert m["corpus"]["summary"], "corpus should carry an extractive summary"


def test_enrich_false_yields_no_descriptors():
    from agentpack.mapper import build_map
    doc = _nested_doc()
    chunks = chunk_document(doc, max_tokens=40)
    m = build_map({"name": "c", "generated_at": "t", "manifest": "manifest.yml"},
                  [doc], chunks, enrich=False)

    d = m["documents"][0]
    assert d["summary"] is None
    assert "summary" not in m["corpus"]
    assert _all_empty(d["sections"])
