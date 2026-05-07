#!/usr/bin/env bash
# v6 worker management — start, stop, restart per model.
#
# Usage:
#   bash scripts/infra/v6_workers.sh start   <model_key> <output_dir> <host> <port> <n_workers>
#   bash scripts/infra/v6_workers.sh start145 <model_key> <port>     <n_workers>     # localhost on 145
#   bash scripts/infra/v6_workers.sh stop    <model_key>
#   bash scripts/infra/v6_workers.sh stop145 <model_key>
#   bash scripts/infra/v6_workers.sh stopall
#   bash scripts/infra/v6_workers.sh stopall145
set -uo pipefail

CMD="${1:-help}"

# ─── start workers from 146 ──────────────────────────────────

start_146() {
  local model_key="$1" output="$2" host="$3" port="$4" n="$5"
  cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench
  export CGA_BENCH_EXCLUDE_AUTO=1
  export CGA_BENCH_INCLUDE_AUTO_V2=1
  export PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject
  mkdir -p "${output}/_logs"
  for i in $(seq 1 "$n"); do
    local log="${output}/_logs/${model_key}_p${port}_${i}_${n}.log"
    nohup python scripts/experiments/full_690_runner.py \
      "$model_key" "$output" \
      --host "$host" --port "$port" --shard "${i}/${n}" \
      >"$log" 2>&1 &
    disown
  done
  sleep 2
  echo "  146 ${model_key}: $(ps aux | grep "full_690_runner.py ${model_key} " | grep -v grep | wc -l) workers"
}

# ─── start workers on 145 (co-located) ───────────────────────

start_145() {
  local model_key="$1" port="$2" n="$3"
  sudo -n -u anonymous-org ssh 127.0.0.1 "
    export PYTHONPATH=/home/anonymous-org
    export CGA_BENCH_EXCLUDE_AUTO=1
    export CGA_BENCH_INCLUDE_AUTO_V2=1
    cd /home/anonymous-org/cga_bench
    mkdir -p /home/anonymous-org/v6b_logs
    for i in \$(seq 1 ${n}); do
      log=/home/anonymous-org/v6b_logs/${model_key}_p${port}_\${i}_${n}.log
      nohup /home/anonymous-org/anaconda3/bin/python3 scripts/experiments/full_690_runner.py \
        ${model_key} /home/anonymous-org/results/full_v6b \
        --host localhost --port ${port} --shard \${i}/${n} \
        >\$log 2>&1 &
      disown
    done
    sleep 2
    echo \"  145 ${model_key}: \$(ps aux | grep \"full_690_runner.py ${model_key} \" | grep -v grep | wc -l) workers\"
  " 2>&1 | tail -3
}

# ─── stop ────────────────────────────────────────────────────

stop_146() { pkill -f "full_690_runner.py $1 " 2>/dev/null; sleep 2; }
stop_145() { sudo -n -u anonymous-org ssh 127.0.0.1 "pkill -f 'full_690_runner.py $1 '" 2>/dev/null; sleep 3; }
stop_all_146() { pkill -f 'full_690_runner.py' 2>/dev/null; sleep 2; }
stop_all_145() { sudo -n -u anonymous-org ssh 127.0.0.1 "pkill -f 'full_690_runner.py'" 2>/dev/null; sleep 3; }

# ─── dispatch ────────────────────────────────────────────────

case "$CMD" in
  start)      start_146 "$2" "$3" "$4" "$5" "$6" ;;
  start145)   start_145 "$2" "$3" "$4" ;;
  stop)       stop_146 "$2"; echo "stopped $2" ;;
  stop145)    stop_145 "$2"; echo "stopped 145 $2" ;;
  stopall)    stop_all_146; stop_all_145; echo "stopped all" ;;
  stopall146) stop_all_146; echo "stopped all 146" ;;
  stopall145) stop_all_145; echo "stopped all 145" ;;
  *)
    cat <<EOF
v6 worker management

Commands:
  start    <model_key> <output> <host> <port> <n>   spawn n workers from 146
  start145 <model_key> <port> <n>                   spawn n workers ON 145
  stop     <model_key>                              kill workers for model on 146
  stop145  <model_key>                              kill workers for model on 145
  stopall                                           kill all workers everywhere
  stopall146                                        kill all workers on 146
  stopall145                                        kill all workers on 145

Example:
  bash $0 start qwen397b results/full_v6b 127.0.0.1 30001 8
  bash $0 start145 gemma31b 30100 16
  bash $0 stopall
EOF
    exit 1 ;;
esac
