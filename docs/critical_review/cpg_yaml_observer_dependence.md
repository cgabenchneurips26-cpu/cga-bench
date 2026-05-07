# Critical Review — CPG YAML allowed_actions Observer Dependence

**Date**: 2026-04-25
**Severity**: 중대 (paper-level methodological issue)
**Triggered by**: deepseek r1 7B의 C1 score 0.675 분석 — model weakness가 아닌 CPG YAML 정의 dependency 발견

---

## 1. 발견된 문제

### 1.1 현재 DEVIATION 정의

```python
# assessor_core/violations.py
# 어떤 액션이 current node의 allowed_actions 에 없으면 DEVIATION
violation_type = ViolationType.DEVIATION
```

C1_path_selection score 가 직접 영향:
```python
C1 = (total_actions - DEVIATION_count) / total_actions
```

### 1.2 결정적 결함

**`allowed_actions` 는 CPG YAML 저자가 정함**.

같은 임상 시나리오에서:
- 보수적 저자 (좁은 allowed_set) → 합리적인 추가 탐색도 모두 DEVIATION
- 너그러운 저자 (넓은 allowed_set) → 같은 액션 OK

**즉 C1 score 는 모델 능력보다 CPG YAML 저자의 cognitive style을 더 강하게 반영함**.

### 1.3 구체 사례

| Scenario | Action | allowed_set | 임상 평가 | rubric 평가 |
|---|---|---|---|---|
| `htn_basic_aortic_dissection_bb_first` | `order_stat_ct_head` | ❌ (저자 제외) | 표준 진료 (stroke/ICH r/o) | DEVIATION −1 |
| `htn_basic_aortic_dissection_bb_first` | `give_iv_fluids` | ❌ | 보조요법으로 합리적 | DEVIATION −1 |
| `acls_trap_opioid_naloxone` | `obtain_12_lead_ecg` | ✅ (저자 포함) | 표준 진료 | OK |

같은 액션 (`obtain_12_lead_ecg`) 도 시나리오 X에서는 OK, 시나리오 Y에서는 DEVIATION. 차이는 *모델의 임상 판단* 이 아니라 *YAML 저자의 포함 여부*.

---

## 2. 왜 중대한가

### 2.1 Self-referential benchmarking
우리가 CPG YAML을 만들 때 (수동/LLM 자동화 모두):
1. 저자가 allowed_set을 결정
2. 우리가 그 allowed_set 기준으로 모델 평가
3. 모델이 저자의 선택과 다르면 "wrong"

→ **벤치마크가 *임상 사실* 이 아닌 *YAML 저자 cognitive style* 을 측정**.

### 2.2 Auto-generated CPG YAML 로 더 심각해짐

`scripts/cpg_v2_phase3/generate_expansion_graphs.py` 등 LLM-assisted CPG generation 사용 시:
- 같은 임상 가이드라인이라도 LLM 출력이 매번 다름
- LLM 의 보수적/너그러운 정도에 따라 allowed_set 달라짐
- 같은 모델이 같은 시나리오에서 매번 다른 점수 받을 가능성

### 2.3 NeurIPS reviewer 공격 가능성 (높음)

> "당신의 'protocol adherence' 결과는 protocol 내용보다 protocol을 표현한 YAML 저자의 임의 선택에 더 의존하는 거 아닌가? 같은 시나리오를 다른 저자가 YAML화 하면 결과가 변하는가? Inter-annotator agreement 보여라."

→ Inter-rater κ on allowed_actions 측정 안 하면 reproducibility 의심.

---

## 3. 권장 대응

### 3.1 즉각 (이번 paper)

**§Limitations 추가**:
> "CGA-Bench's DEVIATION classification depends on `allowed_actions` choices in CPG YAML authoring. The same clinical action may be classified differently across CPGs. Reasoning models that explore broader actions are penalized in C1 path-selection regardless of clinical reasonableness. We discuss alternative C1' in Appendix C."

**§Appendix C: Alt-rubric C1'**
- Soft DEVIATION 분류 도입 (action이 *어떤* CPG node 의 allowed_set 에 있으면 soft, 어디에도 없으면 hard)
- C1' = (total - hard_dev - soft_dev × 0.3) / total
- Per-model 비교 (deepseek r1 가 C1' 에서는 다른 모델과 parity 보일 가능성)

### 3.2 v2 (next benchmark version)

**CPG YAML 작성 표준 (CYAS — CPG YAML Authoring Standard)**:

#### Tier 1: 반드시 allowed_set 에 포함
- mandatory_actions (current node)
- mandatory_actions (downstream reachable nodes)
- 표준 임상 평가 액션 (assess_vital_signs, establish_iv_access, etc.)

#### Tier 2: 시나리오 도메인 표준 액션 (canonical clinical action set)
- 도메인별 (chest_pain/sepsis/aki/...) standard-of-care 액션 list 사전 정의
- domain_canonical_actions[domain] 라이브러리에서 자동 import

#### Tier 3: 시나리오 specific 추가
- trap action (의도적 wrong 제시 — 모델이 회피하는지 평가)
- 시나리오 특이 보조요법

#### Tier 4 (forbidden): 명시적 exclusion
- forbidden_actions: contraindications, drug interactions, sequence violations

#### 검증 protocol
- Inter-annotator κ on allowed_set: 2 명 의사가 동일 시나리오 YAML 작성, κ ≥ 0.7 검증
- Tier 1, 2 자동 생성 (LLM 안 씀) — 결정론적
- Tier 3 만 LLM-assisted, 검증 필수

### 3.3 즉각 가능한 임시 조치

**(c) Action_normalizer 보강** — bug fix 카테고리, paper에 영향 없음:
- `give_iv_fluids` → `give_crystalloid_fluid` (이미 있음)
- `order_stat_ct_head` → 시나리오에 따라 동적 mapping 어려움
- `give_oxygen` → `give_supplemental_oxygen` 등 canonical 형태로 통일

이 변경은 *동일 의미의 다른 string* 통일이지 의미 변경이 아님 → pre-registration 영향 0.

---

## 4. 영향 받는 paper 섹션

| Section | 변경 |
|---|---|
| §Methods C1 정의 | 그대로 두되 limitation 명시 |
| §Results 표 | sub-score breakdown (C1-C5) 추가 — deepseek 의 C3-C5 강함 보임 |
| §Discussion | "Reasoning models trade protocol adherence for broader exploration" |
| §Limitations | observer-dependence 명시 + v2 plan 언급 |
| §Appendix C | Alt-rubric C1' 분석, soft DEVIATION 정의 |
| §Future Work | CYAS (CPG YAML Authoring Standard) v2 release |

---

## 5. 결정 사항

- ✅ Phase B continues with current rubric (pre-reg integrity)
- ✅ Action_normalizer 보강만 진행 (bug fix)
- ✅ Paper에 §Limitations + §Appendix C alt-rubric 추가
- ✅ v2 benchmark에서 CYAS 도입 (future work)
- ❌ Mid-study rubric 변경 안 함 (methodology violation)

---

## 6. 추적 정보

- 발견 commit: phase B 진행 중 (2026-04-25 evening)
- 관련 score: `reports/cpg_scores_v2_full_124.json` (allowed_actions 기준 정의)
- 관련 코드: `assessor_core/violations.py` line 478, `assessor_core/harm_scorer.py` line 192
- 관련 데이터: deepseek_r1_7b 200-eps sample → 1526 DEVIATION events / 588 unique action_ids
- 영향 범위: 8 모델 × 706 + 4720 scenarios = paper 전체 결과
