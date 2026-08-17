"""Deterministic, offline, domain-agnostic node descriptors for the knowledge map (Phase B).

- ``keyphrases`` — YAKE (statistical, language-independent, no training/corpora/models)
- ``gist`` — extractive 1-line summary via TextRank (networkx PageRank over sentence overlap)

No LLM, no network, no model/data downloads. ``yake`` and ``networkx`` are heavy-import-free
so they are imported lazily; if ``yake`` is unavailable, ``keyphrases`` degrades to ``[]`` rather
than raising, so a pack can still build a structural map.

Candidate text is filtered for layout noise before extraction — TOC dot-leader entries,
markdown table debris, and mostly-punctuation/number spans — so summaries never surface
table-of-contents rows (see ``_is_noise``/``_sentences``).
"""
import math
import re
from typing import List, Optional

_WORD = re.compile(r"[A-Za-z0-9']+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_MIN_CHARS = 20
_DOT_LEADER = re.compile(r"(?:\.\s?){4,}")


def _is_noise(span: str) -> bool:
    """Layout noise (TOC entries, table debris) that must never become a keyphrase or gist
    candidate: dot-leader spans and spans that are mostly punctuation/numbers."""
    if _DOT_LEADER.search(span):
        return True
    solid = [c for c in span if not c.isspace()]
    if not solid:
        return True
    return sum(c.isalpha() for c in solid) < len(solid) / 2


def keyphrases(text: Optional[str], top: int = 6, max_ngram: int = 3) -> List[str]:
    """Top salient keyphrases for a block of text (YAKE; lower internal score = more salient)."""
    text = " ".join(_sentences(text or ""))
    if len(text) < _MIN_CHARS:
        return []
    try:
        import yake
    except ImportError:
        return []
    extractor = yake.KeywordExtractor(lan="en", n=max_ngram, top=top, dedupLim=0.8)
    return [phrase for phrase, _score in extractor.extract_keywords(text)]


def _sentences(text: str) -> List[str]:
    """Candidate sentences for enrichment, with layout noise dropped.

    Splitting runs per line, then per markdown table cell (``|``), then on sentence
    punctuation — so a TOC/table fragment glued onto a prose span (block texts are
    space-joined upstream) is discarded on its own, without taking the prose with it.
    """
    out = []
    for line in text.splitlines():
        for cell in line.split("|"):
            for s in _SENTENCE.split(cell):
                s = s.strip()
                if s and not _is_noise(s):
                    out.append(s)
    return out


def _similarity(a: set, b: set) -> float:
    """Classic TextRank sentence similarity: shared words normalised by length."""
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    if overlap == 0:
        return 0.0
    return overlap / (math.log(len(a) + 1) + math.log(len(b) + 1) + 1e-9)


def gist(text: Optional[str], max_sentences: int = 1) -> str:
    """A short extractive summary: the most central sentence(s) by TextRank, in original order."""
    sentences = _sentences((text or "").strip())
    # Defense in depth for future uncapped callers: the O(N^2) graph below is unusable well
    # before 400 sentences (~well past any 8000-char caller-side cap).
    sentences = sentences[:400]
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    import networkx as nx

    tokens = [{w.lower() for w in _WORD.findall(s)} for s in sentences]
    graph = nx.Graph()
    graph.add_nodes_from(range(len(sentences)))
    for i in range(len(sentences)):
        for j in range(i + 1, len(sentences)):
            sim = _similarity(tokens[i], tokens[j])
            if sim > 0:
                graph.add_edge(i, j, weight=sim)

    try:
        scores = nx.pagerank(graph, weight="weight")
    except nx.PowerIterationFailedConvergence:
        scores = {i: 0.0 for i in range(len(sentences))}

    ranked = sorted(range(len(sentences)), key=lambda i: scores.get(i, 0.0), reverse=True)
    chosen = sorted(ranked[:max_sentences])  # restore original reading order
    return " ".join(sentences[i] for i in chosen)
