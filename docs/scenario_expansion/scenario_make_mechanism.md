# Task: Graph별 시나리오 생성 메커니즘과 수량 정밀 분석

## 목적

각 CPG graph에서 PatientGenerator가 시나리오를 **어떤 로직으로, 몇 개** 만드는지 정확히 파악한다.

## 실행할 분석

### 분석 1: Graph별 생성 메커니즘 해부

```python
# scripts/analyze_generation_mechanics.py
"""
각 graph에서 시나리오가 생성되는 과정을 단계별로 추적.
"""
from pathlib import Path
from cpg_model.constraint_derivation import ConstraintDerivationEngine
from cpg_model.patient_generator import PatientGenerator
from collections import defaultdict
import yaml

engine = ConstraintDerivationEngine()
generator = PatientGenerator(engine)

print("=" * 100)
print("SCENARIO GENERATION MECHANICS — FULL BREAKDOWN")
print("=" * 100)

total_rules = 0
total_trigger = 0
total_normal = 0
total_combo = 0
total_skipped = 0

graph_details = []

for graph_path in sorted(Path("cpg_model/graphs/").glob("*.yaml")):
    with open(graph_path) as f:
        graph = yaml.safe_load(f)
    
    graph_id = graph.get("graph_id", graph_path.stem)
    
    # 1. Conditional rules 수집
    rules = generator._collect_all_rules(graph)
    
    # 2. 각 rule에서 trigger/normal patient 생성 시도
    trigger_count = 0
    normal_count = 0
    skipped_count = 0
    
    rule_details = []
    for rule in rules:
        trigger_patient = generator._generate_trigger_patient(rule, graph)
        normal_patient = generator._generate_normal_patient(rule, graph)
        
        trigger_ok = trigger_patient is not None
        normal_ok = normal_patient is not None
        
        if trigger_ok:
            # 실제로 condition이 fire하는지 검증
            fires = engine._evaluate_condition(rule["condition"], trigger_patient)
            if fires:
                trigger_count += 1
            else:
                skipped_count += 1
                trigger_ok = False
        
        if normal_ok:
            fires = engine._evaluate_condition(rule["condition"], normal_patient)
            if not fires:  # normal은 fire하지 않아야 함
                normal_count += 1
            else:
                skipped_count += 1
                normal_ok = False
        
        rule_details.append({
            "rule_id": rule["rule_id"],
            "condition": rule["condition"][:80],
            "severity": rule.get("severity", "?"),
            "trigger_generated": trigger_ok,
            "normal_generated": normal_ok,
        })
    
    # 3. Combinatorial (2-rule 조합) 수
    combo_scenarios = generator._generate_combinatorial_patients(rules, graph) if hasattr(generator, '_generate_combinatorial_patients') else []
    combo_count = len(combo_scenarios) if combo_scenarios else 0
    
    total_from_graph = trigger_count + normal_count + combo_count
    
    graph_details.append({
        "graph_id": graph_id,
        "conditional_rules": len(rules),
        "trigger_scenarios": trigger_count,
        "normal_scenarios": normal_count,
        "combo_scenarios": combo_count,
        "skipped": skipped_count,
        "total": total_from_graph,
    })
    
    total_rules += len(rules)
    total_trigger += trigger_count
    total_normal += normal_count
    total_combo += combo_count
    total_skipped += skipped_count
    
    print(f"\n{'─' * 80}")
    print(f"GRAPH: {graph_id}")
    print(f"  Conditional rules: {len(rules)}")
    print(f"  → Trigger scenarios (trap): {trigger_count}")
    print(f"  → Normal scenarios (baseline): {normal_count}")
    print(f"  → Combinatorial scenarios: {combo_count}")
    print(f"  → Skipped (condition didn't fire): {skipped_count}")
    print(f"  = TOTAL from this graph: {total_from_graph}")
    print(f"  Rules detail:")
    for rd in rule_details:
        t = "✓" if rd["trigger_generated"] else "✗"
        n = "✓" if rd["normal_generated"] else "✗"
        print(f"    {rd['rule_id'][:50]:50s} [{rd['severity']:8s}] trigger={t} normal={n}")

print(f"\n{'=' * 100}")
print(f"GRAND TOTAL")
print(f"{'=' * 100}")
print(f"  Graphs: {len(graph_details)}")
print(f"  Conditional rules: {total_rules}")
print(f"  Trigger (trap) scenarios: {total_trigger}")
print(f"  Normal (baseline) scenarios: {total_normal}")
print(f"  Combinatorial scenarios: {total_combo}")
print(f"  Skipped: {total_skipped}")
print(f"  AUTO-GENERATED TOTAL: {total_trigger + total_normal + total_combo}")

# 수동 시나리오 수
from cpg_model.scenario_loader import ScenarioLoader
loader = ScenarioLoader()
all_scenarios = loader.load_all_scenarios()
manual = [s for s in all_scenarios if not hasattr(s, 'generation_method') or not s.generation_method]
auto = [s for s in all_scenarios if hasattr(s, 'generation_method') and s.generation_method]

print(f"\n  Manual scenarios: {len(manual)}")
print(f"  Auto scenarios (loaded): {len(auto)}")
print(f"  GRAND TOTAL: {len(all_scenarios)}")

# 생성 공식 요약
print(f"\n{'=' * 100}")
print(f"GENERATION FORMULA")
print(f"{'=' * 100}")
print(f"  Per conditional rule: 최대 2개 (1 trigger + 1 normal)")
print(f"  실제 생성률: {(total_trigger + total_normal) / (total_rules * 2) * 100:.0f}% of theoretical max")
print(f"  Theoretical max (rules × 2): {total_rules * 2}")
print(f"  Actual auto-generated: {total_trigger + total_normal + total_combo}")
print(f"  Efficiency: {(total_trigger + total_normal + total_combo) / (total_rules * 2) * 100:.0f}%")

# 테이블 형태 출력
print(f"\n{'=' * 100}")
print(f"{'Graph':<35s} {'Rules':>6s} {'Trigger':>8s} {'Normal':>7s} {'Combo':>6s} {'Skip':>5s} {'Total':>6s}")
print(f"{'─' * 35} {'─' * 6} {'─' * 8} {'─' * 7} {'─' * 6} {'─' * 5} {'─' * 6}")
for gd in sorted(graph_details, key=lambda x: -x["total"]):
    print(f"{gd['graph_id']:<35s} {gd['conditional_rules']:>6d} {gd['trigger_scenarios']:>8d} {gd['normal_scenarios']:>7d} {gd['combo_scenarios']:>6d} {gd['skipped']:>5d} {gd['total']:>6d}")
print(f"{'─' * 35} {'─' * 6} {'─' * 8} {'─' * 7} {'─' * 6} {'─' * 5} {'─' * 6}")
print(f"{'TOTAL':<35s} {total_rules:>6d} {total_trigger:>8d} {total_normal:>7d} {total_combo:>6d} {total_skipped:>5d} {total_trigger + total_normal + total_combo:>6d}")
```

