#!/usr/bin/env bash
# Phase Orchestrator — completes the Phase B 8-model run autonomously.
#
# Sequence:
#  Stage 0 (now): gemma31b on 145 (8 GPU) + qwen397b on 144 (8 GPU TP=4×2)
#  Stage 1 (when gemma done): kill 145 gemma → launch 5 small models on 145
#  Stage 2 (when qwen397b done): kill 144 qwen397b → launch 4× nemotron on 144
#  Stage 3 (when all done): exit
#
# Each stage:
#  1. Detect current model(s) completion (eps >= target)
#  2. Kill workers + endpoints for completed models
#  3. Launch next batch of endpoints
#  4. Wait for endpoints ready
#  5. Update worker_watchdog.conf to spawn workers for new models
#  6. Loop
#
# Usage:
#   nohup bash scripts/infra/phase_orchestrator.sh > /tmp/phase_orch.log 2>&1 &
set -uo pipefail

REPO_146=/home/anonymous-org/anonymous-project/AnonProject/cga_bench
WD_CONF="${REPO_146}/scripts/infra/worker_watchdog.conf"
LOG=/tmp/phase_orch.log
INTERVAL_S=180  # check every 3 minutes
TARGET_EPS=9558

count_eps() {
  local where="$1" output="$2" model="$3"
  case "$where" in
    146) find "${output}/${model}" -maxdepth 1 -name '*.json' \
           -not -name 'checkpoint*' -not -name 'model_summary*' 2>/dev/null | wc -l ;;
    145) sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 127.0.0.1 \
           "find ${output}/${model} -maxdepth 1 -name '*.json' -not -name 'checkpoint*' -not -name 'model_summary*' 2>/dev/null | wc -l" 2>/dev/null ;;
  esac
}

stage1_done=0
stage2_done=0
stage3_done=0
# Stuck-detection: if a model is ≥STUCK_PCT for STUCK_MINUTES with no progress,
# force-trigger the next stage anyway (orphan eps will be picked up later by gap-fill).
STUCK_PCT=98          # 98% = within 191 eps of target
STUCK_MINUTES=30      # if stuck this long, give up and transition
gemma_first_seen_98=0
qwen_first_seen_98=0
nemo_first_seen_98=0

