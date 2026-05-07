# V3 Violation Spread Analysis

Analysis of violation distribution patterns across 15 scenarios, 4 models, and 3 runs (180 total episodes) from the CGA-Bench clean-slate rescored dataset.

## 1. Model × Scenario CGA Heatmap (mean across 3 runs)

+------------------------------+----------------+------------+------------+------------+------------+---------+
| Scenario                     | Domain         | OSS-120B   | Qwen-27B   | Qwen-35B   | Qwen-4B    | Mean    |
+------------------------------+----------------+------------+------------+------------+------------+---------+
| adhf_warm_wet                | Unknown        | 0.345      | 0.500      | 0.340      | 0.393      | 0.395   |
| af_new_onset_basic           | AF             | 0.550      | 0.222      | 0.401      | 0.455      | 0.407   |
| aki_stage1_basic             | AKI            | 0.554      | 0.541      | 0.566      | 0.560      | 0.555   |
| contrast_aki_prevention_bas  | ContrastAKI    | 0.556      | 0.510      | 0.547      | 0.507      | 0.530   |
| copd_moderate_exacerbation   | COPD           | 0.556      | 0.521      | 0.436      | 0.400      | 0.478   |
| dka_hypokalemia_trap         | DKA            | 0.347      | 0.385      | 0.385      | 0.347      | 0.366   |
| dka_moderate_basic           | DKA            | 0.425      | 0.615      | 0.615      | 0.533      | 0.547   |
| gi_bleeding_upper_basic      | GIBleed        | 0.389      | 0.500      | 0.182      | 0.500      | 0.393   |
| hemorrhagic_stroke           | Unknown        | 0.338      | 0.000      | 0.064      | 0.000      | 0.100   |
| htn_emergency_basic          | HTNEmergency   | 0.528      | 0.282      | 0.433      | 0.403      | 0.412   |
| pe_submassive_basic          | PE             | 0.611      | 0.342      | 0.385      | 0.200      | 0.385   |
| septic_shock_basic           | Unknown        | 0.797      | 0.765      | 0.744      | 0.800      | 0.776   |
| septic_shock_penicillin_all  | Unknown        | 0.803      | 0.760      | 0.744      | 0.683      | 0.748   |
| stemi_inferior_rv_trap       | Unknown        | 0.812      | 0.729      | 0.741      | 0.692      | 0.743   |
| stroke_tpa_eligible          | Unknown        | 0.000      | 0.000      | 0.000      | 0.000      | 0.000   |
+------------------------------+----------------+------------+------------+------------+------------+---------+

## 2. Model × Scenario Violation Count Heatmap (mean)

+------------------------------+----------------+------------+------------+------------+------------+---------+
| Scenario                     | Domain         | OSS-120B   | Qwen-27B   | Qwen-35B   | Qwen-4B    | Mean    |
+------------------------------+----------------+------------+------------+------------+------------+---------+
| adhf_warm_wet                | Unknown        | 19.0       | 5.0        | 11.7       | 4.7        | 10.1    |
| af_new_onset_basic           | AF             | 10.7       | 18.7       | 8.0        | 6.0        | 10.8    |
| aki_stage1_basic             | AKI            | 15.3       | 15.0       | 14.3       | 11.0       | 13.9    |
| contrast_aki_prevention_bas  | ContrastAKI    | 16.0       | 17.3       | 16.0       | 12.3       | 15.4    |
| copd_moderate_exacerbation   | COPD           | 10.7       | 8.7        | 7.7        | 3.0        | 7.5     |
| dka_hypokalemia_trap         | DKA            | 20.7       | 8.0        | 8.0        | 10.0       | 11.7    |
| dka_moderate_basic           | DKA            | 18.7       | 5.0        | 5.0        | 7.0        | 8.9     |
| gi_bleeding_upper_basic      | GIBleed        | 14.7       | 3.0        | 12.0       | 3.0        | 8.2     |
| hemorrhagic_stroke           | Unknown        | 20.7       | 6.0        | 9.3        | 8.0        | 11.0    |
| htn_emergency_basic          | HTNEmergency   | 11.3       | 17.0       | 9.0        | 6.3        | 10.9    |
| pe_submassive_basic          | PE             | 9.3        | 12.3       | 9.0        | 8.0        | 9.7     |
| septic_shock_basic           | Unknown        | 4.7        | 4.0        | 4.0        | 1.0        | 3.4     |
| septic_shock_penicillin_all  | Unknown        | 4.3        | 4.3        | 4.0        | 2.3        | 3.8     |
| stemi_inferior_rv_trap       | Unknown        | 3.3        | 4.3        | 4.7        | 4.0        | 4.1     |
| stroke_tpa_eligible          | Unknown        | 13.0       | 10.0       | 10.7       | 13.7       | 11.8    |
+------------------------------+----------------+------------+------------+------------+------------+---------+

