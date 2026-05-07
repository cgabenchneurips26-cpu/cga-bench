# 외부 서버 A100×5 활용: vLLM 배포 + 에피소드 가속 + E8 + LLM Judge

> 서버: ssh [email-redacted]
> GPU: id 0, 1, 3, 4, 5 (5개)
> SSH 인증: 완료 (ssh-copy-id 됨)
> 목적: qwen27b 병목 해소 + E8 Adapter + Terminal Judge + Model Diversity

---

## Step 0: 서버 환경 확인

```bash
ssh [email-redacted] << 'REMOTE_CHECK'
echo "=== GPU 상태 ==="
nvidia-smi --query-gpu=index,name,memory.total,memory.used,utilization.gpu --format=csv,noheader

echo ""
echo "=== 사용 가능한 GPU 확인 ==="
for gid in 0 1 3 4 5; do
  used=$(nvidia-smi --id=$gid --query-gpu=memory.used --format=csv,noheader,nounits)
  echo "  GPU $gid: ${used}MiB used"
done

echo ""
echo "=== Python/vLLM 설치 상태 ==="
which python3 && python3 --version
pip show vllm 2>/dev/null | grep -E "Name|Version" || echo "vLLM not installed"

echo ""
echo "=== 디스크 여유 ==="
df -h / /home 2>/dev/null | tail -2

echo ""
echo "=== 네트워크: 기존 서버에서 접근 가능한지 ==="
echo "이 서버 IP: $(hostname -I | awk '{print $1}')"

echo ""
echo "=== CUDA 버전 ==="
nvcc --version 2>/dev/null | tail -1 || echo "nvcc not found"

echo ""
echo "=== 열린 포트 확인 (8200-8209) ==="
ss -tlnp | grep -E "820[0-9]" || echo "8200-8209 모두 비어있음"
REMOTE_CHECK
```

---

## Step 1: vLLM 설치 (필요 시)

```bash
ssh [email-redacted] << 'REMOTE_INSTALL'
# vLLM이 없으면 설치
if ! pip show vllm &>/dev/null; then
  echo "Installing vLLM..."
  pip install vllm --break-system-packages
fi

# huggingface-cli 로그인 (gated 모델 필요 시)
# huggingface-cli login --token YOUR_TOKEN

echo "vLLM version: $(pip show vllm 2>/dev/null | grep Version)"
REMOTE_INSTALL
```

---

## Step 2: vLLM 서버 4개 배포

### GPU 배분 계획:
```
GPU 0: qwen27b 인스턴스 #1 (에피소드 가속)         → port 8201
GPU 1: qwen27b 인스턴스 #2 (에피소드 가속)         → port 8202
GPU 3: qwen35b (E8 Adapter fresh gen)              → port 8203
GPU 4: qwen35b (Terminal LLM Judge + WS-3 + WS-5)  → port 8204
GPU 5: 추가 모델 (Model Diversity)                  → port 8205
```

```bash
ssh [email-redacted] << 'REMOTE_VLLM'
# tmux 세션으로 각 vLLM을 백그라운드 실행

# === GPU 0: qwen27b #1 ===
tmux new-session -d -s vllm_qwen27b_0 "
  CUDA_VISIBLE_DEVICES=0 python3 -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-27B-Instruct \
    --port 8201 \
    --gpu-memory-utilization 0.92 \
    --max-model-len 8192 \
    --max-num-seqs 16 \
    --dtype auto \
    --trust-remote-code \
    2>&1 | tee /tmp/vllm_qwen27b_0.log
"
echo "Started qwen27b #1 on GPU 0, port 8201"

# === GPU 1: qwen27b #2 ===
tmux new-session -d -s vllm_qwen27b_1 "
  CUDA_VISIBLE_DEVICES=1 python3 -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-27B-Instruct \
    --port 8202 \
    --gpu-memory-utilization 0.92 \
    --max-model-len 8192 \
    --max-num-seqs 16 \
    --dtype auto \
    --trust-remote-code \
    2>&1 | tee /tmp/vllm_qwen27b_1.log
"
echo "Started qwen27b #2 on GPU 1, port 8202"

# === GPU 3: qwen35b (E8 + Judge용) ===
tmux new-session -d -s vllm_qwen35b "
  CUDA_VISIBLE_DEVICES=3 python3 -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-32B-Instruct \
    --port 8203 \
    --gpu-memory-utilization 0.92 \
    --max-model-len 8192 \
    --max-num-seqs 16 \
    --dtype auto \
    --trust-remote-code \
    2>&1 | tee /tmp/vllm_qwen35b.log
"
echo "Started qwen35b on GPU 3, port 8203"

# === GPU 4: Judge 전용 ===
tmux new-session -d -s vllm_judge "
  CUDA_VISIBLE_DEVICES=4 python3 -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-32B-Instruct \
    --port 8204 \
    --gpu-memory-utilization 0.92 \
    --max-model-len 8192 \
    --max-num-seqs 8 \
    --dtype auto \
    --trust-remote-code \
    2>&1 | tee /tmp/vllm_judge.log
"
echo "Started judge model on GPU 4, port 8204"

# GPU 5는 Step 5에서 추가 모델 결정 후 배포

echo ""
echo "=== 배포 상태 확인 (30초 대기 후) ==="
sleep 30
for port in 8201 8202 8203 8204; do
  status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$port/v1/models 2>/dev/null)
  echo "  Port $port: $status"
done
REMOTE_VLLM
```

