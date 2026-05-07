# EX-38: Variable Action Duration -- Cross-Model Persistence

## Overview

Post-hoc reprocessing of v5 episodes to test whether timing violations
persist under realistic per-action durations (vs 5-min fixed step).

**Attack:** "5-min fixed step is unrealistic. Timing violations are artifacts."
**Defense:** 96.5% of violations persist under variable durations
across all 8 models (95% CI: [96.0, 97.0]).

## Per-Model Results

| Model | Episodes | Baseline Viols | Persisting | Resolved | New | Persistence % |
|-------|----------|----------------|------------|----------|-----|---------------|
| deepseek_r1_7b | 2118 | 6309 | 6049 | 260 | 114 | **95.88%** |
| gemma31b | 2118 | 4608 | 4455 | 153 | 273 | **96.68%** |
| nemotron30b | 2118 | 3536 | 3449 | 87 | 179 | **97.54%** |
| oss120b | 2118 | 6160 | 5854 | 306 | 202 | **95.03%** |
| qwen27b | 2118 | 5288 | 5142 | 146 | 255 | **97.24%** |
| qwen35b | 2118 | 6240 | 5993 | 247 | 261 | **96.04%** |
| qwen397b | 2118 | 5530 | 5353 | 177 | 246 | **96.8%** |
| qwen4b | 2118 | 3869 | 3739 | 130 | 214 | **96.64%** |
| **Total** | | **41540** | **40034** | **1506** | **1744** | **96.37%** |

## Default-Duration Sensitivity Sweep

| Default (min) | Baseline Viols | Persisting | Persistence % |
|---------------|----------------|------------|---------------|
| 3 | 41540 | 36998 | **89.07%** |
| 5 | 41540 | 40034 | **96.37%** |
| 7 | 41540 | 40697 | **97.97%** |
| 10 | 41540 | 41018 | **98.74%** |

## Domain-Stratified Persistence

| Domain (Graph) | Baseline Viols | Persisting | Rate % |
|----------------|----------------|------------|--------|
| acls_cardiac_arrest | 9090 | 8786 | 96.7% |
| gina_asthma_exacerbation | 5258 | 5257 | 100.0% |
| ada_dka_management | 4994 | 4286 | 85.8% |
| idsa_meningitis | 3813 | 3791 | 99.4% |
| aba_burn_resuscitation | 2312 | 2308 | 99.8% |
| aha_chest_pain_evaluation | 2027 | 2025 | 99.9% |
| anaphylaxis_management | 1791 | 1791 | 100.0% |
| status_epilepticus | 1766 | 1766 | 100.0% |
| toxicology_management | 1508 | 1508 | 100.0% |
| apa_agitation_management | 1506 | 1505 | 99.9% |
| aha_heart_failure_2022 | 1269 | 1121 | 88.3% |
| pals_pediatric_emergency | 1173 | 1173 | 100.0% |
| acog_obstetric_hemorrhage | 1045 | 1045 | 100.0% |
| aha_stroke_2019 | 719 | 715 | 99.4% |
| ssc_sepsis_hour1_bundle | 628 | 555 | 88.4% |

## Interpretation

Across all 8 models in COMPLETE_MODELS, 96.5% (95% CI: [96.0, 97.0]) of baseline timing violations persist when the fixed 5-min step is replaced with clinically realistic per-action durations (21 action-type mappings). The sensitivity sweep over default fallback durations [3, 5, 7, 10] min confirms robustness: persistence stays above 89.1% in all configurations. The 5-min fixed step is therefore conservative, not inflating violations.

Runtime: 20.1s
