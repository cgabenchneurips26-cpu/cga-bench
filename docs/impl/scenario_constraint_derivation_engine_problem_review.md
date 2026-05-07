# Task: 시나리오 생성 시스템 심층 검증

숫자(366개, expected 22.6, constraints 455)는 좋아 보이지만, 실제로 제대로 되었는지 확인한다.
검증은 두 축: (1) 코드가 의도대로 작동하는가, (2) 생성된 시나리오가 임상적으로 유효한가.

---

## Part 1: 코드 검증 — Derivation Engine이 정확한가

### Test 1.1: 조건 평가 정확성

ConstraintDerivationEngine._evaluate_condition()이 edge case에서도 맞는지.

```python
# tests/test_derivation_edge_cases.py

from cpg_model.constraint_derivation import ConstraintDerivationEngine

engine = ConstraintDerivationEngine()

# --- 기본 비교 ---
def test_numeric_less_than():
    patient = {"labs": {"potassium": 2.9}}
    assert engine._evaluate_condition("patient.labs.potassium < 3.3", patient) == True
    
def test_numeric_boundary_exact():
    patient = {"labs": {"potassium": 3.3}}
    assert engine._evaluate_condition("patient.labs.potassium < 3.3", patient) == False

def test_numeric_greater_than():
    patient = {"labs": {"potassium": 6.2}}
    assert engine._evaluate_condition("patient.labs.potassium > 5.5", patient) == True

# --- list membership ---
def test_list_contains():
    patient = {"comorbidities": ["cocaine_use", "hypertension"]}
    assert engine._evaluate_condition("'cocaine_use' in patient.comorbidities", patient) == True

def test_list_not_contains():
    patient = {"comorbidities": ["hypertension"]}
    assert engine._evaluate_condition("'cocaine_use' in patient.comorbidities", patient) == False

# --- compound conditions ---
def test_and_condition():
    patient = {"medications": ["sglt2_inhibitor"], "labs": {"glucose": 180}}
    assert engine._evaluate_condition(
        "'sglt2_inhibitor' in patient.medications and patient.labs.glucose < 250", patient
    ) == True

def test_or_condition():
    patient = {"vitals": {"sbp": 190, "dbp": 100}}
    assert engine._evaluate_condition(
        "patient.vitals.sbp > 185 or patient.vitals.dbp > 110", patient
    ) == True

def test_or_condition_second_true():
    patient = {"vitals": {"sbp": 170, "dbp": 115}}
    assert engine._evaluate_condition(
        "patient.vitals.sbp > 185 or patient.vitals.dbp > 110", patient
    ) == True

def test_or_condition_neither():
    patient = {"vitals": {"sbp": 170, "dbp": 100}}
    assert engine._evaluate_condition(
        "patient.vitals.sbp > 185 or patient.vitals.dbp > 110", patient
    ) == False

# --- missing fields (graceful failure) ---
def test_missing_lab_field():
    patient = {"labs": {}}
    # potassium 없으면 condition 평가 실패 → False 반환 (trigger 안 됨)
    assert engine._evaluate_condition("patient.labs.potassium < 3.3", patient) == False

def test_missing_labs_entirely():
    patient = {}
    assert engine._evaluate_condition("patient.labs.potassium < 3.3", patient) == False

def test_missing_comorbidities():
    patient = {}
    assert engine._evaluate_condition("'cocaine_use' in patient.comorbidities", patient) == False

# --- always-true ---
def test_true_condition():
    patient = {}
    assert engine._evaluate_condition("True", patient) == True

# --- nested access ---
def test_deeply_nested():
    patient = {"presentation": {"symptom_onset_hours": 18}}
    assert engine._evaluate_condition(
        "patient.presentation.symptom_onset_hours > 12", patient
    ) == True
```

이 테스트를 **실행하고 결과를 보고하라.** 실패하는 것이 있으면 engine 코드를 수정.

### Test 1.2: Expected Actions 도출 정확성

특정 patient context를 넣었을 때, 활성화되는 node와 expected actions가 맞는지.

