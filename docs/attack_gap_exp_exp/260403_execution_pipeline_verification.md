> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# Task: 실행 파이프라인 전수 검증

시나리오 생성은 검증 완료. 이제 "시나리오가 실제로 실행되어 올바른 채점 결과를 내는지" 파이프라인 전체를 검증한다.

**원칙: 각 검증 항목의 결과를 raw로 출력하라. "PASS"만 보고하지 말 것.**

---

## Section A: CPG Engine이 새 Graph를 정상 처리하는가

### A.1: 모든 25개 Graph가 CPGEngine으로 로드되는가

```python
# audit/pipeline/audit_engine_load.py
"""
25개 graph 전부를 CPGEngine으로 로드.
기존 14개는 당연히 되지만, 신규 6개 + held-out 5개가 문제일 수 있음.
"""
from pathlib import Path
import traceback

# CPGEngine 또는 CPGEngineFactory 찾기
# 실제 import path 확인 필요
try:
    from cpg_model.engine import CPGEngine, CPGEngineFactory
except ImportError:
    try:
        from cpg_model.engine import CPGEngine
        CPGEngineFactory = None
    except ImportError:
        print("ERROR: Cannot import CPGEngine. Find correct import:")
        import subprocess
        subprocess.run(["grep", "-r", "class CPGEngine", "cpg_model/", "--include=*.py"])
        exit(1)

results = []
for graph_path in sorted(Path("cpg_model/graphs/").glob("*.yaml")):
    try:
        if CPGEngineFactory:
            engine = CPGEngineFactory.load_from_file(graph_path)
        else:
            engine = CPGEngine(graph_path)
        
        # 기본 속성 접근 가능한지
        node_count = len(engine.graph.nodes) if hasattr(engine.graph, 'nodes') else "?"
        entry = engine.graph.entry_node if hasattr(engine.graph, 'entry_node') else "?"
        
        results.append(("OK", graph_path.stem, node_count, entry))
        print(f"  OK: {graph_path.stem} — {node_count} nodes, entry={entry}")
    except Exception as e:
        results.append(("FAIL", graph_path.stem, str(e)[:100], ""))
        print(f"  FAIL: {graph_path.stem}")
        traceback.print_exc()
        print()

ok = sum(1 for r in results if r[0] == "OK")
fail = sum(1 for r in results if r[0] == "FAIL")
print(f"\nTotal: {ok} OK, {fail} FAIL out of {len(results)}")
```

### A.2: Engine이 Node 전환을 정상적으로 하는가 (신규 graph)

```python
# audit/pipeline/audit_engine_traversal.py
"""
신규 11개 graph (6 new + 5 held-out)에서 engine이 node를 순회하는지.
entry node에서 시작해서 최소 1번 전환이 가능한지 확인.
"""
from pathlib import Path
import yaml

NEW_GRAPHS = [
    "anaphylaxis_management", "acls_cardiac_arrest", "status_epilepticus",
    "gina_asthma_exacerbation", "idsa_meningitis", "toxicology_management",
    "aba_burn_resuscitation", "aabb_transfusion", "acog_obstetric_hemorrhage",
    "pals_pediatric_emergency", "apa_agitation_management"
]

for graph_name in NEW_GRAPHS:
    graph_path = Path(f"cpg_model/graphs/{graph_name}.yaml")
    if not graph_path.exists():
        # 이름이 다를 수 있음
        candidates = list(Path("cpg_model/graphs/").glob(f"*{graph_name[:10]}*"))
        if candidates:
            graph_path = candidates[0]
        else:
            print(f"SKIP: {graph_name} — file not found")
            continue
    
    with open(graph_path) as f:
        graph = yaml.safe_load(f)
    
    nodes = graph.get("nodes", {})
    edges = graph.get("edges", [])
    entry = graph.get("entry_node", "")
    
    print(f"\n{graph_name}:")
    print(f"  Entry: {entry}")
    print(f"  Nodes: {len(nodes)}")
    print(f"  Edges: {len(edges)}")
    
    # entry node가 실제로 존재하는지
    if entry and entry not in nodes:
        print(f"  ERROR: entry_node '{entry}' not in nodes!")
    
    # 모든 edge의 from/to가 유효한 node인지
    for edge in edges:
        src = edge.get("from", "")
        dst = edge.get("to", "")
        if src and src not in nodes:
            print(f"  ERROR: edge from '{src}' — node not found")
        if dst and dst not in nodes:
            print(f"  ERROR: edge to '{dst}' — node not found")
    
    # 도달 불가능한 node가 있는지 (entry에서 BFS)
    if entry and edges:
        reachable = set()
        queue = [entry]
        adj = {}
        for edge in edges:
            adj.setdefault(edge.get("from", ""), []).append(edge.get("to", ""))
        while queue:
            n = queue.pop(0)
            if n in reachable:
                continue
            reachable.add(n)
            for neighbor in adj.get(n, []):
                if neighbor not in reachable:
                    queue.append(neighbor)
        
        unreachable = set(nodes.keys()) - reachable
        if unreachable:
            print(f"  WARNING: {len(unreachable)} unreachable nodes: {sorted(unreachable)}")
        else:
            print(f"  OK: All {len(nodes)} nodes reachable from entry")
```

