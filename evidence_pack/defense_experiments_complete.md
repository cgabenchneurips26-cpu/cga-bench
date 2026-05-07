# Defense Experiments Complete Data Report (EX-21 ~ EX-33)

Generated: 2026-04-08 from evidence_pack JSON sources.
Dataset: N=14,826 episodes (7 models, 706 scenarios, 3 runs) unless noted otherwise.

---

## EX-21: Model & Scaffold Generalization

**Source**: `ex21_model_diversity/ex21_model_diversity.json`
**Purpose**: Test whether evaluator blind spots persist across new model families beyond the 7 baseline models.

### Diversity Models

| Model | N Episodes | Hard Viol % | AC Pass | MAB Pass | C2 Pass | TCC Pass | Flip Rate | AO-FA Rate |
|-------|-----------|------------|---------|----------|---------|----------|-----------|------------|
| DeepSeek-R1-7B | 186 | 87.6% | 97.3% | 72.0% | 18.3% | 12.4% | 95.7% | 7.0% |
| OpenBioLLM-8B | 927 | 9.9% | 0.0% | 0.0% | 0.0% | 90.1% | 90.1% | 0.0% |
| Llama4-Scout-17B | 0 | — | — | — | — | — | — | — |

### Baseline Models (7 complete)

| Model | N Episodes | Hard % | AC Pass | MAB Pass | C2 Pass | TCC Pass | Flip Rate | AO-FA |
|-------|-----------|--------|---------|----------|---------|----------|-----------|-------|
| OSS-120B | 2,118 | 53.4% | 85.5% | 50.6% | 55.1% | 46.6% | 79.3% | 21.6% |
| Qwen3.5-35B | 2,118 | 46.6% | 81.6% | 54.2% | 44.4% | 53.4% | 82.2% | 15.3% |
| Qwen3.5-27B | 2,118 | 54.5% | 78.7% | 56.8% | 52.4% | 45.5% | 79.1% | 16.4% |
| Qwen3-4B | 2,118 | 43.5% | 54.5% | 48.8% | 41.9% | 56.5% | 82.2% | 9.4% |
| Qwen3.5-397B | 2,118 | 55.9% | 78.8% | 55.7% | 41.9% | 44.1% | 85.8% | 14.3% |
| Gemma4-31B | 2,118 | 38.1% | 72.2% | 54.2% | 55.9% | 61.9% | 76.6% | 11.1% |
| Nemotron-30B | 2,118 | 43.5% | 54.3% | 48.6% | 42.2% | 56.5% | 86.1% | 8.2% |

### Per-Evaluator FA Rates (%)

| Model | AC-Proxy FA | MAB-Proxy FA | C2 FA | CGA-Bench FA |
|-------|-----------|-------------|-------|-------------|
| DeepSeek-R1-7B | 96.9 | 79.1 | 8.0 | 0.0 |
| OpenBioLLM-8B | 0.0 | 0.0 | 0.0 | 0.0 |
| OSS-120B | 90.4 | 53.1 | 45.9 | 0.0 |
| Qwen3.5-35B | 90.6 | 58.9 | 38.4 | 0.0 |
| Qwen3.5-27B | 78.8 | 67.7 | 39.3 | 0.0 |
| Qwen3-4B | 65.7 | 66.7 | 34.5 | 0.0 |
| Qwen3.5-397B | 85.5 | 66.9 | 34.3 | 0.0 |
| Gemma4-31B | 82.4 | 61.2 | 42.7 | 0.0 |
| Nemotron-30B | 72.3 | 70.1 | 30.0 | 0.0 |

### Summary
- Diversity mean flip rate: **92.9%** vs baseline mean: **81.6%**
- Diversity mean AO-FA: **3.5%** vs baseline mean: **13.8%**
- **Bidirectional disagreement**: DeepSeek (high coverage, many hard violations) vs OpenBioLLM (zero coverage, few hard violations)
- Conclusion: Blind spots persist across model families

---

## EX-23: Artifact Mimic Ablation

**Source**: `ex23_artifact_ablation/artifact_ablation.json`
**Purpose**: Quantify detection loss when action-set evaluators are used instead of trace-level TCC.
**N**: 14,826 episodes; 7,104 TCC failures (47.9%)

