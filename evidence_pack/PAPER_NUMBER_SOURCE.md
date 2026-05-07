> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# PAPER NUMBER SOURCE — Authoritative Reference

> **This document is the ONLY approved number source for the NeurIPS 2026 paper.**
> Do not use FINAL_NUMBERS.md (stale). Do not use numbers from composite_metric.json
> or friedman_verification.json directly (they are Pre-R1-R5).

**Generated**: 2026-04-01
**Pipeline**: Post-R1-R5 strict scoring (clean_slate_rescored)
**Source JSON**: `evidence_pack/analysis/robustness_clean_v2.json`
**Supplementary**: `evidence_pack/FINAL_NUMBERS_CLEAN_V2.md`
**Episodes**: 180 (4 models x 15 scenarios x 3 runs)

---

## 1. Friedman Tests

### 1a. Primary Result (Holm-Bonferroni corrected, family=2)

| Test | Chi-sq | Raw p | Holm alpha | Significant |
|------|--------|-------|------------|-------------|
| **Composite A (k=2)** | **21.5414** | **8.1e-05** | 0.025 | **YES** |
| CGA alone | 4.5882 | 0.2046 | 0.050 | No |

**Source**: `robustness_clean_v2.json` -> holm_correction

### 1b. Per-Run Friedman (Composite A)

| Run | Chi-sq | p-value |
|-----|--------|---------|
| r0 | 17.08 | 0.000681 |
| r1 | 21.14 | 0.000098 |
| r2 | 14.82 | 0.001980 |

**Source**: `robustness_clean_v2.json` -> run_consistency

### 1c. Leave-One-Scenario-Out (LOSO)

- **All 15/15 significant** at p < 0.0003
- p range: [0.0000, 0.0003], median = 0.0002
- Min chi-sq: 18.90, Max chi-sq: 23.78

**Source**: `FINAL_NUMBERS_CLEAN_V2.md` Section 1

---

## 2. k-Space Sensitivity

- **Significant range**: k = 1.1 to 4.0
- **Significant count**: 30/36 (83%)
- **Prespecified k=2**: p = 0.0001

**Source**: `FINAL_NUMBERS_CLEAN_V2.md` Section 4

---

## 3. BSR (Blind Spot Rate)

### 3a. Baseline Selection

| Baseline | Correlation with CGA (r) |
|----------|--------------------------|
| B1 TrackA | 0.856 |
| **B2 Jaccard** (selected) | **0.585** |
| B3 Binary | 0.695 |

B2 selected for lowest CGA correlation (most conservative).

### 3b. BSR Results (B2 Jaccard)

| Perturbation | BSR | Valid Episodes |
|-------------|-----|----------------|
| P1: Timing shift | 10.6% | 180 |
| P2: Sequence swap | 16.7% | 36 |
| P3: Deviation | 18.2% | 159 |
| P4: Commission | 0.0% | 96 |
| P5: Omission | 0.0% | 180 |
| **Overall** | **5.1%** [1.8%, 8.9%] | **492** |

**Source**: `evidence_pack/analysis/bsr_results.json`

---

## 4. Model Performance (Post-R1-R5)

### 4a. CGA Scores

| Model | Size | CGA Mean | CGA Std | 95% CI |
|-------|------|----------|---------|--------|
| **oss-120b** (DeepSeek-V3-0324) | 120B | **0.5072** | 0.2167 | [0.4439, 0.5685] |
| qwen27b (DeepSeek-R1-Distill) | 27B | 0.4447 | 0.2395 | [0.3735, 0.5122] |
| qwen35b (Qwen3.5-35B-A3B) | 35B | 0.4389 | 0.2294 | [0.3702, 0.5047] |
| qwen4b (Qwen3-4B) | 4B | 0.4316 | 0.2269 | [0.3642, 0.4949] |

### 4b. Composite A Scores

