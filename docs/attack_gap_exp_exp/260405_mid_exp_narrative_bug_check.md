# 중간 결과 비판적 검증 — "Bug인가, Finding인가?"

> 원칙: 모든 이상 수치는 finding 전에 bug를 먼저 의심한다.
> 어떤 결과도 검증 없이 논문에 넣지 않는다.

---

## 검증 1: Model Ordering 역전은 버그인가?

qwen397b(30%) < qwen4b(51.7%) — 397B가 4B보다 낮다. 이건 정상이 아닐 수 있다.

```python
import json, glob, os
from collections import defaultdict

EPISODES_DIR = "results/full_706_v5"

model_stats = defaultdict(lambda: {
    'total': 0,
    'actions_counts': [],
    'empty_actions': 0,
    'deviation_counts': [],
    'compliance_scores': [],
    'hard_viol_count': 0,
    'violation_counts': [],
    'n_actions_zero': 0,
})

for model_dir in sorted(glob.glob(os.path.join(EPISODES_DIR, "*"))):
    if not os.path.isdir(model_dir): continue
    model = os.path.basename(model_dir)
    for f in sorted(glob.glob(os.path.join(model_dir, "*.json"))):
        try:
            ep = json.load(open(f))
        except: continue
        
        s = model_stats[model]
        s['total'] += 1
        
        actions = ep.get('actions', [])
        n_actions = ep.get('actions_count', len(actions))
        s['actions_counts'].append(n_actions)
        
        if n_actions == 0:
            s['n_actions_zero'] += 1
        
        if n_actions <= 3:
            s['empty_actions'] += 1
        
        # Deviation count (actions that aren't in expected)
        expected = set(ep.get('expected_actions', []))
        if isinstance(actions, list) and actions:
            deviations = 0
            for a in actions:
                action_name = a.get('action', a) if isinstance(a, dict) else str(a)
                if action_name not in expected:
                    deviations += 1
            s['deviation_counts'].append(deviations)
        
        compliance = ep.get('compliance_score', 0)
        if compliance is not None:
            s['compliance_scores'].append(compliance)
        
        violations = ep.get('violation_events', [])
        s['violation_counts'].append(len(violations))
        
        has_hard = any(isinstance(v, dict) and 
                      v.get('severity', v.get('type','')).upper() in 
                      ('HARD','FORBIDDEN','WITHIN','BEFORE','CRITICAL')
                      for v in violations)
        if has_hard:
            s['hard_viol_count'] += 1

import numpy as np
print(f"{'Model':15s} {'N':>5s} {'Actions':>8s} {'Empty':>6s} {'Zero':>5s} {'Deviations':>11s} {'Compliance':>11s} {'HardViol%':>9s} {'Viols/ep':>9s}")
print("-" * 95)
for model in sorted(model_stats):
    s = model_stats[model]
    n = s['total']
    mean_actions = np.mean(s['actions_counts']) if s['actions_counts'] else 0
    empty_pct = s['empty_actions'] / max(n, 1) * 100
    zero_pct = s['n_actions_zero'] / max(n, 1) * 100
    mean_dev = np.mean(s['deviation_counts']) if s['deviation_counts'] else 0
    mean_comp = np.mean(s['compliance_scores']) if s['compliance_scores'] else 0
    hard_pct = s['hard_viol_count'] / max(n, 1) * 100
    mean_viols = np.mean(s['violation_counts']) if s['violation_counts'] else 0
    print(f"{model:15s} {n:5d} {mean_actions:8.1f} {empty_pct:5.1f}% {zero_pct:4.1f}% {mean_dev:11.1f} {mean_comp:11.3f} {hard_pct:8.1f}% {mean_viols:9.1f}")

print("\n=== 핵심 질문 ===")
print("1. qwen397b의 mean actions가 다른 모델 대비 비정상적으로 낮거나 높은가?")
print("2. empty/zero action 비율이 특정 모델에서 높은가? (Bug 4/6 잔존)")
print("3. deviation이 큰 모델 = 과잉 action = 더 많은 violation인가?")
print("4. compliance와 hard_viol의 관계가 모델마다 다른가?")
```

---

## 검증 2: Auto FA 53.4%는 over-generation artifact인가?

