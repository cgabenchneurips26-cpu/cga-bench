# Normalizer Gap Clinical Review Summary

## Context

OMISSION root cause analysis (v2) initially concluded H2 (normalizer gap) was minor (37 pairs).
Raw episode inspection revealed 66.1% near-miss rate in mismatch-selected episodes.
Full quantification across 9,674 episodes shows the true rate is 18.2% — significant but not dominant.

## Key Numbers

| Metric | Value |
|--------|-------|
| Total episodes | 9,674 |
| Total expected actions | 137,924 |
| Total omitted actions | 58,667 |
| Near-miss omissions (sim>=0.5) | 10,653 (18.2%) |
| Episodes with near-miss | 4,681 (48.4%) |
| Unique (performed, expected) pairs | 356 |

## Projected Impact by Fix Threshold

| Threshold | Pairs | Removable | Rate Before | Rate After | Reduction |
|-----------|-------|-----------|-------------|------------|-----------|
| 0.9 | 6 | 243 | 42.5% | 42.4% | 0.4% |
| 0.8 | 35 | 1,090 | 42.5% | 41.8% | 1.9% |
| 0.7 | 86 | 2,364 | 42.5% | 40.8% | 4.0% |
| 0.6 | 180 | 5,219 | 42.5% | 38.8% | 8.9% |
| 0.5 | 356 | 10,653 | 42.5% | 34.8% | 18.2% |

## Why 66% Became 18%

The 66.1% near-miss rate from the 10-episode mismatch inspection was selection-biased:
those 10 episodes were specifically chosen for having the MOST near-misses.
The population rate across all 9,674 episodes is 18.2%.

## Clinical Validity Assessment of Top Pairs

Many high-similarity pairs are clinically INVALID matches. String similarity ≠ clinical equivalence.

### VALID Aliases (same clinical intent)

| Performed | Expected | Sim | Episodes | Reason |
|-----------|----------|-----|----------|--------|
| `discontinue_nephrotoxic_agents` | `discontinue_nephrotoxins` | 0.89 | 125 | Exact synonym |
| `consult_nephrology_if_needed` | `consult_nephrology` | 0.78 | 231 | Conditional satisfies unconditional |
| `monitor_creatinine_q6h` | `monitor_creatinine_q12h` | 0.93 | 207 | More frequent satisfies less frequent |
| `monitor_creatinine_q6h` | `monitor_creatinine_daily` | 0.83 | 216 | More frequent satisfies less frequent |
| `order_type_and_crossmatch` | `type_and_crossmatch` | 0.86 | 54 | Prefix variant |
| `optimize_fluid_status` | `optimize_volume_status` | 0.84 | 24 | Clinical synonym |
| `give_iv_crystalloid_bolus` | `give_crystalloid_fluid` | 0.81 | 23 | Specific satisfies general |
| `give_crystalloid_fluid` | `give_crystalloid_30ml_kg` | 0.78 | 28 | General satisfies specific (debatable) |
| `check_scr_at_72h` | `check_scr_at_48h` | 0.88 | 91 | Serial monitoring (q6h covers both) |
| `give_anticoagulation` | `initiate_anticoagulation` | 0.82 | 21 | Verb variant |
| `observe_minimum_24_hours` | `observe_minimum_4_hours` | 0.98 | 15 | Longer satisfies shorter |
| `order_imaging_ct_head` | `order_stat_ct_head` | 0.77 | 50 | Urgency variant |
| `give_iv_diuretic` | `iv_diuretics` | 0.79 | 49 | Verb/noun variant |
| `order_serial_ecg` | `serial_ecg` | 0.77 | 17 | Prefix variant |
| `establish_iv_access` | `establish_large_bore_iv_access` | 0.78 | 24 | General satisfies specific |
| `assess_aki_risk_factors` | `assess_aki_risk` | 0.79 | 12 | Suffix variant |
| `avoid_additional_nephrotoxins` | `avoid_nephrotoxins` | 0.77 | 22 | Adjective variant |
| `admit_to_icu_or_stroke_unit` | `admit_to_stroke_unit` | 0.85 | 13 | Superset satisfies subset |
| `review_nephrotoxic_medications` | `review_medications` | 0.75 | 26 | Specific satisfies general |
| `give_aspirin_loading` | `give_aspirin` | 0.75 | 31 | Specific satisfies general |
| `give_bronchodilator` | `give_short_acting_bronchodilator` | 0.74 | 43 | General satisfies specific |
| `give_epinephrine_repeat_3_5min` | `give_epinephrine_1mg_iv` | 0.72 | 23 | Same drug, timing variant |
| `monitor_potassium` | `monitor_potassium_q4h` | 0.90 | 26 | General satisfies specific |
| `monitor_potassium` | `monitor_potassium_q6h` | 0.90 | 18 | General satisfies specific |
| `monitor_urine_output` | `monitor_urine_output_target_200ml_h` | 0.73 | 26 | General satisfies specific |
| `review_nephrotoxic_medications` | `hold_nephrotoxic_medications` | 0.83 | 12 | Review implies hold (debatable) |
| `consider_ace_or_arb_or_arni` | `initiate_ace_or_arb_or_arni` | 0.78 | 97 | Consider ≈ initiate in context |
| `consider_beta_blocker` | `initiate_beta_blocker` | 0.71 | 94 | Consider ≈ initiate in context |

