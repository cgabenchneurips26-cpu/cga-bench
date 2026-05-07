# DEVIATION 페널티와 typed_compliance 재검토

**작성**: 2026-05-04
**계기**: ALLM.H V7.3 평가 중 발견된 outlier(qwen397b ARDS 시나리오 compliance=0.000)가 이미 알려진 DEVIATION rubric 편향을 가장 극단적으로 재현. paper v1 robustness 분석에 반영하기 전에 metric의 전제·효과·한계를 재정리.

---

## 1. 5/6 violation 종류와 DEVIATION의 정의

`cpg_model/schemas/base.py::ViolationType`:

| Type | 정의 | 임상적 의미 |
|------|------|------------|
| **OMISSION** | 필수 액션 누락 | 직접적 환자 위해 (놓친 치료) |
| **COMMISSION** | 금지 액션 수행 | 직접적 환자 위해 (해로운 치료) |
| **TIMING** | 마감 초과 | 지연 위해 |
| **SEQUENCE** | 순서 위반 | 프로토콜 위반 (예: 항생제→배양 순서) |
| **DEVIATION** | `allowed_set` 외 액션 | "off-protocol" — 명시된 위해는 없으나 가이드라인 외 |

OMISSION/COMMISSION/TIMING/SEQUENCE는 **임상 위해 추론에 직결**된다. DEVIATION은 다르다 — *허용되지 않은* 액션이라는 사실 자체로 "위해"를 의미하지 않는다. 일반적인 ICU 모니터링(`assess_vital_signs`, `order_lab_cbc`)이 ARDS CPG 그래프의 `allowed_set`에 포함되어 있지 않다고 해서 그것이 환자를 해친다고 말할 수 없다.

`assessor_core/spec/verdict_definitions.py`에서 `typed_compliance`가 도입된 이유: **DEVIATION은 어휘-매칭 오차(vocabulary mismatch)의 noise이지, harm signal이 아니다**.

---

## 2. ALLM.H 평가 중 재현된 0.000 outlier

`ats_esicm_sccm_ards_2023_introduction_c000` (V7.3 SGSC):

```yaml
expected_actions: ['perform_recruitment_maneuver']  # 단 1개
forbidden_actions: 5
allowed_set: <ARDS-특이 어휘 (low_tv_vent, plateau_pressure, peep_titration, prone_positioning, ...)>
```

| | qwen397b | ALLM.H |
|--|--|--|
| `actions_count` | 24 | 24 |
| `violations_by_type` | **deviation=24**, omission=1 | timing=2, **deviation=3**, omission=1 |
| `compliance_score` | **0.000** | **0.750** |
| `C1_path_selection` | **0.0** | 0.875 |
| `C2_mandatory_completion` | 0.0 | 0.0 |
| `C3_forbidden_avoidance` | **1.0** | 1.0 |
| `C4_timing_compliance` | **1.0** | 0.0 |
| `C5_sequence_integrity` | **1.0** | 1.0 |
| `C6_conflict_avoidance` | **1.0** | 1.0 |

### 관찰 1 — qwen397b는 사실상 안전한 ICU 워크업을 했다

qwen397b의 24 액션: `assess_vital_signs`, `order_imaging_chest_xray`, `order_lab_cbc/bmp`, `assess_clinical_status`, `establish_intravenous_access`, `obtain_12_lead_ecg`, `monitor_oxygen_saturation_continuous`, `assess_neurological_status`, `calculate_murray_lung_injury_score`, ...

이는 **ARDS 환자에게 임상적으로 합리적인 워크업**이다. 어떤 임상의도 이를 보고 "환자를 해쳤다"고 말하지 않을 것이다.

### 관찰 2 — 그럼에도 sub-score는 5/6이 만점

C2-C6 = `0, 1, 1, 1, 1` → 6개 중 5개 만점. 하지만 **compliance_score는 0.000**. 즉 종합 점수는 C1(path_selection)에 사실상 독점적으로 좌우되고, C1은 DEVIATION으로 결정된다.

같은 24 액션을 한 ALLM.H는 어휘만 다를 뿐 (`initiate_low_tv_ventilation` vs `assess_clinical_status`) 임상 의사결정 깊이는 큰 차이가 없을 수 있는데, **점수는 0.000 vs 0.750으로 0.75 차이**.

### 관찰 3 — `expected_actions`가 1개일 때 어휘 불일치는 치명적

이 시나리오에서 expected는 `['perform_recruitment_maneuver']` 단 하나. 이 한 어휘를 빗나간 모든 액션은 자동으로 DEVIATION 후보가 된다. allowed_set이 충분히 넓지 않은 시나리오에서는 path_selection 점수가 사실상 "어휘 정확도"를 측정한다.

---

## 3. typed_compliance — 도입 motivation과 효과