| Model | Comp A Mean | 95% CI |
|-------|-------------|--------|
| oss-120b | **0.5054** | [0.4405, 0.5682] |
| qwen35b | 0.4150 | [0.3486, 0.4799] |
| qwen27b | 0.3909 | [0.3200, 0.4622] |
| qwen4b | 0.3175 | [0.2580, 0.3770] |

### 4c. CI Overlap (Pairwise)

- oss120b vs qwen35b: OVERLAP (gap = -0.0394)
- qwen35b vs qwen27b: OVERLAP (gap = -0.1136)
- qwen27b vs qwen4b: OVERLAP (gap = -0.0570)

**Source**: `FINAL_NUMBERS_CLEAN_V2.md` Section 5

### 4d. Ranking (Post-R1-R5)

| Metric | Rank 1 | Rank 2 | Rank 3 | Rank 4 |
|--------|--------|--------|--------|--------|
| CGA | oss-120b (0.507) | qwen27b (0.445) | qwen35b (0.439) | qwen4b (0.432) |
| Composite A | oss-120b (0.505) | qwen35b (0.415) | qwen27b (0.391) | qwen4b (0.318) |

---

## 5. Sub-Construct Profiles (C1-C5)

### 5a. Per-Model Means

| Model | C1 Path | C2 Mandatory | C3 Forbidden | C4 Timing | C5 Sequence |
|-------|---------|-------------|-------------|-----------|-------------|
| oss-120b | 0.667 | **0.616** | 0.867 | 0.852 | 1.000 |
| qwen27b | 0.754 | 0.563 | 0.867 | 0.902 | 1.000 |
| qwen35b | 0.703 | 0.558 | 0.867 | 0.903 | 1.000 |
| qwen4b | **0.789** | 0.524 | 0.867 | **0.927** | 1.000 |

### 5b. Per-Construct Friedman

| Construct | Chi-sq | p-value | Significant |
|-----------|--------|---------|-------------|
| C1 Path Selection | 5.16 | 0.1602 | No |
| **C2 Mandatory Completion** | **9.55** | **0.0228** | **Yes** |
| C3 Forbidden Avoidance | 0.00 | 1.0000 | No (constant) |
| C4 Timing Compliance | 5.13 | 0.1626 | No |
| C5 Sequence Integrity | 0.00 | 1.0000 | No (constant) |

**Source**: `FINAL_NUMBERS_CLEAN_V2.md` Section 6

---

## 6. Q2 Episodes (Task PASS but CGA FAIL)

### 6a. Post-R1-R5 Definition

- **Threshold**: C2 >= 0.7 AND CGA < 0.5
- **Q2 count**: 7 / 180 (3.9%)
- **Optimal C2 threshold**: 0.65 (max spread = 0.222)

### 6b. Episode List

| Scenario | Model | Run | C2 | CGA | Actions | Violations |
|----------|-------|-----|-----|------|---------|------------|
| htn_emergency_basic | qwen35b | 1 | 0.833 | 0.467 | 15 | 8 |
| dka_moderate_basic | oss120b | 0 | 0.800 | 0.389 | 36 | 22 |
| dka_moderate_basic | oss120b | 1 | 0.800 | 0.438 | 32 | 18 |
| dka_moderate_basic | oss120b | 2 | 0.800 | 0.448 | 29 | 16 |
| pe_submassive_basic | qwen27b | 0 | 0.750 | 0.304 | 23 | 16 |
| pe_submassive_basic | qwen27b | 1 | 0.750 | 0.389 | 18 | 11 |
| pe_submassive_basic | qwen27b | 2 | 0.750 | 0.333 | 15 | 10 |

### 6c. Inverse (CGA >= 0.5 but C2 < 0.7): 22 episodes

**Source**: `FINAL_NUMBERS_CLEAN_V2.md` Section 12

---

## 7. Correlations

