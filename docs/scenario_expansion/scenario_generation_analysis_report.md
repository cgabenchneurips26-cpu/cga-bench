# Scenario Constraint Derivation Engine — 전체 분석 보고서

작성일: 2026-04-03

## 1. 시스템 아키텍처

```
CPG Graph YAML (nodes, edges, conditional_rules, evidence)
       │
       ├──→ ConstraintDerivationEngine
       │         │
       │    Patient Context ──→ DerivedConstraintSet
       │                          ├─ FORBIDDEN (conditional + unconditional)
       │                          ├─ REQUIRED (conditional rules)
       │                          ├─ BEFORE (sequence_rules + required_prior_actions)
       │                          ├─ WITHIN (deadlines)
       │                          └─ EXPECTED (pathway activation → mandatory_actions)
       │
       └──→ PatientGenerator
                  │
             conditional_rules의 condition 분석
                  │
                  ├──→ trigger patients (condition 만족 → trap scenario)
                  ├──→ normal patients (condition 불만족 → baseline scenario)
                  └──→ combinatorial patients (2-3 rules 동시 trigger)
```

## 2. 핵심 수치

| Metric | Value |
|--------|-------|
| Total CPG graphs | 25 |
| Conditional rules | 239 |
| Unconditional forbidden | 184 |
| Sequence rules (BEFORE) | 53 |
| Total constraints | 453+ |
| Auto-generated scenarios | 313 |
| Manual scenarios | 105 |
| **Total scenarios** | **418** |

## 3. 시나리오 생성 메커니즘

### 3.1 생성 공식

각 conditional rule에서:
- **1 trigger patient**: condition == True → trap scenario
- **1 normal patient**: condition == False → baseline scenario
- **Combinatorial**: 2-3 independent rules 동시 trigger

### 3.2 Graph별 생성 수

| Graph | Rules | Trigger | Normal | Combo | Skip | Total |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|
| acls_cardiac_arrest | 16 | 16 | 14 | 5 | 2 | 35 |
| idsa_meningitis | 16 | 16 | 14 | 4 | 2 | 34 |
| gina_asthma_exacerbation | 17 | 16 | 12 | 4 | 6 | 32 |
| kdigo_aki_full | 15 | 14 | 13 | 5 | 3 | 32 |
| toxicology_management | 17 | 15 | 14 | 2 | 5 | 31 |
| ... | | | | | | |
| **TOTAL** | **239** | **221** | **222** | **94** | **31** | **537** |

- Single-rule efficiency: 93% (443/478)
- Post-deduplication: 537 → 313

### 3.3 Deduplication 분석

| 항목 | 값 |
|------|---:|
| Pre-dedup | 537 |
| Post-dedup | 313 |
| Unique rule sets | 289 |
| Duplicates removed | 24 |

생성 방법 분포:
- single_rule_trigger: 194 (62%)
- combinatorial: 94 (30%)
- single_rule_normal: 25 (8%)

Normal 시나리오는 triggered_rules=[]로 동일하여 graph당 1개만 유지.

## 4. 시나리오 생성 잠재력

### 4.1 5축 확장 모델

| 축 | 수량 | 설명 |
|---|---:|---|
| 축 1 — Single-rule trigger | 239 | rule당 1개 trap |
| 축 2 — Pathway normal | 31 | pathway 조합별 baseline |
| 축 3 — Value variation | 148 | numeric rule × 2 추가값 (boundary, extreme) |
| 축 4 — 2-rule combinatorial | 1,237 | 2개 rule 동시 trigger |
| **실용적 최대 (축 1-4)** | **1,655** | |
| 축 5 — 3-rule combinatorial | 4,567 | 3개 rule 동시 trigger |
| **이론적 최대 (축 1-5)** | **6,222** | |

### 4.2 확장 규모별 실행 추정

| 규모 | 시나리오 | Episodes (×5mod×3run) | 실행 시간 (4 GPU 병렬) |
|------|------:|------:|------:|
| 현재 | ~418 | 6,270 | ~5.4일 |
| +Pathway normals | ~449 | 6,735 | ~5.8일 |
| +Value variation | ~597 | 8,955 | ~7.8일 |
| Full practical max | ~1,655 | 24,825 | ~21.5일 |

### 4.3 현재 활용률

- 현재: 418 / 1,655 = **25.3%**
- 논문 주장: "Our framework supports up to 1,655 clinically valid scenarios; we evaluate 418 selected scenarios covering all 25 CPG domains."

## 5. Pathway Variation 분석

