"""Build the corpus concept graph (graph.yml) from pack output artifacts.

Pure post-processor: reads map.yml + manifest.yml already written to
pack_dir. Never imports parsers/chunker/cache/trust.py (see
docs/specs/0003-corpus-concept-graph.md §3) -- this is what makes
`agentpack graph <pack_dir>` (rebuild) and the pack-time hook the SAME
code path, so rebuild parity holds by construction.

T1 scope: document + section nodes and `contains` edges. T2 adds concept
promotion and `mentions` edges. `references` (T3) and communities (T4)
extend _build_graph_inner in later tasks without touching this module's
public surface.
"""
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from agentpack.config import _GRAPH_DEFAULTS
from agentpack.models import CorpusGraph, GraphEdge, GraphNode

# Fixed structural gate, independent of the user-tunable [graph] params: a
# graph across fewer than this many *successfully parsed* documents has no
# cross-document value by construction (spec §3) -- not the same knob as
# params["min_docs"], which gates individual CONCEPT promotion (T2).
_MIN_SUCCESSFUL_SOURCES = 2

# Concept normalization recipe (spec §4) -- the ONLY place a concept slug is
# minted. Two keyphrases with the same slug are the same concept.
_SLUG_NON_WORD = re.compile(r"[^\w]+")
_SLUG_REPEAT_UNDERSCORE = re.compile(r"_+")
_MIN_SLUG_LENGTH = 4


def _slug(phrase: str) -> str:
    return _SLUG_REPEAT_UNDERSCORE.sub("_", _SLUG_NON_WORD.sub("_", phrase.casefold())).strip("_")


def _passes_length_gate(slug: str) -> bool:
    """>=4 chars and not purely numeric/underscore (spec §4, gate 3)."""
    if len(slug) < _MIN_SLUG_LENGTH:
        return False
    stripped = slug.replace("_", "")
    return bool(stripped) and not stripped.isdigit()


def _iter_all_sections(sections, source_id: str):
    """Yield (section_dict, source_id) for every section in a document's
    map.yml tree, at every depth -- concepts can be promoted from a
    keyphrase anywhere in the tree, not just top-level sections."""
    for section in sections or []:
        yield section, source_id
        yield from _iter_all_sections(section.get("nodes") or [], source_id)


