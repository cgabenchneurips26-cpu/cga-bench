# Cross-Benchmark Comparison Feasibility Report

## Summary

All 4 benchmarks have computable native metrics on the same episodes where CGA was evaluated.
25/110 episodes (23%) show discordance: native metric says OK, CGA finds violations.

## Per-Benchmark Feasibility

### 1. AgentClinic (N=20, 6 discordant)

**Original metric**: Diagnostic accuracy + action_coverage
- `expected_diagnosis`: available for 20/20 episodes (e.g., "Myasthenia gravis")
- `agent_diagnosis`: available for 0/20 (agent did not output final diagnosis)
- `correct_diagnosis`: 0/20 (all False — agent never diagnosed correctly)
- `action_coverage`: available for 20/20 (range: 0.33–1.00, mean=0.659)

**Feasibility**: ✅ action_coverage computable. Diagnostic accuracy = 0% (agent limitation, not evaluation limitation).

**Finding**: 6/20 episodes where action_coverage ≥ 0.5 but CGA finds violations (deviation, sequence). Action coverage measures WHAT was done; CGA measures HOW it was done.

**Source**: `reports/evidence_pack/external_benchmarks/agentclinic_live_results_20.json`

### 2. HealthBench (N=50, 7 discordant)

**Original metric**: `native_normalized` — the ORIGINAL HealthBench rubric score
- Available for 50/50 episodes
- This is NOT our modular score — it's the actual HealthBench evaluation
- Mean: 0.453 (range: 0.17–1.00)

**CGA metric**: `mandatory_coverage` (mean: 0.318) + `forbidden_avoidance` (mean: 0.73)

**Correlation**: native_normalized vs mandatory_coverage: r=0.903 (p<0.0001)
- High correlation = both metrics care about action coverage
- But CGA adds forbidden_avoidance dimension that rubric doesn't capture

**Feasibility**: ✅ Fully computable. native_normalized IS the original HealthBench score.

**Finding**: 7/50 episodes where native ≥ 0.5 but mandatory_coverage < 0.5 or forbidden_avoidance < 0.8.

**Source**: `reports/evidence_pack/external_benchmarks/healthbench_results_50.json`

### 3. MedAgentBench (N=20, 10 discordant)

**Original metric**: action_coverage (proxy for FHIR Success Rate)
- Available for 20/20 episodes
- ALL 20 episodes have action_coverage = 1.0 (task fully completed)
- The agent completed every expected action in every scenario

**Why not exact FHIR SR**: MedAgentBench's original SR requires a live FHIR server environment. Our agent runs in the CGA-Bench RAG environment. action_coverage (expected actions performed / expected actions total) is the closest computable proxy.

**CGA metric**: compliance_score (mean: 0.967)

**Feasibility**: ✅ action_coverage computable. True FHIR SR not computable (different runtime environment).

**Finding**: 10/20 episodes where action_coverage = 1.0 (task complete) but CGA finds 1+ deviation violation. The agent completed all required tasks but also performed off-protocol actions that CGA catches.

**Source**: `reports/evidence_pack/external_benchmarks/medagentbench_live_results_20.json`

### 4. MedChain (N=20, 2 discordant)

**Original metric**: action_coverage
- Available for 20/20 episodes
- Low mean: 0.104 (MedChain agent performed few expected actions)
- 13/20 have expected_diagnosis available

**CGA metric**: compliance_score (mean: 0.965)

**Feasibility**: ✅ action_coverage computable.

**Finding**: 2/20 episodes where action_coverage ≥ 0.5 but CGA finds violations. Low discordance because MedChain's action_coverage is already low (agent barely acted).

**Source**: `reports/evidence_pack/external_benchmarks/medchain_live_results_20.json`

## Unified Table

| Benchmark | N | Native Metric | Native Mean | CGA Mean | Discordant | % |
|-----------|---|---------------|-------------|----------|------------|---|
| AgentClinic | 20 | action_coverage | 0.659 | 0.937 | 6 | 30% |
| MedAgentBench | 20 | action_coverage | 1.000 | 0.967 | 10 | 50% |
| MedChain | 20 | action_coverage | 0.104 | 0.965 | 2 | 10% |
| HealthBench | 50 | native_normalized | 0.453 | 0.318 | 7 | 14% |
| **Total** | **110** | | | | **25** | **23%** |

## What "Discordant" Means

A discordant episode is one where:
- The native benchmark metric indicates acceptable performance (≥ 0.5)
- BUT CGA identifies at least one violation (deviation, timing, sequence, or omission)

These 25 episodes are the empirical evidence that existing metrics have blind spots
that CGA can detect. The most striking case is MedAgentBench: 10/20 episodes where
the agent completed ALL expected tasks (coverage=1.0) but performed additional
off-protocol actions that CGA flags as deviations.

## Limitations

1. **action_coverage ≠ FHIR SR**: For MedAgentBench, we use action_coverage as a proxy for the original Success Rate, which requires a live FHIR server.

2. **AgentClinic diagnostic accuracy = 0%**: The CGA RAG agent never produces a final diagnosis, so diagnostic accuracy is trivially 0/20. The cross-comparison is based on action_coverage instead.

3. **CGA violations are mostly deviations**: The discordant cases are dominated by deviation violations (off-protocol actions), not safety-critical violations. The clinical significance of these deviations varies.