## 3. Violation Type Distribution per Model

+--------------+-------------+---------------+-----------+-------------+-------------+-----------+
| Model        | Omission%   | Commission%   | Timing%   | Sequence%   | Deviation%  | Mean/Ep   |
+--------------+-------------+---------------+-----------+-------------+-------------+-----------+
| OSS-120B     | 19.8%       | 1.0%          | 8.0%      | 0.0%        | 71.2%       | 12.82     |
| Qwen-27B     | 31.5%       | 1.4%          | 5.5%      | 0.0%        | 61.5%       | 9.24      |
| Qwen-35B     | 32.8%       | 1.5%          | 5.8%      | 0.0%        | 60.0%       | 8.89      |
| Qwen-4B      | 44.9%       | 2.0%          | 7.6%      | 0.0%        | 45.5%       | 6.69      |
+--------------+-------------+---------------+-----------+-------------+-------------+-----------+

## 4. Domain Aggregation — Mean CGA per Domain per Model

+----------------+------------+------------+------------+------------+---------+
| Domain         | OSS-120B   | Qwen-27B   | Qwen-35B   | Qwen-4B    | Mean    |
+----------------+------------+------------+------------+------------+---------+
| AF             | 0.550      | 0.222      | 0.401      | 0.455      | 0.407   |
| AKI            | 0.554      | 0.541      | 0.566      | 0.560      | 0.555   |
| COPD           | 0.556      | 0.521      | 0.436      | 0.400      | 0.478   |
| ContrastAKI    | 0.556      | 0.510      | 0.547      | 0.507      | 0.530   |
| DKA            | 0.386      | 0.500      | 0.500      | 0.440      | 0.457   |
| GIBleed        | 0.389      | 0.500      | 0.182      | 0.500      | 0.393   |
| HTNEmergency   | 0.528      | 0.282      | 0.433      | 0.403      | 0.412   |
| PE             | 0.611      | 0.342      | 0.385      | 0.200      | 0.385   |
| Unknown        | 0.516      | 0.459      | 0.439      | 0.428      | 0.460   |
+----------------+------------+------------+------------+------------+---------+

### Dominant Violation Type per Domain

+----------------+-----------+-------------+----------+------------+------------+------------+
| Domain         | Omission  | Commission  | Timing   | Sequence   | Deviation  | Dominant   |
+----------------+-----------+-------------+----------+------------+------------+------------+
| AF             | 24        | 0           | 11       | 0          | 95         | deviation  |
| AKI            | 12        | 0           | 0        | 0          | 155        | deviation  |
| COPD           | 28        | 0           | 0        | 0          | 62         | deviation  |
| ContrastAKI    | 15        | 0           | 6        | 0          | 164        | deviation  |
| DKA            | 96        | 24          | 35       | 0          | 92         | omission   |
| GIBleed        | 33        | 0           | 0        | 0          | 65         | deviation  |
| HTNEmergency   | 22        | 0           | 0        | 0          | 109        | deviation  |
| PE             | 24        | 0           | 0        | 0          | 92         | deviation  |
| Unknown        | 257       | 0           | 63       | 0          | 210        | omission   |
+----------------+-----------+-------------+----------+------------+------------+------------+

### Domains Ranked by Commission Violations (safety-critical)

  - **DKA**: 24 commission violations
  - **AF**: 0 commission violations
  - **AKI**: 0 commission violations
  - **COPD**: 0 commission violations
  - **ContrastAKI**: 0 commission violations
  - **GIBleed**: 0 commission violations
  - **HTNEmergency**: 0 commission violations
  - **PE**: 0 commission violations
  - **Unknown**: 0 commission violations

### Domains Ranked by Timing Violations

  - **Unknown**: 63 timing violations
  - **DKA**: 35 timing violations
  - **AF**: 11 timing violations
  - **ContrastAKI**: 6 timing violations
  - **AKI**: 0 timing violations
  - **COPD**: 0 timing violations
  - **GIBleed**: 0 timing violations
  - **HTNEmergency**: 0 timing violations
  - **PE**: 0 timing violations

## 5. Severity Distribution per Model

+--------------+---------+-----------+---------+---------+---------+
| Model        | Minor   | Moderate  | Major   | Severe  | Total   |
+--------------+---------+-----------+---------+---------+---------+
| OSS-120B     | 11      | 542       | 4       | 20      | 577     |
| Qwen-27B     | 6       | 399       | 8       | 3       | 416     |
| Qwen-35B     | 11      | 383       | 6       | 0       | 400     |
| Qwen-4B      | 6       | 286       | 3       | 6       | 301     |
+--------------+---------+-----------+---------+---------+---------+

