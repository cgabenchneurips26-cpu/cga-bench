# Q2 Detailed Breakdown: Task PASS / CGA FAIL

## Summary

- Total Q2: **28** (natural=11, perturbed=17)
- Natural Q2 (strongest evidence): **11** real LLM runs

## Natural Q2 — Real LLM Episodes

| # | Scenario | Agent | Source | CGA% | Violations | Mode |
|---|----------|-------|--------|------|-----------|------|
| 1 | aki_stage1_basic | oracle | oss120b_exp | 20.0% | deviation:4 | overaction |
| 2 | septic_shock_basic | rag_vllm | oss120b_exp | 0.0% | deviation:7, timing:1 | mixed |
| 3 | septic_shock_penicillin_allergy | rag_vllm | oss120b_exp | 0.0% | deviation:6, timing:2 | mixed |
| 4 | stemi_inferior_rv_trap | rag_vllm | oss120b_exp | 16.7% | deviation:4, timing:1 | mixed |
| 5 | septic_shock_basic | rag_vllm | oss120b_v2 | 60.0% | timing:1, deviation:1 | mixed |
| 6 | septic_shock_penicillin_allergy | rag_vllm | oss120b_v2 | 60.0% | timing:1, deviation:1 | mixed |
| 7 | stemi_inferior_rv_trap | rag_vllm | oss120b_v2 | 50.0% | timing:2, deviation:1 | mixed |
| 8 | aki_stage1_basic | rag_vllm | oss120b_v3 | 0.0% | deviation:17 | overaction |
| 9 | septic_shock_basic | rag_vllm | oss120b_v3 | 60.0% | timing:1, deviation:1 | mixed |
| 10 | septic_shock_penicillin_allergy | rag_vllm | oss120b_v3 | 60.0% | timing:2 | timing |
| 11 | stemi_inferior_rv_trap | rag_vllm | oss120b_v3 | 50.0% | timing:2, deviation:1 | mixed |


### Natural Q2 Failure Modes

| Mode | Count |
|------|-------|
| mixed | 8 |
| overaction | 2 |
| timing | 1 |


## Perturbed Q2 — Controlled Experiments

| # | Scenario | Type | CGA% | Δ CGA | Target Dim | Δ Target |
|---|----------|------|------|-------|-----------|---------|
| 1 | septic_shock_basic | P2_swap_order | 50.0% | -50.0% | sequence_integrity | -0.500 |
| 2 | septic_shock_basic | P5_contraindicated | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| 3 | septic_shock_penicillin_allergy | P2_swap_order | 50.0% | -50.0% | sequence_integrity | -0.500 |
| 4 | septic_shock_penicillin_allergy | P5_contraindicated | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| 5 | stemi_inferior_rv_trap | P1_delay | 50.0% | -50.0% | timing_compliance | -0.500 |
| 6 | stemi_inferior_rv_trap | P2_swap_order | 50.0% | -50.0% | sequence_integrity | +0.000 |
| 7 | stemi_inferior_rv_trap | P5_contraindicated | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| 8 | dka_moderate_basic | P2_swap_order | 0.0% | -100.0% | sequence_integrity | -1.000 |
| 9 | dka_moderate_basic | P5_contraindicated | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| 10 | dka_hypokalemia_trap | P2_swap_order | 0.0% | -100.0% | sequence_integrity | -1.000 |
| 11 | dka_hypokalemia_trap | P5_contraindicated | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| 12 | stroke_tpa_eligible | P1_delay | 50.0% | -50.0% | timing_compliance | -0.500 |
| 13 | stroke_tpa_eligible | P2_swap_order | 50.0% | -50.0% | sequence_integrity | +0.000 |
| 14 | stroke_tpa_eligible | P5_contraindicated | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| 15 | contrast_aki_prevention_basic | P5_contraindicated | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| 16 | aki_stage1_basic | P1_delay | 0.0% | -100.0% | timing_compliance | -1.000 |
| 17 | aki_stage1_basic | P5_contraindicated | 0.0% | -100.0% | forbidden_avoidance | -1.000 |


## Baseline Source Note

Perturbation baselines are **auto-generated from CPG graphs**.
The **natural Q2 episodes** from real LLM runs are the strongest evidence.