#!/usr/bin/env bash
# Launch Llama-4-Scout-17B-16E-Instruct on 145 with TP=4 across the four
# currently-idle A100 80GB GPUs (0, 1, 6, 7). The original launch_vllm_
# v8_track1_145.sh had llama4scout at TP=2 (GPUs 0-1) and OOM'd at exactly
# 160 GB total (model is ~218 GB BF16; 109B param MoE with 17B active).
#
# TP=4 → 4 × 80 = 320 GB combined → fits with margin.
# Model is already cached locally at /home/anonymous-org/.cache/huggingface/hub/
# models--meta-llama--Llama-4-Scout-17B-16E-Instruct so no download.
#
# Other 4 GPUs on 145 are reserved:
#   GPU 2,3 — qwen4b ×2 (do not disturb, expansion_runner active)
#   GPU 4,5 — gemma31b ×2 (do not disturb, expansion_runner active)
#
# Usage:
#   sudo -u anonymous-org ssh 127.0.0.1 'bash -s' < scripts/infra/launch_vllm_v8_track1_llama4scout_tp4.sh
set -euo pipefail

mkdir -p /home/anonymous-org/vllm_logs/v8_track1

VLLM_BIN=/home/anonymous-org/anaconda3/bin/vllm
LOG=/home/anonymous-org/vllm_logs/v8_track1/llama4scout_tp4.log

CUDA_VISIBLE_DEVICES=0,1,6,7 nohup "$VLLM_BIN" serve meta-llama/Llama-4-Scout-17B-16E-Instruct \
  --port 30401 \
  --tensor-parallel-size 4 \
  --gpu-memory-utilization 0.92 \
  --max-model-len 8192 \
  --max-num-seqs 256 \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --api-key sk-no-key-required \
  --trust-remote-code \
  >"$LOG" 2>&1 &
disown
echo "[launch] llama4scout_tp4 PID=$!  GPUs=0,1,6,7  port=30401  log=$LOG"
echo "Health: curl -H 'Authorization: Bearer sk-no-key-required' http://localhost:8013/v1/models"