---

## Section B: ActionNormalizer가 새 Action을 처리하는가

### B.1: 모든 graph action이 normalizer에 알려져 있는가

```python
# audit/pipeline/audit_normalizer_coverage.py
"""
모든 graph의 expected_actions + forbidden_actions를 ActionNormalizer에 통과시켜
unknown/unmapped action이 있는지 확인.
"""
from pathlib import Path
import yaml

# ActionNormalizer import
try:
    from cpg_model.action_normalizer import ActionNormalizer
    normalizer = ActionNormalizer()
except ImportError:
    print("Finding ActionNormalizer...")
    import subprocess
    subprocess.run(["grep", "-r", "class ActionNormalizer\|class.*Normalizer", "cpg_model/", "--include=*.py"])
    exit(1)

all_actions = set()
for p in Path("cpg_model/graphs/").glob("*.yaml"):
    with open(p) as f:
        g = yaml.safe_load(f)
    for nid, node in g.get("nodes", {}).items():
        all_actions.update(node.get("expected_actions", []))
        all_actions.update(node.get("forbidden_actions", []))
        for rule in node.get("conditional_rules", []):
            all_actions.update(rule.get("effect", {}).get("actions", []))

print(f"Total unique actions across all graphs: {len(all_actions)}")

# 각 action을 normalizer에 통과
unknown = []
mapped = []
identity = []  # 입력 == 출력 (매핑 없이 통과)

for action in sorted(all_actions):
    try:
        result = normalizer.normalize(action)
        if result is None or result == "":
            unknown.append(action)
        elif result == action:
            identity.append(action)
        else:
            mapped.append((action, result))
    except Exception as e:
        unknown.append(f"{action} (ERROR: {e})")

print(f"\nIdentity (no mapping needed): {len(identity)}")
print(f"Mapped to different name: {len(mapped)}")
print(f"Unknown/unmapped: {len(unknown)}")

if mapped:
    print(f"\nMapped actions (first 20):")
    for orig, norm in mapped[:20]:
        print(f"  {orig} → {norm}")

if unknown:
    print(f"\nUNKNOWN actions (PROBLEM — may fail during scoring):")
    for a in unknown[:30]:
        print(f"  {a}")
```

### B.2: Agent가 출력할 법한 action이 expected에 매핑되는가

