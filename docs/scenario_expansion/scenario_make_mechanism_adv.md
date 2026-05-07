# Task: 시나리오 생성 가능 최대 수 정밀 계산

## 목적

현재 시스템에서 **이론적으로 만들 수 있는 모든 의미있는 시나리오 variation**을 정확히 계산한다.
실제로 전부 만들 필요는 없지만, "우리 framework는 N개까지 생성 가능하며, 그 중 M개를 선별 실행했다"라고 논문에 쓸 수 있어야 한다.

## 분석 1: Pathway Variation 계산

각 graph에서 `patient_activation_condition`이 상호 배타적인 node 그룹(pathway)을 식별한다.
각 pathway 조합이 하나의 고유한 "normal" 시나리오 유형이다.

```python
# scripts/count_pathway_variations.py
"""
각 graph의 node들을 patient_activation_condition 기준으로 분석.
상호 배타적 pathway를 식별하고, pathway 조합 수를 계산.
"""
from pathlib import Path
import yaml
from collections import defaultdict

print("=" * 90)
print("PATHWAY VARIATION ANALYSIS")
print("=" * 90)

total_pathways = 0
total_pathway_scenarios = 0

for graph_path in sorted(Path("cpg_model/graphs/").glob("*.yaml")):
    with open(graph_path) as f:
        graph = yaml.safe_load(f)
    
    graph_id = graph.get("graph_id", graph_path.stem)
    nodes = graph.get("nodes", {})
    
    # Node를 activation condition으로 분류
    always_active = []       # condition == "True" 또는 없음
    conditional_nodes = []   # patient context에 따라 활성/비활성
    
    for node_id, node in nodes.items():
        cond = node.get("patient_activation_condition", "True").strip()
        expected = node.get("expected_actions", [])
        
        if cond == "True" or cond == "":
            always_active.append({
                "node_id": node_id,
                "expected": expected,
                "condition": cond
            })
        else:
            conditional_nodes.append({
                "node_id": node_id,
                "expected": expected,
                "condition": cond
            })
    
    # Conditional node들 중 상호 배타적 그룹 찾기
    # (같은 변수를 다른 값으로 분기하는 node들)
    # 예: 'acute_ischemic_stroke' in patient.comorbidities vs 'intracerebral_hemorrhage' in patient.imaging
    
    # 단순화: conditional node 각각이 독립적 on/off라고 가정
    # 실제 pathway 수 = 2^(독립 조건 수) 중 유효한 조합
    # 하지만 실제로는 상호 배타적이므로 합이 아닌 선택
    
    # 상호 배타적 그룹 식별 (같은 변수 사용)
    condition_groups = defaultdict(list)
    for cn in conditional_nodes:
        # condition에서 사용하는 주요 변수 추출
        cond = cn["condition"]
        # 단순 heuristic: 첫 번째 patient.* 변수
        main_var = extract_main_variable(cond)
        condition_groups[main_var].append(cn)
    
    # 각 그룹 내에서는 하나만 선택 (상호 배타)
    # 그룹 간에는 독립적으로 조합
    group_sizes = [len(g) + 1 for g in condition_groups.values()]  # +1 for "none active"
    
    from functools import reduce
    from operator import mul
    pathway_combinations = reduce(mul, group_sizes, 1) if group_sizes else 1
    
    # always_active expected 수
    always_expected = sum(len(n["expected"]) for n in always_active)
    
    total_pathways += len(conditional_nodes)
    total_pathway_scenarios += pathway_combinations
    
    print(f"\n{graph_id}:")
    print(f"  Always-active nodes: {len(always_active)} ({always_expected} expected actions)")
    print(f"  Conditional nodes: {len(conditional_nodes)}")
    print(f"  Condition groups: {len(condition_groups)}")
    for var, group in condition_groups.items():
        print(f"    {var}: {len(group)} options → {[n['node_id'] for n in group]}")
    print(f"  Pathway combinations: {pathway_combinations}")

print(f"\n{'=' * 90}")
print(f"Total pathway-based normal scenario variations: {total_pathway_scenarios}")

def extract_main_variable(condition):
    """condition string에서 주요 분기 변수 추출"""
    # "'acute_ischemic_stroke' in patient.comorbidities" → "patient.comorbidities:ischemic"
    # "patient.labs.ph < 7.0" → "patient.labs.ph"
    # "patient.presentation.symptom_onset_hours <= 4.5" → "patient.presentation.symptom_onset_hours"
    import re
    
    # patient.* 변수 찾기
    vars_found = re.findall(r'patient\.\w+(?:\.\w+)*', condition)
    if vars_found:
        return vars_found[0]
    
    # 'something' in patient.* 패턴
    in_match = re.search(r"in patient\.(\w+)", condition)
    if in_match:
        return f"patient.{in_match.group(1)}"
    
    return "unknown"
```