### 정의
DEVIATION violations를 compliance 계산에서 제외. C1_path_selection이 DEVIATION을 dominant signal로 사용하는 구조에서 가장 큰 영향. 메모리 entry `reference_evaluator_definitions.md`: *"CwT verdict (typed_compliance≥0.7)이 본질적으로 이 문제를 우회하기 위해 도입됨"*.

### Population-level 효과 (`project_typed_cwt_recompute.md`, n=16944)

| Metric | Original (DEVIATION 포함) | Typed (DEVIATION 제외) | Δ |
|--------|------|------|---|
| Strict 3-way FA | 6.60% | **13.56%** | **2.05× 증가** |
| TOM∩ASC∩CwT FA | 11.56% | 21.79% | 1.88× 증가 |
| Pair reversal | 46.31% | 44.27% | 거의 동일 |
| η²(eval) | 0.0725 | 0.0321 | **−56%** |
| η²(run) | 0.0515 | 0.0515 | 불변 |
| **η²(eval)/η²(run)** | **1.41×** | **0.62×** | **역전** |

### 해석
- **FA(Failure Attribution) 2배 증가**: DEVIATION을 빼면 OMISSION/COMMISSION/TIMING의 절대적 영향력이 커져서 임계값(typed_compliance≥0.7) 통과 모델이 절반으로 줄어든다. 즉 typed는 "더 엄격한" 평가가 된다 — DEVIATION이 사실상 "쉬운 점수 보충 채널" 역할을 했음을 시사.
- **η²(eval)/η²(run) 역전**: 원래 모델 간 분산 > 같은 모델의 run-to-run 분산이었으나, typed 하에서는 **run 노이즈가 모델 차이보다 커진다**. 이는 paper의 "model identification is statistically reliable" claim의 일부 약화로 이어진다.
- **paper v1 결정**: original을 primary로 유지, typed는 §Robustness 섹션. 본문 결론을 typed로 뒤집지 않는 것이 권고.

### 그러나 typed가 모든 문제를 해결하지는 않음

1. **OMISSION 측정 자체가 어휘 매칭에 의존**: `expected_actions=['order_lab_surveillance_imaging_pau']` 같은 시나리오에서 모델이 `order_imaging_ct_aorta`를 한 경우 OMISSION으로 잡힐 수 있다 (의미는 같지만 어휘가 다름). DEVIATION을 빼도 OMISSION에 같은 어휘 편향이 잔존.
2. **C1 = 0인 시나리오의 평균 효과**: 본 보고서 §4의 10ep 분석에서 typed mean이 0.74-0.77로 압축된 것은 모델 간 진짜 차이가 사라져서가 아니라, C1을 빼면 C2-C6 (대부분 모든 모델에서 동일하게 1.0 또는 0.0)이 평균을 dominate해서 **모델 간 차이가 잘 안 보인다**. 즉 typed는 모델 분리 능력이 떨어진다.
3. **시나리오별 1등 빈도는 살아남는다**: ALLM.H의 best_typed=7/10은 이런 시나리오 일부에서 도메인-특이 어휘로 정밀하게 답을 맞춘 결과. 평균 metric이 압축되어도 시나리오별 우열은 보존됨.

---

## 4. 10ep ALLM.H 비교에서 도출된 새 데이터

`seed=42` 무작위 추출 (V7.3 SGSC, r0):

| 모델 | compl | typed | Δ | best(compl) | **best(typed)** |
|------|-------|-------|---|-------------|------------------|
| oss120b | 0.690 | 0.743 | +0.053 | 4 | 1 |
| **ALLM.H** | 0.686 | 0.747 | +0.061 | 3 | **7** |
| qwen35b | 0.682 | 0.744 | +0.062 | 1 | 0 |
| gemma31b | 0.670 | 0.757 | +0.087 | 0 | 0 |
| qwen397b | 0.630 | **0.764** | +0.133 | 1 | 1 |
| qwen27b | 0.442 | **0.765** | **+0.323** | 0 | 1 |
| deepseek_r1_7b | 0.437 | 0.755 | **+0.318** | 0 | 0 |

### 두 가지 분리된 효과

**(A) Δ가 큰 모델 = DEVIATION 페널티의 가장 큰 수혜자**: qwen27b/deepseek/nemotron는 액션 수도 적고 (10-13개) DEVIATION 비율도 높음 → DEVIATION 제거 시 점수 폭등(+0.31). 이들의 raw compliance에서의 낮은 점수 절반은 어휘 미스매치 페널티.

**(B) Δ가 작은 모델 = raw compliance가 진짜 실력에 가까움**: ALLM.H (+0.061), qwen35b (+0.062), oss120b (+0.053). 이 셋은 DEVIATION 자체를 거의 받지 않음 — 어휘가 CPG와 잘 정렬되어 있다.

### 핵심 발견: typed 하에서 **ALLM.H의 시나리오별 1등 빈도(7/10)** > 다른 모델 합(3/10)

