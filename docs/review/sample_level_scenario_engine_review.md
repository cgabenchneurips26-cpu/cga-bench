# Task: 회의적 감사 — "정말 맞는지" Sample-Level 검증

Aggregate 통계(689개, 100% differentiation, 0 contradiction)를 믿지 말고, **개별 시나리오를 열어서** 실제로 맞는지 확인한다.

모든 결과를 **raw로 출력**하라. 요약하지 말 것.

---

## Audit 1: Companion Rule이 실제로 작동하는가?

60개 companion rule을 추가했다고 했다. 그중 5개를 랜덤 추출하여 실제로 fire하는지 검증.

```python
# audit/audit_companion_rules.py
"""
companion rule 5개를 추출하여:
1. rule의 condition을 읽고
2. 해당 condition을 만족하는 시나리오를 찾고
3. 그 시나리오의 forbidden에 companion rule의 action이 실제로 포함되어 있는지 확인
"""
import yaml, random
from pathlib import Path
from cpg_model.constraint_derivation import ConstraintDerivationEngine

engine = ConstraintDerivationEngine()
random.seed(42)

# companion rule 수집
companions = []
for p in Path("cpg_model/graphs/").glob("*.yaml"):
    with open(p) as f:
        g = yaml.safe_load(f)
    for nid, node in g.get("nodes", {}).items():
        for rule in node.get("conditional_rules", []):
            if rule.get("skip_scenario_generation"):
                companions.append({
                    "graph": g["graph_id"],
                    "node": nid,
                    "rule": rule,
                    "graph_path": str(p),
                })

print(f"Total companion rules: {len(companions)}")
sample = random.sample(companions, min(5, len(companions)))

for comp in sample:
    print(f"\n{'='*70}")
    print(f"Graph: {comp['graph']}")
    print(f"Rule: {comp['rule']['rule_id']}")
    print(f"Condition: {comp['rule']['condition']}")
    print(f"Forbidden actions: {comp['rule']['effect']['actions']}")
    
    # 이 rule의 parent condition을 만족하는 시나리오 찾기
    from cpg_model.scenario_loader import ScenarioLoader
    loader = ScenarioLoader()
    
    matching_scenarios = []
    for s in loader.load_all_scenarios():
        if s.guideline_graph != comp["graph"]:
            continue
        patient = s.patient if isinstance(s.patient, dict) else vars(s.patient)
        try:
            fires = engine._evaluate_condition(comp["rule"]["condition"], patient)
        except:
            fires = False
        if fires:
            matching_scenarios.append(s)
    
    print(f"Scenarios where condition fires: {len(matching_scenarios)}")
    
    if matching_scenarios:
        s = matching_scenarios[0]
        forbidden_set = set(s.forbidden_actions or [])
        companion_actions = set(comp["rule"]["effect"]["actions"])
        present = companion_actions & forbidden_set
        missing = companion_actions - forbidden_set
        
        print(f"  Sample scenario: {s.scenario_id}")
        print(f"  Companion actions in forbidden: {sorted(present)}")
        print(f"  Companion actions MISSING from forbidden: {sorted(missing)}")
        
        if missing:
            print(f"  *** BUG: Companion rule fires but actions not in scenario forbidden! ***")
        else:
            print(f"  OK: All companion actions present")
    else:
        print(f"  WARNING: No scenario triggers this companion rule")
```

---

## Audit 2: "100% Differentiation" 직접 검증

verify_trap_differentiation.py의 결과를 믿지 말고 직접 계산.

```python
# audit/audit_differentiation_direct.py
"""
모든 trap 시나리오를 직접 열어서 같은 graph의 normal과 forbidden을 비교.
"""
from cpg_model.scenario_loader import ScenarioLoader
from collections import defaultdict

loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()

normal_fb = defaultdict(set)
for s in scenarios:
    if not s.trap_scenario:
        normal_fb[s.guideline_graph].update(s.forbidden_actions or [])

undiff = []
for s in scenarios:
    if not s.trap_scenario:
        continue
    trap_fb = set(s.forbidden_actions or [])
    normal = normal_fb.get(s.guideline_graph, set())
    unique = trap_fb - normal
    
    if not unique:
        undiff.append({
            "id": s.scenario_id,
            "graph": s.guideline_graph,
            "trap_fb_count": len(trap_fb),
            "normal_fb_count": len(normal),
            "overlap": len(trap_fb & normal),
        })

print(f"Undifferentiated traps: {len(undiff)}")
if undiff:
    for u in undiff[:20]:
        print(f"  {u['id']} ({u['graph']}): trap={u['trap_fb_count']}, normal={u['normal_fb_count']}, overlap={u['overlap']}")
else:
    print("CONFIRMED: 0 undifferentiated traps")
```