### Violation Type Episode Counts
| Type | Episodes with violation |
|------|----------------------|
| FORBIDDEN | 1,349 |
| MUST | 7,288 |
| BEFORE | 266 |
| WITHIN | 6,783 |

### Evaluator Mode Comparison

| Mode | Pass Rate | FA Count | FA Rate | Detection Loss vs TCC |
|------|-----------|----------|---------|----------------------|
| AC-Artifact | 72.2% | 5,773 | 38.9% | **81.3%** |
| MAB-Artifact | 52.7% | 4,509 | 30.4% | **63.5%** |
| HB-Artifact | 72.2% | 5,768 | 38.9% | **81.2%** |
| TCC | 52.1% | 0 | 0.0% | 0.0% |

### Per-Type Detection Rates (%)

| Violation Type | AC-Artifact | MAB-Artifact | HB-Artifact | TCC |
|---------------|-------------|-------------|-------------|-----|
| FORBIDDEN | 20.5 | 56.1 | 20.5 | **100.0** |
| WITHIN | 18.2 | 36.0 | 18.3 | **100.0** |
| BEFORE | 0.0 | 8.3 | 1.9 | **100.0** |
| MUST | 35.8 | 48.4 | 35.8 | 50.3 |

### Key Finding
- AC-Artifact and HB-Artifact are near-identical (81.3% vs 81.2% detection loss) because HB only subtracts `seq_count * 0.05` from coverage
- BEFORE violations are nearly invisible to all action-set evaluators (0.0--8.3%)
- TCC detects 100% of FORBIDDEN, WITHIN, BEFORE; 50.3% of MUST (MUST/OMISSION is soft)

---

## EX-24: Consensus False-Accept Severity

**Source**: `ex24_fa_severity/consensus_fa_severity.json`
**Purpose**: Characterize clinical severity of episodes that pass ALL three process-oblivious evaluators (TOM+ASC+CwT) despite hard violations.

### Headline Numbers
- Total episodes: **14,826**
- Consensus FA (all 3 pass + hard violation): **2,038** (**13.7%**)
- Model FA range: **8.2--21.6%**

### Severity Breakdown

| Severity | Count | % of FA | % of Total |
|----------|-------|---------|-----------|
| CRITICAL | 554 | 27.2% | 3.7% |
| HIGH | 89 | 4.4% | 0.6% |
| MEDIUM | 1,395 | 68.4% | 9.4% |
| LOW | 0 | 0.0% | 0.0% |

### Top Domains by Consensus FA

| Domain | Total FA | Top Severity |
|--------|----------|-------------|
| ada_dka_management | 566 | CRITICAL: 273, MEDIUM: 293 |
| aha_stroke_2019 | 292 | MEDIUM: 247, HIGH: 45 |
| atrial_fibrillation | 246 | MEDIUM: 218, HIGH: 28 |
| qwen4b | 200 | MEDIUM: 173, HIGH: 27 |
| status_epilepticus | 158 | MEDIUM: 99, CRITICAL: 59 |
| ssc_sepsis_hour1_bundle | 144 | MEDIUM: 101, CRITICAL: 43 |
| gina_asthma_exacerbation | 112 | MEDIUM: 112 |
| aha_chest_pain_evaluation | 109 | CRITICAL: 82, MEDIUM: 17 |
| idsa_meningitis | 103 | MEDIUM: 101 |
| toxicology_management | 98 | MEDIUM: 98 |
| aha_heart_failure_2022 | 91 | CRITICAL: 91 |
| kdigo_contrast_aki | 58 | MEDIUM: 52, HIGH: 6 |
| hypertensive_emergency | 26 | MEDIUM: 26 |
| pals_pediatric_emergency | 27 | MEDIUM: 27 |
| apa_agitation_management | 5 | MEDIUM: 4, CRITICAL: 1 |
| pulmonary_embolism | 3 | CRITICAL: 3 |

### Per-Model FA Rates

