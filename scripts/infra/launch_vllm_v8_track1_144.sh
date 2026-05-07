#!/usr/bin/env bash
# Launch v8-track1 vLLM fleet on 127.0.0.1 (H200 143GB × 8).
# Track 1 goal: ADD parallel-throughput instances for the gemma31b and
# nemotron30b models (the slowest two of the four missing v7 baseline
# models). 144 only carries models whose weights are already cached
# locally so we don't pay 50+ GB downloads on the critical path.
#
# Cached on 144 (verified 2026-04-28):
#   google/gemma-4-31b-it                          ✓
#   nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8      ✓
# NOT cached on 144 (handled on 145 only):
#   meta-llama/Llama-4-Scout-17B-16E-Instruct      (50+ GB, skip)
#   Qwen/Qwen3-4B-Instruct-2507                    (only base 4B is cached)
#
# GPU map (144, 8× H200 143GB):
#   GPU 0   gemma31b         port 30310   TP=1
#   GPU 1   gemma31b         port 30311   TP=1
#   GPU 2   gemma31b         port 30312   TP=1
#   GPU 3   gemma31b         port 30313   TP=1
#   GPU 4   nemotron30b      port 30320   TP=1
#   GPU 5   nemotron30b      port 30321   TP=1
#   GPU 6   nemotron30b      port 30322   TP=1
#   GPU 7   nemotron30b      port 30323   TP=1
# 4× gemma31b + 4× nemotron30b = 8 GPUs used, both models 4× parallel.
#
# Caller (from 146):
#   sudo -u anonymous-org ssh [email-redacted] 'bash -s' < scripts/infra/launch_vllm_v8_track1_144.sh
set -euo pipefail

mkdir -p ~/vllm_logs/v8_track1

COMMON_FLAGS=(
  --gpu-memory-utilization 0.92
  --max-model-len 8192
  --max-num-seqs 256
  --enable-prefix-caching
  --enable-chunked-prefill
  --api-key sk-no-key-required
)

# vLLM lives in ~/.local/bin/ on 144 (verified 2026-04-28).
if [[ -x "${HOME}/.local/bin/vllm" ]]; then
  VLLM_BIN="${HOME}/.local/bin/vllm"
elif command -v vllm >/dev/null 2>&1; then
  VLLM_BIN="$(command -v vllm)"
else
  echo "[launch] ERROR: vllm binary not found on 144." >&2
  exit 1
fi

launch() {
  local name="$1" cuda="$2" port="$3" tp="$4" model="$5"
  shift 5
  local extra=("$@")
  local log="${HOME}/vllm_logs/v8_track1/${name}.log"
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

# 4× gemma31b on GPUs 0-3
launch gemma31b_c      0    30310 1 google/gemma-4-31b-it
launch gemma31b_d      1    30311 1 google/gemma-4-31b-it
launch gemma31b_e      2    30312 1 google/gemma-4-31b-it
launch gemma31b_f      3    30313 1 google/gemma-4-31b-it

# 4× nemotron30b on GPUs 4-7
launch nemotron30b_c   4    30320 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8
launch nemotron30b_d   5    30321 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8
launch nemotron30b_e   6    30322 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8
launch nemotron30b_f   7    30323 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8

echo
echo "8 v8-track1 vLLM instances launched on 144 (H200)."
echo "Logs: ~/vllm_logs/v8_track1/*.log"
echo "Health: curl -H 'Authorization: Bearer sk-no-key-required' http://localhost:8013<port>/v1/models"
echo "Ports: 30310-30313 (gemma31b ×4), 30320-30323 (nemotron30b ×4)"