### Severity Distribution per Domain

+----------------+---------+-----------+---------+---------+---------+
| Domain         | Minor   | Moderate  | Major   | Severe  | Total   |
+----------------+---------+-----------+---------+---------+---------+
| AF             | 3       | 122       | 3       | 2       | 130     |
| AKI            | 0       | 167       | 0       | 0       | 167     |
| COPD           | 0       | 90        | 0       | 0       | 90      |
| ContrastAKI    | 2       | 179       | 2       | 2       | 185     |
| DKA            | 7       | 217       | 0       | 23      | 247     |
| GIBleed        | 0       | 98        | 0       | 0       | 98      |
| HTNEmergency   | 0       | 131       | 0       | 0       | 131     |
| PE             | 0       | 116       | 0       | 0       | 116     |
| Unknown        | 22      | 490       | 16      | 2       | 530     |
+----------------+---------+-----------+---------+---------+---------+

## 6. Scenario Difficulty Ranking

### Hardest Scenarios (lowest mean CGA, all models pooled)

+-------+--------------------------------+----------------+-----------+----------+----------------+
| Rank  | Scenario                       | Domain         | Mean CGA  | Std CGA  | Discrimination |
+-------+--------------------------------+----------------+-----------+----------+----------------+
| 1     | stroke_tpa_eligible            | Unknown        | 0.000     | 0.000    | 0.000          |
| 2     | hemorrhagic_stroke             | Unknown        | 0.100     | 0.143    | 0.139          |
| 3     | dka_hypokalemia_trap           | DKA            | 0.366     | 0.023    | 0.019          |
| 4     | pe_submassive_basic            | PE             | 0.385     | 0.151    | 0.148          |
| 5     | gi_bleeding_upper_basic        | GIBleed        | 0.393     | 0.131    | 0.130          |
| 6     | adhf_warm_wet                  | Unknown        | 0.395     | 0.086    | 0.064          |
| 7     | af_new_onset_basic             | AF             | 0.407     | 0.124    | 0.119          |
| 8     | htn_emergency_basic            | HTNEmergency   | 0.412     | 0.124    | 0.088          |
| 9     | copd_moderate_exacerbation     | COPD           | 0.478     | 0.103    | 0.063          |
| 10    | contrast_aki_prevention_basic  | ContrastAKI    | 0.530     | 0.025    | 0.022          |
| 11    | dka_moderate_basic             | DKA            | 0.547     | 0.079    | 0.078          |
| 12    | aki_stage1_basic               | AKI            | 0.555     | 0.011    | 0.009          |
| 13    | stemi_inferior_rv_trap         | Unknown        | 0.743     | 0.047    | 0.043          |
| 14    | septic_shock_penicillin_aller  | Unknown        | 0.748     | 0.061    | 0.043          |
| 15    | septic_shock_basic             | Unknown        | 0.776     | 0.026    | 0.023          |
+-------+--------------------------------+----------------+-----------+----------+----------------+

## 7. Core 8 vs Expansion 7 Scenarios

**Core scenarios (3):** aki_stage1_basic, dka_hypokalemia_trap, dka_moderate_basic

**Expansion scenarios (12):** adhf_warm_wet, af_new_onset_basic, contrast_aki_prevention_basic, copd_moderate_exacerbation, gi_bleeding_upper_basic, hemorrhagic_stroke, htn_emergency_basic, pe_submassive_basic, septic_shock_basic, septic_shock_penicillin_allergy, stemi_inferior_rv_trap, stroke_tpa_eligible

+--------------------------------+------------+------------+
| Metric                         | Core       | Expansion  |
+--------------------------------+------------+------------+
| N episodes                     | 36         | 144        |
| Mean CGA                       | 0.489      | 0.447      |
| Std CGA                        | 0.100      | 0.249      |
|   Omission %                   | 26.1%      | 31.5%      |
|   Commission %                 | 5.8%       | 0.0%       |
|   Timing %                     | 8.5%       | 6.2%       |
|   Sequence %                   | 0.0%       | 0.0%       |
|   Deviation %                  | 59.7%      | 62.3%      |
|   OSS-120B mean CGA            | 0.442      | 0.524      |
|   Qwen-27B mean CGA            | 0.514      | 0.428      |
|   Qwen-35B mean CGA            | 0.522      | 0.418      |
|   Qwen-4B mean CGA             | 0.480      | 0.419      |
| Model ranking                  | Qwen-35B>Qwen-27B>Qwen-4B>OSS-120B | OSS-120B>Qwen-27B>Qwen-4B>Qwen-35B |
| Ranking stable?                | —          | NO         |
+--------------------------------+------------+------------+