| Model | FA Count | FA Rate | Critical | High | Medium |
|-------|----------|---------|----------|------|--------|
| oss120b | 457 | 21.6% | 174 | 7 | 276 |
| qwen27b | 347 | 16.4% | 143 | 8 | 196 |
| qwen35b | 323 | 15.3% | 88 | 28 | 207 |
| qwen397b | 302 | 14.3% | 44 | 12 | 246 |
| gemma31b | 236 | 11.1% | 104 | 7 | 125 |
| qwen4b | 200 | 9.4% | 0 | 27 | 173 |
| nemotron30b | 173 | 8.2% | 1 | 0 | 172 |

### By Source
- Auto-generated scenarios: 1,753 FA (CRITICAL: 468, HIGH: 51, MEDIUM: 1,234)
- Manual scenarios: 285 FA (CRITICAL: 86, HIGH: 38, MEDIUM: 161)

---

## EX-25: Engine Structural Audit

**Source**: `ex25_engine_audit/engine_audit.json`
**Purpose**: Static analysis of all 25 CPG graphs for structural integrity.

### Global Statistics
| Metric | Value |
|--------|-------|
| Graphs | 25 |
| Total nodes | 167 |
| Total constraints | **1,049** |
| Unique actions | 611 |
| Constraints per node | 6.3 |

### Constraint Type Distribution
| Type | Count | % |
|------|-------|---|
| MUST | 557 | 53.1% |
| FORBIDDEN | 212 | 20.2% |
| WITHIN | 215 | 20.5% |
| BEFORE | 65 | 6.2% |

### Audit Results
| Check | Value | Status |
|-------|-------|--------|
| Contradictions | **0** (0.0%) | PASS |
| Duplicates | 98 (9.3%) | WARN |
| Unreachable nodes | 61 (36.5%) | INFO |
| Dead-end nodes | 96 (57.5%) | INFO |
| Provenance complete | 167/167 (100%) | PASS |

### Unreachable Node Distribution
Concentrated in 5 multi-entry graphs with alternative clinical pathways:
| Graph | Unreachable | Total Nodes |
|-------|------------|-------------|
| aha_stroke_2019 | 24 | 25 |
| aha_heart_failure_2022 | 23 | 24 |
| kdigo_aki_full | 12 | 13 |
| atrial_fibrillation | 1 | 3 |
| pulmonary_embolism | 1 | 3 |

**Note**: "Unreachable" = not activated in current scenario set (alternative pathways). Cannot produce false violations; reduces recall for rare pathways only.

### Duplicate Details (98 total)
Top graphs: acls_cardiac_arrest (8), ada_dka_management (4), aha_chest_pain_evaluation (4), aba_burn_resuscitation (3).
Types: FORBIDDEN (5), BEFORE (4), MUST (3), WITHIN (2).

### Top Graphs by Constraint Count
| Graph | Constraints | MUST | FORBIDDEN | WITHIN | BEFORE |
|-------|-----------|------|-----------|--------|--------|
| aha_stroke_2019 | 120 | 99 | 15 | 6 | 0 |
| aha_heart_failure_2022 | 92 | 76 | 9 | 7 | 0 |
| ada_dka_management | 82 | 32 | 19 | 19 | 12 |
| aha_chest_pain_evaluation | 66 | 27 | 13 | 16 | 10 |
| kdigo_aki_full | 63 | 49 | 5 | 9 | 0 |
| gina_asthma_exacerbation | 58 | 20 | 24 | 14 | 0 |
| aba_burn_resuscitation | 53 | 24 | 8 | 15 | 6 |
| kdigo_contrast_aki | 51 | 26 | 10 | 8 | 7 |
| status_epilepticus | 51 | 15 | 19 | 11 | 6 |
| acls_cardiac_arrest | 49 | 17 | 12 | 15 | 5 |

---

## EX-26: Scorer Fidelity Audit

**Source**: `ex26_scorer_fidelity/scorer_fidelity.json`
**Purpose**: Verify that each native scorer (AC, MAB, TCC) produces expected verdicts on 40 hand-crafted traces across 8 violation categories.

### Results
- **40 traces**, **3 scorers**, **8 categories**, **120 total checks**
- **100% exact match** across all scorers and categories
- **Cohen's kappa = 1.0** for each scorer

