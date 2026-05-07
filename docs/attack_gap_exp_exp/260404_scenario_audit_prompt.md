# 현재 688 시나리오 vs 생성 잠재력 대조 감사

## 목표

현재 688개 시나리오가 4개 생성 축(single-rule trigger, pathway normal, value variation, 2-rule combinatorial)의 잠재력 중 어디까지 커버하는지 정확히 파악한다.

## Step 1: 현재 688개의 generation_method 분포

```python
import yaml, glob
from collections import Counter, defaultdict

# manual 시나리오
manual_files = [f for f in glob.glob('configs/scenarios/*.yaml') 
                if 'auto_generated' not in f]
manual_scenarios = []
for f in manual_files:
    with open(f) as fh:
        data = yaml.safe_load(fh)
        if isinstance(data, list):
            manual_scenarios.extend(data)
        elif isinstance(data, dict):
            if 'scenarios' in data:
                manual_scenarios.extend(data['scenarios'])
            else:
                manual_scenarios.append(data)

# auto 시나리오
with open('configs/scenarios/auto_generated_scenarios.yaml') as f:  # 실제 경로 확인
    auto_scenarios = yaml.safe_load(f)
    if isinstance(auto_scenarios, dict) and 'scenarios' in auto_scenarios:
        auto_scenarios = auto_scenarios['scenarios']

print(f"Manual: {len(manual_scenarios)}")
print(f"Auto: {len(auto_scenarios)}")
print(f"Total: {len(manual_scenarios) + len(auto_scenarios)}")

# generation_method 분포
methods = Counter()
for s in auto_scenarios:
    method = s.get('generation_method', s.get('method', 'unknown'))
    methods[method] += 1

print("\n=== Auto generation methods ===")
for method, count in methods.most_common():
    print(f"  {method}: {count}")
```

## Step 2: 각 축별 현재 커버리지 vs 잠재력

### Axis 1: Single-rule trigger
```python
# 전체 conditional rules 수
all_rules = []
for graph_path in sorted(glob.glob('cpg_model/graphs/*.yaml')):
    # _archive 제외
    if '_archive' in graph_path:
        continue
    with open(graph_path) as f:
        graph = yaml.safe_load(f)
    rules = graph.get('conditional_rules', [])
    graph_name = graph_path.split('/')[-1].replace('.yaml', '')
    for r in rules:
        all_rules.append({'graph': graph_name, 'rule': r})

total_rules = len(all_rules)

# 현재 single_trigger 시나리오가 커버하는 rule 수
single_trigger_scenarios = [s for s in auto_scenarios 
                            if s.get('generation_method') == 'single_trigger']
covered_rules = set()
for s in single_trigger_scenarios:
    # rule ID 또는 trigger 정보 추출 (실제 필드명 확인)
    rule_id = s.get('triggered_rule', s.get('rule_id', s.get('source_rule', '')))
    if rule_id:
        covered_rules.add(rule_id)

print(f"\n=== Axis 1: Single-rule trigger ===")
print(f"  Total conditional rules: {total_rules}")
print(f"  Single-trigger scenarios: {len(single_trigger_scenarios)}")
print(f"  Covered rules: {len(covered_rules)}")
print(f"  Coverage: {len(covered_rules)/total_rules*100:.1f}%")
# companion rules (skip_generation=true)는 시나리오를 안 만드므로 제외해서 재계산
```

### Axis 2: Pathway normals
```python
# 현재 pathway_normal 시나리오
pathway_normals = [s for s in auto_scenarios 
                   if s.get('generation_method') == 'pathway_normal']

# graph별 pathway normal 수
pathway_by_graph = defaultdict(list)
for s in pathway_normals:
    graph = s.get('graph_id', s.get('cpg_graph', 'unknown'))
    pathway_by_graph[graph].append(s)

print(f"\n=== Axis 2: Pathway normals ===")
print(f"  Total pathway_normal scenarios: {len(pathway_normals)}")
print(f"  Graphs with pathway normals: {len(pathway_by_graph)}")
for graph, scenarios in sorted(pathway_by_graph.items()):
    print(f"    {graph}: {len(scenarios)} normals")

# 잠재력과 비교: 이전 분석에서 136 pathway combos
print(f"  Potential (from analysis): ~136 pathway combos")
print(f"  Coverage: {len(pathway_normals)}/136 = {len(pathway_normals)/136*100:.1f}%")
```

