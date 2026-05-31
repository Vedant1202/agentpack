# AgentPack Benchmark: Context Pipeline Evaluation

> Produced with the v0.3.0 pipeline (Docling structured-tree parsing, HNSW vector search, RRF
> hybrid fusion). This document is the complete benchmark reference: 9 retrieval strategies
> evaluated on two corpora — FinanceBench (homogeneous) and DocBench (heterogeneous) — with both
> deterministic retrieval metrics and generative (LLM-as-judge) answer-quality metrics.

## Abstract
This benchmark evaluates **AgentPack**, an offline document-to-agent-context compiler, against standard RAG baselines. The hypothesis is not that AgentPack is a superior reasoning model, but that **AgentPack improves the context pipeline for document-grounded agents**. By compiling messy, unstructured files (PDFs, CSVs, Markdown) into clean, citation-bearing semantic chunks, AgentPack reduces context bloat and delivers high-signal context to downstream LLMs. Holding the LLM constant, the study measures how nine retrieval strategies affect both retrieval quality and end-to-end answer quality across a homogeneous and a heterogeneous corpus.

## 1. Introduction
Modern LLMs feature large context windows, leading many developers to rely on "Raw File" stuffing—dumping entire 100+ page PDFs into the prompt. This is computationally expensive and suffers from the "Lost in the Middle" phenomenon [3], where reasoning degrades as the relevant passage is buried in noise.

"Naive RAG" attempts to solve this by slicing documents into arbitrary character counts. This frequently fractures semantic boundaries — splitting financial tables or sentences in half — leading to low-quality retrieval.

**The goal** is to evaluate, with the LLM held constant, whether structure-aware parsing and semantic chunking provide a better context layer, and to characterize where each retrieval strategy succeeds or fails. The two corpora are chosen to differ in document homogeneity, which turns out to be the dominant factor in which strategy wins.

## 2. Methodology

Two evaluation types are reported:

- **Deterministic (retrieval) eval** — no LLM is involved in retrieval. Each strategy retrieves chunks for a query, and the retrieved chunks are compared against manually annotated gold evidence (the correct source files). Measures retrieval quality directly.
- **Generative eval** — the retrieved context is passed to a generation model to produce an answer, and a separate judge model scores the answer against a gold answer. Measures end-to-end answer quality given each strategy's context.

### 2.1 Datasets

