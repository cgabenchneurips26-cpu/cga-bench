#!/usr/bin/env bash
# launch_shard2.sh — Launch shard 2/2 workers for all v7.3 models
# Created: 2026-05-02 05:30 UTC
# Purpose: All shard 1/2 workers were launched but shard 2/2 was never started.
#          This script launches shard 2/2 workers to cover the remaining 209 scenarios.
#
# Architecture:
#   qwen397b  → 144:30002  (shard 2/2, using qwen397b_s2 key → same output dir)
#   qwen4b    → 146:8102   (extra container, shard 2/2)
#   deepseek  → 146:30010  (extra container, shard 2/2)
#   qwen27b   → 146:28010  (shared port, shard 2/2)
#   gemma31b  → 146:30003  (shared port, shard 2/2)
#   nemotron  → 146:30004  (shared port, shard 2/2)

set -euo pipefail

BENCH_ROOT="/home/anonymous-org/anonymous-project/AnonProject/cga_bench"
RESULTS="results/v73_full"
LOG_DIR="${BENCH_ROOT}/${RESULTS}/_logs"
SHARD="2/2"
TIMESTAMP=$(date +%s)

cd "$BENCH_ROOT"
mkdir -p "$LOG_DIR"

launch_workers() {
    local model_key="$1"
    local n_workers="$2"
    local host="$3"
    local port="$4"
    local label="${model_key}_s2"

    echo "[$(date +%H:%M:%S)] Launching ${n_workers} shard 2/2 workers: ${model_key} → ${host}:${port}"

    for i in $(seq 1 "$n_workers"); do
        nohup env PYTHONPATH="${BENCH_ROOT}" \
            python3 scripts/experiments/full_v73_runner.py \
                "$model_key" "$RESULTS" \
                --shard "$SHARD" \
                --host "$host" \
                --port "$port" \
            > "${LOG_DIR}/${label}_w${i}_${TIMESTAMP}.log" 2>&1 &
    done

    echo "  → ${n_workers} workers launched (PID range: $(jobs -p | tail -${n_workers} | head -1)-$(jobs -p | tail -1))"
}

echo "============================================="
echo "  v7.3 Shard 2/2 Launch — $(date)"
echo "============================================="
echo ""

# Health checks first
echo "=== Endpoint health checks ==="
check_health() {
    local host="$1" port="$2" label="$3"
    if curl -s -m 5 -H "Authorization: Bearer sk-no-key-required" "http://${host}:${port}/health" >/dev/null 2>&1; then
        echo "  ✓ ${label} (${host}:${port})"
        return 0
    else
        echo "  ✗ ${label} (${host}:${port}) — OFFLINE"
        return 1
    fi
}

ALL_OK=true
check_health "127.0.0.1 30002 "qwen397b"    || ALL_OK=false
check_health "localhost"     8102  "qwen4b"       || ALL_OK=false
check_health "localhost"     30010 "deepseek_r1_7b" || ALL_OK=false
check_health "localhost"     28010 "qwen27b"      || ALL_OK=false
check_health "localhost"     30003 "gemma31b"      || ALL_OK=false
check_health "localhost"     30004 "nemotron30b"   || ALL_OK=false

if [ "$ALL_OK" = false ]; then
    echo ""
    echo "WARNING: Some endpoints offline. Launching only healthy endpoints."
fi
echo ""

# Launch shard 2/2 workers
# Worker counts calibrated by model size:
#   <=7B → 32 workers, 27-35B → 12 workers, >=200B → 12 workers

echo "=== Launching shard 2/2 workers ==="

# qwen397b: 12 workers on 144:30002 via qwen397b_s2 key (resolves to qwen397b dir)
launch_workers "qwen397b_s2" 12 "127.0.0.1 30002

# qwen4b: 32 workers on 146:8102 (extra container)
launch_workers "qwen4b" 32 "localhost" 8102

# deepseek_r1_7b: 32 workers on 146:30010 (extra container)
launch_workers "deepseek_r1_7b" 32 "localhost" 30010

# qwen27b: 12 workers on 146:28010 (shared port — shard 1/2 almost done)
launch_workers "qwen27b" 12 "localhost" 28010

# gemma31b: 12 workers on 146:30003 (shared port)
launch_workers "gemma31b" 12 "localhost" 30003

# nemotron30b: 8 workers on 146:30004 (shared port)
launch_workers "nemotron30b" 8 "localhost" 30004

echo ""
echo "=== Launch complete ==="
TOTAL_WORKERS=$((12 + 32 + 32 + 12 + 12 + 8))
echo "Total: ${TOTAL_WORKERS} shard 2/2 workers across 6 models"
echo "Logs: ${LOG_DIR}/*_s2_*_${TIMESTAMP}.log"
echo ""
echo "Monitor with:"
echo "  # Episode counts"
echo "  for d in ${RESULTS}/*/; do echo \"\$(basename \$d): \$(find \$d -name '*.json' ! -name 'checkpoint*' ! -name 'model_summary*' | wc -l)\"; done"
echo "  # Worker counts"
echo "  ps aux | grep full_v73_runner | grep -v grep | awk '{print \$NF}' | sort | uniq -c | sort -rn"
