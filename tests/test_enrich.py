"""Phase B — deterministic, offline node descriptors (YAKE keyphrases + TextRank gist).

These must be domain-agnostic, deterministic, and never touch the network.
"""


def test_keyphrases_surface_salient_terms():
    from agentpack.enrich import keyphrases
    text = ("The reconciliation of non-GAAP measures includes adjusted EBIT and "
            "adjusted free cash flow. Adjusted EBIT margin improved year over year.")
    kps = keyphrases(text, top=6)
    assert kps, "should return keyphrases"
    joined = " ".join(kps).lower()
    assert any(t in joined for t in ("ebit", "non-gaap", "cash flow")), kps


def test_keyphrases_short_or_empty_text_returns_empty():
    from agentpack.enrich import keyphrases
    assert keyphrases("Too short.") == []
    assert keyphrases("") == []
    assert keyphrases(None) == []


def test_gist_is_extractive_single_sentence():
    from agentpack.enrich import gist
    text = ("Apple reported quarterly revenue of 119 billion dollars. "
            "The iPhone segment grew six percent year over year. "
            "Services set an all-time revenue record this quarter. "
            "The company expects similar revenue in the next quarter.")
    g = gist(text, max_sentences=1)
    assert g, "gist should be non-empty"
    assert g in text, "gist must be extractive (a verbatim source sentence)"


def test_gist_short_text_passthrough():
    from agentpack.enrich import gist
    assert gist("One sentence only.") == "One sentence only."
    assert gist("") == ""


def test_enrichment_is_deterministic():
    from agentpack.enrich import keyphrases, gist
    text = ("Segment information and revenue growth this year. Adjusted EBIT by reporting segment. "
            "Net debt reconciliation and free cash flow analysis for the full fiscal year.")
    assert keyphrases(text) == keyphrases(text)
    assert gist(text) == gist(text)


def test_enrichment_works_offline(monkeypatch):
    """Descriptors must not touch the network (no model downloads, no API)."""
    import socket

    def _no_net(*a, **k):
        raise AssertionError("network access attempted during enrichment")

    monkeypatch.setattr(socket.socket, "connect", _no_net)
    from agentpack.enrich import keyphrases, gist
    text = ("Reconciliation of adjusted EBITDA and net debt for the group. "
            "Free cash flow improved across all reporting segments this fiscal year.")
    assert keyphrases(text)
    assert gist(text)