### Per-Category Results
| Category | Total Checks | Matches | Rate |
|----------|-------------|---------|------|
| timing_only | 15 | 15 | 100% |
| order_only | 15 | 15 | 100% |
| forbid_only | 15 | 15 | 100% |
| omission_only | 15 | 15 | 100% |
| mixed | 15 | 15 | 100% |
| clean | 15 | 15 | 100% |
| partial | 15 | 15 | 100% |
| boundary | 15 | 15 | 100% |

### Key Behavioral Verification
- AC passes timing/order/forbid violations (blind by design)
- MAB passes timing/order violations but catches severe forbid+omission
- TCC catches timing, order, forbid violations; passes clean + omission-only (OMISSION is soft)

---

## EX-27: Timing Stress Suite

**Source**: `ex27_timing_stress/timing_stress.json`
**Purpose**: 4 sub-experiments testing sensitivity of WITHIN violation detection to timing model assumptions.
**N**: 14,025 episodes (deduplicated canonical set)

### Sub-A: Duration Model Perturbation
| Metric | Value |
|--------|-------|
| Baseline violation rate | 63.66% |
| Model violation rate | 63.3% |
| Flip to pass | 180 |
| Flip to fail | 130 |
| Total flips | 310 (2.21%) |
| WITHIN persist rate | **97.98%** |

Top graphs by flip: copd_exacerbation (92), aha_stroke_2019 (82), cap_pneumonia (65)

### Sub-B: Parallel Batch Perturbation
| Metric | Value |
|--------|-------|
| Baseline violation rate | 63.66% |
| Model violation rate | 62.92% |
| Total flips | 363 (2.59%) |
| WITHIN persist rate | **97.39%** |

### Sub-C: Zero Reasoning Delay
| Metric | Value |
|--------|-------|
| Flips | **0** (0.0%) |
| WITHIN persist rate | **100.0%** |

This confirms that reasoning delay is not a confound.

### Sub-D: Clock Step Sweep

| Step Size | Violation Rate | Flip from Baseline | Flip Rate |
|-----------|---------------|-------------------|-----------|
| 2 min | 43.42% | 2,838 | 20.24% |
| 5 min (baseline) | 63.66% | 0 | 0.0% |
| 10 min | 75.37% | 1,642 | 11.71% |
| 15 min | 87.68% | 3,369 | 24.02% |
| 20 min | 90.35% | 3,743 | **26.69%** |

**Key finding**: 31.8% of baseline WITHIN violations are clock-granularity-dependent (resolve at 2-min step). The remaining 68.2% persist regardless of clock resolution.

---

## EX-28: Bug-Fix Invariance Matrix

**Source**: `ex28_bugfix_invariance/invariance_matrix.json`
**Purpose**: Verify that pipeline changes (normalizer gap-fix, solver choice) do not flip TCC verdicts.
**N**: 14,055 episodes

### Normalizer Impact
| Metric | Value |
|--------|-------|
| Episodes affected by gap-fix | 9,200 (65.46%) |
| Total gap actions | 16,177 |
| Mandatory gap actions | 6,618 |
| Coverage could flip (AC) | 921 |
| **TCC could flip** | **0** |
| Gap-fix aliases | 40 |
| Gap-fix targets | 21 |

Top targets: establish_iv_access (4,849), monitor_urine_output (2,533), check_current_medications (2,256)

### Version Matrix

| Version | Normalizer | Solver | TCC Pass | AC Pass | MAB Pass | FA(AC) | FA(MAB) |
|---------|-----------|--------|----------|---------|----------|--------|---------|
| V3 (current) | v1 gap-fix | ILP | 47.67% | 72.36% | 54.44% | 8.28% | 16.35% |
| V1 tiered | v1 gap-fix | tiered | 47.67% | 72.36% | 54.44% | 8.28% | 16.35% |
| V2 norm-v0 | v0 no gap-fix | ILP | 47.67% | UB +6.55pp | — | — | — |
| V0 pre-fix | v0 no gap-fix | tiered | 47.67% | UB +6.55pp | — | — | — |