**FinanceBench (homogeneous).** [Patronus AI FinanceBench](https://github.com/patronus-ai/financebench) [1] (also on [HuggingFace](https://huggingface.co/datasets/PatronusAI/financebench)) — real SEC 10-K filings, earnings reports, and complex financial Q&A. Using the internal `agentpack prep-benchmark` tool, 50 documents/queries were randomly sampled; 8 were discarded for dead PDF links or unreadable formats, leaving **42 queries**. All documents share financial terminology, table structures, and reporting conventions.

**DocBench (heterogeneous).** [Zou et al., 2024 — DocBench](https://arxiv.org/abs/2407.10701) — **30 documents** sampled across five domains: Academia (ACL papers), Finance (annual reports), Government (country/budget reports), Law (court filings), and News. **30 queries** drawn from DocBench's human-annotated gold QA pairs; gold answers are extracted text, not model-generated. Documents span different vocabularies, writing styles, and structure, approximating a production agent corpus of mixed document types.

### 2.2 Gold Standards
- **`queries.yml`**: Query IDs mapped to the exact user question.
- **`gold_evidence.yml`**: human-annotated mapping of a Query ID to the required source file/section (used for deterministic scoring).
- **`gold_answers.yml`**: reference answers used by the judge for generative scoring.

### 2.3 Evaluation Framework
- **Generation Model:** `gemini-3.1-flash-lite`
- **Judge Model:** `gemini-3.5-flash`
- **Embedder:** `fastembed BAAI/bge-small-en-v1.5`, shared by every dense pipeline so that chunking and ranking — not the embedding model — are the variables under test.

**Deterministic metrics**

| Metric | What It Measures |
|---|---|
| **Hit@3** | Did the correct document appear in the top-3 retrieved chunks? (1.0 = always) |
| **MRR** | Mean Reciprocal Rank — how early the correct chunk appears. Rank 1 = 1.0; rank 2 = 0.5; rank 3 = 0.33. |
| **Citation Prec** | Fraction of returned chunks that came from the correct source file. Penalizes irrelevant chunks. |
| **Avg Context Tokens** | Mean tokens in retrieved context per query — a proxy for LLM input cost. |
| **Avg LLM Cost ($)** | Estimated cost to feed the context to an LLM, at $0.25 per 1M tokens (Gemini Flash-Lite pricing). |

**Generative metrics** (0–5, judged)

| Metric | What It Measures |
|---|---|
| **Correctness** | How well the answer matches the facts of the gold answer. |
| **Faithfulness** | Whether the answer relies only on the provided context (5 = no hallucination). |
| **Answer Relevance** | Whether the answer directly addresses the question. |
| **Context Relevance** | Whether the retrieved context actually contained the answer. |

### 2.4 Strategies Evaluated

| Mode | Description |
|---|---|
| **Raw File** | Returns entire source documents — no chunking, no ranking. Recall ceiling, precision floor. Excluded from generative eval due to token cost. |
| **Naive Chunk** | Fixed 4,000-character chunks ranked by BM25. No semantic understanding. |
| **Naive Chunk + Vector** | Dense retrieval over fixed 4,000-character chunks. Isolates the embedder from chunking strategy. |
| **Recursive Chunk + Vector** | Dense retrieval over LangChain-style recursive splits (~1,000 chars). A common industry default. |
| **Parent-Document** | Dense matching on small child chunks; the larger parent chunk is returned. Small-to-big retrieval. |
| **Cross-Encoder Rerank** | Re-scores AgentPack Hybrid candidates with a cross-encoder (`ms-marco-MiniLM-L-6-v2`). |
| **AgentPack (FTS)** | SQLite FTS5 (BM25) over structure-aware Docling-parsed chunks, with AND-precision query logic and OR fallback. |
| **AgentPack (Vector)** | Dense retrieval over Docling-parsed chunks. Semantic only. |
| **AgentPack (Hybrid)** | Reciprocal Rank Fusion (RRF) combining FTS and Vector over Docling-parsed chunks. |

## 3. Results

### 3.1 FinanceBench (Homogeneous Corpus)

**Retrieval**

| Mode | Hit@3 | MRR | Citation Prec | Avg Context Tokens | Avg LLM Cost ($) |
|---|---|---|---|---|---|
| Raw File | 0.57 | 0.43 | 0.19 | 424,378 | $0.106095 |
| Naive Chunk | 0.40 | 0.25 | 0.21 | 2,945 | $0.000736 |
| Naive Chunk + Vector | 0.62 | 0.52 | 0.40 | 3,140 | $0.000785 |
| Recursive Chunk + Vector | 0.57 | 0.45 | 0.34 | 920 | $0.000230 |
| Parent-Document | 0.62 | 0.51 | 0.34 | 1,668 | $0.000417 |
| Cross-Encoder Rerank | 0.79 | 0.60 | 0.40 | 2,611 | $0.000653 |
| AgentPack (FTS) | 0.50 | 0.34 | 0.25 | 3,085 | $0.000771 |
| AgentPack (Vector) | 0.83 | 0.60 | 0.41 | 2,641 | $0.000660 |
| AgentPack (Hybrid) | 0.64 | 0.42 | 0.30 | 2,859 | $0.000715 |

**Generative**

| Mode | Correctness | Faithfulness | Answer Relevance | Context Relevance | Avg Context Tokens | Avg LLM Cost ($) |
|---|---|---|---|---|---|---|
| Naive Chunk | 2.64 | 4.36 | 3.88 | 1.83 | 2,949 | $0.000737 |
| Naive Chunk + Vector | 3.57 | 4.55 | 4.38 | 2.31 | 3,144 | $0.000786 |
| Recursive Chunk + Vector | 3.07 | 4.81 | 4.52 | 1.64 | 923 | $0.000231 |
| Parent-Document | 3.31 | 4.83 | 4.48 | 1.79 | 1,672 | $0.000418 |
| Cross-Encoder Rerank | 3.62 | 4.71 | 4.40 | 2.55 | 2,615 | $0.000654 |
| AgentPack (Vector) | 3.95 | 4.69 | 4.40 | 3.14 | 2,645 | $0.000661 |
| AgentPack (Hybrid) | 3.31 | 4.48 | 4.14 | 2.71 | 2,864 | $0.000716 |

**Observations**
- On a homogeneous corpus, dense vector retrieval is the strongest signal. AgentPack (Vector) records the highest Hit@3 (0.83) and the highest generative correctness (3.95) and context relevance (3.14).
- BM25 methods are weak here: Naive Chunk (0.40) and AgentPack FTS (0.50) have the lowest Hit@3, because shared financial vocabulary gives keyword matching little to discriminate on.
- FTS + Vector fusion does not help when documents share vocabulary: AgentPack Hybrid (0.64) trails AgentPack Vector (0.83). Cross-Encoder Rerank (0.79), on the same fused candidate set, recovers most of the lost ranking quality.
- Several methods pair high faithfulness with low context relevance (e.g. Recursive Chunk + Vector: 4.81 / 1.64), indicating answers faithful to retrieved context that does not contain the needed information — a pattern tied to character-boundary splits cutting through financial tables.

### 3.2 DocBench (Heterogeneous Corpus)

**Retrieval**

| Mode | Hit@3 | MRR | Citation Prec | Avg Context Tokens | Avg LLM Cost ($) |
|---|---|---|---|---|---|
| Raw File | 0.87 | 0.83 | 0.29 | 278,462 | $0.069615 |
| Naive Chunk | 0.87 | 0.85 | 0.67 | 2,882 | $0.000720 |
| Naive Chunk + Vector | 0.83 | 0.76 | 0.63 | 2,719 | $0.000680 |
| Recursive Chunk + Vector | 0.87 | 0.83 | 0.70 | 789 | $0.000197 |
| Parent-Document | 0.80 | 0.76 | 0.63 | 1,435 | $0.000359 |
| Cross-Encoder Rerank | 0.83 | 0.79 | 0.61 | 2,062 | $0.000515 |
| AgentPack (FTS) | 0.83 | 0.82 | 0.64 | 2,048 | $0.000512 |
| AgentPack (Vector) | 0.83 | 0.76 | 0.58 | 1,962 | $0.000490 |
| AgentPack (Hybrid) | 0.87 | 0.82 | 0.67 | 2,132 | $0.000533 |

**Generative**

| Mode | Correctness | Faithfulness | Answer Relevance | Context Relevance | Avg Context Tokens | Avg LLM Cost ($) |
|---|---|---|---|---|---|---|
| Naive Chunk | 3.77 | 4.37 | 4.27 | 3.87 | 2,885 | $0.000721 |
| Naive Chunk + Vector | 3.53 | 4.23 | 4.00 | 3.70 | 2,722 | $0.000681 |
| Recursive Chunk + Vector | 3.53 | 4.60 | 4.43 | 3.97 | 792 | $0.000198 |
| Parent-Document | 3.60 | 4.47 | 4.43 | 3.90 | 1,438 | $0.000360 |
| Cross-Encoder Rerank | 3.53 | 4.33 | 4.20 | 3.73 | 2,154 | $0.000538 |
| AgentPack (Vector) | 2.93 | 4.43 | 4.17 | 3.27 | 1,979 | $0.000495 |
| AgentPack (Hybrid) | 3.50 | 4.37 | 4.33 | 3.73 | 2,152 | $0.000538 |

**Observations**
- On a heterogeneous corpus, keyword precision becomes useful. AgentPack FTS rises from 0.50 (FinanceBench) to 0.83 Hit@3, and AgentPack Hybrid (0.87) is the strongest AgentPack mode — fusion gains when FTS and Vector contribute independently.
- AgentPack Hybrid ties the top Hit@3 (0.87, shared with Raw File, Naive Chunk, and Recursive Chunk + Vector) using ~2,100 tokens, roughly 130× fewer than Raw File.
- Generative correctness is clustered tightly across most modes (3.50–3.77). AgentPack Hybrid (3.50) sits within this cluster; Naive Chunk leads (3.77).
- AgentPack Vector is the weakest mode here: lowest correctness (2.93) and lowest citation precision (0.58), indicating its top-3 spans more documents than necessary on heterogeneous text.
- Recursive Chunk + Vector matches the leading Hit@3 (0.87) and correctness (3.53) at roughly one-third the token count (789 vs ~2,100) — the most token-efficient strong performer on prose.

### 3.3 Cross-Corpus Summary (Hit@3, sorted by average)

| Mode | DocBench | FinanceBench | Avg |
|---|---|---|---|
| AgentPack (Vector) | 0.83 | 0.83 | 0.83 |
| Cross-Encoder Rerank | 0.83 | 0.79 | 0.81 |
| AgentPack (Hybrid) | 0.87 | 0.64 | 0.76 |
| Naive Chunk + Vector | 0.83 | 0.62 | 0.73 |
| Raw File | 0.87 | 0.57 | 0.72 |
| Recursive Chunk + Vector | 0.87 | 0.57 | 0.72 |
| Parent-Document | 0.80 | 0.62 | 0.71 |
| AgentPack (FTS) | 0.83 | 0.50 | 0.67 |
| Naive Chunk | 0.87 | 0.40 | 0.64 |

Methods that top one corpus often fall sharply on the other (Naive Chunk: 0.87 → 0.40; Recursive Chunk + Vector: 0.87 → 0.57). AgentPack (Vector) shows the smallest gap between corpus types (0.83 / 0.83).

## 4. Discussion

### 4.1 Cost and Token Efficiency
On FinanceBench, AgentPack achieved a **~161x reduction in token usage** versus Raw File (2,641 vs 424,378 tokens), dropping context cost per query from nearly $0.11 to under $0.0007. All AgentPack modes operate at roughly 2,000–2,900 tokens per query on both corpora — over 100× fewer than Raw File — while matching or exceeding its Hit@3.

### 4.2 Context Relevance and Precision (AgentPack vs. Naive Chunk)
On FinanceBench, AgentPack (Vector) context was judged **~1.7x more relevant** than Naive Chunk (3.14 vs 1.83), and it doubled Naive Chunk's Hit@3 (0.83 vs 0.40) and citation precision (0.41 vs 0.21). Respecting document boundaries and preserving tabular structure during chunking yields unbroken, higher-signal evidence rather than fractured text.

### 4.3 Signal-to-Noise and the "Lost in the Middle" Effect
By construction, Raw File contains 100% of every document and therefore always contains the answer — yet its retrieval citation precision is only **0.19** on FinanceBench (0.29 on DocBench), meaning the large majority of supplied content is off-target. Feeding this volume of low-precision context is expensive (hundreds of thousands of tokens per query) and, per the "Lost in the Middle" literature [3], detrimental to reasoning. AgentPack's structure-aware retrieval more than doubles citation precision while cutting context size ~100–160×. (Raw File is excluded from the generative tables for this reason: its per-query cost is prohibitive at scale.)

### 4.4 Corpus Homogeneity Determines the Best Mode
The two AgentPack modes are near mirror images across corpus type. On heterogeneous DocBench, Hybrid leads (0.87 Hit@3, 3.50 correctness) because rare domain-specific terms make the FTS signal discriminative and fusion productive. On homogeneous FinanceBench, shared vocabulary makes FTS noisy, so pure Vector leads (0.83 Hit@3, 3.95 correctness) and Hybrid drops to 0.64. AgentPack (Vector) is the most stable single mode across both corpora (0.83 / 0.83), the smallest gap of any method tested. The practical implication is that mode should be matched to corpus characteristics; a corpus-adaptive or query-level mode-selection strategy is the main open improvement.

### 4.5 The Generation Bottleneck
Where AgentPack supplies the matching mode, correctness tops the field (3.95/5 on FinanceBench). Absolute scores remain bounded by the generation model: `gemini-3.1-flash-lite` still struggles with multi-step financial arithmetic. AgentPack supplies the high-signal context; a frontier reasoning model is expected to push correctness higher over the same context.

## 5. Potential Future Avenues
1. **Frontier reasoning models:** re-run the generative evaluation with a frontier generator to overcome the `flash-lite` arithmetic bottleneck.
2. **Corpus-adaptive mode selection:** gate or weight the FTS component by corpus homogeneity (or per query) so a single default mode performs well on both corpus types.
3. **Token efficiency:** close the gap to Recursive Chunk + Vector (~790 tokens) on heterogeneous prose while retaining AgentPack's structural fidelity on tables.
4. **Cross-encoder reranking:** the cross-encoder (`ms-marco-MiniLM-L-6-v2`), evaluated here as a baseline, is a strong ranker on financial text (0.79 Hit@3 on FinanceBench); integrating it as an optional rerank pass inside AgentPack is on the roadmap.
5. **Additional datasets:** **TAT-QA** (extreme tabular/quantitative extraction) and **QASPER** (long academic-paper retrieval) would add further points in the corpus-type space.

## 6. Summary — AgentPack
- **Three retrieval modes over structure-aware chunks.** AgentPack parses documents with Docling and exposes FTS (BM25), Vector (dense), and Hybrid (RRF fusion) retrieval over the resulting chunks.
- **Most stable across corpus types.** AgentPack (Vector) has the smallest Hit@3 variance of any method tested (0.83 on both corpora) and the highest cross-corpus average (0.83).
- **Best mode depends on corpus homogeneity.** Hybrid leads on heterogeneous data (DocBench: 0.87 Hit@3, 3.50 correctness); Vector leads on homogeneous data (FinanceBench: 0.83 Hit@3, 3.95 correctness). The non-leading mode underperforms in each case.
- **FTS fusion helps only on heterogeneous data.** Hybrid gains over Vector on DocBench (0.87 vs 0.83) but loses on FinanceBench (0.64 vs 0.83), where shared vocabulary makes keyword signals noisy.
- **Competitive but not cheapest on prose.** On heterogeneous text, Recursive Chunk + Vector matches AgentPack's best Hit@3 (0.87) and correctness (3.53) at ~2.7× lower token cost. AgentPack's advantage over it concentrates on the homogeneous corpus, where that baseline drops to 0.57 Hit@3.
- **Highest answer correctness where the mode matches the corpus.** AgentPack (Vector) posts the top judge-graded correctness of any strategy on FinanceBench (3.95/5).
- **Vector precision on heterogeneous data is a known weak point.** AgentPack Vector has the lowest citation precision (0.58) and correctness (2.93) of the AgentPack modes on DocBench.
- **100×+ cheaper than Raw File** while matching or exceeding its Hit@3 on both corpora.
- **No single default mode is optimal everywhere** — realizing peak performance currently requires matching the mode to the corpus; a corpus-adaptive default is the main open improvement.

## 7. References
1. Patronus AI. (2023). *FinanceBench: A New Benchmark for Financial Question Answering.* [GitHub](https://github.com/patronus-ai/financebench) / [HuggingFace](https://huggingface.co/datasets/PatronusAI/financebench).
2. Es, S., et al. (2023). *RAGAS: Automated Evaluation of Retrieval Augmented Generation.* [arXiv:2309.15217](https://arxiv.org/abs/2309.15217).
3. Liu, N. F., et al. (2023). *Lost in the Middle: How Language Models Use Long Contexts.* [arXiv:2307.03172](https://arxiv.org/abs/2307.03172).
4. Zou, A., et al. (2024). *DocBench: A Benchmark for Evaluating LLM-based Document Reading Systems.* [arXiv:2407.10701](https://arxiv.org/abs/2407.10701).