enginePrecision=0.217이면 engine constraint의 78%가 invalid일 수 있다.
auto scenarios의 높은 FA가 "진짜 blind spot"인지 "잘못된 constraint"인지 구분해야 한다.

```python
import json, glob, os
from collections import Counter, defaultdict

EPISODES_DIR = "results/full_706_v5"

# Auto vs Manual episodes 분리
auto_viols = Counter()
manual_viols = Counter()
auto_episodes = []
manual_episodes = []

for model_dir in sorted(glob.glob(os.path.join(EPISODES_DIR, "*"))):
    if not os.path.isdir(model_dir): continue
    for f in sorted(glob.glob(os.path.join(model_dir, "*.json"))):
        try:
            ep = json.load(open(f))
        except: continue
        
        sid = ep.get('scenario_id', '')
        is_auto = 'auto' in sid.lower() or ep.get('source', '') == 'auto'
        # auto_generated_scenarios.yaml에서 온 것인지 확인
        # 다른 판별 방법이 필요하면 scenario config에서 확인
        
        violations = ep.get('violation_events', [])
        
        for v in violations:
            if not isinstance(v, dict): continue
            vtype = v.get('type', v.get('constraint_type', 'UNKNOWN')).upper()
            if is_auto:
                auto_viols[vtype] += 1
            else:
                manual_viols[vtype] += 1
        
        if is_auto:
            auto_episodes.append(ep)
        else:
            manual_episodes.append(ep)

print(f"Manual episodes: {len(manual_episodes)}")
print(f"Auto episodes: {len(auto_episodes)}")

print(f"\n=== Violation Type Distribution ===")
print(f"{'Type':15s} {'Manual':>8s} {'Auto':>8s} {'Auto/Manual':>12s}")
all_types = set(manual_viols.keys()) | set(auto_viols.keys())
for vtype in sorted(all_types):
    m = manual_viols.get(vtype, 0)
    a = auto_viols.get(vtype, 0)
    ratio = a / max(m, 1)
    print(f"{vtype:15s} {m:8d} {a:8d} {ratio:12.1f}x")

print(f"\n=== 핵심 질문 ===")
print("1. auto에서만 급증하는 violation type은? → engine over-generation 의심")
print("2. manual에도 있는 violation type이 auto에서 비례적으로 증가했는가? → 정상 스케일링")
print("3. auto-only violation의 구체적 예시를 확인해야 함 (아래)")

# Auto-only violations 샘플
print(f"\n=== Auto episode 샘플 (hard violation 있는 것) ===")
auto_hard = [ep for ep in auto_episodes 
             if any(isinstance(v, dict) and v.get('type','').upper() in ('FORBIDDEN','WITHIN','COMMISSION')
                    for v in ep.get('violation_events', []))]

for ep in auto_hard[:3]:
    print(f"\nScenario: {ep.get('scenario_id','')}")
    print(f"  Actions: {ep.get('actions_count', '?')}")
    print(f"  Compliance: {ep.get('compliance_score', '?')}")
    violations = ep.get('violation_events', [])
    hard = [v for v in violations if isinstance(v, dict) and 
            v.get('type','').upper() in ('FORBIDDEN','WITHIN','COMMISSION')]
    for v in hard[:3]:
        print(f"  Violation: {v.get('type','')} — {v.get('description', v.get('action', ''))[:100]}")
```

---

## 검증 3: Held-out FA=77%는 graph 버그인가?

77%는 비정상적으로 높다. Held-out graph/scenario 자체의 문제일 수 있다.

