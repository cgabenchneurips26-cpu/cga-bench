#!/bin/bash
# Two instances: 30001 does react+checklist, 30002 does direct+tooluse
cd ${CGA_BENCH_ROOT}/cga_bench
export PYTHONPATH=${CGA_BENCH_ROOT}

# Chain F: 144:30001 (react + checklist)
chain_F() {
    LOG=/tmp/chain_w8_qwen397b_F.log
    echo "[$(date '+%H:%M:%S')] Starting qwen397b chain F (144:30001)" | tee "$LOG"
    for scaffold in react checklist; do
        echo "[$(date '+%H:%M:%S')] ==> qwen397b_${scaffold}" | tee -a "$LOG"
        python scripts/experiments/full_690_runner.py "qwen397b_${scaffold}" results/ex_w8_crossmodel >> "$LOG" 2>&1
        echo "[$(date '+%H:%M:%S')] qwen397b_${scaffold} exit=$?" | tee -a "$LOG"
    done
    echo "[$(date '+%H:%M:%S')] qwen397b chain F complete" | tee -a "$LOG"
}

# Chain G: 144:30002 (direct + tooluse)
chain_G() {
    LOG=/tmp/chain_w8_qwen397b_G.log
    echo "[$(date '+%H:%M:%S')] Starting qwen397b chain G (144:30002)" | tee "$LOG"
    for scaffold in direct tooluse; do
        echo "[$(date '+%H:%M:%S')] ==> qwen397b_${scaffold}_s2" | tee -a "$LOG"
        python scripts/experiments/full_690_runner.py "qwen397b_${scaffold}_s2" results/ex_w8_crossmodel >> "$LOG" 2>&1
        echo "[$(date '+%H:%M:%S')] qwen397b_${scaffold}_s2 exit=$?" | tee -a "$LOG"
    done
    echo "[$(date '+%H:%M:%S')] qwen397b chain G complete" | tee -a "$LOG"
}

chain_F &
chain_G &
wait
echo "[$(date '+%H:%M:%S')] Both qwen397b chains complete"
