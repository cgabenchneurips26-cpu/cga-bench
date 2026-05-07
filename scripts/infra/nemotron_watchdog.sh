#!/usr/bin/env bash
# Watchdog: auto-restart dead nemotron containers on 144 H200.
# Polls every 60s, restarts any endpoint that doesn't answer /v1/models.
#
# Config per user-supplied guide (avoids Xid 43 with vllm:latest):
#   - vllm/vllm-openai:v0.12.0 (pinned)
#   - --tensor-parallel-size 2 across 2 GPUs
#   - --max-num-seqs 8 (low concurrency)
#   - --kv-cache-dtype fp8
#   - --tool-call-parser qwen3_coder
#   - --ipc host + --init for clean signal handling (no zombies)
#
# 4 instances total: a(GPU 0,1), b(GPU 2,3), c(GPU 4,5), d(GPU 6,7).
#
# Run from 146:
#   nohup bash scripts/infra/nemotron_watchdog.sh > /tmp/nemo_wd.log 2>&1 &
set -uo pipefail

ENDPOINTS=(
  "a 0,1 30013"
  "b 2,3 30014"
  "c 4,5 30015"
  "d 6,7 30016"
)

restart() {
  local name="$1" gpus="$2" port="$3"
  echo "[$(date +%T)] RESTART vllm-nemotron-${name} (GPU ${gpus}, port ${port})"
  sudo -n -u anonymous-org ssh [email-redacted] "docker rm -f vllm-nemotron-${name} 2>/dev/null; docker run -d --rm --runtime=nvidia --init --gpus '\"device=${gpus}\"' \
      --name vllm-nemotron-${name} \
      --ipc host \
      -v /home/anonymous-user/.cache/huggingface:/root/.cache/huggingface \
      -p ${port}:8000 \
      vllm/vllm-openai:v0.12.0 \
      --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8 \
      --port 8000 --tensor-parallel-size 2 \
      --max-num-seqs 8 \
      --max-model-len 32768 \
      --kv-cache-dtype fp8 \
      --tool-call-parser qwen3_coder \
      --enable-auto-tool-choice \
      --trust-remote-code \
      --api-key sk-no-key-required" 2>&1 | tail -1
}

while true; do
  for ep in "${ENDPOINTS[@]}"; do
    set -- $ep; name=$1; gpus=$2; port=$3
    if ! curl -s --max-time 5 -H "Authorization: Bearer sk-no-key-required" "http://localhost:8013${port}/v1/models" 2>/dev/null | grep -q "Nemotron"; then
      restart "$name" "$gpus" "$port"
      sleep 90
    fi
  done
  sleep 60
done
