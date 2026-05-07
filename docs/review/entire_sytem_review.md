# CGA-Bench 전체 파이프라인 Critical Review

## 왜 이것이 필요한가

4번째 실행 시작. 이전 3번 모두 실행 중 버그 발견으로 폐기:
1차: available_actions 하드코딩 + JSON 파싱 실패
2차: max_tokens=2048 truncation
3차: 프롬프트 버그 (optional action 미생성)

공통 패턴: **각 레이어는 단독 테스트에서 통과했지만, 레이어 간 연결에서 실패.**
이번 검증은 레이어 간 연결부를 집중 점검한다.

---

## 검증 구조: 10개 레이어 × 연결부

```
[1. CPG Graph YAML] 
    ↓ (연결부 A: graph → engine)
[2. Constraint Derivation Engine]
    ↓ (연결부 B: engine → scenarios)
[3. PatientGenerator / ScenarioLoader]
    ↓ (연결부 C: scenario → environment)
[4. Environment (state machine)]
    ↓ (연결부 D: env → agent)
[5. RAG Agent (LLM + normalizer)]
    ↓ (연결부 E: agent actions → env step)
[6. Environment.step() + action_effects]
    ↓ (연결부 F: episode trace → scoring)
[7. Scoring Pipeline (ViolationExtractor + HarmScorer)]
    ↓ (연결부 G: scores → evaluators)
[8. Multi-Evaluator Framework]
    ↓ (연결부 H: evaluators → verdict matrix)
[9. Verdict Matrix + Downstream Analysis]
    ↓ (연결부 I: analysis → paper numbers)
[10. auto_numbers.tex → main.tex]
```

---

## 검증 1: Scoring Pipeline이 새 환경과 독립적인가 (연결부 F)

### 왜 위험한가
채점은 "사후에 전체 trace를 독립적으로 평가"한다고 가정했다. 하지만:
- Runtime CPG engine이 node를 진행하면서 state를 변경
- Scoring CPG engine이 같은 graph를 로드해서 채점
- **두 engine이 같은 인스턴스를 공유하면 scoring이 runtime state에 오염됨**

### 검증 방법
```python
# 1. runtime engine과 scoring engine이 별도 인스턴스인지 확인
# episode runner 코드에서:
# - environment가 사용하는 engine 인스턴스
# - scoring pipeline이 사용하는 engine 인스턴스
# 이 둘의 id()가 다른지 확인

# 2. 같은 episode JSON을 두 번 채점했을 때 동일한 결과가 나오는지
# (첫 채점이 engine state를 변경하면 두 번째 결과가 달라짐)
episode_json = "results/full_706_final/oss120b/SOME_EPISODE.json"
score1 = score_episode(episode_json)
score2 = score_episode(episode_json)
assert score1 == score2, "SCORING IS NOT IDEMPOTENT"

# 3. runtime에서 node가 진행된 후에도 scoring이 전체 trace를 보는지
# scoring이 "현재 활성 노드의 constraint만" 평가하면 violation을 놓침
```

## 검증 2: Episode JSON에 채점에 필요한 모든 정보가 있는가 (연결부 F)

### 왜 위험한가
채점 파이프라인이 episode JSON에서 actions, timestamps, patient_state를 읽는다.
새 환경(CPG 동적 available_actions)에서 JSON 스키마가 달라졌을 수 있다.

### 검증 방법
```python
# 새 실행에서 생성된 episode JSON 1개를 열어서:
import json
ep = json.load(open("results/full_706_final/oss120b/FIRST_EPISODE.json"))

# 1. 필수 필드 존재 확인
required_fields = [
    'scenario_id', 'agent_id', 'actions', 'states', 
    'total_duration_minutes', 'termination_reason'
]
for field in required_fields:
    assert field in ep, f"MISSING FIELD: {field}"

# 2. 각 action에 timestamp가 있는지
for i, action in enumerate(ep['actions']):
    assert 'timestamp_minutes' in action, f"Action {i} missing timestamp"
    assert 'action_id' in action, f"Action {i} missing action_id"
    assert isinstance(action['timestamp_minutes'], (int, float)), f"Action {i} timestamp not numeric"

# 3. timestamps가 단조 증가하는지
timestamps = [a['timestamp_minutes'] for a in ep['actions']]
for i in range(1, len(timestamps)):
    assert timestamps[i] >= timestamps[i-1], f"Non-monotonic timestamp at action {i}"

# 4. action_id가 canonical action alphabet에 있는지
# (normalizer가 제대로 매핑했으면 모두 canonical이어야 함)
```

## 검증 3: ActionNormalizer가 모든 모델 출력을 커버하는가 (연결부 D-E)

