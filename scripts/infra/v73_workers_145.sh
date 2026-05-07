#!/usr/bin/env bash
# v7.3 co-located workers on 145 — shard 2/2.
# All endpoints are on 146 (127.0.0.1 or 144 (127.0.0.1
# Results written to 145 local disk, rsync back to 146 after completion.
#
# Prerequisites:
#   1. rsync code: sudo -u anonymous-org rsync ... 127.0.0.1
#   2. pip3 install: openai pydantic rank_bm25 tiktoken numpy
#
# Usage:
#   sudo -n -u anonymous-org ssh 127.0.0.1 'bash /home/anonymous-org/bench_ws/cga_bench/scripts/infra/v73_workers_145.sh'
#   # Or from 146:
#   bash scripts/infra/v73_workers_145.sh   # (ssh wrapper)

set -uo pipefail

# ─── Config ─────────────────────────────────────────────────────────

ROOT_145=/home/anonymous-org/bench_ws/cga_bench
OUTPUT_145="$ROOT_145/results/v73_full"
LOGDIR_145="$OUTPUT_145/_logs"
SHARD="2/2"
EP_HOST=127.0.0.1   # 146's endpoints
EP_144=127.0.0.1    # 144's qwen397b

mkdir -p "$OUTPUT_145" "$LOGDIR_145"
cd "$ROOT_145"

ts() { date '+%H:%M:%S'; }

# ─── Worker Spawn ───────────────────────────────────────────────────

spawn() {
  local model_key="$1" n_workers="$2" host="$3" port="$4"
  echo "[$(ts)] 145: Spawning $n_workers workers for $model_key (shard $SHARD → $host:$port)"
  for i in $(seq 1 "$n_workers"); do
    local log="$LOGDIR_145/${model_key}_145_w${i}_$(date +%s).log"
    nohup env \
      PYTHONPATH="$ROOT_145/..":"$ROOT_145" \
      python3 "$ROOT_145/scripts/experiments/full_v73_runner.py" \
      "$model_key" "$OUTPUT_145" \
      --host "$host" --port "$port" --shard "$SHARD" \
      >"$log" 2>&1 &
    disown
  done
}

# ─── Launch ─────────────────────────────────────────────────────────

echo ""
echo "================================================================"
echo "[$(ts)] v7.3 Workers on 145 (shard $SHARD)"
echo "  Output: $OUTPUT_145"
echo "  Endpoints: $EP_HOST (146 models), $EP_144 (qwen397b)"
echo "================================================================"

# 146-hosted models: call via network
spawn qwen4b          32  "$EP_HOST" 8101
spawn deepseek_r1_7b  32  "$EP_HOST" 30009
spawn qwen27b         16  "$EP_HOST" 28010
spawn qwen35b         16  "$EP_HOST" 8013
spawn gemma31b        16  "$EP_HOST" 30003
spawn nemotron30b      8  "$EP_HOST" 30004

# 144-hosted model: qwen397b (two instances)
spawn qwen397b        12  "$EP_144" 30001
spawn qwen397b_s2     12  "$EP_144" 30002

echo ""
echo "[$(ts)] All 145 workers spawned. Total: $(( 32+32+16+16+16+8+12+12 )) workers"
echo "  Monitor: ps aux | grep full_v73_runner | grep -v grep | wc -l"
echo "  Rsync back: sudo -u anonymous-org rsync -az 127.0.0.1 /path/to/146/results/v73_full/"
