# Task: Graph ID 이중화 통일

## 문제

같은 clinical domain이 두 개의 graph ID로 분리되어 있다:

| Domain | V1 (수동 시나리오 참조) | V2 (자동 시나리오 참조) | 수동 | 자동 |
|---|---|---|---|---|
| Chest Pain | `aha_chest_pain` | `aha_chest_pain_evaluation` | 13 | 21 |
| Heart Failure | `aha_heart_failure` | `aha_heart_failure_2022` | 10 | 39 |
| Stroke | `aha_stroke` | `aha_stroke_2019` | 13 | 20 |
| Sepsis | `ssc_sepsis_hour1` | `ssc_sepsis_hour1_bundle` | 10 | 13 |

V2는 V1에 conditional_rules + patient_activation_condition을 추가한 superset이다.
V1 graph 파일이 아직 남아있어서 수동 시나리오가 V1을 참조한다.

## 해결 방향

V2로 통일한다. V1 graph 파일을 제거하고, 수동 시나리오의 `guideline_graph`를 V2 이름으로 변경한다.

## Step 1: 현재 상태 확인

```bash
# V1과 V2 graph 파일이 모두 존재하는지
ls -la cpg_model/graphs/aha_chest_pain*.yaml
ls -la cpg_model/graphs/aha_heart_failure*.yaml
ls -la cpg_model/graphs/aha_stroke*.yaml
ls -la cpg_model/graphs/ssc_sepsis*.yaml
```

## Step 2: V2가 V1의 superset인지 확인

통일 전에, V2가 V1의 모든 node/forbidden/sequence를 포함하는지 확인해야 한다.

```python
# scripts/verify_graph_superset.py
import yaml

PAIRS = [
    ("cpg_model/graphs/aha_chest_pain.yaml", "cpg_model/graphs/aha_chest_pain_evaluation.yaml"),
    ("cpg_model/graphs/aha_heart_failure.yaml", "cpg_model/graphs/aha_heart_failure_2022.yaml"),
    ("cpg_model/graphs/aha_stroke.yaml", "cpg_model/graphs/aha_stroke_2019.yaml"),
    ("cpg_model/graphs/ssc_sepsis_hour1.yaml", "cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml"),
]

for v1_path, v2_path in PAIRS:
    with open(v1_path) as f:
        v1 = yaml.safe_load(f)
    with open(v2_path) as f:
        v2 = yaml.safe_load(f)
    
    v1_nodes = set(v1.get("nodes", {}).keys())
    v2_nodes = set(v2.get("nodes", {}).keys())
    
    v1_forbidden = set()
    v2_forbidden = set()
    for node in v1.get("nodes", {}).values():
        v1_forbidden.update(node.get("forbidden_actions", []))
    for node in v2.get("nodes", {}).values():
        v2_forbidden.update(node.get("forbidden_actions", []))
    
    missing_nodes = v1_nodes - v2_nodes
    missing_forbidden = v1_forbidden - v2_forbidden
    
    print(f"\n{v1_path} → {v2_path}")
    print(f"  V1 nodes: {len(v1_nodes)}, V2 nodes: {len(v2_nodes)}")
    print(f"  Missing nodes in V2: {missing_nodes or 'none'}")
    print(f"  V1 forbidden: {len(v1_forbidden)}, V2 forbidden: {len(v2_forbidden)}")
    print(f"  Missing forbidden in V2: {missing_forbidden or 'none'}")
    
    if missing_nodes or missing_forbidden:
        print(f"  *** WARNING: V2 is NOT a superset — merge needed ***")
    else:
        print(f"  OK: V2 is superset of V1")
```

**이 스크립트를 먼저 실행하라.** 결과에 따라 두 가지 경로:
- **모두 superset**: Step 3으로 바로 진행
- **일부 누락**: V1의 누락된 node/forbidden을 V2에 병합한 후 진행

## Step 3: 수동 시나리오의 guideline_graph 변경

```python
# scripts/unify_graph_ids.py
import yaml
from pathlib import Path

REMAP = {
    "aha_chest_pain": "aha_chest_pain_evaluation",
    "aha_heart_failure": "aha_heart_failure_2022",
    "aha_stroke": "aha_stroke_2019",
    "ssc_sepsis_hour1": "ssc_sepsis_hour1_bundle",
}

changed_total = 0

for yaml_path in sorted(Path("configs/scenarios/").glob("*.yaml")):
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    
    if not data:
        continue
    
    items = data if isinstance(data, list) else [data]
    changed = False
    
    for s in items:
        old_graph = s.get("guideline_graph", "")
        if old_graph in REMAP:
            s["guideline_graph"] = REMAP[old_graph]
            changed = True
            changed_total += 1
            print(f"  {s.get('scenario_id', '?')}: {old_graph} → {REMAP[old_graph]}")
    
    if changed:
        with open(yaml_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

print(f"\nTotal remapped: {changed_total}")
```

