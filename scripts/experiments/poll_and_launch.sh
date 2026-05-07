#!/bin/bash
# Poll endpoints and auto-launch W8 chains when ready
cd ${CGA_BENCH_ROOT}/cga_bench
LOG=/tmp/poll_and_launch.log

nemotron_launched=0
qwen397b_launched=0

echo "[$(date '+%H:%M:%S')] Polling endpoints for readiness..." | tee "$LOG"

while true; do
    # Check nemotron30b (145:30005)
    if [ "$nemotron_launched" -eq 0 ]; then
        resp=$(curl -s --max-time 3 -H "Authorization: Bearer sk-no-key-required" http://localhost:8013/v1/models 2>/dev/null)
        if echo "$resp" | grep -q '"object":"list"'; then
            echo "[$(date '+%H:%M:%S')] nemotron30b READY — launching W8 chain" | tee -a "$LOG"
            nohup bash scripts/experiments/launch_nemotron30b_w8.sh >> "$LOG" 2>&1 &
            nemotron_launched=1
        fi
    fi

    # Check qwen397b (144:30001)
    if [ "$qwen397b_launched" -eq 0 ]; then
        resp=$(curl -s --max-time 3 http://localhost:8013/v1/models 2>/dev/null)
        if echo "$resp" | grep -q '"object":"list"'; then
            echo "[$(date '+%H:%M:%S')] qwen397b READY — launching W8 chains" | tee -a "$LOG"
            nohup bash scripts/experiments/launch_qwen397b_w8.sh >> "$LOG" 2>&1 &
            qwen397b_launched=1
        fi
    fi

    # All launched?
    if [ "$nemotron_launched" -eq 1 ] && [ "$qwen397b_launched" -eq 1 ]; then
        echo "[$(date '+%H:%M:%S')] All endpoints ready, all chains launched." | tee -a "$LOG"
        break
    fi

    sleep 30
done
