# EX-18: Artifact Mimic — TCC Value-Add Over Existing Evaluators

**Episodes analyzed:** 16944

**Headline:** AC+TCC catches 57.1% more failures than AC alone (7202/12609 AC-passing episodes have hard violations). MAB+TCC: 60.3% gain. C2+TCC: 44.3% gain.

## Pass Rates by Evaluator

| Evaluator | Pass | Rate |
|-----------|------|------|
| AC | 12609 | 74.4% |
| MAB | 8972 | 53.0% |
| C2 | 5837 | 34.4% |
| TCC | 8391 | 49.5% |

## TCC Gain (Blind Spots Exposed)

| Proxy | Proxy=PASS & TCC=FAIL | Gain (%) |
|-------|----------------------|----------|
| AC-Proxy | 7202 | 57.1% |
| MAB-Proxy | 5406 | 60.3% |
| C2 | 2585 | 44.3% |

## Blind Spot Violation Types

Among AC-passing episodes that TCC catches:

- COMMISSION: 1770
- DEVIATION: 26771
- OMISSION: 29084
- SEQUENCE: 283
- TIMING: 13016

## Per-Model Breakdown

| Model | N | AC Pass% | TCC Pass% | AC+TCC Gain | Gain% |
|-------|---|----------|-----------|-------------|-------|
| deepseek_r1_7b | 2118 | 76.3% | 34.9% | 1203 | 74.4% |
| gemma31b | 2118 | 74.2% | 59.8% | 722 | 45.9% |
| nemotron30b | 2118 | 56.9% | 56.0% | 711 | 59.0% |
| oss120b | 2118 | 85.4% | 46.3% | 1031 | 57.0% |
| qwen27b | 2118 | 79.1% | 44.7% | 927 | 55.3% |
| qwen35b | 2118 | 83.5% | 52.7% | 904 | 51.1% |
| qwen397b | 2118 | 82.9% | 45.4% | 1049 | 59.7% |
| qwen4b | 2118 | 56.9% | 56.3% | 655 | 54.3% |

## Example Blind Spots

- **aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi** (deepseek_r1_7b r0): coverage=0.833, violations={'DEVIATION': 3, 'TIMING': 1, 'OMISSION': 2}
- **aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood** (deepseek_r1_7b r1): coverage=0.857, violations={'DEVIATION': 4, 'TIMING': 1, 'OMISSION': 1}
- **aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood** (deepseek_r1_7b r2): coverage=0.857, violations={'DEVIATION': 4, 'TIMING': 1, 'OMISSION': 1}
- **aabb_t_combo_txa_within_3h_jehovah_no_blood** (deepseek_r1_7b r0): coverage=1.0, violations={'DEVIATION': 4, 'TIMING': 1, 'COMMISSION': 1}
- **aabb_t_combo_txa_within_3h_jehovah_no_blood** (deepseek_r1_7b r1): coverage=1.0, violations={'DEVIATION': 4, 'TIMING': 1}
- **aabb_t_pathway_restrictive_thr_massive_transfu_transfusion_rea** (deepseek_r1_7b r1): coverage=1.0, violations={'DEVIATION': 4, 'TIMING': 1}
- **aabb_t_pathway_restrictive_thr_massive_transfu_transfusion_rea** (deepseek_r1_7b r2): coverage=1.0, violations={'TIMING': 1, 'DEVIATION': 3}
- **aabb_t_trap_cardiac_liberal_threshold** (deepseek_r1_7b r1): coverage=0.857, violations={'DEVIATION': 4, 'TIMING': 1, 'OMISSION': 1}
- **aabb_t_trap_jehovah_no_blood** (deepseek_r1_7b r1): coverage=1.0, violations={'DEVIATION': 4, 'TIMING': 1}
- **aabb_t_trap_txa_within_3h** (deepseek_r1_7b r1): coverage=1.0, violations={'DEVIATION': 4, 'TIMING': 1}