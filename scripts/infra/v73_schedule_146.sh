#!/usr/bin/env bash
# v7.3 Full Schedule for 146 (A100x8) — launch, monitor, boost.
#
# GPU Allocation:
#   Round 1 (6 models, 7 GPUs):
#     GPU 0: qwen4b (TP=1, port 8101)
#     GPU 1: deepseek_r1_7b (TP=1, port 30009)
#     GPU 2: qwen27b BF16 (TP=1, port 28010)
#     GPU 3: qwen35b BF16 (TP=1, port 8013)
#     GPU 4: gemma31b (TP=1, port 30003)
#     GPU 5,6: nemotron30b BF16 (TP=2, port 30004)
#     GPU 7: spare
#
#   Round 2 (boost — auto-triggered):
#     qwen4b done → GPU 0+7 → oss120b (TP=2, port 28000)
#
#   Round 3 (boost — auto-triggered):
#     4+ GPUs freed → llama4scout (TP=4, port 8201)
#
# Usage:
#   nohup bash scripts/infra/v73_schedule_146.sh > /tmp/v73_schedule.log 2>&1 &
#   tail -f /tmp/v73_schedule.log
#
# Requires: Docker images already pulled on 146.
#   docker pull vllm/vllm-openai:latest
#
# IMPORTANT: Most models are NOT cached on 146. First launch downloads
# weights inside the container (mounted to host HF cache). Large models
# (27B-35B BF16) take 30-60 min to download. The script uses a 3600s
# health timeout to accommodate this. Only openai/gpt-oss-120b is cached.
#
# To pre-download models (recommended before first run):
#   bash scripts/infra/v73_schedule_146.sh --prefetch

set -uo pipefail

ROOT=/home/anonymous-org/anonymous-project/AnonProject/cga_bench
OUTPUT="$ROOT/results/v73_full"
TARGET=1254       # 418 scenarios x 3 runs
INTERVAL_S=120    # 2 min poll
STATE_FILE=/tmp/v73_schedule.state
CACHE=/home/hub
LOGDIR="$OUTPUT/_logs"

HEALTH_TIMEOUT=3600  # 60 min — first launch downloads model weights

touch "$STATE_FILE"
mkdir -p "$OUTPUT" "$LOGDIR"

# ─── Core Helpers (must be defined before prefetch) ───────────────────

ts() { date '+%H:%M:%S'; }

health_ok() {
  local port="$1"
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
    -H 'Authorization: Bearer sk-no-key-required' \
    "http://localhost:${port}/v1/models" 2>/dev/null)
  [ "$code" = "200" ]
}

# ─── Prefetch Mode ────────────────────────────────────────────────────
# Downloads all model weights to host HF cache without running the full
# schedule. Run once before the first production launch.

if [ "${1:-}" = "--prefetch" ]; then
  echo "[$(ts)] PREFETCH MODE: downloading model weights to $CACHE"
  echo "  This runs each model briefly to trigger HF download, then stops."
  echo ""
  models_to_fetch=(
    "Qwen/Qwen3-4B-Instruct-2507"
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
    "Qwen/Qwen3.5-27B"
    "Qwen/Qwen3.5-35B-A3B"
    "google/gemma-4-31b-it"
    "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
  )
  for mid in "${models_to_fetch[@]}"; do
    local_name=$(echo "$mid" | tr '/' '_')
    echo "[$(ts)] Fetching $mid ..."
    docker run --rm --runtime=nvidia --init \
      -e "NVIDIA_VISIBLE_DEVICES=0" --ipc host \
      -v "${CACHE}:/root/.cache/huggingface/hub" \
      --name "prefetch-${local_name}" \
      "vllm/vllm-openai:latest" \
      --model "$mid" --port 8000 \
      --max-model-len 512 --max-num-seqs 1 \
      --gpu-memory-utilization 0.5 \
      --api-key sk-no-key-required &
    FETCH_PID=$!
    # Wait until model files appear or container exits
    for attempt in $(seq 1 360); do
      if ! kill -0 "$FETCH_PID" 2>/dev/null; then break; fi
      if health_ok 8000 2>/dev/null; then
        echo "[$(ts)] $mid: downloaded + loaded OK"
        docker rm -f "prefetch-${local_name}" >/dev/null 2>&1
        break
      fi
      sleep 10
    done
    docker rm -f "prefetch-${local_name}" >/dev/null 2>&1
    wait "$FETCH_PID" 2>/dev/null || true
    sleep 3
  done
  echo "[$(ts)] PREFETCH complete"
  exit 0
