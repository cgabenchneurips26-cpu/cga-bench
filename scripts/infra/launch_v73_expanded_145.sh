#!/usr/bin/env bash
# Launch 6 vLLM models on server 145 (A100x8) for v7.3 expanded benchmark.
# Each model gets 1 GPU (TP=1). BF16 dtype for models that need it on A100.
#
# Usage:
#   bash scripts/infra/launch_v73_expanded_145.sh          # Launch all 6
#   bash scripts/infra/launch_v73_expanded_145.sh status    # Health check
#   bash scripts/infra/launch_v73_expanded_145.sh stop      # Kill all vLLM on 145
set -euo pipefail

SSH_KEY="/tmp/anonymous-org_key"
HOST="127.0.0.1
SSH_USER="anonymous-org"
VLLM_BIN="/home/anonymous-org/anaconda3/bin/vllm"
LOG_DIR="~/vllm_logs"
API_KEY="sk-no-key-required"

# Common vLLM flags
COMMON="--gpu-memory-utilization 0.92 --max-model-len 8192 --max-num-seqs 256 \
--enable-prefix-caching --enable-chunked-prefill --api-key ${API_KEY}"

ssh_cmd() {
    ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 "${SSH_USER}@${HOST}" "$@"
}

launch_model() {
    local gpu="$1" port="$2" model="$3" name="$4"
    shift 4
    local extra="$*"

    echo "[LAUNCH] GPU=$gpu PORT=$port MODEL=$model NAME=$name"
    ssh_cmd "mkdir -p ${LOG_DIR} && \
CUDA_VISIBLE_DEVICES=${gpu} nohup ${VLLM_BIN} serve ${model} \
  --port ${port} --tensor-parallel-size 1 ${COMMON} ${extra} \
  > ${LOG_DIR}/${name}.log 2>&1 & disown"
    echo "  -> PID launched, check ${LOG_DIR}/${name}.log"
}

health_check() {
    local port="$1" name="$2"
    local resp
    resp=$(curl -s -m 5 -H "Authorization: Bearer ${API_KEY}" \
        "http://${HOST}:${port}/v1/models" 2>/dev/null || echo "FAIL")
    if echo "$resp" | grep -q '"id"'; then
        echo "  [OK] ${name} on :${port}"
    else
        echo "  [FAIL] ${name} on :${port}"
    fi
}

case "${1:-launch}" in
    launch)
        echo "=== Launching 6 models on 145 ==="

        # GPU 0: Qwen3-4B (small, fast)
        launch_model 0 8101 "Qwen/Qwen3-4B-Instruct-2507" "qwen4b"

        # GPU 1: DeepSeek-R1-7B
        launch_model 1 30009 "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B" "deepseek_r1_7b"

        # GPU 2: Qwen3.5-27B (BF16 for A100 compat)
        launch_model 2 28010 "Qwen/Qwen3.5-27B" "qwen27b" "--dtype bfloat16"

        # GPU 3: Qwen3.5-35B-A3B (BF16 for A100 compat)
        launch_model 3 8013 "Qwen/Qwen3.5-35B-A3B" "qwen35b" "--dtype bfloat16"

        # GPU 4: Gemma-4-31B-IT (port 30210 — 30003 firewalled externally)
        launch_model 4 30210 "google/gemma-4-31b-it" "gemma31b" \
            "--limit-mm-per-prompt '{\"image\":0}' --trust-remote-code"

        # GPU 5: Nemotron-3-Nano-30B-A3B-BF16
        launch_model 5 30211 "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16" "nemotron30b"

        echo ""
        echo "=== All 6 launched. Wait 2-5 min for model loading. ==="
        echo "Run: bash $0 status    to verify"
        ;;

    status)
        echo "=== Health check: 145 endpoints ==="
        health_check 8101  "qwen4b"
        health_check 30009 "deepseek_r1_7b"
        health_check 28010 "qwen27b"
        health_check 8013  "qwen35b"
        health_check 30210 "gemma31b"
        health_check 30211 "nemotron30b"
        ;;

    stop)
        echo "=== Stopping all vLLM on 145 ==="
        ssh_cmd 'pkill -f "vllm serve" || true'
        echo "Done. Verify with: nvidia-smi on 145"
        ;;

    *)
        echo "Usage: $0 [launch|status|stop]"
        exit 1
        ;;
esac
