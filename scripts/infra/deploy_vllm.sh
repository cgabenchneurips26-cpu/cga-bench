#!/bin/bash
# =============================================================================
# deploy_vllm.sh — One-stop vLLM endpoint + worker deployment script
#
# Eliminates manual trial-and-error for model IDs, GPU allocation, Docker vs
# bare-metal, and worker spawning across the 144/145/146 cluster.
#
# Usage:
#   bash scripts/infra/deploy_vllm.sh launch <host> <gpus> <port> <model_key>
#   bash scripts/infra/deploy_vllm.sh workers <model_key> <host> <port> <n_workers>
#   bash scripts/infra/deploy_vllm.sh status [host]
#   bash scripts/infra/deploy_vllm.sh stop <host> <port>
#   bash scripts/infra/deploy_vllm.sh health <host> <port>
#   bash scripts/infra/deploy_vllm.sh models
#
# Examples:
#   # Launch oss120b on 144 GPUs 4,5 port 30003 (auto-selects bare-metal)
#   bash scripts/infra/deploy_vllm.sh launch 144 4,5 30003 oss120b
#
#   # Spawn 12 workers from 145 connecting to 144:30003
#   bash scripts/infra/deploy_vllm.sh workers oss120b 127.0.0.1 30003 12
#
#   # Check all endpoints on 144
#   bash scripts/infra/deploy_vllm.sh status 144
#
#   # List all known models
#   bash scripts/infra/deploy_vllm.sh models
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# MODEL REGISTRY — Single source of truth for model IDs, TP, and options
# ---------------------------------------------------------------------------
# Format: model_key|vllm_model_id|tp_size|max_model_len|extra_flags|label
declare -A MODEL_REGISTRY
MODEL_REGISTRY=(
  [oss120b]="openai/gpt-oss-120b|2|8192||oss-120b"
  [qwen397b]="Qwen/Qwen3.5-397B-A17B-FP8|4|16384|--tool-call-parser hermes --enable-auto-tool-choice|qwen397b"
  [qwen35b]="Qwen/Qwen3.5-35B-A3B-FP8|1|8192||qwen35b"
  [qwen27b]="Qwen/Qwen3.5-27B-FP8|1|8192||qwen27b"
  [qwen4b]="Qwen/Qwen3-4B-Instruct-2507|1|8192||qwen4b"
  [gemma31b]="google/gemma-4-31b-it|1|8192|--limit-mm-per-prompt image=0 --trust-remote-code|gemma31b"
  [nemotron30b]="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8|1|8192|--max-num-seqs 8|nemotron30b"
  [deepseek_r1_7b]="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B|1|8192||deepseek-r1-7b"
  [llama4scout]="meta-llama/Llama-4-Scout-17B-16E-Instruct|4|8192|--trust-remote-code|llama4scout"
)

# ---------------------------------------------------------------------------
# HOST REGISTRY — Machine-specific paths and capabilities
# ---------------------------------------------------------------------------
declare -A HOST_IP
HOST_IP=([144]="127.0.0.1 [145]="127.0.0.1 [146]="127.0.0.1

declare -A HOST_SSH
HOST_SSH=([144]="[email-redacted]" [145]="127.0.0.1 [146]="localhost")

declare -A HOST_VLLM_BIN
HOST_VLLM_BIN=([144]="/home/anonymous-user/.local/bin/vllm" [145]="/home/anonymous-org/anaconda3/bin/vllm" [146]="/home/anonymous-org/anaconda3/bin/vllm")

declare -A HOST_GPU_TYPE
HOST_GPU_TYPE=([144]="H200" [145]="A100" [146]="A100")

declare -A HOST_HF_CACHE
HOST_HF_CACHE=([144]="/home/anonymous-user/.cache/huggingface" [145]="/home/anonymous-org/.cache/huggingface" [146]="/home/hub")

declare -A HOST_LOGDIR
HOST_LOGDIR=([144]="/home/anonymous-user/vllm_logs" [145]="/tmp" [146]="/tmp")

declare -A HOST_CODEPATH
HOST_CODEPATH=([144]="" [145]="/home/anonymous-org/bench_ws/cga_bench" [146]="/home/anonymous-org/anonymous-project/AnonProject/cga_bench")

API_KEY="sk-no-key-required"

# ---------------------------------------------------------------------------
# Helper: parse model registry entry
# ---------------------------------------------------------------------------
parse_model() {
  local key="$1"
  if [[ -z "${MODEL_REGISTRY[$key]+x}" ]]; then
    echo "ERROR: Unknown model key '$key'. Use 'models' command to list." >&2
    return 1
  fi
  IFS='|' read -r VLLM_MODEL_ID TP_SIZE MAX_MODEL_LEN EXTRA_FLAGS MODEL_LABEL <<< "${MODEL_REGISTRY[$key]}"
}

resolve_host() {
  local host="$1"
  # Accept both "144" and "127.0.0.1
  case "$host" in
    144|145|146) echo "$host" ;;
    127.0.0.1 echo "144" ;;
    127.0.0.1 echo "145" ;;
    127.0.0.1 echo "146" ;;
    *) echo "ERROR: Unknown host '$host'" >&2; return 1 ;;
  esac
}

