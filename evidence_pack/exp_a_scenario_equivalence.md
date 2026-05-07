# EXP-A: Scenario Structural Equivalence Report

**Manual scenarios**: 107
**Auto scenarios**: 601
**Enriched (with graph match)**: 706

Bonferroni correction applied (k=6).

## 1. Constraint Density

| Type | Manual (mean +/- sd) | Auto (mean +/- sd) | U | p (adj) | d |
|------|----------------------|--------------------|---|---------|---|
| FORBIDDEN | 9.733 +/- 6.477 | 13.501 +/- 8.301 | 23283 | 1.05e-04 | -0.468 |
| REQUIRED | 0.010 +/- 0.098 | 0.411 +/- 0.591 | 20498 | 6.67e-12 | -0.734 |
| BEFORE | 3.476 +/- 4.589 | 2.624 +/- 3.528 | 32938 | 1.0000 | 0.230 |
| WITHIN | 0.000 +/- 0.000 | 0.000 +/- 0.000 | 31552 | 1.0000 | 0.000 |
| EXPECTED | 12.790 +/- 5.675 | 14.027 +/- 5.809 | 27014 | 0.1092 | -0.214 |
| **Total** | 26.010 +/- 14.596 | 30.562 +/- 14.112 | 24906 | 0.0034 | -0.321 |

## 2. Domain Coverage

- Jaccard similarity: **0.538**
- Manual domains: 15, Auto domains: 25
- Shared: 14, Manual-only: [''], Auto-only: ['aabb_transfusion', 'aba_burn_resuscitation', 'acls_cardiac_arrest', 'acog_obstetric_hemorrhage', 'anaphylaxis_management', 'apa_agitation_management', 'gina_asthma_exacerbation', 'idsa_meningitis', 'pals_pediatric_emergency', 'status_epilepticus', 'toxicology_management']
- Chi-square: chi2=117.038, p(adj)=4.41e-13

## 3. Patient Complexity

**Active conditions**: Manual 2.019 +/- 1.101, Auto 0.923 +/- 0.880, KS=0.468, p(adj)=1.47e-17, d=1.196

**Triggered rules**: Manual 0.695 +/- 0.845, Auto 4.220 +/- 3.685, KS=0.523, p(adj)=2.42e-22, d=-1.031

## 4. Expected Actions

Manual: 6.619 +/- 1.695 (n=105)
Auto: 14.003 +/- 5.798 (n=601)
Mann-Whitney U=7092, p(adj)=2.83e-36, d=-1.370

## 5. Trap Scenario Ratio

Manual: 64/107 (59.8%)
Auto: 505/601 (84.0%)
Chi-square=32.233, p(adj)=8.20e-08

## 6. Provenance Completeness

**Auto provenance validity**: 18288/18368 (99.6%)
  Invalid examples: ["aha_ch_trap_aspirin_allergy_no_aspirin: 'allergy_map:aspirin'", "aha_ch_combo_active_bleed_no_anticoag_aspirin_allergy_no_aspirin: 'allergy_map:aspirin'", "aha_ch_combo_cocaine_no_bb_aspirin_allergy_no_aspirin: 'allergy_map:aspirin'"]
**Manual derivation coverage**: mean=0.989 +/- 0.084, 95% CI [0.971, 1.000]
  (n=105 scenarios with expected_actions)

## Summary

Of 6 analyses (Bonferroni-corrected), **6** show statistically significant differences between manual and auto scenarios.