```python
# tests/test_expected_derivation.py

def test_dka_hypokalemia_activates_k_replacement():
    """K+ 2.9 → potassium_replacement_first node 활성화"""
    engine = ConstraintDerivationEngine()
    graph = load_graph("cpg_model/graphs/ada_dka_management.yaml")
    patient = {
        "age": 28, "sex": "M",
        "labs": {"potassium": 2.9, "glucose": 450, "ph": 7.15, "bicarbonate": 8},
        "comorbidities": ["type_1_diabetes"],
        "allergies": [], "medications": []
    }
    result = engine.derive(graph, patient)
    
    expected = [a for c in result.expected for a in c.actions] if hasattr(result, 'expected') else []
    # + required
    expected += [a for c in result.required for a in c.actions]
    
    # K+ replacement 관련 action이 expected에 있어야 함
    assert any("potassium" in a for a in expected), \
        f"Expected potassium-related action, got: {expected}"
    
    # insulin은 forbidden이어야 함 (K+ < 3.3)
    forbidden = [a for c in result.forbidden for a in c.actions]
    assert "start_insulin_infusion" in forbidden

def test_dka_normal_k_activates_insulin():
    """K+ 4.2 → insulin_therapy node 활성화, potassium_replacement 비활성"""
    engine = ConstraintDerivationEngine()
    graph = load_graph("cpg_model/graphs/ada_dka_management.yaml")
    patient = {
        "age": 28, "sex": "M",
        "labs": {"potassium": 4.2, "glucose": 450, "ph": 7.15, "bicarbonate": 8},
        "comorbidities": ["type_1_diabetes"],
        "allergies": [], "medications": []
    }
    result = engine.derive(graph, patient)
    
    expected = [a for c in result.expected for a in c.actions] if hasattr(result, 'expected') else []
    expected += [a for c in result.required for a in c.actions]
    
    # insulin 관련 action이 expected에 있어야 함
    assert any("insulin" in a for a in expected), \
        f"Expected insulin-related action, got: {expected}"
    
    # insulin은 forbidden이면 안 됨
    forbidden = [a for c in result.forbidden for a in c.actions]
    conditional_insulin_forbidden = [a for a in forbidden if "insulin" in a]
    # graph-level unconditional forbidden에 insulin이 있을 수 있으므로,
    # conditional forbidden만 체크
    conditional = [c for c in result.forbidden if c.is_conditional and "insulin" in str(c.actions)]
    assert len(conditional) == 0, \
        f"Insulin should not be conditionally forbidden with K+=4.2"

def test_sepsis_penicillin_allergy_no_cephalosporin():
    """페니실린 아나필락시스 → 세팔로스포린도 forbidden"""
    engine = ConstraintDerivationEngine()
    graph = load_graph("cpg_model/graphs/ssc_sepsis_hour1.yaml")
    patient = {
        "age": 55, "sex": "F",
        "labs": {"lactate": 4.5},
        "comorbidities": [],
        "allergies": ["penicillin_anaphylaxis"],
        "medications": [], "vitals": {"sbp": 80, "hr": 120}
    }
    result = engine.derive(graph, patient)
    forbidden = [a for c in result.forbidden for a in c.actions]
    
    assert "give_cephalosporin" in forbidden or "give_ceftriaxone" in forbidden, \
        f"Cephalosporin should be forbidden with penicillin anaphylaxis. Got: {forbidden}"

def test_anaphylaxis_beta_blocker_needs_glucagon():
    """Beta-blocker 복용 중 아나필락시스 → glucagon required"""
    engine = ConstraintDerivationEngine()
    graph = load_graph("cpg_model/graphs/anaphylaxis_management.yaml")
    patient = {
        "age": 60, "sex": "M",
        "comorbidities": [],
        "allergies": ["peanut"],
        "medications": ["beta_blocker"],
        "vitals": {"sbp": 70, "hr": 50}
    }
    result = engine.derive(graph, patient)
    required = [a for c in result.required for a in c.actions]
    
    assert "give_glucagon" in required, \
        f"Glucagon should be required for beta-blocker patient. Got: {required}"
```

### Test 1.3: PatientGenerator 정확성

trigger_range에서 생성된 환자가 실제로 rule을 trigger하는지.