```python
# audit/pipeline/audit_normalizer_reverse.py
"""
Agent는 "order CT head", "give aspirin 325mg", "intubate patient" 같은 
자연어에 가까운 형태를 출력한다.
ActionNormalizer가 이를 graph의 expected_actions로 매핑하는지 확인.

대표적인 agent output 패턴과 expected action 매핑을 수동으로 테스트.
"""
# 대표적 agent output → expected mapping 쌍
TEST_CASES = [
    # (agent가 출력할 법한 형태, 매핑되어야 하는 expected action)
    ("obtain 12-lead ECG", "obtain_12_lead_ecg"),
    ("order troponin", "order_lab_troponin"),
    ("give aspirin", "give_aspirin"),
    ("start IV normal saline", "start_iv_fluid_ns"),
    ("activate cath lab", "activate_cath_lab"),
    ("check potassium", "order_lab_bmp"),
    ("start insulin drip", "start_insulin_infusion"),
    ("intubate", "perform_early_intubation"),
    ("give epinephrine IM", "give_epinephrine_im"),
    ("order CT head", "order_stat_ct_head"),
    ("consult neurosurgery", "neurosurgery_consult"),
    ("give tPA", "give_alteplase_0.9mg_kg"),
    ("start norepinephrine", "start_vasopressor_if_hypotensive"),
    ("give lorazepam", "give_benzodiazepine_weight_based"),
    ("perform needle decompression", "perform_needle_decompression"),
]

try:
    from cpg_model.action_normalizer import ActionNormalizer
    normalizer = ActionNormalizer()
except:
    print("Cannot import ActionNormalizer")
    exit(1)

print("Agent Output → Expected Action Mapping Test")
print("=" * 70)

for agent_output, expected in TEST_CASES:
    try:
        result = normalizer.normalize(agent_output)
        match = result == expected
        status = "OK" if match else "MISMATCH"
        print(f"  {status}: '{agent_output}' → '{result}' (expected: '{expected}')")
    except Exception as e:
        print(f"  ERROR: '{agent_output}' → {e}")
```

---

## Section C: Scoring이 새 시나리오에서 작동하는가

### C.1: Scorer가 기본 violation을 탐지하는가

```python
# audit/pipeline/audit_scorer_basic.py
"""
간단한 mock episode를 만들어서 scorer가:
1. Forbidden action 수행 → violation 탐지
2. Expected action 누락 → omission 탐지
3. Sequence 위반 → sequence violation 탐지
하는지 확인.
"""
# Scorer import 찾기
import subprocess
result = subprocess.run(
    ["grep", "-r", "class.*Scorer\|class.*Assessor\|def.*score.*episode\|def.*evaluate", 
     "cpg_model/", "scoring/", "--include=*.py", "-l"],
    capture_output=True, text=True
)
print(f"Scorer/Assessor files:\n{result.stdout}")

# 실제 import는 위 결과를 보고 결정
# 예시 구조:
try:
    from scoring.constraint_checker import ConstraintChecker
    # 또는
    from scoring.violation_detector import ViolationDetector
    # 또는 
    from cpg_model.assessor import Assessor
except ImportError:
    print("Finding scorer...")
    subprocess.run(["grep", "-r", "def.*check_violation\|def.*detect_violation\|def.*score", 
                    "scoring/", "cpg_model/", "--include=*.py"])
    print("\n위 결과를 보고 올바른 import를 사용하라")
```

### C.2: 새 graph에서 episode를 end-to-end로 실행 가능한가

```python
# audit/pipeline/audit_e2e_new_graph.py
"""
신규 graph 11개 각각에서 가장 간단한 시나리오 1개를 선택하여
runner의 초기화 단계까지 실행 가능한지 확인.
"""
from cpg_model.scenario_loader import ScenarioLoader, get_cpg_graph_path

NEW_GRAPHS = [
    "anaphylaxis_management", "acls_cardiac_arrest", "status_epilepticus",
    "gina_asthma_exacerbation", "idsa_meningitis", "toxicology_management",
    "aba_burn_resuscitation", "aabb_transfusion", "acog_obstetric_hemorrhage",
    "pals_pediatric_emergency", "apa_agitation_management"
]

loader = ScenarioLoader()
all_scenarios = loader.load_all_scenarios()

for graph_name in NEW_GRAPHS:
    # 이 graph의 시나리오 중 가장 간단한 것 (expected 가장 적은 것)
    graph_scenarios = [s for s in all_scenarios if s.guideline_graph == graph_name]
    
    if not graph_scenarios:
        # 이름이 정확히 안 맞을 수 있음
        graph_scenarios = [s for s in all_scenarios if graph_name[:10] in s.guideline_graph]
    
    if not graph_scenarios:
        print(f"SKIP: {graph_name} — no scenarios found")
        continue
    
    simplest = min(graph_scenarios, key=lambda s: len(s.expected_actions or []))
    
    print(f"\n{graph_name} — testing with {simplest.scenario_id}:")
    
    # 1. Graph path resolve
    try:
        graph_path = get_cpg_graph_path(simplest.scenario_id)
        print(f"  Graph path: {graph_path} {'EXISTS' if graph_path.exists() else 'MISSING'}")
    except Exception as e:
        print(f"  Graph path FAIL: {e}")
        continue
    
    # 2. Engine 초기화
    try:
        from cpg_model.engine import CPGEngineFactory
        engine = CPGEngineFactory.load_from_file(graph_path)
        print(f"  Engine load: OK")
    except Exception as e:
        print(f"  Engine load FAIL: {e}")
        continue
    
    # 3. Forbidden injection
    try:
        engine.set_scenario_forbidden_actions(simplest.forbidden_actions or [])
        print(f"  Forbidden injection: OK ({len(simplest.forbidden_actions or [])} actions)")
    except Exception as e:
        print(f"  Forbidden injection FAIL: {e}")
    
    # 4. Patient context 설정 (있으면)
    try:
        if hasattr(engine, 'set_patient_context'):
            patient = simplest.patient if isinstance(simplest.patient, dict) else vars(simplest.patient)
            engine.set_patient_context(patient)
            print(f"  Patient context: OK")
        else:
            print(f"  Patient context: method not found (may not be needed)")
    except Exception as e:
        print(f"  Patient context FAIL: {e}")
```