fi

# ─── Helpers ──────────────────────────────────────────────────────────

already_done() { grep -qx "$1" "$STATE_FILE" 2>/dev/null; }
mark_done()    { echo "$1" >> "$STATE_FILE"; }

count_eps() {
  local model="$1"
  local d="$OUTPUT/$model"
  [ -d "$d" ] || { echo 0; return; }
  find "$d" -maxdepth 1 -name '*.json' \
    ! -name 'checkpoint*' ! -name 'model_summary*' ! -name '.claim_*' \
    2>/dev/null | wc -l
}

wait_healthy() {
  local port="$1" label="$2" max_wait="${3:-300}"
  local elapsed=0
  while [ "$elapsed" -lt "$max_wait" ]; do
    if health_ok "$port"; then
      echo "[$(ts)] $label on port $port: HEALTHY"
      return 0
    fi
    sleep 10
    elapsed=$((elapsed + 10))
  done
  echo "[$(ts)] ERROR: $label on port $port not healthy after ${max_wait}s"
  return 1
}

# ─── Docker Launch (146 local) ────────────────────────────────────────
# All models use v6_endpoint.sh — BF16 variants registered as
# nemotron30b_bf16, qwen35b_bf16, qwen27b_bf16, gemma31b_local, llama4scout.

launch_model() {
  local gpu="$1" port="$2" model_key="$3"
  echo "[$(ts)] Launching $model_key on GPU $gpu port $port (v6_endpoint.sh)"
  bash "$ROOT/scripts/infra/v6_endpoint.sh" launch 146 "$gpu" "$port" "$model_key"
}

# ─── Worker Spawn ─────────────────────────────────────────────────────

spawn_workers() {
  local model_key="$1" n_workers="$2" port_override="${3:-}" shard="${4:-}"
  local extra_args=""
  [ -n "$port_override" ] && extra_args="$extra_args --port $port_override"
  [ -n "$shard" ] && extra_args="$extra_args --shard $shard"

  echo "[$(ts)] Spawning $n_workers workers for $model_key ${shard:+(shard $shard)}"
  for i in $(seq 1 "$n_workers"); do
    local log="$LOGDIR/${model_key}_w${i}_$(date +%s).log"
    nohup env \
      PYTHONPATH="$ROOT/..":"$ROOT" \
      python3 "$ROOT/scripts/experiments/full_v73_runner.py" \
      "$model_key" "$OUTPUT" $extra_args \
      >"$log" 2>&1 &
    disown
  done
  echo "[$(ts)] $n_workers workers spawned for $model_key"
}

# ─── Stop Container ──────────────────────────────────────────────────

stop_model() {
  local model_key="$1"
  local container
  # Pattern matches both plain (qwen4b) and suffixed (qwen27b_bf16, gemma31b_local) keys
  container=$(docker ps --format '{{.Names}}' | grep "^vllm-${model_key}.*-146-" | head -1)
  if [ -n "$container" ]; then
    echo "[$(ts)] Stopping $container"
    docker rm -f "$container" >/dev/null 2>&1
    sleep 3
  fi
}

# ─── Phase 1: Launch Round 1 ─────────────────────────────────────────

launch_round1() {
  if already_done "round1_launched"; then
    echo "[$(ts)] Round 1 already launched, skipping"
    return
  fi

  echo ""
  echo "================================================================"
  echo "[$(ts)] ROUND 1: Launching 6 models on GPUs 0-6"
  echo "================================================================"

  # All launches via v6_endpoint.sh — BF16 variants use _bf16 / _local keys
  launch_model 0 8101 qwen4b
  launch_model 1 30009 deepseek_r1_7b
  launch_model 2 28010 qwen27b_bf16
  launch_model 3 8013  qwen35b_bf16
  launch_model 4 30003 gemma31b_local
  launch_model 5,6 30004 nemotron30b_bf16

  echo "[$(ts)] Waiting for endpoints + spawning workers in parallel..."

  # Each model: wait_healthy → spawn_workers independently (no blocking others)
  wait_and_spawn() {
    local port="$1" label="$2" n_workers="$3"
    if wait_healthy "$port" "$label" "$HEALTH_TIMEOUT"; then
      spawn_workers "$label" "$n_workers" "" "1/2"
    else
      echo "[$(ts)] WARNING: $label failed to start — watchdog will retry"
    fi
  }

  wait_and_spawn 8101  qwen4b          32 &
  wait_and_spawn 30009 deepseek_r1_7b  32 &
  wait_and_spawn 28010 qwen27b         16 &
  wait_and_spawn 8013  qwen35b         16 &
  wait_and_spawn 30003 gemma31b        16 &
  wait_and_spawn 30004 nemotron30b      8 &

  # Wait for all background health+spawn jobs to finish
  wait

  mark_done "round1_launched"
  echo "[$(ts)] Round 1 launch complete"
}