### 왜 위험한가
Agent가 "give_antibiotics"라고 출력하면 normalizer가 "give_broad_spectrum_antibiotics"로 매핑해야 한다.
매핑 실패 시 action이 reject되어 에피소드가 인위적으로 짧아짐.
이것이 이전에 "Qwen 6 actions" 문제의 일부였을 수 있음.

### 검증 방법
```python
# 1. dry-run 5개 에피소드에서 reject된 action 전수 조사
# 로그에서 "Rejecting action" 또는 "not in available_actions" 메시지 수집
grep -c "Rejecting\|not in available" results/full_706_final/log_*.txt

# 2. reject된 action의 실제 내용 확인
grep "Rejecting" results/full_706_final/log_*.txt | head -20
# 이 action들이 정말로 invalid한지, 아니면 normalizer 매핑이 부족한지 판단

# 3. 모델별 reject rate 비교
# oss120b와 Qwen의 reject rate가 크게 다르면 normalizer가 특정 모델의 출력 형식에 편향
```

## 검증 4: Timing Model 정확성 (연결부 E-F)

### 왜 위험한가
WITHIN constraint는 "action X를 Y분 내에 수행"이다.
Environment가 시간을 잘못 진행하면 timing violation이 artifact가 된다.
self-critical-review #19에서 리뷰어가 "timing validity audit"를 요구했다.

### 검증 방법
```python
# 1. Environment의 시간 진행 모델 확인
# 각 action 후 시간이 얼마나 증가하는지
# action_type별로 다른지, 고정 5분인지

# 2. 에피소드에서 timing violation이 발생한 action 확인
# violation의 deadline과 actual timestamp를 비교
# deadline이 비현실적이면 graph 문제, timestamp가 비현실적이면 env 문제

# 3. 같은 action sequence를 두 번 실행했을 때 timestamps가 동일한지 (determinism)
```

## 검증 5: Perturbation Pipeline 정확성 (E1 실험)

### 왜 위험한가
E1은 논문의 hero evidence다. Matched pair를 만들 때:
- Safe variant: d_G = 0 (conformant)
- Unsafe variant: 정확히 1개 violation만 추가

Perturbation 코드에 버그가 있으면 논문의 핵심 주장이 무효화된다.

### 검증 방법
```python
# 1. Perturbation 코드 위치 확인
find . -name "*.py" | xargs grep -l "perturbation\|matched_pair\|inject_violation"

# 2. 각 perturbation type별 1개씩 수동 검증:
# - WITHIN: safe에 없는 timing delay가 unsafe에만 있는지
# - BEFORE: safe의 action 순서가 unsafe에서 뒤바뀌었는지
# - FORBID: safe에 없는 forbidden action이 unsafe에만 있는지
# - MUST: safe에 있는 required action이 unsafe에서 빠졌는지

# 3. 중요: perturbation이 terminal output을 보존하는지
# safe와 unsafe의 final diagnosis가 동일해야 함
```

## 검증 6: Evaluator 구현 정확성 (연결부 G)

### 왜 위험한가
6개 evaluator 중 하나라도 버그가 있으면 verdict matrix 전체가 틀림.
특히 concept-level evaluator (TOM, ASC, PAF, CwT, TCC)가 실제로 논문 설명대로 동작하는지.

### 검증 방법
```python
# 1. 각 evaluator에 known-answer 테스트
# 수동으로 만든 3개 trace:
# - trace_perfect: 모든 constraint 만족 → 모든 evaluator pass
# - trace_timing_only: timing violation만 있음 → TCC만 fail, 나머지 pass
# - trace_forbidden_only: forbidden violation만 → TCC fail, PAF가 잡는지?

# 2. TCC의 BSR=0 by construction 검증
# TCC가 fail한 에피소드에서 실제로 hard violation이 있는지 전수 확인
# TCC가 pass한 에피소드에서 hard violation이 없는지 전수 확인

# 3. DxEM이 정말 모든 에피소드를 pass하는지 확인
# (degenerate evaluator이므로 pass rate = 100%이어야 함)
```

## 검증 7: Scenario-Graph 매핑 (연결부 B-C)

### 왜 위험한가
706개 시나리오가 각각 올바른 CPG graph에 매핑되어야 한다.
Graph ID 이중화 통일 작업을 했는데, 일부가 잘못 매핑되었을 수 있다.

### 검증 방법
```python
# 1. 모든 시나리오의 graph_id가 실제 존재하는 graph 파일을 가리키는지
import yaml, glob
graph_files = {f.split('/')[-1].replace('.yaml','') 
               for f in glob.glob('cpg_model/graphs/*.yaml') 
               if '_archive' not in f}

for scenario_file in glob.glob('configs/scenarios/*.yaml'):
    with open(scenario_file) as f:
        data = yaml.safe_load(f)
    scenarios = data if isinstance(data, list) else data.get('scenarios', [data])
    for s in scenarios:
        graph_id = s.get('graph_id', s.get('cpg_graph', ''))
        if graph_id and graph_id not in graph_files:
            print(f"BROKEN LINK: {s.get('scenario_id')} → {graph_id}")

# 2. 18개 새 pathway normal이 올바른 graph에 매핑되었는지 별도 확인
```