ssh_cmd() {
  local host_num="$1"; shift
  local ssh_target="${HOST_SSH[$host_num]}"
  if [[ "$host_num" == "146" ]]; then
    eval "$@"
  else
    ssh "$ssh_target" "$@"
  fi
}

# ---------------------------------------------------------------------------
# Command: models — List all known models
# ---------------------------------------------------------------------------
cmd_models() {
  echo "=== Model Registry ==="
  printf "%-15s %-45s %s %s %s\n" "KEY" "MODEL_ID" "TP" "MAX_LEN" "EXTRA"
  echo "----------------------------------------------------------------------"
  for key in $(echo "${!MODEL_REGISTRY[@]}" | tr ' ' '\n' | sort); do
    parse_model "$key"
    printf "%-15s %-45s %s  %s     %s\n" "$key" "$VLLM_MODEL_ID" "$TP_SIZE" "$MAX_MODEL_LEN" "$EXTRA_FLAGS"
  done
}

# ---------------------------------------------------------------------------
# Command: launch — Start vLLM endpoint (bare-metal)
# ---------------------------------------------------------------------------
cmd_launch() {
  local host_arg="$1" gpus="$2" port="$3" model_key="$4"
  local enforce_eager="${5:-}"  # optional: pass "eager" to add --enforce-eager
  local host_num
  host_num=$(resolve_host "$host_arg")
  parse_model "$model_key"

  local vllm_bin="${HOST_VLLM_BIN[$host_num]}"
  local logdir="${HOST_LOGDIR[$host_num]}"
  local logfile="${logdir}/vllm_${model_key}_gpu${gpus//,/_}_p${port}.log"

  local eager_flag=""
  if [[ "$enforce_eager" == "eager" ]]; then
    eager_flag="--enforce-eager"
  fi

  echo "=== Launching $model_key on host $host_num ==="
  echo "  Model:  $VLLM_MODEL_ID"
  echo "  GPUs:   $gpus (TP=$TP_SIZE)"
  echo "  Port:   $port"
  echo "  Log:    $logfile"
  echo "  Method: bare-metal ($vllm_bin)"
  [[ -n "$eager_flag" ]] && echo "  Mode:   enforce-eager (no CUDA graphs)"

  local cmd="mkdir -p $logdir && CUDA_VISIBLE_DEVICES=$gpus nohup $vllm_bin serve $VLLM_MODEL_ID \
    --port $port \
    --tensor-parallel-size $TP_SIZE \
    --max-model-len $MAX_MODEL_LEN \
    --gpu-memory-utilization 0.92 \
    --enable-prefix-caching \
    --enable-chunked-prefill \
    --max-num-seqs 256 \
    --api-key $API_KEY \
    $eager_flag \
    $EXTRA_FLAGS \
    > $logfile 2>&1 & echo PID=\$!"

  ssh_cmd "$host_num" "$cmd"
  echo "  -> Launched. Monitor with: ssh ${HOST_SSH[$host_num]} 'tail -f $logfile'"
}

