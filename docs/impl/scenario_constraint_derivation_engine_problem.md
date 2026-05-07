# Task: 두 가지 핵심 문제 수정

## 문제 진단

### 문제 1: 자동 생성 시나리오의 expected_actions가 거의 없음 (mean=0.9)

현재 ConstraintDerivationEngine은 forbidden/required만 도출한다.
하지만 시나리오가 benchmark로 작동하려면 **expected_actions가 있어야** C2(compliance score)를 계산할 수 있다.
Expected=0이면 agent가 아무것도 안 해도 compliance=1.0이 되어 의미없는 시나리오가 된다.

**해결**: graph의 node별 mandatory_actions/expected_actions를 patient context 기반으로
활성화된 pathway의 action들로 도출한다.

### 문제 2: 105개 수동 시나리오 중 70개의 forbidden이 derived에 매핑 안 됨

논문에서 "all constraints are derived"라고 주장하려면,
수동 시나리오의 forbidden도 graph conditional rule로 커버되어야 한다.
현재 70개의 scenario-specific forbidden이 graph rule에 없다.

**해결**: 누락된 forbidden을 graph conditional rule로 추가한다 (gap 메우기).

---

## Part A: Expected Actions 도출 (Pathway Activation)

### 개념

CPG graph는 node들의 네트워크이다. 환자가 어떤 경로(pathway)를 타느냐에 따라
활성화되는 node가 다르고, 각 node의 expected_actions가 시나리오의 expected가 된다.

```
Graph: ada_dka_management
  initial_assessment (항상 활성)
    → severity_classification (항상 활성)
      → potassium_replacement_first (K+ < 3.3이면 활성)
      → insulin_therapy (항상 활성)
      → severe_dka_pathway (pH < 7.0이면 활성)
      → ongoing_monitoring (항상 활성)
```

환자의 labs/vitals/comorbidities를 보고 어떤 node가 활성화되는지 결정하면,
그 node들의 expected_actions가 시나리오의 expected가 된다.

### Step A.1: Graph Node에 activation_condition 추가

각 node에 이미 preconditions가 있지만, 이건 engine 런타임용이다.
PatientGenerator가 사용할 수 있는 형태의 activation_condition을 추가한다.

현재 graph YAML을 읽어서 각 node의 구조를 파악하라:
```bash
cat cpg_model/graphs/ada_dka_management.yaml | head -100
```

각 node에 `patient_activation_condition` 필드를 추가한다:

```yaml
# 예: ada_dka_management.yaml

initial_assessment:
  type: assessment
  # 기존 필드 유지
  expected_actions: [assess_vital_signs, establish_iv_access, order_lab_glucose, order_lab_bmp, order_lab_abg]
  patient_activation_condition: "True"  # 항상 활성

severity_classification:
  type: decision
  expected_actions: [classify_dka_severity]
  patient_activation_condition: "True"

potassium_replacement_first:
  type: treatment
  expected_actions: [order_lab_bmp, give_potassium_iv, recheck_potassium_in_1h]
  patient_activation_condition: "patient.labs.potassium < 3.3"

insulin_therapy:
  type: treatment
  expected_actions: [start_insulin_infusion, monitor_glucose_hourly]
  patient_activation_condition: "patient.labs.potassium >= 3.3"  # K+가 충분해야 insulin 가능

severe_dka_pathway:
  type: treatment
  expected_actions: [admit_to_icu, continuous_cardiac_monitoring, consider_bicarbonate_if_ph_below_6.9]
  patient_activation_condition: "patient.labs.ph < 7.0 or patient.labs.bicarbonate < 5"

ongoing_monitoring:
  type: monitoring
  expected_actions: [monitor_potassium_q2h, assess_anion_gap_closure]
  patient_activation_condition: "True"
```

**모든 20개 graph의 모든 node에 patient_activation_condition을 추가하라.**

규칙:
- entry node + 공통 assessment node: `"True"` (항상 활성)
- severity/pathway 분기 node: 환자 조건으로 분기 (lab값, vitals, comorbidities)
- 치료 node: 해당 치료가 적용되는 조건
- condition이 불명확하면 `"True"`로 두되, 주석으로 `# TODO: refine` 표기

### Step A.2: ConstraintDerivationEngine에 expected actions 도출 추가

`cpg_model/constraint_derivation.py`를 수정한다:

```python
class ConstraintDerivationEngine:
    
    def derive(self, graph: dict, patient: dict, scenario_id: str = "") -> DerivedConstraintSet:
        result = DerivedConstraintSet(scenario_id=scenario_id, graph_id=graph.get("graph_id", ""))
        
        # 기존 1-4 유지 (forbidden, sequence, conditional, allergy)
        # ...
        
        # 5. Expected actions 도출 (pathway activation)
        activated_expected = self._derive_expected_actions(graph, patient)
        for action, provenance in activated_expected:
            result.add(DerivedConstraint(
                constraint_type="EXPECTED",
                actions=[action],
                provenance=provenance,
                evidence="",
                severity="STANDARD",
                description=f"Expected action from activated pathway",
                condition_met="pathway_active",
                is_conditional=True
            ))
        
        return result
    
    def _derive_expected_actions(self, graph: dict, patient: dict) -> list:
        """
        graph의 각 node를 순회하여, patient_activation_condition이 True인
        node의 expected_actions를 수집.
        
        Returns: [(action, provenance_string), ...]
        """
        activated = []
        
        for node_id, node in graph.get("nodes", {}).items():
            condition = node.get("patient_activation_condition", "True")
            
            if self._evaluate_condition(condition, patient):
                for action in node.get("expected_actions", []):
                    provenance = f"graph:{graph['graph_id']}:node:{node_id}:expected"
                    activated.append((action, provenance))
        
        # 중복 제거 (같은 action이 여러 node에서 나올 수 있음)
        seen = set()
        unique = []
        for action, prov in activated:
            if action not in seen:
                seen.add(action)
                unique.append((action, prov))
        
        return unique
```

### Step A.3: PatientGenerator가 expected actions를 시나리오에 주입

`cpg_model/patient_generator.py`를 수정한다:

```python
class PatientGenerator:
    
    def generate_from_graph(self, graph: dict) -> List[GeneratedScenario]:
        scenarios = []
        all_rules = self._collect_all_rules(graph)
        
        for rule in all_rules:
            trigger_patient = self._generate_trigger_patient(rule, graph)
            if trigger_patient:
                derived = self.engine.derive(graph, trigger_patient, ...)
                
                # expected_actions를 derived에서 추출
                expected_actions = [a for c in derived.required for a in c.actions]
                # + pathway activation에서 온 EXPECTED
                expected_actions += [a for c in derived.expected for a in c.actions]
                expected_actions = list(dict.fromkeys(expected_actions))  # 중복 제거, 순서 유지
                
                # forbidden_actions도 derived에서
                forbidden_actions = [a for c in derived.forbidden for a in c.actions]
                forbidden_actions = list(dict.fromkeys(forbidden_actions))
                
                scenarios.append(GeneratedScenario(
                    scenario_id=...,
                    guideline_graph=graph["graph_id"],
                    patient=trigger_patient,
                    expected_actions=expected_actions,    # 이제 채워짐
                    forbidden_actions=forbidden_actions,
                    derived_constraints=derived.to_yaml(),
                    trap_scenario=True,
                    trap_description=rule.get("description", ""),
                    triggered_rules=[rule["rule_id"]],
                    generation_method="auto:single_rule_trigger"
                ))
        # ... normal patient도 동일하게
```

### Step A.4: 검증

```bash
python scripts/generate_all_scenarios.py

python -c "
from cpg_model.scenario_loader import ScenarioLoader
loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()

auto = [s for s in scenarios if 'auto' in s.scenario_id or s.generation_method]
ea_counts = [len(s.expected_actions) for s in auto]
print(f'Auto-generated expected_actions: min={min(ea_counts)}, max={max(ea_counts)}, mean={sum(ea_counts)/len(ea_counts):.1f}')

# Expected=0인 시나리오가 있으면 경고
zero_ea = [s.scenario_id for s in auto if len(s.expected_actions) == 0]
if zero_ea:
    print(f'WARNING: {len(zero_ea)} auto scenarios still have 0 expected_actions')
    for sid in zero_ea[:10]:
        print(f'  {sid}')
else:
    print('PASS: All auto scenarios have expected_actions')
"
```

**목표: 자동 생성 시나리오의 expected_actions mean >= 4**

---

## Part B: Manual Forbidden Coverage 확장

### Step B.1: Gap 분석

먼저 70개 시나리오의 "derived에 없는 forbidden" 목록을 추출한다:

