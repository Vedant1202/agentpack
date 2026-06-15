"""Deterministic, offline, domain-agnostic node descriptors for the knowledge map (Phase B).

- ``keyphrases`` — YAKE (statistical, language-independent, no training/corpora/models)
- ``gist`` — extractive 1-line summary via TextRank (networkx PageRank over sentence overlap)

No LLM, no network, no model/data downloads. ``yake`` and ``networkx`` are heavy-import-free
so they are imported lazily; if ``yake`` is unavailable, ``keyphrases`` degrades to ``[]`` rather
than raising, so a pack can still build a structural map.
"""
import math
import re
from typing import List, Optional

_WORD = re.compile(r"[A-Za-z0-9']+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_MIN_CHARS = 20


def keyphrases(text: Optional[str], top: int = 6, max_ngram: int = 3) -> List[str]:
    """Top salient keyphrases for a block of text (YAKE; lower internal score = more salient)."""
    text = (text or "").strip()
    if len(text) < _MIN_CHARS:
        return []
    try:
        import yake
    except ImportError:
        return []
    extractor = yake.KeywordExtractor(lan="en", n=max_ngram, top=top, dedupLim=0.8)
    return [phrase for phrase, _score in extractor.extract_keywords(text)]


def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE.split(text) if s.strip()]


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
    text = (text or "").strip()
    sentences = _sentences(text)
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
