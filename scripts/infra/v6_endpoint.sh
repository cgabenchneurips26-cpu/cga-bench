#!/usr/bin/env bash
# v6 endpoint management — launch / stop vLLM containers per model
# with the v6-validated configuration baked in.
#
# Each model has a known-good docker config (Phase A discovered the
# right combination per model). This script wraps those.
#
# Usage:
#   bash scripts/infra/v6_endpoint.sh launch <model> <host> <gpu> <port>
#   bash scripts/infra/v6_endpoint.sh stop   <host> <name>
#   bash scripts/infra/v6_endpoint.sh listall
set -uo pipefail

CMD="${1:-help}"

# ─── known-good per-model launch configs ──────────────────────

# Args: $1 host(144/145/146)  $2 gpu_spec  $3 port  $4 model_key
launch_endpoint() {
  local host="$1" gpu="$2" port="$3" model="$4"

  local hostnet cache cache_mount
  case "$host" in
    144) hostnet="[email-redacted]"; cache="/home/anonymous-user/.cache/huggingface"; cache_mount="/root/.cache/huggingface" ;;
    145) hostnet="127.0.0.1 cache="/home/anonymous-org/.cache/huggingface"; cache_mount="/root/.cache/huggingface" ;;
    146) hostnet=""; cache="/home/hub"; cache_mount="/root/.cache/huggingface/hub" ;;
    *) echo "host must be 144/145/146"; return 1 ;;
  esac

  # GPU isolation via NVIDIA_VISIBLE_DEVICES env (works with --runtime=nvidia)
  # Avoids the docker `--gpus "device=X,Y"` quoting bug when piped through ssh+bash:
  # the inner double-quotes get stripped, docker daemon then reports
  # `cannot set both Count and DeviceIDs on device request`. The env-var form
  # has no quoting ambiguity.
  local docker_args=(
    -d --rm --runtime=nvidia --init
    -e "NVIDIA_VISIBLE_DEVICES=${gpu}"
    --ipc host
    -v "${cache}:${cache_mount}"
    -p "${port}:8000"
  )

  case "$model" in
    qwen397b)
      local image="vllm-qwen35:latest"
      local model_id="Qwen/Qwen3.5-397B-A17B-FP8"
      local extra="--tensor-parallel-size 4 --max-model-len 16384 --gpu-memory-utilization 0.90 --tool-call-parser hermes --enable-auto-tool-choice"
      ;;
    nemotron30b)
      local image="vllm/vllm-openai:v0.12.0"
      local model_id="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8"
      local extra="--tensor-parallel-size 2 --max-num-seqs 8 --max-model-len 32768 --kv-cache-dtype fp8 --tool-call-parser qwen3_coder --enable-auto-tool-choice --trust-remote-code"
      ;;
    gemma31b)
      local image="vllm/vllm-openai:nightly"
      local model_id="google/gemma-4-31b-it"
      local extra='--tensor-parallel-size 1 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --max-num-batched-tokens 8192 --limit-mm-per-prompt {\"image\":0} --enable-prefix-caching --enable-chunked-prefill --trust-remote-code'
      ;;
    qwen35b)
      local image="vllm/vllm-openai:latest"
      local model_id="Qwen/Qwen3.5-35B-A3B-FP8"
      local extra="--tensor-parallel-size 1 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill"
      ;;
    qwen27b)
      local image="vllm/vllm-openai:latest"
      local model_id="Qwen/Qwen3.5-27B-FP8"
      local extra="--tensor-parallel-size 1 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill"
      ;;
    qwen4b)
      local image="vllm/vllm-openai:latest"
      local model_id="Qwen/Qwen3-4B-Instruct-2507"
      local extra="--tensor-parallel-size 1 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill"
      ;;
    deepseek_r1_7b)
      local image="vllm/vllm-openai:latest"
      local model_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
      local extra="--tensor-parallel-size 1 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill"
      ;;
    oss120b)
      local image="vllm/vllm-openai:latest"
      local model_id="openai/gpt-oss-120b"
      local extra="--tensor-parallel-size 2 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill"
      ;;
    # ── BF16 variants for A100 (compute cap 8.0 — FP8 needs 8.9+) ──
    nemotron30b_bf16)
      local image="vllm/vllm-openai:latest"
      local model_id="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
      local extra="--tensor-parallel-size 2 --max-num-seqs 8 --max-model-len 8192 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill --trust-remote-code"
      ;;
    qwen35b_bf16)
      local image="vllm/vllm-openai:latest"
      local model_id="Qwen/Qwen3.5-35B-A3B"
      local extra="--tensor-parallel-size 1 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill"
      ;;
    qwen27b_bf16)
      local image="vllm/vllm-openai:latest"
      local model_id="Qwen/Qwen3.5-27B"
      local extra="--tensor-parallel-size 1 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill"
      ;;
    gemma31b_local)
      local image="vllm/vllm-openai:latest"
      local model_id="google/gemma-4-31b-it"
      local extra='--tensor-parallel-size 1 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --max-num-batched-tokens 8192 --limit-mm-per-prompt {\"image\":0} --enable-prefix-caching --enable-chunked-prefill --trust-remote-code'
      ;;
    llama4scout)
      local image="vllm/vllm-openai:latest"
      local model_id="meta-llama/Llama-4-Scout-17B-16E-Instruct"
      local extra="--tensor-parallel-size 4 --max-model-len 8192 --max-num-seqs 256 --gpu-memory-utilization 0.92 --enable-prefix-caching --enable-chunked-prefill --trust-remote-code"
      ;;
    *) echo "Unknown model: $model"; return 1 ;;
  esac

  local name="vllm-${model}-${host}-g${gpu//,/-}-p${port}"
  local cmd="docker run ${docker_args[*]} --name ${name} ${image} --model ${model_id} --port 8000 ${extra} --api-key sk-no-key-required"

  # Capture output + exit code so docker errors are not swallowed.
  # Previous version used `... | tail -1; echo launched ${name}` which
  # printed "launched" even when docker run failed.
  local rc=0 output
  if [ -n "$hostnet" ]; then
    output=$(sudo -n -u anonymous-org ssh "$hostnet" "$cmd" 2>&1) || rc=$?
  else
    output=$(eval "$cmd" 2>&1) || rc=$?
  fi
  if [ "$rc" -ne 0 ]; then
    echo "  ERROR launching ${name} (docker run rc=${rc}):"
    echo "$output" | sed 's/^/    /'
    return 1
  fi

  # Race-safe presence check: container could docker-run-ok but vllm
  # crash within seconds and --rm wipes it. Verify it stays up briefly.
  sleep 3
  local ps_check
  if [ -n "$hostnet" ]; then
    ps_check=$(sudo -n -u anonymous-org ssh "$hostnet" "docker ps --format '{{.Names}}' | grep -Fx '${name}' || true")
  else
    ps_check=$(docker ps --format '{{.Names}}' | grep -Fx "${name}" || true)
  fi
  if [ -z "$ps_check" ]; then
    echo "  ERROR ${name}: container exited within 3s of launch"
    echo "    docker run output:"
    echo "$output" | tail -5 | sed 's/^/      /'
    return 1
  fi
  local cid
  cid=$(echo "$output" | tail -1 | cut -c1-12)
  echo "  launched ${name} (cid=${cid})"
}