---

## Section D: Config & 실행 스크립트 검증

### D.1: 5개 Model Config 검증

```bash
# 모든 model config가 존재하고 유효한 YAML인지
for config in configs/models/rag_qwen397b.yaml configs/models/rag_oss120b.yaml configs/models/rag_qwen35.yaml configs/models/rag_qwen3_4b.yaml configs/models/rag_deepseek_r1.yaml; do
    if [ -f "$config" ]; then
        python -c "import yaml; yaml.safe_load(open('$config')); print('OK: $config')"
    else
        echo "MISSING: $config"
    fi
done
```

### D.2: run_benchmark.py의 argument parsing

```bash
# help 출력으로 필수 argument 확인
python run_benchmark.py --help 2>&1 | head -30

# scenario list 파일이 run_benchmark에서 사용 가능한 형태인지
python -c "
from cpg_model.scenario_loader import ScenarioLoader
loader = ScenarioLoader()
ids = sorted([s.scenario_id for s in loader.load_all_scenarios()])
print(f'Total scenario IDs: {len(ids)}')
print(f'First 5: {ids[:5]}')
print(f'Last 5: {ids[-5:]}')
# scenario_list 파일 생성
with open('configs/scenario_list_full.txt', 'w') as f:
    f.write('\n'.join(ids))
print(f'Written to configs/scenario_list_full.txt')
"
```

### D.3: vLLM endpoint 접근 가능한지 (GPU 있을 때만)

```bash
# vLLM이 설치되어 있는지
python -c "import vllm; print(f'vLLM version: {vllm.__version__}')" 2>&1

# GPU 상태
nvidia-smi 2>&1 | head -10 || echo "No GPU available"
```

---

## Section E: 기존 Episode와의 호환성

### E.1: 기존 episode JSON이 있으면 새 scorer로 채점 가능한지

```python
# audit/pipeline/audit_existing_episodes.py
"""
results/clean_slate_rescored/ 에 기존 episode가 있으면
새 constraint로 채점했을 때 에러 없이 완료되는지.
"""
from pathlib import Path
import json

episode_dirs = [
    Path("results/clean_slate_rescored/"),
    Path("results/"),
]

episodes_found = False
for d in episode_dirs:
    if not d.exists():
        continue
    
    episode_files = list(d.glob("**/*.json"))
    if not episode_files:
        continue
    
    episodes_found = True
    print(f"Found {len(episode_files)} episode files in {d}")
    
    # 첫 번째 episode의 구조 확인
    with open(episode_files[0]) as f:
        ep = json.load(f)
    
    print(f"Sample episode keys: {list(ep.keys())[:10]}")
    print(f"  scenario_id: {ep.get('scenario_id', 'N/A')}")
    print(f"  model: {ep.get('model', ep.get('model_name', 'N/A'))}")
    print(f"  actions count: {len(ep.get('agent_actions', ep.get('actions', [])))}")
    
    # 이 episode의 scenario가 현재 scenario list에 있는지
    from cpg_model.scenario_loader import ScenarioLoader
    loader = ScenarioLoader()
    current_ids = {s.scenario_id for s in loader.load_all_scenarios()}
    
    ep_scenario = ep.get("scenario_id", "")
    if ep_scenario in current_ids:
        print(f"  Scenario '{ep_scenario}' exists in current list: OK")
    else:
        print(f"  Scenario '{ep_scenario}' NOT in current list: may need re-mapping")
    break

if not episodes_found:
    print("No existing episodes found — clean start")
```

