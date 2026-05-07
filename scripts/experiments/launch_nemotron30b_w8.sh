#!/bin/bash
cd ${CGA_BENCH_ROOT}/cga_bench
export PYTHONPATH=${CGA_BENCH_ROOT}
LOG=/tmp/chain_w8_nemotron30b.log
echo "[$(date '+%H:%M:%S')] Starting nemotron30b W8 chain (145:30005)" | tee "$LOG"
for scaffold in react direct checklist tooluse; do
    echo "[$(date '+%H:%M:%S')] ==> nemotron30b_${scaffold}" | tee -a "$LOG"
    python scripts/experiments/full_690_runner.py "nemotron30b_${scaffold}" results/ex_w8_crossmodel >> "$LOG" 2>&1
    echo "[$(date '+%H:%M:%S')] nemotron30b_${scaffold} exit=$?" | tee -a "$LOG"
done
echo "[$(date '+%H:%M:%S')] nemotron30b chain complete" | tee -a "$LOG"
