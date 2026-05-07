#!/usr/bin/env bash
# Phase B fast resume — idempotent. Detects existing endpoints/workers and only
# spawns what's missing. Avoids the watchdog ramp-up delay (REFILL_BATCH=4/120s).
#
# Usage:
#   bash scripts/infra/phase_b_resume.sh
#
# Pre-conditions: 145 + 144 hosts reachable via sudo -n -u anonymous-org ssh.
# Post-conditions: All Phase B endpoints HTTP 200, all workers spawned at full
# target count immediately (no ramp).
set -uo pipefail

ROOT=/home/anonymous-org/anonymous-project/AnonProject/cga_bench
OUTPUT_145=/home/anonymous-org/results/full_v6b
OUTPUT_146=/home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b
TARGET_EPS=9558

declare -A MODEL_PORT=(
  [qwen4b]=30006 [qwen27b]=30007 [qwen35b]=30008 [oss120b]=30005
  [deepseek_r1_7b]=30012 [gemma31b]=30100
)
declare -A MODEL_GPU=(
  [qwen4b]=0 [qwen27b]=1 [qwen35b]=2 [gemma31b]=3
  [deepseek_r1_7b]=4 [oss120b]=6,7
)
declare -A MODEL_WORKERS=(
  [qwen4b]=32 [qwen27b]=16 [qwen35b]=16 [oss120b]=12
  [deepseek_r1_7b]=32 [gemma31b]=16
)

ensure_endpoint_145() {
  local model="$1" port="$2" gpu="$3"
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
    -H 'Authorization: Bearer sk-no-key-required' \
    "http://localhost:8013${port}/v1/models" 2>/dev/null || echo 000)
  if [ "$code" = "200" ]; then
    echo "  endpoint $model:$port already up"
    return
  fi
  echo "  launching $model on 145 GPU $gpu port $port"
  bash "$ROOT/scripts/infra/v6_endpoint.sh" launch 145 "$gpu" "$port" "$model" >/dev/null 2>&1
}

count_workers_145() {
  sudo -n -u anonymous-org ssh -o ConnectTimeout=5 127.0.0.1 \
    "ps aux | grep 'full_690_runner.py $1 ' | grep -v grep | wc -l" 2>/dev/null
}

spawn_workers_145() {
  local model="$1" port="$2" target="$3"
  local current
  current=$(count_workers_145 "$model")
  current=${current:-0}
  if [ "$current" -ge "$target" ]; then
    echo "  $model: $current/$target workers — sufficient"
    return
  fi
  local gap=$(( target - current ))
  echo "  $model: $current/$target → spawning $gap on 145"
  sudo -n -u anonymous-org ssh -o ConnectTimeout=5 127.0.0.1 "
    export PYTHONPATH=/home/anonymous-org
    export CGA_BENCH_EXCLUDE_AUTO=1 CGA_BENCH_INCLUDE_AUTO_V2=1
    cd /home/anonymous-org/cga_bench
    mkdir -p /home/anonymous-org/v6b_logs
    for i in \$(seq 1 ${gap}); do
      log=/home/anonymous-org/v6b_logs/${model}_resume_\$(date +%s)_\${i}.log
      nohup /home/anonymous-org/anaconda3/bin/python3 scripts/experiments/full_690_runner.py \
        ${model} $OUTPUT_145 --host localhost --port ${port} >\$log 2>&1 &
      disown
    done
  " 2>/dev/null
}

count_workers_146() {
  ps aux | grep "full_690_runner.py $1 " | grep -v grep | wc -l
}

spawn_workers_146_to_144() {
  local model="$1" host="$2" port="$3" target="$4"
  local current=$(count_workers_146 "$model")
  if [ "$current" -ge "$target" ]; then
    echo "  $model→144: $current/$target workers — sufficient"
    return
  fi
  local gap=$(( target - current ))
  echo "  $model→144: $current/$target → spawning $gap on 146"
  cd "$ROOT"
  export CGA_BENCH_EXCLUDE_AUTO=1 CGA_BENCH_INCLUDE_AUTO_V2=1
  export PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject
  mkdir -p "$OUTPUT_146/_logs"
  for i in $(seq 1 "$gap"); do
    local log="$OUTPUT_146/_logs/${model}_resume_$(date +%s)_${i}.log"
    nohup python scripts/experiments/full_690_runner.py "$model" "$OUTPUT_146" \
      --host "$host" --port "$port" >"$log" 2>&1 &
    disown
  done
}

echo "=== Phase B resume @ $(date '+%T') ==="

# 145 endpoints
echo "[1/3] verifying 145 endpoints"
for m in qwen4b qwen27b qwen35b gemma31b deepseek_r1_7b oss120b; do
  ensure_endpoint_145 "$m" "${MODEL_PORT[$m]}" "${MODEL_GPU[$m]}"
done

# 145 workers (skip gemma31b if done)
echo "[2/3] spawning 145 workers"
for m in qwen4b qwen27b qwen35b oss120b deepseek_r1_7b gemma31b; do
  eps=$(sudo -n -u anonymous-org ssh 127.0.0.1 "find $OUTPUT_145/$m -maxdepth 1 -name '*.json' 2>/dev/null | wc -l" 2>/dev/null)
  eps=${eps:-0}
  if [ "$eps" -ge "$TARGET_EPS" ]; then
    echo "  $m: $eps/$TARGET_EPS — DONE, skip"
    continue
  fi
  spawn_workers_145 "$m" "${MODEL_PORT[$m]}" "${MODEL_WORKERS[$m]}"
done

# 144 workers (called from 146)
echo "[3/3] spawning 146→144 workers"
spawn_workers_146_to_144 qwen397b 127.0.0.1 30001 16
spawn_workers_146_to_144 nemotron30b 127.0.0.1 30003 8
spawn_workers_146_to_144 nemotron30b 127.0.0.1 30004 8

echo "=== resume complete @ $(date '+%T') ==="
echo "Monitor with: bash scripts/infra/phase_b_monitor.sh"
