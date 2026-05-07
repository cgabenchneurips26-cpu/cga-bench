# E8: Cross-Benchmark Blind-Spot Audit — 실행 프롬프트

## 목적
MedAgentBench 300 episodes + AgentClinic 122 episodes를 CGA-Bench TCC evaluator로 채점하여,
"native scorer가 pass한 에피소드 중 TCC가 violation을 발견하는 비율"을 계산한다.
이 결과는 논문의 **E8: Cross-Benchmark Portability** 실험으로 들어간다.

## 배경
- 리뷰어 #16: "native scorer를 안 돌려봤다"
- 리뷰어 #17: "counterfactual replay with official scorers"
- 이 실험이 성공하면 두 공격이 동시에 해소됨

---

## Step 1: 데이터 현황 확인

```bash
# 1-1. MAB 에피소드 구조 확인
echo "=== MAB episode structure ==="
head -1 data/episodes/medagentbench_observed_safety3_audit4.jsonl | python3 -c "
import json, sys
ep = json.loads(sys.stdin.readline())
print('Keys:', list(ep.keys()))
# native score 필드 찾기
for key in ['score', 'task_success', 'success', 'pass', 'result', 'evaluation', 'grading', 'native_score']:
    if key in ep:
        print(f'  Native score field: {key} = {ep[key]}')
# action 필드 찾기
for key in ['actions', 'steps', 'trajectory', 'trace', 'events', 'interactions']:
    if key in ep:
        val = ep[key]
        print(f'  Actions field: {key} (type={type(val).__name__}, len={len(val) if isinstance(val, list) else \"N/A\"})')
# domain/scenario 필드 찾기
for key in ['task', 'scenario', 'domain', 'category', 'clinical_domain', 'task_id']:
    if key in ep:
        print(f'  Domain field: {key} = {str(ep[key])[:100]}')
"

# 1-2. AC 에피소드 구조 확인
echo ""
echo "=== AC episode structure ==="
head -1 data/episodes/agentclinic_converted.jsonl | python3 -c "
import json, sys
ep = json.loads(sys.stdin.readline())
print('Keys:', list(ep.keys()))
for key in ['score', 'success', 'pass', 'result', 'evaluation', 'diagnosis_correct', 'native_score']:
    if key in ep:
        print(f'  Native score field: {key} = {ep[key]}')
for key in ['actions', 'steps', 'trajectory', 'trace', 'events', 'interactions', 'conversation']:
    if key in ep:
        val = ep[key]
        print(f'  Actions field: {key} (type={type(val).__name__}, len={len(val) if isinstance(val, list) else \"N/A\"})')
for key in ['task', 'scenario', 'domain', 'category', 'clinical_domain', 'scenario_id', 'disease']:
    if key in ep:
        print(f'  Domain field: {key} = {str(ep[key])[:100]}')
"

# 1-3. native score 분포
echo ""
echo "=== Native score distributions ==="
python3 -c "
import json
# MAB
with open('data/episodes/medagentbench_observed_safety3_audit4.jsonl') as f:
    mab = [json.loads(l) for l in f]
print(f'MAB: {len(mab)} episodes')
# 가능한 score 필드 자동 탐지
score_fields = [k for k in mab[0].keys() if any(s in k.lower() for s in ['score', 'success', 'pass', 'result', 'eval'])]
for sf in score_fields:
    vals = [ep.get(sf) for ep in mab if ep.get(sf) is not None]
    if vals:
        if isinstance(vals[0], (int, float, bool)):
            pass_count = sum(1 for v in vals if (v == True or v == 1 or (isinstance(v, float) and v >= 0.5)))
            print(f'  {sf}: {pass_count}/{len(vals)} pass ({100*pass_count/len(vals):.1f}%)')

# AC
with open('data/episodes/agentclinic_converted.jsonl') as f:
    ac = [json.loads(l) for l in f]
print(f'AC: {len(ac)} episodes')
score_fields = [k for k in ac[0].keys() if any(s in k.lower() for s in ['score', 'success', 'pass', 'result', 'eval', 'diagnosis'])]
for sf in score_fields:
    vals = [ep.get(sf) for ep in ac if ep.get(sf) is not None]
    if vals:
        if isinstance(vals[0], (int, float, bool)):
            pass_count = sum(1 for v in vals if (v == True or v == 1 or (isinstance(v, float) and v >= 0.5)))
            print(f'  {sf}: {pass_count}/{len(vals)} pass ({100*pass_count/len(vals):.1f}%)')
"
```

---

## Step 2: 기존 Replay 스크립트 확인

```bash
# 2-1. MAB replay 스크립트 구조 파악
echo "=== MAB replay script ==="
head -50 scripts/experiments/v3_p1b_medagentbench_replay.py

echo ""
echo "=== AC replay script ==="
head -50 scripts/experiments/v3_p1a_agentclinic_replay.py

# 2-2. run_external_benchmark.py 진입점 확인
echo ""
echo "=== External benchmark runner ==="
head -80 run_external_benchmark.py
```

이 스크립트들의 실행 방법과 출력 형식을 파악하라.
특히:
- 입력: 에피소드 JSONL 파일
- adapter를 통해 CGA-Bench trace로 변환
- TCC evaluator로 채점
- 출력: violation 탐지 결과

---

## Step 3: Cross-Benchmark Replay 실행

