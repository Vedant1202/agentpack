from pathlib import Path
from agentpack.config import load_config

def test_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg["chunk_max_tokens"] == 800
    assert cfg["fast"] is False
    assert cfg["exclude"] == []


def test_toml_overrides_defaults(tmp_path):
    (tmp_path / "agentpack.toml").write_text(
        "[pack]\nchunk_max_tokens = 400\nfast = true\nexclude = ['*.log']\n"
    )
    cfg = load_config(tmp_path)
    assert cfg["chunk_max_tokens"] == 400
    assert cfg["fast"] is True
    assert cfg["exclude"] == ["*.log"]
    # unset key falls back to default
    assert cfg["chunk_overlap"] == 0.15


def test_partial_toml(tmp_path):
    (tmp_path / "agentpack.toml").write_text("[pack]\nremove_empty_lines = true\n")
    cfg = load_config(tmp_path)
    assert cfg["remove_empty_lines"] is True
    assert cfg["fast"] is False  # default
