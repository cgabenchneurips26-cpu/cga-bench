# Task: PatientGenerator 확장 — Pathway Normal + Value Variation

## 목적

PatientGenerator에 2개 생성 축을 추가하여 framework의 시나리오 생성 능력을 완성한다.
- **Pathway Normal**: 같은 graph에서 다른 경로를 타는 baseline 시나리오
- **Value Variation**: 같은 rule에서 다른 값(경계, 극단)으로 trap 시나리오

추가로 cardiogenic shock expected=41 문제도 수정한다.

## Part 1: Pathway Normal 생성

### 개념

현재 normal 시나리오는 "어떤 conditional rule도 trigger하지 않는 환자"로 정의되어 있어서, 같은 graph의 normal은 전부 동일하게 취급된다(triggered_rules=[]). 

하지만 CPG graph에는 여러 pathway가 있고, patient_activation_condition에 따라 활성화되는 node가 다르다. 각 pathway 조합이 **서로 다른 expected_actions set**을 만들므로, 각각이 고유한 baseline 시나리오다.

### Step 1.1: 기존 코드 확인

PatientGenerator의 현재 dedup 로직을 확인하라:

```bash
grep -n "deduplicate\|triggered_rules" cpg_model/patient_generator.py
```

현재 dedup 기준: `frozenset(s.triggered_rules)` → normal은 전부 `frozenset()` → 1개만 남음.

### Step 1.2: PathwayAnalyzer 구현

`cpg_model/patient_generator.py`에 추가:

