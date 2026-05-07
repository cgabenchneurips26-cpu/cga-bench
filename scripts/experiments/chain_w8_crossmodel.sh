#!/bin/bash
# W8 Cross-Model Replication chain launcher (v2 — fixed model keys & prereqs)
# 3 models × 3 scaffolds = 9 cells, each targeting 706 scenarios × 3 runs
# Chains A/B/C: qwen35b react/direct/checklist (parallel, ports 8017/8018/8019)
# Chain D: oss120b react→direct→checklist (sequential, port 30008)
# Chain E: gemma31b react→direct→checklist (sequential, port 145:30003)
# Usage: nohup bash scripts/experiments/chain_w8_crossmodel.sh >> /tmp/chain_w8_crossmodel.log 2>&1 &
cd ${CGA_BENCH_ROOT}/cga_bench
export PYTHONPATH=${CGA_BENCH_ROOT}

LOG=/tmp/chain_w8_crossmodel.log
RESULTS_DIR=results/ex_w8_crossmodel
MAX_WAIT=43200  # 12 hours max wait per stage

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# ---------------------------------------------------------------------------
# check_episodes: count results in a JSON file (handles both dict and list)
# ---------------------------------------------------------------------------
check_episodes() {
    local file=$1
    if [ ! -f "$file" ]; then
        echo 0
        return
    fi
    python3 -c "
import json
d = json.load(open('$file'))
if isinstance(d, list):
    print(len(d))
elif isinstance(d, dict):
    print(len(d.get('results', [])))
else:
    print(0)
" 2>/dev/null || echo 0
}

# ---------------------------------------------------------------------------
# count_episode_files: count episode .json files in a model output dir
# (excludes checkpoint*.json and model_summary.json)
# ---------------------------------------------------------------------------
count_episode_files() {
    local model_dir=$1
    if [ ! -d "$model_dir" ]; then
        echo 0
        return
    fi
    python3 -c "
import pathlib, sys
d = pathlib.Path('$model_dir')
n = len([f for f in d.glob('*.json')
         if not f.name.startswith(('checkpoint', 'model_summary', '.claim'))])
print(n)
" 2>/dev/null || echo 0
}

# ---------------------------------------------------------------------------
# wait_for_completion: poll file until it reaches target episode count
# ---------------------------------------------------------------------------
wait_for_completion() {
    local file=$1
    local target=$2
    local label=$3
    local waited=0
    log "Waiting for $label ($file) to reach $target episodes..."
    while true; do
        n=$(check_episodes "$file")
        if [ "$n" -ge "$target" ]; then
            log "$label DONE: $n/$target episodes"
            return 0
        fi
        if [ "$waited" -ge "$MAX_WAIT" ]; then
            log "TIMEOUT: $label still at $n/$target after ${MAX_WAIT}s"
            return 1
        fi
        sleep 60
        waited=$((waited + 60))
    done
}

# ---------------------------------------------------------------------------
# wait_for_model_dir: poll model output dir until it has target episode files
# Used to gate sequential runs within D/E chains
# ---------------------------------------------------------------------------
wait_for_model_dir() {
    local model_dir=$1
    local target=$2
    local label=$3
    local waited=0
    log "Waiting for $label ($model_dir) to reach $target episode files..."
    while true; do
        n=$(count_episode_files "$model_dir")
        if [ "$n" -ge "$target" ]; then
            log "$label DONE: $n/$target episode files"
            return 0
        fi
        if [ "$waited" -ge "$MAX_WAIT" ]; then
            log "TIMEOUT: $label still at $n/$target after ${MAX_WAIT}s"
            return 1
        fi
        sleep 60
        waited=$((waited + 60))
    done
}

# ---------------------------------------------------------------------------
# run_cell: launch a single full_690_runner cell and log outcome
# ---------------------------------------------------------------------------
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

# ============================================================
# CHAIN A: 144:8017 (qwen35b TP=1) → qwen35b_react
# Prereq: defense_c3 agentclinic_qwen35b (uses 8017)
# ============================================================
chain_A() {
    wait_for_completion \
        "results/defense_c3/agentclinic_qwen35b.json" \
        200 \
        "C3 AC qwen35b (8017)" || return 1

    run_cell "qwen35b_react" "qwen35b_react [Chain A, 144:8017]"
}

