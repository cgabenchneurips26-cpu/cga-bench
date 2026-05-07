#!/usr/bin/env bash
# Phase B boost daemon — when a 145 model hits target, redeploy its GPU as a
# helper instance for the slowest-pending model. Doubles throughput on the
# bottleneck without leaving any GPU idle.
#
# Boost map (145 only — 144 is qwen397b/nemotron, separate fleet):
# Updated 2026-04-26: deepseek_r1_7b is the dominant bottleneck (~25h vs others
# ~10-15h) due to R1 reasoning chain length. First freed GPU goes to deepseek
# helper. Subsequent freed GPUs go to other slow models.
#   qwen4b done  -> GPU 0 -> 2nd deepseek_r1_7b (port 30106)  [was: qwen27b]
#   deepseek_r1_7b done -> GPU 4 -> 2nd qwen27b (port 30108)  [was: qwen35b]
#   qwen35b done -> GPU 2 -> 2nd qwen27b (port 30207)
#   qwen27b done -> GPU 1 -> 2nd oss120b shard? skip (oss120b TP=2 needs 2 GPUs)
#                  Instead: spawn extra qwen35b helper if still running.
#
# Each helper endpoint adds N workers to the watchdog conf semantically
# (here we just spawn workers directly via ssh). Idempotent: skips
# already-promoted helpers.
#
# Usage:
#   nohup bash scripts/infra/phase_b_boost.sh > /tmp/phase_b_boost.log 2>&1 &
#   tail -f /tmp/phase_b_boost.log

set -uo pipefail

ROOT=/home/anonymous-org/anonymous-project/AnonProject/cga_bench
OUTPUT_145=/home/anonymous-org/results/full_v6b
TARGET=9558
INTERVAL_S=180  # 3 min poll

# state file: which boosts already applied (one per line: SOURCE_MODEL)
STATE_FILE=/tmp/phase_b_boost.state
touch "$STATE_FILE"

ssh145() {
  sudo -n -u anonymous-org ssh -o ConnectTimeout=5 -o ServerAliveInterval=15 127.0.0.1 "$@"
}

count_eps_145() {
  ssh145 "find $OUTPUT_145/$1 -maxdepth 1 -name '*.json' 2>/dev/null | wc -l" 2>/dev/null
}

already_boosted() {
  grep -qx "$1" "$STATE_FILE"
}

mark_boosted() {
  echo "$1" >> "$STATE_FILE"
}

# Args: source_model (now done, GPU freed), helper_model, helper_gpu, helper_port, helper_workers
boost() {
  local src="$1" helper="$2" gpu="$3" port="$4" workers="$5"
  if already_boosted "$src"; then
    return
  fi
  local eps
  eps=$(count_eps_145 "$src")
  eps=${eps:-0}
  if [ "$eps" -lt "$TARGET" ]; then
    echo "[$(date '+%T')] $src: $eps/$TARGET — not done yet, skip boost"
    return
  fi

  echo "[$(date '+%T')] === BOOST: $src complete ($eps eps) → redeploy GPU $gpu as 2nd $helper:$port ==="

  # Stop source endpoint to free GPU
  local src_container
  src_container=$(ssh145 "docker ps --format '{{.Names}}' | grep '^vllm-${src}-145' | head -1" 2>/dev/null)
  if [ -n "$src_container" ]; then
    echo "[$(date '+%T')]   stopping $src_container"
    ssh145 "docker rm -f $src_container" >/dev/null 2>&1
    sleep 3
  fi

  # Launch helper endpoint
  echo "[$(date '+%T')]   launching $helper on GPU $gpu port $port"
  bash "$ROOT/scripts/infra/v6_endpoint.sh" launch 145 "$gpu" "$port" "$helper" >/dev/null 2>&1

  # Wait for helper to come up (60-180 s typical)
  local code attempt
  for attempt in $(seq 1 60); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
      -H 'Authorization: Bearer sk-no-key-required' \
      "http://localhost:8013${port}/v1/models" 2>/dev/null)
    if [ "$code" = "200" ]; then break; fi
    sleep 5
  done
  if [ "$code" != "200" ]; then
    echo "[$(date '+%T')]   ERROR: helper $helper:$port not 200 after 5min — abort boost"
    return
  fi
  echo "[$(date '+%T')]   helper $helper:$port HTTP 200"

  # Spawn helper workers
  echo "[$(date '+%T')]   spawning $workers helper workers on 145"
  ssh145 "
    export PYTHONPATH=/home/anonymous-org
    export CGA_BENCH_EXCLUDE_AUTO=1 CGA_BENCH_INCLUDE_AUTO_V2=1
    cd /home/anonymous-org/cga_bench
    mkdir -p /home/anonymous-org/v6b_logs
    for i in \$(seq 1 ${workers}); do
      log=/home/anonymous-org/v6b_logs/${helper}_boost_\$(date +%s)_\${i}.log
      nohup /home/anonymous-org/anaconda3/bin/python3 scripts/experiments/full_690_runner.py \
        ${helper} $OUTPUT_145 --host localhost --port ${port} >\$log 2>&1 &
      disown
    done
  " >/dev/null 2>&1

  mark_boosted "$src"
  echo "[$(date '+%T')] === BOOST $src→$helper applied ==="
}

