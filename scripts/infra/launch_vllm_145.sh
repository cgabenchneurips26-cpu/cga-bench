#!/usr/bin/env bash
# Launch standard vLLM fleet on 127.0.0.1 (A100 80GB × 8).
# Model-to-GPU mapping is intentional: see .claude/rules/vllm-launch.md for
# the rationale (prefix caching + max-model-len=8192 + max-num-seqs=256 are
# project-standard options that combine to ~3x throughput over defaults).
#
# Precondition: all existing vllm processes on 145 have been stopped.
# Intended caller from 146:
#   sudo -u anonymous-org ssh 127.0.0.1 'bash -s' < scripts/infra/launch_vllm_145.sh
#
# Safety: each model is backgrounded with nohup; STDIO/ERR redirected to
# /var/log/vllm/<name>.log. Wait for health (/v1/models) before routing
# traffic.
set -euo pipefail

mkdir -p /var/log/vllm

# Common flags for every instance. See .claude/rules/vllm-launch.md.
COMMON_FLAGS=(
  --gpu-memory-utilization 0.92
  --max-model-len 8192
  --max-num-seqs 256
  --enable-prefix-caching
  --enable-chunked-prefill
  --api-key sk-no-key-required
)

launch() {
  local name="$1"       # log label
  local cuda="$2"       # CUDA_VISIBLE_DEVICES value
  local port="$3"       # host port
  local tp="$4"         # tensor-parallel-size
  local model="$5"      # HF model id
  shift 5
  local extra=("$@")    # any model-specific flags

  local log="/var/log/vllm/${name}.log"
  echo "[launch] name=${name} cuda=${cuda} port=${port} tp=${tp} model=${model}"
  CUDA_VISIBLE_DEVICES="${cuda}" nohup vllm serve "${model}" \
    --port "${port}" \
    --tensor-parallel-size "${tp}" \
    "${COMMON_FLAGS[@]}" \
    "${extra[@]}" \
    >"${log}" 2>&1 &
  disown
  echo "[launch] ${name} -> PID $!  log=${log}"
}

# GPU 0: qwen4b instance #1
launch qwen4b_1        0   30006 1 Qwen/Qwen3-4B-Instruct-2507

# GPU 1: qwen4b instance #2 (the 4B model sees the heaviest sweep traffic)
launch qwen4b_2        1   30008 1 Qwen/Qwen3-4B-Instruct-2507

# GPU 2: qwen27b FP8
launch qwen27b         2   30003 1 Qwen/Qwen3.5-27B-FP8

# GPU 3: qwen35b MoE FP8
launch qwen35b         3   30007 1 Qwen/Qwen3.5-35B-A3B-FP8

# GPU 4: gemma-31b (BF16 default, ~62GB — fits in 80GB at 0.92 util)
launch gemma31b        4   30004 1 google/gemma-4-31b-it

# GPU 5: deepseek r1 distill 7b
launch deepseek_r1_7b  5   30009 1 deepseek-ai/DeepSeek-R1-Distill-Qwen-7B

# GPUs 6-7: oss120b TP=2
launch oss120b         6,7 30005 2 openai/gpt-oss-120b

echo
echo "All 7 vLLM instances launched. Logs: /var/log/vllm/*.log"
echo "Health check: curl -H 'Authorization: Bearer sk-no-key-required' http://localhost:<port>/v1/models"
