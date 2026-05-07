#!/usr/bin/env bash
# Re-launch nemotron30b on 145 + 144 (post-fix: add --trust-remote-code).
# nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8 ships custom modeling code that
# vLLM's pydantic ModelConfig refuses to accept without explicit consent —
# hence --trust-remote-code which is the documented escape hatch for HF
# repos with custom Python in their checkpoint.
#
# Usage:
#   sudo -u anonymous-org ssh 127.0.0.1 'bash -s' < scripts/infra/launch_vllm_v8_track1_nemotron.sh 145
#   sudo -u anonymous-org ssh [email-redacted] 'bash -s' < scripts/infra/launch_vllm_v8_track1_nemotron.sh 144
set -euo pipefail

HOST="${1:-145}"

if [[ "$HOST" == "145" ]]; then
  VLLM_BIN=/home/anonymous-org/anaconda3/bin/vllm
  LOG_DIR=/home/anonymous-org/vllm_logs/v8_track1
  # 145 has 8× A100 80GB. GPUs 0,1 reserved for llama4scout (failed → skip).
  # 2,3 = qwen4b (already running). 4,5 free (gemma failed). 6,7 = nemotron.
  GPUS=(6 7)
  PORTS=(30220 30221)
  NAMES=(nemotron30b_a nemotron30b_b)
elif [[ "$HOST" == "144" ]]; then
  VLLM_BIN="${HOME}/.local/bin/vllm"
  LOG_DIR="${HOME}/vllm_logs/v8_track1"
  # 144 has 8× H200 143GB. Use 4 GPUs for nemotron (more parallelism).
  GPUS=(4 5 6 7)
  PORTS=(30320 30321 30322 30323)
  NAMES=(nemotron30b_c nemotron30b_d nemotron30b_e nemotron30b_f)
else
  echo "Unknown host: $HOST (expected 145 or 144)" >&2
  exit 2
fi

mkdir -p "$LOG_DIR"

COMMON_FLAGS=(
  --gpu-memory-utilization 0.92
  --max-model-len 8192
  --max-num-seqs 256
  --enable-prefix-caching
  --enable-chunked-prefill
  --api-key sk-no-key-required
  --trust-remote-code
)

MODEL=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8

for i in "${!GPUS[@]}"; do
  cuda="${GPUS[$i]}"
  port="${PORTS[$i]}"
  name="${NAMES[$i]}"
  log="${LOG_DIR}/${name}.log"
  echo "[launch] host=${HOST} name=${name} cuda=${cuda} port=${port} model=${MODEL}"
  CUDA_VISIBLE_DEVICES="${cuda}" nohup "${VLLM_BIN}" serve "${MODEL}" \
    --port "${port}" \
    --tensor-parallel-size 1 \
    "${COMMON_FLAGS[@]}" \
    >"${log}" 2>&1 &
  disown
  echo "[launch] ${name} -> PID $!  log=${log}"
done

echo
echo "${#GPUS[@]} nemotron30b instances launched on ${HOST}."
echo "Health: curl -H 'Authorization: Bearer sk-no-key-required' http://127.0.0.1