| Graph | Conditional Nodes | Pathway Combos |
|-------|:---:|:---:|
| aha_heart_failure_2022 | 16 | 45 |
| kdigo_aki_full | 9 | 30 |
| aha_stroke_2019 | 14 | 15 |
| aba_burn_resuscitation | 3 | 8 |
| aabb_transfusion / acog | 3 | 6 |
| 나머지 17개 | 0 | 1 |
| **Total** | **55** | **136** |

### Pathway Diversity 예시

**Stroke** (4 pathways, 매우 다른 expected):
- Ischemic tPA eligible: 27 expected
- Ischemic thrombectomy (LVO): 31 expected
- Hemorrhagic ICH: 20 expected
- Wake-up stroke (extended window): 19 expected

**DKA** (2 pathways):
- Moderate (pH 7.15): 17 expected
- Severe (pH 6.85): 21 expected (+ICU, bicarbonate)

**Heart Failure** (3+ pathways):
- HFrEF stable: 19 expected (GDMT)
- HFpEF fluid overload: 18 expected (diuretics)
- Cardiogenic shock: 41 expected (shock + MCS)

## 6. 품질 검증 결과

### 6.1 코드 검증

| Test Suite | Tests | Result |
|-----------|:---:|:---:|
| Edge cases (condition eval) | 16 | PASS |
| Expected derivation | 5 | PASS |
| PatientGenerator accuracy | 2 | PASS |
| Determinism | 2 | PASS |
| Constraint derivation core | 30 | PASS |
| Patient generator core | 21 | PASS |
| Engine regression | 118 | PASS |
| **Total** | **194** | **PASS** |

### 6.2 생성 시나리오 품질

| 검증 항목 | 결과 |
|-----------|------|
| Expected∩Forbidden 모순 | **0** |
| Expected=0 AND Forbidden=0 | **0** |
| Vitals 생리학적 범위 이탈 | 3 (ACLS K+>10, 허용범위) |
| Trap-Normal differentiation | 21/25 graphs > 50% |

### 6.3 버그 발견 및 수정

1. **eval() safe builtins**: `{"__builtins__": {}}` → `str()`, `len()` 차단됨 → safe whitelist 추가
2. **Compound condition trigger failure**: AND 조건에서 trigger_range 불완전 → 사후 검증 추가
3. **Over-activated nodes**: 91 expected in stroke → `patient_activation_condition` 추가 → max=28
4. **Unconditional forbidden 과다**: trap differentiation 저하 → conditional로 전환

## 7. 파일 목록

### Core Engine
- `cpg_model/constraint_derivation.py` — ConstraintDerivationEngine
- `cpg_model/patient_generator.py` — PatientGenerator
- `cpg_model/allergy_drug_map.yaml` — Allergy-drug mapping
- `cpg_model/schemas/base.py` — ConditionalRule, ConstraintType, RuleSeverity

### CPG Graphs (25 total)
- 14 기존 + 11 신규 (anaphylaxis, ACLS, status epilepticus, asthma, meningitis, toxicology, transfusion, burn, obstetric hemorrhage, agitation, PALS)

### Scripts
- `scripts/generate_all_scenarios.py` — 시나리오 자동 생성
- `scripts/validate_conditional_rules.py` — 스키마 검증
- `scripts/generate_audit_matrix.py` — Rule Coverage Audit
- `scripts/cross_reference_manual_vs_derived.py` — Manual↔Derived 교차 검증
- `scripts/detect_contradictions.py` — 모순 탐지
- `scripts/verify_trap_differentiation.py` — Trap 차별화 검증
- `scripts/verify_expected_distribution.py` — Expected 분포 검증
- `scripts/analyze_generation_mechanics.py` — 생성 메커니즘 해부
- `scripts/theoretical_max_scenarios.py` — 이론적 최대
- `scripts/count_pathway_variations.py` — Pathway 조합 분석
- `scripts/count_total_scenario_potential.py` — 5축 잠재력 계산
- `scripts/show_normal_diversity_examples.py` — Pathway diversity 예시

### Tests (194 total)
- `tests/test_constraint_derivation.py` (30)
- `tests/test_patient_generator.py` (21)
- `tests/test_patient_generator_accuracy.py` (2)
- `tests/test_derivation_edge_cases.py` (16)
- `tests/test_expected_derivation.py` (5)
- `tests/test_derivation_determinism.py` (2)
- `tests/test_engine/` (118 existing)

## 8. Git Commits

1. `46880e65` — feat(cpg): implement Scenario Constraint Derivation Engine
2. `aba39e4a` — feat(cpg): deep verification + expected actions pathway activation + analysis scripts