---

## Audit 3: 랜덤 시나리오 5개의 임상적 유효성 직접 검토

```python
# audit/audit_clinical_validity_random.py
"""
689개 중 5개를 랜덤 추출하여 전체 내용을 출력.
사람이 읽고 "이 시나리오가 임상적으로 말이 되는가" 판단할 수 있도록.
"""
import random
from cpg_model.scenario_loader import ScenarioLoader

random.seed(123)
loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()

# trap 3개 + normal 2개
traps = [s for s in scenarios if s.trap_scenario]
normals = [s for s in scenarios if not s.trap_scenario]

sample = random.sample(traps, 3) + random.sample(normals, 2)

for s in sample:
    p = s.patient if isinstance(s.patient, dict) else vars(s.patient)
    print(f"\n{'='*80}")
    print(f"ID: {s.scenario_id}")
    print(f"Graph: {s.guideline_graph}")
    print(f"Trap: {s.trap_scenario}")
    print(f"Generation method: {getattr(s, 'generation_method', 'manual')}")
    print(f"Triggered rules: {getattr(s, 'triggered_rules', [])}")
    print(f"\nPatient:")
    print(f"  Age: {p.get('age')}, Sex: {p.get('sex')}")
    print(f"  Comorbidities: {p.get('comorbidities', [])}")
    print(f"  Allergies: {p.get('allergies', [])}")
    print(f"  Medications: {p.get('medications', [])}")
    print(f"  Labs: {p.get('labs', {})}")
    print(f"  Vitals: {p.get('vitals', {})}")
    print(f"\nExpected actions ({len(s.expected_actions)}):")
    for a in (s.expected_actions or []):
        print(f"  + {a}")
    print(f"\nForbidden actions ({len(s.forbidden_actions)}):")
    for a in (s.forbidden_actions or []):
        print(f"  ✗ {a}")
    if s.trap_scenario:
        print(f"\nTrap description: {getattr(s, 'trap_description', 'N/A')}")
```

---

## Audit 4: Expected와 Forbidden이 실제로 Derivation Engine에서 나오는지

시나리오 YAML에 적힌 expected/forbidden이 engine.derive()의 결과와 일치하는지.
"YAML에 직접 적었지만 engine이 모르는 constraint"가 있으면 provenance chain이 끊긴 것.

```python
# audit/audit_derivation_consistency.py
"""
auto-generated 시나리오 10개에 대해:
1. YAML의 expected/forbidden 읽기
2. engine.derive()로 다시 계산
3. 두 결과가 일치하는지 비교
"""
import random, yaml
from cpg_model.constraint_derivation import ConstraintDerivationEngine
from cpg_model.scenario_loader import ScenarioLoader
from pathlib import Path

random.seed(77)
engine = ConstraintDerivationEngine()
loader = ScenarioLoader()

auto = [s for s in loader.load_all_scenarios() 
        if getattr(s, 'generation_method', '') and 'auto' in str(getattr(s, 'generation_method', ''))]

sample = random.sample(auto, min(10, len(auto)))

mismatches = 0
for s in sample:
    # YAML에 기록된 것
    yaml_expected = set(s.expected_actions or [])
    yaml_forbidden = set(s.forbidden_actions or [])
    
    # Engine으로 다시 계산
    graph_path = next(
        (p for p in Path("cpg_model/graphs/").glob("*.yaml")
         if yaml.safe_load(open(p)).get("graph_id") == s.guideline_graph),
        None
    )
    if not graph_path:
        print(f"SKIP: {s.scenario_id} — graph not found")
        continue
    
    with open(graph_path) as f:
        graph = yaml.safe_load(f)
    
    patient = s.patient if isinstance(s.patient, dict) else vars(s.patient)
    derived = engine.derive(graph, patient, s.scenario_id)
    
    derived_forbidden = set()
    for c in derived.forbidden:
        derived_forbidden.update(c.actions)
    
    derived_expected = set()
    for attr in ['expected', 'required']:
        if hasattr(derived, attr):
            for c in getattr(derived, attr):
                derived_expected.update(c.actions)
    
    # 비교
    fb_only_yaml = yaml_forbidden - derived_forbidden
    fb_only_derived = derived_forbidden - yaml_forbidden
    ea_only_yaml = yaml_expected - derived_expected
    ea_only_derived = derived_expected - yaml_expected
    
    if fb_only_yaml or fb_only_derived or ea_only_yaml or ea_only_derived:
        mismatches += 1
        print(f"\nMISMATCH: {s.scenario_id}")
        if fb_only_yaml:
            print(f"  Forbidden in YAML but NOT in derived: {fb_only_yaml}")
        if fb_only_derived:
            print(f"  Forbidden in derived but NOT in YAML: {fb_only_derived}")
        if ea_only_yaml:
            print(f"  Expected in YAML but NOT in derived: {ea_only_yaml}")
        if ea_only_derived:
            print(f"  Expected in derived but NOT in YAML: {ea_only_derived}")
    else:
        print(f"MATCH: {s.scenario_id}")

print(f"\n{'='*50}")
print(f"Mismatches: {mismatches}/{len(sample)}")
```

