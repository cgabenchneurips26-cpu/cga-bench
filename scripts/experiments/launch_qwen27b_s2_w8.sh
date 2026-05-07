#!/bin/bash
cd ${CGA_BENCH_ROOT}/cga_bench
export PYTHONPATH=${CGA_BENCH_ROOT}
LOG=/tmp/chain_w8_qwen27b_s2.log
echo "[$(date '+%H:%M:%S')] Starting qwen27b S2 chain (145:30007) — checklist+tooluse" | tee "$LOG"
for scaffold in checklist tooluse; do
    echo "[$(date '+%H:%M:%S')] ==> qwen27b_${scaffold}_s2" | tee -a "$LOG"
    python scripts/experiments/full_690_runner.py "qwen27b_${scaffold}_s2" results/ex_w8_crossmodel >> "$LOG" 2>&1
    echo "[$(date '+%H:%M:%S')] qwen27b_${scaffold}_s2 exit=$?" | tee -a "$LOG"
done
echo "[$(date '+%H:%M:%S')] qwen27b S2 chain complete" | tee -a "$LOG"