# ─── Phase 2: Boost — oss120b when qwen4b finishes ───────────────────

boost_oss120b() {
  if already_done "boost_oss120b"; then return; fi

  local eps
  eps=$(count_eps qwen4b)
  if [ "$eps" -lt "$TARGET" ]; then return; fi

  echo ""
  echo "================================================================"
  echo "[$(ts)] BOOST: qwen4b complete ($eps eps) → oss120b on GPU 0,7"
  echo "================================================================"

  stop_model qwen4b
  launch_model 0,7 28000 oss120b

  if wait_healthy 28000 oss120b "$HEALTH_TIMEOUT"; then
    spawn_workers oss120b 12 "" "1/2"
    mark_done "boost_oss120b"
    echo "[$(ts)] BOOST oss120b applied"
  else
    echo "[$(ts)] ERROR: oss120b failed to start"
  fi
}

# ─── Phase 3: Boost — llama4scout when 4+ GPUs free ──────────────────

boost_llama4scout() {
  if already_done "boost_llama4scout"; then return; fi

  # Need 4 contiguous-ish GPUs. Track which Round 1 models (excl qwen4b
  # which was already repurposed for oss120b) are done.
  local freed_gpus=()
  local freed_count=0

  for pair in "deepseek_r1_7b:1" "qwen27b:2" "qwen35b:3" "gemma31b:4"; do
    local model="${pair%%:*}" gpu="${pair##*:}"
    local eps
    eps=$(count_eps "$model")
    if [ "$eps" -ge "$TARGET" ]; then
      freed_gpus+=("$gpu")
      freed_count=$((freed_count + 1))
    fi
  done

  # Also check nemotron (2 GPUs)
  local nemo_eps
  nemo_eps=$(count_eps nemotron30b)
  if [ "$nemo_eps" -ge "$TARGET" ]; then
    freed_gpus+=(5 6)
    freed_count=$((freed_count + 2))
  fi

  if [ "$freed_count" -lt 4 ]; then return; fi

  # Pick first 4 freed GPUs
  local gpu_spec="${freed_gpus[0]},${freed_gpus[1]},${freed_gpus[2]},${freed_gpus[3]}"

  echo ""
  echo "================================================================"
  echo "[$(ts)] BOOST: $freed_count GPUs free → llama4scout TP=4 on GPU $gpu_spec"
  echo "================================================================"

  # Stop completed model containers to free GPU memory
  for pair in "deepseek_r1_7b:1" "qwen27b:2" "qwen35b:3" "gemma31b:4"; do
    local model="${pair%%:*}"
    local eps
    eps=$(count_eps "$model")
    if [ "$eps" -ge "$TARGET" ]; then
      stop_model "$model"
    fi
  done
  if [ "$nemo_eps" -ge "$TARGET" ]; then
    stop_model nemotron30b
  fi

  launch_model "$gpu_spec" 8201 llama4scout

  if wait_healthy 8201 llama4scout "$HEALTH_TIMEOUT"; then
    spawn_workers llama4scout 12 "" "1/2"
    mark_done "boost_llama4scout"
    echo "[$(ts)] BOOST llama4scout applied"
  else
    echo "[$(ts)] ERROR: llama4scout failed to start"
  fi
}

# ─── Health Watchdog — restart dead containers + respawn workers ─────

# Map: model_key -> "gpu port docker_key n_workers"
declare -A ROUND1_SPEC=(
  [qwen4b]="0 8101 qwen4b 32"
  [deepseek_r1_7b]="1 30009 deepseek_r1_7b 32"
  [qwen27b]="2 28010 qwen27b_bf16 16"
  [qwen35b]="3 8013 qwen35b_bf16 16"
  [gemma31b]="4 30003 gemma31b_local 16"
  [nemotron30b]="5,6 30004 nemotron30b_bf16 8"
)