---

## Audit 5: skip_scenario_generation이 정말 시나리오 생성을 막는지

60개 companion rule에 `skip_scenario_generation: true`를 달았다. 이 rule에서 시나리오가 안 만들어졌는지 확인.

```python
# audit/audit_skip_generation.py
"""
skip_scenario_generation=true인 rule의 rule_id가
어떤 시나리오의 triggered_rules에도 없어야 한다.
"""
import yaml
from pathlib import Path
from cpg_model.scenario_loader import ScenarioLoader

# skip rule ids
skip_rules = set()
for p in Path("cpg_model/graphs/").glob("*.yaml"):
    with open(p) as f:
        g = yaml.safe_load(f)
    for nid, node in g.get("nodes", {}).items():
        for rule in node.get("conditional_rules", []):
            if rule.get("skip_scenario_generation"):
                skip_rules.add(rule["rule_id"])

print(f"Skip rules: {len(skip_rules)}")

# 시나리오에서 확인
loader = ScenarioLoader()
violations = []
for s in loader.load_all_scenarios():
    triggered = set(getattr(s, 'triggered_rules', []) or [])
    overlap = triggered & skip_rules
    if overlap:
        violations.append(f"{s.scenario_id}: triggered skip rule {overlap}")

print(f"Violations: {len(violations)}")
for v in violations[:10]:
    print(f"  {v}")
```

---

## Audit 6: Value Variation이 실제로 다른 값을 가지는지

176개 value variation 시나리오가 정말 서로 다른 lab 값을 가지는지.

```python
# audit/audit_value_diversity.py
"""
같은 rule의 boundary/extreme/trigger가 실제로 다른 값을 가지는지.
"""
from cpg_model.scenario_loader import ScenarioLoader
from collections import defaultdict

loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()

# generation_method에 'value_'가 포함된 시나리오
value_scenarios = [s for s in scenarios 
                   if 'value_' in str(getattr(s, 'generation_method', ''))]

print(f"Value variation scenarios: {len(value_scenarios)}")

# 같은 rule을 trigger하는 시나리오끼리 묶기
by_rule = defaultdict(list)
for s in value_scenarios:
    rules = tuple(sorted(getattr(s, 'triggered_rules', []) or []))
    by_rule[rules].append(s)

# 같은 rule 그룹 내에서 lab 값이 다른지 확인
identical_groups = 0
for rules, group in by_rule.items():
    if len(group) < 2:
        continue
    
    # 첫 번째와 나머지의 labs 비교
    labs_list = []
    for s in group:
        p = s.patient if isinstance(s.patient, dict) else vars(s.patient)
        labs_list.append(str(p.get("labs", {})))
    
    if len(set(labs_list)) == 1:
        identical_groups += 1
        print(f"IDENTICAL: {[s.scenario_id for s in group]} — same labs: {labs_list[0][:80]}")
    else:
        print(f"DIVERSE: {[s.scenario_id for s in group]} — {len(set(labs_list))} unique lab sets")

print(f"\nIdentical groups: {identical_groups}")
```

---

## Audit 7: Pathway Normal이 실제로 다른 Expected를 가지는지

