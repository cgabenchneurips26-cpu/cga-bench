# YAML Graph ↔ CPG Cross-Validation Report

**Date**: 2026-04-04
**Domains validated**: 25
**Manually curated**: 3
**Auto-generated**: 22

## Summary

| Category | Count | Impact |
|---|---|---|
| True hallucinations (auto-gen) | 0 | Affects grade |
| Vocabulary gaps (manual files) | 64 | Informational only |
| Omissions | 0 | Affects grade |
| Confirmed errors | 16 | Affects grade |
| Informational notes | 38 | Does not affect grade |
| **Total confirmed issues** | **16** | |

| Grade | Count |
|---|---|
| A (excellent) | 16 |
| B (good) | 6 |
| C (acceptable) | 1 |
| D (needs review) | 2 |

**Overall verdict**: NEEDS REVIEW -- Issues detected requiring clinical review.

> **Note on vocabulary gaps**: The 3 manually-curated parsed.json files (sepsis, chest pain, KDIGO AKI) use natural clinical language while the YAML graphs use snake_case action identifiers. The reported vocabulary gaps are expected terminology differences, not real hallucinations.

---

## Per-Domain Results

| Domain | Type | Halluc. | Vocab Gap | Omis. | Errors | Info | Grade |
|---|---|---|---|---|---|---|---|
| aabb_transfusion | Auto | 0 | 0 | 0 | 0 | 1 | **A** |
| aha_chest_pain_evaluation | Manual | 0 | 23 | 0 | 0 | 11 | **A** |
| aha_heart_failure_2022 | Auto | 0 | 0 | 0 | 0 | 0 | **A** |
| anaphylaxis_management | Auto | 0 | 0 | 0 | 0 | 0 | **A** |
| apa_agitation_management | Auto | 0 | 0 | 0 | 0 | 1 | **A** |
| atrial_fibrillation | Auto | 0 | 0 | 0 | 0 | 0 | **A** |
| copd_exacerbation | Auto | 0 | 0 | 0 | 0 | 0 | **A** |
| gi_bleeding | Auto | 0 | 0 | 0 | 0 | 0 | **A** |
| hypertensive_emergency | Auto | 0 | 0 | 0 | 0 | 0 | **A** |
| idsa_meningitis | Auto | 0 | 0 | 0 | 0 | 0 | **A** |
| kdigo_aki_full | Manual | 0 | 18 | 0 | 0 | 14 | **A** |
| kdigo_contrast_aki | Auto | 0 | 0 | 0 | 0 | 0 | **A** |
| pals_pediatric_emergency | Auto | 0 | 0 | 0 | 0 | 0 | **A** |
| pulmonary_embolism | Auto | 0 | 0 | 0 | 0 | 0 | **A** |
| status_epilepticus | Auto | 0 | 0 | 0 | 0 | 0 | **A** |
| universal_clinical_safety | Auto | 0 | 0 | 0 | 0 | 0 | **A** |
| aba_burn_resuscitation | Auto | 0 | 0 | 0 | 1 | 1 | **B** |
| acog_obstetric_hemorrhage | Auto | 0 | 0 | 0 | 1 | 0 | **B** |
| aha_stroke_2019 | Auto | 0 | 0 | 0 | 1 | 0 | **B** |
| cap_pneumonia | Auto | 0 | 0 | 0 | 1 | 0 | **B** |
| ssc_sepsis_hour1_bundle | Manual | 0 | 23 | 0 | 1 | 5 | **B** |
| toxicology_management | Auto | 0 | 0 | 0 | 1 | 3 | **B** |
| acls_cardiac_arrest | Auto | 0 | 0 | 0 | 2 | 1 | **C** |
| ada_dka_management | Auto | 0 | 0 | 0 | 5 | 0 | **D** |
| gina_asthma_exacerbation | Auto | 0 | 0 | 0 | 3 | 1 | **D** |

---

## Detailed Findings (Confirmed Issues)

### ada_dka_management (Grade D)

*Type*: Auto-generated

**Confirmed Errors**:

- [timing_mismatch] Deadline mismatch for 'recheck_potassium_in_1h': graph=90.0min, CPG=30.0min
- [timing_mismatch] Deadline mismatch for 'monitor_potassium_q2h': graph=120.0min, CPG=60.0min
- [timing_mismatch] Deadline mismatch for 'place_arterial_line': graph=60.0min, CPG=30.0min
- [timing_mismatch] Deadline mismatch for 'monitor_bmp_q2_4h': graph=240.0min, CPG=60.0min
- [timing_mismatch] Deadline mismatch for 'assess_anion_gap_closure': graph=240.0min, CPG=60.0min

### gina_asthma_exacerbation (Grade D)

*Type*: Auto-generated

**Confirmed Errors**:

- [timing_mismatch] Deadline mismatch for 'measure_oxygen_saturation': graph=3.0min, CPG=10.0min
- [timing_mismatch] Deadline mismatch for 'perform_endotracheal_intubation': graph=15.0min, CPG=5.0min
- [timing_mismatch] Deadline mismatch for 'determine_disposition': graph=240.0min, CPG=60.0min

### acls_cardiac_arrest (Grade C)

*Type*: Auto-generated

**Confirmed Errors**:

- [timing_mismatch] Deadline mismatch for 'evaluate_reversible_causes': graph=10.0min, CPG=3.0min
- [timing_mismatch] Deadline mismatch for 'optimize_hemodynamics': graph=15.0min, CPG=60.0min

### aba_burn_resuscitation (Grade B)

*Type*: Auto-generated

**Confirmed Errors**:

