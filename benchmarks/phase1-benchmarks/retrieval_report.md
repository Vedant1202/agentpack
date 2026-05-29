# AgentPack Deterministic Eval: phase1-benchmarks
Queries: 3

| Mode | Hit@3 | MRR | Citation Prec | Avg Context Tokens | Avg LLM Cost ($) |
|---|---|---|---|---|---|
| Raw File | 1.00 | 0.83 | 0.83 | 304.7 | $0.000076 |
| Naive Chunk | 1.00 | 0.83 | 0.83 | 304.7 | $0.000076 |
| AgentPack (FTS) | 0.33 | 0.17 | 0.17 | 323.7 | $0.000081 |
| AgentPack (Vector) | 0.33 | 0.17 | 0.17 | 487.0 | $0.000122 |
| AgentPack (Hybrid) | 0.33 | 0.17 | 0.17 | 487.0 | $0.000122 |