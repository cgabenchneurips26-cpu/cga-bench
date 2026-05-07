#!/usr/bin/env bash
# Re-launch on 144 (H200 143GB × 8) AFTER vLLM upgrade to >= 0.19.
#
# Two models — neither runs on 145:
#   nemotron30b: needs compute capability 8.9+ for modelopt FP8 (H200=9.0; A100=8.0 fails)
#   llama4scout: 109B model needs ~218GB BF16; A100 80GB×2 OOMs at TP=2;
#                144 H200 143GB×2 = 286GB at TP=2 fits with margin
#
# vLLM lazy-downloads weights on first launch — llama4scout will pull
# ~50GB FP8 or ~218GB BF16 from HF on the first call. The 144 HF cache
# has ~592GB free at v8 build time so this is fine.
#
# GPU map (144):
#   GPU 0-1   llama4scout      port 30401   TP=2
#   GPU 2     nemotron30b      port 30420   TP=1
#   GPU 3     nemotron30b      port 30421   TP=1
#   GPU 4     nemotron30b      port 30422   TP=1
#   GPU 5     nemotron30b      port 30423   TP=1
#   GPU 6     nemotron30b      port 30424   TP=1
#   GPU 7     nemotron30b      port 30425   TP=1
# 1× llama4scout TP=2 + 6× nemotron30b TP=1 = uses all 8 H200s.
#
# Usage:
#   sudo -u anonymous-org ssh [email-redacted] 'bash -s' < scripts/infra/launch_vllm_v8_track1_144_v2.sh
set -euo pipefail

mkdir -p ~/vllm_logs/v8_track1

VLLM_BIN=${HOME}/.local/bin/vllm
if ! [[ -x "$VLLM_BIN" ]]; then
  if command -v vllm >/dev/null 2>&1; then
    VLLM_BIN="$(command -v vllm)"
  else
    echo "[launch] ERROR: vllm binary not found on 144." >&2
    exit 1
  fi
fi

COMMON_FLAGS=(
  --gpu-memory-utilization 0.90
  --max-model-len 8192
  --max-num-seqs 256
  --enable-prefix-caching
  --enable-chunked-prefill
  --api-key sk-no-key-required
  --trust-remote-code
)

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

# Llama-4-Scout TP=2 on H200 GPUs 0-1 (109B BF16 ≈ 218GB; 286GB available)
launch llama4scout_v2  0,1  30401 2 meta-llama/Llama-4-Scout-17B-16E-Instruct

# 6× nemotron30b on H200 GPUs 2-7 (FP8 modelopt requires capability 8.9+;
# H200 = 9.0 ✓)
launch nemotron30b_v2_a 2  30420 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8
launch nemotron30b_v2_b 3  30421 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8
launch nemotron30b_v2_c 4  30422 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8
launch nemotron30b_v2_d 5  30423 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8
launch nemotron30b_v2_e 6  30424 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8
launch nemotron30b_v2_f 7  30425 1 nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8

echo
echo "1× llama4scout TP=2 + 6× nemotron30b TP=1 launched on 144 H200."
echo "Logs: ~/vllm_logs/v8_track1/*.log"
echo "Health: curl -H 'Authorization: Bearer sk-no-key-required' http://localhost:8013<port>/v1/models"
echo "Ports: 30401 (llama4scout), 30420-30425 (nemotron30b ×6)"
