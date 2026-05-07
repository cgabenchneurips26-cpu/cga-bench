# Claude Code 세션 프롬프트: 에피소드 체계적 Self-Review

## 배경

수동으로 에피소드 1개(apa_agitation/qwen35b)를 검증했더니 시스템 버그가 발견됨:
- `attempt_verbal_deescalation`이 t=20m에 수행되었는데 OMISSION으로 기록 (TIMING이어야 함)
- DEVIATION 3건이 trace에 없는 action을 참조 (normalizer artifact)

이게 **1개 에피소드에서 우연히 발견**된 것이라, 다른 에피소드에서도 같은/다른 유형의 버그가 있을 수 있음.
체계적으로 20-30개 에피소드를 수동 수준으로 검증해야 함.

## 작업

### Step 1: 다양한 에피소드 샘플링 (20-30개)

아래 카테고리에서 골고루 선택:

```python
import json, glob, random
from collections import defaultdict

episodes = []
for f in glob.glob('results/full_706_final/*/*.json'):
    try:
        ep = json.load(open(f))
        ep['_file'] = f
        ep['_model'] = f.split('/')[-2]
        episodes.append(ep)
    except:
        pass

# 카테고리별 1-2개씩:
categories = {
    'timing_heavy': [],      # TIMING violation이 3개 이상
    'omission_heavy': [],    # OMISSION이 5개 이상  
    'commission': [],        # COMMISSION이 1개 이상
    'sequence': [],          # SEQUENCE violation이 있는 것
    'mixed': [],             # 3가지 이상 violation type
    'zero_violation': [],    # violation 0개 (TCC=pass)
    'high_compliance': [],   # compliance > 0.9
    'low_compliance': [],    # compliance < 0.2
    'held_out': [],          # held-out graph (aba_burn, aabb, acog, pals, apa)
}

# 다양한 graph에서:
unique_graphs = set()
# 다양한 model에서:
unique_models = set()

for ep in episodes:
    viols = ep.get('violation_events', [])
    if not isinstance(viols, list):
        continue
    
    types = set()
    type_counts = defaultdict(int)
    for v in viols:
        if isinstance(v, dict):
            vt = v.get('violation_type', v.get('type', '')).upper()
            types.add(vt)
            if 'OMISSION' in vt: type_counts['OMISSION'] += 1
            elif 'TIMING' in vt or 'WITHIN' in vt: type_counts['TIMING'] += 1
            elif 'COMMISSION' in vt or 'FORBID' in vt: type_counts['COMMISSION'] += 1
            elif 'SEQUENCE' in vt or 'BEFORE' in vt: type_counts['SEQUENCE'] += 1
    
    graph_id = ep.get('graph_id', ep.get('cpg_graph', ''))
    model = ep.get('_model', '')
    
    if type_counts['TIMING'] >= 3 and len(categories['timing_heavy']) < 3:
        categories['timing_heavy'].append(ep)
    elif type_counts['OMISSION'] >= 5 and len(categories['omission_heavy']) < 3:
        categories['omission_heavy'].append(ep)
    # ... 등등

# 최종 30개 에피소드를 selected_episodes.json으로 저장
```

**핵심**: 같은 graph에서만 뽑지 말 것. 최소 10개 다른 graph, 5개 다른 model에서 뽑아야 함.

### Step 2: 각 에피소드에 대해 수동 수준 검증

각 에피소드에 대해 아래 절차를 수행:

#### 2a. Graph에서 active constraints 확인
```python
# 해당 scenario의 graph YAML 로드
graph = yaml.safe_load(open(f'cpg_model/graphs/{graph_id}.yaml'))

# 해당 node들의 mandatory/forbidden/deadline/sequence 추출
for node in graph['nodes']:
    mandatory = node.get('mandatory_actions', node.get('expected_actions', []))
    forbidden = node.get('forbidden_actions', [])
    deadlines = node.get('deadlines', [])
    sequence = node.get('sequence_rules', [])
    # 기록
```

#### 2b. Action trace와 대조
```python
performed_actions = [(a['action'], a.get('timestamp', i*5)) for i, a in enumerate(ep['actions'])]

for mandatory_action in all_mandatory:
    performed = any(a == mandatory_action for a, t in performed_actions)
    if performed:
        # 시간 확인 — deadline 내인가?
        perform_time = next(t for a, t in performed_actions if a == mandatory_action)
        deadline = deadlines.get(mandatory_action, None)
        if deadline and perform_time > deadline:
            expected_violation = 'TIMING'
        else:
            expected_violation = None
    else:
        expected_violation = 'OMISSION'
```

