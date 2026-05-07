#!/usr/bin/env bash
# v6 Phase A qwen397b workers from 146 → 144 endpoints.
#
# 2 instances on 144 (TP=4 each, ports 30001 and 30002).
# 8 workers per instance = 16 total qwen397b workers.
# Output: results/full_v6a_706/qwen397b/
set -uo pipefail

REPO=/home/anonymous-org/anonymous-project/AnonProject/cga_bench
LOGDIR="${REPO}/results/full_v6a_706/_logs"
OUTDIR="${REPO}/results/full_v6a_706"
mkdir -p "$LOGDIR" "$OUTDIR"

export CGA_BENCH_EXCLUDE_AUTO=1
export PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject

launch_worker() {
  local port="$1" shard="$2"
  local logname="qwen397b_p${port}_$(echo "$shard" | tr '/' '_')"
  local log="${LOGDIR}/${logname}.log"
  echo "[worker] qwen397b shard=${shard} port=${port} log=${log}"
  cd "$REPO"
  nohup python scripts/experiments/full_690_runner.py \
    qwen397b "$OUTDIR" \
    --host 127.0.0.1 --port "$port" --shard "$shard" \
    >"$log" 2>&1 &
  disown
}

# Single qwen397b instance on 144:30001 (30002 disabled due to shm_broadcast).
# 8 workers — project rule: ≥200B models use 4-8 workers.
for i in $(seq 1 8); do launch_worker 30001 "$i/8"; done

echo
echo "qwen397b workers launched: 8 total on 144:30001."
echo "Logs: ${LOGDIR}/qwen397b_p<port>_<shard>.log"