| Measure | Value | p | Source |
|---------|-------|---|--------|
| CGA vs Task Completion C2≥0.7 (point-biserial) | **r = 0.70** | **< 10^-26** | robustness_clean_v2.json → c2_threshold_correlations["0.7"] |
| ~~CGA vs actions_count>0~~ | ~~r = 0.0~~ | ~~1.0~~ | ~~DEGENERATE: all 180 episodes have actions, constant binary~~ |
| Model Size vs CGA (Spearman) | rho = 0.8 | 0.2 | robustness_clean_v2.json (4 models, ns) |
| BSR baseline B2 vs CGA (Jaccard) | r = 0.585 | - | bsr_results.json |

---

## 8. Violation Co-Occurrence (180 episodes)

| Type | Prevalence |
|------|-----------|
| Omission | 97.8% |
| Deviation | 89.4% |
| Timing | 33.9% |
| Commission | 13.3% |
| Sequence | 0.0% |

**Source**: `FINAL_NUMBERS_CLEAN_V2.md` Section 9

---

## 9. Power Analysis

| N Scenarios | Power |
|-------------|-------|
| 5 | 0.540 |
| 7 | 0.836 (min for 80%) |
| 9 | 0.993 |
| 15 (current) | 1.000 |

**Source**: `FINAL_NUMBERS_CLEAN_V2.md` Section 10

---

## 10. Benchmark Infrastructure

| Metric | Value | Source |
|--------|-------|--------|
| Clinical domains | 6 | scenario configs |
| Scenarios | 15 | scenario configs |
| CPG graphs | 14 | cpg_model/graphs/ |
| Total nodes | 113 | scenario_complexity.json |
| Timing constraints | 92 | timing_evidence.json |
| Mandatory actions | 341 | scenario_complexity.json |
| Forbidden actions | 93 | scenario_complexity.json |
| Sequence deps | 40 | scenario_complexity.json |
| Oracle range | 20-100% (mean 82.9%) | oracle_error_decomposition.json |
| Tests passing | 3,281+ | CI |

---

## 11. Cross-Benchmark (17,784 episodes)

| Benchmark | Episodes | Discordant (corrected) |
|-----------|----------|----------------------|
| AgentClinic | 321 | 12.5% |
| HealthBench | 5,000 | 19.4% |
| MedChain | 12,163 | 31.8% |
| MedAgentBench | 300 | 5.8% |

**Source**: `evidence_pack/analysis/cross_comparison_17k.json` (v3)

---

## 12. Weight Sensitivity (Pre-R1-R5, methodology valid)

- Kendall's W = 1.000 across 5 weight profiles
- **Source**: `scoring_sensitivity.json`

---

## Errata vs Current Paper (main.tex)

All items below were FIXED in commit f3184f87 (2026-04-01):

| Paper Line | Old Value | Corrected Value | Status |
|------------|-----------|-----------------|--------|
| 65 | p=0.020 | p<10^-4 (Holm) | FIXED |
| 568 | chi2=9.80, p=0.020 | chi2=21.54, p=8.1e-05 | FIXED |
| 570 | p=0.074 (CGA alone) | p=0.205 | FIXED |
| 583-586 | Pre-R1-R5 model table | Post-R1-R5 model table | FIXED |
| 584 | oss-20B model | qwen27b (27B) | FIXED |
| 594 | "highest CGA 0.763" | CGA-Composite Divergence narrative | FIXED |
| 907-908 | r0=0.021, r1=0.032, r2=0.019 | r0=0.00068, r1=0.000098, r2=0.002 | FIXED |

### Bug found 2026-04-01: r=0.0 was degenerate

`robustness_clean_v2.json` → `cga_vs_task_completion` used `actions_count > 0`
as "task completion" binary. Since ALL 180 episodes have actions, the binary
is constant (all 1s), producing degenerate r=0.0, p=1.0.

**Correct value**: C2≥0.7 threshold → r=0.70, p<10^-26 (from same JSON,
`c2_threshold_correlations["0.7"]`). Paper updated accordingly.

---

*Last verified: 2026-04-01. Re-verify after any scoring pipeline change.*