## Step 4: ScenarioLoader의 graph resolution 확인

`scenario_loader.py`의 `get_cpg_graph_path()`가 graph_id → 파일 경로를 매핑하는 부분을 확인한다. V1 이름으로 resolve하는 하드코딩이 있으면 V2로 변경하거나 alias를 추가한다.

```bash
grep -n "aha_chest_pain\|aha_heart_failure\|aha_stroke\|ssc_sepsis_hour1" cpg_model/scenario_loader.py
```

매핑 테이블이 있으면 V1 항목을 V2로 변경. 또는 V1→V2 alias 추가:

```python
# scenario_loader.py의 graph_map에 추가 (있으면)
GRAPH_ALIASES = {
    "aha_chest_pain": "aha_chest_pain_evaluation",
    "aha_heart_failure": "aha_heart_failure_2022",
    "aha_stroke": "aha_stroke_2019",
    "ssc_sepsis_hour1": "ssc_sepsis_hour1_bundle",
}
```

## Step 5: V1 graph 파일 처리

V2로 통일되었으면 V1 파일은 더 이상 불필요하다. 삭제하거나 _archive로 이동.

```bash
mkdir -p cpg_model/graphs/_archive

# V1 파일을 archive로 이동 (삭제 대신)
for f in aha_chest_pain.yaml aha_heart_failure.yaml aha_stroke.yaml ssc_sepsis_hour1.yaml; do
    if [ -f "cpg_model/graphs/$f" ]; then
        mv "cpg_model/graphs/$f" "cpg_model/graphs/_archive/$f"
        echo "Archived: $f"
    fi
done
```

## Step 6: 전체 검증

```bash
# 1. 모든 시나리오가 유효한 graph를 참조하는지
python -c "
from cpg_model.scenario_loader import ScenarioLoader, get_cpg_graph_path
loader = ScenarioLoader()
for s in loader.load_all_scenarios():
    path = get_cpg_graph_path(s.scenario_id)
    assert path.exists(), f'{s.scenario_id}: graph not found at {path}'
print(f'All {len(loader.load_all_scenarios())} scenarios resolve to valid graph files')
"

# 2. 이중화가 해소되었는지 — 같은 domain이 하나의 graph_id만 가지는지
python -c "
from cpg_model.scenario_loader import ScenarioLoader
from collections import Counter
loader = ScenarioLoader()
gc = Counter(s.guideline_graph for s in loader.load_all_scenarios())
print('Graph distribution (should have no duplicates):')
for g, c in gc.most_common():
    print(f'  {g}: {c}')

# 이중화 확인
old_ids = ['aha_chest_pain', 'aha_heart_failure', 'aha_stroke', 'ssc_sepsis_hour1']
for oid in old_ids:
    if oid in gc:
        print(f'ERROR: Old graph ID still in use: {oid} ({gc[oid]} scenarios)')
    else:
        print(f'OK: {oid} no longer used')
"

# 3. Graph 파일이 _archive로 이동되었는지
ls cpg_model/graphs/_archive/

# 4. Regression
python -m pytest tests/ -x -q --ignore=tests/test_exit_criteria/ 2>&1 | tail -5

# 5. 시나리오 총 수 변화 없음 확인
python -c "
from cpg_model.scenario_loader import ScenarioLoader
loader = ScenarioLoader()
total = len(loader.load_all_scenarios())
print(f'Total scenarios: {total}')
assert total >= 685, f'Scenario count dropped: {total}'
"

# 6. Engine load — archive 이동 후에도 25개(또는 21개 active) graph 모두 로드
python -c "
from pathlib import Path
import yaml
active = list(Path('cpg_model/graphs/').glob('*.yaml'))
print(f'Active graph files: {len(active)}')
for p in sorted(active):
    with open(p) as f:
        g = yaml.safe_load(f)
    print(f'  {g.get(\"graph_id\", p.stem)}')
"
```

## Completion Criteria

- [ ] V2가 V1의 superset 확인 (또는 병합 완료)
- [ ] 모든 수동 시나리오의 guideline_graph가 V2 이름으로 변경됨
- [ ] ScenarioLoader가 V2 이름으로 정상 resolve
- [ ] V1 graph 파일이 _archive로 이동됨
- [ ] 이중화 graph ID 0개 (old ID가 어떤 시나리오에도 없음)
- [ ] 시나리오 총 수 변화 없음 (≥685)
- [ ] 전체 regression 0
- [ ] 최종 graph 수 보고 (active만)