```python
class PathwayAnalyzer:
    """
    Graph의 node들을 patient_activation_condition 기준으로 분석하여
    가능한 pathway 조합을 열거한다.
    """
    
    def __init__(self, engine: ConstraintDerivationEngine):
        self.engine = engine
    
    def find_pathway_combinations(self, graph: dict) -> List[dict]:
        """
        Graph에서 의미있는 pathway 조합을 찾아
        각 조합에 해당하는 patient context를 생성.
        
        Returns: [
            {
                "pathway_id": "ischemic_tpa",
                "description": "Ischemic stroke, tPA eligible",
                "active_nodes": ["initial_assessment", "administer_iv_tpa", ...],
                "patient_context_overrides": {
                    "comorbidities": ["acute_ischemic_stroke"],
                    "presentation": {"symptom_onset_hours": 2},
                    ...
                }
            },
            ...
        ]
        """
        nodes = graph.get("nodes", {})
        
        # 1. Conditional node 수집
        conditional_nodes = []
        always_active_nodes = []
        
        for node_id, node in nodes.items():
            cond = node.get("patient_activation_condition", "True").strip()
            if cond in ("True", ""):
                always_active_nodes.append(node_id)
            elif cond == "False":
                continue  # 항상 비활성
            else:
                conditional_nodes.append({
                    "node_id": node_id,
                    "condition": cond,
                    "expected_actions": node.get("expected_actions", []),
                    "description": node.get("description", ""),
                })
        
        if not conditional_nodes:
            # Pathway 분기 없음 → 단일 normal만 가능
            return [{"pathway_id": "default", "description": "Single pathway", 
                     "active_nodes": always_active_nodes, "patient_context_overrides": {}}]
        
        # 2. Condition에서 사용하는 변수별로 그룹화
        #    같은 변수를 쓰는 node들은 상호 배타적 (하나만 활성화)
        groups = self._group_by_decision_variable(conditional_nodes)
        
        # 3. 각 그룹에서 하나씩 선택하는 조합 생성
        #    그룹 A: [ischemic, hemorrhagic]
        #    그룹 B: [tpa_eligible, thrombectomy, late_presenter]
        #    → A×B 조합 (단, 논리적으로 가능한 것만)
        combinations = self._enumerate_valid_combinations(groups)
        
        # 4. 각 조합에 대해 patient context override 생성
        pathways = []
        for combo in combinations:
            pathway = self._combo_to_pathway(combo, always_active_nodes, graph)
            if pathway:
                pathways.append(pathway)
        
        return pathways
    
    def _group_by_decision_variable(self, conditional_nodes: list) -> dict:
        """
        Condition이 같은 변수를 참조하는 node들을 그룹화.
        
        예:
        - "'acute_ischemic_stroke' in patient.comorbidities" → group: "stroke_type"
        - "'intracerebral_hemorrhage' in patient.imaging" → group: "stroke_type"
        - "patient.presentation.symptom_onset_hours <= 4.5" → group: "onset_time"
        """
        import re
        
        groups = {}
        
        for cn in conditional_nodes:
            cond = cn["condition"]
            
            # 핵심 변수 추출
            group_key = self._extract_group_key(cond)
            
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(cn)
        
        return groups
    
    def _extract_group_key(self, condition: str) -> str:
        """
        Condition에서 결정 변수(group key) 추출.
        
        패턴 매칭:
        - "'X' in patient.comorbidities" → X를 포함하는 의미적 그룹
        - "patient.labs.X < N" → "labs.X"
        - "patient.presentation.X > N" → "presentation.X"
        """
        import re
        
        # 패턴 1: 'value' in patient.field
        in_match = re.search(r"'(\w+)'\s+in\s+patient\.(\w+)", condition)
        if in_match:
            value, field = in_match.groups()
            # 같은 field의 상호 배타적 값들을 그룹화
            # 예: 'acute_ischemic_stroke' in comorbidities vs 'intracerebral_hemorrhage' in imaging
            # → 이건 다른 field이므로 다른 그룹
            return f"{field}:{self._semantic_group(value)}"
        
        # 패턴 2: patient.X.Y < N 또는 > N
        comp_match = re.search(r"patient\.(\w+(?:\.\w+)*)\s*[<>=]", condition)
        if comp_match:
            return comp_match.group(1)
        
        return f"other:{hash(condition) % 1000}"
    
    def _semantic_group(self, value: str) -> str:
        """
        값의 의미적 그룹 분류.
        예: acute_ischemic_stroke, intracerebral_hemorrhage → "stroke_type"
        """
        stroke_types = ["acute_ischemic_stroke", "intracerebral_hemorrhage", "hemorrhagic_stroke", 
                       "subarachnoid_hemorrhage", "wake_up_stroke"]
        hf_types = ["hfref", "hfpef", "hfmref", "adhf", "cardiogenic_shock"]
        aki_stages = ["aki_stage_1", "aki_stage_2", "aki_stage_3"]
        
        if value in stroke_types:
            return "stroke_type"
        if value in hf_types:
            return "hf_type"
        if value in aki_stages:
            return "aki_stage"
        
        return value
    
    def _enumerate_valid_combinations(self, groups: dict) -> list:
        """
        각 그룹에서 하나씩 선택하는 조합 열거.
        논리적으로 불가능한 조합은 제외.
        """
        from itertools import product
        
        group_lists = list(groups.values())
        
        if not group_lists:
            return [()]
        
        # 각 그룹에 "none" 옵션 추가 (이 그룹의 어떤 node도 활성화 안 됨)
        group_options = []
        for group in group_lists:
            options = group + [None]  # None = 이 그룹 비활성
            group_options.append(options)
        
        combos = list(product(*group_options))
        
        # 전부 None인 조합 제외 (아무 pathway도 안 타는 건 의미 없음)
        combos = [c for c in combos if any(x is not None for x in c)]
        
        # 논리적 충돌 제거 (예: ischemic + hemorrhagic 동시 활성)
        valid = []
        for combo in combos:
            active_nodes = [n for n in combo if n is not None]
            if not self._has_logical_conflict(active_nodes):
                valid.append(combo)
        
        return valid
    
    def _has_logical_conflict(self, active_nodes: list) -> bool:
        """
        활성 node 간 논리적 충돌 여부.
        예: ischemic stroke node + hemorrhagic stroke node → 충돌
        """
        node_ids = [n["node_id"] for n in active_nodes]
        
        # 알려진 충돌 쌍
        conflicts = [
            ({"administer_iv_tpa", "tpa_pathway"}, {"hemorrhagic_stroke_management", "ich_management"}),
            ({"hfref_gdmt"}, {"cardiogenic_shock_management"}),
            # 필요 시 추가
        ]
        
        node_set = set(node_ids)
        for group_a, group_b in conflicts:
            if node_set & group_a and node_set & group_b:
                return True
        
        return False
    
    def _combo_to_pathway(self, combo: tuple, always_active: list, graph: dict) -> dict:
        """
        조합을 pathway 정의로 변환.
        각 활성 node의 condition에서 patient context를 역추론.
        """
        active_nodes = always_active.copy()
        patient_overrides = {}
        descriptions = []
        
        for node in combo:
            if node is None:
                continue
            active_nodes.append(node["node_id"])
            descriptions.append(node.get("description", node["node_id"]))
            
            # condition에서 patient context 역추론
            overrides = self._condition_to_patient_context(node["condition"])
            self._merge_overrides(patient_overrides, overrides)
        
        pathway_id = "_".join(n["node_id"][:15] for n in combo if n is not None)[:60]
        
        return {
            "pathway_id": pathway_id,
            "description": " + ".join(descriptions[:3]),
            "active_nodes": active_nodes,
            "patient_context_overrides": patient_overrides,
        }
    
    def _condition_to_patient_context(self, condition: str) -> dict:
        """
        Condition string에서 이를 만족시키는 patient context를 역추론.
        
        "'acute_ischemic_stroke' in patient.comorbidities"
        → {"comorbidities": ["acute_ischemic_stroke"]}
        
        "patient.presentation.symptom_onset_hours <= 4.5"
        → {"presentation": {"symptom_onset_hours": 3.0}}
        
        "patient.labs.ph < 7.0"
        → {"labs": {"ph": 6.85}}
        """
        import re
        overrides = {}
        
        # 패턴 1: 'value' in patient.field
        for match in re.finditer(r"'(\w+)'\s+in\s+patient\.(\w+)", condition):
            value, field = match.groups()
            if field not in overrides:
                overrides[field] = []
            if isinstance(overrides[field], list):
                overrides[field].append(value)
        
        # 패턴 2: patient.X.Y < N → Y = N * 0.85 (safely below)
        for match in re.finditer(r"patient\.(\w+)\.(\w+)\s*<\s*([\d.]+)", condition):
            field, subfield, threshold = match.groups()
            threshold = float(threshold)
            if field not in overrides:
                overrides[field] = {}
            overrides[field][subfield] = round(threshold * 0.85, 2)
        
        # 패턴 3: patient.X.Y <= N
        for match in re.finditer(r"patient\.(\w+)\.(\w+)\s*<=\s*([\d.]+)", condition):
            field, subfield, threshold = match.groups()
            threshold = float(threshold)
            if field not in overrides:
                overrides[field] = {}
            overrides[field][subfield] = round(threshold * 0.9, 2)
        
        # 패턴 4: patient.X.Y > N → Y = N * 1.15
        for match in re.finditer(r"patient\.(\w+)\.(\w+)\s*>\s*([\d.]+)", condition):
            field, subfield, threshold = match.groups()
            threshold = float(threshold)
            if field not in overrides:
                overrides[field] = {}
            overrides[field][subfield] = round(threshold * 1.15, 2)
        
        # 패턴 5: patient.X.Y >= N
        for match in re.finditer(r"patient\.(\w+)\.(\w+)\s*>=\s*([\d.]+)", condition):
            field, subfield, threshold = match.groups()
            threshold = float(threshold)
            if field not in overrides:
                overrides[field] = {}
            overrides[field][subfield] = round(threshold * 1.1, 2)
        
        return overrides
    
    def _merge_overrides(self, target: dict, source: dict):
        """두 override dict를 병합"""
        for key, value in source.items():
            if key not in target:
                target[key] = value
            elif isinstance(target[key], list) and isinstance(value, list):
                target[key].extend(v for v in value if v not in target[key])
            elif isinstance(target[key], dict) and isinstance(value, dict):
                target[key].update(value)
```