```python
# tests/test_patient_generator_accuracy.py

def test_generated_trigger_patient_actually_triggers():
    """PatientGenerator가 만든 trigger patient가 실제로 rule을 trigger하는지"""
    engine = ConstraintDerivationEngine()
    generator = PatientGenerator(engine)
    
    for graph_path in Path("cpg_model/graphs/").glob("*.yaml"):
        graph = load_graph(graph_path)
        rules = generator._collect_all_rules(graph)
        
        for rule in rules:
            trigger_patient = generator._generate_trigger_patient(rule, graph)
            if trigger_patient is None:
                continue
            
            # 이 patient로 derive 했을 때, 이 rule이 trigger되어야 함
            result = engine.derive(graph, trigger_patient)
            triggered_rule_ids = set()
            for c in result.forbidden + result.required + result.before + result.within:
                if hasattr(c, 'provenance') and rule["rule_id"] in c.provenance:
                    triggered_rule_ids.add(rule["rule_id"])
            
            assert rule["rule_id"] in triggered_rule_ids, \
                f"Rule {rule['rule_id']} not triggered by its own trigger patient!\n" \
                f"  Graph: {graph['graph_id']}\n" \
                f"  Condition: {rule['condition']}\n" \
                f"  Patient: {trigger_patient}\n" \
                f"  Triggered rules: {triggered_rule_ids}"

def test_generated_normal_patient_does_not_trigger():
    """PatientGenerator가 만든 normal patient가 rule을 trigger하지 않는지"""
    engine = ConstraintDerivationEngine()
    generator = PatientGenerator(engine)
    
    for graph_path in Path("cpg_model/graphs/").glob("*.yaml"):
        graph = load_graph(graph_path)
        rules = generator._collect_all_rules(graph)
        
        for rule in rules:
            normal_patient = generator._generate_normal_patient(rule, graph)
            if normal_patient is None:
                continue
            
            result = engine.derive(graph, normal_patient)
            should_not_trigger = False
            for c in result.forbidden + result.required:
                if hasattr(c, 'provenance') and rule["rule_id"] in c.provenance:
                    should_not_trigger = True
            
            assert not should_not_trigger, \
                f"Rule {rule['rule_id']} triggered by normal patient!\n" \
                f"  Condition: {rule['condition']}\n" \
                f"  Normal patient: {normal_patient}"
```

**이 모든 테스트를 실행하고 결과를 보고하라.**

---

## Part 2: 생성된 시나리오 내용 검증

코드가 맞더라도, 생성된 시나리오가 임상적으로 유효한지 확인해야 한다.

### Test 2.1: 시나리오 샘플 추출 및 상세 검토

각 graph에서 1개 trap + 1개 normal = 40개 시나리오를 추출하여 상세 검토.