# ─── 144 boost: nemotron done → 2nd qwen397b on freed GPU 4-7 ──────────
ssh144() {
  sudo -n -u anonymous-org ssh -o ConnectTimeout=5 -o ServerAliveInterval=15 [email-redacted] "$@"
}

OUTPUT_146=/home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b
OUTPUT_144=/home/anonymous-user/cga_bench/results/full_v6b

count_eps_146() {
  # After 15:40 UTC migration, nemotron + qwen397b workers run on 144 and write
  # to 144 path. 146 path holds historical episodes from before migration.
  # Return the max so boost trigger doesn't fire prematurely on stale 146 count.
  local e146 e144
  e146=$(find "${OUTPUT_146}/${1}" -maxdepth 1 -name '*.json' 2>/dev/null | wc -l)
  e144=$(ssh144 "find ${OUTPUT_144}/${1} -maxdepth 1 -name '*.json' 2>/dev/null | wc -l" 2>/dev/null)
  e144=${e144:-0}
  echo $(( e146 > e144 ? e146 : e144 ))
}

# Boost on 144: when both nemotron endpoints (30003+30004) finish nemotron's
# 10146 target, stop them and launch a 2nd qwen397b TP=4 instance on GPU 4-7.
# This roughly doubles qwen397b throughput (was the 144 critical path).
boost_144_nemo_to_qwen397b() {
  if already_boosted "nemotron30b_to_qwen397b"; then return; fi
  local eps
  eps=$(count_eps_146 nemotron30b)
  eps=${eps:-0}
  if [ "$eps" -lt "$TARGET" ]; then
    echo "[$(date '+%T')] nemotron30b: $eps/$TARGET — not done yet, skip 144 boost"
    return
  fi

  echo "[$(date '+%T')] === BOOST 144: nemotron complete ($eps eps) → free GPU 4-7 → 2nd qwen397b TP=4 port 30002 ==="

  # Stop both nemotron containers
  for c in vllm-nemotron30b-144-g4-5-p30003 vllm-nemotron30b-144-g6-7-p30004; do
    ssh144 "docker rm -f $c" >/dev/null 2>&1
  done
  sleep 5

  # Launch 2nd qwen397b on GPU 4,5,6,7 TP=4 port 30002
  bash "$ROOT/scripts/infra/v6_endpoint.sh" launch 144 4,5,6,7 30002 qwen397b >/dev/null 2>&1

  # Wait for endpoint up (qwen397b TP=4 takes ~3-8 min to load)
  local code
  for attempt in $(seq 1 60); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
      -H 'Authorization: Bearer sk-no-key-required' \
      "http://localhost:8013/v1/models" 2>/dev/null)
    if [ "$code" = "200" ]; then break; fi
    sleep 10
  done
  if [ "$code" != "200" ]; then
    echo "[$(date '+%T')]   ERROR: 2nd qwen397b 30002 not 200 after 10min — abort"
    return
  fi
  echo "[$(date '+%T')]   2nd qwen397b 30002 HTTP 200"

  # Spawn 24 helper workers from 146 calling 144:30002
  cd "$ROOT"
  export CGA_BENCH_EXCLUDE_AUTO=1 CGA_BENCH_INCLUDE_AUTO_V2=1
  export PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject
  mkdir -p "$OUTPUT_146/_logs"
  for i in $(seq 1 24); do
    local log="$OUTPUT_146/_logs/qwen397b_boost_$(date +%s)_${i}.log"
    nohup python scripts/experiments/full_690_runner.py qwen397b "$OUTPUT_146" \
      --host 127.0.0.1 --port 30002 >"$log" 2>&1 &
    disown
  done

  mark_boosted "nemotron30b_to_qwen397b"
  echo "[$(date '+%T')] === BOOST 144 nemotron→2nd qwen397b applied (24 helper workers) ==="
}

echo "[$(date '+%T')] phase_b_boost started, interval=${INTERVAL_S}s, state=$STATE_FILE"

while true; do
  # 145 boosts (small models complete first)
  boost gemma31b        qwen27b        3 30307 16
  boost qwen4b          deepseek_r1_7b 0 30106 32
  boost deepseek_r1_7b  qwen27b        4 30108 16
  boost qwen35b         qwen27b        2 30207 16
  boost qwen27b         qwen35b        1 30208 16

  # 144 boost (nemotron done first → 2nd qwen397b)
  boost_144_nemo_to_qwen397b

  # When everything 145 + 144 done, exit
  total_done_145=0
  for m in qwen4b qwen27b qwen35b oss120b deepseek_r1_7b; do
    eps=$(count_eps_145 "$m")
    eps=${eps:-0}
    [ "$eps" -ge "$TARGET" ] && total_done_145=$((total_done_145 + 1))
  done
  qwen397b_eps=$(count_eps_146 qwen397b)
  qwen397b_eps=${qwen397b_eps:-0}
  if [ "$total_done_145" -ge 5 ] && [ "$qwen397b_eps" -ge "$TARGET" ]; then
    echo "[$(date '+%T')] all Phase B models done — boost daemon exiting"
    exit 0
  fi

  sleep "$INTERVAL_S"
done