## 분석 2: 전체 Variation 합산

```python
# scripts/count_total_scenario_potential.py
"""
모든 variation 축을 합산하여 이론적 최대 시나리오 수 계산.
"""
from pathlib import Path
import yaml
from math import comb

print("=" * 90)
print("TOTAL SCENARIO GENERATION POTENTIAL")
print("=" * 90)

grand_total = {
    "single_trigger": 0,
    "pathway_normal": 0,
    "value_variation": 0,
    "combo_2": 0,
    "combo_3": 0,
}

for graph_path in sorted(Path("cpg_model/graphs/").glob("*.yaml")):
    with open(graph_path) as f:
        graph = yaml.safe_load(f)
    
    graph_id = graph.get("graph_id", graph_path.stem)
    
    # Conditional rules
    rules = []
    for node_id, node in graph.get("nodes", {}).items():
        for rule in node.get("conditional_rules", []):
            rules.append(rule)
    n_rules = len(rules)
    
    # Pathway variations (conditional nodes)
    nodes = graph.get("nodes", {})
    conditional_nodes = [
        n for n in nodes.values() 
        if n.get("patient_activation_condition", "True").strip() not in ("True", "False", "")
    ]
    # 각 conditional node는 독립적 on/off (보수적 추정)
    # 실제로는 상호 배타적이므로 이보다 적음
    n_pathways = max(len(set(
        extract_pathway_group(n.get("patient_activation_condition", ""))
        for n in conditional_nodes
    )), 1)
    
    # Numeric rules (value variation 가능)
    numeric_rules = [r for r in rules if any(
        op in r.get("condition", "") for op in ["<", ">", "<=", ">="]
    )]
    
    # 이 graph의 variation
    single_trigger = n_rules                                    # rule당 1 trigger
    pathway_normal = n_pathways                                 # pathway 조합 수
    value_var = len(numeric_rules) * 2                          # boundary + extreme
    c2 = comb(n_rules, 2) if n_rules >= 2 else 0               # 2-rule 조합
    c3 = comb(n_rules, 3) if n_rules >= 3 else 0               # 3-rule 조합
    
    total_graph = single_trigger + pathway_normal + value_var + c2
    # c3은 너무 많으므로 "이론적 최대"에만 포함
    
    grand_total["single_trigger"] += single_trigger
    grand_total["pathway_normal"] += pathway_normal
    grand_total["value_variation"] += value_var
    grand_total["combo_2"] += c2
    grand_total["combo_3"] += c3
    
    print(f"\n{graph_id}:")
    print(f"  Rules: {n_rules}")
    print(f"  Pathways: {n_pathways}")
    print(f"  Single trigger: {single_trigger}")
    print(f"  Pathway normals: {pathway_normal}")
    print(f"  Value variations: {value_var}")
    print(f"  2-rule combos: {c2}")
    print(f"  3-rule combos: {c3}")
    print(f"  Practical total (excl. 3-rule): {total_graph}")

print(f"\n{'=' * 90}")
print(f"GRAND TOTAL ACROSS ALL 25 GRAPHS")
print(f"{'=' * 90}")

practical = (grand_total["single_trigger"] + grand_total["pathway_normal"] + 
             grand_total["value_variation"] + grand_total["combo_2"])
theoretical = practical + grand_total["combo_3"]

print(f"""
  축 1 — Single-rule trigger:     {grand_total['single_trigger']:>6d}  (rule당 1개 trap)
  축 2 — Pathway normal:          {grand_total['pathway_normal']:>6d}  (pathway 조합별 1개 baseline)
  축 3 — Value variation:         {grand_total['value_variation']:>6d}  (numeric rule × 2 추가값)
  축 4 — 2-rule combinatorial:    {grand_total['combo_2']:>6d}  (rule 2개 동시 trigger)
  ─────────────────────────────────────────
  실용적 최대 (축 1-4):           {practical:>6d}
  
  축 5 — 3-rule combinatorial:    {grand_total['combo_3']:>6d}  (rule 3개 동시 trigger)
  ─────────────────────────────────────────
  이론적 최대 (축 1-5):           {theoretical:>6d}
  
  현재 생성:                      {313:>6d}  (auto)
  + 수동:                         {105:>6d}
  = 현재 총:                      {418:>6d}
  
  활용률 (현재/실용적):           {418/practical*100:>5.1f}%
""")

# 권장 생성 규모
print(f"""
  ┌─────────────────────┬────────┬─────────────┬──────────────┐
  │       규모          │ 시나리오│  Episodes    │ 실행 시간    │
  │                     │        │ (×5mod×3run) │ (4 GPU 병렬) │
  ├─────────────────────┼────────┼─────────────┼──────────────┤
  │ 현재                │ ~420   │ 6,300       │ ~4.5일       │
  │ 권장 (Pathway 추가) │ ~600   │ 9,000       │ ~6일         │
  │ 확장 (Value 추가)   │ ~800   │ 12,000      │ ~8일         │
  │ 최대 (2-combo 포함) │ ~2,000 │ 30,000      │ ~21일        │
  └─────────────────────┴────────┴─────────────┴──────────────┘
""")

def extract_pathway_group(condition):
    """condition에서 pathway 그룹 식별"""
    import re
    vars_found = re.findall(r'patient\.(\w+)', condition)
    return vars_found[0] if vars_found else "default"
```

