#!/usr/bin/env bash
# Launch nemotron30b on 144 via Docker per /home/anonymous-org/gemma_nemotron_setup.md.
# Uses vllm/vllm-openai:latest container (host driver bypass via container CUDA),
# with the recommended config: TP=2, --max-num-seqs 8, --kv-cache-dtype fp8,
# --tool-call-parser qwen3_coder. 4 instances spread across 8 H200 GPUs.
#
# Caller (from 146):
#   sudo -u anonymous-org ssh [email-redacted] 'bash -s' < scripts/infra/launch_nemotron_docker_144.sh
set -euo pipefail

HF=/home/anonymous-user/.cache/huggingface

for spec in 0,1:30420 2,3:30422 4,5:30424 6,7:30426; do
  gpus=${spec%:*}
  port=${spec#*:}
  pname=$(echo "$gpus" | tr ',' '-')
  cname=nemotron-$pname

  docker rm -f "$cname" 2>/dev/null || true

  echo "[launch] $cname GPU=$gpus port=$port"
  docker run -d \
    --name "$cname" \
    --ipc host \
    --gpus "\"device=$gpus\"" \
    -p "$port:$port" \
    -v "$HF:/root/.cache/huggingface" \
    vllm/vllm-openai:latest \
    --model nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8 \
    --max-num-seqs 8 \
    --tensor-parallel-size 2 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.85 \
    --trust-remote-code \
    --kv-cache-dtype fp8 \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder \
    --host 0.0.0.0 \
    --port "$port" \
    --api-key sk-no-key-required
done

echo
echo "Containers launched. Wait ~3-5 min for model load, then health-check:"
echo "  curl -H 'Authorization: Bearer sk-no-key-required' http://localhost:8013/v1/models"
docker ps --format '{{.Names}}\t{{.Status}}' | grep nemotron | head -5