**⚠️ 모델 이름 확인 필요**: 
기존 서버에서 qwen27b가 정확히 어떤 모델인지 확인하라:
```bash
# 기존 서버에서
curl -s http://localhost:28010/v1/models | python3 -c "import json,sys; print(json.load(sys.stdin))"
# 또는
grep -r "qwen27b\|qwen.*27\|Qwen2.5-27" configs/ scripts/ --include="*.py" --include="*.yaml" | head -5
```
→ 정확한 모델 ID로 위의 `--model` 인자를 교체.

---

## Step 3: vLLM 서버 정상 동작 확인

```bash
echo "=== 외부 서버에서 vLLM 응답 테스트 ==="
NEW_SERVER="127.0.0.1

for port in 8201 8202 8203 8204; do
  echo "--- Port $port ---"
  curl -s http://$NEW_SERVER:$port/v1/models | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(f'  Model: {d[\"data\"][0][\"id\"]}')
    print(f'  Status: OK')
except:
    print('  Status: FAILED')
" 2>/dev/null || echo "  Status: UNREACHABLE"
done

echo ""
echo "=== 간단한 추론 테스트 ==="
curl -s http://$NEW_SERVER:8201/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-27B-Instruct",
    "messages": [{"role": "user", "content": "Say hello in one word."}],
    "max_tokens": 10
  }' | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(f'Response: {d[\"choices\"][0][\"message\"][\"content\"]}')" 2>/dev/null
```

**⚠️ 방화벽 확인**: 기존 서버에서 127.0.0.1 접근 가능한지.
안 되면 SSH 터널 사용:
```bash
# 기존 서버에서 SSH 터널
ssh -L 8201:localhost:8201 -L 8202:localhost:8202 \
    -L 8203:localhost:8203 -L 8204:localhost:8204 \
    -N -f [email-redacted]
```

---

## Step 4: qwen27b 에피소드 가속 — shard 분할