stage1_transition() {
  echo "[$(date '+%T')] STAGE 1: gemma31b complete → 145 redeploy with 5 small models"
  # 1. Stop gemma workers + remove 5 of 8 gemma containers (keep g6, g7 finishing if any)
  sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 127.0.0.1 "pkill -f 'full_690_runner.py gemma31b'" 2>/dev/null
  sleep 5
  for g in 0 1 2 3 4 5; do
    sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 127.0.0.1 "docker rm -f vllm-gemma4-g${g}" 2>/dev/null
  done

  # 2. Launch 5 small models on freed GPUs (use existing v6_endpoint.sh launcher inline)
  echo "[$(date '+%T')] STAGE 1: launching 5 endpoints on 145 GPUs 0-5"
  # oss120b TP=2 GPU 0,1
  sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 127.0.0.1 'docker run -d --rm --runtime=nvidia --init --gpus "\"device=0,1\"" --name vllm-oss120b --ipc host -v /home/anonymous-org/.cache/huggingface:/root/.cache/huggingface -p 30005:8000 vllm/vllm-openai:latest --model openai/gpt-oss-120b --port 8000 --tensor-parallel-size 2 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill --api-key sk-no-key-required' 2>&1 | tail -1
  # qwen35b GPU 2
  sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 127.0.0.1 'docker run -d --rm --runtime=nvidia --init --gpus "\"device=2\"" --name vllm-qwen35b --ipc host -v /home/anonymous-org/.cache/huggingface:/root/.cache/huggingface -p 30008:8000 vllm/vllm-openai:latest --model Qwen/Qwen3.5-35B-A3B-FP8 --port 8000 --tensor-parallel-size 1 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill --api-key sk-no-key-required' 2>&1 | tail -1
  # qwen27b GPU 3
  sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 127.0.0.1 'docker run -d --rm --runtime=nvidia --init --gpus "\"device=3\"" --name vllm-qwen27b --ipc host -v /home/anonymous-org/.cache/huggingface:/root/.cache/huggingface -p 30007:8000 vllm/vllm-openai:latest --model Qwen/Qwen3.5-27B-FP8 --port 8000 --tensor-parallel-size 1 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill --api-key sk-no-key-required' 2>&1 | tail -1
  # qwen4b GPU 4
  sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 127.0.0.1 'docker run -d --rm --runtime=nvidia --init --gpus "\"device=4\"" --name vllm-qwen4b --ipc host -v /home/anonymous-org/.cache/huggingface:/root/.cache/huggingface -p 30006:8000 vllm/vllm-openai:latest --model Qwen/Qwen3-4B-Instruct-2507 --port 8000 --tensor-parallel-size 1 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill --api-key sk-no-key-required' 2>&1 | tail -1
  # deepseek GPU 5
  sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 127.0.0.1 'docker run -d --rm --runtime=nvidia --init --gpus "\"device=5\"" --name vllm-deepseek --ipc host -v /home/anonymous-org/.cache/huggingface:/root/.cache/huggingface -p 30012:8000 vllm/vllm-openai:latest --model deepseek-ai/DeepSeek-R1-Distill-Qwen-7B --port 8000 --tensor-parallel-size 1 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill --api-key sk-no-key-required' 2>&1 | tail -1

  # 3. Wait for endpoints to load (~3-8 min for big models)
  echo "[$(date '+%T')] STAGE 1: waiting for 5 endpoints to load…"
  for tries in $(seq 1 30); do
    ok=0
    for p in 30005 30006 30007 30008 30012; do
      if curl -s --max-time 3 -H "Authorization: Bearer sk-no-key-required" "http://localhost:8013${p}/v1/models" 2>/dev/null | grep -q '"id"'; then
        ok=$((ok+1))
      fi
    done
    [ "$ok" -ge 4 ] && break
    sleep 30
  done
  echo "[$(date '+%T')] STAGE 1: ${ok}/5 endpoints alive"

  # 4. Update watchdog conf to include 5 new models
  python3 - "$WD_CONF" <<'PY'
import sys
conf = sys.argv[1]
new_lines = """gemma31b   145 localhost:30100      /home/anonymous-org/results/full_v6b 16 9558
qwen397b   146 127.0.0.1  /home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b 16 9558
oss120b        145 localhost:30005   /home/anonymous-org/results/full_v6b 12 9558
qwen35b        145 localhost:30008   /home/anonymous-org/results/full_v6b 16 9558
qwen27b        145 localhost:30007   /home/anonymous-org/results/full_v6b 16 9558
qwen4b         145 localhost:30006   /home/anonymous-org/results/full_v6b 32 9558
deepseek_r1_7b 145 localhost:30012   /home/anonymous-org/results/full_v6b 32 9558
"""
header = "# Phase B Stage 1 (auto-updated by phase_orchestrator)\n"
open(conf, "w").write(header + new_lines)
print(f"updated {conf}")
PY
  echo "[$(date '+%T')] STAGE 1 done — worker_watchdog will spawn new workers next iteration"
  stage1_done=1
}