### Step 1.3: PatientGenerator에 Pathway 생성 통합

```python
class PatientGenerator:
    
    def __init__(self, engine):
        self.engine = engine
        self.pathway_analyzer = PathwayAnalyzer(engine)
        # ... 기존 코드 유지
    
    def generate_from_graph(self, graph: dict) -> List[GeneratedScenario]:
        scenarios = []
        graph_id = graph["graph_id"]
        
        # === 기존: single-rule trigger/normal + combinatorial ===
        # ... (기존 코드 유지) ...
        
        # === 신규: Pathway-based normal 시나리오 ===
        pathway_scenarios = self._generate_pathway_normals(graph)
        scenarios.extend(pathway_scenarios)
        
        # === Deduplication 개선 ===
        scenarios = self._deduplicate_v2(scenarios)
        
        return scenarios
    
    def _generate_pathway_normals(self, graph: dict) -> List[GeneratedScenario]:
        """
        Graph의 pathway 조합별로 normal(baseline) 시나리오 생성.
        각 pathway는 서로 다른 expected_actions set을 가진다.
        """
        graph_id = graph["graph_id"]
        pathways = self.pathway_analyzer.find_pathway_combinations(graph)
        
        scenarios = []
        for pw in pathways:
            # Base patient + pathway overrides
            base = self._get_base_patient(graph_id)
            self._apply_overrides(base, pw["patient_context_overrides"])
            
            # Derive constraints
            derived = self.engine.derive(graph, base, f"{graph_id}_pathway_{pw['pathway_id']}")
            
            # Expected actions 추출
            expected = self._extract_expected(derived)
            forbidden = self._extract_forbidden(derived)
            
            if not expected:
                continue  # expected 없는 pathway는 스킵
            
            scenarios.append(GeneratedScenario(
                scenario_id=f"{self._graph_to_prefix(graph_id)}_pathway_{pw['pathway_id']}",
                guideline_graph=graph_id,
                patient=base,
                expected_actions=expected,
                forbidden_actions=forbidden,
                derived_constraints=derived.to_yaml() if hasattr(derived, 'to_yaml') else {},
                trap_scenario=False,
                trap_description="",
                triggered_rules=[],
                generation_method="auto:pathway_normal",
                pathway_id=pw["pathway_id"],
                pathway_description=pw["description"],
            ))
        
        return scenarios
    
    def _apply_overrides(self, patient: dict, overrides: dict):
        """Patient context에 pathway override 적용"""
        for key, value in overrides.items():
            if isinstance(value, list):
                existing = patient.get(key, [])
                if isinstance(existing, list):
                    patient[key] = existing + [v for v in value if v not in existing]
                else:
                    patient[key] = value
            elif isinstance(value, dict):
                existing = patient.get(key, {})
                if isinstance(existing, dict):
                    existing.update(value)
                    patient[key] = existing
                else:
                    patient[key] = value
            else:
                patient[key] = value
    
    def _deduplicate_v2(self, scenarios: List[GeneratedScenario]) -> List[GeneratedScenario]:
        """
        개선된 dedup: triggered_rules가 아닌 (expected_actions set + forbidden_actions set)으로 비교.
        같은 expected+forbidden이면 같은 시나리오로 취급.
        """
        seen = set()
        unique = []
        
        for s in scenarios:
            key = (
                frozenset(s.expected_actions or []),
                frozenset(s.forbidden_actions or []),
                frozenset(getattr(s, 'triggered_rules', []) or [])
            )
            if key not in seen:
                seen.add(key)
                unique.append(s)
        
        return unique
```