## 분석 3: Normal 시나리오 다양화의 구체적 예시

```python
# scripts/show_normal_diversity_examples.py
"""
graph 3개를 골라서 pathway-based normal 시나리오가 얼마나 다른지 보여준다.
"""
from cpg_model.constraint_derivation import ConstraintDerivationEngine
import yaml

engine = ConstraintDerivationEngine()

# 예시 1: aha_stroke
print("=" * 80)
print("EXAMPLE: aha_stroke — Pathway-based Normal Diversity")
print("=" * 80)

with open("cpg_model/graphs/aha_stroke.yaml") as f:  # 실제 파일명에 맞게
    stroke_graph = yaml.safe_load(f)

stroke_normals = [
    {
        "name": "Ischemic + tPA eligible",
        "patient": {
            "age": 65, "sex": "M",
            "comorbidities": ["acute_ischemic_stroke", "hypertension"],
            "imaging": ["no_hemorrhage"],
            "presentation": {"symptom_onset_hours": 2, "nihss": 14},
            "vitals": {"sbp": 170, "dbp": 95, "hr": 88},
            "labs": {}, "allergies": [], "medications": [],
            "history": [], "exam_findings": []
        }
    },
    {
        "name": "Ischemic + thrombectomy (LVO)",
        "patient": {
            "age": 58, "sex": "F",
            "comorbidities": ["acute_ischemic_stroke", "lvo_confirmed", "atrial_fibrillation"],
            "imaging": ["lvo_on_cta"],
            "presentation": {"symptom_onset_hours": 8, "nihss": 18},
            "vitals": {"sbp": 160, "dbp": 90, "hr": 95},
            "labs": {}, "allergies": [], "medications": [],
            "history": [], "exam_findings": []
        }
    },
    {
        "name": "Hemorrhagic stroke (ICH)",
        "patient": {
            "age": 72, "sex": "M",
            "comorbidities": ["intracerebral_hemorrhage", "hypertension"],
            "imaging": ["intracerebral_hemorrhage"],
            "presentation": {"nihss": 20},
            "vitals": {"sbp": 210, "dbp": 120, "hr": 75},
            "labs": {}, "allergies": [], "medications": ["warfarin"],
            "history": [], "exam_findings": []
        }
    },
    {
        "name": "Wake-up stroke (extended window)",
        "patient": {
            "age": 60, "sex": "F",
            "comorbidities": ["acute_ischemic_stroke"],
            "imaging": ["favorable_perfusion_mismatch"],
            "presentation": {"symptom_onset_hours": 14, "nihss": 12, "last_known_well_unknown": True},
            "vitals": {"sbp": 155, "dbp": 85, "hr": 80},
            "labs": {}, "allergies": [], "medications": [],
            "history": [], "exam_findings": []
        }
    },
]

for normal in stroke_normals:
    result = engine.derive(stroke_graph, normal["patient"], f"stroke_normal_{normal['name']}")
    
    expected = []
    for attr in ['expected', 'required']:
        if hasattr(result, attr):
            expected.extend([a for c in getattr(result, attr) for a in c.actions])
    expected = list(dict.fromkeys(expected))
    
    forbidden = [a for c in result.forbidden for a in c.actions]
    forbidden = list(dict.fromkeys(forbidden))
    
    print(f"\n--- {normal['name']} ---")
    print(f"  Expected ({len(expected)}): {expected[:8]}{'...' if len(expected) > 8 else ''}")
    print(f"  Forbidden ({len(forbidden)}): {forbidden[:5]}{'...' if len(forbidden) > 5 else ''}")
    print(f"  → 이 pathway의 expected는 다른 pathway와 {'겹침' if len(expected) < 5 else '다름'}")

# 예시 2: ada_dka_management
print(f"\n{'=' * 80}")
print("EXAMPLE: ada_dka_management — Pathway-based Normal Diversity")
print("=" * 80)

with open("cpg_model/graphs/ada_dka_management.yaml") as f:
    dka_graph = yaml.safe_load(f)

dka_normals = [
    {
        "name": "Moderate DKA, normal K+",
        "patient": {
            "age": 35, "sex": "M",
            "labs": {"potassium": 4.2, "glucose": 450, "ph": 7.15, "bicarbonate": 10},
            "comorbidities": ["type_1_diabetes"],
            "allergies": [], "medications": [], "vitals": {"hr": 110, "sbp": 100},
            "presentation": {}, "history": [], "exam_findings": []
        }
    },
    {
        "name": "Severe DKA, pH < 7.0",
        "patient": {
            "age": 28, "sex": "F",
            "labs": {"potassium": 4.5, "glucose": 680, "ph": 6.85, "bicarbonate": 3},
            "comorbidities": ["type_1_diabetes"],
            "allergies": [], "medications": [], "vitals": {"hr": 130, "sbp": 85},
            "presentation": {}, "history": [], "exam_findings": []
        }
    },
    {
        "name": "DKA + pneumonia trigger",
        "patient": {
            "age": 55, "sex": "M",
            "labs": {"potassium": 3.8, "glucose": 520, "ph": 7.20, "bicarbonate": 12},
            "comorbidities": ["type_2_diabetes"],
            "allergies": [], "medications": [],
            "vitals": {"hr": 105, "sbp": 110, "temp": 39.2, "spo2": 92},
            "presentation": {"has_fever": True}, "history": [], "exam_findings": ["bilateral_crackles"]
        }
    },
]

for normal in dka_normals:
    result = engine.derive(dka_graph, normal["patient"], f"dka_normal_{normal['name']}")
    expected = []
    for attr in ['expected', 'required']:
        if hasattr(result, attr):
            expected.extend([a for c in getattr(result, attr) for a in c.actions])
    expected = list(dict.fromkeys(expected))
    
    print(f"\n--- {normal['name']} ---")
    print(f"  Expected ({len(expected)}): {expected[:8]}{'...' if len(expected) > 8 else ''}")
```

**위 3개 스크립트를 모두 실행하고 전체 출력을 보고하라.**