### 분석 2: 시나리오 확장 가능성 — 이론적 최대

```python
# scripts/theoretical_max_scenarios.py
"""
현재 rule 구조에서 이론적으로 만들 수 있는 최대 시나리오 수 계산.

시나리오 생성 source:
1. Single-rule trigger: 각 rule × 1 trigger patient = N scenarios
2. Single-rule normal: 각 rule × 1 normal patient = N scenarios
3. Combinatorial (2-rule): C(N,2) 조합 = N*(N-1)/2 scenarios (같은 graph 내)
4. Combinatorial (3-rule): C(N,3) = N*(N-1)*(N-2)/6
5. Cross-domain: 서로 다른 graph의 rule 조합 (현재 미구현)
6. Value variation: 같은 rule이지만 다른 lab 값 (K+=2.9 vs K+=1.5)
"""
from pathlib import Path
from math import comb
import yaml

print("THEORETICAL MAXIMUM SCENARIOS")
print("=" * 80)

for graph_path in sorted(Path("cpg_model/graphs/").glob("*.yaml")):
    with open(graph_path) as f:
        graph = yaml.safe_load(f)
    
    graph_id = graph.get("graph_id", graph_path.stem)
    
    # conditional rules 수
    rules = []
    for node_id, node in graph.get("nodes", {}).items():
        for rule in node.get("conditional_rules", []):
            rules.append(rule)
    
    n = len(rules)
    
    # 현재 구현
    current_single = n * 2  # trigger + normal per rule
    current_combo = 0  # 구현 여부에 따라
    
    # 이론적 확장
    combo_2 = comb(n, 2)  # 2-rule 조합
    combo_3 = comb(n, 3)  # 3-rule 조합
    
    # Value variation (각 numeric rule에서 3개 값: low, mid, boundary)
    numeric_rules = [r for r in rules if any(
        op in r.get("condition", "") for op in ["<", ">", "<=", ">="]
    )]
    value_variation = len(numeric_rules) * 3  # low, mid, boundary 각각
    
    theoretical_max = current_single + combo_2 + value_variation
    
    print(f"\n{graph_id} ({n} rules):")
    print(f"  Current: {current_single} (single trigger+normal)")
    print(f"  + 2-rule combos: {combo_2}")
    print(f"  + value variations: {value_variation} ({len(numeric_rules)} numeric rules × 3)")
    print(f"  = Theoretical max: {theoretical_max}")
```

### 분석 3: Deduplication이 얼마나 줄이는지

```python
# scripts/analyze_deduplication.py
"""
PatientGenerator의 _deduplicate()가 얼마나 시나리오를 줄이는지 확인.
같은 triggered_rules set이면 하나만 유지하는 로직.
"""
# PatientGenerator의 generate_from_graph를 수정하여
# dedup 전/후 수를 출력하도록 하거나,
# 실제 auto_generated_scenarios.yaml에서 triggered_rules 분포를 분석

from cpg_model.scenario_loader import ScenarioLoader

loader = ScenarioLoader()
auto = [s for s in loader.load_all_scenarios() 
        if hasattr(s, 'generation_method') and s.generation_method]

from collections import Counter
rule_sets = Counter()
for s in auto:
    rules = tuple(sorted(getattr(s, 'triggered_rules', []) or []))
    rule_sets[rules] += 1

print(f"Total auto scenarios: {len(auto)}")
print(f"Unique triggered_rules sets: {len(rule_sets)}")
print(f"Duplicates removed: {len(auto) - len(rule_sets)} (if any)")
print(f"\nRule set distribution:")
for rules, count in rule_sets.most_common(20):
    print(f"  {count}x: {rules[:3]}{'...' if len(rules) > 3 else ''}")
```

이 3개 스크립트를 모두 실행하고 전체 출력을 보고하라.