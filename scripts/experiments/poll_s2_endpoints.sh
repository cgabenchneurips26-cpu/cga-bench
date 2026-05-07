#!/bin/bash
# Poll S2 endpoints and auto-launch W8 chains when ready
cd ${CGA_BENCH_ROOT}/cga_bench
LOG=/tmp/poll_s2.log
echo "[$(date '+%H:%M:%S')] Polling S2 endpoints (145:30007 qwen27b, 145:30008 qwen4b)..." | tee "$LOG"

LAUNCHED_27B=0
LAUNCHED_4B=0

while [ $LAUNCHED_27B -eq 0 ] || [ $LAUNCHED_4B -eq 0 ]; do
    if [ $LAUNCHED_27B -eq 0 ]; then
        resp=$(curl -s --max-time 3 -H "Authorization: Bearer sk-no-key-required" http://localhost:8013/v1/models 2>/dev/null)
        if echo "$resp" | grep -q '"object":"list"'; then
            echo "[$(date '+%H:%M:%S')] qwen27b_s2 (30007) READY — launching chain" | tee -a "$LOG"
            nohup bash scripts/experiments/launch_qwen27b_s2_w8.sh >> "$LOG" 2>&1 &
            LAUNCHED_27B=1
        fi
    fi
    if [ $LAUNCHED_4B -eq 0 ]; then
        resp=$(curl -s --max-time 3 -H "Authorization: Bearer sk-no-key-required" http://localhost:8013/v1/models 2>/dev/null)
        if echo "$resp" | grep -q '"object":"list"'; then
            echo "[$(date '+%H:%M:%S')] qwen4b_s2 (30008) READY — launching chain" | tee -a "$LOG"
            nohup bash scripts/experiments/launch_qwen4b_s2_w8.sh >> "$LOG" 2>&1 &
            LAUNCHED_4B=1
        fi
    fi
    if [ $LAUNCHED_27B -eq 0 ] || [ $LAUNCHED_4B -eq 0 ]; then
        sleep 15
    fi
done
echo "[$(date '+%H:%M:%S')] All S2 chains launched. Exiting poll." | tee -a "$LOG"
