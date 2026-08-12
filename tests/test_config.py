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


def test_graph_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg["graph"] == {
        "enabled": True,
        "df_cap": 0.30,
        "min_docs": 2,
        "similarity_threshold": 0.80,
    }


def test_graph_section_overrides_defaults(tmp_path):
    (tmp_path / "agentpack.toml").write_text(
        "[graph]\nenabled = false\ndf_cap = 0.5\nmin_docs = 3\nsimilarity_threshold = 0.9\n"
    )
    cfg = load_config(tmp_path)
    assert cfg["graph"] == {
        "enabled": False,
        "df_cap": 0.5,
        "min_docs": 3,
        "similarity_threshold": 0.9,
    }


def test_graph_partial_section_keeps_other_defaults(tmp_path):
    (tmp_path / "agentpack.toml").write_text("[graph]\nmin_docs = 3\n")
    cfg = load_config(tmp_path)
    assert cfg["graph"]["min_docs"] == 3
    assert cfg["graph"]["df_cap"] == 0.30  # default
    assert cfg["graph"]["enabled"] is True  # default


def test_graph_min_docs_one_is_valid(tmp_path):
    """min_docs = 1 is a deliberate opt-in (intra-document concepts), not an error."""
    (tmp_path / "agentpack.toml").write_text("[graph]\nmin_docs = 1\n")
    cfg = load_config(tmp_path)
    assert cfg["graph"]["min_docs"] == 1


def test_graph_df_cap_boundary_one_is_valid(tmp_path):
    """Range is (0, 1] -- 1.0 is a valid (if degenerate) upper bound."""
    (tmp_path / "agentpack.toml").write_text("[graph]\ndf_cap = 1.0\n")
    cfg = load_config(tmp_path)
    assert cfg["graph"]["df_cap"] == 1.0


def test_graph_df_cap_zero_falls_back_with_warning(tmp_path, capsys):
    (tmp_path / "agentpack.toml").write_text("[graph]\ndf_cap = 0\n")
    cfg = load_config(tmp_path)
    assert cfg["graph"]["df_cap"] == 0.30  # falls back to default
    err = capsys.readouterr().err
    assert "df_cap" in err


def test_graph_df_cap_above_one_falls_back_with_warning(tmp_path, capsys):
    (tmp_path / "agentpack.toml").write_text("[graph]\ndf_cap = 1.5\n")
    cfg = load_config(tmp_path)
    assert cfg["graph"]["df_cap"] == 0.30
    err = capsys.readouterr().err
    assert "df_cap" in err


def test_graph_min_docs_zero_falls_back_with_warning(tmp_path, capsys):
    (tmp_path / "agentpack.toml").write_text("[graph]\nmin_docs = 0\n")
    cfg = load_config(tmp_path)
    assert cfg["graph"]["min_docs"] == 2  # falls back to default
    err = capsys.readouterr().err
    assert "min_docs" in err


def test_graph_min_docs_bool_rejected(tmp_path, capsys):
    """TOML `true`/`false` parse as Python bool, which is an int subclass --
    must not silently become min_docs=1."""
    (tmp_path / "agentpack.toml").write_text("[graph]\nmin_docs = true\n")
    cfg = load_config(tmp_path)
    assert cfg["graph"]["min_docs"] == 2  # falls back to default
    err = capsys.readouterr().err
    assert "min_docs" in err


def test_graph_similarity_threshold_out_of_range_falls_back(tmp_path, capsys):
    (tmp_path / "agentpack.toml").write_text("[graph]\nsimilarity_threshold = 2.0\n")
    cfg = load_config(tmp_path)
    assert cfg["graph"]["similarity_threshold"] == 0.80
    err = capsys.readouterr().err
    assert "similarity_threshold" in err


def test_graph_section_does_not_affect_pack_keys(tmp_path):
    """[graph] and [pack] are independent namespaces."""
    (tmp_path / "agentpack.toml").write_text(
        "[pack]\nchunk_max_tokens = 400\n\n[graph]\nmin_docs = 5\n"
    )
    cfg = load_config(tmp_path)
    assert cfg["chunk_max_tokens"] == 400
    assert cfg["graph"]["min_docs"] == 5
    assert cfg["fast"] is False  # untouched pack default