### PARTIALLY VALID (need clinical judgment)

| Performed | Expected | Sim | Episodes | Concern |
|-----------|----------|-----|----------|---------|
| `calculate_contrast_volume_limit` | `use_minimum_contrast_volume` | 0.62 | 539 | Calculating limit IS using minimum, but action semantics differ |
| `give_hydrocortisone_iv` | `give_systemic_corticosteroid` | 0.56 | 251 | Hydrocortisone IS a systemic corticosteroid |
| `give_hydrocortisone_iv` | `give_systemic_corticosteroid_iv` | 0.60 | 244 | Same as above, IV route matches |
| `prescribe_oral_corticosteroid_5_day` | `give_systemic_corticosteroid` | 0.57 | 141 | Oral steroid IS systemic corticosteroid |

### INVALID (clinically distinct actions)

| Performed | Expected | Sim | Episodes | Why Invalid |
|-----------|----------|-----|----------|-------------|
| `assess_inhaler_technique` | `reassess_after_treatment` | 0.58 | 552 | Different clinical actions entirely |
| `check_current_medications` | `hold_nephrotoxic_medications` | 0.60 | 279 | Checking ≠ holding |
| `order_lab_coagulation` | `give_anticoagulation` | 0.68 | 258 | Ordering test ≠ giving treatment |
| `give_epinephrine_nebulized` | `give_epinephrine_im` | 0.80 | 111 | Different routes, clinically distinct |
| `admit_to_ward` | `admit_to_icu` | 0.72 | 83 | Different acuity levels |
| `order_lab_blood_culture` | `order_lab_blood_gas` | 0.76 | 74 | Completely different tests |
| `consult_cardiology` | `consult_endocrinology` | 0.77 | 48 | Different specialties |
| `order_lab_inr` | `order_lab_free_t4` | 0.73 | 44 | Completely different tests |
| `order_lab_inr` | `order_lab_free_t3` | 0.73 | 44 | Completely different tests |
| `continuous_cardiac_monitoring` | `continuous_fetal_monitoring` | 0.82 | 16 | Cardiac ≠ fetal |
| `order_lab_bmp` | `order_lab_crp` | 0.85 | 12 | Different panels |
| `order_lab_anion_gap` | `order_lab_abg` | 0.75 | 14 | Different tests |

## Revised Diagnosis

1. **Primary OMISSION cause**: Model capability — models fail to emit specific mandatory actions
2. **Secondary cause**: Normalizer gap (~8-10% of omissions are genuinely fixable)
3. **Not a cause**: Action effects coverage (all mandatory actions exist in action_effects)
4. **Confounding factor**: 48.4% of episodes have at least one near-miss, inflating perceived gap in small samples

## Impact Estimate for Normalizer Fix

Fixing the ~28 VALID aliases above (total impact ~1,500-2,000 episodes) would:
- Reduce omission rate from ~42.5% to ~41.0-41.5%
- Reduce OMISSION count by ~2-3%
- Meaningful for paper accuracy but does not change the narrative

The PARTIALLY VALID aliases (hydrocortisone→corticosteroid, calculate_contrast→use_minimum_contrast)
could add another ~1,000 episodes if accepted after clinician review.