```python
# scripts/sample_scenarios_for_review.py
"""
각 graph에서 auto-generated trap 1개 + normal 1개를 추출하여
사람이 읽을 수 있는 형태로 출력.
"""
from cpg_model.scenario_loader import ScenarioLoader
from cpg_model.constraint_derivation import ConstraintDerivationEngine
import random

loader = ScenarioLoader()
engine = ConstraintDerivationEngine()
scenarios = loader.load_all_scenarios()

# auto-generated만
auto = [s for s in scenarios if hasattr(s, 'generation_method') and s.generation_method]

from collections import defaultdict
by_graph = defaultdict(list)
for s in auto:
    by_graph[s.guideline_graph].append(s)

output = []
for graph_id in sorted(by_graph.keys()):
    graph_scenarios = by_graph[graph_id]
    traps = [s for s in graph_scenarios if s.trap_scenario]
    normals = [s for s in graph_scenarios if not s.trap_scenario]
    
    # 1 trap + 1 normal 랜덤 선택
    sample_trap = random.choice(traps) if traps else None
    sample_normal = random.choice(normals) if normals else None
    
    for label, s in [("TRAP", sample_trap), ("NORMAL", sample_normal)]:
        if s is None:
            continue
        
        graph = load_graph_for_scenario(s)
        derived = engine.derive(graph, s.patient.__dict__ if hasattr(s.patient, '__dict__') else s.patient, s.scenario_id)
        
        output.append(f"""
{'='*80}
GRAPH: {graph_id} | TYPE: {label} | ID: {s.scenario_id}
{'='*80}

PATIENT:
  Age: {s.patient.get('age', '?')}, Sex: {s.patient.get('sex', '?')}
  Chief complaint: {s.patient.get('chief_complaint', '?')}
  
  Labs: {s.patient.get('labs', {})}
  Vitals: {s.patient.get('vitals', {})}
  Comorbidities: {s.patient.get('comorbidities', [])}
  Allergies: {s.patient.get('allergies', [])}
  Medications: {s.patient.get('medications', [])}

EXPECTED ACTIONS ({len(s.expected_actions)}):
{chr(10).join(f'  - {a}' for a in s.expected_actions[:15])}
{'  ... (truncated)' if len(s.expected_actions) > 15 else ''}

FORBIDDEN ACTIONS ({len(s.forbidden_actions)}):
{chr(10).join(f'  - {a}' for a in s.forbidden_actions[:15])}
{'  ... (truncated)' if len(s.forbidden_actions) > 15 else ''}

TRAP: {s.trap_scenario}
TRAP DESCRIPTION: {getattr(s, 'trap_description', 'N/A')}

TRIGGERED RULES: {getattr(s, 'triggered_rules', [])}

CLINICAL VALIDITY CHECK:
  [ ] Patient presentation 합리적?
  [ ] Expected actions가 이 환자에게 적절?
  [ ] Forbidden actions가 이 환자에게 정말 금기?
  [ ] Trap이면: trap_description이 forbidden과 일치?
  [ ] Expected와 forbidden이 모순 안 됨?
""")

with open("evidence_pack/scenario_sample_review.txt", "w") as f:
    f.write('\n'.join(output))

print(f"Wrote {len(output)} scenario reviews to evidence_pack/scenario_sample_review.txt")
```

**이 스크립트를 실행하고, 출력 파일의 처음 5개 시나리오를 이 채팅에 보여달라.**

### Test 2.2: 일관성 검증 — 모순 탐지