---

## Part 2: Value Variation 생성

### 개념

같은 conditional rule이지만 **다른 값**으로 trigger하는 시나리오.
임상적으로 중요한 이유: K+=3.2(경계)에서의 오류와 K+=1.5(극단)에서의 오류는 severity가 다르다.

### Step 2.1: ValueVariationGenerator 구현

```python
class ValueVariationGenerator:
    """
    Numeric conditional rule에서 value variation 시나리오를 생성.
    
    rule: "patient.labs.potassium < 3.3"
    trigger_range: {min: 1.5, max: 3.2}
    
    → boundary: K+=3.2 (threshold 바로 아래 — 경계 테스트)
    → extreme: K+=1.5 (범위 하단 — 극단 테스트)
    → 기존 single_trigger: K+=random(1.5, 3.2) (중간값)
    """
    
    def __init__(self, engine: ConstraintDerivationEngine):
        self.engine = engine
    
    def generate_variations(self, rule: dict, base_patient: dict, graph: dict) -> List[dict]:
        """
        하나의 numeric rule에서 boundary + extreme variation 생성.
        
        Returns: [(patient_context, variation_type, value_description), ...]
        """
        trigger_range = rule.get("trigger_range", {})
        variations = []
        
        for var_path, range_spec in trigger_range.items():
            rtype = range_spec.get("type", "float")
            
            if rtype not in ("float", "int"):
                continue  # list_contains 등은 value variation 불가
            
            rmin = range_spec.get("min")
            rmax = range_spec.get("max")
            
            if rmin is None or rmax is None:
                continue
            
            # Boundary value: threshold 바로 아래/위
            # rule condition이 "< X"이면 boundary = X - epsilon
            threshold = self._extract_threshold(rule["condition"], var_path)
            
            if threshold is not None:
                # Boundary: threshold에서 살짝 안쪽
                if rtype == "float":
                    boundary_val = round(threshold - 0.1, 1) if "<" in rule["condition"] else round(threshold + 0.1, 1)
                    # boundary가 range 안에 있는지 확인
                    if rmin <= boundary_val <= rmax:
                        variations.append({
                            "type": "boundary",
                            "var_path": var_path,
                            "value": boundary_val,
                            "description": f"{var_path.split('.')[-1]}={boundary_val} (near threshold {threshold})"
                        })
                elif rtype == "int":
                    boundary_val = int(threshold - 1) if "<" in rule["condition"] else int(threshold + 1)
                    if rmin <= boundary_val <= rmax:
                        variations.append({
                            "type": "boundary",
                            "var_path": var_path,
                            "value": boundary_val,
                            "description": f"{var_path.split('.')[-1]}={boundary_val} (near threshold {threshold})"
                        })
            
            # Extreme value: range의 끝쪽
            if rtype == "float":
                extreme_val = round(rmin + (rmax - rmin) * 0.1, 1)  # 하위 10%
            else:
                extreme_val = rmin
            
            if extreme_val != boundary_val if 'boundary_val' in dir() else True:
                variations.append({
                    "type": "extreme",
                    "var_path": var_path,
                    "value": extreme_val,
                    "description": f"{var_path.split('.')[-1]}={extreme_val} (extreme low)"
                })
        
        return variations
    
    def _extract_threshold(self, condition: str, var_path: str) -> float:
        """
        Condition string에서 비교 threshold 추출.
        "patient.labs.potassium < 3.3" → 3.3
        """
        import re
        # var_path의 마지막 부분으로 검색
        var_name = var_path.split(".")[-1]
        
        pattern = rf"patient\.\w+\.{var_name}\s*[<>=]+\s*([\d.]+)"
        match = re.search(pattern, condition)
        if match:
            return float(match.group(1))
        
        return None
```

