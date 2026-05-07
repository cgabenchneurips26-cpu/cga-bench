#!/usr/bin/env bash
# Final attempt: launch nemotron30b ×8 on 144 H200 after the env-fix chain:
#   - vLLM 0.20 → 0.19 (driver 12080 compat)
#   - torchao 0.12.0 uninstalled (was importing missing torch._inductor)
#   - ninja installed (FX graph compile in NemotronH FP8 inference)
# All four GPUs idle on 144 at this attempt.
set -euo pipefail

mkdir -p ~/vllm_logs/v8_track1

VLLM=~/.local/bin/vllm

COMMON_FLAGS=(
  --gpu-memory-utilization 0.90
  --max-model-len 8192
  --max-num-seqs 256
  --enable-prefix-caching
  --enable-chunked-prefill
  --api-key sk-no-key-required
  --trust-remote-code
)

MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8

for i in 0 1 2 3 4 5 6 7; do
  port=$((30420 + i))
  log=~/vllm_logs/v8_track1/nemo_v6_${i}.log
  echo "[launch] cuda=${i} port=${port} log=${log}"
  CUDA_VISIBLE_DEVICES=${i} nohup "${VLLM}" serve "${MODEL}" \
    --port "${port}" \
    --tensor-parallel-size 1 \
    "${COMMON_FLAGS[@]}" \
    > "${log}" 2>&1 &
  disown
  echo "[launch] PID=$!"
done

echo "Done — 8 nemotron30b instances launched. Check logs in ~/vllm_logs/v8_track1/"
