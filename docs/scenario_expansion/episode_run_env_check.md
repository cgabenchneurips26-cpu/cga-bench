> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# Task: 690개 시나리오 에피소드 실행 환경 파악 + 실행 계획

## GPU 환경

| 서버 | GPU | 모델 | 접근 방법 |
|------|-----|------|----------|
| 외부 127.0.0.1 | GPU 0-3 (종류 미확인) | Qwen3.5-397B-A17B-FP8 (이미 serving 중) | OpenAI-compatible API, port 30001 |
| 로컬 | A100 80GB × 8 (GPU 0-7) | 나머지 4 모델 (vLLM으로 serve) | 로컬 vLLM |

## Step 1: 기존 실행 코드 파악

기존에 episode 실행에 사용한 코드와 parallel.py를 찾아서 구조를 파악하라.

```bash
# 1. parallel.py 찾기
find . -name "parallel*.py" -o -name "run_parallel*.py" -o -name "*parallel*" | grep -v __pycache__ | grep -v .git

# 2. 기존 episode runner 찾기
find . -name "run_benchmark*.py" -o -name "run_episode*.py" -o -name "run_experiment*.py" | grep -v __pycache__

# 3. 기존 model config 찾기 (pipeline audit에서 configs/models/ 비어있었음)
find . -name "*.yaml" -path "*/config*" | grep -i model | head -20
find . -name "*.yaml" | xargs grep -l "model_name\|backend.*vllm\|backend.*openai" 2>/dev/null | head -20

# 4. 기존 181 episodes가 어떤 명령으로 생성되었는지 히스토리 확인
ls -la results/clean_slate_rescored/
ls results/clean_slate_rescored/ | head -20

# 5. 기존 episode JSON의 구조에서 실행 config 추출
python -c "
import json
from pathlib import Path
eps = list(Path('results/clean_slate_rescored/').glob('**/*.json'))
if eps:
    with open(eps[0]) as f:
        ep = json.load(f)
    print('Keys:', list(ep.keys()))
    print('agent_id:', ep.get('agent_id'))
    print('model_name:', ep.get('model_name'))
    print('scenario_id:', ep.get('scenario_id'))
    # config 정보가 있으면 출력
    for key in ['config', 'agent_config', 'model_config', 'experiment_config']:
        if key in ep:
            print(f'{key}:', ep[key])
"

# 6. run_benchmark.py의 argument 확인
python run_benchmark.py --help 2>&1 || echo "run_benchmark.py not found or error"

# 7. parallel.py 내용 확인
for f in $(find . -name "parallel*.py" | grep -v __pycache__); do
    echo "=== $f ==="
    head -50 "$f"
    echo ""
done

# 8. Makefile의 episode 관련 타겟 확인
grep -A 5 "episode\|benchmark\|run" Makefile 2>/dev/null || echo "No Makefile or no matching targets"

# 9. experiment config 확인
ls configs/experiments/ 2>/dev/null
for f in configs/experiments/*.yaml; do
    echo "=== $f ==="
    head -30 "$f"
    echo ""
done 2>/dev/null

# 10. vLLM serving 스크립트 찾기
find . -name "serve*.py" -o -name "serve*.sh" -o -name "start_vllm*.sh" | grep -v __pycache__
```

**위 10개를 모두 실행하고 결과를 raw로 보고하라.**

## Step 2: 실행 계획 수립 (Step 1 결과 기반)

Step 1에서 파악한 코드 구조에 맞게 실행 계획을 구체화한다.

### 2A. 모델 serving 계획

```
외부 서버 (127.0.0.1
  - Qwen3.5-397B: 이미 serving 중 (port 30001)
  - 추가 모델: GPU 0-3이 397B에 전부 사용 중인지 확인 필요
    → 397B는 FP8이라도 4 GPU 필요할 수 있음

로컬 서버 (A100 ×8):
  - GPU 0-1: openai/gpt-oss-120b (vLLM, ~120B → 2 GPU tensor parallel)
  - GPU 2-3: Qwen3.5-35B-A3B-FP8 (vLLM, ~35B → 1-2 GPU)
  - GPU 4:   Qwen3-4B (vLLM, ~4B → 1 GPU)
  - GPU 5:   DeepSeek-R1-Distill-7B (vLLM, ~7B → 1 GPU)
  - GPU 6-7: 여유 (or oss-120b에 4 GPU 할당)
```

### 2B. 실행 매트릭스

```
690 scenarios × 5 models × 3 runs = 10,350 episodes

Model별:
  - Qwen3.5-397B:       690 × 3 = 2,070 episodes (외부 서버)
  - gpt-oss-120b:       690 × 3 = 2,070 episodes (로컬)
  - Qwen3.5-35B:        690 × 3 = 2,070 episodes (로컬)
  - Qwen3-4B:           690 × 3 = 2,070 episodes (로컬)
  - DeepSeek-R1-7B:     690 × 3 = 2,070 episodes (로컬)
```

### 2C. parallel.py 활용 방안

기존 parallel.py의 구조를 파악한 후, 다음을 지원하도록 확장/수정:

```python
# 예상 구조
class ParallelRunner:
    def __init__(self, 
                 scenario_list: List[str],
                 model_configs: List[dict],
                 runs_per_scenario: int = 3,
                 max_workers: int = 4):
        ...
    
    def run_all(self):
        # 각 (scenario, model, run) 조합을 병렬 실행
        ...
```

필요한 수정:
1. **외부 서버 모델 지원**: OpenAI-compatible endpoint로 접근
2. **로컬 vLLM 모델 지원**: 로컬 vLLM endpoint로 접근
3. **GPU 할당**: 모델별 GPU 지정
4. **체크포인트/재시작**: 중간에 중단되어도 이어서 실행
5. **실패 로깅**: timeout, crash, empty trace 분류

### 2D. 모델 Config 형식

기존 config 파일 구조를 파악한 후, 5개 모델 config를 생성한다.

```yaml
# 예상 구조 (실제는 Step 1 결과에 맞게 조정)
model_name: "Qwen/Qwen3.5-397B-A17B-FP8"
backend: openai_compatible  # 또는 vllm
base_url: "http://localhost:8013/v1"
api_key: "sk-no-key-required"
scaffold: rag
parameters:
  temperature: 0.7
  max_tokens: 1024
```

## Step 3: Dry Run

실행 계획이 수립되면 각 모델에 대해 1 scenario × 1 run dry-run:

```bash
# 397B (외부)
python run_benchmark.py --scenario septic_shock_basic --model qwen397b --runs 1

# oss-120b (로컬)
python run_benchmark.py --scenario septic_shock_basic --model oss120b --runs 1

# ... 5개 모델 전부
```

## Step 4: 본실행

dry-run 성공 후 parallel.py 또는 실행 스크립트로 전체 실행.

```bash
# 예상 명령 (Step 1 결과에 맞게 조정)
python parallel.py \
    --scenario-list configs/scenario_list_full.txt \
    --models qwen397b,oss120b,qwen35,qwen4b,deepseek_r1 \
    --runs 3 \
    --output results/full_run_20260403/ \
    --checkpoint results/full_run_20260403/checkpoint.json
```

---

## Deliverable

Step 1의 결과를 모두 보고한 후, 다음을 제시하라:
1. **기존 코드 구조 요약** (어떤 파일이 뭘 하는지)
2. **5개 모델 config YAML** (기존 형식에 맞게)
3. **실행 명령어** (dry-run + 본실행)
4. **시간 추정** (모델별, 전체)
5. **모니터링 방법** (진행률, 실패 탐지)