stop_endpoint() {
  local host="$1" name="$2"
  case "$host" in
    144) sudo -n -u anonymous-org ssh [email-redacted] "docker rm -f ${name}" 2>&1 | tail -1 ;;
    145) sudo -n -u anonymous-org ssh 127.0.0.1 "docker rm -f ${name}" 2>&1 | tail -1 ;;
    146) docker rm -f "${name}" 2>&1 | tail -1 ;;
  esac
}

list_all_endpoints() {
  echo "=== 144 ==="
  sudo -n -u anonymous-org ssh [email-redacted] 'docker ps --format "  {{.Names}}\t{{.Status}}"' 2>&1 | grep -i vllm
  echo "=== 145 ==="
  sudo -n -u anonymous-org ssh 127.0.0.1 'docker ps --format "  {{.Names}}\t{{.Status}}"' 2>&1 | grep -i vllm
  echo "=== 146 ==="
  docker ps --format "  {{.Names}}\t{{.Status}}" 2>&1 | grep -i vllm
}

case "$CMD" in
  launch)  launch_endpoint "$2" "$3" "$4" "$5" ;;
  stop)    stop_endpoint "$2" "$3" ;;
  listall) list_all_endpoints ;;
  *)
    cat <<EOF
v6 endpoint management

  launch  <host:144|145|146> <gpu_spec> <port> <model_key>
  stop    <host:144|145|146> <container_name>
  listall

Models with v6-validated configs: qwen397b, nemotron30b, gemma31b,
qwen35b, qwen27b, qwen4b, deepseek_r1_7b, oss120b

Examples:
  bash $0 launch 144 0,1,2,3 30001 qwen397b
  bash $0 launch 145 3 30010 gemma31b
  bash $0 launch 144 4,5 30013 nemotron30b
  bash $0 stop 144 vllm-qwen397b-144-g0-1-2-3-p30001
  bash $0 listall
EOF
    exit 1 ;;
esac