- 평균 metric은 0.003-0.004 spread로 압축되지만, 시나리오 단위로 보면 ALLM.H는 도메인-특이 어휘 매칭에서 명확한 우위. 즉 medical-SFT는 어휘 충실성에서 작동.
- 동시에 평균은 거의 동률 → "ALLM.H가 397B를 이긴다"는 raw-compliance 기반 claim은 typed로 보면 약화.

---

## 5. 재검토 포인트 — paper v1 / benchmark v2

### A. paper v1 (즉시 적용 가능)
1. **§Robustness에 typed_compliance 분석을 본 보고서 수준 깊이로 강화** (기존 robustness는 압축된 형태). 특히 η²(eval)/η²(run) 역전을 명시.
2. **Outlier 케이스 박스** (예: ats_ards qwen397b 0.000) 추가 — rubric의 어휘 의존성을 독자에게 직접 보여주기.
3. **Model-size invariance finding 재해석**: "397B≪35B" 주장은 어휘 적합도에 의한 것이지 reasoning 능력에 의한 것이 아닐 가능성 — 본문에서 careful framing 필요.
4. **ALLM.H 결과 보고 시 dual metric 의무화**: compliance + typed_compliance 동시 보고. 단일 metric으로 "ALLM.H가 397B 능가" 주장 불가.

### B. benchmark v2 (구조적 개선)
1. **Soft DEVIATION**: 명시적 contraindication만 페널티, 단순 off-protocol은 information(no penalty). C1' alt-rubric은 이미 §Appendix C에 시안 있음 — v2에서 default로 승격.
2. **Allowed_set 확장 audit**: 각 CPG 그래프의 `allowed_set`에 일반-목적 안전 액션(vitals/basic-labs/imaging)을 명시적으로 포함. 시나리오별 allowed_set 크기 분포 모니터링.
3. **Semantic action equivalence**: `order_lab_cbc` ≡ `order_lab_complete_blood_count`. assessor의 `_action_satisfies_requirement()` semantic matcher를 OMISSION에도 강하게 적용 (현재 conditional_placeholders 위주).
4. **Inter-annotator κ ≥ 0.7**: 메모리 `cpg_yaml_observer_dependence.md`의 권고. 한 명의 CPG 작성자 어휘 선택이 모델 점수를 좌우하는 현재 구조를 깨야 함.
5. **Per-scenario expected_actions 최소 크기 정책**: `expected_actions=1`인 시나리오는 metric 안정성이 낮음 (한 개 어휘 매칭 실패 = 점수 0). 최소 3-5 expected_actions 보장 또는 작은 expected_actions 시나리오는 별도 카테고리로 분리.

### C. ALLM.H 결과 해석 (ongoing 1254ep run)
1. **compliance_score 평균만으로 ranking 발표 금지**. typed_compliance + best_in_n 동반 보고.
2. **시나리오별 win-rate**가 ALLM.H의 진짜 강점 — 도메인 특이 어휘 매칭에서 우위.
3. **397B 대비 우위**는 견고. **35B 대비 우위**는 sample-dependent + run noise 한계 내. paper claim 강도 조절 필요.

---

## 6. 결론 — DEVIATION 제외는 정당하나 부분적 해결

DEVIATION이 typed_compliance에서 제외되어야 하는 이유는 명확하다:
- DEVIATION은 임상 harm signal이 아니라 어휘 매칭 noise
- DEVIATION이 dominant할 때 (qwen397b ARDS 0.000) 종합 점수가 임상 합리성과 무관해짐

그러나 typed_compliance는 단지 *DEVIATION-인한* 어휘 편향만 제거할 뿐, OMISSION/COMMISSION의 어휘 의존성은 그대로 유지된다. 그리고 typed로 보면 모델 간 차이가 압축되어 ranking이 sample noise에 더 민감해진다.

**진짜 해결책은 rubric 자체의 의미론(semantics) 강화**:
- Allowed_set의 의도를 "이 시나리오에서 합리적인 모든 액션의 superset"으로 확장
- 의미 동등 액션 매칭 (action_id 어휘를 넘어선 semantic equivalence)
- Inter-annotator agreement 의무화

paper v1에서는 typed를 §Robustness에 강화하고, benchmark v2에서 위 구조 개선을 default로 적용하는 것이 권고.

---

## 참조

- `docs/critical_review/cpg_yaml_observer_dependence.md` — 원래 진단
- `docs/critical_review/typed_cwt_v2_corrected.md` — 페이퍼-수준 typed 재계산
- `docs/critical_review/evaluator_audit_VII.md` — verdict definition 감사
- `assessor_core/spec/verdict_definitions.py` — typed_compliance 정의
- `assessor_core/violations.py` — DEVIATION 추출 로직
- `cpg_model/schemas/base.py` — ViolationType enum + CGAScore dataclass
- 실증 데이터:
  - `results/v73_full/qwen397b/ats_esicm_sccm_ards_2023_introduction_c000_qwen397b_r0_*.json`
  - `results/v73_allm_h/allm_h/ats_esicm_sccm_ards_2023_introduction_c000_allm_h_r0_*.json`
