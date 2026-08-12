"""
agentpack.toml config loader.

Looks for agentpack.toml in the input directory (or CWD). Settings here
override CLI defaults so packs are reproducible across runs.

Example agentpack.toml:
    [pack]
    chunk_max_tokens = 800
    chunk_overlap = 0.15
    fast = false
    remove_empty_lines = false
    include = []
    exclude = []

    [graph]
    enabled = true
    df_cap = 0.30
    min_docs = 2
    similarity_threshold = 0.80
"""
import sys
import tomllib
from pathlib import Path
from typing import Any, Dict


_DEFAULTS: Dict[str, Any] = {
    "chunk_max_tokens": 800,
    "chunk_overlap": 0.15,
    "fast": False,
    "remove_empty_lines": False,
    "include": [],
    "exclude": [],
}

_GRAPH_DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "df_cap": 0.30,
    "min_docs": 2,
    "similarity_threshold": 0.80,
}


def _is_number(value: Any) -> bool:
    """int/float, excluding bool (bool subclasses int; TOML `true` must never
    silently pass a numeric range check)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_graph_settings(raw_graph: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a [graph] table against its allowed ranges. Out-of-range or
    wrong-type values fall back to the default with a stderr warning naming
    the key -- this never raises, matching the graph builder's own
    never-crash-the-pack posture."""
    settings = dict(_GRAPH_DEFAULTS)

    if "enabled" in raw_graph:
        settings["enabled"] = bool(raw_graph["enabled"])

    if "df_cap" in raw_graph:
        value = raw_graph["df_cap"]
        if _is_number(value) and 0 < value <= 1:
            settings["df_cap"] = value
        else:
            print(
                f"[agentpack] Warning: [graph] df_cap={value!r} is out of range "
                f"(0, 1]; using default {_GRAPH_DEFAULTS['df_cap']}.",
                file=sys.stderr,
            )

    if "min_docs" in raw_graph:
        value = raw_graph["min_docs"]
        if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
            settings["min_docs"] = value
        else:
            print(
                f"[agentpack] Warning: [graph] min_docs={value!r} must be an "
                f"integer >= 1; using default {_GRAPH_DEFAULTS['min_docs']}.",
                file=sys.stderr,
            )

    if "similarity_threshold" in raw_graph:
        value = raw_graph["similarity_threshold"]
        if _is_number(value) and 0 < value <= 1:
            settings["similarity_threshold"] = value
        else:
            print(
                f"[agentpack] Warning: [graph] similarity_threshold={value!r} is "
                f"out of range (0, 1]; using default "
                f"{_GRAPH_DEFAULTS['similarity_threshold']}.",
                file=sys.stderr,
            )

    return settings


def load_config(directory: str | Path) -> Dict[str, Any]:
    """Load agentpack.toml from `directory` (or CWD). Missing keys fall back to
    defaults. [graph] settings live under the returned "graph" key -- a
    separate namespace from the top-level [pack] keys, never merged."""
    cfg = dict(_DEFAULTS)
    cfg["graph"] = dict(_GRAPH_DEFAULTS)
    config_path = Path(directory) / "agentpack.toml"
    if config_path.exists():
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
        pack_section = raw.get("pack", {})
        for key in _DEFAULTS:
            if key in pack_section:
                cfg[key] = pack_section[key]
        cfg["graph"] = _validate_graph_settings(raw.get("graph", {}))
    return cfg