def _promote_concepts(
    map_docs_by_id: Dict[str, dict],
    existing_section_ids: set,
    params: Dict,
) -> Tuple[List[GraphNode], List[GraphEdge]]:
    """Walk every section (any depth, all documents), promote recurring
    keyphrases into concept nodes per the three gates (spec §4), and emit
    `mentions` edges.

    A section that ends up with >=1 mentions edge but has no node yet (i.e.
    it's non-top-level -- top-level sections already got a node from the
    contains-edge pass in _build_graph_inner) gains one here.
    existing_section_ids is mutated in place so a section mentioning
    multiple promoted concepts doesn't get double-added.
    """
    total_sections = 0
    # slug -> [(source_id, node_id, section_title, raw_keyphrase_text), ...]
    contributions: Dict[str, List[Tuple[str, str, str, str]]] = {}

    for map_doc in map_docs_by_id.values():
        source_id = map_doc.get("source_id")
        for section, sid in _iter_all_sections(map_doc.get("sections"), source_id):
            total_sections += 1
            node_id = section.get("node_id")
            if not node_id:
                continue
            title = section.get("title") or node_id
            seen_slugs_in_section: set = set()
            for phrase in (section.get("keyphrases") or []):
                slug = _slug(phrase)
                if not slug or slug in seen_slugs_in_section:
                    continue
                seen_slugs_in_section.add(slug)
                contributions.setdefault(slug, []).append((sid, node_id, title, phrase))

    new_nodes: List[GraphNode] = []
    new_edges: List[GraphEdge] = []
    if total_sections == 0:
        return new_nodes, new_edges

    min_docs = params["min_docs"]
    df_cap = params["df_cap"]

    for slug, occurrences in contributions.items():
        if not _passes_length_gate(slug):
            continue
        distinct_docs = {sid for sid, _nid, _title, _phrase in occurrences}
        if len(distinct_docs) < min_docs:
            continue
        # One occurrence per contributing SECTION (already deduped per-section
        # above), so len(occurrences) is a section count, not a phrase count.
        if len(occurrences) / total_sections > df_cap:
            continue

        # Promoted. Label = most frequent surface form; ties broken lexically
        # (ascending) so the choice is deterministic regardless of collection order.
        label_counts = Counter(phrase for _sid, _nid, _title, phrase in occurrences)
        label = sorted(label_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

        concept_id = f"c_{slug}"
        new_nodes.append(GraphNode(id=concept_id, kind="concept", label=label))

        seen_sections_for_slug: set = set()
        for sid, node_id, title, _phrase in occurrences:
            if node_id in seen_sections_for_slug:
                continue
            seen_sections_for_slug.add(node_id)
            if node_id not in existing_section_ids:
                new_nodes.append(GraphNode(id=node_id, kind="section", label=title, doc=sid))
                existing_section_ids.add(node_id)
            new_edges.append(GraphEdge(
                source=node_id, target=concept_id, relation="mentions", basis="keyphrase",
            ))

    return new_nodes, new_edges


def _load_yaml(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_graph_inner(base: Path, params: Dict) -> Optional[dict]:
    manifest = _load_yaml(base / "manifest.yml")
    if manifest is None:
        print("[agentpack] Note: no manifest.yml found; skipping graph.yml.", file=sys.stderr)
        return None

    sources = manifest.get("sources", []) or []
    n_success = sum(1 for s in sources if s.get("status") == "success")
    if n_success < _MIN_SUCCESSFUL_SOURCES:
        print(
            f"[agentpack] Note: only {n_success} successfully parsed source(s); "
            f"skipping graph.yml (needs >= {_MIN_SUCCESSFUL_SOURCES} documents "
            f"for cross-document value).",
            file=sys.stderr,
        )
        return None

    map_obj = _load_yaml(base / "map.yml") or {}
    map_docs_by_id = {
        d.get("source_id"): d for d in (map_obj.get("documents", []) or [])
    }

    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    existing_section_ids: set = set()

    for src in sources:
        source_id = src.get("id")
        if not source_id:
            continue
        nodes.append(GraphNode(
            id=source_id, kind="document", label=src.get("path", source_id),
        ))

        map_doc = map_docs_by_id.get(source_id)
        if not map_doc:
            continue
        for section in (map_doc.get("sections", []) or []):
            node_id = section.get("node_id")
            if not node_id:
                continue
            nodes.append(GraphNode(
                id=node_id, kind="section",
                label=section.get("title") or node_id, doc=source_id,
            ))
            existing_section_ids.add(node_id)
            edges.append(GraphEdge(
                source=source_id, target=node_id,
                relation="contains", basis="structural",
            ))

    concept_nodes, concept_edges = _promote_concepts(map_docs_by_id, existing_section_ids, params)
    nodes.extend(concept_nodes)
    edges.extend(concept_edges)

    nodes.sort(key=lambda n: (n.kind, n.id))
    edges.sort(key=lambda e: (e.source, e.target, e.relation))

    pack_meta = manifest.get("pack", {}) or {}
    graph = CorpusGraph(
        graph_version=1,
        pack={
            "name": pack_meta.get("name", base.name),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "manifest": "manifest.yml",
        },
        params=params,
        nodes=nodes,
        edges=edges,
        communities=[],
    )
    return graph.model_dump()


def build_graph(pack_dir: str, params: Optional[Dict] = None) -> Optional[dict]:
    """Build the corpus concept graph from an existing pack's map.yml +
    manifest.yml. Returns a plain dict (validated via CorpusGraph) ready for
    yaml.dump, or None if the graph should not be built (too few successful
    sources, or missing/corrupt inputs). Never raises -- the whole body runs
    inside one outer try/except, mirroring trust.py's never-crash-the-pack
    posture: a malformed pack degrades to "no graph.yml", never an exception
    that would take the rest of the pack down with it.
    """
    try:
        return _build_graph_inner(Path(pack_dir), dict(params or _GRAPH_DEFAULTS))
    except Exception as e:
        print(
            f"[agentpack] Warning: graph build failed, skipping graph.yml ({e}).",
            file=sys.stderr,
        )
        return None


def write_graph(pack_dir: str, params: Optional[Dict] = None) -> bool:
    """Build the graph and write graph.yml next to manifest.yml. Returns True
    if graph.yml was written, False if the build was skipped or failed (see
    build_graph -- this function itself never raises either)."""
    graph_obj = build_graph(pack_dir, params)
    if graph_obj is None:
        return False
    out = Path(pack_dir) / "graph.yml"
    with open(out, "w", encoding="utf-8") as f:
        yaml.dump(graph_obj, f, default_flow_style=False, sort_keys=False)
    return True
