================================================================================
OMISSION ROOT CAUSE ANALYSIS v2
전제: mandatory actions는 모두 action_effects에 존재함
================================================================================

## H1: Engine Over-Specification 검증
  Manual scenarios: 1507 episodes
    OMISSION rate: 0.272
    Omissions/episode: 2.4
  Auto scenarios: 7928 episodes
    OMISSION rate: 0.331
    Omissions/episode: 5.1
  Auto/Manual OMISSION rate ratio: 1.22x
  🟡 Auto가 약간 높음 → 부분적 over-specification

## H2: Action Normalizer Gap 검증
  Total deviations: 33700
  Total omissions: 43680
  Deviation-OMISSION overlaps (sim >= 0.6): 37
  ⚠️ 37개 deviation이 expected action과 유사
     → Normalizer가 이들을 인식했으면 OMISSION이 감소했을 것

  Top misses:
    'order_stat_ct_head' ≈ 'order_stat_ct_head' (sim=1.0) [qwen27b]
    'nephrology_consult' ≈ 'urgent_nephrology_consult' (sim=0.837) [gemma31b]
    'assess_aki_risk_factors' ≈ 'assess_aki_risk' (sim=0.789) [nemotron30b]
    'order_lab_blood_culture' ≈ 'order_lab_blood_gas' (sim=0.762) [nemotron30b]
    'start_iv_fluid_normal_saline' ≈ 'start_iv_fluid_ns' (sim=0.756) [nemotron30b]
    'order_imaging_electrocardiogram' ≈ 'order_imaging_ct_angiography' (sim=0.746) [qwen27b]
    'order_lab_procalcitonin' ≈ 'order_lab_creatinine' (sim=0.744) [gemma31b]
    'determine_last_known_well' ≈ 'obtain_last_known_well_time' (sim=0.731) [qwen35b]
    'order_lab_urinalysis' ≈ 'order_lab_creatinine' (sim=0.7) [gemma31b]
    'calculate_nihss_score' ≈ 'calculate_chadsvasc' (sim=0.7) [qwen35b]
    'order_imaging_electrocardiogram' ≈ 'order_imaging_ct_pulmonary_angiography' (sim=0.696) [qwen35b]
    'give_alteplase_if_eligible' ≈ 'give_alteplase_0.9mg_kg' (sim=0.694) [oss120b]
    'order_lab_abg' ≈ 'order_lab_potassium' (sim=0.688) [gemma31b]
    'disposition' ≈ 'determine_disposition' (sim=0.688) [qwen35b]
    'order_lab_unknown' ≈ 'order_lab_troponin' (sim=0.686) [qwen35b]

## H3: Universal vs Model-Specific OMISSION
  Universal fail (모든 모델 실패): 2627 (29.0%)
  Partial fail (일부만 실패):     2161
  Universal pass (모든 모델 성공): 4272
  🟡 Universal fail이 29%
     → 일부 constraint가 문제이나 대부분은 모델 능력 차이

  Top universal-fail actions (모든 모델이 실패하는 action):
    optimize_volume_status                            :   65 scenarios
    monitor_creatinine_daily                          :   64 scenarios
    monitor_acid_base                                 :   62 scenarios
    perform_endotracheal_intubation                   :   62 scenarios
    monitor_potassium                                 :   61 scenarios
    monitor_creatinine_q12h                           :   61 scenarios
    provide_discharge_instructions                    :   57 scenarios
    reassess_after_treatment                          :   46 scenarios
    optimize_hemodynamics                             :   45 scenarios
    give_epinephrine_im                               :   44 scenarios
    resume_cpr_immediately                            :   44 scenarios
    evaluate_alternative_diagnoses                    :   44 scenarios
    order_echocardiogram                              :   41 scenarios
    admit_to_icu                                      :   39 scenarios
    standard_contrast_administration                  :   37 scenarios

