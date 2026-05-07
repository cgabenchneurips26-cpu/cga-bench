#!/bin/bash
# Chain launcher v2: Supplements v1 by covering 6 idle endpoints
# Fixes from critical review: logging, error handling, --resume, PYTHONPATH, timeouts
# Usage: nohup bash scripts/experiments/chain_defense_w9_v2.sh >> /tmp/chain_defense_w9_v2.log 2>&1 &
cd ${CGA_BENCH_ROOT}/cga_bench
export PYTHONPATH=${CGA_BENCH_ROOT}/cga_bench

LOG=/tmp/chain_defense_w9_v2.log
MAX_WAIT=43200  # 12 hours max wait

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

check_episodes() {
    local file=$1
    if [ ! -f "$file" ]; then
        echo 0
        return
    fi
    python3 -c "import json; d=json.load(open('$file')); print(len(d.get('results',[])))" 2>/dev/null || echo 0
}

wait_for_completion() {
    local file=$1
    local target=$2
    local label=$3
    local waited=0
    log "Waiting for $label ($file) to reach $target episodes..."
    while true; do
        n=$(check_episodes "$file" "$target")
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

check_endpoint() {
    local url=$1
    curl -s --max-time 5 "${url}/health" >/dev/null 2>&1 || \
    curl -s --max-time 5 "${url}/v1/models" >/dev/null 2>&1
}

run_or_log() {
    local label=$1
    shift
    log "Launching: $label"
    if "$@" >> "$LOG" 2>&1; then
        log "SUCCESS: $label"
    else
        log "FAILED (exit=$?): $label"
    fi
}

# ============================================================
# CHAIN 5: 145:30005 (gemma TP=2) — idle after T=0.0 gemma
# → HealthBench gemma shard 2 (samples 201-400)
# ============================================================
chain_30005() {
    wait_for_completion "results/defense_temp/agentclinic_gemma31b_t0_0.json" 100 "Temp T=0.0 gemma" || return 1

    if ! check_endpoint "http://localhost:8013"; then
        log "WARN: 145:30005 not responding, trying 145:30003 model name on 30005"
    fi

    log "Launching HealthBench gemma31b shard2 on 145:30005..."
    run_or_log "HealthBench gemma shard2" \
        env OPENAI_API_KEY="sk-no-key-required" \
        python scripts/e2e_healthbench.py \
        --endpoint http://localhost:8013/v1 \
        --model "google/gemma-4-31b-it" \
        --limit 200 --save-every 20 \
        --output reports/healthbench_e2e/healthbench_gemma31b_shard2_200.json
}

# ============================================================
# CHAIN 6: 144:8018 (qwen35b TP=1) — idle after T=0.3 qwen
# → HealthBench qwen shard 2
# ============================================================
chain_8018() {
    wait_for_completion "results/defense_temp/agentclinic_qwen35b_t0_3.json" 100 "Temp T=0.3 qwen" || return 1

    log "Launching HealthBench qwen35b shard2 on 144:8018..."
    run_or_log "HealthBench qwen shard2" \
        env OPENAI_API_KEY="not_needed" \
        python scripts/e2e_healthbench.py \
        --endpoint http://localhost:8013/v1 \
        --model "Qwen/Qwen3.5-35B-A3B-FP8" \
        --limit 200 --save-every 20 \
        --output reports/healthbench_e2e/healthbench_qwen35b_shard2_200.json
}

# ============================================================
# CHAIN 7: 144:8019 (qwen35b TP=1) — idle after T=0.7 qwen
# → C3 AgentClinic qwen35b duplicate (convergent validity)
# ============================================================
chain_8019() {
    wait_for_completion "results/defense_temp/agentclinic_qwen35b_t0_7.json" 100 "Temp T=0.7 qwen" || return 1

    log "Launching C3 AgentClinic qwen35b (TP=1 replica) on 144:8019..."
    run_or_log "C3 AC qwen35b replica" \
        env VLLM_MODEL="Qwen/Qwen3.5-35B-A3B-FP8" VLLM_URL="http://localhost:8013/v1" \
        OPENAI_API_KEY="not_needed" \
        python run_external_benchmark.py --benchmark agentclinic --limit 200 \
        --output results/defense_c3/agentclinic_qwen35b_tp1.json --save-every 10
}

# ============================================================
# CHAIN 8: 145:30006 (gemma TP=2) — idle after T=0.3 gemma
# → C3 AgentClinic gemma T=0.3 (temperature robustness)
# ============================================================
chain_30006() {
    wait_for_completion "results/defense_temp/agentclinic_gemma31b_t0_3.json" 100 "Temp T=0.3 gemma" || return 1

    log "Launching C3 MedAgentBench gemma (TP=2 replica) on 145:30006..."
    run_or_log "C3 MAB gemma replica" \
        env VLLM_MODEL="google/gemma-4-31b-it" VLLM_URL="http://localhost:8013/v1" \
        OPENAI_API_KEY="sk-no-key-required" \
        python run_external_benchmark.py --benchmark medagentbench --limit 200 \
        --output results/defense_c3/medagentbench_gemma31b_replica.json --save-every 10
}

# ============================================================
# Endpoints 144:8020 and 145:30007 left idle — no high-value
# work without new code (W9-4 MedCalc / W9-5 Synthea)
# ============================================================

# Launch supplement chains
log "=== Defense W9 Chain Launcher v2 (supplement) ==="
log "Covering 4 idle endpoints: 145:30005, 144:8018, 144:8019, 145:30006"
log "Idle (no work): 144:8020, 145:30007"

chain_30005 &
chain_8018 &
chain_8019 &
chain_30006 &

log "All supplement chains launched."
wait
log "=== All supplement chains complete ==="