watchdog_check() {
  for model_key in "${!ROUND1_SPEC[@]}"; do
    local spec="${ROUND1_SPEC[$model_key]}"
    local gpu port docker_key n_workers
    read -r gpu port docker_key n_workers <<< "$spec"

    local eps
    eps=$(count_eps "$model_key")
    # Skip if already complete
    [ "$eps" -ge "$TARGET" ] && continue

    # Check endpoint health
    if ! health_ok "$port"; then
      # Container dead — check if any container with this key exists
      local existing
      existing=$(docker ps --format '{{.Names}}' | grep "^vllm-${docker_key}.*-146-" | head -1)
      if [ -z "$existing" ]; then
        echo "[$(ts)] WATCHDOG: $model_key (port $port) dead — relaunching"
        launch_model "$gpu" "$port" "$docker_key"
        # Wait for it (shorter timeout, no 60min download needed since /home/hub)
        if wait_healthy "$port" "$model_key" 600; then
          echo "[$(ts)] WATCHDOG: $model_key recovered — respawning workers"
          spawn_workers "$model_key" "$n_workers" "" "1/2"
        else
          echo "[$(ts)] WATCHDOG: $model_key failed to recover after 600s"
        fi
      fi
      continue
    fi

    # Endpoint healthy — check if workers are alive
    local w_count
    w_count=$(ps aux 2>/dev/null | grep "full_v73_runner.py $model_key " | grep -v grep | wc -l)
    if [ "$w_count" -eq 0 ]; then
      echo "[$(ts)] WATCHDOG: $model_key endpoint healthy but 0 workers — respawning"
      spawn_workers "$model_key" "$n_workers" "" "1/2"
    fi
  done

  # Also check boost models (oss120b, llama4scout) if active
  for pair in "oss120b:28000:12" "llama4scout:8201:12"; do
    local bmodel="${pair%%:*}"
    local rest="${pair#*:}"
    local bport="${rest%%:*}"
    local bworkers="${rest#*:}"

    already_done "boost_${bmodel}" || continue  # Only if boost was triggered
    local beps
    beps=$(count_eps "$bmodel")
    [ "$beps" -ge "$TARGET" ] && continue

    if health_ok "$bport"; then
      local bw_count
      bw_count=$(ps aux 2>/dev/null | grep "full_v73_runner.py $bmodel " | grep -v grep | wc -l)
      if [ "$bw_count" -eq 0 ]; then
        echo "[$(ts)] WATCHDOG: $bmodel (boost) endpoint healthy but 0 workers — respawning"
        spawn_workers "$bmodel" "$bworkers" "" "1/2"
      fi
    fi
  done
}

# ─── Status Display ──────────────────────────────────────────────────

show_status() {
  echo ""
  echo "--- v7.3 Status [$(ts)] ---"
  local total_done=0
  local all_models="qwen4b deepseek_r1_7b qwen27b qwen35b gemma31b nemotron30b oss120b llama4scout"
  for m in $all_models; do
    local eps
    eps=$(count_eps "$m")
    local pct=$((eps * 100 / TARGET))
    local status="running"
    [ "$eps" -ge "$TARGET" ] && { status="DONE"; total_done=$((total_done + 1)); }
    [ "$eps" -eq 0 ] && status="pending"
    printf "  %-16s %4d / %d (%3d%%) [%s]\n" "$m" "$eps" "$TARGET" "$pct" "$status"
  done
  echo "  Total models done: $total_done / 8"
  echo "---"
}

# ─── Main Loop ────────────────────────────────────────────────────────

echo ""
echo "================================================================"
echo "[$(ts)] v7.3 Schedule Daemon started"
echo "  Output: $OUTPUT"
echo "  Target: $TARGET episodes per model (418 x 3)"
echo "  Poll interval: ${INTERVAL_S}s"
echo "  State: $STATE_FILE"
echo "================================================================"

launch_round1

while true; do
  watchdog_check
  boost_oss120b
  boost_llama4scout

  show_status

  # Check if all 8 models are done
  all_done=0
  for m in qwen4b deepseek_r1_7b qwen27b qwen35b gemma31b nemotron30b oss120b llama4scout; do
    eps=$(count_eps "$m")
    [ "$eps" -ge "$TARGET" ] && all_done=$((all_done + 1))
  done

  if [ "$all_done" -ge 8 ]; then
    echo ""
    echo "================================================================"
    echo "[$(ts)] ALL 8 MODELS COMPLETE — schedule daemon exiting"
    echo "================================================================"
    show_status
    exit 0
  fi

  sleep "$INTERVAL_S"
done