### 4-1. 남은 에피소드 파악
```bash
echo "=== qwen27b 현재 완료 현황 ==="
QWEN27_DIR="results/full_706_v5/qwen27b"
DONE=$(find "$QWEN27_DIR" -name "*.json" 2>/dev/null | wc -l)
TARGET=$((706 * 3))
REMAIN=$((TARGET - DONE))
echo "완료: $DONE / $TARGET"
echo "남은: $REMAIN episodes"

echo ""
echo "=== 완료된 scenario-run 목록 추출 ==="
python3 -c "
import os, json, glob
done_dir = 'results/full_706_v5/qwen27b'
done_files = glob.glob(os.path.join(done_dir, '*.json'))
done_keys = set()
for f in done_files:
    try:
        ep = json.load(open(f))
        sid = ep.get('scenario_id', os.path.basename(f).replace('.json',''))
        rid = ep.get('run_id', 0)
        done_keys.add(f'{sid}__r{rid}')
    except:
        pass
print(f'Done keys: {len(done_keys)}')

# 전체 시나리오 목록
import yaml
all_scenarios = []
for sf in glob.glob('configs/scenarios/*.yaml'):
    data = yaml.safe_load(open(sf))
    if isinstance(data, list):
        for s in data:
            if isinstance(s, dict):
                all_scenarios.append(s.get('scenario_id', s.get('id','')))
    elif isinstance(data, dict) and 'scenarios' in data:
        for s in data['scenarios']:
            if isinstance(s, dict):
                all_scenarios.append(s.get('scenario_id', s.get('id','')))

# 남은 것
remaining = []
for sid in all_scenarios:
    for rid in range(3):
        key = f'{sid}__r{rid}'
        if key not in done_keys:
            remaining.append((sid, rid))

print(f'Remaining: {len(remaining)} episodes')

# 3등분 (기존 서버 1 + 신규 서버 2)
n = len(remaining)
shard_size = n // 3
shards = [
    remaining[:shard_size],           # 기존 서버 유지
    remaining[shard_size:2*shard_size], # 신규 GPU 0 (port 8201)
    remaining[2*shard_size:],           # 신규 GPU 1 (port 8202)
]

for i, shard in enumerate(shards):
    fname = f'configs/shard_qwen27b_{i}.json'
    with open(fname, 'w') as f:
        json.dump([{'scenario_id': s, 'run_id': r} for s, r in shard], f, indent=2)
    print(f'Shard {i}: {len(shard)} episodes → {fname}')
"
```

### 4-2. Shard runner 실행
```bash
NEW_SERVER="127.0.0.1

# Shard 1 → 신규 서버 GPU 0 (port 8201)
nohup python3 scripts/full_706_runner.py \
  --model-endpoint http://$NEW_SERVER:8201/v1 \
  --model-name qwen27b \
  --shard-file configs/shard_qwen27b_1.json \
  --output-dir results/full_706_v5/qwen27b/ \
  --max-tokens 4096 \
  > logs/shard_qwen27b_1.log 2>&1 &
echo "Shard 1 started (PID: $!)"

# Shard 2 → 신규 서버 GPU 1 (port 8202)
nohup python3 scripts/full_706_runner.py \
  --model-endpoint http://$NEW_SERVER:8202/v1 \
  --model-name qwen27b \
  --shard-file configs/shard_qwen27b_2.json \
  --output-dir results/full_706_v5/qwen27b/ \
  --max-tokens 4096 \
  > logs/shard_qwen27b_2.log 2>&1 &
echo "Shard 2 started (PID: $!)"
```

**⚠️ 주의**: `full_706_runner.py`가 `--shard-file` 인자를 지원하는지 확인.
지원 안 하면 runner를 수정하거나, 시나리오 리스트를 필터링하는 wrapper 작성:

```python
# scripts/shard_runner.py (필요 시)
"""
Shard runner: 지정된 scenario-run 목록만 실행.
Usage:
    python scripts/shard_runner.py \
        --shard-file configs/shard_qwen27b_1.json \
        --model-endpoint http://localhost:8013/v1 \
        --output-dir results/full_706_v5/qwen27b/
"""
import json, sys, os
sys.path.insert(0, '.')

# shard 파일 로드
shard = json.load(open(sys.argv[sys.argv.index('--shard-file') + 1]))
# 기존 runner의 핵심 함수 import해서 shard만 실행
# from scripts.full_706_runner import run_single_episode
# for item in shard:
#     run_single_episode(item['scenario_id'], item['run_id'], ...)
```

### 4-3. 기존 qwen27b runner와 충돌 방지
```bash
# 기존 서버의 qwen27b runner가 아직 돌고 있으면:
# 1. 같은 output 디렉토리 사용 → 파일 이름이 scenario_id 기반이면 충돌 없음
# 2. 하지만 동일 scenario-run을 중복 실행하면 안 됨
# → shard 분할이 done_keys를 제외하므로 안전

echo "=== 기존 qwen27b runner 상태 ==="
ps aux | grep "qwen27b\|28010" | grep -v grep
```

---

## Step 5: E8 Adapter — AgentClinic Fresh Generation

### 5-1. 프로젝트 코드를 신규 서버에도 배포 (또는 기존 서버에서 원격 endpoint 사용)

