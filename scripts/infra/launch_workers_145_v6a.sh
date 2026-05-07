#!/usr/bin/env bash
# v6 Phase A workers — 7 models × 706×3 = 14,826 episodes on 145.
#
# Runs ON 127.0.0.1 (workers + endpoints co-located, no network hop).
# Caller from 146:
#   sudo -u anonymous-org ssh 127.0.0.1 'bash -s' < scripts/infra/launch_workers_145_v6a.sh
#
# Precondition: scripts/infra/launch_vllm_145_v6.sh ran successfully and all 7
# vLLM endpoints respond on /v1/models (qwen4b 30006, qwen27b 30007, qwen35b 30008,
# gemma31b 30010, nemotron30b 30011, deepseek_r1_7b 30012, oss120b 30005).
set -uo pipefail

PYTHON=/home/anonymous-org/anaconda3/bin/python3
REPO=/home/anonymous-org/cga_bench    # symlink → cga_bench_v6
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

# qwen4b — 4B model, 32 workers
for i in $(seq 1 32); do launch_worker qwen4b 30006 "$i/32"; done
# deepseek_r1_7b — 7B model, 32 workers
for i in $(seq 1 32); do launch_worker deepseek_r1_7b 30012 "$i/32"; done
# qwen27b — 27B dense, 16 workers
for i in $(seq 1 16); do launch_worker qwen27b 30007 "$i/16"; done
# qwen35b — 35B MoE, 16 workers
for i in $(seq 1 16); do launch_worker qwen35b 30008 "$i/16"; done
# gemma31b — 31B, 16 workers
for i in $(seq 1 16); do launch_worker gemma31b 30010 "$i/16"; done
# nemotron30b — 30B, 16 workers
for i in $(seq 1 16); do launch_worker nemotron30b 30011 "$i/16"; done
# oss120b — 120B TP=2, 12 workers
for i in $(seq 1 12); do launch_worker oss120b 30005 "$i/12"; done

echo
echo "All v6a workers launched on 145. Total: 32+32+16+16+16+16+12 = 140 workers."
echo "Logs: ${LOGDIR}/<model>_<i_N>.log"
echo "Output: ${OUTDIR}/<model>/<scenario>_<model>_r<run>_<ts>.json"
echo "Monitor: ls ${OUTDIR}/<model>/ | wc -l"
