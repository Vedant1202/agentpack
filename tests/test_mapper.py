"""Phase A1 — walking skeleton for the hierarchical knowledge map (map.yml).

Tests the deterministic structural tree: corpus -> document -> (flat) section -> chunk_ids,
plus the chunker change that persists the full section_path into chunk metadata.
"""
import yaml
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
    referenced = [cid for d in m["documents"] for s in d["sections"] for cid in s["chunk_ids"]]
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