### Step 2.2: PatientGenerator에 Value Variation 통합

```python
class PatientGenerator:
    
    def __init__(self, engine):
        self.engine = engine
        self.pathway_analyzer = PathwayAnalyzer(engine)
        self.value_generator = ValueVariationGenerator(engine)
        # ... 기존
    
    def generate_from_graph(self, graph: dict) -> List[GeneratedScenario]:
        scenarios = []
        graph_id = graph["graph_id"]
        all_rules = self._collect_all_rules(graph)
        
        for rule in all_rules:
            # === 기존: single trigger + normal ===
            # ... 기존 코드 유지 ...
            
            # === 신규: value variation ===
            value_scenarios = self._generate_value_variations(rule, graph)
            scenarios.extend(value_scenarios)
        
        # === 기존: combinatorial ===
        # ...
        
        # === 신규: pathway normals ===
        pathway_scenarios = self._generate_pathway_normals(graph)
        scenarios.extend(pathway_scenarios)
        
        # === Dedup ===
        scenarios = self._deduplicate_v2(scenarios)
        
        return scenarios
    
    def _generate_value_variations(self, rule: dict, graph: dict) -> List[GeneratedScenario]:
        """
        Numeric rule에서 boundary + extreme variation 시나리오 생성.
        """
        graph_id = graph["graph_id"]
        base = self._get_base_patient(graph_id)
        
        variations = self.value_generator.generate_variations(rule, base, graph)
        
        scenarios = []
        for var in variations:
            import copy
            patient = copy.deepcopy(base)
            
            # trigger_range의 다른 변수는 기존 trigger_patient 로직으로 설정
            trigger_range = rule.get("trigger_range", {})
            for var_path, range_spec in trigger_range.items():
                if var_path == var["var_path"]:
                    # 이 변수는 variation 값 사용
                    self._set_nested(patient, var_path.replace("patient.", ""), var["value"])
                else:
                    # 나머지는 기존 sampling
                    value = self._sample_value(range_spec)
                    if value is not None:
                        self._set_nested(patient, var_path.replace("patient.", ""), value)
            
            # condition이 실제로 fire하는지 검증
            if not self.engine._evaluate_condition(rule["condition"], patient):
                continue
            
            derived = self.engine.derive(graph, patient, f"val_{var['type']}_{rule['rule_id']}")
            expected = self._extract_expected(derived)
            forbidden = self._extract_forbidden(derived)
            
            scenarios.append(GeneratedScenario(
                scenario_id=f"{self._graph_to_prefix(graph_id)}_trap_{self._rule_to_suffix(rule['rule_id'])}_{var['type']}",
                guideline_graph=graph_id,
                patient=patient,
                expected_actions=expected,
                forbidden_actions=forbidden,
                derived_constraints=derived.to_yaml() if hasattr(derived, 'to_yaml') else {},
                trap_scenario=True,
                trap_description=f"{rule.get('description', '')} [{var['description']}]",
                triggered_rules=[rule["rule_id"]],
                generation_method=f"auto:value_{var['type']}",
            ))
        
        return scenarios
```

