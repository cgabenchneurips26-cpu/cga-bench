#!/bin/bash
# =============================================================
# Auto-Transition: oss120b_react → oss120b_tooluse
# =============================================================
# Monitors oss120b_react unique scenario coverage.
# When all 706 unique scenarios are covered, kills react runners
# and launches replacement tooluse runners.
# =============================================================

RESULTS_DIR="${CGA_BENCH_ROOT}/cga_bench/results/ex_w8_crossmodel"
CGA_DIR="${CGA_BENCH_ROOT}/cga_bench"
TARGET=706
CHECK_INTERVAL=120

echo "[$(date '+%H:%M:%S')] Auto-transition monitor started (react → tooluse)"
echo "[$(date '+%H:%M:%S')] Watching oss120b_react for ${TARGET} unique scenarios"

while true; do
    # Count unique scenarios by checking scenario_id in JSON files
    count=$(python3 -c "
import json, os, glob
d = '${RESULTS_DIR}/oss120b_react'
files = glob.glob(os.path.join(d, '*.json'))
scenarios = set()
for f in files:
    bn = os.path.basename(f)
    if bn in ('checkpoint.json', 'model_summary.json'):
        continue
    try:
        data = json.load(open(f))
        sid = data.get('scenario_id', '')
        if sid:
            scenarios.add(sid)
    except:
        pass
print(len(scenarios))
" 2>/dev/null)

    echo "[$(date '+%H:%M:%S')] oss120b_react: ${count}/${TARGET} unique scenarios"

    if [ "$count" -ge "$TARGET" ]; then
        echo ""
        echo "=============================================="
        echo "[$(date '+%H:%M:%S')] REACT COMPLETE! Starting transition..."
        echo "=============================================="

        # Step 1: Kill all react runners
        echo "[$(date '+%H:%M:%S')] Killing react shard_runners..."
        pids_shard=$(ps aux | grep 'shard_runner.*oss120b_react' | grep -v grep | awk '{print $2}')
        if [ -n "$pids_shard" ]; then
            echo "$pids_shard" | xargs kill 2>/dev/null
            echo "[$(date '+%H:%M:%S')] Killed $(echo "$pids_shard" | wc -w) shard_runner react processes"
        fi

        echo "[$(date '+%H:%M:%S')] Killing react full_690_runners..."
        pids_full=$(ps aux | grep 'full_690_runner.*oss120b_react' | grep -v grep | awk '{print $2}')
        if [ -n "$pids_full" ]; then
            echo "$pids_full" | xargs kill 2>/dev/null
            echo "[$(date '+%H:%M:%S')] Killed $(echo "$pids_full" | wc -w) full_690_runner react processes"
        fi

        sleep 3

        # Step 2: Launch replacement tooluse runners
        echo "[$(date '+%H:%M:%S')] Launching additional tooluse runners..."
        cd "$CGA_DIR"

        # 144 endpoints (ports 30010, 30011, 30012)
        for port_key in p10 p11 p12; do
            port=${port_key#p}
            port="300${port}"
            shard_key="oss120b_tooluse_${port_key}"
            for s in 1 2; do
                PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                    nohup python scripts/experiments/shard_runner.py \
                    "$shard_key" "$port" results/ex_w8_crossmodel \
                    --host 127.0.0.1 --split all \
                    > "/tmp/${shard_key}_rx_boost${s}.log" 2>&1 &
            done
            echo "[$(date '+%H:%M:%S')] Launched 2x ${shard_key} (port ${port}, 144)"
        done

        # 145 endpoints (ports 30003, 30005, 30006, 30007)
        for port in 30003 30005 30006 30007; do
            shard_key="oss120b_tooluse_145p${port}"
            for s in 1 2; do
                PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                    nohup python scripts/experiments/shard_runner.py \
                    "$shard_key" "$port" results/ex_w8_crossmodel \
                    --host 127.0.0.1 --split all \
                    > "/tmp/${shard_key}_rx_boost${s}.log" 2>&1 &
            done
            echo "[$(date '+%H:%M:%S')] Launched 2x ${shard_key} (port ${port}, 145)"
        done

        # 4 extra on port 30008 (144 original)
        for i in 1 2 3 4; do
            shard_key="oss120b_tooluse_p10"
            PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                nohup python scripts/experiments/shard_runner.py \
                "$shard_key" 30008 results/ex_w8_crossmodel \
                --host 127.0.0.1 --split all \
                > "/tmp/oss120b_tooluse_p8_rx${i}.log" 2>&1 &
        done
        echo "[$(date '+%H:%M:%S')] Launched 4x tooluse on port 30008 (144)"

        echo ""
        echo "=============================================="
        echo "[$(date '+%H:%M:%S')] Transition complete!"
        echo "  Killed: ~18 react runners"
        echo "  Launched: 18 additional tooluse runners"
        echo "=============================================="

        sleep 5
        tooluse_count=$(ps aux | grep 'shard_runner.*oss120b_tooluse' | grep -v grep | wc -l)
        echo "[$(date '+%H:%M:%S')] Active tooluse runners: ${tooluse_count}"

        exit 0
    fi

    sleep "$CHECK_INTERVAL"
done
