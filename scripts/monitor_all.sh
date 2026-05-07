#!/bin/bash
# Monitor all CGA-Bench episode runners + vLLM servers
# Usage: bash scripts/monitor_all.sh

NEW_SERVER="127.0.0.1
RESULTS_DIR="results/full_706_v5"
TARGET_PER_MODEL=$((706 * 3))

echo "=========================================="
echo "  CGA-Bench Episode Monitor"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

echo ""
echo "--- Episode Progress (target: $TARGET_PER_MODEL per model) ---"
if [ -d "$RESULTS_DIR" ]; then
    for d in "$RESULTS_DIR"/*/; do
        [ -d "$d" ] || continue
        model=$(basename "$d")
        count=$(find "$d" -maxdepth 1 -name "*.json" ! -name "checkpoint*" 2>/dev/null | wc -l)
        pct=$((count * 100 / TARGET_PER_MODEL))
        bar_len=$((pct / 5))
        bar=$(printf '%*s' "$bar_len" '' | tr ' ' '#')
        printf "  %-15s %4d/%d (%3d%%) %s\n" "$model" "$count" "$TARGET_PER_MODEL" "$pct" "$bar"
    done
else
    echo "  (no results directory found)"
fi

echo ""
echo "--- vLLM Server Status (local) ---"
for entry in "28000:oss120b" "8013:qwen35b" "28010:qwen27b" "8101:qwen4b"; do
    port="${entry%%:*}"
    label="${entry##*:}"
    status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "http://localhost:$port/v1/models" 2>/dev/null)
    if [ "$status" = "200" ] || [ "$status" = "401" ]; then
        printf "  localhost:%-6d %-15s ALIVE (%s)\n" "$port" "$label" "$status"
    else
        printf "  localhost:%-6d %-15s DOWN  (%s)\n" "$port" "$label" "$status"
    fi
done

echo ""
echo "--- vLLM Server Status (127.0.0.1 — existing remote) ---"
for entry in "30001:qwen397b" "30003:gemma31b" "30004:nemotron30b"; do
    port="${entry%%:*}"
    label="${entry##*:}"
    status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "http://localhost:8013$port/v1/models" 2>/dev/null)
    if [ "$status" = "200" ] || [ "$status" = "401" ]; then
        printf "  127.0.0.1 %-15s ALIVE (%s)\n" "$port" "$label" "$status"
    else
        printf "  127.0.0.1 %-15s DOWN  (%s)\n" "$port" "$label" "$status"
    fi
done

echo ""
echo "--- vLLM Server Status ($NEW_SERVER — new remote) ---"
for entry in "8201:qwen27b-r1" "8202:qwen27b-r2" "8203:qwen35b-e8" "8204:qwen35b-judge" "8205:llama4scout"; do
    port="${entry%%:*}"
    label="${entry##*:}"
    status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 "http://$NEW_SERVER:$port/v1/models" 2>/dev/null)
    if [ "$status" = "200" ] || [ "$status" = "401" ]; then
        printf "  $NEW_SERVER:%-6d %-15s ALIVE (%s)\n" "$port" "$label" "$status"
    else
        printf "  $NEW_SERVER:%-6d %-15s DOWN  (%s)\n" "$port" "$label" "$status"
    fi
done

echo ""
echo "--- E8 Adapter Progress ---"
e8_dir="results/e8_adapter_ac"
if [ -d "$e8_dir" ]; then
    e8_count=$(find "$e8_dir" -name "*.json" 2>/dev/null | wc -l)
    echo "  AgentClinic fresh: $e8_count files"
else
    echo "  (not started)"
fi

echo ""
echo "--- Active Runner Processes ---"
ps aux | grep -E "full_690_runner|shard_runner|run_external_benchmark|exp_2_llm_judge" | grep -v grep | \
    awk '{printf "  PID %-8s %s %s %s\n", $2, $(NF-2), $(NF-1), $NF}'

echo ""
echo "--- Recent Errors (last 3 per log) ---"
for log in logs/shard_qwen27b_r*.log logs/llama4scout.log; do
    if [ -f "$log" ]; then
        errs=$(grep -ci "error\|traceback\|FAILED" "$log" 2>/dev/null)
        echo "  $(basename "$log"): $errs errors"
        if [ "$errs" -gt 0 ] 2>/dev/null; then
            grep -i "error\|FAILED" "$log" 2>/dev/null | tail -3 | sed 's/^/    /'
        fi
    fi
done
