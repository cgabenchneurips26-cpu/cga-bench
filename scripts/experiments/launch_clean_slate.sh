#!/bin/bash
# Clean Slate Launch Script
set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTDIR="${CGA_BENCH_ROOT}/cga_bench/results/clean_slate_${TIMESTAMP}"
mkdir -p "$OUTDIR"
echo "$OUTDIR" > /tmp/clean_slate_outdir.txt

export PYTHONPATH=${CGA_BENCH_ROOT}
PYTHON=/home/anonymous-org/anaconda3/bin/python3.13
cd ${CGA_BENCH_ROOT}/cga_bench

echo "=== Clean Slate Launch ==="
echo "OUTDIR: $OUTDIR"
echo "TIME: $(date)"

# Launch 4 models
nohup $PYTHON scripts/experiments/clean_slate_runner.py oss120b > "${OUTDIR}/log_oss120b.txt" 2>&1 &
echo "oss120b: PID $!"

nohup $PYTHON scripts/experiments/clean_slate_runner.py qwen35b > "${OUTDIR}/log_qwen35b.txt" 2>&1 &
echo "qwen35b: PID $!"

nohup $PYTHON scripts/experiments/clean_slate_runner.py qwen27b > "${OUTDIR}/log_qwen27b.txt" 2>&1 &
echo "qwen27b: PID $!"

nohup $PYTHON scripts/experiments/clean_slate_runner.py qwen4b > "${OUTDIR}/log_qwen4b.txt" 2>&1 &
echo "qwen4b: PID $!"

echo "All 4 models launched at $(date)"
echo "Monitor: tail -f ${OUTDIR}/log_*.txt"
