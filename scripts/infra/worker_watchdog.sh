#!/usr/bin/env bash
# Worker Watchdog — polls per-model worker counts and refills natural dropouts.
#
# Why: full_690_runner workers exit cleanly when their assigned shard runs out
# of unclaimed scenarios. Throughput drops as workers retire. This watchdog
# detects when worker count falls below target and spawns no-shard refill
# workers (which scan remaining missing combos). It stops refilling once
# the model's episode count meets the target.
#
# Config file: scripts/infra/worker_watchdog.conf
#   Format (one line per model):
#     model_key host:where_to_run endpoint_host:endpoint_port output_dir target_workers target_eps
#   Lines starting with # ignored.
#   host_where_to_run: 146 (local) or 145 (ssh) or 144 (ssh anonymous-user)
#
# Usage:
#   nohup bash scripts/infra/worker_watchdog.sh > /tmp/worker_wd.log 2>&1 &
#   tail -f /tmp/worker_wd.log
#   # stop:
#   pkill -f worker_watchdog.sh
set -uo pipefail

CONF="${1:-/home/anonymous-org/anonymous-project/AnonProject/cga_bench/scripts/infra/worker_watchdog.conf}"
INTERVAL_S=120  # check every 2 minutes
REFILL_BATCH=4  # spawn this many refill workers per gap-fill iteration

count_eps() {
  local where="$1" output="$2" model="$3"
  case "$where" in
    146) find "${output}/${model}" -maxdepth 1 -name '*.json' \
           -not -name 'checkpoint*' -not -name 'model_summary*' 2>/dev/null | wc -l ;;
    145) sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 127.0.0.1 \
           "find ${output}/${model} -maxdepth 1 -name '*.json' -not -name 'checkpoint*' -not -name 'model_summary*' 2>/dev/null | wc -l" 2>/dev/null ;;
    144) sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 [email-redacted] \
           "find ${output}/${model} -maxdepth 1 -name '*.json' -not -name 'checkpoint*' -not -name 'model_summary*' 2>/dev/null | wc -l" 2>/dev/null ;;
  esac
}

count_workers() {
  local where="$1" model="$2"
  case "$where" in
    146) ps aux | grep "full_690_runner.py ${model} " | grep -v grep | wc -l ;;
    145) sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 127.0.0.1 \
           "ps aux | grep 'full_690_runner.py ${model} ' | grep -v grep | wc -l" 2>/dev/null ;;
    144) sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 [email-redacted] \
           "ps aux | grep 'full_690_runner.py ${model} ' | grep -v grep | wc -l" 2>/dev/null ;;
  esac
}

refill_146() {
  local model="$1" output="$2" host="$3" port="$4" n="$5"
  cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench
  export CGA_BENCH_EXCLUDE_AUTO=1 CGA_BENCH_INCLUDE_AUTO_V2=1
  export PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject
  for i in $(seq 1 "$n"); do
    local log="${output}/_logs/${model}_wd_$(date +%s)_${i}.log"
    nohup python scripts/experiments/full_690_runner.py "$model" "$output" \
      --host "$host" --port "$port" >"$log" 2>&1 &
    disown
  done
}

refill_145() {
  local model="$1" output="$2" port="$3" n="$4"
  sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 127.0.0.1 "
    export PYTHONPATH=/home/anonymous-org
    export CGA_BENCH_EXCLUDE_AUTO=1
    export CGA_BENCH_INCLUDE_AUTO_V2=1
    cd /home/anonymous-org/cga_bench
    mkdir -p /home/anonymous-org/v6b_logs
    for i in \$(seq 1 ${n}); do
      log=/home/anonymous-org/v6b_logs/${model}_wd_\$(date +%s)_\${i}.log
      nohup /home/anonymous-org/anaconda3/bin/python3 scripts/experiments/full_690_runner.py \
        ${model} ${output} --host localhost --port ${port} >\$log 2>&1 &
      disown
    done
  " 2>/dev/null
}

refill_144() {
  local model="$1" output="$2" port="$3" n="$4"
  sudo -n -u anonymous-org ssh -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 [email-redacted] "
    export PYTHONPATH=/home/anonymous-user
    export CGA_BENCH_EXCLUDE_AUTO=1
    export CGA_BENCH_INCLUDE_AUTO_V2=1
    cd /home/anonymous-user/cga_bench
    mkdir -p /home/anonymous-user/v6b_logs
    for i in \$(seq 1 ${n}); do
      log=/home/anonymous-user/v6b_logs/${model}_wd_\$(date +%s)_\${i}.log
      nohup python3 scripts/experiments/full_690_runner.py \
        ${model} ${output} --host localhost --port ${port} >\$log 2>&1 &
      disown
    done
  " 2>/dev/null
}

# ─── main loop ──────────────────────────────────────────────

if [ ! -f "$CONF" ]; then
  echo "ERROR: config not found: $CONF"
  echo "Create one: see header for format."
  exit 1
fi

echo "[$(date '+%T')] watchdog started, conf=$CONF, interval=${INTERVAL_S}s"

while true; do
  while IFS=' ' read -r model where endpoint output target_workers target_eps; do
    # Skip blank lines and comments
    [[ -z "$model" || "$model" =~ ^# ]] && continue

    eps=$(count_eps "$where" "$output" "$model")
    workers=$(count_workers "$where" "$model")
    eps=${eps:-0}
    workers=${workers:-0}

    if [ "$eps" -ge "$target_eps" ]; then
      [ "$workers" -gt 0 ] && echo "[$(date '+%T')] $model: COMPLETE (eps=$eps/${target_eps}); workers will exit naturally"
      continue
    fi

    if [ "$workers" -lt "$target_workers" ]; then
      gap=$(( target_workers - workers ))
      gap=$(( gap < REFILL_BATCH ? gap : REFILL_BATCH ))
      ehost=${endpoint%%:*}
      eport=${endpoint##*:}
      echo "[$(date '+%T')] $model: eps=$eps/${target_eps} workers=$workers/${target_workers} → refill ${gap} on ${where}:${ehost}:${eport}"
      case "$where" in
        146) refill_146 "$model" "$output" "$ehost" "$eport" "$gap" ;;
        145) refill_145 "$model" "$output" "$eport" "$gap" ;;
        144) refill_144 "$model" "$output" "$eport" "$gap" ;;
      esac
    fi
  done < "$CONF"

  sleep "$INTERVAL_S"
done