# ---------------------------------------------------------------------------
# Command: launch-docker — Start vLLM via Docker (for 144 when bare-metal fails)
# ---------------------------------------------------------------------------
cmd_launch_docker() {
  local host_arg="$1" gpus="$2" port="$3" model_key="$4"
  local enforce_eager="${5:-}"
  local host_num
  host_num=$(resolve_host "$host_arg")
  parse_model "$model_key"

  local hf_cache="${HOST_HF_CACHE[$host_num]}"
  local container_name="vllm-${model_key}-gpu${gpus//,/-}-p${port}"

  local eager_flag=""
  if [[ "$enforce_eager" == "eager" ]]; then
    eager_flag="--enforce-eager"
  fi

  # Build GPU device string for --gpus flag
  local gpu_device_str="\"device=${gpus}\""

  echo "=== Launching $model_key via Docker on host $host_num ==="
  echo "  Model:     $VLLM_MODEL_ID"
  echo "  GPUs:      $gpus (TP=$TP_SIZE)"
  echo "  Port:      $port"
  echo "  Container: $container_name"
  echo "  HF Cache:  $hf_cache"

  local cmd="docker run -d --name $container_name \
    --gpus '${gpu_device_str}' \
    -v ${hf_cache}:/root/.cache/huggingface \
    -p ${port}:8000 \
    vllm/vllm-openai:nightly \
    --model $VLLM_MODEL_ID \
    --tensor-parallel-size $TP_SIZE \
    --max-model-len $MAX_MODEL_LEN \
    --gpu-memory-utilization 0.92 \
    --enable-prefix-caching \
    --enable-chunked-prefill \
    --max-num-seqs 256 \
    --api-key $API_KEY \
    $eager_flag \
    $EXTRA_FLAGS"

  ssh_cmd "$host_num" "$cmd"
  echo "  -> Container started. Monitor with: ssh ${HOST_SSH[$host_num]} 'docker logs -f $container_name'"
}

# ---------------------------------------------------------------------------
# Command: workers — Spawn benchmark workers on 145
# ---------------------------------------------------------------------------
cmd_workers() {
  local model_key="$1" host="$2" port="$3" n_workers="$4"
  local results_dir="${5:-results/v73_full}"
  local worker_host="145"
  local codepath="${HOST_CODEPATH[$worker_host]}"

  echo "=== Spawning $n_workers workers for $model_key -> $host:$port ==="

  local logfile="/tmp/v73_${model_key}_${host##*.}_${port}.log"
  local cmd="cd $codepath && PYTHONPATH=. && for i in \$(seq 1 $n_workers); do \
    nohup python3 scripts/experiments/full_v73_runner.py $model_key $results_dir \
      --host $host --port $port \
      >> $logfile 2>&1 & \
  done && echo 'Spawned $n_workers workers -> $host:$port, log: $logfile'"

  ssh_cmd "$worker_host" "$cmd"
}

# ---------------------------------------------------------------------------
# Command: health — Check if endpoint is serving
# ---------------------------------------------------------------------------
cmd_health() {
  local host_arg="$1" port="$2"
  local host_num
  host_num=$(resolve_host "$host_arg")
  local ip="${HOST_IP[$host_num]}"

  echo "=== Health check: $ip:$port ==="
  local result
  result=$(curl -s -m 5 -H "Authorization: Bearer $API_KEY" \
    "http://${ip}:${port}/v1/models" 2>/dev/null || echo "UNREACHABLE")

  if echo "$result" | grep -q '"id"'; then
    local model_id
    model_id=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['id'])" 2>/dev/null || echo "?")
    echo "  Status: SERVING"
    echo "  Model:  $model_id"
  else
    echo "  Status: DOWN or LOADING"
    echo "  Response: $result"
  fi
}