### 3-1. MAB Replay (300 episodes)

기존 replay 스크립트를 사용하거나, 아래 로직으로 직접 실행:

```python
"""
Cross-benchmark replay: MedAgentBench episodes → CGA-Bench TCC
"""
import json
import sys
sys.path.insert(0, '.')

from env.adapters.medagentbench_adapter import MedAgentBenchAdapter
# TCC evaluator import (실제 경로에 맞게 조정)
# from cpg_model.engine import CPGEngine
# from assessor.scoring.violation_detector import ViolationDetector

def run_cross_benchmark_audit(episodes_path, adapter_class, benchmark_name):
    """
    1. 에피소드 로드
    2. adapter로 CGA-Bench trace 변환
    3. TCC 채점
    4. native_pass + tcc_fail 카운트
    """
    with open(episodes_path) as f:
        episodes = [json.loads(l) for l in f]
    
    adapter = adapter_class()
    
    results = {
        'total': len(episodes),
        'converted': 0,
        'conversion_failed': 0,
        'native_pass': 0,
        'native_fail': 0,
        'tcc_pass': 0,
        'tcc_fail': 0,
        'native_pass_tcc_fail': 0,  # ← 핵심 수치: blind spot
        'native_pass_tcc_pass': 0,
        'native_fail_tcc_fail': 0,
        'native_fail_tcc_pass': 0,
        'violations_in_blind_spot': [],
    }
    
    for ep in episodes:
        # 1. Native score 추출 (필드명은 Step 1에서 확인)
        native_pass = ep.get('task_success', ep.get('success', ep.get('score', 0)))
        if isinstance(native_pass, (int, float)):
            native_pass = native_pass >= 0.5
        
        if native_pass:
            results['native_pass'] += 1
        else:
            results['native_fail'] += 1
        
        # 2. Adapter 변환
        try:
            trace = adapter.convert(ep)  # 메서드명은 실제 구현에 맞게
            results['converted'] += 1
        except Exception as e:
            results['conversion_failed'] += 1
            continue
        
        # 3. TCC 채점
        # violations = tcc_evaluate(trace)  # 실제 TCC evaluator 호출
        # tcc_pass = len([v for v in violations if v.is_hard]) == 0
        
        # 4. Cross-tabulation
        # if native_pass and not tcc_pass:
        #     results['native_pass_tcc_fail'] += 1
        #     results['violations_in_blind_spot'].extend(violations)
        # ... etc
    
    return results

# 실행
# mab_results = run_cross_benchmark_audit(
#     'data/episodes/medagentbench_observed_safety3_audit4.jsonl',
#     MedAgentBenchAdapter,
#     'MedAgentBench'
# )
# print(json.dumps(mab_results, indent=2))
```

위 코드는 **골격**이다. 실제 import 경로와 메서드명을 기존 replay 스크립트
(v3_p1b_medagentbench_replay.py)에서 가져와서 완성하라.

### 3-2. AC Replay (122 episodes)

동일 패턴으로 AgentClinic adapter 사용.

---

## Step 4: 결과 보고

아래 형식으로 결과를 정리하라:

```markdown
## E8: Cross-Benchmark Blind-Spot Audit 결과

### MedAgentBench (N=300)
| Metric | Value |
|--------|-------|
| Conversion success | N/300 (N%) |
| Native pass rate | N% |
| TCC pass rate | N% |
| **Blind-spot rate** (native pass + TCC fail) | **N%** |
| Violation types in blind spots | FORBIDDEN: N, WITHIN: N, BEFORE: N |
| Domain coverage | sepsis, chest_pain, ... |

### AgentClinic (N=122)
| Metric | Value |
|--------|-------|
| Conversion success | N/122 (N%) |
| Native pass rate | N% |
| TCC pass rate | N% |
| **Blind-spot rate** (native pass + TCC fail) | **N%** |

### Cross-Benchmark Agreement
| | TCC Pass | TCC Fail |
|---|---------|----------|
| **Native Pass** | N (true positive) | **N (blind spot)** |
| **Native Fail** | N (false negative) | N (true negative) |
```

---

## Step 5: 논문 매크로 생성

결과를 아래 매크로로 출력:

```
\newcommand{\crossMABTotal}{300}
\newcommand{\crossMABConverted}{??}
\newcommand{\crossMABNativePass}{??}
\newcommand{\crossMABBlindSpot}{??}       % native pass + TCC fail
\newcommand{\crossMABBlindSpotPct}{??}    % as percentage of native pass
\newcommand{\crossACTotal}{122}
\newcommand{\crossACConverted}{??}
\newcommand{\crossACNativePass}{??}
\newcommand{\crossACBlindSpot}{??}
\newcommand{\crossACBlindSpotPct}{??}
```

---

## 우선순위

1. **먼저** Step 1 (데이터 확인)과 Step 2 (기존 스크립트 파악)를 완료
2. 기존 replay 스크립트가 동작하면 그걸 바로 사용
3. 동작 안 하면 Step 3의 골격을 기존 코드 기반으로 완성
4. 결과가 나오면 Step 4, 5 형식으로 보고

**핵심 목표**: "MedAgentBench가 pass한 에피소드 N개 중 M개(X%)에서 
CGA-Bench TCC가 hard violation을 발견" — 이 한 줄이 논문에 들어가면 
리뷰어 #16, #17이 동시에 해소된다.