### Axis 3: Value variation
```python
value_scenarios = [s for s in auto_scenarios 
                   if 'value' in s.get('generation_method', '').lower() 
                   or 'boundary' in s.get('generation_method', '').lower()
                   or 'extreme' in s.get('generation_method', '').lower()]

print(f"\n=== Axis 3: Value variation ===")
print(f"  Total value variation scenarios: {len(value_scenarios)}")
# 어떤 수치 파라미터가 변형되었는지
value_params = Counter()
for s in value_scenarios:
    param = s.get('varied_parameter', s.get('parameter', 'unknown'))
    value_params[param] += 1
for param, count in value_params.most_common(10):
    print(f"    {param}: {count}")
print(f"  Potential (from analysis): ~148")
```

### Axis 4: Combinatorial
```python
combo_scenarios = [s for s in auto_scenarios 
                   if 'combinat' in s.get('generation_method', '').lower()
                   or 'multi' in s.get('generation_method', '').lower()]

print(f"\n=== Axis 4: Combinatorial ===")
print(f"  Total combinatorial scenarios: {len(combo_scenarios)}")
# 2-rule vs 3-rule
combo_depth = Counter()
for s in combo_scenarios:
    rules = s.get('triggered_rules', s.get('rules', []))
    combo_depth[len(rules)] += 1
for depth, count in sorted(combo_depth.items()):
    print(f"    {depth}-rule combos: {count}")
print(f"  Potential 2-rule (from analysis): ~1,237")
print(f"  Potential 3-rule (from analysis): ~4,567")
```

## Step 3: Graph별 시나리오 분포

```python
# graph별 총 시나리오 수 (manual + auto)
graph_dist = defaultdict(lambda: {'manual': 0, 'auto': 0, 'methods': Counter()})

for s in manual_scenarios:
    graph = s.get('graph_id', s.get('cpg_graph', s.get('domain', 'unknown')))
    graph_dist[graph]['manual'] += 1

for s in auto_scenarios:
    graph = s.get('graph_id', s.get('cpg_graph', 'unknown'))
    graph_dist[graph]['auto'] += 1
    method = s.get('generation_method', 'unknown')
    graph_dist[graph]['methods'][method] += 1

print(f"\n=== Graph별 시나리오 분포 ===")
print(f"{'Graph':<35} {'Manual':>7} {'Auto':>7} {'Total':>7}  Methods")
print("-" * 100)
for graph in sorted(graph_dist.keys()):
    d = graph_dist[graph]
    total = d['manual'] + d['auto']
    methods_str = ', '.join(f"{m}:{c}" for m, c in d['methods'].most_common(3))
    print(f"{graph:<35} {d['manual']:>7} {d['auto']:>7} {total:>7}  {methods_str}")

# 시나리오 0개인 graph
all_graphs = set()
for f in glob.glob('cpg_model/graphs/*.yaml'):
    if '_archive' not in f:
        all_graphs.add(f.split('/')[-1].replace('.yaml', ''))
covered_graphs = set(graph_dist.keys())
uncovered = all_graphs - covered_graphs
if uncovered:
    print(f"\n*** UNCOVERED GRAPHS (시나리오 0개): {uncovered}")
```

## Step 4: Gap 분석 요약

```python
print("\n" + "=" * 80)
print("GAP ANALYSIS SUMMARY")
print("=" * 80)
print(f"""
현재: {len(manual_scenarios) + len(auto_scenarios)} scenarios (manual {len(manual_scenarios)} + auto {len(auto_scenarios)})

Axis 1 (Single-rule):     {len(single_trigger_scenarios)} / {total_rules} rules covered
Axis 2 (Pathway normal):  {len(pathway_normals)} / ~136 combos covered  
Axis 3 (Value variation):  {len(value_scenarios)} / ~148 possible
Axis 4 (Combinatorial):    {len(combo_scenarios)} / ~1,237 2-rule combos

EXPANSION OPPORTUNITIES:
- Pathway normals: +{max(0, 136 - len(pathway_normals))} possible
- Value variations: +{max(0, 148 - len(value_scenarios))} possible
- 2-rule combos (selective): +{max(0, min(200, 1237 - len(combo_scenarios)))} recommended
- Uncovered graphs: {len(uncovered)} graphs with 0 scenarios
""")
```

## 완료 기준

이 스크립트의 출력을 **그대로 보고하라.** 요약하거나 해석하지 말 것.
숫자를 보고 확장 여부와 범위를 결정한다.