---

## Part 3: Cardiogenic Shock expected=41 수정

```bash
# 먼저 어떤 node가 과다 활성화되는지 확인
python -c "
from cpg_model.constraint_derivation import ConstraintDerivationEngine
import yaml

engine = ConstraintDerivationEngine()
with open('cpg_model/graphs/aha_heart_failure_2022.yaml') as f:
    graph = yaml.safe_load(f)

# cardiogenic shock 환자
patient = {
    'comorbidities': ['cardiogenic_shock', 'hfref'],
    'vitals': {'sbp': 75, 'hr': 120, 'spo2': 88},
    'labs': {'bnp': 5000, 'lactate': 6.0, 'potassium': 4.5},
    'allergies': [], 'medications': [],
    'presentation': {}, 'history': [], 'exam_findings': []
}

result = engine.derive(graph, patient, 'test_cs')
expected = []
for attr in ['expected', 'required']:
    if hasattr(result, attr):
        for c in getattr(result, attr):
            for a in c.actions:
                src = c.provenance.split(':node:')[1].split(':')[0] if ':node:' in c.provenance else '?'
                expected.append((a, src))

print(f'Total expected: {len(expected)}')
by_node = {}
for a, n in expected:
    by_node.setdefault(n, []).append(a)
for n, actions in sorted(by_node.items(), key=lambda x: -len(x[1])):
    print(f'  {n}: {len(actions)} actions')
    for a in actions[:5]:
        print(f'    - {a}')
    if len(actions) > 5:
        print(f'    ... +{len(actions)-5} more')
"
```

cardiogenic_shock_management node의 patient_activation_condition을 더 세분화하거나,
이 node의 expected_actions를 core actions로 줄여라.

목표: cardiogenic shock pathway에서도 expected ≤ 30.

---

## Part 4: 검증

### 전체 재생성 + 통계

