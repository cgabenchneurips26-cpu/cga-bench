#!/usr/bin/env bash
# Launch v8-track1 vLLM fleet on 127.0.0.1 (A100 80GB × 8).
# Track 1 goal: complete v7 baseline by running 4 missing open-weight models
# (qwen4b, gemma31b, nemotron30b, llama4scout) on the v7 236-scenario corpus.
#
# This host serves the SMALLER 3 models with 2 instances each (max throughput
# for the 4B/27B/35B parameter range) plus llama4scout TP=2 instance #1.
# The 144 host (launch_vllm_v8_track1_144.sh) carries the 2nd llama instance
# and a 2nd round of the smaller models for further parallelism.
#
# GPU map:
#   GPU 0-1   llama4scout      port 30201   TP=2
#   GPU 2     qwen4b           port 30206   TP=1
#   GPU 3     qwen4b           port 30207   TP=1
#   GPU 4     gemma31b         port 30210   TP=1
#   GPU 5     gemma31b         port 30211   TP=1
#   GPU 6     nemotron30b      port 30220   TP=1
#   GPU 7     nemotron30b      port 30221   TP=1
#
# Precondition: all existing vllm processes on 145 stopped. User has confirmed
# all 8 GPUs are free (2026-04-28 session).
#
# Caller (from 146):
#   sudo -u anonymous-org ssh 127.0.0.1 'bash -s' < scripts/infra/launch_vllm_v8_track1_145.sh
set -euo pipefail

mkdir -p /home/anonymous-org/vllm_logs/v8_track1

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
  local log="/home/anonymous-org/vllm_logs/v8_track1/${name}.log"
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

# Llama-4-Scout (TP=2, GPUs 0-1)
launch llama4scout_a   0,1  30201 2 meta-llama/Llama-4-Scout-17B-16E-Instruct

# Qwen3-4B-Instruct ×2 (TP=1, GPUs 2-3)
launch qwen4b_a        2    30206 1 Qwen/Qwen3-4B-Instruct-2507
launch qwen4b_b        3    30207 1 Qwen/Qwen3-4B-Instruct-2507

# Gemma-4-31B-IT ×2 (TP=1, GPUs 4-5)
launch gemma31b_a      4    30210 1 google/gemma-4-31b-it
launch gemma31b_b      5    30211 1 google/gemma-4-31b-it

# Nemotron-3-Nano-30B-FP8 ×2 (TP=1, GPUs 6-7)
launch nemotron30b_a   6    30220 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8
launch nemotron30b_b   7    30221 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8

echo
echo "All 7 v8-track1 vLLM instances launched on 145."
echo "Logs: /home/anonymous-org/vllm_logs/v8_track1/*.log"
echo "Health: curl -H 'Authorization: Bearer sk-no-key-required' http://localhost:8013<port>/v1/models"
echo "Ports: 30201 (llama4scout), 30206-30207 (qwen4b), 30210-30211 (gemma31b), 30220-30221 (nemotron30b)"