```python
import json, glob, os, yaml
from collections import defaultdict

EPISODES_DIR = "results/full_706_v5"

# Held-out graph 목록
HELD_OUT_KEYWORDS = ['aba_burn', 'aabb_trans', 'acog_obstetric', 'pals_pediatric', 'apa_agitation',
                     'burn', 'transfusion', 'obstetric', 'pediatric', 'agitation']

def is_heldout(scenario_id):
    sid = scenario_id.lower()
    return any(kw in sid for kw in HELD_OUT_KEYWORDS)

# Domain별 분석
domain_stats = defaultdict(lambda: {
    'total': 0, 'hard_viol': 0, 'compliance_sum': 0,
    'mean_actions': [], 'mean_violations': [],
    'is_heldout': False
})

for model_dir in sorted(glob.glob(os.path.join(EPISODES_DIR, "*"))):
    if not os.path.isdir(model_dir): continue
    for f in sorted(glob.glob(os.path.join(model_dir, "*.json"))):
        try:
            ep = json.load(open(f))
        except: continue
        
        sid = ep.get('scenario_id', '')
        # Extract domain from scenario_id (first part before _)
        domain = '_'.join(sid.split('_')[:2]) if sid else 'unknown'
        
        s = domain_stats[domain]
        s['total'] += 1
        s['is_heldout'] = is_heldout(sid)
        
        violations = ep.get('violation_events', [])
        has_hard = any(isinstance(v, dict) and 
                      v.get('severity', v.get('type','')).upper() in 
                      ('HARD','FORBIDDEN','WITHIN','BEFORE','CRITICAL')
                      for v in violations)
        if has_hard:
            s['hard_viol'] += 1
        
        s['compliance_sum'] += (ep.get('compliance_score', 0) or 0)
        s['mean_actions'].append(ep.get('actions_count', len(ep.get('actions', []))))
        s['mean_violations'].append(len(violations))

import numpy as np
print(f"{'Domain':30s} {'HO':>3s} {'N':>5s} {'FA%':>6s} {'Compl':>6s} {'Actions':>8s} {'Viols':>6s}")
print("-" * 75)
for domain in sorted(domain_stats, key=lambda d: domain_stats[d]['is_heldout']):
    s = domain_stats[domain]
    if s['total'] < 5: continue
    fa = s['hard_viol'] / max(s['total'], 1) * 100
    comp = s['compliance_sum'] / max(s['total'], 1)
    acts = np.mean(s['mean_actions'])
    viols = np.mean(s['mean_violations'])
    ho = "HO" if s['is_heldout'] else ""
    print(f"{domain:30s} {ho:>3s} {s['total']:5d} {fa:5.1f}% {comp:6.3f} {acts:8.1f} {viols:6.1f}")

print(f"\n=== 핵심 질문 ===")
print("1. held-out domain 중 특정 domain이 비정상적으로 높은 FA를 보이는가?")
print("2. held-out의 constraint density가 in-domain보다 높은가?")
print("3. held-out에서 action count가 비정상적으로 낮은가? (모델이 뭘 해야 할지 몰라서)")
print("4. in-domain 중에서도 FA가 70%+ 인 domain이 있는가?")

# Held-out graph의 constraint density 확인
print(f"\n=== Held-out Graph Constraint Density ===")
for gf in sorted(glob.glob('cpg_model/graphs/*.yaml')):
    name = os.path.basename(gf).replace('.yaml', '')
    if not any(kw in name.lower() for kw in HELD_OUT_KEYWORDS):
        continue
    try:
        g = yaml.safe_load(open(gf))
        nodes = g.get('nodes', [])
        if isinstance(nodes, dict): nodes = list(nodes.values())
        n_nodes = len(nodes)
        n_rules = len(g.get('conditional_rules', []))
        n_forbidden = sum(len(n.get('forbidden_actions', [])) for n in nodes if isinstance(n, dict))
        n_deadlines = sum(len(n.get('deadlines', {})) for n in nodes if isinstance(n, dict))
        print(f"  {name}: nodes={n_nodes}, rules={n_rules}, forbidden={n_forbidden}, deadlines={n_deadlines}")
    except:
        pass
```

---

## 검증 4: All-oblivious FA 24.1%는 정확한가?

preliminary 스크립트가 compliance_score >= 0.5를 AC pass로 근사했는데, 
실제 evaluator 로직과 다를 수 있다.

