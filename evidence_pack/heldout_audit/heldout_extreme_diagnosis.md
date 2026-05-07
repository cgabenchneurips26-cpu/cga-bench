================================================================================
HELD-OUT 극단 도메인 진단 보고서
================================================================================

## 1. 전 도메인 Constraint Density 비교
Graph ID                                      Nodes   Exp  Forb    DL   Seq  Cond  Total  Density
------------------------------------------------------------------------------------------------------------------------
aabb_transfusion                                  4     0     8     8     0     0     16      4.0 ★
aba_burn_resuscitation                            6     0     8    15     3     0     26      4.3 ★
acls_cardiac_arrest                               6     0    12    15     2     0     29      4.8
acog_obstetric_hemorrhage                         4     0     2    10     0     0     12      3.0 ★
ada_dka_management                                8     0    19    19     0     0     38      4.8
aha_chest_pain_evaluation                        11     0    13    16     0     0     29      2.6
aha_heart_failure_2022                           24     0     9     7     0     0     16      0.7
aha_stroke_2019                                  25     0    15     6     0     0     21      0.8
anaphylaxis_management                            5     0    19     9     2     0     30      6.0
apa_agitation_management                          4     0     5     9     0     0     14      3.5 ★
atrial_fibrillation                               3     0     1     2     0     0      3      1.0
cap_pneumonia                                     3     0     1     3     0     0      4      1.3
copd_exacerbation                                 2     0     2     2     0     0      4      2.0
gi_bleeding                                       2     0     1     2     0     0      3      1.5
gina_asthma_exacerbation                          5     0    24    14     0     0     38      7.6
hypertensive_emergency                            2     0     2     2     0     0      4      2.0
idsa_meningitis                                   5     0     6    12     1     0     19      3.8
kdigo_aki_full                                   13     0     5     9     0     0     14      1.1
kdigo_contrast_aki                                7     0    10     8     0     0     18      2.6
pals_pediatric_emergency                          4     0     5     9     0     0     14      3.5 ★
pulmonary_embolism                                3     0     2     4     0     0      6      2.0
ssc_sepsis_hour1_bundle                           7     0    10    11     0     0     21      3.0
status_epilepticus                                5     0    19    11     2     0     32      6.4
toxicology_management                             6     0     9    11     0     0     20      3.3
universal_clinical_safety                         3     0     5     1     0     0      6      2.0

  Mean density (all): 3.1
  Median density (all): 3.0
  Held-out densities: aabb_transfusion=4.0, aba_burn_resuscitation=4.3, acog_obstetric_hemorrhage=3.0, apa_agitation_management=3.5, pals_pediatric_emergency=3.5

## 2. 도메인별 Hard Violation Rate (에피소드)
Graph ID                                      Episodes HardViol     Rate  MeanComp  MeanActs
----------------------------------------------------------------------------------------------------

## 4. 극단 대비: aba_burn (98.6%) vs aabb_transfusion (2.8%)
  Metric                             aba_burn   aabb_trans    Ratio
  ----------------------------------------------------------------------
  Nodes                                   6.0          4.0      1.5x
  Expected actions                        0.0          0.0      infx
  Forbidden                               8.0          8.0      1.0x
  Deadlines                              15.0          8.0      1.9x
  Constraint density                      4.3          4.0      1.1x
  Conditional rules                       0.0          0.0      infx

## 5. 권장 조치
============================================================

  🔴 aba_burn/apa_agitation 98-100% hard violation 대응:
  
  1. [즉시] Violation type breakdown 확인
     - OMISSION 지배적이면: expected_actions가 과다 → soft로 전환 검토
     - FORBIDDEN 지배적이면: conditional rule의 condition 검증
     - WITHIN 지배적이면: deadline 완화 검토
  
  2. [즉시] 모든 모델이 실패하는 specific constraint 식별
     → 위의 "Top Violated Actions"에서 확인
     → 이 action들이 clinically mandatory인지 확인 필요
  
  3. [논문] Held-out 결과를 aggregate로만 쓰지 말고 per-domain breakdown 필수
     → Table에 5개 held-out domain 각각의 violation rate 제시
     → "Cross-domain variance는 constraint density와 상관"이라는 framing
  
  4. [논문] aba_burn/apa_agitation이 높은 이유를 limitation이 아닌
     "constraint-dense domain에서 blind spot이 더 심각"으로 framing 가능
     → 이 경우 constraint가 valid해야 함 (clinician 필요)
  
  5. [코드] aabb_transfusion이 2.8%인 이유도 확인
     → constraint가 너무 느슨하면 sensitivity 문제
     → TCC가 거의 모든 episode를 pass하면 "too lenient" 공격 가능