**Option A**: 기존 서버에서 원격 vLLM endpoint를 사용 (코드 이동 불필요)
```bash
# 기존 서버에서 실행, 모델만 신규 서버
NEW_SERVER="127.0.0.1
python3 run_external_benchmark.py \
  --benchmark agentclinic \
  --model-endpoint http://$NEW_SERVER:8203/v1 \
  --output results/e8_adapter_ac/ \
  --n-runs 1
```

**Option B**: 신규 서버에 코드 복사
```bash
rsync -avz --exclude='results/' --exclude='.git/' --exclude='__pycache__/' \
  ./ [email-redacted]:~/cga-bench/
```

### 5-2. AgentClinic domain-matched 시나리오 확인 + 실행
```bash
# 먼저 run_external_benchmark.py의 AgentClinic 실행 방법 파악 (이전 프롬프트 Step 1 참조)
# 그 다음 domain-matched 53개 시나리오로 실행

# 예시 (실제 명령은 Step 1 결과에 따라 조정):
NEW_SERVER="127.0.0.1
python3 run_external_benchmark.py \
  --benchmark agentclinic \
  --model-endpoint http://$NEW_SERVER:8203/v1 \
  --scenarios-filter "chest_pain,sepsis,pe,aki,dka,stroke,stemi,gib,hf" \
  --output results/e8_adapter_ac/ \
  --n-runs 1 \
  --max-tokens 4096
```

### 5-3. 완료 후 TCC 채점
```bash
python3 scripts/experiments/run_e8_adapter_direction.py \
  --benchmark agentclinic \
  --episodes-dir results/e8_adapter_ac/ \
  --output evidence_pack/analysis/e8_adapter_ac.json
```

---

## Step 6: Terminal LLM Judge (#8)

완료된 에피소드(다른 모델)로 Terminal LLM Judge를 즉시 시작.

```bash
# 완료된 에피소드가 가장 많은 모델 찾기
BEST_MODEL=$(ls -d results/full_706_v5/*/ | while read d; do
  echo "$(find "$d" -name '*.json' | wc -l) $(basename $d)"
done | sort -rn | head -1 | awk '{print $2}')
echo "Using $BEST_MODEL for Terminal LLM Judge test"

NEW_SERVER="127.0.0.1

# GPU 4 (port 8204)의 judge 모델 사용
python3 scripts/experiments/run_terminal_llm_judge.py \
  --episodes-dir results/full_706_v5/$BEST_MODEL \
  --endpoint http://$NEW_SERVER:8204/v1 \
  --output evidence_pack/analysis/terminal_judge_$BEST_MODEL.json \
  --max-episodes 200
```

---

## Step 7: 추가 모델 (GPU 5) — Model Diversity 강화

### 7-1. 모델 선정
```bash
ssh [email-redacted] << 'REMOTE_MODEL'
echo "=== GPU 5 메모리 ==="
nvidia-smi --id=5 --query-gpu=memory.total --format=csv,noheader

echo ""
echo "=== 사용 가능한 모델 후보 ==="
echo "A100 80GB 기준:"
echo "  1. meta-llama/Llama-4-Scout-17B-16E-Instruct (MoE, ~34GB) — Meta family 추가"
echo "  2. mistralai/Mistral-Small-3.1-24B-Instruct-2503 (~48GB) — Mistral family 추가"
echo "  3. microsoft/Phi-4 (14B, ~28GB) — Microsoft family 추가"
echo "  4. deepseek-ai/DeepSeek-R1-Distill-Qwen-14B (~28GB) — Reasoning 추가"

# HuggingFace에서 다운로드 속도 테스트
echo ""
echo "=== 다운로드 속도 테스트 ==="
timeout 10 wget -q --spider https://huggingface.co && echo "HuggingFace reachable" || echo "HuggingFace not reachable"
REMOTE_MODEL
```

