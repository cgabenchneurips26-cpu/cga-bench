#!/usr/bin/env bash
# v6 Phase A workers — Phase 1 of 2: 5 ready models on 145.
# Phase 2 launcher (gemma31b + nemotron30b) added once their endpoints come up.
set -uo pipefail

PYTHON=/home/anonymous-org/anaconda3/bin/python3
REPO=/home/anonymous-org/cga_bench
PARENT=/home/anonymous-org
LOGDIR=/home/anonymous-org/v6a_logs
OUTDIR=/home/anonymous-org/results/full_v6a_706
mkdir -p "$LOGDIR" "$OUTDIR"

export CGA_BENCH_EXCLUDE_AUTO=1
export PYTHONPATH="$PARENT"

launch_worker() {
  local model_key="$1" port="$2" shard="$3"
  local logname="${model_key}_$(echo "$shard" | tr '/' '_')"
  local log="${LOGDIR}/${logname}.log"
  echo "[worker] ${model_key} shard=${shard} port=${port} log=${log}"
  cd "$REPO"
  nohup "$PYTHON" scripts/experiments/full_690_runner.py \
    "$model_key" "$OUTDIR" \
    --host localhost --port "$port" --shard "$shard" \
    >"$log" 2>&1 &
  disown
}

for i in $(seq 1 32); do launch_worker qwen4b 30006 "$i/32"; done
for i in $(seq 1 32); do launch_worker deepseek_r1_7b 30012 "$i/32"; done
for i in $(seq 1 16); do launch_worker qwen27b 30007 "$i/16"; done
for i in $(seq 1 16); do launch_worker qwen35b 30008 "$i/16"; done
for i in $(seq 1 12); do launch_worker oss120b 30005 "$i/12"; done

echo "Phase-1 workers launched on 145: 32+32+16+16+12 = 108 workers."
