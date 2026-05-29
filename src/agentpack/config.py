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
"""
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


def load_config(directory: str | Path) -> Dict[str, Any]:
    """Load agentpack.toml from `directory` (or CWD). Missing keys fall back to defaults."""
    cfg = dict(_DEFAULTS)
    config_path = Path(directory) / "agentpack.toml"
    if config_path.exists():
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
        pack_section = raw.get("pack", {})
        for key in _DEFAULTS:
            if key in pack_section:
                cfg[key] = pack_section[key]
    return cfg
