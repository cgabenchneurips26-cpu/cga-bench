================================================================================
EPISODE SYSTEMATIC SELF-REVIEW
Verified: 30 episodes
================================================================================

## Summary
  Clean episodes: 8/30
  Episodes with issues: 22/30 (73%)
  Total issues found: 198

## Bug Classification
  Bug Type                                  Count  % of episodes
  ---------------------------------------- ------ --------------
  PHANTOM_DEVIATION                           116            70%
  MISSING_TIMING                               32            40%
  FALSE_OMISSION_SHOULD_BE_TIMING              27            40%
  FALSE_OMISSION_PERFORMED                     22            23%
  COMMISSION_NOT_FORBIDDEN                      1             3%

## Bug Examples

  PHANTOM_DEVIATION:
    gemma31b/dka_alcoholic_ketoacidosis_mimic: order_lab_unknown — DEVIATION references action not in performed trace
    gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi: order_lab_type_and_screen — DEVIATION references action not in performed trace
    gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi: order_imaging_ct — DEVIATION references action not in performed trace

  COMMISSION_NOT_FORBIDDEN:
    gemma31b/dka_cerebral_edema_pediatric_trap: start_insulin_infusion — COMMISSION violation but action not in episode's forbidden list

  FALSE_OMISSION_PERFORMED:
    gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi: apply_liberal_threshold_hb_8 — Action performed (t=95.0m) but marked OMISSION (no deadline or within deadline)
    gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi: transfuse_if_hb_below_8 — Action performed (t=100.0m) but marked OMISSION (no deadline or within deadline)
    gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi: apply_liberal_threshold_hb_8 — Action performed (t=95.0m) but marked OMISSION (no deadline or within deadline)

  FALSE_OMISSION_SHOULD_BE_TIMING:
    gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi: send_blood_bank_workup — Performed at t=90.0m, deadline=30m → should be TIMING, not OMISSION
    gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi: send_blood_bank_workup — Performed at t=90.0m, deadline=30m → should be TIMING, not OMISSION
    gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi: send_blood_bank_workup — Performed at t=90.0m, deadline=30m → should be TIMING, not OMISSION

  MISSING_TIMING:
    gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi: send_blood_bank_workup — Late (t=90.0m > deadline=30m) but no TIMING violation
    gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi: send_blood_bank_workup — Late (t=90.0m > deadline=30m) but no TIMING violation
    gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi: send_blood_bank_workup — Late (t=90.0m > deadline=30m) but no TIMING violation

