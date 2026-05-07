#!/bin/bash
# =============================================================
# Transition Script: Free idle GPUs → oss120b acceleration
# =============================================================
# Run from: <relay> machine (anonymized)
#
# PHASE 1: COMPLETED (Apr 19 04:45 KST)
#   - Stopped qwen35b Docker containers on 144 (GPU 0-3)
#   - Stopped qwen35b-amega on 144 (GPU 6,7)
#   - Launched 3 new oss120b TP=2 Docker containers:
#     oss120b-accel-01 (GPU 0,1, port 30010)
#     oss120b-accel-23 (GPU 2,3, port 30011)
#     oss120b-accel-67 (GPU 6,7, port 30012)
#   - 15 shard runners launched across 30010/30011/30012
#
# PHASE 2: When gemma31b_tooluse completes on 145
#   - Stop gemma4 containers (4x)
#   - Start 4x oss120b TP=2 containers (reuse ports 30003/30005-30007)
#
# All experiments use checkpoint/resume, safe to interrupt.
# =============================================================

SSH144="ssh -i /tmp/anonymous-org_key -o StrictHostKeyChecking=no [email-redacted]"
SSH145="ssh -i /tmp/anonymous-org_key -o StrictHostKeyChecking=no [email-redacted]"

# =============================================================
# PHASE 2: 145 → oss120b (after gemma31b_tooluse done)
# Prerequisites:
#   - gemma31b_tooluse at 706/706
#   - Model transfer complete: du -sh on 145 shows ~61G
# =============================================================
phase2_145() {
    echo "=== PHASE 2: 145 transition ==="

    # Verify model exists
    echo "Checking model on 145..."
    $SSH145 'du -sh /home/anonymous-org/.cache/huggingface/hub/models--openai--gpt-oss-120b/ 2>/dev/null || echo "MODEL NOT FOUND"'

    # Stop gemma4 containers
    echo "Stopping gemma4 containers..."
    $SSH145 'docker stop gemma4 gemma4_s2 gemma4_s3 gemma4_s4 2>/dev/null'
    $SSH145 'docker rm gemma4 gemma4_s2 gemma4_s3 gemma4_s4 2>/dev/null'
    sleep 5

    # Verify GPUs freed
    $SSH145 'nvidia-smi --query-gpu=index,memory.used --format=csv,noheader'

    # Start 4 x oss120b TP=2 containers
    # Using same image (gemma4 tag) and volume mount as existing containers
    local ports=(30003 30005 30006 30007)
    local gpu_pairs=("0,1" "2,3" "4,5" "6,7")
    local names=("oss120b-145-01" "oss120b-145-23" "oss120b-145-45" "oss120b-145-67")

    for i in 0 1 2 3; do
        echo "Starting ${names[$i]} on GPU ${gpu_pairs[$i]} (port ${ports[$i]})..."
        $SSH145 "docker run -d \
            --runtime=nvidia \
            -e NVIDIA_VISIBLE_DEVICES=${gpu_pairs[$i]} \
            --name ${names[$i]} \
            -p ${ports[$i]}:8000 \
            -v /home/anonymous-org/.cache/huggingface:/root/.cache/huggingface \
            vllm/vllm-openai:gemma4 \
            --model openai/gpt-oss-120b \
            --tensor-parallel-size 2 \
            --max-model-len 8192 \
            --gpu-memory-utilization 0.9 \
            --api-key sk-no-key-required \
            --trust-remote-code --enforce-eager"
    done

    echo "Waiting 120s for vLLM startup..."
    sleep 120

    # Health check
    echo "Health check:"
    for port in "${ports[@]}"; do
        curl -s -m 10 -H "Authorization: Bearer sk-no-key-required" \
            http://localhost:8013$port/v1/models \
            | python3 -c "import sys,json; print('$port:', json.load(sys.stdin)['data'][0]['id'])" \
            2>/dev/null || echo "$port: NOT READY"
    done
}

# =============================================================
# PHASE 2b: Launch oss120b runners for 145 endpoints
# =============================================================
phase2b_runners() {
    echo "=== PHASE 2b: Launch 145 oss120b runners ==="
    cd ${CGA_BENCH_ROOT}/cga_bench

    for port in 30003 30005 30006 30007; do
        for scaffold in react direct checklist tooluse; do
            shard_key="oss120b_${scaffold}_145p${port}"
            PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                nohup python scripts/experiments/shard_runner.py \
                $shard_key $port results/ex_w8_crossmodel \
                --host 127.0.0.1 --split all \
                > /tmp/${shard_key}.log 2>&1 &
        done
    done

    echo "Launched 16 runners (4 ports × 4 scaffolds) on 145"
}

echo "Usage:"
echo "  source transition_oss120b.sh"
echo "  phase2_145      # After gemma31b_tooluse done on 145"
echo "  phase2b_runners # After 145 endpoints are healthy"
