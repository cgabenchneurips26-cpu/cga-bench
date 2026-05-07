# EX-32: Solver Taxonomy — Tiered-Better Classification

**Total episodes:** 16944
**Equal:** 12060
**Tiered better:** 1511 (8.92%)
**ILP better:** 3373 (19.91%)
**Verdict reversals:** 0
**Mean diff (tiered-better):** 1176.4
**Runtime:** 834.0s

## Category Breakdown

| Category | Count | % of TB | % of Total | Mean Diff | Max Diff | Reversals |
|----------|-------|---------|------------|-----------|----------|-----------|
| Tie Break | 240 | 15.9% | 1.42% | 8.0 | 10.0 | 0 |
| Phase Ordering | 241 | 15.9% | 1.42% | 21.1 | 80.0 | 0 |
| Formulation Gap | 1030 | 68.2% | 6.08% | 1718.9 | 14210.0 | 0 |

## Per-Graph Breakdown

| Graph | Tiered Better | ILP Better | Equal | Mean Diff | Max Diff |
|-------|---------------|------------|-------|-----------|----------|
| kdigo_contrast_aki | 380 | 375 | 253 | 16.1 | 80.0 |
| acls_cardiac_arrest | 327 | 17 | 712 | 517.7 | 980.0 |
| ada_dka_management | 319 | 689 | 0 | 2882.7 | 14210.0 |
| status_epilepticus | 289 | 31 | 64 | 2194.2 | 8915.0 |
| anaphylaxis_management | 90 | 272 | 46 | 473.4 | 980.0 |
| aba_burn_resuscitation | 53 | 4 | 423 | 7.7 | 15.0 |
| pals_pediatric_emergency | 17 | 222 | 1 | 7.4 | 25.0 |
| aha_stroke_2019 | 12 | 0 | 876 | 8.8 | 10.0 |
| apa_agitation_management | 10 | 2 | 348 | 16.5 | 30.0 |
| atrial_fibrillation | 4 | 0 | 548 | 11.2 | 25.0 |
| idsa_meningitis | 4 | 16 | 724 | 617.5 | 1000.0 |
| aha_heart_failure_2022 | 2 | 0 | 1294 | 7.5 | 10.0 |
| gina_asthma_exacerbation | 2 | 184 | 918 | 750.0 | 1000.0 |
| aabb_transfusion | 1 | 0 | 287 | 1000.0 | 1000.0 |
| ssc_sepsis_hour1_bundle | 1 | 397 | 154 | 5.0 | 5.0 |
| aha_chest_pain_evaluation | 0 | 816 | 0 | 0 | 0 |
| cap_pneumonia | 0 | 63 | 465 | 0 | 0 |
| pulmonary_embolism | 0 | 285 | 411 | 0 | 0 |

## Verdict Reversals

**None.** No tiered-better episode flips a PASS/FAIL verdict. Both solvers agree on pass/fail for all diverged episodes.

## Interpretation

The dominant source of tiered-better episodes is **kdigo_contrast_aki** (380 episodes). 
Tie-break cases (|diff| <= 10) are numeric precision differences. Phase-ordering cases (10 < |diff| <= 100) arise from tiered's greedy FORBIDDEN-first processing. Formulation gaps (|diff| > 100) indicate genuine structural differences in how constraints interact. Zero verdict reversals confirms solver choice does not affect headline conclusions.