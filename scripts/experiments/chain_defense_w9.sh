#!/bin/bash
# Chain launcher: monitors defense experiment completion and launches W9 experiments
# Usage: bash scripts/experiments/chain_defense_w9.sh
set -euo pipefail
cd ${CGA_BENCH_ROOT}/cga_bench

check_episodes() {
    local file=$1
    local target=$2
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
    echo "[$(date +%H:%M)] Waiting for $label ($file) to reach $target episodes..."
    while true; do
        n=$(check_episodes "$file" "$target")
        if [ "$n" -ge "$target" ]; then
            echo "[$(date +%H:%M)] $label DONE: $n/$target episodes"
            return
        fi
        sleep 60
    done
}

# ============================================================
# CHAIN 1: 144:8017 (qwen35b TP=1)
# Current: Temp T=0.0 → Next: HealthBench qwen35b
# ============================================================
chain_8017() {
    wait_for_completion "results/defense_temp/agentclinic_qwen35b_t0_0.json" 100 "Temp T=0.0 qwen35b"
    echo "[$(date +%H:%M)] Launching HealthBench qwen35b on 144:8017..."
    PYTHONPATH=. OPENAI_API_KEY="not_needed" python scripts/e2e_healthbench.py \
        --endpoint http://localhost:8013/v1 \
        --model "Qwen/Qwen3.5-35B-A3B-FP8" \
        --limit 200 --save-every 20 \
        --output reports/healthbench_e2e/healthbench_qwen35b_200.json
}

# ============================================================
# CHAIN 2: 145:30003 (gemma TP=2)
# Current: Temp T=0.1 control → Next: HealthBench gemma31b
# ============================================================
chain_30003() {
    wait_for_completion "results/defense_temp/agentclinic_gemma31b_t0_1.json" 100 "Temp T=0.1 gemma ctrl"
    echo "[$(date +%H:%M)] Launching HealthBench gemma31b on 145:30003..."
    PYTHONPATH=. OPENAI_API_KEY="sk-no-key-required" python scripts/e2e_healthbench.py \
        --endpoint http://localhost:8013/v1 \
        --model "google/gemma-4-31b-it" \
        --limit 200 --save-every 20 \
        --output reports/healthbench_e2e/healthbench_gemma31b_200.json
}

# ============================================================
# CHAIN 3: 144:30008 (oss120b TP=2)
# Current: AMEGA → Next: C3 AgentClinic → C3 MAB → HealthBench
# ============================================================
chain_30008() {
    # Wait for AMEGA oss120b (3 runs × 24 = look for run3 file)
    echo "[$(date +%H:%M)] Waiting for AMEGA oss120b to complete..."
    while [ ! -f "results/amega_oss120b_run3.json" ]; do sleep 60; done
    sleep 10  # let file finish writing

    echo "[$(date +%H:%M)] Launching C3 AgentClinic oss120b on 144:30008..."
    VLLM_MODEL="openai/gpt-oss-120b" VLLM_URL="http://localhost:8013/v1" \
        OPENAI_API_KEY="sk-no-key-required" \
        python run_external_benchmark.py --benchmark agentclinic --limit 200 \
        --output results/defense_c3/agentclinic_oss120b.json --save-every 10

    echo "[$(date +%H:%M)] Launching C3 MedAgentBench oss120b on 144:30008..."
    VLLM_MODEL="openai/gpt-oss-120b" VLLM_URL="http://localhost:8013/v1" \
        OPENAI_API_KEY="sk-no-key-required" \
        python run_external_benchmark.py --benchmark medagentbench --limit 200 \
        --output results/defense_c3/medagentbench_oss120b.json --save-every 10

    echo "[$(date +%H:%M)] Launching HealthBench oss120b on 144:30008..."
    PYTHONPATH=. OPENAI_API_KEY="sk-no-key-required" python scripts/e2e_healthbench.py \
        --endpoint http://localhost:8013/v1 \
        --model "openai/gpt-oss-120b" \
        --limit 200 --save-every 20 \
        --output reports/healthbench_e2e/healthbench_oss120b_200.json
}

# ============================================================
# CHAIN 4: 144:30009 (qwen35b TP=2)
# Current: AMEGA → Next: C3 AgentClinic → C3 MAB
# ============================================================
chain_30009() {
    echo "[$(date +%H:%M)] Waiting for AMEGA qwen35b to complete..."
    while [ ! -f "results/amega_qwen35b_run3.json" ]; do sleep 60; done
    sleep 10

    echo "[$(date +%H:%M)] Launching C3 AgentClinic qwen35b on 144:30009..."
    VLLM_MODEL="Qwen/Qwen3.5-35B-A3B-FP8" VLLM_URL="http://localhost:8013/v1" \
        OPENAI_API_KEY="sk-no-key-required" \
        python run_external_benchmark.py --benchmark agentclinic --limit 200 \
        --output results/defense_c3/agentclinic_qwen35b.json --save-every 10

    echo "[$(date +%H:%M)] Launching C3 MedAgentBench qwen35b on 144:30009..."
    VLLM_MODEL="Qwen/Qwen3.5-35B-A3B-FP8" VLLM_URL="http://localhost:8013/v1" \
        OPENAI_API_KEY="sk-no-key-required" \
        python run_external_benchmark.py --benchmark medagentbench --limit 200 \
        --output results/defense_c3/medagentbench_qwen35b.json --save-every 10
}

# Launch all chains in parallel
echo "=== Defense → W9 Chain Launcher ==="
echo "Starting 4 parallel chains at $(date)"
chain_8017 &
chain_30003 &
chain_30008 &
chain_30009 &

echo "All chains launched. Monitor with: tail -f /tmp/chain_defense_w9.log"
wait
echo "=== All chains complete at $(date) ==="