stage2_transition() {
  echo "[$(date '+%T')] STAGE 2: qwen397b complete → 144 redeploy with 4× nemotron"
  pkill -f 'full_690_runner.py qwen397b' 2>/dev/null
  sleep 5
  sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 [email-redacted] "docker rm -f qwen3.5-397b-a qwen3.5-397b-b" 2>/dev/null
  for spec in "0,1 30013 a" "2,3 30014 b" "4,5 30015 c" "6,7 30016 d"; do
    set -- $spec; gpus=$1; port=$2; suffix=$3
    sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 [email-redacted] "docker run -d --rm --runtime=nvidia --init --gpus '\"device=${gpus}\"' \
      --name vllm-nemotron-${suffix} --ipc host \
      -v /home/anonymous-user/.cache/huggingface:/root/.cache/huggingface \
      -p ${port}:8000 vllm/vllm-openai:v0.12.0 \
      --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8 --port 8000 \
      --tensor-parallel-size 2 --max-num-seqs 8 --max-model-len 32768 \
      --kv-cache-dtype fp8 --tool-call-parser qwen3_coder \
      --enable-auto-tool-choice --trust-remote-code --api-key sk-no-key-required" 2>&1 | tail -1
  done
  echo "[$(date '+%T')] STAGE 2: 4 nemotron containers launched, waiting…"
  for tries in $(seq 1 30); do
    ok=0
    for p in 30013 30014 30015 30016; do
      if curl -s --max-time 3 -H "Authorization: Bearer sk-no-key-required" "http://localhost:8013${p}/v1/models" 2>/dev/null | grep -q "Nemotron"; then
        ok=$((ok+1))
      fi
    done
    [ "$ok" -ge 4 ] && break
    sleep 30
  done
  echo "[$(date '+%T')] STAGE 2: ${ok}/4 nemotron alive"

  # Update watchdog conf — drop qwen397b, add nemotron
  python3 - "$WD_CONF" <<'PY'
import sys
conf = sys.argv[1]
new_lines = """gemma31b       145 localhost:30100      /home/anonymous-org/results/full_v6b 16 9558
oss120b        145 localhost:30005      /home/anonymous-org/results/full_v6b 12 9558
qwen35b        145 localhost:30008      /home/anonymous-org/results/full_v6b 16 9558
qwen27b        145 localhost:30007      /home/anonymous-org/results/full_v6b 16 9558
qwen4b         145 localhost:30006      /home/anonymous-org/results/full_v6b 32 9558
deepseek_r1_7b 145 localhost:30012      /home/anonymous-org/results/full_v6b 32 9558
nemotron30b    146 127.0.0.1  /home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b 32 9558
"""
header = "# Phase B Stage 2 (auto-updated by phase_orchestrator)\n"
open(conf, "w").write(header + new_lines)
print(f"updated {conf}")
PY
  echo "[$(date '+%T')] STAGE 2 done"
  stage2_done=1
}