```python
# audit/audit_pathway_diversity.py
"""
같은 graph의 pathway normal 시나리오가 서로 다른 expected_actions를 가지는지.
"""
from cpg_model.scenario_loader import ScenarioLoader
from collections import defaultdict

loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()

pathway = [s for s in scenarios 
           if getattr(s, 'generation_method', '') == 'auto:pathway_normal']

print(f"Pathway normal scenarios: {len(pathway)}")

by_graph = defaultdict(list)
for s in pathway:
    by_graph[s.guideline_graph].append(s)

for g, group in sorted(by_graph.items()):
    if len(group) < 2:
        continue
    
    ea_sets = [frozenset(s.expected_actions or []) for s in group]
    unique = len(set(ea_sets))
    
    if unique == 1:
        print(f"PROBLEM: {g} — {len(group)} pathways but ALL have identical expected!")
    else:
        # pairwise overlap
        overlaps = []
        for i in range(len(ea_sets)):
            for j in range(i+1, len(ea_sets)):
                inter = len(ea_sets[i] & ea_sets[j])
                union = len(ea_sets[i] | ea_sets[j])
                overlaps.append(inter/union if union else 1.0)
        avg_overlap = sum(overlaps)/len(overlaps) if overlaps else 0
        print(f"OK: {g} — {len(group)} pathways, {unique} unique, avg overlap={avg_overlap:.0%}")
```

---

## Audit 8: 새 세션에서의 시나리오 수 변화 추적

689라고 했는데 이전에는 418, 359, 366 등 숫자가 계속 바뀌었다. 어디서 늘었는지 추적.

```python
# audit/audit_scenario_count_breakdown.py
"""
시나리오가 어디서 오는지 source별로 분해.
"""
from cpg_model.scenario_loader import ScenarioLoader
from collections import Counter
from pathlib import Path

loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()

# Source file별
source_count = Counter()
for s in scenarios:
    # scenario_id에서 source 추정, 또는 generation_method
    method = getattr(s, 'generation_method', 'manual')
    source_count[method] += 1

print(f"Total: {len(scenarios)}")
print(f"\nBy generation method:")
for m, c in source_count.most_common():
    print(f"  {m}: {c}")

# YAML file별 시나리오 수
yaml_count = Counter()
for p in Path("configs/scenarios/").glob("*.yaml"):
    import yaml
    with open(p) as f:
        data = yaml.safe_load(f)
    if isinstance(data, list):
        yaml_count[p.name] = len(data)
    elif isinstance(data, dict) and "scenarios" in data:
        yaml_count[p.name] = len(data["scenarios"])
    else:
        yaml_count[p.name] = 1 if data else 0

print(f"\nBy YAML file:")
for f, c in yaml_count.most_common():
    print(f"  {f}: {c}")
print(f"  Sum: {sum(yaml_count.values())}")
```

---

## Audit 9: Allergy Drug Map 정확성

allergy_drug_map.yaml이 실제 교차 반응을 정확히 반영하는지.

```python
# audit/audit_allergy_map.py
"""
penicillin_anaphylaxis가 cephalosporin을 포함하는지 등 핵심 매핑 확인.
"""
import yaml

with open("cpg_model/allergy_drug_map.yaml") as f:
    amap = yaml.safe_load(f)

# 핵심 검증
checks = [
    ("penicillin_anaphylaxis", "cephalosporin", True, "JACI 2019 cross-reactivity"),
    ("penicillin_anaphylaxis", "ceftriaxone", True, "10% cross-reactivity"),
    ("penicillin", "amoxicillin", True, "same class"),
    ("aspirin", "ibuprofen", False, "different mechanism — only in AERD"),
    ("sulfa", "furosemide", False, "sulfonamide antibiotic ≠ sulfonamide non-antibiotic"),
    ("heparin_hit", "enoxaparin", True, "LMWH cross-reactivity in HIT"),
]

for allergy, drug, should_contain, reason in checks:
    drugs = amap.get(allergy, [])
    contains = drug in drugs
    status = "OK" if contains == should_contain else "WRONG"
    print(f"  {status}: {allergy} → {drug}: in_map={contains}, expected={should_contain} ({reason})")
```

---

## Audit 10: 실행 가능성 — Dry Run

실제로 1개 시나리오를 benchmark runner에서 실행 가능한지.

```bash
# 가장 간단한 시나리오로 dry-run
python run_benchmark.py \
    --scenario septic_shock_basic \
    --model configs/models/rag_qwen3_4b.yaml \
    --runs 1 \
    --dry-run 2>&1 | tail -20
```

dry-run이 안 되면 689개 전체 실행도 안 됨.

---

## 모든 audit의 결과를 **raw로 출력**하라. 요약하지 말 것.
특히 MISMATCH, BUG, PROBLEM, WRONG, IDENTICAL 키워드가 포함된 줄에 주목.