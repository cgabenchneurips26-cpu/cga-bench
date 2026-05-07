#!/bin/bash
# Poll nemotron30b endpoint and auto-launch when ready
cd ${CGA_BENCH_ROOT}/cga_bench
LOG=/tmp/poll_nemotron30b.log
echo "[$(date '+%H:%M:%S')] Polling nemotron30b (145:30005)..." | tee "$LOG"

while true; do
    resp=$(curl -s --max-time 3 -H "Authorization: Bearer sk-no-key-required" http://localhost:8013/v1/models 2>/dev/null)
    if echo "$resp" | grep -q '"object":"list"'; then
        echo "[$(date '+%H:%M:%S')] nemotron30b READY — launching W8 chain" | tee -a "$LOG"
        nohup bash scripts/experiments/launch_nemotron30b_w8.sh >> "$LOG" 2>&1 &
        echo "[$(date '+%H:%M:%S')] Launched. Exiting poll." | tee -a "$LOG"
        break
    fi
    sleep 30
done
