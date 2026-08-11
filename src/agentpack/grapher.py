"""Build the corpus concept graph (graph.yml) from pack output artifacts.

Pure post-processor: reads map.yml + manifest.yml already written to
pack_dir. Never imports parsers/chunker/cache/trust.py (see
docs/specs/0003-corpus-concept-graph.md §3) -- this is what makes
`agentpack graph <pack_dir>` (rebuild) and the pack-time hook the SAME
code path, so rebuild parity holds by construction.

T1 scope: document + section nodes and `contains` edges only. Concept
promotion/`mentions` (T2), `references` (T3), and communities (T4) extend
_build_graph_inner in later tasks without touching this module's public
surface.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from agentpack.config import _GRAPH_DEFAULTS
from agentpack.models import CorpusGraph, GraphEdge, GraphNode

# Fixed structural gate, independent of the user-tunable [graph] params: a
# graph across fewer than this many *successfully parsed* documents has no
# cross-document value by construction (spec §3) -- not the same knob as
# params["min_docs"], which gates individual CONCEPT promotion (T2).
_MIN_SUCCESSFUL_SOURCES = 2


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
            edges.append(GraphEdge(
                source=source_id, target=node_id,
                relation="contains", basis="structural",
            ))

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