### Stability Checks (8 metrics)

| Metric | Delta/Value | Threshold | Stable? |
|--------|------------|-----------|---------|
| TCC verdict flip | 0.0 pp | 2.0 pp | YES |
| AC-Proxy verdict flip (UB) | 6.55 pp | 2.0 pp | NO |
| FA(AC) delta | 6.55 pp | 2.0 pp | NO |
| FA(MAB) delta | 0.0 pp | 2.0 pp | YES |
| Solver Spearman rho | 0.918 | >0.85 | YES |
| Solver verdict reversals | 0 | <10 | YES |
| Evaluator ranking | preserved | — | YES |
| Model ranking | preserved | — | YES |

**Result**: 6/8 stable. TCC: **0 flips**. AC instability is upper-bound from normalizer gap-fix (OMISSION is soft, so TCC unaffected).

---

## EX-29: Held-Out Domain Breakdown

**Source**: `ex29_heldout_domain/heldout_domain_breakdown.json`
**Purpose**: Test whether blind spots generalize to 5 held-out CPG domains not seen during development.

### Per-Domain Results

| Domain | N | Hard % | Flip % | FA(AC) | FA(MAB) | FA(C2) | AO-FA | TCC Pass | Cohen's d |
|--------|---|--------|--------|--------|---------|--------|-------|----------|-----------|
| aabb_transfusion | 252 | 2.8% | 65.1% | 2.8% | 0.0% | 2.8% | 2.8% | 97.2% | -0.698 |
| aba_burn_resuscitation | 420 | 98.6% | 92.9% | 91.2% | 69.3% | 23.6% | 23.6% | 1.4% | 1.162 |
| acog_obstetric_hemorrhage | 189 | 72.5% | 85.7% | 72.5% | 16.9% | 72.5% | 72.5% | 27.5% | 0.761 |
| apa_agitation_management | 315 | 92.1% | 100.0% | 92.1% | 49.2% | 67.3% | 67.3% | 7.9% | 1.178 |
| pals_pediatric_emergency | 180 | 83.3% | 99.4% | 83.3% | 32.2% | 78.3% | 78.3% | 16.7% | 0.989 |

### In-Domain Aggregate (20 core graphs)
| Metric | Value |
|--------|-------|
| N episodes | 12,699 |
| Hard rate | 44.9% |
| Flip rate | 78.8% |
| FA(AC) | 36.0% |
| FA(MAB) | 30.4% |
| FA(C2) | 10.9% |
| AO-FA | 10.9% |
| TCC pass | 55.1% |

### Violation Distribution (%)

| Domain | COMMISSION | TIMING | SEQUENCE | OMISSION | DEVIATION |
|--------|-----------|--------|----------|----------|-----------|
| aabb_transfusion | 0.3 | 0.0 | 0.0 | 12.1 | 87.6 |
| aba_burn_resuscitation | 0.0 | 7.0 | 1.8 | 53.8 | 37.5 |
| acog_obstetric_hemorrhage | 3.4 | 9.0 | 0.0 | 13.0 | 74.6 |
| apa_agitation_management | 2.3 | 19.4 | 0.0 | 24.9 | 53.4 |
| pals_pediatric_emergency | 0.0 | 20.6 | 0.0 | 5.3 | 74.1 |
| **In-domain** | 1.6 | 10.2 | 0.1 | 47.2 | 40.8 |

### Cross-Domain
- FA range: **2.8% -- 92.1%**
- Flip range: **65.1% -- 100.0%**
- All 5 held-out domains exhibit blind spots

---

## EX-30: Non-Timing Trap Augmentation

**Source**: `ex30_non_timing/non_timing_traps.json`
**Purpose**: Quantify blind spots from BEFORE and FORBIDDEN constraints (non-timing dimensions).
**N**: 14,055 episodes

### Constraint Inventory (Graph-Level)
| Type | Count |
|------|-------|
| BEFORE (sequence_dependencies) | 9 |
| FORBIDDEN combinations | 5 |
| FORBIDDEN node-level | 212 |
| **Total non-timing** | **226** |