---

## Section F: Temporal Constraints 검증

### F.1: 164 deadline entries가 정상 작동하는지

```python
# audit/pipeline/audit_temporal.py
"""
CPGNode.deadlines (WITHIN constraints)가 올바르게 파싱되고
temporal_constraints.py에서 사용 가능한지.
"""
from pathlib import Path
import yaml

total_deadlines = 0
deadline_details = []

for p in Path("cpg_model/graphs/").glob("*.yaml"):
    with open(p) as f:
        g = yaml.safe_load(f)
    for nid, node in g.get("nodes", {}).items():
        deadlines = node.get("deadlines", node.get("timing_constraints", []))
        if deadlines:
            total_deadlines += len(deadlines) if isinstance(deadlines, list) else 1
            deadline_details.append((p.stem, nid, deadlines))

print(f"Total deadline entries: {total_deadlines}")
print(f"Graphs with deadlines: {len(set(d[0] for d in deadline_details))}")

# 신규 graph에 deadline이 있는지
new_graphs = ["anaphylaxis", "acls", "status_epilepticus", "gina_asthma", "idsa_meningitis", "toxicology",
              "aba_burn", "aabb_trans", "acog_obstet", "pals_ped", "apa_agit"]

for ng in new_graphs:
    matching = [d for d in deadline_details if ng in d[0]]
    if matching:
        print(f"  {ng}: {len(matching)} deadlines")
        for _, nid, dl in matching[:2]:
            print(f"    {nid}: {dl}")
    else:
        print(f"  {ng}: 0 deadlines (may need adding for timing-sensitive domains)")
```

---

## Section G: 논문 수치 일관성

### G.1: handoff 문서의 수치와 현재 코드가 일치하는지

```python
# audit/pipeline/audit_numbers_consistency.py
"""
handoff v2 문서에 적힌 수치와 실제 코드/데이터가 일치하는지.
"""
from cpg_model.scenario_loader import ScenarioLoader
from cpg_model.constraint_derivation import ConstraintDerivationEngine
from pathlib import Path
import yaml

loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()

# Handoff v2 claims
claims = {
    "CPG Graphs": 25,
    "Total Scenarios": 689,  # 또는 현재 기대값
    "Manual Scenarios": 105,
    "Tests Passing": 194,  # 또는 현재 기대값
}

# 실제 확인
actual_graphs = len(list(Path("cpg_model/graphs/").glob("*.yaml")))
actual_scenarios = len(scenarios)
actual_manual = len([s for s in scenarios if not (hasattr(s, 'generation_method') and s.generation_method)])
actual_auto = actual_scenarios - actual_manual

print("=== Handoff v2 Number Verification ===")
print(f"Graphs: claimed={claims['CPG Graphs']}, actual={actual_graphs} {'OK' if actual_graphs == claims['CPG Graphs'] else 'MISMATCH'}")
print(f"Total scenarios: claimed={claims['Total Scenarios']}, actual={actual_scenarios}")
print(f"Manual: claimed={claims['Manual Scenarios']}, actual={actual_manual}")
print(f"Auto: actual={actual_auto}")

# Conditional rules 수
total_rules = 0
for p in Path("cpg_model/graphs/").glob("*.yaml"):
    with open(p) as f:
        g = yaml.safe_load(f)
    for nid, node in g.get("nodes", {}).items():
        total_rules += len(node.get("conditional_rules", []))
print(f"Conditional rules: {total_rules}")

# Sequence rules 수
total_seq = 0
for p in Path("cpg_model/graphs/").glob("*.yaml"):
    with open(p) as f:
        g = yaml.safe_load(f)
    for nid, node in g.get("nodes", {}).items():
        sr = node.get("sequence_rules", [])
        if isinstance(sr, list):
            total_seq += len(sr)
print(f"Sequence rules: {total_seq}")
```

---

**모든 Section (A-G)을 실행하고, 각 항목의 결과를 raw로 출력하라.**
특히 FAIL, ERROR, MISSING, MISMATCH, WARNING 키워드에 주목.