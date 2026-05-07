#!/bin/bash
# Deploy DeepSeek-R1 7B on 127.0.0.1 (8 GPUs, 8 hours max)
#
# Usage: SSH into 145 and run:
#   bash deploy_deepseek_145.sh
#
# After completion, rsync results back:
#   rsync -avz 127.0.0.1 \
#     results/full_706_v5/deepseek_r1_7b/
#
# Then dedup:
#   python scripts/experiments/full_690_runner.py deepseek_r1_7b results/full_706_v5 --dedup

set -euo pipefail

MODEL="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
RESULTS_DIR="/data1/deepseek_bench"
REPO_DIR="/data1/anonymous-project/AnonProject/cga_bench"  # Adjust if different on 145
NUM_GPUS=8
BASE_PORT=8401  # Different from localhost 8301-8308
API_KEY="sk-no-key-required"

echo "=== Step 1: Launch 8 vLLM servers ==="
for i in $(seq 0 $((NUM_GPUS - 1))); do
    PORT=$((BASE_PORT + i))
    echo "  GPU $i -> port $PORT"
    CUDA_VISIBLE_DEVICES=$i python -m vllm.entrypoints.openai.api_server \
        --model "$MODEL" \
        --port "$PORT" \
        --tensor-parallel-size 1 \
        --gpu-memory-utilization 0.9 \
        --max-model-len 16384 \
        --api-key "$API_KEY" \
        > "/tmp/vllm_deepseek_gpu${i}.log" 2>&1 &
    echo "    PID: $!"
done

echo ""
echo "=== Step 2: Wait for servers to be ready ==="
sleep 30  # Initial wait for model loading

for i in $(seq 0 $((NUM_GPUS - 1))); do
    PORT=$((BASE_PORT + i))
    for attempt in $(seq 1 30); do
        if curl -s -H "Authorization: Bearer $API_KEY" \
            "http://localhost:${PORT}/v1/models" > /dev/null 2>&1; then
            echo "  GPU $i (port $PORT): READY"
            break
        fi
        if [ "$attempt" -eq 30 ]; then
            echo "  GPU $i (port $PORT): FAILED after 5 min"
            exit 1
        fi
        sleep 10
    done
done

echo ""
echo "=== Step 3: Launch 8 shard runners ==="
mkdir -p "$RESULTS_DIR"

for i in $(seq 1 $NUM_GPUS); do
    PORT=$((BASE_PORT + i - 1))
    SHARD="${i}/${NUM_GPUS}"
    LOG="${RESULTS_DIR}/log_deepseek_r1_7b_145_s${i}of${NUM_GPUS}.txt"
    echo "  Shard $SHARD -> port $PORT"

    PYTHONPATH=/data1/anonymous-project/AnonProject \
    nohup python "$REPO_DIR/scripts/experiments/full_690_runner.py" \
        deepseek_r1_7b "$RESULTS_DIR" \
        --shard "$SHARD" \
        --port "$PORT" \
        --host localhost \
        > "$LOG" 2>&1 &
    echo "    PID: $!"
done

echo ""
echo "=== Deployment complete ==="
echo "Monitor: tail -f ${RESULTS_DIR}/log_deepseek_r1_7b_145_s1of${NUM_GPUS}.txt"
echo "Count:   ls ${RESULTS_DIR}/deepseek_r1_7b/*.json | wc -l"
echo ""
echo "=== After 8 hours: rsync results back to localhost ==="
echo "From localhost run:"
echo "  rsync -avz 127.0.0.1 results/full_706_v5/deepseek_r1_7b/"
echo "  python scripts/experiments/full_690_runner.py deepseek_r1_7b results/full_706_v5 --dedup"
echo ""
echo "=== To stop everything ==="
echo "  pkill -f 'vllm.*DeepSeek-R1-Distill'"
echo "  pkill -f 'full_690_runner.*deepseek'"
