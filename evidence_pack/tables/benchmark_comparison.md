# Benchmark Comparison

| Benchmark | Year | Task Type | Evaluation | Scenarios | Domains | CPG-Grounded | Auto-Gen | Provenance | Closed-Loop |
|-----------|------|-----------|------------|-----------|---------|--------------|----------|------------|-------------|
| **CGA-Bench (ours)** | 2026 | Interactive agent | Multi-evaluator, CPG-grounded | 366 | 20 | Yes | Yes | Yes | Yes |
| MedQA | 2021 | Multiple-choice QA | Accuracy | 12,723 | General | No | No | No | No |
| HealthBench | 2025 | Open-ended dialogue | LLM-as-judge (criteria) | 5,000 | General health | No | No | No | No |
| AgentClinic | 2024 | Simulated patient dialogue | Diagnostic accuracy | 321 | General clinical | No | No | No | Yes |
| MedAgentBench | 2025 | EHR agent tasks | Task completion | 300 | EHR operations | No | No | No | Yes |
| MedChain | 2025 | Multi-hop reasoning | Accuracy / F1 | 12,163 | General medical | No | Yes | No | No |
| ClinicalBench | 2024 | Clinical NLP tasks | F1 / Accuracy | ~2,000 | Clinical notes | No | No | No | No |
| CLUE | 2024 | Clinical reasoning | Rubric scoring | ~300 | General clinical | No | No | No | No |

## Constraint Type Dimensions

Only CGA-Bench supports structured constraint types (FORBIDDEN, BEFORE, WITHIN) with conditional rules.