```bash
python scripts/cross_reference_manual_vs_derived.py --output-gaps gaps.json
```

또는 직접:

```python
# scripts/analyze_manual_gaps.py
"""
수동 시나리오의 forbidden 중 derived에 없는 것을 분류.
"""
from cpg_model.constraint_derivation import ConstraintDerivationEngine
from cpg_model.scenario_loader import ScenarioLoader

engine = ConstraintDerivationEngine()
loader = ScenarioLoader()

gaps_by_type = {
    "naming_mismatch": [],     # 이름만 다르고 의미 같음 → normalizer로 해결
    "needs_conditional_rule": [], # graph에 rule 추가 필요
    "scenario_specific": [],   # 매우 특수해서 graph rule로 일반화 불가
}

manual_scenarios = [s for s in loader.load_all_scenarios() 
                    if not hasattr(s, 'generation_method') or not s.generation_method]

for s in manual_scenarios:
    if not s.forbidden_actions:
        continue
    
    graph = load_graph_for_scenario(s)
    derived = engine.derive(graph, s.patient.__dict__, s.scenario_id)
    derived_forbidden = set(a for c in derived.forbidden for a in c.actions)
    manual_forbidden = set(s.forbidden_actions)
    
    missing = manual_forbidden - derived_forbidden
    
    for action in missing:
        # 분류 로직
        if is_naming_variant(action, derived_forbidden):
            gaps_by_type["naming_mismatch"].append({
                "scenario": s.scenario_id,
                "action": action,
                "graph": s.guideline_graph
            })
        elif is_generalizable(action):
            gaps_by_type["needs_conditional_rule"].append({
                "scenario": s.scenario_id,
                "action": action,
                "graph": s.guideline_graph,
                "patient_condition": extract_trigger_condition(s)
            })
        else:
            gaps_by_type["scenario_specific"].append({
                "scenario": s.scenario_id,
                "action": action,
                "graph": s.guideline_graph
            })

print(f"Naming mismatch (normalizer로 해결): {len(gaps_by_type['naming_mismatch'])}")
print(f"Needs conditional rule (graph에 추가): {len(gaps_by_type['needs_conditional_rule'])}")
print(f"Scenario-specific (일반화 불가): {len(gaps_by_type['scenario_specific'])}")

import json
with open("evidence_pack/manual_forbidden_gaps.json", "w") as f:
    json.dump(gaps_by_type, f, indent=2)
```

### Step B.2: Gap별 해결

**Type 1: Naming mismatch** → ActionNormalizer에 매핑 추가

예: `discharge_without_fetal_assessment` ↔ `discharge_without_assessment` + pregnancy context

```python
# cpg_model/action_normalizer.py에 추가
NORMALIZER_MAP.update({
    "discharge_without_fetal_assessment": "discharge_without_assessment",
    "delay_cath_lab_for_dka_resolution": "delay_reperfusion",
    # ... gap 분석 결과에서 추출
})
```

**Type 2: Needs conditional rule** → graph에 rule 추가

gap 분석 결과를 읽고, 각각에 대해 graph의 적절한 node에 conditional rule을 추가한다.

예시 패턴:
- `give_systemic_thrombolysis_with_recent_surgery_contraindication` 
  → pulmonary_embolism graph에 rule 추가:
  ```yaml
  - rule_id: "PE-RECENT-SURGERY-NO-SYSTEMIC-THROMBOLYSIS"
    condition: "'recent_major_surgery' in patient.comorbidities"
    effect: {type: FORBIDDEN, actions: [give_systemic_thrombolysis, give_tpa_systemic]}
  ```

- `give_anticoagulation_without_chadsvasc`
  → atrial_fibrillation graph에 rule 추가:
  ```yaml
  - rule_id: "AF-ANTICOAG-NEEDS-CHADSVASC"
    condition: "True"  # 모든 AF 환자에서 CHA2DS2-VASc 없이 항응고 금기
    effect: {type: FORBIDDEN, actions: [give_anticoagulation_without_chadsvasc]}
  ```

**Type 3: Scenario-specific** → 이건 graph rule로 일반화 불가.
이 경우 시나리오에 `_manual_override: true` 플래그를 달고,
논문에서 "N% of constraints are derived, remaining M% are scenario-specific overrides with documented justification"으로 보고.

### Step B.3: 재실행 + 검증

Gap을 메운 후:

```bash
# Conditional rules 재검증
python scripts/validate_conditional_rules.py

# Cross-reference 재실행
python scripts/cross_reference_manual_vs_derived.py

# 목표: "manual forbidden not in derived" 비율이 70/105 → 20/105 이하로 감소
```

### Step B.4: Coverage 통계 업데이트

```bash
python scripts/generate_audit_matrix.py

python -c "
from cpg_model.scenario_loader import ScenarioLoader
from cpg_model.constraint_derivation import ConstraintDerivationEngine

engine = ConstraintDerivationEngine()
loader = ScenarioLoader()

total_manual = 0
covered = 0
override = 0

for s in loader.load_all_scenarios():
    if hasattr(s, 'generation_method') and s.generation_method:
        continue  # 자동 생성은 skip
    
    total_manual += 1
    graph = load_graph_for_scenario(s)
    derived = engine.derive(graph, s.patient.__dict__, s.scenario_id)
    derived_forbidden = set(a for c in derived.forbidden for a in c.actions)
    manual_forbidden = set(s.forbidden_actions)
    
    missing = manual_forbidden - derived_forbidden
    if not missing:
        covered += 1
    elif len(missing) <= 2:
        covered += 1  # 1-2개 누락은 허용 범위
    else:
        override += 1

print(f'Manual scenarios fully/mostly covered by derivation: {covered}/{total_manual} ({covered/total_manual*100:.0f}%)')
print(f'Manual scenarios needing override: {override}/{total_manual} ({override/total_manual*100:.0f}%)')
"
```

**목표: 수동 시나리오의 80%+ 이상이 derived constraints로 커버됨**

---

## Part C: Sequence Rules (BEFORE) 보강

현재 sequence rules가 7개뿐이다. 기존 handoff 문서에 29 BEFORE가 있었으므로 부족하다.

### Step C.1: 기존 graph의 sequence_rules 확인

```bash
grep -r "sequence_rules" cpg_model/graphs/ | wc -l
grep -r "BEFORE" cpg_model/graphs/ | wc -l
```

기존 graph의 edge 정의나 node ordering에서 implicit sequence를 찾아
명시적 sequence_rules로 변환한다.

주요 추가 대상:
- `aha_chest_pain`: ECG → interpret → activate cath lab (기존 10개 BEFORE)
- `ada_dka_management`: IV access → fluid → insulin / BMP → K+ check → insulin (기존 12개)
- `ssc_sepsis_hour1`: blood culture → antibiotics / fluid → vasopressor (기존 4개)
- `aha_stroke`: CT → tPA decision / NIHSS → treatment (기존 0개 — 추가 필요)

각 graph에 sequence_rules를 기존 BEFORE constraint와 일치하도록 추가/확인하라.

```bash
# 기존 handoff 문서의 BEFORE 수와 현재 graph의 sequence_rules 수 대조
python -c "
expected_before = {
    'aha_chest_pain': 10,
    'ada_dka_management': 12,
    'ssc_sepsis_hour1': 4,
    'atrial_fibrillation': 1,
    'cap_pneumonia': 2,
    'kdigo_contrast_aki': 7,
}
# 각 graph에서 실제 sequence_rules 수 확인
for graph_id, expected in expected_before.items():
    graph = load_graph(f'cpg_model/graphs/{graph_id}.yaml')
    actual = count_sequence_rules(graph)
    status = 'OK' if actual >= expected else 'MISSING'
    print(f'{graph_id}: expected={expected}, actual={actual} [{status}]')
"
```

---

## Completion Criteria

- [ ] 자동 생성 시나리오 expected_actions mean >= 4
- [ ] Expected=0인 자동 생성 시나리오 0개
- [ ] 수동 시나리오 forbidden coverage >= 80% (derived로)
- [ ] Sequence rules >= 29 (기존 BEFORE 수 이상)
- [ ] 361+ total constraints 유지 또는 증가
- [ ] 모든 기존 테스트 통과 (regression 0)
- [ ] cross_reference WARNING 20개 이하

## 작업 순서

1. **Part A 먼저**: 모든 graph node에 patient_activation_condition 추가 → engine 수정 → 재생성
2. **Part C**: sequence_rules 보강 (A와 병행 가능)
3. **Part B**: gap 분석 → rule 추가 → cross-reference 재확인
4. **전체 재검증**: 시나리오 재생성 + 통계 확인