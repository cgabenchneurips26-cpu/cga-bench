#!/bin/bash
# W8 Cross-Model Expansion: 4 new models × 4 scaffolds = 16 cells
# qwen397b: 144:30001 + 144:30002 (2 instances, split scaffolds)
# qwen27b: 145:30003
# nemotron30b: 145:30005
# qwen4b: 145:30006

cd ${CGA_BENCH_ROOT}/cga_bench
export PYTHONPATH=${CGA_BENCH_ROOT}

LOG=/tmp/chain_w8_expansion.log
RESULTS_DIR=results/ex_w8_crossmodel

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

run_cell() {
    local model_key=$1
    local label=$2
    log "==> Launching W8 cell: $label (model_key=$model_key)"
    if python scripts/experiments/full_690_runner.py \
            "$model_key" \
            "$RESULTS_DIR" \
            >> "$LOG" 2>&1; then
        log "SUCCESS: $label"
    else
        log "FAILED (exit=$?): $label"
        return 1
    fi
}

# Chain F: qwen397b via 144:30001 (react + checklist)
chain_F() {
    run_cell "qwen397b_react" "qwen397b_react [144:30001]" || return 1
    run_cell "qwen397b_checklist" "qwen397b_checklist [144:30001]"
}

# Chain G: qwen397b via 144:30002 (direct + tooluse)
chain_G() {
    run_cell "qwen397b_direct_s2" "qwen397b_direct [144:30002]" || return 1
    run_cell "qwen397b_tooluse_s2" "qwen397b_tooluse [144:30002]"
}

# Chain H: qwen27b via 145:30003 (all 4 sequential)
chain_H() {
    run_cell "qwen27b_react" "qwen27b_react [145:30003]" || return 1
    run_cell "qwen27b_direct" "qwen27b_direct [145:30003]" || return 1
    run_cell "qwen27b_checklist" "qwen27b_checklist [145:30003]" || return 1
    run_cell "qwen27b_tooluse" "qwen27b_tooluse [145:30003]"
}

# Chain I: nemotron30b via 145:30005 (all 4 sequential)
chain_I() {
    run_cell "nemotron30b_react" "nemotron30b_react [145:30005]" || return 1
    run_cell "nemotron30b_direct" "nemotron30b_direct [145:30005]" || return 1
    run_cell "nemotron30b_checklist" "nemotron30b_checklist [145:30005]" || return 1
    run_cell "nemotron30b_tooluse" "nemotron30b_tooluse [145:30005]"
}

# Chain J: qwen4b via 145:30006 (all 4 sequential)
chain_J() {
    run_cell "qwen4b_react" "qwen4b_react [145:30006]" || return 1
    run_cell "qwen4b_direct" "qwen4b_direct [145:30006]" || return 1
    run_cell "qwen4b_checklist" "qwen4b_checklist [145:30006]" || return 1
    run_cell "qwen4b_tooluse" "qwen4b_tooluse [145:30006]"
}

mkdir -p "$RESULTS_DIR"
log "=== W8 Expansion Chain Launcher ==="
log "16 cells: qwen397b/qwen27b/nemotron30b/qwen4b × react/direct/checklist/tooluse"

chain_F &
chain_G &
chain_H &
chain_I &
chain_J &

log "All chains launched. Monitor: tail -f $LOG"
wait
log "=== All W8 expansion chains complete ==="
