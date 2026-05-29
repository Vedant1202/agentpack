# AgentPack Generative Eval: financebench_sample
Queries: 42
Generation Model: gemini-3.1-flash-lite
Judge Model: gemini-3.1-pro-preview

| Mode | Correctness (0-5) | Faithfulness (0-5) | Answer Relevance (0-5) | Context Relevance (0-5) | Avg Context Tokens | Avg LLM Cost ($) |
|---|---|---|---|---|---|---|
| Raw File | 1.14 | 1.45 | 1.36 | 1.21 | 424381.3 | $0.106095 |
| Naive Chunk | 1.55 | 1.67 | 1.67 | 0.38 | 2949.1 | $0.000737 |
| AgentPack (Vector) | 1.55 | 1.55 | 1.55 | 0.74 | 2625.9 | $0.000656 |