# ---------------------------------------------------------------------------
# Command: status — Show GPU usage and endpoints on a host
# ---------------------------------------------------------------------------
cmd_status() {
  local host_arg="${1:-all}"

  if [[ "$host_arg" == "all" ]]; then
    for h in 144 145 146; do
      cmd_status "$h"
      echo ""
    done
    return
  fi

  local host_num
  host_num=$(resolve_host "$host_arg")
  local ip="${HOST_IP[$host_num]}"

  echo "=== Host $host_num ($ip) — ${HOST_GPU_TYPE[$host_num]} ==="

  # GPU status
  echo "--- GPU Memory ---"
  ssh_cmd "$host_num" "nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null" || echo "  (unreachable)"

  # vLLM processes
  echo "--- vLLM Processes ---"
  ssh_cmd "$host_num" "ps aux | grep 'vllm serve' | grep -v grep | awk '{print \"  PID=\"\$2, \"GPU=\", \"CMD=\"\$11,\$12,\$13,\$14,\$15}' 2>/dev/null" || echo "  (none)"

  # Docker containers
  echo "--- Docker Containers ---"
  ssh_cmd "$host_num" "docker ps --format '  {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null | grep -i vllm || echo '  (none)'" || echo "  (unreachable)"

  # Workers (145 only)
  if [[ "$host_num" == "145" ]]; then
    echo "--- Benchmark Workers ---"
    ssh_cmd "$host_num" "ps aux | grep full_v73_runner | grep -v grep | awk '{print \$NF}' | sort | uniq -c | sort -rn | head -10 2>/dev/null" || echo "  (none)"
    echo "  Total: $(ssh_cmd "$host_num" "ps aux | grep full_v73_runner | grep -v grep | wc -l 2>/dev/null")"
  fi
}

# ---------------------------------------------------------------------------
# Command: stop — Stop vLLM on a port (bare-metal: kill; Docker: stop+rm)
# ---------------------------------------------------------------------------
cmd_stop() {
  local host_arg="$1" port="$2"
  local host_num
  host_num=$(resolve_host "$host_arg")

  echo "=== Stopping vLLM on $host_num:$port ==="

  # Try Docker first
  local container
  container=$(ssh_cmd "$host_num" "docker ps --format '{{.Names}}' 2>/dev/null | grep 'p${port}'" || true)
  if [[ -n "$container" ]]; then
    echo "  Stopping Docker container: $container"
    ssh_cmd "$host_num" "docker stop $container && docker rm $container"
    echo "  -> Done"
    return
  fi

  # Bare-metal: find and kill by port
  local pids
  pids=$(ssh_cmd "$host_num" "ps aux | grep 'vllm serve' | grep -- '--port $port' | grep -v grep | awk '{print \$2}'" || true)
  if [[ -n "$pids" ]]; then
    echo "  Killing PIDs: $pids"
    ssh_cmd "$host_num" "kill $pids 2>/dev/null; sleep 2; kill -9 $pids 2>/dev/null" || true
    # Also kill orphan EngineCore processes
    local orphans
    orphans=$(ssh_cmd "$host_num" "ps aux | grep 'VLLM::EngineCore' | grep -v grep | awk '{print \$2}'" || true)
    if [[ -n "$orphans" ]]; then
      echo "  Killing orphan EngineCore PIDs: $orphans"
      ssh_cmd "$host_num" "kill -9 $orphans 2>/dev/null" || true
    fi
    echo "  -> Done"
  else
    echo "  No vLLM process found on port $port"
  fi
}

# ---------------------------------------------------------------------------
# Command: kill-workers — Kill workers for a specific model
# ---------------------------------------------------------------------------
cmd_kill_workers() {
  local model_key="$1"
  local worker_host="145"

  echo "=== Killing $model_key workers on 145 ==="
  local count
  count=$(ssh_cmd "$worker_host" "ps aux | grep full_v73_runner | grep '$model_key' | grep -v grep | wc -l")
  echo "  Found $count workers"

  if [[ "$count" -gt 0 ]]; then
    ssh_cmd "$worker_host" "ps aux | grep full_v73_runner | grep '$model_key' | grep -v grep | awk '{print \$2}' | xargs kill 2>/dev/null" || true
    echo "  -> Killed"
  fi
}