- [timing_mismatch] Deadline mismatch for 'estimate_tbsa': graph=15.0min, CPG=5.0min

### acog_obstetric_hemorrhage (Grade B)

*Type*: Auto-generated

**Confirmed Errors**:

- [timing_mismatch] Deadline mismatch for 'consult_surgery': graph=30.0min, CPG=60.0min

### aha_stroke_2019 (Grade B)

*Type*: Auto-generated

**Confirmed Errors**:

- [timing_mismatch] Deadline mismatch for 'order_stat_ct_head': graph=25.0min, CPG=10.0min

### cap_pneumonia (Grade B)

*Type*: Auto-generated

**Confirmed Errors**:

- [timing_mismatch] Deadline mismatch for 'give_beta_lactam_plus_macrolide': graph=60.0min, CPG=240.0min

### ssc_sepsis_hour1_bundle (Grade B)

*Type*: Manually curated

**Confirmed Errors**:

- [timing_mismatch] Deadline mismatch for 'start_vasopressor_if_hypotensive': graph=60.0min, CPG=180.0min

### toxicology_management (Grade B)

*Type*: Auto-generated

**Confirmed Errors**:

- [timing_mismatch] Deadline mismatch for 'review_ecg_for_toxicity': graph=15.0min, CPG=30.0min

---

## Informational: Manual File Vocabulary Gaps

These are expected terminology differences between manually-written parsed.json files and the YAML graph's snake_case action identifiers. They do NOT indicate errors.

### aha_chest_pain_evaluation

Vocabulary gaps: 23 actions

- `activate_cath_lab` (mandatory)
- `admit_to_cardiology_service` (mandatory)
- `admit_to_ccu` (mandatory)
- `determine_disposition` (mandatory)
- `discharge_home` (forbidden)
- ... and 18 more

Informational notes: 11

- [timing_possible_fp] Large timing gap for 'assess_for_early_invasive': graph=120.0min vs CPG=1440.0min (likely false positive, ratio=12.0x)
- [quote_vocabulary_gap] Source quote in node 'Initial Chest Pain Assessment' uses different wording than manually-curated parsed.json (expected)
- [quote_vocabulary_gap] Source quote in node 'ECG Interpretation' uses different wording than manually-curated parsed.json (expected)
- ... and 8 more

### kdigo_aki_full

Vocabulary gaps: 18 actions

- `assess_for_ckd_development` (mandatory)
- `assess_vascular_access` (mandatory)
- `give_albumin_infusion` (conditional)
- `give_aminoglycoside_in_hepatorenal` (conditional)
- `give_aminoglycoside_without_monitoring` (conditional)
- ... and 13 more

Informational notes: 14

- [timing_possible_fp] Large timing gap for 'order_baseline_creatinine': graph=60.0min vs CPG=2880.0min (likely false positive, ratio=48.0x)
- [quote_vocabulary_gap] Source quote in node 'Initial AKI Assessment' uses different wording than manually-curated parsed.json (expected)
- [quote_vocabulary_gap] Source quote in node 'AKI Staging' uses different wording than manually-curated parsed.json (expected)
- ... and 11 more

### ssc_sepsis_hour1_bundle

Vocabulary gaps: 23 actions

- `admit_to_icu` (mandatory)
- `admit_to_ward` (forbidden)
- `assess_organ_dysfunction` (mandatory)
- `attribute_ams_to_dementia` (conditional)
- `determine_disposition` (mandatory)
- ... and 18 more

Informational notes: 5

- [quote_vocabulary_gap] Source quote in node 'Sepsis Recognition' uses different wording than manually-curated parsed.json (expected)
- [quote_vocabulary_gap] Source quote in node 'Septic Shock Hour-1 Bundle' uses different wording than manually-curated parsed.json (expected)
- [quote_vocabulary_gap] Source quote in node 'Reassessment after Initial Bundle' uses different wording than manually-curated parsed.json (expected)
- ... and 2 more

---

## Clean Domains (0 confirmed issues)

- aabb_transfusion (Grade A)
- aha_chest_pain_evaluation (Grade A)
- aha_heart_failure_2022 (Grade A)
- anaphylaxis_management (Grade A)
- apa_agitation_management (Grade A)
- atrial_fibrillation (Grade A)
- copd_exacerbation (Grade A)
- gi_bleeding (Grade A)
- hypertensive_emergency (Grade A)
- idsa_meningitis (Grade A)
- kdigo_aki_full (Grade A)
- kdigo_contrast_aki (Grade A)
- pals_pediatric_emergency (Grade A)
- pulmonary_embolism (Grade A)
- status_epilepticus (Grade A)
- universal_clinical_safety (Grade A)

---

## Methodology

### Issue Classification

Issues are classified into two tiers:

**Confirmed (affects grade)**:
- *True hallucinations*: Auto-generated parsed.json actions not supported by graph text (indicates generation bug)
- *Omissions*: Strong CPG recommendations with no matching graph action
- *Confirmed errors*: Timing mismatches with <4x ratio (credible discrepancy)

**Informational (does NOT affect grade)**:
- *Vocabulary gaps*: Manual parsed.json uses different terminology than graph action IDs (expected)
- *Timing possible FP*: Timing mismatches with >4x ratio (likely regex false positive)
- *Quote vocabulary gap*: Manual file source quotes use different wording (expected)

### Limitations

- 22/25 parsed.json auto-generated from YAML graphs: cross-validation is internal consistency check
- 3/25 manually curated: genuine cross-validation possible but vocabulary differences are expected
- Timing detection uses keyword proximity with >=2 keyword requirement to reduce false positives