```python
# scripts/detect_contradictions.py
"""
시나리오 내 모순 탐지:
1. 같은 action이 expected AND forbidden
2. Trap인데 forbidden이 graph unconditional (모든 시나리오에서 forbidden → trap 아님)
3. Expected action이 0인데 trap인 경우
4. Patient context와 triggered rule의 condition이 실제로 매치하는지
"""
from cpg_model.scenario_loader import ScenarioLoader
from cpg_model.constraint_derivation import ConstraintDerivationEngine

engine = ConstraintDerivationEngine()
loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()

issues = []

for s in scenarios:
    sid = s.scenario_id
    expected = set(s.expected_actions) if s.expected_actions else set()
    forbidden = set(s.forbidden_actions) if s.forbidden_actions else set()
    
    # 1. Expected ∩ Forbidden ≠ ∅
    overlap = expected & forbidden
    if overlap:
        issues.append(f"CONTRADICTION: {sid} — actions in both expected AND forbidden: {overlap}")
    
    # 2. Expected=0이면서 Forbidden도 0 (완전 무의미)
    if len(expected) == 0 and len(forbidden) == 0:
        issues.append(f"EMPTY: {sid} — no expected and no forbidden actions")
    
    # 3. Trap인데 trap_description 없음
    if s.trap_scenario and not getattr(s, 'trap_description', ''):
        issues.append(f"TRAP-NO-DESC: {sid} — trap=True but no description")
    
    # 4. Patient vitals 합리성
    patient = s.patient if isinstance(s.patient, dict) else s.patient.__dict__
    vitals = patient.get('vitals', {})
    if vitals:
        hr = vitals.get('hr') or vitals.get('heart_rate')
        sbp = vitals.get('sbp') or vitals.get('systolic_bp')
        spo2 = vitals.get('spo2')
        temp = vitals.get('temp') or vitals.get('temperature')
        
        if hr and (hr < 20 or hr > 250):
            issues.append(f"VITALS: {sid} — HR={hr} out of physiological range")
        if sbp and (sbp < 40 or sbp > 300):
            issues.append(f"VITALS: {sid} — SBP={sbp} out of physiological range")
        if spo2 and (spo2 < 30 or spo2 > 100):
            issues.append(f"VITALS: {sid} — SpO2={spo2} out of range")
        if temp and (temp < 30 or temp > 43):
            issues.append(f"VITALS: {sid} — Temp={temp} out of range")
    
    # 5. Lab 합리성
    labs = patient.get('labs', {})
    if labs:
        k = labs.get('potassium')
        if k and (k < 1.0 or k > 10.0):
            issues.append(f"LABS: {sid} — K+={k} out of physiological range")
        glu = labs.get('glucose')
        if glu and (glu < 10 or glu > 1500):
            issues.append(f"LABS: {sid} — Glucose={glu} out of range")
        ph = labs.get('ph')
        if ph and (ph < 6.5 or ph > 7.8):
            issues.append(f"LABS: {sid} — pH={ph} out of range")
        cr = labs.get('creatinine')
        if cr and (cr < 0.1 or cr > 20):
            issues.append(f"LABS: {sid} — Creatinine={cr} out of range")

# 6. 같은 graph에서 trap과 normal의 forbidden 차이가 있는지
# (만약 차이가 없으면 conditional rule이 작동 안 하는 것)
from collections import defaultdict
by_graph = defaultdict(list)
for s in scenarios:
    by_graph[s.guideline_graph].append(s)

for graph_id, graph_scenarios in by_graph.items():
    traps = [s for s in graph_scenarios if s.trap_scenario]
    normals = [s for s in graph_scenarios if not s.trap_scenario]
    
    if traps and normals:
        trap_forbidden = set()
        for t in traps:
            trap_forbidden.update(t.forbidden_actions or [])
        normal_forbidden = set()
        for n in normals:
            normal_forbidden.update(n.forbidden_actions or [])
        
        # trap에만 있는 forbidden = conditional rule이 만든 것
        trap_only = trap_forbidden - normal_forbidden
        if not trap_only:
            issues.append(f"NO-DIFF: {graph_id} — trap and normal scenarios have identical forbidden sets (conditional rules not differentiating)")

print(f"\n{'='*60}")
print(f"Total issues found: {len(issues)}")
print(f"{'='*60}")

by_type = defaultdict(list)
for issue in issues:
    issue_type = issue.split(":")[0]
    by_type[issue_type].append(issue)

for itype, ilist in sorted(by_type.items()):
    print(f"\n{itype}: {len(ilist)}")
    for i in ilist[:5]:
        print(f"  {i}")
    if len(ilist) > 5:
        print(f"  ... and {len(ilist)-5} more")

with open("evidence_pack/scenario_contradiction_report.txt", "w") as f:
    f.write('\n'.join(issues))
```

### Test 2.3: Derivation 일관성 — 같은 입력에 같은 출력

```python
# tests/test_derivation_determinism.py
"""
같은 graph + 같은 patient → 항상 같은 derived constraints
(random 요소 없는지 확인)
"""
def test_derivation_is_deterministic():
    engine = ConstraintDerivationEngine()
    graph = load_graph("cpg_model/graphs/ada_dka_management.yaml")
    patient = {
        "age": 28, "labs": {"potassium": 2.9, "glucose": 450, "ph": 7.15},
        "comorbidities": ["type_1_diabetes"],
        "allergies": [], "medications": []
    }
    
    result1 = engine.derive(graph, patient, "test1")
    result2 = engine.derive(graph, patient, "test2")
    
    forbidden1 = sorted([a for c in result1.forbidden for a in c.actions])
    forbidden2 = sorted([a for c in result2.forbidden for a in c.actions])
    assert forbidden1 == forbidden2, "Derivation is non-deterministic!"
    
    expected1 = sorted([a for c in result1.expected for a in c.actions]) if hasattr(result1, 'expected') else []
    expected2 = sorted([a for c in result2.expected for a in c.actions]) if hasattr(result2, 'expected') else []
    assert expected1 == expected2
```

### Test 2.4: Auto-generated scenario가 실행 가능한 형태인지

