======================================================================
CGA-Bench 시스템 전수 검증 보고서
======================================================================

────────────────────────────────────────────────────────────
✅ S1: Constraint Completeness: PASS
  issue: None
  missing_types: []
  type_counts: {'DEVIATION': 39671, 'OMISSION': 49643, 'COMMISSION': 1257, 'TIMING': 7032, 'SEQUENCE': 244}
  Examples:
    DEVIATION: [{'file': 'c_cardiac_liberal_threshold_gemma31b_r0_20260404_163956.json', 'action': None, 'raw_type': 'DEVIATION'}, {'file': 'c_cardiac_liberal_threshold_gemma31b_r0_20260404_163956.json', 'action': None, 'raw_type': 'DEVIATION'}, {'file': 'c_cardiac_liberal_threshold_gemma31b_r0_20260404_163956.json', 'action': None, 'raw_type': 'DEVIATION'}]
    OMISSION: [{'file': 'ah_no_blood_anaphylaxis_epi_gemma31b_r0_20260404_164600.json', 'action': 'apply_liberal_threshold_hb_8', 'raw_type': 'OMISSION'}, {'file': 'ah_no_blood_anaphylaxis_epi_gemma31b_r0_20260404_164600.json', 'action': 'give_epinephrine_im', 'raw_type': 'OMISSION'}, {'file': 'ah_no_blood_anaphylaxis_epi_gemma31b_r0_20260404_164600.json', 'action': 'send_blood_bank_workup', 'raw_type': 'OMISSION'}]
    COMMISSION: [{'file': '_within_3h_jehovah_no_blood_gemma31b_r1_20260404_165004.json', 'action': None, 'raw_type': 'COMMISSION'}, {'file': '_within_3h_jehovah_no_blood_gemma31b_r2_20260404_165107.json', 'action': None, 'raw_type': 'COMMISSION'}, {'file': 'thin_3h_time_sin_extreme_lo_gemma31b_r2_20260404_171559.json', 'action': None, 'raw_type': 'COMMISSION'}]

────────────────────────────────────────────────────────────
🟡 S2: Violation-Action Correspondence: WARN
  bad_rate: 0.004674082394289648
  commission_in_performed: 304
  commission_not_in_performed: 63
  omission_in_expected: 27166
  omission_not_in_expected: 66

────────────────────────────────────────────────────────────
🟡 S5: State Isolation: WARN
  high_variance_count: 171
  high_variance_rate: 5.6
  n_multi_run_groups: 3058
  High-variance runs:
    nemotron30b/caki_trap_ckd_prep_specific_egfr_extreme_lo: score_range=0.913, scores=[0.9565217391304348, 0.17391304347826086, 0.9565217391304348, 0.17391304347826086, 1.0, 0.08695652173913049]
    nemotron30b/caki_trap_high_no_repeat_contrast_egfr_extreme_lo: score_range=0.87, scores=[0.9565217391304348, 0.13043478260869568, 0.9130434782608696, 0.17391304347826086, 1.0, 0.21739130434782605]
    nemotron30b/caki_trap_high_risk_prehydrate_egfr_extreme_hi: score_range=0.87, scores=[1.0, 0.13043478260869568, 0.9565217391304348, 0.21739130434782605, 1.0, 0.17391304347826086]

────────────────────────────────────────────────────────────
✅ S8: Scoring Sanity: PASS
  no_violations_field: 0
  out_of_range: 0
  perfect_with_violations: 0
  zero_without_violations: 0

────────────────────────────────────────────────────────────
✅ S9: Empty Actions: PASS
  empty_count: 7
  empty_rate: 0.06
  issue: 7 episodes with 0 actions (0.1%)
  model_empty: {'gemma31b': 1, 'nemotron30b': 1, 'oss120b': 1, 'qwen27b': 1, 'qwen35b': 1, 'qwen397b': 1, 'qwen4b': 1}
  very_few_count: 69
  ⚠️ 7 episodes with 0 actions (0.1%)
  Examples:
    {'type': 'EMPTY', 'model': 'gemma31b', 'scenario': '', 'file': 'results/full_706_v5/gemma31b/checkpoint.json'}
    {'type': 'EMPTY', 'model': 'nemotron30b', 'scenario': '', 'file': 'results/full_706_v5/nemotron30b/checkpoint.json'}
    {'type': 'EMPTY', 'model': 'oss120b', 'scenario': '', 'file': 'results/full_706_v5/oss120b/checkpoint.json'}

────────────────────────────────────────────────────────────
✅ S10: Violation Type per Graph: PASS
  n_issues: 0

────────────────────────────────────────────────────────────
📊 Model Sanity Overview:
  Model                     N   Acts  0-act%   Comp  Viols
  -------------------------------------------------------
  gemma31b               1610   18.7    0.1%  0.547    9.4
  nemotron30b            2103   12.9    0.0%  0.496    8.6
  oss120b                1107   24.4    0.1%  0.514   12.0
  qwen27b                2122   21.6    0.0%  0.701    6.7
  qwen35b                2105   22.8    0.0%  0.634    8.6
  qwen397b                698   21.6    0.1%  0.518   11.1
  qwen4b                 1205   15.0    0.1%  0.473    9.3

============================================================
SUMMARY: 4 PASS, 2 WARN, 0 FAIL
🟡 2 warnings — 검토 필요하지만 blocking은 아님
============================================================