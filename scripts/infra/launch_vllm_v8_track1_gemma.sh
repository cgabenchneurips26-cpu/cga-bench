#!/usr/bin/env bash
# Re-launch gemma-4-31b-it after 145's transformers upgrade (4.57.6 → 5.6.2,
# applied 2026-04-28 to fix the "model type 'gemma4' not recognized" load
# failure of the original launch_vllm_v8_track1_145.sh script).
#
# Two instances on 145 GPUs 4-5 (currently idle) for parallel throughput
# matching the qwen4b ×2 setup already running on GPUs 2-3.
#
# Usage:
#   sudo -u anonymous-org ssh 127.0.0.1 'bash -s' < scripts/infra/launch_vllm_v8_track1_gemma.sh
set -euo pipefail

VLLM_BIN=/home/anonymous-org/anaconda3/bin/vllm
LOG_DIR=/home/anonymous-org/vllm_logs/v8_track1
mkdir -p "$LOG_DIR"

COMMON_FLAGS=(
  --gpu-memory-utilization 0.92
  --max-model-len 8192
  --max-num-seqs 256
  --enable-prefix-caching
  --enable-chunked-prefill
  --api-key sk-no-key-required
)

launch() {
  local name="$1" cuda="$2" port="$3" model="$4"
  local log="${LOG_DIR}/${name}.log"
  echo "[launch] name=${name} cuda=${cuda} port=${port} model=${model}"
  CUDA_VISIBLE_DEVICES="${cuda}" nohup "${VLLM_BIN}" serve "${model}" \
    --port "${port}" \
    --tensor-parallel-size 1 \
    "${COMMON_FLAGS[@]}" \
    >"${log}" 2>&1 &
  disown
  echo "[launch] ${name} -> PID $!  log=${log}"
}

# GPUs 4-5 (currently idle on 145; previously failed to load gemma31b)
launch gemma31b_v2_a 4 30210 google/gemma-4-31b-it
launch gemma31b_v2_b 5 30211 google/gemma-4-31b-it

echo
echo "2 gemma31b instances re-launched on 145 with transformers 5.6.2."
echo "Health: curl -H 'Authorization: Bearer sk-no-key-required' http://localhost:8013/v1/models"
