# EX-30: Non-Timing Trap Augmentation

## Overview

Demonstrates that BEFORE and FORBIDDEN constraints (no WITHIN involved) independently create blind spots where coverage-based evaluators pass but TCC fails. Addresses the concern that CGA-Bench is 'only a timing benchmark.'

## Graph Constraint Inventory

- **Total non-timing constraints:** 226
  - BEFORE (sequence): 9
  - FORBIDDEN (combination): 5
  - FORBIDDEN (per-node): 212
- **Graphs with non-timing constraints:** 25/25

## Phase 1: Natural Non-Timing Blind Spots

From 16944 canonical episodes:
- **Non-timing TCC failures:** 354 (2.09%)
- **AC-Proxy blind:** 255 (72.0% of non-timing failures)
- **MAB-Proxy blind:** 184 (52.0% of non-timing failures)
- **Both AC+MAB blind:** 175

Violation type breakdown:
  - ('FORBIDDEN',): 315
  - ('BEFORE',): 39

## Phase 2: Synthetic Trap Traces

| Trap | Constraint | Coverage | F1 | AC Pass | TCC Fail | Blind Spot |
|------|-----------|----------|----|---------|---------:|------------|
| tpa_before_ct | BEFORE | 1.000 | 1.000 | YES | YES | YES |
| anticoag_after_tpa | FORBIDDEN | 1.000 | 0.889 | YES | YES | YES |
| nitrates_rv_infarct | FORBIDDEN | 1.000 | 0.889 | YES | YES | YES |
| insulin_before_k_correction | BEFORE+FORBIDDEN | 1.000 | 1.000 | YES | YES | YES |

### Trap Details

**tpa_before_ct**: Stroke: tPA administered before CT head rules out hemorrhage. BEFORE constraint from aha_stroke_2019 sequence_dependencies.
- Constraint source: `sequence_dependencies: order_stat_ct_head before administer_iv_tpa`
- Violating trace: ['activate_stroke_team', 'perform_nihss', 'establish_iv_access', 'give_alteplase_0.9mg_kg', 'order_stat_ct_head']
- Conformant trace: ['activate_stroke_team', 'perform_nihss', 'establish_iv_access', 'order_stat_ct_head', 'give_alteplase_0.9mg_kg']

**anticoag_after_tpa**: Stroke: anticoagulation given within 24h after tPA. FORBIDDEN combination from aha_stroke_2019 forbidden_combinations.
- Constraint source: `forbidden_combinations: give_alteplase + anticoagulation_within_24h`
- Violating trace: ['activate_stroke_team', 'order_stat_ct_head', 'give_alteplase_0.9mg_kg', 'give_anticoagulation', 'monitor_neurological_status']
- Conformant trace: ['activate_stroke_team', 'order_stat_ct_head', 'give_alteplase_0.9mg_kg', 'monitor_neurological_status']

**nitrates_rv_infarct**: Chest pain: nitroglycerin given to RV infarct patient. FORBIDDEN from aha_chest_pain_evaluation node forbidden_actions.
- Constraint source: `node forbidden_actions: give_nitroglycerin (RV infarct context)`
- Violating trace: ['obtain_12_lead_ecg', 'order_troponin', 'give_aspirin_loading', 'give_nitroglycerin', 'obtain_right_sided_ecg']
- Conformant trace: ['obtain_12_lead_ecg', 'order_troponin', 'give_aspirin_loading', 'obtain_right_sided_ecg']

**insulin_before_k_correction**: DKA: insulin started before potassium correction when K+ < 3.3. FORBIDDEN from ada_dka_management node forbidden_actions.
- Constraint source: `node forbidden_actions: start_insulin_drip (K+ < 3.3 context)`
- Violating trace: ['order_lab_basic_metabolic_panel', 'give_crystalloid_fluid', 'order_lab_potassium', 'start_insulin_drip', 'correct_potassium']
- Conformant trace: ['order_lab_basic_metabolic_panel', 'give_crystalloid_fluid', 'order_lab_potassium', 'correct_potassium', 'start_insulin_drip']

## Interpretation

Of 16944 real episodes, 354 (2.09%) have hard violations from BEFORE/FORBIDDEN constraints alone (zero WITHIN violations). Of these, 255 (72.0%) are missed by AC-Proxy. All 4 synthetic traps confirm that coverage-based evaluators are structurally blind to ordering and conditional-forbidden violations. CGA-Bench is not merely a 'timing benchmark' — non-timing constraint dimensions account for the majority of its constraint inventory (226 non-timing vs graph WITHIN constraints) and produce real blind spots in practice.