### Natural Episode Results
| Metric | Value |
|--------|-------|
| Non-timing TCC failures | **247** (1.76%) |
| AC blind to these | 176 (71.3%) |
| MAB blind to these | 152 (61.5%) |
| Both blind | 152 |

Violation type combos:
- FORBIDDEN only: 208 episodes
- BEFORE only: 39 episodes

Per-model distribution: Gemma31B (60), Qwen35B (60), Qwen27B (55), OSS-120B (47), Qwen397B (20), Nemotron30B (5)

### Synthetic Traps (4 constructed)

| Trap | Domain | Type | AC Pass | MAB Pass | TCC Fail | Blind Spot |
|------|--------|------|---------|----------|----------|------------|
| tpa_before_ct | aha_stroke_2019 | BEFORE | YES | YES | YES | YES |
| anticoag_after_tpa | aha_stroke_2019 | FORBIDDEN | YES | YES | YES | YES |
| nitrates_rv_infarct | aha_chest_pain | FORBIDDEN | YES | YES | YES | YES |
| insulin_before_k_correction | ada_dka | BEFORE+FORBIDDEN | YES | YES | YES | YES |

All 4 synthetic traps achieve 100% coverage (F1 >= 0.889), pass both AC and MAB, but fail TCC.

---

## EX-31: Witness Patch

**Status**: NOT EXECUTED
**No data available.**

---

## EX-32: Solver Taxonomy

**Source**: `ex32_solver_taxonomy/solver_taxonomy.json`
**Purpose**: Classify episodes where tiered solver gives lower d_G than ILP solver.
**N**: 15,855 episodes

### Classification

| Category | Count | % of Total | % of Tiered-Better | Mean |d| | Max |d| | Verdict Reversals |
|----------|-------|-----------|-------------------|---------|---------|-------------------|
| Equal | 10,835 | 68.3% | — | — | — | — |
| ILP better | 3,867 | 24.4% | — | — | — | — |
| **Tiered better** | **1,153** | **7.27%** | 100% | 688.0 | 7,930 | **0** |

### Tiered-Better Subcategories

| Subcategory | Count | % of Tiered-Better | Mean |d| | Max |d| |
|-------------|-------|-------------------|---------|---------|
| tie_break | 144 | 12.5% | 8.6 | 10 |
| phase_ordering | 251 | 21.8% | 24.3 | 50 |
| formulation_gap | 758 | **65.7%** | 1,036.9 | 7,930 |

### Verdict Reversals: **0**
No episode changes pass/fail verdict when switching between ILP and tiered solver.

### Dominant Graphs for Tiered-Better
| Graph | Tiered Better | ILP Better | Equal |
|-------|-------------|-----------|-------|
| acls_cardiac_arrest | 347 | 167 | 629 |
| kdigo_contrast_aki | 321 | 332 | 235 |
| status_epilepticus | 250 | 23 | 63 |
| anaphylaxis_management | 84 | 233 | 91 |
| ada_dka_management | 76 | 806 | 0 |
| ssc_sepsis_hour1_bundle | 58 | 309 | 116 |
| aba_burn_resuscitation | 16 | 439 | 85 |

---

## EX-33: Benchmark Survey

**Source**: `ex33_benchmark_survey/benchmark_survey.json`
**Purpose**: Systematic comparison of CGA-Bench against 11 other clinical AI benchmarks on 4 process dimensions.

### Dimension Coverage Summary
- **12** benchmarks surveyed (11 others + CGA-Bench)
- **0** others check timing deadlines
- **1** other checks ordering (AMEGA)
- **2** others check conditional safety (CancerGUIDE, MTBBench)
- **0** others check CPG fidelity

### Observation Levels
| Level | Count |
|-------|-------|
| free_text | 6 |
| action_set | 4 |
| action_sequence | 1 |
| structured_trace (CGA-Bench only) | 1 |

### Scoring Paradigms
| Paradigm | Count |
|----------|-------|
| llm_judge | 3 |
| f1_match | 2 |
| rubric | 3 |
| checklist | 3 |
| constraint_graph (CGA-Bench only) | 1 |

### Full Benchmark Comparison Table

