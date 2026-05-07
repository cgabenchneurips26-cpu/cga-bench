# Evidence Level 일괄 점검 + 전체 재채점

## 시작 전

```
git add -A && git commit -m "pre-evidence-fix checkpoint"
```

이 commit을 기억해둬. 문제 생기면 여기로 돌아온다.

---

## Step 1: 14개 YAML 전수 점검 + 수정 (2h)

```
14개 CPG YAML graph의 모든 node에서 recommendation_class와 
evidence_level field를 점검하고, 누락된 것을 전부 올바른 값으로 채워줘.

각 graph에 대해:

1. cpg_model/graphs/{graph_name}.yaml을 열어서
   모든 node의 recommendation_class, evidence_level 확인

2. 누락된 field가 있으면 해당 CPG source 문서 기준으로 채워:

   === Source별 evidence grading 체계 ===
   
   SSC 2021 (ssc_sepsis_hour1):
   - Strong recommendation = recommendation_class: "I"
   - Weak recommendation = recommendation_class: "IIa"
   - Evidence: High(A), Moderate(B), Low(C)
   
   AHA 2021/2022/2019 (aha_chest_pain, aha_stroke, aha_heart_failure):
   - Class I = recommendation_class: "I"
   - Class IIa = recommendation_class: "IIa"
   - Class IIb = recommendation_class: "IIb"  
   - Class III = recommendation_class: "III"
   - Level A/B/C
   
   KDIGO (kdigo_aki_full, kdigo_contrast_aki):
   - Level 1 = Strong = recommendation_class: "I"
   - Level 2 = Weak = recommendation_class: "IIa"
   - Grade A/B/C/D
   
   ADA (ada_dka_management):
   - ADA는 COR/LOE 대신 evidence grade 사용
   - Consensus-based = recommendation_class: "IIa" 또는 적절한 값

   기타 (AF, COPD, HTN, PE, GIB, universal_clinical_safety):
   - 해당 CPG source의 recommendation strength에 따라

3. 채울 때 규칙:
   - CPG source에서 명확한 evidence가 있으면 → 그 값
   - CPG source가 불명확하면 → "IIa" (moderate, conservative)
   - Decision/classification node (action이 없는 순수 분기 node) → 
     recommendation_class 불필요, 있으면 유지 없으면 추가 안 함
   - universal_clinical_safety → 일반 안전 규칙이므로 "I" (Class I)

4. 수정 로그 작성:
   | Graph | Node | Field | Old value | New value | Source |
   모든 변경을 기록.

5. 수정 후 YAML schema validation 실행:
   scripts/ci/validate_cpg_schema.py (있으면)
   또는 YAML 파싱 + 필수 field 확인

출력:
- 수정된 14개 YAML (직접 수정)
- system_review/evidence_fix_log.md (변경 로그)
```

---

## Step 2: 전체 재채점 (1h)

```
YAML 수정 후, Exp11을 재실행해서 새 severity classification 산출.

1. Exp11 재실행:
   scripts/experiments/gap_experiments.py의 exp11 method
   → event_level_hardviol_v3.json 출력 (v2와 구분)

2. 새 수치 계산:
   - UP_strong (new): ?/78
   - UP_crit (new): ?/78
   - UP_any (new): ?/78
   - 모델별 breakdown
   - domain별 breakdown

3. 기존 수치와 비교:
   | Metric | Before | After | Delta |
   | UP_strong | 27/78 (34.6%) | ?/78 (?%) | |
   | UP_crit | 13/78 (16.7%) | ?/78 (?%) | |
   | UP_any | 48/78 (61.5%) | ?/78 (?%) | |

출력:
- evidence_pack/additional/event_level/event_level_hardviol_v3.json
- system_review/rescore_comparison.md
```

---

## Step 3: 전체 downstream 재계산 (2h)

```
새 Exp11 결과 (v3)로 모든 논문 수치 재계산:

1. Scenario-clustered bootstrap CI (UP_strong, UP_crit, UP_any)
2. Verdict matrix (모든 evaluator × 3 tier)
3. Stratification (Core/Expansion)
4. Instrumentation ablation (B-1)
5. Domain spread (A-4)
6. Domain-removal robustness (B-3)
7. Clock scale sweep는 별도 method이므로 영향 없음 (확인만)
8. Per-model table (Table 9)
9. C1 ablation table (Table 10)

각각의 결과를 이전 값과 비교해서 delta 보고.

출력:
- 모든 결과를 evidence_pack/analysis/post_evidence_fix/ 에 저장
- system_review/full_rescore_results.md
```

---

## Step 4: System Review 추가 점검 (병렬 가능, 1h)

```
system review critical review에서 나온 추가 이슈도 같이 해결:

1. VIOLATION_PRIORITY 영향 확인:
   - COMMISSION이 SEQUENCE/TIMING을 mask하는 episode가 몇 개?
   - mask된 violation이 UP_strong에 영향을 주는가?
   
2. scenario_expected_actions vs CPG engine M_G:
   - C2 denominator가 어디서 오는지 확인
   - 두 source의 차이가 있는 episode/scenario

3. patient_specific_constraints:
   - allergy 정보가 episode에 있는 scenario 목록
   - dynamic forbidden이 fire하는 경우가 있는지

4. SafeExpressionEvaluator:
   - 14 YAML의 precondition field 전수 검사
   - malformed expression이 있는지

출력: system_review/additional_checks.md
```

---

## Step 5: Commit + 검증 (30min)

```
1. 전체 테스트:
   PYTHONPATH=. pytest tests/ -v
   실패하는 테스트 → golden snapshot 업데이트 필요할 수 있음

2. 새 수치 vs tracking_sheet 교차 확인

3. commit:
   git add -A && git commit -m "fix: evidence level metadata for all 14 CPG graphs + full rescore"

4. 새 tracking_sheet.md 생성:
   기존 tracking_sheet의 모든 CONFIRMED 항목을 
   새 수치로 업데이트
```