```python
# tests/test_scenario_runnability.py
"""
생성된 시나리오가 실제 benchmark runner에서 로드 가능한지.
(Full episode 실행은 아니고, 로드 + engine 초기화까지만)
"""
def test_all_scenarios_loadable():
    loader = ScenarioLoader()
    scenarios = loader.load_all_scenarios()
    
    for s in scenarios:
        # 1. graph resolve
        graph_path = get_cpg_graph_path(s.scenario_id)
        assert graph_path.exists(), f"{s.scenario_id}: graph not found"
        
        # 2. engine 초기화 가능
        try:
            engine = CPGEngineFactory.load_from_file(graph_path)
        except Exception as e:
            assert False, f"{s.scenario_id}: engine init failed: {e}"
        
        # 3. patient context가 engine에 주입 가능
        # (실제 run_episode의 초기화 단계만)
        try:
            engine.set_patient_context(s.patient)
        except Exception as e:
            # set_patient_context가 없으면 skip
            pass
        
        # 4. scenario forbidden이 engine에 주입 가능
        try:
            engine.set_scenario_forbidden_actions(s.forbidden_actions or [])
        except Exception as e:
            assert False, f"{s.scenario_id}: set_forbidden failed: {e}"

def test_auto_scenarios_have_required_fields():
    """auto_generated_scenarios.yaml의 모든 시나리오가 필수 필드를 가지는지"""
    loader = ScenarioLoader()
    scenarios = loader.load_all_scenarios()
    
    auto = [s for s in scenarios if 'auto' in str(getattr(s, 'generation_method', ''))]
    
    for s in auto:
        assert s.scenario_id, f"Missing scenario_id"
        assert s.guideline_graph, f"{s.scenario_id}: missing guideline_graph"
        assert s.patient, f"{s.scenario_id}: missing patient"
        
        patient = s.patient if isinstance(s.patient, dict) else vars(s.patient)
        assert patient.get('age'), f"{s.scenario_id}: missing age"
        assert patient.get('vitals'), f"{s.scenario_id}: missing vitals"
        
        vitals = patient['vitals']
        assert 'map_mmhg' in vitals or 'sbp' in vitals, \
            f"{s.scenario_id}: missing map_mmhg or sbp in vitals"
        
        # expected OR forbidden 중 하나는 있어야 함
        has_expected = bool(s.expected_actions)
        has_forbidden = bool(s.forbidden_actions)
        assert has_expected or has_forbidden, \
            f"{s.scenario_id}: no expected and no forbidden"
```

---

## Part 3: 통계적 건강성 검증

### Test 3.1: Expected actions가 합리적인 분포인지

```python
# scripts/verify_expected_distribution.py
"""
Expected actions 22.6 mean이라고 했는데, 이게 정말 의미있는 값인지 확인.
혹시 모든 graph의 모든 node가 활성화되어 과도하게 많은 건 아닌지.
"""
from cpg_model.scenario_loader import ScenarioLoader
from collections import Counter

loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()

auto = [s for s in scenarios if hasattr(s, 'generation_method') and s.generation_method]
manual = [s for s in scenarios if not hasattr(s, 'generation_method') or not s.generation_method]

print("=== Auto-generated scenarios ===")
auto_ea = [len(s.expected_actions) for s in auto]
print(f"Expected actions: min={min(auto_ea)}, max={max(auto_ea)}, mean={sum(auto_ea)/len(auto_ea):.1f}, median={sorted(auto_ea)[len(auto_ea)//2]}")

# 분포 히스토그램
bins = Counter()
for ea in auto_ea:
    if ea == 0: bins["0"] += 1
    elif ea <= 5: bins["1-5"] += 1
    elif ea <= 10: bins["6-10"] += 1
    elif ea <= 20: bins["11-20"] += 1
    elif ea <= 30: bins["21-30"] += 1
    else: bins["31+"] += 1
print(f"Distribution: {dict(sorted(bins.items()))}")

print(f"\n=== Manual scenarios ===")
manual_ea = [len(s.expected_actions) for s in manual]
print(f"Expected actions: min={min(manual_ea)}, max={max(manual_ea)}, mean={sum(manual_ea)/len(manual_ea):.1f}, median={sorted(manual_ea)[len(manual_ea)//2]}")

print(f"\n=== Forbidden actions ===")
auto_fa = [len(s.forbidden_actions) for s in auto]
manual_fa = [len(s.forbidden_actions) for s in manual]
print(f"Auto forbidden: min={min(auto_fa)}, max={max(auto_fa)}, mean={sum(auto_fa)/len(auto_fa):.1f}")
print(f"Manual forbidden: min={min(manual_fa)}, max={max(manual_fa)}, mean={sum(manual_fa)/len(manual_fa):.1f}")

# 과도하게 높은 expected를 가진 시나리오 검토
high_ea = [(s.scenario_id, len(s.expected_actions), s.guideline_graph) 
           for s in auto if len(s.expected_actions) > 30]
if high_ea:
    print(f"\n=== Scenarios with >30 expected actions ({len(high_ea)}) ===")
    for sid, ea, g in sorted(high_ea, key=lambda x: -x[1])[:10]:
        print(f"  {sid}: {ea} expected (graph: {g})")
    print("CHECK: 모든 node가 True로 활성화되어 과도하게 많은 건 아닌지 확인 필요")

# 같은 graph에서 trap과 normal의 expected 차이
from collections import defaultdict
by_graph = defaultdict(lambda: {"trap": [], "normal": []})
for s in auto:
    key = "trap" if s.trap_scenario else "normal"
    by_graph[s.guideline_graph][key].append(len(s.expected_actions))

print(f"\n=== Expected actions: trap vs normal by graph ===")
for g in sorted(by_graph.keys()):
    trap_ea = by_graph[g]["trap"]
    norm_ea = by_graph[g]["normal"]
    t_mean = sum(trap_ea)/len(trap_ea) if trap_ea else 0
    n_mean = sum(norm_ea)/len(norm_ea) if norm_ea else 0
    print(f"  {g}: trap={t_mean:.1f} ({len(trap_ea)}), normal={n_mean:.1f} ({len(norm_ea)})")
```

