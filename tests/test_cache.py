import pytest
from pathlib import Path
from agentpack.cache import make_key, cache_get, cache_set


def test_round_trip(tmp_path):
    key = make_key("sha256abc", "parser_v1", "opts_default")
    assert cache_get(tmp_path, key) is None  # cold miss

    cache_set(tmp_path, key, {"blocks": [1, 2, 3]})
    result = cache_get(tmp_path, key)
    assert result == {"blocks": [1, 2, 3]}


def test_version_change_misses(tmp_path):
    """Changing a version component must produce a different key → cache miss."""
    key_v1 = make_key("sha256abc", "parser_v1")
    key_v2 = make_key("sha256abc", "parser_v2")
    assert key_v1 != key_v2

    cache_set(tmp_path, key_v1, "value_v1")
    assert cache_get(tmp_path, key_v2) is None


def test_overwrite(tmp_path):
    key = make_key("x")
    cache_set(tmp_path, key, "first")
    cache_set(tmp_path, key, "second")
    assert cache_get(tmp_path, key) == "second"


def test_cache_db_created(tmp_path):
    key = make_key("y")
    cache_set(tmp_path, key, 42)
    assert (tmp_path / "cache.db").exists()