stage3_transition() {
  echo "[$(date '+%T')] STAGE 3: nemotron complete + oss120b still active → boost oss120b on 144"
  # Stop nemotron containers, repurpose 144 GPUs for 4× oss120b (TP=2 each)
  for n in a b c d; do
    sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 [email-redacted] \
      "docker rm -f vllm-nemotron-${n}" 2>/dev/null
  done
  sleep 5

  # 4 oss120b instances on 144 (TP=2 each, GPU 0,1 / 2,3 / 4,5 / 6,7)
  for spec in "0,1 30005 a" "2,3 30006 b" "4,5 30007 c" "6,7 30008 d"; do
    set -- $spec; gpus=$1; port=$2; suffix=$3
    sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 [email-redacted] \
      "docker run -d --rm --runtime=nvidia --init --gpus '\"device=${gpus}\"' \
        --name vllm-oss120b-144-${suffix} --ipc host \
        -v /home/anonymous-user/.cache/huggingface:/root/.cache/huggingface \
        -p ${port}:8000 vllm/vllm-openai:latest \
        --model openai/gpt-oss-120b --port 8000 \
        --tensor-parallel-size 2 --max-model-len 8192 --max-num-seqs 256 \
        --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill \
        --api-key sk-no-key-required" 2>&1 | tail -1
  done
  echo "[$(date '+%T')] STAGE 3: 4 oss120b containers launched, waiting…"
  for tries in $(seq 1 30); do
    ok=0
    for p in 30005 30006 30007 30008; do
      if curl -s --max-time 3 -H "Authorization: Bearer sk-no-key-required" "http://localhost:8013${p}/v1/models" 2>/dev/null | grep -q "gpt-oss"; then
        ok=$((ok+1))
      fi
    done
    [ "$ok" -ge 3 ] && break
    sleep 30
  done
  echo "[$(date '+%T')] STAGE 3: ${ok}/4 oss120b on 144 alive"

  # Update watchdog conf — add 4 boost endpoints for oss120b on 144
  python3 - "$WD_CONF" <<'PY'
import sys
conf = sys.argv[1]
new_lines = """gemma31b       145 localhost:30100      /home/anonymous-org/results/full_v6b 16 9558
oss120b        145 localhost:30005      /home/anonymous-org/results/full_v6b 12 9558
oss120b_boost1 146 127.0.0.1  /home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b 12 9558
oss120b_boost2 146 127.0.0.1  /home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b 12 9558
oss120b_boost3 146 127.0.0.1  /home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b 12 9558
oss120b_boost4 146 127.0.0.1  /home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b 12 9558
qwen35b        145 localhost:30008      /home/anonymous-org/results/full_v6b 16 9558
qwen27b        145 localhost:30007      /home/anonymous-org/results/full_v6b 16 9558
qwen4b         145 localhost:30006      /home/anonymous-org/results/full_v6b 32 9558
deepseek_r1_7b 145 localhost:30012      /home/anonymous-org/results/full_v6b 32 9558
"""
header = "# Phase B Stage 3 — oss120b boost on 144 (auto-updated by phase_orchestrator)\n# NOTE: oss120b_boost* aliases all run model_key=oss120b — workers manually launched below\n"
open(conf, "w").write(header + new_lines)
print(f"updated {conf}")
PY

  # Spawn workers from 146 to 144 oss120b boost endpoints
  cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench
  export CGA_BENCH_EXCLUDE_AUTO=1 CGA_BENCH_INCLUDE_AUTO_V2=1
  export PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject
  for port in 30005 30006 30007 30008; do
    for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
      log="/home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b/_logs/oss120b_boost_p${port}_${i}.log"
      nohup python scripts/experiments/full_690_runner.py oss120b results/full_v6b --host 127.0.0.1 --port $port >$log 2>&1 &
      disown
    done
  done
  echo "[$(date '+%T')] STAGE 3: 48 oss120b boost workers launched on 146 → 144 (12 per endpoint)"
  stage3_done=1
}

# ─── main loop ──────────────────────────────────────────────

echo "[$(date '+%T')] phase_orchestrator started, interval=${INTERVAL_S}s, target_eps=${TARGET_EPS}"