| Benchmark | Year | Venue | Obs Level | Scoring | Timing | Order | Cond Safety | CPG |
|-----------|------|-------|-----------|---------|--------|-------|-------------|-----|
| AgentClinic | 2024 | NeurIPS | free_text | llm_judge | - | - | - | - |
| MedAgentBench | 2025 | NAACL | action_set | f1_match | - | - | - | - |
| HealthBench | 2025 | arXiv | free_text | rubric | - | - | - | - |
| AMEGA | 2024 | arXiv | action_seq | checklist | - | **Y** | - | - |
| CliBench | 2024 | EMNLP | action_set | checklist | - | - | - | - |
| MedGUIDE | 2024 | ML4H | free_text | llm_judge | - | - | - | - |
| CancerGUIDE | 2024 | arXiv | free_text | rubric | - | - | **Y** | - |
| MTBBench | 2024 | arXiv | action_set | checklist | - | - | **Y** | - |
| EHRStruct | 2024 | arXiv | action_set | f1_match | - | - | - | - |
| LLMEval-Med | 2024 | arXiv | free_text | llm_judge | - | - | - | - |
| NICE | 2024 | arXiv | free_text | rubric | - | - | - | - |
| **CGA-Bench** | **2025** | **NeurIPS** | **struct_trace** | **constraint_graph** | **Y** | **Y** | **Y** | **Y** |

---

## Cross-Experiment Summary

### Paper Integration Status

| # | Experiment | Status | Main Text | Appendix |
|---|-----------|--------|-----------|----------|
| 1 | EX-23 Artifact Mimic | COMPLETE | Missing | Missing |
| 2 | EX-24 Consensus FA Severity | COMPLETE | Missing | Missing |
| 3 | EX-25 Engine Structural Audit | COMPLETE | Missing | Missing |
| 4 | EX-26 Scorer Fidelity | COMPLETE | Appendix only (7-check table) | Partial |
| 5 | EX-27 Timing Stress Suite | NEEDS RERUN | Missing | Missing |
| 6 | EX-28 Bug-Fix Invariance | COMPLETE | Missing | Missing |
| 7 | EX-29 Held-Out Breakdown | COMPLETE | Missing | Missing |
| 8 | EX-30 Non-Timing Traps | COMPLETE | Missing | Missing |
| 9 | EX-31 Witness Patch | NOT EXECUTED | — | — |
| 10 | EX-32 Solver Taxonomy | COMPLETE | Missing | Missing |
| 11 | EX-33 Benchmark Survey | COMPLETE | Missing | Missing |
| 12 | EX-21 Model Diversity | COMPLETE | Appendix only | Partial |

### Key Macro Values (for auto_numbers.tex)

| Macro | Value | Source |
|-------|-------|--------|
| `\mimicACDetectionLoss` | 81.3 | EX-23 |
| `\mimicMABDetectionLoss` | 63.5 | EX-23 |
| `\mimicHBDetectionLoss` | 81.2 | EX-23 |
| `\consensusFATotal` | 2,038 | EX-24 |
| `\consensusFARate` | 13.7 | EX-24 |
| `\auditTotalRules` | 1,049 | EX-25 |
| `\auditContradictions` | 0 | EX-25 |
| `\auditUnreachable` | 36.5% | EX-25 |
| `\auditProvenance` | 100% | EX-25 |
| `\scorerFidelityRate` | 100% | EX-26 |
| `\timingDurModelViolRate` | 63.3 | EX-27 |
| `\timingDurModelWithinPersist` | 97.98 | EX-27 |
| `\clockSweepMaxFlip` | 26.7 | EX-27 |
| `\invarianceTCCFlips` | 0 | EX-28 |
| `\invarianceMaxFADelta` | 6.55 | EX-28 |
| `\nonTimingNaturalCount` | 247 | EX-30 |
| `\nonTimingACBlindPct` | 71.3 | EX-30 |
| `\solverTieredBetterN` | 1,153 | EX-32 |
| `\solverVerdictReversalN` | 0 | EX-32 |
| `\surveyNBenchmarks` | 12 | EX-33 |
| `\surveyTimingChecked` | 0 | EX-33 |
