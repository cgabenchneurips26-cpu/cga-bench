#!/usr/bin/env bash
# v6 ops dashboard — endpoint health + workers + GPU + eps in one shot.
#
# Usage:
#   bash scripts/infra/v6_status.sh           # full status
#   bash scripts/infra/v6_status.sh endpoints # endpoint health only
#   bash scripts/infra/v6_status.sh workers   # worker counts only
#   bash scripts/infra/v6_status.sh gpu       # GPU util only
#   bash scripts/infra/v6_status.sh eps       # episode counts + fb sanity
#   bash scripts/infra/v6_status.sh fb        # fb% per model (full sanity)
set -uo pipefail

MODE="${1:-all}"

PHASE_A_DIR=/home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6a_706
PHASE_B_DIR=/home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b
MODELS=(qwen397b oss120b nemotron30b gemma31b qwen35b qwen27b qwen4b deepseek_r1_7b)

# 144 endpoints (any of qwen397b 30001/30002, nemotron 30013-30016)
ENDPOINTS_144=(30001 30002 30013 30014 30015 30016)
# 145 endpoints (gemma 30100-30107 OR oss120b 30005, qwen 30006-30010, etc.)
ENDPOINTS_145=(30005 30006 30007 30008 30010 30011 30012 30100 30101 30102 30103 30104 30105 30106 30107)
# 146 endpoints (qwen4b pilot 28010 etc.)
ENDPOINTS_146=(28010 28011)

# ─── helpers ───────────────────────────────────────────────────

probe_endpoint() {
  # $1 host  $2 port → prints "$id" or "DOWN"
  curl -s --max-time 2 -H "Authorization: Bearer sk-no-key-required" \
    "http://${1}:${2}/v1/models" 2>/dev/null \
    | python3 -c "import json,sys
try: d=json.load(sys.stdin); print(d['data'][0]['id'])
except: print('DOWN')"
}

check_endpoints() {
  echo "=== Endpoint health ==="
  for p in "${ENDPOINTS_144[@]}"; do
    m=$(probe_endpoint 127.0.0.1 "$p")
    [ "$m" = "DOWN" ] || echo "  144:$p → $m"
  done
  for p in "${ENDPOINTS_145[@]}"; do
    m=$(probe_endpoint 127.0.0.1 "$p")
    [ "$m" = "DOWN" ] || echo "  145:$p → $m"
  done
  for p in "${ENDPOINTS_146[@]}"; do
    m=$(probe_endpoint localhost "$p")
    [ "$m" = "DOWN" ] || echo "  146:$p → $m"
  done
}

check_workers() {
  echo "=== Workers (full_690_runner.py) ==="
  printf "  146: "
  ps aux | grep "full_690_runner.py" | grep -v grep | wc -l
  printf "  145: "
  sudo -n -u anonymous-org ssh 127.0.0.1 'ps aux | grep "full_690_runner.py" | grep -v grep | wc -l' 2>/dev/null
  echo "  by-model on 146:"
  ps aux | grep "full_690_runner.py" | grep -v grep \
    | awk '{for(i=1;i<=NF;i++)if($i~/runner.py$/){print $(i+1);break}}' \
    | sort | uniq -c | awk '{printf "    %s: %s\n", $2, $1}'
  echo "  by-model on 145:"
  sudo -n -u anonymous-org ssh 127.0.0.1 'ps aux | grep "full_690_runner.py" | grep -v grep' 2>/dev/null \
    | awk '{for(i=1;i<=NF;i++)if($i~/runner.py$/){print $(i+1);break}}' \
    | sort | uniq -c | awk '{printf "    %s: %s\n", $2, $1}'
}

check_gpu() {
  echo "=== GPU util (144 H200) ==="
  sudo -n -u anonymous-org ssh [email-redacted] \
    'nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader' 2>/dev/null \
    | awk -F, '{printf "  GPU %s: util=%s mem=%s\n", $1, $2, $3}'
  echo "=== GPU util (145 A100) ==="
  sudo -n -u anonymous-org ssh 127.0.0.1 \
    'nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader' 2>/dev/null \
    | awk -F, '{printf "  GPU %s: util=%s mem=%s\n", $1, $2, $3}'
  echo "=== GPU util (146) ==="
  nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader 2>/dev/null \
    | awk -F, '{printf "  GPU %s: util=%s mem=%s\n", $1, $2, $3}'
}

count_eps() {
  local model_dir="$1"
  find "$model_dir" -maxdepth 1 -name '*.json' \
    -not -name 'checkpoint*' -not -name 'model_summary*' 2>/dev/null | wc -l
}

check_eps() {
  echo "=== Episode counts ==="
  echo "Phase A (target 2118 each):"
  for m in "${MODELS[@]}"; do
    n=$(count_eps "${PHASE_A_DIR}/${m}")
    printf "  %-18s %5d / 2118\n" "$m" "$n"
  done
  echo "Phase B (target 9558 each, 56 CPGs × 3 runs after 28-CPG archive):"
  for m in "${MODELS[@]}"; do
    n=$(count_eps "${PHASE_B_DIR}/${m}")
    printf "  %-18s %5d / 9558\n" "$m" "$n"
  done
}

check_fb() {
  echo "=== fb% sanity per model (Phase B) ==="
  python3 - "${PHASE_B_DIR}" "${MODELS[@]}" <<'PY'
import os, json, glob, sys
DB = sys.argv[1]
models = sys.argv[2:]
print(f"  {'model':18s} {'n':>5} {'fb%':>5} {'empty':>5} {'comp':>6}")
for m in models:
    files = [f for f in glob.glob(f"{DB}/{m}/*.json")
             if 'checkpoint' not in os.path.basename(f) and 'summary' not in os.path.basename(f)]
    fb = empty = 0; comp = 0.0
    for f in files:
        try: d = json.load(open(f))
        except: continue
        a = d.get('actions') or []
        if not a: empty += 1
        if any('Initial diagnostic workup' in (x.get('justification') or '') for x in a):
            fb += 1
        comp += d.get('compliance_score', 0) or 0
    n = len(files)
    if n == 0:
        print(f"  {m:18s} {n:>5} (no episodes)")
        continue
    print(f"  {m:18s} {n:>5} {100*fb/n:>4.1f}% {empty:>5} {comp/n:>5.3f}")
PY
}

# ─── dispatch ──────────────────────────────────────────────────

case "$MODE" in
  endpoints) check_endpoints ;;
  workers)   check_workers ;;
  gpu)       check_gpu ;;
  eps)       check_eps ;;
  fb)        check_fb ;;
  all)       check_endpoints; echo; check_workers; echo; check_gpu; echo; check_eps; echo; check_fb ;;
  *) echo "Usage: $0 [all|endpoints|workers|gpu|eps|fb]"; exit 1 ;;
esac