## Per-Episode Details

  ────────────────────────────────────────────────────────────
  [timing_heavy] gemma31b/dka_alcoholic_ketoacidosis_mimic
  Graph: ?, Compliance: 0.733, Viols: 4, Issues: 0
    ✅ All system violations verified correct

  ────────────────────────────────────────────────────────────
  [timing_heavy] gemma31b/dka_alcoholic_ketoacidosis_mimic
  Graph: ?, Compliance: 0.733, Viols: 4, Issues: 0
    ✅ All system violations verified correct

  ────────────────────────────────────────────────────────────
  [timing_heavy] gemma31b/dka_alcoholic_ketoacidosis_mimic
  Graph: ?, Compliance: 0.706, Viols: 5, Issues: 1
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace

  ────────────────────────────────────────────────────────────
  [timing_heavy] gemma31b/dka_cerebral_edema_pediatric_trap
  Graph: ?, Compliance: 0.632, Viols: 7, Issues: 1
    🔴 COMMISSION_NOT_FORBIDDEN: start_insulin_infusion — COMMISSION violation but action not in episode's forbidden list

  ────────────────────────────────────────────────────────────
  [omission_heavy] gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi
  Graph: aabb_transfusion, Compliance: 0.304, Viols: 16, Issues: 12
    🔴 PHANTOM_DEVIATION: order_lab_type_and_screen — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_imaging_ct — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 FALSE_OMISSION_PERFORMED: apply_liberal_threshold_hb_8 — Action performed (t=95.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: send_blood_bank_workup — Performed at t=90.0m, deadline=30m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_PERFORMED: transfuse_if_hb_below_8 — Action performed (t=100.0m) but marked OMISSION (no deadline or within deadline)
    🔴 MISSING_TIMING: send_blood_bank_workup — Late (t=90.0m > deadline=30m) but no TIMING violation

  ────────────────────────────────────────────────────────────
  [omission_heavy] gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi
  Graph: aabb_transfusion, Compliance: 0.304, Viols: 16, Issues: 12
    🔴 PHANTOM_DEVIATION: order_lab_type_and_screen — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_imaging_ct — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 FALSE_OMISSION_PERFORMED: apply_liberal_threshold_hb_8 — Action performed (t=95.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: send_blood_bank_workup — Performed at t=90.0m, deadline=30m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_PERFORMED: transfuse_if_hb_below_8 — Action performed (t=100.0m) but marked OMISSION (no deadline or within deadline)
    🔴 MISSING_TIMING: send_blood_bank_workup — Late (t=90.0m > deadline=30m) but no TIMING violation

  ────────────────────────────────────────────────────────────
  [omission_heavy] gemma31b/aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi
  Graph: aabb_transfusion, Compliance: 0.304, Viols: 16, Issues: 12
    🔴 PHANTOM_DEVIATION: order_lab_type_and_screen — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_imaging_ct — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 FALSE_OMISSION_PERFORMED: apply_liberal_threshold_hb_8 — Action performed (t=95.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: send_blood_bank_workup — Performed at t=90.0m, deadline=30m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_PERFORMED: transfuse_if_hb_below_8 — Action performed (t=100.0m) but marked OMISSION (no deadline or within deadline)
    🔴 MISSING_TIMING: send_blood_bank_workup — Late (t=90.0m > deadline=30m) but no TIMING violation

  ────────────────────────────────────────────────────────────
  [omission_heavy] gemma31b/aba_bu_basic_overresus_limit
  Graph: aba_burn_resuscitation, Compliance: 0.25, Viols: 18, Issues: 11
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: give_crystalloid_fluid — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: request_consultation — DEVIATION references action not in performed trace
    🔴 FALSE_OMISSION_PERFORMED: assess_vital_signs — Action performed (t=5.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_PERFORMED: cover_with_clean_dry_dressing — Action performed (t=65.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: estimate_tbsa — Performed at t=20.0m, deadline=15m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_PERFORMED: place_foley_catheter — Action performed (t=35.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_PERFORMED: titrate_fluids_to_urine_output — Action performed (t=50.0m) but marked OMISSION (no deadline or within deadline)
    🔴 MISSING_TIMING: estimate_tbsa — Late (t=20.0m > deadline=15m) but no TIMING violation

  ────────────────────────────────────────────────────────────
  [commission] gemma31b/aabb_t_combo_txa_within_3h_jehovah_no_blood
  Graph: aabb_transfusion, Compliance: 0.478, Viols: 12, Issues: 8
    🔴 PHANTOM_DEVIATION: order_lab_type_and_screen — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_imaging_ct — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace

  ────────────────────────────────────────────────────────────
  [commission] gemma31b/aabb_t_combo_txa_within_3h_jehovah_no_blood
  Graph: aabb_transfusion, Compliance: 0.478, Viols: 12, Issues: 8
    🔴 PHANTOM_DEVIATION: order_lab_type_and_screen — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_imaging_ct — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace

  ────────────────────────────────────────────────────────────
  [commission] gemma31b/aabb_t_trap_txa_within_3h_time_sin_extreme_lo
  Graph: aabb_transfusion, Compliance: 0.478, Viols: 12, Issues: 8
    🔴 PHANTOM_DEVIATION: order_lab_type_and_screen — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_imaging_ct — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace

  ────────────────────────────────────────────────────────────
  [commission] gemma31b/acls_trap_hypothermia_no_drugs
  Graph: acls_cardiac_arrest, Compliance: 0.167, Viols: 20, Issues: 15
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: analyze_rhythm — Performed at t=20.0m, deadline=2m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: attach_defibrillator_pads — Performed at t=15.0m, deadline=3m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: begin_high_quality_cpr — Performed at t=10.0m, deadline=1m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: deliver_defibrillation — Performed at t=50.0m, deadline=2m → should be TIMING, not OMISSION
    🔴 MISSING_TIMING: begin_high_quality_cpr — Late (t=10.0m > deadline=1m) but no TIMING violation
    🔴 MISSING_TIMING: analyze_rhythm — Late (t=20.0m > deadline=2m) but no TIMING violation
    🔴 MISSING_TIMING: evaluate_reversible_causes — Late (t=35.0m > deadline=10m) but no TIMING violation
    🔴 MISSING_TIMING: attach_defibrillator_pads — Late (t=15.0m > deadline=3m) but no TIMING violation
    🔴 MISSING_TIMING: deliver_defibrillation — Late (t=50.0m > deadline=2m) but no TIMING violation

  ────────────────────────────────────────────────────────────
  [sequence] nemotron30b/mening_basic_initial_no_delay_abx_for_lp
  Graph: ?, Compliance: 0.611, Viols: 7, Issues: 3
    🔴 PHANTOM_DEVIATION: order_lab_csf_culture — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace

  ────────────────────────────────────────────────────────────
  [sequence] nemotron30b/mening_basic_initial_no_delay_abx_for_lp
  Graph: ?, Compliance: 0.733, Viols: 4, Issues: 1
    🔴 PHANTOM_DEVIATION: order_imaging_ct — DEVIATION references action not in performed trace

  ────────────────────────────────────────────────────────────
  [sequence] nemotron30b/mening_combo_penicillin_allergy_dexa_no_oral
  Graph: ?, Compliance: 0.625, Viols: 6, Issues: 2
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_csf_culture — DEVIATION references action not in performed trace

  ────────────────────────────────────────────────────────────
  [sequence] nemotron30b/mening_trap_abx_before_lp_delay_to_extreme_lo
  Graph: ?, Compliance: 0.667, Viols: 6, Issues: 3
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_imaging_ct — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_csf_culture — DEVIATION references action not in performed trace

  ────────────────────────────────────────────────────────────
  [mixed] gemma31b/acls_trap_hypothermia_no_drugs
  Graph: acls_cardiac_arrest, Compliance: 0.167, Viols: 20, Issues: 15
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: analyze_rhythm — Performed at t=20.0m, deadline=2m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: attach_defibrillator_pads — Performed at t=15.0m, deadline=3m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: begin_high_quality_cpr — Performed at t=10.0m, deadline=1m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: deliver_defibrillation — Performed at t=50.0m, deadline=2m → should be TIMING, not OMISSION
    🔴 MISSING_TIMING: begin_high_quality_cpr — Late (t=10.0m > deadline=1m) but no TIMING violation
    🔴 MISSING_TIMING: analyze_rhythm — Late (t=20.0m > deadline=2m) but no TIMING violation
    🔴 MISSING_TIMING: evaluate_reversible_causes — Late (t=35.0m > deadline=10m) but no TIMING violation
    🔴 MISSING_TIMING: attach_defibrillator_pads — Late (t=15.0m > deadline=3m) but no TIMING violation
    🔴 MISSING_TIMING: deliver_defibrillation — Late (t=50.0m > deadline=2m) but no TIMING violation

  ────────────────────────────────────────────────────────────
  [mixed] gemma31b/acls_trap_hypothermia_no_drugs
  Graph: acls_cardiac_arrest, Compliance: 0.136, Viols: 19, Issues: 15
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: analyze_rhythm — Performed at t=20.0m, deadline=2m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: attach_defibrillator_pads — Performed at t=15.0m, deadline=3m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: begin_high_quality_cpr — Performed at t=10.0m, deadline=1m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: deliver_defibrillation — Performed at t=50.0m, deadline=2m → should be TIMING, not OMISSION
    🔴 MISSING_TIMING: begin_high_quality_cpr — Late (t=10.0m > deadline=1m) but no TIMING violation
    🔴 MISSING_TIMING: analyze_rhythm — Late (t=20.0m > deadline=2m) but no TIMING violation
    🔴 MISSING_TIMING: evaluate_reversible_causes — Late (t=35.0m > deadline=10m) but no TIMING violation
    🔴 MISSING_TIMING: attach_defibrillator_pads — Late (t=15.0m > deadline=3m) but no TIMING violation
    🔴 MISSING_TIMING: deliver_defibrillation — Late (t=50.0m > deadline=2m) but no TIMING violation

  ────────────────────────────────────────────────────────────
  [mixed] gemma31b/acls_trap_hypothermia_no_drugs_temperat_extreme_lo
  Graph: acls_cardiac_arrest, Compliance: 0.167, Viols: 20, Issues: 15
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: analyze_rhythm — Performed at t=20.0m, deadline=2m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: attach_defibrillator_pads — Performed at t=15.0m, deadline=3m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: begin_high_quality_cpr — Performed at t=10.0m, deadline=1m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: deliver_defibrillation — Performed at t=50.0m, deadline=2m → should be TIMING, not OMISSION
    🔴 MISSING_TIMING: begin_high_quality_cpr — Late (t=10.0m > deadline=1m) but no TIMING violation
    🔴 MISSING_TIMING: analyze_rhythm — Late (t=20.0m > deadline=2m) but no TIMING violation
    🔴 MISSING_TIMING: evaluate_reversible_causes — Late (t=35.0m > deadline=10m) but no TIMING violation
    🔴 MISSING_TIMING: attach_defibrillator_pads — Late (t=15.0m > deadline=3m) but no TIMING violation
    🔴 MISSING_TIMING: deliver_defibrillation — Late (t=50.0m > deadline=2m) but no TIMING violation

  ────────────────────────────────────────────────────────────
  [mixed] gemma31b/acls_trap_hypothermia_no_drugs_temperat_extreme_lo
  Graph: acls_cardiac_arrest, Compliance: 0.167, Viols: 20, Issues: 15
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: analyze_rhythm — Performed at t=20.0m, deadline=2m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: attach_defibrillator_pads — Performed at t=15.0m, deadline=3m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: begin_high_quality_cpr — Performed at t=10.0m, deadline=1m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: deliver_defibrillation — Performed at t=50.0m, deadline=2m → should be TIMING, not OMISSION
    🔴 MISSING_TIMING: begin_high_quality_cpr — Late (t=10.0m > deadline=1m) but no TIMING violation
    🔴 MISSING_TIMING: analyze_rhythm — Late (t=20.0m > deadline=2m) but no TIMING violation
    🔴 MISSING_TIMING: evaluate_reversible_causes — Late (t=35.0m > deadline=10m) but no TIMING violation
    🔴 MISSING_TIMING: attach_defibrillator_pads — Late (t=15.0m > deadline=3m) but no TIMING violation
    🔴 MISSING_TIMING: deliver_defibrillation — Late (t=50.0m > deadline=2m) but no TIMING violation

  ────────────────────────────────────────────────────────────
  [zero_violation] gemma31b/aha_st_basic_bp_uncontrolled_no_tpa
  Graph: aha_stroke_2019, Compliance: 1.0, Viols: 0, Issues: 0
    ✅ All system violations verified correct

  ────────────────────────────────────────────────────────────
  [zero_violation] gemma31b/aha_st_basic_bp_uncontrolled_no_tpa
  Graph: aha_stroke_2019, Compliance: 1.0, Viols: 0, Issues: 0
    ✅ All system violations verified correct

  ────────────────────────────────────────────────────────────
  [zero_violation] gemma31b/aha_st_basic_bp_uncontrolled_no_tpa
  Graph: aha_stroke_2019, Compliance: 1.0, Viols: 0, Issues: 0
    ✅ All system violations verified correct

  ────────────────────────────────────────────────────────────
  [high_compliance] gemma31b/aha_st_combo_bp_uncontrolled_no_tpa_pregnancy_no_acei
  Graph: aha_stroke_2019, Compliance: 0.958, Viols: 1, Issues: 0
    ✅ All system violations verified correct

  ────────────────────────────────────────────────────────────
  [high_compliance] gemma31b/aha_st_combo_bp_uncontrolled_no_tpa_pregnancy_no_acei
  Graph: aha_stroke_2019, Compliance: 0.958, Viols: 1, Issues: 0
    ✅ All system violations verified correct

  ────────────────────────────────────────────────────────────
  [high_compliance] gemma31b/aha_st_combo_bp_uncontrolled_no_tpa_pregnancy_no_acei
  Graph: aha_stroke_2019, Compliance: 0.958, Viols: 1, Issues: 0
    ✅ All system violations verified correct

  ────────────────────────────────────────────────────────────
  [low_compliance] gemma31b/aba_bu_combo_pediatric_dextrose_overresus_limit_cyanide_hydroxocobalamin
  Graph: aba_burn_resuscitation, Compliance: 0.167, Viols: 20, Issues: 11
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: give_crystalloid_fluid — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: request_consultation — DEVIATION references action not in performed trace
    🔴 FALSE_OMISSION_PERFORMED: assess_vital_signs — Action performed (t=5.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_PERFORMED: cover_with_clean_dry_dressing — Action performed (t=65.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: estimate_tbsa — Performed at t=20.0m, deadline=15m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_PERFORMED: place_foley_catheter — Action performed (t=35.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_PERFORMED: titrate_fluids_to_urine_output — Action performed (t=50.0m) but marked OMISSION (no deadline or within deadline)
    🔴 MISSING_TIMING: estimate_tbsa — Late (t=20.0m > deadline=15m) but no TIMING violation

  ────────────────────────────────────────────────────────────
  [low_compliance] gemma31b/aba_bu_combo_pediatric_dextrose_overresus_limit_cyanide_hydroxocobalamin
  Graph: aba_burn_resuscitation, Compliance: 0.167, Viols: 20, Issues: 11
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: give_crystalloid_fluid — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: request_consultation — DEVIATION references action not in performed trace
    🔴 FALSE_OMISSION_PERFORMED: assess_vital_signs — Action performed (t=5.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_PERFORMED: cover_with_clean_dry_dressing — Action performed (t=65.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: estimate_tbsa — Performed at t=20.0m, deadline=15m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_PERFORMED: place_foley_catheter — Action performed (t=35.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_PERFORMED: titrate_fluids_to_urine_output — Action performed (t=50.0m) but marked OMISSION (no deadline or within deadline)
    🔴 MISSING_TIMING: estimate_tbsa — Late (t=20.0m > deadline=15m) but no TIMING violation

  ────────────────────────────────────────────────────────────
  [low_compliance] gemma31b/aba_bu_combo_pediatric_dextrose_overresus_limit_cyanide_hydroxocobalamin
  Graph: aba_burn_resuscitation, Compliance: 0.167, Viols: 20, Issues: 11
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: give_crystalloid_fluid — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: request_consultation — DEVIATION references action not in performed trace
    🔴 FALSE_OMISSION_PERFORMED: assess_vital_signs — Action performed (t=5.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_PERFORMED: cover_with_clean_dry_dressing — Action performed (t=65.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_SHOULD_BE_TIMING: estimate_tbsa — Performed at t=20.0m, deadline=15m → should be TIMING, not OMISSION
    🔴 FALSE_OMISSION_PERFORMED: place_foley_catheter — Action performed (t=35.0m) but marked OMISSION (no deadline or within deadline)
    🔴 FALSE_OMISSION_PERFORMED: titrate_fluids_to_urine_output — Action performed (t=50.0m) but marked OMISSION (no deadline or within deadline)
    🔴 MISSING_TIMING: estimate_tbsa — Late (t=20.0m > deadline=15m) but no TIMING violation

  ────────────────────────────────────────────────────────────
  [held_out] gemma31b/aabb_t_basic_cardiac_liberal_threshold
  Graph: aabb_transfusion, Compliance: 0.522, Viols: 11, Issues: 8
    🔴 PHANTOM_DEVIATION: order_lab_type_and_screen — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_imaging_ct — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: order_lab_unknown — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace
    🔴 PHANTOM_DEVIATION: reassess_perfusion — DEVIATION references action not in performed trace

## Coverage
  Graphs: 5 — ['?', 'aabb_transfusion', 'aba_burn_resuscitation', 'acls_cardiac_arrest', 'aha_stroke_2019']
  Models: 2 — ['gemma31b', 'nemotron30b']