### 7-2. 추가 모델 배포 + 에피소드 실행
```bash
ssh [email-redacted] << 'REMOTE_MODEL5'
# Llama-4-Scout (Meta family 추가, 가장 차별화됨)
tmux new-session -d -s vllm_llama4 "
  CUDA_VISIBLE_DEVICES=5 python3 -m vllm.entrypoints.openai.api_server \
    --model meta-llama/Llama-4-Scout-17B-16E-Instruct \
    --port 8205 \
    --gpu-memory-utilization 0.92 \
    --max-model-len 8192 \
    --max-num-seqs 16 \
    --dtype auto \
    --trust-remote-code \
    2>&1 | tee /tmp/vllm_llama4.log
"
echo "Started Llama-4-Scout on GPU 5, port 8205"
REMOTE_MODEL5

# 기존 서버에서 에피소드 실행
NEW_SERVER="127.0.0.1
nohup python3 scripts/full_706_runner.py \
  --model-endpoint http://$NEW_SERVER:8205/v1 \
  --model-name llama4scout \
  --output-dir results/full_706_v5/llama4scout/ \
  --max-tokens 4096 \
  > logs/llama4scout.log 2>&1 &
echo "Llama-4-Scout episode runner started (PID: $!)"
```

---

## Step 8: 모니터링 대시보드

```bash
# 전체 현황 한눈에 보기
cat << 'MONITOR' > scripts/monitor_all.sh
#!/bin/bash
NEW_SERVER="127.0.0.1

echo "=========================================="
echo "  CGA-Bench Episode Monitor $(date)"
echo "=========================================="

echo ""
echo "--- Episode Progress ---"
for d in results/full_706_v5/*/; do
  model=$(basename "$d")
  count=$(find "$d" -name "*.json" 2>/dev/null | wc -l)
  target=$((706 * 3))
  pct=$((count * 100 / target))
  bar=$(printf '%*s' $((pct/5)) '' | tr ' ' '█')
  printf "  %-15s %4d/%d (%3d%%) %s\n" "$model" "$count" "$target" "$pct" "$bar"
done

echo ""
echo "--- vLLM Server Status ---"
for port in 8013 8101 28000 28010; do
  status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 http://localhost:$port/v1/models 2>/dev/null)
  printf "  localhost:%-5d %s\n" "$port" "$([ "$status" = "200" ] && echo "✅ ALIVE" || echo "❌ DOWN")"
done
for port in 8201 8202 8203 8204 8205; do
  status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 http://$NEW_SERVER:$port/v1/models 2>/dev/null)
  printf "  $NEW_SERVER:%-5d %s\n" "$port" "$([ "$status" = "200" ] && echo "✅ ALIVE" || echo "❌ DOWN")"
done

echo ""
echo "--- E8 Adapter Progress ---"
e8_count=$(find results/e8_adapter_ac/ -name "*.json" 2>/dev/null | wc -l)
echo "  AgentClinic fresh: $e8_count episodes"

echo ""
echo "--- Errors (last 3) ---"
for log in logs/shard_qwen27b_*.log logs/llama4scout.log; do
  if [ -f "$log" ]; then
    errs=$(grep -ci "error\|traceback" "$log" 2>/dev/null)
    echo "  $(basename $log): $errs errors"
  fi
done
MONITOR
chmod +x scripts/monitor_all.sh
echo "모니터링: bash scripts/monitor_all.sh"
```

---

## 보고 형식

모든 Step 완료 후 아래를 채워서 보고하라:

```markdown
## 외부 서버 배포 현황

### vLLM 서버
| GPU | Port | 모델 | 상태 | 용도 |
|-----|------|------|------|------|
| 0 | 8201 | qwen27b | ✅/❌ | 에피소드 가속 shard 1 |
| 1 | 8202 | qwen27b | ✅/❌ | 에피소드 가속 shard 2 |
| 3 | 8203 | qwen35b | ✅/❌ | E8 Adapter fresh gen |
| 4 | 8204 | qwen35b | ✅/❌ | Terminal Judge + WS-3 |
| 5 | 8205 | llama4scout | ✅/❌ | Model Diversity |

### qwen27b 가속
- 기존 완료: N episodes
- 남은: N episodes
- Shard 0 (기존): N episodes (기존 서버)
- Shard 1 (신규 GPU 0): N episodes → 실행 중/완료
- Shard 2 (신규 GPU 1): N episodes → 실행 중/완료
- 예상 완료: [시각]

### E8 Adapter
- AgentClinic matched scenarios: N개
- Fresh generation 상태: 대기/실행 중/완료
- TCC 채점 상태: 대기/완료

### Terminal LLM Judge
- 테스트 에피소드: N개
- 실행 상태: 대기/실행 중/완료

### 추가 모델
- 모델: [name]
- 에피소드 진행: N / 2118
```