# ---------------------------------------------------------------------------
# Command: progress — Show episode counts for all models
# ---------------------------------------------------------------------------
cmd_progress() {
  local results_dir="${1:-results/v73_full}"
  local worker_host="145"
  local codepath="${HOST_CODEPATH[$worker_host]}"

  echo "=== V7.3 Benchmark Progress ==="
  ssh_cmd "$worker_host" "cd $codepath && for m in gemma31b qwen4b qwen27b qwen397b deepseek_r1_7b nemotron30b oss120b qwen35b llama4scout; do count=\$(ls $results_dir/\$m/*.json 2>/dev/null | wc -l); printf '  %-18s %s/1254\n' \"\$m\" \"\$count\"; done"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
case "${1:-help}" in
  launch)        cmd_launch "${2:?host}" "${3:?gpus}" "${4:?port}" "${5:?model_key}" "${6:-}" ;;
  launch-docker) cmd_launch_docker "${2:?host}" "${3:?gpus}" "${4:?port}" "${5:?model_key}" "${6:-}" ;;
  workers)       cmd_workers "${2:?model_key}" "${3:?host}" "${4:?port}" "${5:?n_workers}" "${6:-}" ;;
  health)        cmd_health "${2:?host}" "${3:?port}" ;;
  status)        cmd_status "${2:-all}" ;;
  stop)          cmd_stop "${2:?host}" "${3:?port}" ;;
  kill-workers)  cmd_kill_workers "${2:?model_key}" ;;
  progress)      cmd_progress "${2:-}" ;;
  models)        cmd_models ;;
  help|*)
    cat <<'USAGE'
deploy_vllm.sh — vLLM endpoint + worker deployment automation

Commands:
  launch <host> <gpus> <port> <model> [eager]   Launch bare-metal vLLM
  launch-docker <host> <gpus> <port> <model> [eager]  Launch Docker vLLM
  workers <model> <host> <port> <n>              Spawn benchmark workers on 145
  health <host> <port>                           Check endpoint health
  status [host|all]                              Show GPUs, processes, workers
  stop <host> <port>                             Stop vLLM (Docker or bare-metal)
  kill-workers <model>                           Kill workers for a model on 145
  progress [results_dir]                         Show episode counts
  models                                         List all known models

Hosts: 144 (H200x8), 145 (A100x8), 146 (A100x8)
       Also accepts IPs: 127.0.0.1 etc.

Examples:
  # Full oss120b deployment on 144 (all 8 GPUs)
  bash scripts/infra/deploy_vllm.sh launch 144 0,1 30001 oss120b
  bash scripts/infra/deploy_vllm.sh launch 144 2,3 30002 oss120b
  bash scripts/infra/deploy_vllm.sh launch 144 4,5 30003 oss120b
  bash scripts/infra/deploy_vllm.sh launch 144 6,7 30004 oss120b
  bash scripts/infra/deploy_vllm.sh workers oss120b 127.0.0.1 30001 12
  bash scripts/infra/deploy_vllm.sh workers oss120b 127.0.0.1 30002 12
  bash scripts/infra/deploy_vllm.sh workers oss120b 127.0.0.1 30003 12
  bash scripts/infra/deploy_vllm.sh workers oss120b 127.0.0.1 30004 12

  # Check everything
  bash scripts/infra/deploy_vllm.sh status all
  bash scripts/infra/deploy_vllm.sh progress

Notes:
  - 144: ALWAYS get user permission before stopping anything
  - nemotron30b requires compute 8.9+ (H200 only, NOT A100)
  - oss120b: TP=2 minimum (120B params)
  - qwen397b: TP=4, use gpu-mem-util=0.90 on H200
  - Docker on 144: use --enforce-eager if CUDA graph capture hangs
  - Workers run on 145 (/home/anonymous-org/bench_ws/cga_bench/)
USAGE
    ;;
esac