```python
import json, glob, os

EPISODES_DIR = "results/full_706_v5"

# 에피소드 1개를 상세히 뜯어본다
sample_files = glob.glob(os.path.join(EPISODES_DIR, "*", "*.json"))[:1]
if sample_files:
    ep = json.load(open(sample_files[0]))
    
    print("=== Episode Fields (evaluator 관련) ===")
    for k in sorted(ep.keys()):
        if any(x in k.lower() for x in ['pass', 'score', 'verdict', 'eval', 'comply', 
                                          'proxy', 'mab', 'ac_', 'c2', 'cwt', 'tcc',
                                          'dxem', 'tom', 'asc', 'paf', 'coverage']):
            val = ep[k]
            print(f"  {k}: {val}")
    
    print(f"\n=== Violation Events 구조 ===")
    viols = ep.get('violation_events', [])
    print(f"  Count: {len(viols)}")
    if viols:
        v = viols[0]
        print(f"  First violation keys: {sorted(v.keys()) if isinstance(v, dict) else type(v)}")
        print(f"  First violation: {json.dumps(v, indent=2)[:500]}")
    
    print(f"\n=== 핵심 질문 ===")
    print("1. 개별 evaluator verdict 필드가 있는가? (ac_proxy_pass, mab_proxy_pass 등)")
    print("2. 있다면 preliminary 스크립트의 근사가 맞는가?")
    print("3. 없다면 실제 evaluator를 돌려야 하는가? (make post-episode)")
    print("4. compliance_score의 정의가 정확히 무엇인가?")

# 실제 evaluator 재실행이 필요한지 확인
print(f"\n=== Evaluator 재채점 필요 여부 ===")
print("만약 episode JSON에 개별 evaluator verdict가 없다면,")
print("중간 결과의 모든 수치는 '근사치'이지 '정확한 값'이 아님.")
print("→ make post-episode 또는 rescore 스크립트가 필요.")
```

---

## 검증 5: Violation type 이름 확인

```
OMISSION 33K, DEVIATION 27K, TIMING 5K, COMMISSION 1K, SEQUENCE 223
```

이 이름들이 논문의 constraint type (FORBIDDEN, WITHIN, BEFORE, MUST)과 
어떻게 매핑되는지 확인해야 한다.

```python
import json, glob, os
from collections import Counter

EPISODES_DIR = "results/full_706_v5"

# 모든 violation type과 필드 구조 수집
all_types = Counter()
sample_by_type = {}

for f in glob.glob(os.path.join(EPISODES_DIR, "*", "*.json"))[:500]:
    try:
        ep = json.load(open(f))
    except: continue
    for v in ep.get('violation_events', []):
        if not isinstance(v, dict): continue
        vtype = v.get('type', 'NO_TYPE')
        all_types[vtype] += 1
        if vtype not in sample_by_type:
            sample_by_type[vtype] = v

print("=== Violation Type 전수 목록 ===")
for vtype, count in all_types.most_common():
    print(f"  {vtype}: {count}")

print(f"\n=== 각 type의 샘플 ===")
for vtype, sample in sorted(sample_by_type.items()):
    print(f"\n--- {vtype} ---")
    print(f"  Keys: {sorted(sample.keys())}")
    # constraint 관련 필드
    for k in ['constraint_type', 'severity', 'action', 'description', 'constraint_id', 'deadline']:
        if k in sample:
            print(f"  {k}: {str(sample[k])[:100]}")

print(f"\n=== 매핑 확인 ===")
print("논문의 constraint type과 episode violation type이 일치하는가?")
print("  FORBIDDEN → COMMISSION?")
print("  WITHIN → TIMING?")
print("  BEFORE → SEQUENCE?")
print("  MUST → OMISSION?")
print("  DEVIATION은 뭔가? (expected에 없는 action을 수행?)")
```

---

## 보고 형식

```markdown
## 비판적 검증 결과

### 검증 1: Model Ordering
- qwen397b mean actions: [N] (다른 모델 대비 [높음/낮음/유사])
- empty action 비율: [N%]
- 판단: [버그/정상/추가확인필요]

### 검증 2: Auto FA 53.4%
- auto-only dominant violation type: [TYPE]
- engine over-generation vs genuine blind spot: [판단]
- 구체 예시: [있으면]

### 검증 3: Held-out FA=77%
- 문제 domain: [어디]
- constraint density 비교: [held-out vs in-domain]
- 판단: [graph 버그/정상/수정 필요]

### 검증 4: All-oblivious FA 24.1%
- 개별 evaluator verdict 필드 존재: [Y/N]
- 근사치 vs 정확값: [판단]
- 실제 재채점 필요: [Y/N]

### 검증 5: Violation type 매핑
- OMISSION = [MUST omission / 기타]
- DEVIATION = [?]
- 논문 용어와 일치: [Y/N/수정필요]

### 결론
- 논문에 즉시 사용 가능한 수치: [목록]
- 추가 검증 필요: [목록]  
- 파이프라인 버그 의심: [목록]
```