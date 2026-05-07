#!/bin/bash
# =============================================================
# Auto-Transition: oss120b_tooluse → oss120b_react
# =============================================================
# Monitors oss120b_tooluse unique scenario coverage.
# When all 706 unique scenarios are covered, kills tooluse runners
# and launches replacement react runners.
# =============================================================

RESULTS_DIR="${CGA_BENCH_ROOT}/cga_bench/results/ex_w8_crossmodel"
CGA_DIR="${CGA_BENCH_ROOT}/cga_bench"
TARGET=706
CHECK_INTERVAL=120

echo "[$(date '+%H:%M:%S')] Auto-transition monitor started (tooluse → react)"
echo "[$(date '+%H:%M:%S')] Watching oss120b_tooluse for ${TARGET} unique scenarios"

while true; do
    count=$(python3 -c "
import json, os, glob
d = '${RESULTS_DIR}/oss120b_tooluse'
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

    echo "[$(date '+%H:%M:%S')] oss120b_tooluse: ${count}/${TARGET} unique scenarios"

    if [ "$count" -ge "$TARGET" ]; then
        echo ""
        echo "=============================================="
        echo "[$(date '+%H:%M:%S')] TOOLUSE COMPLETE! Starting transition..."
        echo "=============================================="

        echo "[$(date '+%H:%M:%S')] Killing tooluse shard_runners..."
        pids=$(ps aux | grep 'shard_runner.*oss120b_tooluse' | grep -v grep | awk '{print $2}')
        if [ -n "$pids" ]; then
            echo "$pids" | xargs kill 2>/dev/null
            echo "[$(date '+%H:%M:%S')] Killed $(echo "$pids" | wc -w) tooluse runners"
        fi

        sleep 3

        echo "[$(date '+%H:%M:%S')] Launching react runners..."
        cd "$CGA_DIR"

        # 144 endpoints: 4 ports × 3 runners each = 12
        for port_key in p10:30010 p11:30011 p12:30012; do
            key=${port_key%%:*}; port=${port_key##*:}
            for s in 1 2 3; do
                PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                    nohup python scripts/experiments/shard_runner.py \
                    oss120b_react_${key} ${port} results/ex_w8_crossmodel \
                    --host 127.0.0.1 --split all \
                    > "/tmp/oss120b_react_${key}_final${s}.log" 2>&1 &
            done
        done
        for s in 1 2 3 4 5; do
            PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                nohup python scripts/experiments/shard_runner.py \
                oss120b_react_p10 30008 results/ex_w8_crossmodel \
                --host 127.0.0.1 --split all \
                > "/tmp/oss120b_react_p8_final${s}.log" 2>&1 &
        done

        # 145 endpoints: 4 ports × 3 runners each = 12
        for port in 30003 30005 30006 30007; do
            for s in 1 2 3; do
                PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                    nohup python scripts/experiments/shard_runner.py \
                    oss120b_react_145p${port} ${port} results/ex_w8_crossmodel \
                    --host 127.0.0.1 --split all \
                    > "/tmp/oss120b_react_145p${port}_final${s}.log" 2>&1 &
            done
        done

        echo ""
        echo "=============================================="
        echo "[$(date '+%H:%M:%S')] Transition complete!"
        echo "  Killed: ~26 tooluse runners"
        echo "  Launched: ~26 react runners"
        echo "=============================================="

        sleep 5
        react_count=$(ps aux | grep 'shard_runner.*oss120b_react' | grep -v grep | wc -l)
        echo "[$(date '+%H:%M:%S')] Active react runners: ${react_count}"

        exit 0
    fi

    sleep "$CHECK_INTERVAL"
done