#### 2c. System violation과 비교
```python
system_violations = ep['violation_events']

for v in system_violations:
    # 이 violation이 올바른지 확인:
    # 1. OMISSION인데 실제로 performed에 있는가? → FALSE OMISSION
    # 2. COMMISSION인데 실제로 forbidden에 있는가? → 맞는지 확인
    # 3. TIMING인데 실제로 deadline을 넘겼는가? → margin 확인
    # 4. SEQUENCE인데 실제로 순서가 역전되었는가?
    # 5. DEVIATION인데 실제로 action이 trace에 있는가?
```

#### 2d. 빠진 violation 확인
```python
# 내가 기대하는 violation이 system에 없는 경우도 체크
# 예: forbidden action을 수행했는데 COMMISSION이 없으면 → 감지 실패
```

### Step 3: 결과 정리

각 에피소드에 대해 아래 표 작성:

```
Episode: {file}
Model: {model}, Graph: {graph_id}, Compliance: {score}

System Violations: N개
Manual Expected Violations: M개

| # | System Violation | Type | Action | Manual Assessment | Match? |
|---|-----------------|------|--------|-------------------|--------|
| 1 | OMISSION X      | ...  | ...    | FALSE OMISSION    | 🔴    |

Missing (expected but not in system): 
| # | Expected Type | Action | Reason system missed |
|---|--------------|--------|---------------------|
| 1 | TIMING       | X      | Recorded as OMISSION |

False (in system but shouldn't be):
| # | System Type | Action | Why false |
|---|-------------|--------|-----------|
```

### Step 4: 패턴 분류

30개 에피소드 검증 후 발견된 이슈를 분류:

```
BUG TYPE A: OMISSION for late-performed actions
  - 발생 빈도: N/30 에피소드
  - 영향: OMISSION rate 과대 추정
  - 수정: ViolationExtractor에서 performed 체크 추가

BUG TYPE B: DEVIATION for phantom actions  
  - 발생 빈도: N/30 에피소드
  - 영향: DEVIATION count 과대
  - 수정: Normalizer output과 trace 정합성 체크

BUG TYPE C: [새로 발견되는 유형]
  - ...
```

### Step 5: quantify_omission_timing_overlap.py 실행

위 수동 검증과 병행하여, 전체 에피소드에서 정량화:
```bash
python scripts/risk_mitigation/quantify_omission_timing_overlap.py --episodes-dir results/full_706_final
```

### Step 6: 종합 보고서

```
SYSTEM SELF-REVIEW 결과
━━━━━━━━━━━━━━━━━━━━━━
검증 에피소드: 30개 (10 graphs × 5 models × 다양한 violation profile)

| Bug Type | Frequency | Impact | Fix |
|----------|-----------|--------|-----|
| A: Late→OMISSION | N/30 (X%) | OMISSION rate -Y% | ViolationExtractor |
| B: Phantom DEVIATION | N/30 (X%) | Minor | Normalizer |
| C: ... | ... | ... | ... |

전체 정량화 (quantify 스크립트):
- FALSE OMISSION: X% of all OMISSIONs
- DOUBLE COUNT: Y% 
- TRUE OMISSION: Z%

논문 영향:
- FA rate 변화: [계산]
- BSR 변화: [계산]
- 수정 필요 여부: [판단]
```

## 주의사항

1. **Normalizer를 고려할 것**: action 매칭 시 raw string 비교가 아닌, 현재 normalizer를 통과시킨 후 비교. normalizer가 import 가능하면 직접 사용:
```python
from cpg_model.action_normalizer import ActionNormalizer
normalizer = ActionNormalizer()
normalized = normalizer.normalize(raw_action)
```

2. **Conditional rules 확인**: patient context에 따라 어떤 conditional rule이 activate되는지 확인. scenario YAML의 patient 필드를 graph의 conditional_rules condition과 대조.

3. **다양한 graph 필수**: apa_agitation에서만 검증하면 그 graph 특유의 문제만 찾음. sepsis, stroke, aki, acls, stemi 등 다양한 도메인에서 검증.

4. **Edge case 포함**: violation 0개인 에피소드도 검증 — "진짜 violation이 없는 건지, 감지 못 한 건지" 확인.

## 성공 기준

- 최소 20개 에피소드, 10개 이상 다른 graph에서 검증 완료
- 발견된 bug type 분류 + 빈도 + 영향 범위 정량화
- 논문 수치에 영향을 주는 버그가 있으면 수정 방안 제시