## Expected Action 분포 분석
  Expected per episode: mean=14.2, median=14, max=31
  Performed per episode: mean=19.3, median=22
  Gap (expected - performed): -5.1
  Coverage rate: mean=62.3%, median=62.5%

## Top Omitted Actions (상위 20)
  ✅ obtain_12_lead_ecg                           :  1310  [acls, aha_ch, aabb_t]
  ✅ attach_defibrillator_pads                    :   962  [acls, aabb_t, aba_bu]
  ✅ begin_high_quality_cpr                       :   962  [acls, aabb_t, aba_bu]
  ✅ optimize_hemodynamics                        :   939  [acls, aki, aabb_t]
  ✅ analyze_rhythm                               :   924  [acls, aabb_t, aba_bu]
  ✅ deliver_defibrillation                       :   924  [acls, aabb_t, aba_bu]
  ✅ resume_cpr_immediately                       :   924  [acls, aabb_t, aba_bu]
  ✅ evaluate_alternative_diagnoses               :   924  [aha_he, aha_heart, aabb_t]
  ✅ order_echocardiogram                         :   896  [aha_he, aha_heart, aabb_t]
  ✅ admit_to_icu                                 :   870  [acls, asthma, aha_st]
  ✅ monitor_creatinine_daily                     :   825  [aki, aabb_t, aba_bu]
  ✅ monitor_acid_base                            :   810  [aki, aabb_t, aba_bu]
  ✅ initiate_targeted_temperature_management     :   804  [acls, aabb_t, aba_bu]
  ✅ monitor_creatinine_q12h                      :   795  [aki, aabb_t, aba_bu]
  ✅ monitor_potassium                            :   795  [aki, aabb_t, aba_bu]
  ✅ avoid_contrast                               :   617  [aki, aabb_t, aba_bu]
  ✅ measure_oxygen_saturation                    :   578  [asthma, aabb_t, aba_bu]
  ✅ measure_peak_expiratory_flow                 :   578  [asthma, aabb_t, aba_bu]
  ✅ consult_nephrology                           :   560  [aki, aabb_t, aba_bu]
  ✅ provide_discharge_instructions               :   532  [aha_ch, caki, aabb_t]

## OMISSION Graph 집중도
  aki                                     :  8650 ( 19.8%, cumul  19.8%)
  acls                                    :  8509 ( 19.5%, cumul  39.3%)
  aha_ch                                  :  5725 ( 13.1%, cumul  52.4%)
  asthma                                  :  4997 ( 11.4%, cumul  63.8%)
  aha_he                                  :  3918 (  9.0%, cumul  72.8%)
  aba_bu                                  :  3512 (  8.0%, cumul  80.8%)
  caki                                    :  1539 (  3.5%, cumul  84.4%)
  anaph                                   :  1290 (  3.0%, cumul  87.3%)
  aha_stroke                              :  1177 (  2.7%, cumul  90.0%)
  af                                      :  1127 (  2.6%, cumul  92.6%)

======================================================================
## 최종 진단
======================================================================
  ★ 주요 원인: 모델 능력 차이 (constraint는 적절)

## 권장 조치
  
  H1 확인 시:
    → Engine의 conditional rule 중 over-specification 의심 항목 식별
    → Clinician에게 "이 action이 이 환자에서 mandatory인가?" 확인
    → Invalid → soft 전환
  
  H2 확인 시:
    → top_misses의 deviation-expected 쌍을 normalizer에 alias로 추가
    → cpg_model/action_normalizer.py에 매핑 규칙 추가
  
  H3 확인 시 (universal fail):
    → Top universal-fail actions의 precondition 체인 검토
    → action_effects.yaml에서 해당 action의 precondition이 충족 가능한지 확인
  
  어떤 경우든:
    → 논문 E7에서 OMISSION breakdown 보고 (engine over-spec vs model gap)
    → Clinician validation에서 constraint validity 확인