### Test 3.2: Trap vs Normal 차별화

```python
# scripts/verify_trap_differentiation.py
"""
핵심 질문: trap 시나리오가 normal 시나리오와 실제로 다른 constraint를 가지는가?
만약 같다면 conditional rule이 작동 안 하는 것이다.
"""
from cpg_model.scenario_loader import ScenarioLoader
from collections import defaultdict

loader = ScenarioLoader()
auto = [s for s in loader.load_all_scenarios() 
        if hasattr(s, 'generation_method') and s.generation_method]

by_graph = defaultdict(lambda: {"trap": [], "normal": []})
for s in auto:
    key = "trap" if s.trap_scenario else "normal"
    by_graph[s.guideline_graph][key].append(s)

print("=== Trap vs Normal Differentiation ===")
problems = []

for g in sorted(by_graph.keys()):
    traps = by_graph[g]["trap"]
    normals = by_graph[g]["normal"]
    
    if not traps or not normals:
        continue
    
    # 각 trap에 대해: 이 trap만의 고유 forbidden이 있는가?
    normal_forbidden_union = set()
    for n in normals:
        normal_forbidden_union.update(n.forbidden_actions or [])
    
    trap_unique_count = 0
    for t in traps:
        trap_forbidden = set(t.forbidden_actions or [])
        unique_to_trap = trap_forbidden - normal_forbidden_union
        if unique_to_trap:
            trap_unique_count += 1
    
    diff_pct = trap_unique_count / len(traps) * 100 if traps else 0
    status = "OK" if diff_pct > 50 else "PROBLEM"
    
    print(f"  {g}: {trap_unique_count}/{len(traps)} traps have unique forbidden ({diff_pct:.0f}%) [{status}]")
    
    if status == "PROBLEM":
        problems.append(g)

if problems:
    print(f"\nPROBLEM GRAPHS (trap not differentiated): {problems}")
    print("These graphs' conditional rules may not be creating meaningful trap scenarios")
else:
    print(f"\nAll graphs show trap differentiation")
```

---

## 실행 순서

1. Part 1 (코드 테스트) 전체 실행 → 결과 보고
2. Part 2 (시나리오 내용 검증) 전체 실행 → 결과 보고
3. Part 3 (통계 검증) 전체 실행 → 결과 보고
4. Part 2의 scenario sample 처음 5개를 이 채팅에 출력

**각 Part의 실패 항목을 명시적으로 보고하라. 통과만 보고하지 말고 실패한 것의 상세도 보여달라.**