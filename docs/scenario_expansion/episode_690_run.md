> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# Task: 690 시나리오 에피소드 실행

## Step 1: 외부 서버 연결 확인

```bash
# 397B 서버 상태 확인
curl -s http://localhost:8013/v1/models 2>&1 || echo "CONNECTION FAILED"

# 연결되면 간단한 completion 테스트
python -c "
from openai import OpenAI
client = OpenAI(base_url='http://localhost:8013/v1', api_key='sk-no-key-required')
try:
    response = client.chat.completions.create(
        model='Qwen/Qwen3.5-397B-A17B-FP8',
        messages=[{'role': 'user', 'content': 'Say hello'}],
        max_tokens=10,
        temperature=0.0,
    )
    print(f'397B OK: {response.choices[0].message.content}')
except Exception as e:
    print(f'397B FAIL: {e}')
"
```

**결과에 따라:**
- 연결 성공 → 5 models (397B 포함)
- 연결 실패 → 4 models로 진행, 397B는 서버 복구 후 별도 실행

## Step 2: 현재 serving 확인 + Port 정리

```bash
# 로컬 모든 vLLM endpoint 상태 확인
for port in 8013 8015 8017 8101 28000 28010; do
    result=$(curl -s http://localhost:$port/v1/models 2>&1)
    if echo "$result" | grep -q "model"; then
        model=$(echo "$result" | python -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null)
        echo "Port $port: SERVING $model"
    else
        echo "Port $port: NOT RESPONDING"
    fi
done
```

## Step 3: clean_slate_runner.py 수정

기존 `scripts/experiments/clean_slate_runner.py`를 읽어서 구조를 파악하고, 690 시나리오 + 5 모델을 지원하도록 수정한다.

```bash
# 기존 코드 전체 확인
cat scripts/experiments/clean_slate_runner.py
```

### 수정 사항:

**3A. SCENARIOS 리스트 → 파일에서 로드**

기존에 15개 시나리오가 하드코딩되어 있을 것. 이를 scenario_list_full.txt에서 로드하도록 변경.

```python
# 기존 (예상)
SCENARIOS = [
    "septic_shock_basic",
    "dka_moderate_basic",
    # ... 15개
]

# 변경
import sys
from pathlib import Path

def load_scenarios(path="configs/scenario_list_full.txt"):
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]

SCENARIOS = load_scenarios()
```

**3B. MODEL 설정에 397B + 27B 추가**

기존 MODEL_CONFIGS에 새 모델 추가:

```python
MODEL_CONFIGS = {
    "oss120b": {
        "config": "configs/agents/clean_slate_oss120b.yaml",  # 또는 rag_oss120b.yaml
        "base_url": "http://localhost:28000/v1",
    },
    "qwen35b": {
        "config": "configs/agents/clean_slate_qwen35b.yaml",
        "base_url": "http://localhost:8015/v1",  # 8013→8015 수정!
    },
    "qwen27b": {
        "config": "configs/agents/clean_slate_qwen27b.yaml",
        "base_url": "http://localhost:28010/v1",
    },
    "qwen4b": {
        "config": "configs/agents/clean_slate_qwen4b.yaml",
        "base_url": "http://localhost:8101/v1",
    },
    # 397B — 외부 서버 (연결 확인 후)
    "qwen397b": {
        "config": "configs/agents/clean_slate_qwen397b.yaml",
        "base_url": "http://localhost:8013/v1",
    },
}
```

**3C. Output 디렉토리 변경**

```python
OUTPUT_DIR = Path("results/full_690")
```

**3D. Checkpoint/Resume 지원 확인**

기존에 체크포인트가 있는지 확인. 없으면 추가:

```python
def get_completed_episodes(output_dir):
    """이미 완료된 (scenario, model, run) 조합 반환"""
    completed = set()
    for json_file in output_dir.glob("**/*.json"):
        # 파일명에서 scenario_id, model, run 추출
        # 예: septic_shock_basic_oss120b_r0_20260403_120000.json
        parts = json_file.stem.rsplit("_", 3)  # 실제 패턴에 맞게 조정
        # ...
        completed.add((scenario_id, model_key, run_index))
    return completed
```

## Step 4: Agent Config 생성 (397B + 27B)

기존 config 파일을 복사하여 새 모델용 config 생성.

```bash
# 기존 config 확인
cat configs/agents/clean_slate_oss120b.yaml
```

```bash
# 397B config 생성 (기존 형식에 맞게)
# 핵심: base_url이 외부 서버를 가리킴
cat > configs/agents/clean_slate_qwen397b.yaml << 'TEMPLATE'
# 이 부분은 기존 config 형식을 파악한 후 채운다
TEMPLATE

# 27B config 생성 (기존 형식에 맞게)
cat > configs/agents/clean_slate_qwen27b.yaml << 'TEMPLATE'
# 이 부분은 기존 config 형식을 파악한 후 채운다
TEMPLATE
```

**기존 config (oss120b, qwen35b 등)를 먼저 읽어서 형식을 파악한 후, 같은 형식으로 397B/27B config를 생성하라.**

## Step 5: Port 불일치 수정

```bash
# clean_slate_qwen35b.yaml에서 port 확인
grep -n "port\|url\|8013\|8015" configs/agents/clean_slate_qwen35b.yaml

# 8013 → 8015로 수정 (실제 serving port에 맞게)
sed -i 's/8013/8015/g' configs/agents/clean_slate_qwen35b.yaml
# 또는 직접 편집
```

## Step 6: scenario_list_full.txt 최신화

```bash
python -c "
from cpg_model.scenario_loader import ScenarioLoader
loader = ScenarioLoader()
ids = sorted([s.scenario_id for s in loader.load_all_scenarios()])
with open('configs/scenario_list_full.txt', 'w') as f:
    f.write('\n'.join(ids))
print(f'Written {len(ids)} scenario IDs')
"
```

## Step 7: Dry Run (각 모델 × 1 시나리오)

```bash
export PYTHONPATH=${CGA_BENCH_ROOT}

# 로컬 4개 모델 dry-run
for model in oss120b qwen35b qwen27b qwen4b; do
    echo "=== Dry run: $model ==="
    python scripts/experiments/clean_slate_runner.py $model \
        --scenarios septic_shock_basic \
        --runs 1 \
        --output results/dry_run/ \
        2>&1 | tail -10
    echo ""
done

# 397B dry-run (외부 서버 연결 성공 시)
echo "=== Dry run: qwen397b ==="
python scripts/experiments/clean_slate_runner.py qwen397b \
    --scenarios septic_shock_basic \
    --runs 1 \
    --output results/dry_run/ \
    2>&1 | tail -10
```

**Dry run 결과:**
- JSON episode 파일이 생성되는지
- episode 내용에 agent actions가 있는지
- scoring이 완료되는지

```bash
# Dry run 결과 확인
ls -la results/dry_run/
for f in results/dry_run/*.json; do
    python -c "
import json
with open('$f') as fh:
    ep = json.load(fh)
print(f'  {f}: scenario={ep.get(\"scenario_id\")}, model={ep.get(\"model_name\")}, actions={ep.get(\"actions_count\", 0)}')
"
done
```

## Step 8: 본실행

Dry run 전부 성공 후 본실행.

### 8A. Parallel launcher 수정

기존 `clean_slate_parallel.sh`를 기반으로 수정:

```bash
#!/bin/bash
# scripts/experiments/run_full_690.sh

export PYTHONPATH=${CGA_BENCH_ROOT}
OUTPUT="results/full_690"
mkdir -p $OUTPUT

echo "Starting full 690-scenario run at $(date)"

# 로컬 4개 모델 병렬
nohup python scripts/experiments/clean_slate_runner.py oss120b \
    --output $OUTPUT/oss120b \
    > $OUTPUT/log_oss120b.txt 2>&1 &
echo "oss120b PID: $!"

nohup python scripts/experiments/clean_slate_runner.py qwen35b \
    --output $OUTPUT/qwen35b \
    > $OUTPUT/log_qwen35b.txt 2>&1 &
echo "qwen35b PID: $!"

nohup python scripts/experiments/clean_slate_runner.py qwen27b \
    --output $OUTPUT/qwen27b \
    > $OUTPUT/log_qwen27b.txt 2>&1 &
echo "qwen27b PID: $!"

nohup python scripts/experiments/clean_slate_runner.py qwen4b \
    --output $OUTPUT/qwen4b \
    > $OUTPUT/log_qwen4b.txt 2>&1 &
echo "qwen4b PID: $!"

# 397B (외부 서버, 연결 확인 후)
# nohup python scripts/experiments/clean_slate_runner.py qwen397b \
#     --output $OUTPUT/qwen397b \
#     > $OUTPUT/log_qwen397b.txt 2>&1 &
# echo "qwen397b PID: $!"

echo "All models launched. Monitor with:"
echo "  watch -n 60 'for d in $OUTPUT/*/; do echo \"\$d: \$(ls \$d/*.json 2>/dev/null | wc -l)\"; done'"
echo "  tail -f $OUTPUT/log_*.txt"

wait
echo "All complete at $(date)"
```

### 8B. 진행률 모니터링

```bash
# 실시간 진행률
watch -n 60 '
echo "=== Episode Progress ==="
for d in results/full_690/*/; do
    model=$(basename $d)
    count=$(ls $d/*.json 2>/dev/null | wc -l)
    target=2070
    pct=$((count * 100 / target))
    echo "  $model: $count / $target ($pct%)"
done
echo ""
echo "=== Errors ==="
grep -c "error\|Error\|FAIL\|timeout" results/full_690/log_*.txt 2>/dev/null
'
```

### 8C. 실패 탐지

```bash
# 에러 로그 실시간 확인
tail -f results/full_690/log_*.txt | grep -i "error\|fail\|timeout\|exception"
```

## Step 9: 시간 추정 검증

기존 181 episodes (4 models × 15 scenarios × 3 runs)의 실행 시간을 기반으로 추정:

```bash
# 기존 episode의 실행 시간 추정
python -c "
import json
from pathlib import Path
from datetime import datetime

times = []
for f in Path('results/clean_slate_rescored/').glob('**/*.json'):
    with open(f) as fh:
        ep = json.load(fh)
    # timestamp에서 시간 추출 (형식에 따라 조정)
    ts = ep.get('timestamp', ep.get('created_at', ''))
    actions = ep.get('actions_count', 0)
    model = ep.get('model_name', 'unknown')
    times.append({'model': model, 'actions': actions, 'file': f.name})

from collections import defaultdict
by_model = defaultdict(list)
for t in times:
    by_model[t['model']].append(t['actions'])

for model, actions_list in sorted(by_model.items()):
    avg = sum(actions_list) / len(actions_list)
    print(f'{model}: {len(actions_list)} episodes, avg {avg:.0f} actions')
"
```

## Completion Criteria

- [ ] 외부 서버 연결 상태 확인 (연결 or 불가 명시)
- [ ] 로컬 5개 port 모두 SERVING 확인
- [ ] Port 불일치 수정 (8013→8015)
- [ ] 397B + 27B config 생성
- [ ] scenario_list_full.txt 최신화 (690개)
- [ ] clean_slate_runner.py 수정 (690 시나리오 + 5 모델)
- [ ] Dry run: 모든 가용 모델 × 1 scenario 성공
- [ ] Dry run episode JSON에 actions > 0 확인
- [ ] 본실행 스크립트 준비 (run_full_690.sh)
- [ ] 모니터링 명령어 확인