while true; do
  # Check stage triggers
  if [ "$stage1_done" -eq 0 ]; then
    GEMMA_EPS=$(count_eps 145 /home/anonymous-org/results/full_v6b gemma31b)
    GEMMA_EPS=${GEMMA_EPS:-0}
    GEMMA_PCT=$(( GEMMA_EPS * 100 / TARGET_EPS ))
    echo "[$(date '+%T')] gemma31b eps=${GEMMA_EPS}/${TARGET_EPS} (${GEMMA_PCT}%)"
    NOW=$(date +%s)
    if [ "$GEMMA_EPS" -ge "$TARGET_EPS" ]; then
      stage1_transition
    elif [ "$GEMMA_PCT" -ge "$STUCK_PCT" ]; then
      [ "$gemma_first_seen_98" -eq 0 ] && gemma_first_seen_98=$NOW
      stuck_for=$(( (NOW - gemma_first_seen_98) / 60 ))
      echo "[$(date '+%T')] gemma31b at ${GEMMA_PCT}% for ${stuck_for}min"
      if [ "$stuck_for" -ge "$STUCK_MINUTES" ]; then
        echo "[$(date '+%T')] STUCK-DETECT: gemma stuck ${stuck_for}min ≥${STUCK_MINUTES}, force stage 1"
        stage1_transition
      fi
    fi
  fi

  if [ "$stage2_done" -eq 0 ]; then
    QWEN_EPS=$(count_eps 146 /home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b qwen397b)
    QWEN_EPS=${QWEN_EPS:-0}
    QWEN_PCT=$(( QWEN_EPS * 100 / TARGET_EPS ))
    echo "[$(date '+%T')] qwen397b eps=${QWEN_EPS}/${TARGET_EPS} (${QWEN_PCT}%)"
    NOW=$(date +%s)
    if [ "$QWEN_EPS" -ge "$TARGET_EPS" ]; then
      stage2_transition
    elif [ "$QWEN_PCT" -ge "$STUCK_PCT" ]; then
      [ "$qwen_first_seen_98" -eq 0 ] && qwen_first_seen_98=$NOW
      stuck_for=$(( (NOW - qwen_first_seen_98) / 60 ))
      echo "[$(date '+%T')] qwen397b at ${QWEN_PCT}% for ${stuck_for}min"
      if [ "$stuck_for" -ge "$STUCK_MINUTES" ]; then
        echo "[$(date '+%T')] STUCK-DETECT: qwen397b stuck ${stuck_for}min ≥${STUCK_MINUTES}, force stage 2"
        stage2_transition
      fi
    fi
  fi

  # Stage 3 trigger: nemotron complete + oss120b lagging (boost it on 144)
  if [ "$stage2_done" -eq 1 ] && [ "$stage3_done" -eq 0 ]; then
    NEMO_EPS=$(count_eps 146 /home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b nemotron30b)
    NEMO_EPS=${NEMO_EPS:-0}
    OSS_EPS=$(count_eps 145 /home/anonymous-org/results/full_v6b oss120b)
    OSS_EPS=${OSS_EPS:-0}
    NEMO_PCT=$(( NEMO_EPS * 100 / TARGET_EPS ))
    NOW=$(date +%s)
    echo "[$(date '+%T')] nemotron eps=${NEMO_EPS}/${TARGET_EPS} (${NEMO_PCT}%) oss120b eps=${OSS_EPS}/${TARGET_EPS}"
    # Trigger boost only if oss120b is significantly behind (less than 90%)
    if [ "$NEMO_EPS" -ge "$TARGET_EPS" ] && [ "$OSS_EPS" -lt $(( TARGET_EPS * 90 / 100 )) ]; then
      stage3_transition
    elif [ "$NEMO_PCT" -ge "$STUCK_PCT" ]; then
      [ "$nemo_first_seen_98" -eq 0 ] && nemo_first_seen_98=$NOW
      stuck_for=$(( (NOW - nemo_first_seen_98) / 60 ))
      if [ "$stuck_for" -ge "$STUCK_MINUTES" ] && [ "$OSS_EPS" -lt $(( TARGET_EPS * 90 / 100 )) ]; then
        echo "[$(date '+%T')] STUCK-DETECT: nemotron stuck ${stuck_for}min, oss120b only ${OSS_EPS}/9558 — force stage 3"
        stage3_transition
      fi
    fi
  fi

  # Check if all 8 models complete
  if [ "$stage1_done" -eq 1 ] && [ "$stage2_done" -eq 1 ]; then
    all_done=1
    for m in qwen397b oss120b nemotron30b gemma31b qwen35b qwen27b qwen4b deepseek_r1_7b; do
      where=146
      output=/home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b
      if [ "$m" != "qwen397b" ] && [ "$m" != "nemotron30b" ]; then
        where=145
        output=/home/anonymous-org/results/full_v6b
      fi
      eps=$(count_eps "$where" "$output" "$m")
      eps=${eps:-0}
      [ "$eps" -lt "$TARGET_EPS" ] && all_done=0
    done
    if [ "$all_done" -eq 1 ]; then
      echo "[$(date '+%T')] ALL 8 MODELS COMPLETE — exiting orchestrator"
      break
    fi
  fi

  sleep "$INTERVAL_S"
done