# ============================================================
# CHAIN B: 144:8018 (qwen35b TP=1) → qwen35b_direct
# Prereq: temp sweep done (already satisfied)
# ============================================================
chain_B() {
    wait_for_completion \
        "results/defense_temp/agentclinic_qwen35b_t0_3.json" \
        100 \
        "Temp sweep T=0.3 qwen35b (8018)" || return 1

    run_cell "qwen35b_direct" "qwen35b_direct [Chain B, 144:8018]"
}

# ============================================================
# CHAIN C: 144:8019 (qwen35b TP=1) → qwen35b_checklist
# Prereq: C3 qwen35b_tp1 (currently 40/200)
# ============================================================
chain_C() {
    wait_for_completion \
        "results/defense_c3/agentclinic_qwen35b_tp1.json" \
        200 \
        "C3 AC qwen35b TP=1 replica (8019)" || return 1

    run_cell "qwen35b_checklist" "qwen35b_checklist [Chain C, 144:8019]"
}

# ============================================================
# CHAIN D: 144:30008 (oss120b TP=2)
# Prereq: C3 agentclinic_oss120b (currently 70/200)
# → oss120b_react → oss120b_direct → oss120b_checklist (sequential)
# ============================================================
chain_D() {
    wait_for_completion \
        "results/defense_c3/agentclinic_oss120b.json" \
        200 \
        "C3 AgentClinic oss120b (30008)" || return 1

    # --- Step 1: oss120b react ---
    run_cell "oss120b_react" "oss120b_react [Chain D step 1, 144:30008]" || return 1

    wait_for_model_dir \
        "$RESULTS_DIR/oss120b_react" \
        500 \
        "oss120b_react output" || return 1

    # --- Step 2: oss120b_direct ---
    run_cell "oss120b_direct" "oss120b_direct [Chain D step 2, 144:30008]" || return 1

    wait_for_model_dir \
        "$RESULTS_DIR/oss120b_direct" \
        500 \
        "oss120b_direct output" || return 1

    # --- Step 3: oss120b_checklist ---
    run_cell "oss120b_checklist" "oss120b_checklist [Chain D step 3, 144:30008]"
}

# ============================================================
# CHAIN E: 145:30003 (gemma-4-31b TP=2)
# Prereq: NONE — HealthBench already done, 145 is idle
# → gemma31b_react → gemma31b_direct → gemma31b_checklist (sequential)
# ============================================================
chain_E() {
    log "Chain E: gemma31b — server 145 idle, starting immediately"

    # --- Step 1: gemma31b react ---
    run_cell "gemma31b_react" "gemma31b_react [Chain E step 1, 145:30003]" || return 1

    wait_for_model_dir \
        "$RESULTS_DIR/gemma31b_react" \
        500 \
        "gemma31b_react output" || return 1

    # --- Step 2: gemma31b_direct ---
    run_cell "gemma31b_direct" "gemma31b_direct [Chain E step 2, 145:30003]" || return 1

    wait_for_model_dir \
        "$RESULTS_DIR/gemma31b_direct" \
        500 \
        "gemma31b_direct output" || return 1

    # --- Step 3: gemma31b_checklist ---
    run_cell "gemma31b_checklist" "gemma31b_checklist [Chain E step 3, 145:30003]"
}

# ============================================================
# Launch all chains
# ============================================================
mkdir -p "$RESULTS_DIR"

log "=== W8 Cross-Model Replication Chain Launcher v2 ==="
log "9 cells: qwen35b/oss120b/gemma31b × react/direct/checklist"
log "Results dir: $RESULTS_DIR"
log "Log: $LOG"
log "Chain A: qwen35b_react (waits for c3 qwen35b)"
log "Chain B: qwen35b_direct (prereqs met, starts immediately)"
log "Chain C: qwen35b_checklist (waits for c3 qwen35b_tp1)"
log "Chain D: oss120b sequential (waits for c3 oss120b)"
log "Chain E: gemma31b sequential (starts immediately)"

chain_A &
chain_B &
chain_C &
chain_D &
chain_E &

log "All chains launched. Monitor: tail -f $LOG"
wait
log "=== All W8 chains complete ==="
