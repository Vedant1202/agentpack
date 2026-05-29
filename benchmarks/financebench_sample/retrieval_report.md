# AgentPack Deterministic Eval: financebench_sample
Queries: 42

| Mode | Hit@3 | MRR | Citation Prec | Avg Context Tokens | Avg LLM Cost ($) |
|---|---|---|---|---|---|
| Raw File | 0.57 | 0.43 | 0.19 | 424378.8 | $0.106095 |
| Naive Chunk | 0.40 | 0.25 | 0.21 | 2945.4 | $0.000736 |
| AgentPack (FTS) | 0.50 | 0.34 | 0.25 | 3084.9 | $0.000771 |
| AgentPack (Vector) | 0.83 | 0.58 | 0.41 | 2622.0 | $0.000655 |
| AgentPack (Hybrid) | 0.69 | 0.41 | 0.33 | 2867.4 | $0.000717 |