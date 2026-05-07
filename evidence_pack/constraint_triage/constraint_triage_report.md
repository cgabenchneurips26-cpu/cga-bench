================================================================================
PRE-CLINICIAN CONSTRAINT TRIAGE 보고서
================================================================================

## 1. Triage Summary (512 constraints)

  BUG_NOT_IN_EFFECTS            :   118 ( 23.0%) 🔴
  BUG_NO_EFFECT_NO_DATA         :     0 (  0.0%) 🔴
  STRUCTURAL_ZERO_PERFORM       :     6 (  1.2%) 🟡
  BORDERLINE_LOW                :    15 (  2.9%) 🟡
  BORDERLINE_MED                :    36 (  7.0%) 🟡
  VALID_MODERATE                :    73 ( 14.3%)
  VALID_HIGH                    :    36 (  7.0%)
  EASY_ALL_PERFORM              :   228 ( 44.5%) ✅
  NO_DATA                       :     0 (  0.0%)

  ⚠️ 문제 있는 constraints: 139/512 (27.1%)
  ★ 추정 Corrected Precision: 0.658
    (기존 enginePrecision=0.217 대비)
    → Precision이 과소평가되었을 가능성: 실제로는 65.8%

## 2. Per-Graph Breakdown
  Graph                                    Total   BUG  ZERO  BORD VALID  EASY
  ---------------------------------------------------------------------------------------------------------
  aabb_transfusion                            15     0     0     4     6     5
  aba_burn_resuscitation                      24     5     0     0     6    13
  acls_cardiac_arrest                         16     1     0     2     3    10
  acog_obstetric_hemorrhage                   15     0     0     0     9     6
  ada_dka_management                          30     4     1     0    10    15
  aha_chest_pain_evaluation                   23     1     0     3    13     6
  aha_heart_failure_2022                      68    31     1    13     9    14
  aha_stroke_2019                             91    54     1     9    24     3
  anaphylaxis_management                      13     1     0     0     2    10
  apa_agitation_management                    16     2     0     5     3     6
  atrial_fibrillation                          9     0     0     1     0     8
  cap_pneumonia                                8     0     0     0     0     8
  copd_exacerbation                            8     0     0     0     0     8
  gi_bleeding                                 10     0     0     0     0    10
  gina_asthma_exacerbation                    17     1     1     2     5     8
  hypertensive_emergency                       8     0     0     0     0     8
  idsa_meningitis                             14     1     0     0     2    11
  kdigo_aki_full                              44    10     0    12    10    12
  kdigo_contrast_aki                          21     4     1     0     6    10
  pals_pediatric_emergency                    15     0     0     0     0    15
  pulmonary_embolism                           8     0     0     0     1     7
  ssc_sepsis_hour1_bundle                     12     0     0     0     0    12
  status_epilepticus                          13     1     1     0     0    11
  toxicology_management                       13     2     0     0     0    11
  universal_clinical_safety                    1     0     0     0     0     1

## 3. OMISSION 영향 추정

  만약 BUG + STRUCTURAL_ZERO constraints를 모두 soft로 변경하면:
  - 139 constraints가 hard → soft 전환
  - 이것이 생성하는 OMISSION violations 전부 제거
  - OMISSION 비율이 현재 29.3x에서 대폭 감소 예상
  
  논문 framing 전략:
  1. BUG는 수정 후 재실행 (action_effects에 추가 or constraint 삭제)
  2. STRUCTURAL_ZERO는 "clinician-validated subset"으로 한정
  3. 논문에서 "full constraint set"과 "clinician-validated subset" 둘 다 보고
     → 리뷰어가 precision 공격해도 subset 결과로 방어 가능


## 4. 즉시 실행 가능한 조치
============================================================

  🔴 Phase 1: BUG 수정 (clinician 불필요, 즉시)
  - auto_fix_suggestions.md 참조
  - action_effects.yaml에 누락 action 추가 OR
  - graph YAML에서 해당 node의 expected_actions에서 제거/soft 전환
  
  🟡 Phase 2: STRUCTURAL_ZERO 검토 (코드 레벨)
  - 이 action들의 precondition을 action_effects.yaml에서 확인
  - precondition이 시나리오에서 충족 불가능하면 → constraint 조건 수정
  - precondition이 가능한데 모델이 모두 실패 → clinician 확인 대기
  
  🟢 Phase 3: Clinician 리뷰 (최소 범위)
  - clinician_minimal_review.md 발송
  - 전체 512 constraints가 아닌 139개만 검토 요청
  - 검토 결과로 "clinician-endorsed precision" 계산 가능
  
  📊 Phase 4: 논문 반영
  - Table~constraint_type_precision에 3가지 precision 보고:
    a) Raw precision (현재 0.217)
    b) Corrected precision (BUG 제거 후)
    c) Clinician-endorsed precision (리뷰 후)