## 검증 8: Run Determinism (연결부 전체)

### 왜 위험한가
논문에서 η²(run) = 0.04%라고 주장한다. 하지만:
- LLM seed가 제대로 설정되지 않으면 run 간 variance가 크다
- Environment의 state machine이 비결정적이면 같은 action sequence에서 다른 결과
- random seed가 고정 안 되어 있으면 PatientGenerator의 출력이 달라짐

### 검증 방법
```python
# 같은 시나리오 + 같은 모델 + 같은 seed로 2번 실행
# episode JSON이 동일해야 함 (또는 LLM 출력의 자연 variance만 있어야 함)

# 확인: run_episodes.py에서 seed 설정이 어디서 되는지
grep -n "seed\|random\|np.random" scripts/run_episodes.py  # 실제 파일명
```

## 검증 9: Cross-Model GPU 격리 (인프라)

### 왜 위험한가
5개 모델이 동시에 vLLM 서버를 사용한다. 만약:
- 같은 vLLM 인스턴스에 여러 모델을 로드하면 응답이 섞일 수 있음
- GPU OOM으로 일부 요청이 실패하지만 에러 대신 빈 응답을 반환할 수 있음

### 검증 방법
```bash
# 1. 각 모델이 별도 vLLM 프로세스/포트를 사용하는지
ps aux | grep vllm
# 모델당 1개 프로세스가 있어야 함

# 2. GPU 할당 확인
nvidia-smi
# 모델이 어떤 GPU에 있는지, OOM 위험이 없는지

# 3. episode JSON에서 model_id가 올바른지
# oss120b 디렉토리의 에피소드에 qwen 응답이 섞여 있으면 안 됨
python3 -c "
import json, glob
for m in ['oss120b','qwen35b','qwen397b']:
    files = glob.glob(f'results/full_706_final/{m}/*.json')
    if files:
        ep = json.load(open(files[0]))
        print(f'Dir: {m}, agent_id: {ep.get(\"agent_id\",\"?\")}, model: {ep.get(\"model\",\"?\")}')"
```

## 검증 10: 3 Runs 설정 (실행 구성)

### 왜 위험한가
706 × 5 × 3 = 10,590이어야 하는데, runner가 실제로 3 runs를 생성하는지.
run_id별로 다른 seed를 사용해야 run variance 측정이 의미가 있다.

### 검증 방법
```bash
# 모델 하나에서 같은 시나리오의 에피소드가 3개 있는지
ls results/full_706_final/oss120b/ | grep "septic_shock_basic" | wc -l
# 3이어야 함

# 3개의 파일명에 r0, r1, r2 또는 다른 run 식별자가 있는지
ls results/full_706_final/oss120b/ | grep "septic_shock_basic"

# 3개의 action 수가 약간 다른지 (같으면 같은 seed, 즉 복사)
python3 -c "
import json, glob
files = sorted(glob.glob('results/full_706_final/oss120b/*septic_shock_basic*.json'))
for f in files:
    ep = json.load(open(f))
    print(f'{f.split(\"/\")[-1]}: actions={len(ep.get(\"actions\",[]))}')"
```

---

## 실행 순서

에피소드가 돌고 있는 동안 병렬로 실행 가능. 우선순위:

1. **검증 1 (Scoring 독립성)** — 가장 치명적. 오염되면 모든 수치가 틀림
2. **검증 2 (Episode JSON 스키마)** — 1번과 연결. 스키마 깨지면 채점 불가
3. **검증 6 (Evaluator 정확성)** — known-answer test. 버그 있으면 verdict matrix 전체 무효
4. **검증 3 (Normalizer 커버리지)** — reject rate이 높으면 에피소드 품질 문제
5. **검증 4 (Timing model)** — timing violation이 dominant signal이므로 정확해야 함
6. **검증 9 (GPU 격리)** — 즉시 확인 가능 (ps + nvidia-smi)
7. **검증 10 (3 runs)** — 1시간 후 에피소드 나오면 확인
8. **검증 7 (Scenario-Graph 매핑)** — 이미 한 번 했지만 18개 추가분 재확인
9. **검증 8 (Determinism)** — 시간 되면
10. **검증 5 (Perturbation)** — 에피소드 완료 후

**이 10개 검증 스크립트를 하나의 파일로 만들어서 실행하라.
각 검증의 결과를 PASS/FAIL/WARNING으로 보고하라.
FAIL이 하나라도 있으면 즉시 보고하라.**