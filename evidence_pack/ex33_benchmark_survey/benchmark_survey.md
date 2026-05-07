# EX-33: Benchmark Survey Audit

**Benchmarks surveyed:** 12 (11 external + CGA-Bench)

## Process-Safety Dimension Coverage

- **Process-oblivious** (0/4 dimensions): 8/11
- **Partial coverage** (1-3 dimensions): 3/11
- **Full coverage** (4/4 dimensions, excl. CGA-Bench): 0/11

## Dimension Support (among external benchmarks)

| Dimension | Supported | Rate |
|-----------|-----------|------|
| Timing Support | 0/11 | 0% |
| Ordering Check | 1/11 | 9% |
| Conditional Safety | 2/11 | 18% |
| Cpg Fidelity | 0/11 | 0% |

## Per-Benchmark Detail

| Benchmark | Year | Timing | Order | Cond. | CPG | Obs. Level | Scoring |
|-----------|------|--------|-------|-------|-----|------------|---------|
| AgentClinic | 2024 | - | - | - | - | free_text | llm_judge |
| MedAgentBench | 2025 | - | - | - | - | action_set | f1_match |
| HealthBench | 2025 | - | - | - | - | free_text | rubric |
| AMEGA | 2024 | - | Y | - | - | action_sequence | checklist |
| CliBench | 2024 | - | - | - | - | action_set | checklist |
| MedGUIDE | 2024 | - | - | - | - | free_text | llm_judge |
| CancerGUIDE | 2024 | - | - | Y | - | free_text | rubric |
| MTBBench | 2024 | - | - | Y | - | action_set | checklist |
| EHRStruct | 2024 | - | - | - | - | action_set | f1_match |
| LLMEval-Med | 2024 | - | - | - | - | free_text | llm_judge |
| NICE | 2024 | - | - | - | - | free_text | rubric |
| CGA-Bench | 2025 | Y | Y | Y | Y | structured_trace | constraint_graph |

## Observation Level Distribution

- free_text: 6
- action_set: 4
- action_sequence: 1

## Scoring Paradigm Distribution

- llm_judge: 3
- f1_match: 2
- rubric: 3
- checklist: 3

## Key Finding

Of 11 external benchmarks, 8 (73%) are completely process-oblivious (no timing, ordering, conditional, or CPG checks). Only 0 check timing constraints and 1 check action ordering. None achieve full coverage of all 4 process-safety dimensions.