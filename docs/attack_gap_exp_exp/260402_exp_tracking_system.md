# CGA-Bench 논문 수치/실험 추적 관리 시스템 구축

## 지시사항

main_final_v5.tex를 파싱해서, 논문에 등장하는 **모든 수치, 실험 결과, 빈칸({})**을
하나의 관리 파일(tracking_sheet.md)로 추출해줘.

그리고 아직 수행하지 않은 실험/분석도 함께 정리해서,
"이 파일 하나만 보면 논문의 모든 숫자 상태를 알 수 있는" 마스터 시트를 만들어줘.

---

## Step 1: main.tex에서 모든 수치 추출

main_final_v5.tex (또는 현재 최신 main.tex)를 읽고,
아래 형식으로 **모든 정량적 claim**을 추출해줘.

추출 대상:
- 숫자가 포함된 모든 문장 (%, 개수, 비율, p-value, κ, r 등)
- {} 또는 {CI} 등 빈칸으로 남은 모든 위치
- table의 모든 셀
- appendix의 수치도 포함

각 항목에 대해 아래 컬럼을 채워줘:

```
| ID | 위치(섹션/표/줄) | 수치 또는 {} | 상태 | 출처 | 검증 여부 | 비고 |
```

상태 분류:
- ✅ CONFIRMED: 검증 완료, 확정값
- 🔧 NEEDS_FIX: 값은 있지만 수정 필요
- ⬜ EMPTY: {} 빈칸, 실험/분석 필요
- ⏳ PENDING: 실험 진행 중
- 📎 STRUCTURAL: 정의상 도출되는 값 (예: DxEM 100%)

출처 분류:
- V0~V7: 검증 실험 결과
- P0~P8: gap 실험 결과
- EXP11: 기존 실험 파이프라인
- YAML: CPG YAML 직접 카운트
- CODE: 코드에서 확인
- CALC: 다른 확정값에서 계산
- NONE: 출처 없음 (위험)

---

## Step 2: 미수행 실험/분석 목록

main.tex의 빈칸과 reviewer가 요구하는 실험을 대조해서,
아래 형식의 실험 관리 표를 만들어줘:

```
| 실험ID | 실험명 | 목적 | 채워지는 빈칸(ID) | 소요시간 | 우선순위 | 상태 | 선행조건 |
```

우선순위:
- 🔴 CRITICAL: 이것 없으면 reject
- 🟠 IMPORTANT: 있으면 크게 강화
- 🟡 NICE: 있으면 좋음
- ⚪ OPTIONAL: 시간 남으면

상태:
- ✅ DONE
- ⏳ IN_PROGRESS
- ⬜ NOT_STARTED
- ❌ BLOCKED (선행조건 미충족)

---

## Step 3: 교차 참조 매트릭스

각 실험이 논문의 어느 table/figure/문장을 채우는지 매핑:

```
| 실험ID | Table 1 | Table 2 | Table 3 | ... | Abstract | Intro | Conclusion |
```

셀 값: 해당 실험이 채우는 셀 ID 목록

---

## Step 4: 출력

모든 결과를 하나의 파일로 저장:

```
tracking/tracking_sheet.md
```

파일 구조:
1. Executive Summary (빈칸 수, 확정 수, 위험도)
2. Section A: 수치 추적표 (Step 1)
3. Section B: 실험 관리표 (Step 2)  
4. Section C: 교차 참조 (Step 3)
5. Section D: 즉시 조치 필요 항목 (빈칸 중 CRITICAL인 것)

---

## 입력 파일

main.tex 경로: [현재 main.tex 경로]

참고할 검증 결과 파일들:
- V0: [v0_constraint_audit 결과 경로]
- V1: [v1_dxem_verification 결과 경로]
- V2: [v2_tautology_check 결과 경로]
- V3: [v3_upstrong_reconciliation 결과 경로]
- V4: [v4_forbidden_reconciliation 결과 경로]
- V5: [v5_scorer_fidelity 결과 경로]
- V6: [v6_llm_encoder 결과 경로]
- V7: [v7_normalizer_impact 결과 경로]
- P0~P8: [gap experiments 결과 디렉토리]

---

## 주의사항

1. 논문에 등장하는 숫자는 **하나도 빠뜨리지 마**. "6 domains"도, "14 CPG graphs"도,
   "5-minute increments"도 전부 추적 대상이야.

2. 같은 숫자가 여러 곳에 등장하면 (예: 34.6%가 abstract, intro, Table 2, conclusion에
   모두 나옴), **모든 등장 위치를 기록**해. 나중에 수정할 때 하나라도 빠뜨리면 안 되니까.

3. {} 빈칸은 특히 중요해. 각 빈칸에 대해 "이걸 채우려면 어떤 실험/분석이 필요한가"를
   반드시 연결해줘.

4. table의 경우 각 셀을 개별 항목으로 추적해. 
   예: "Table 2, 120B행 UP_crit열 = 13.6%" 이런 식으로.

5. 검증 결과 파일이 있으면 해당 수치 옆에 검증 상태를 표시해.
   검증 파일이 없는 수치는 ⚠ 표시.