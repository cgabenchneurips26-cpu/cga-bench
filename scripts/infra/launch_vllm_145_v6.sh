#!/usr/bin/env bash
# Launch v6 vLLM fleet on 127.0.0.1 (A100 80GB × 8).
# 7 dedicated single-model endpoints + 1 oss120b TP=2 = 8 GPUs used.
#
# Models (excludes qwen397b which lives on 144 and llama3b dropped from v6):
#   GPU 0  qwen4b           port 30006   TP=1
#   GPU 1  qwen27b          port 30007   TP=1
#   GPU 2  qwen35b          port 30008   TP=1
#   GPU 3  gemma31b         port 30010   TP=1
#   GPU 4  nemotron30b      port 30011   TP=1
#   GPU 5  deepseek_r1_7b   port 30012   TP=1
#   GPU 6-7 oss120b         port 30005   TP=2
#
# Precondition: all existing vllm processes on 145 stopped.
# Caller (from 146):
#   sudo -u anonymous-org ssh 127.0.0.1 'bash -s' < scripts/infra/launch_vllm_145_v6.sh
set -euo pipefail

mkdir -p /home/anonymous-org/vllm_logs

COMMON_FLAGS=(
  --gpu-memory-utilization 0.92
  --max-model-len 8192
  --max-num-seqs 256
  --enable-prefix-caching
  --enable-chunked-prefill
  --api-key sk-no-key-required
)

VLLM_BIN=/home/anonymous-org/anaconda3/bin/vllm

launch() {
  local name="$1" cuda="$2" port="$3" tp="$4" model="$5"
  shift 5
  local extra=("$@")
  local log="/home/anonymous-org/vllm_logs/${name}.log"
  echo "[launch] name=${name} cuda=${cuda} port=${port} tp=${tp} model=${model}"
  CUDA_VISIBLE_DEVICES="${cuda}" nohup "${VLLM_BIN}" serve "${model}" \
    --port "${port}" \
    --tensor-parallel-size "${tp}" \
    "${COMMON_FLAGS[@]}" \
    "${extra[@]}" \
    >"${log}" 2>&1 &
  disown
  echo "[launch] ${name} -> PID $!  log=${log}"
}

launch qwen4b          0   30006 1 Qwen/Qwen3-4B-Instruct-2507
launch qwen27b         1   30007 1 Qwen/Qwen3.5-27B-FP8
launch qwen35b         2   30008 1 Qwen/Qwen3.5-35B-A3B-FP8
launch gemma31b        3   30010 1 google/gemma-4-31b-it
launch nemotron30b     4   30011 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8
launch deepseek_r1_7b  5   30012 1 deepseek-ai/DeepSeek-R1-Distill-Qwen-7B
launch oss120b         6,7 30005 2 openai/gpt-oss-120b

echo
echo "All 7 vLLM instances launched on 145. Logs: /home/anonymous-org/vllm_logs/*.log"
echo "Health check: curl -H 'Authorization: Bearer sk-no-key-required' http://localhost:8013<port>/v1/models"