```bash
python scripts/generate_all_scenarios.py

python -c "
from cpg_model.scenario_loader import ScenarioLoader
from collections import Counter

loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()

auto = [s for s in scenarios if hasattr(s, 'generation_method') and s.generation_method]
manual = [s for s in scenarios if not (hasattr(s, 'generation_method') and s.generation_method)]

print(f'Manual: {len(manual)}')
print(f'Auto: {len(auto)}')
print(f'Total: {len(scenarios)}')

# 생성 방법별 분포
method_dist = Counter(getattr(s, 'generation_method', 'manual') for s in scenarios)
print(f'\nGeneration method distribution:')
for m, c in method_dist.most_common():
    print(f'  {m}: {c}')

# Expected 통계
ea = [len(s.expected_actions) for s in auto]
print(f'\nAuto expected: min={min(ea)}, max={max(ea)}, mean={sum(ea)/len(ea):.1f}')

# Pathway normal 수
pathway_normals = [s for s in auto if getattr(s, 'generation_method', '') == 'auto:pathway_normal']
print(f'Pathway normals: {len(pathway_normals)}')

# Value variations 수
value_vars = [s for s in auto if 'value_' in str(getattr(s, 'generation_method', ''))]
print(f'Value variations: {len(value_vars)}')

# Graph별 분포
gc = Counter(s.guideline_graph for s in scenarios)
print(f'\nGraph distribution:')
for g, c in gc.most_common():
    methods = Counter(getattr(s, 'generation_method', 'manual') for s in scenarios if s.guideline_graph == g)
    print(f'  {g}: {c} total — {dict(methods)}')

assert max(ea) <= 30, f'Still have over-activated: max={max(ea)}'
print(f'\nExpected max <= 30: PASS')
"
```

### Pathway diversity 확인

```bash
python -c "
from cpg_model.scenario_loader import ScenarioLoader

loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()

pathway_normals = [s for s in scenarios if getattr(s, 'generation_method', '') == 'auto:pathway_normal']

if not pathway_normals:
    print('WARNING: No pathway normals generated')
else:
    # 같은 graph의 pathway normal들이 서로 다른 expected를 갖는지
    from collections import defaultdict
    by_graph = defaultdict(list)
    for s in pathway_normals:
        by_graph[s.guideline_graph].append(s)
    
    for g, pw_scenarios in sorted(by_graph.items()):
        if len(pw_scenarios) < 2:
            continue
        
        # expected_actions의 pairwise overlap
        ea_sets = [frozenset(s.expected_actions) for s in pw_scenarios]
        
        all_same = all(s == ea_sets[0] for s in ea_sets)
        if all_same:
            print(f'  WARNING: {g} — all {len(pw_scenarios)} pathway normals have identical expected_actions!')
        else:
            overlaps = []
            for i in range(len(ea_sets)):
                for j in range(i+1, len(ea_sets)):
                    overlap = len(ea_sets[i] & ea_sets[j]) / max(len(ea_sets[i] | ea_sets[j]), 1)
                    overlaps.append(overlap)
            avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0
            print(f'  {g}: {len(pw_scenarios)} pathways, avg overlap={avg_overlap:.0%}')
    
    print(f'Pathways with diversity > 0: {sum(1 for g, ps in by_graph.items() if len(ps) >= 2)}')
"
```

### Value variation 확인

```bash
python -c "
from cpg_model.scenario_loader import ScenarioLoader

loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()

value_vars = [s for s in scenarios if 'value_' in str(getattr(s, 'generation_method', ''))]

print(f'Value variation scenarios: {len(value_vars)}')

boundary = [s for s in value_vars if 'boundary' in str(getattr(s, 'generation_method', ''))]
extreme = [s for s in value_vars if 'extreme' in str(getattr(s, 'generation_method', ''))]
print(f'  Boundary: {len(boundary)}')
print(f'  Extreme: {len(extreme)}')

# 샘플 출력
for s in boundary[:3]:
    print(f'\n  {s.scenario_id}:')
    print(f'    Trap: {s.trap_description[:100]}')
"
```

### 전체 regression

```bash
python -m pytest tests/ -x -q
```

---

## Completion Criteria

- [ ] PathwayAnalyzer 구현 + 통합
- [ ] ValueVariationGenerator 구현 + 통합
- [ ] Dedup v2 (expected+forbidden 기반)로 교체
- [ ] Cardiogenic shock expected ≤ 30
- [ ] Pathway normal 시나리오 ≥ 25개 (유의미한 diversity 있는 것만)
- [ ] Value variation 시나리오 ≥ 100개
- [ ] 전체 auto 시나리오 수 증가 (기존 313 → 예상 ~500)
- [ ] Expected max ≤ 30 유지
- [ ] 같은 graph의 pathway normals가 서로 다른 expected_actions를 가짐
- [ ] 194+ 기존 테스트 통과
- [ ] 최종 통계 출력:
  - Total scenarios (manual + auto)
  - Generation method 분포
  - Graph별 분포
  - 실용적 최대 대비 활용률