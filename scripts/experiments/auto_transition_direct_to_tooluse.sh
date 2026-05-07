#!/bin/bash
# =============================================================
# Auto-Transition: oss120b_direct → oss120b_tooluse
# =============================================================
# Monitors oss120b_direct progress. When it reaches 706/706,
# kills all direct runners and launches replacement tooluse
# runners to maximize throughput on the bottleneck scaffold.
# =============================================================

RESULTS_DIR="${CGA_BENCH_ROOT}/cga_bench/results/ex_w8_crossmodel"
CGA_DIR="${CGA_BENCH_ROOT}/cga_bench"
TARGET=706
CHECK_INTERVAL=60

echo "[$(date '+%H:%M:%S')] Auto-transition monitor started"
echo "[$(date '+%H:%M:%S')] Watching oss120b_direct for ${TARGET}/706 completion"

while true; do
    # Count UNIQUE scenario_ids (not raw file count — prevents dedup false-positive)
    count=$(python3 -c "
import json, os, glob
d = '${RESULTS_DIR}/oss120b_direct'
files = glob.glob(os.path.join(d, '*.json'))
scenarios = set()
for f in files:
    bn = os.path.basename(f)
    if bn.startswith('checkpoint') or bn == 'model_summary.json':
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

    echo "[$(date '+%H:%M:%S')] oss120b_direct: ${count}/${TARGET}"

    if [ "$count" -ge "$TARGET" ]; then
        echo ""
        echo "=============================================="
        echo "[$(date '+%H:%M:%S')] DIRECT COMPLETE! Starting transition..."
        echo "=============================================="

        # Step 1: Kill all direct runners
        echo "[$(date '+%H:%M:%S')] Killing direct shard_runners..."
        pids_shard=$(ps aux | grep 'shard_runner.*oss120b_direct' | grep -v grep | awk '{print $2}')
        if [ -n "$pids_shard" ]; then
            echo "$pids_shard" | xargs kill 2>/dev/null
            echo "[$(date '+%H:%M:%S')] Killed $(echo "$pids_shard" | wc -w) shard_runner direct processes"
        fi

        echo "[$(date '+%H:%M:%S')] Killing direct full_690_runners..."
        pids_full=$(ps aux | grep 'full_690_runner.*oss120b_direct' | grep -v grep | awk '{print $2}')
        if [ -n "$pids_full" ]; then
            echo "$pids_full" | xargs kill 2>/dev/null
            echo "[$(date '+%H:%M:%S')] Killed $(echo "$pids_full" | wc -w) full_690_runner direct processes"
        fi

        sleep 3

        # Step 2: Launch replacement tooluse runners
        # 7 ports × 1 additional runner each = 7 new (doubling existing)
        echo "[$(date '+%H:%M:%S')] Launching additional tooluse runners..."
        cd "$CGA_DIR"

        # 144 endpoints (ports 30010, 30011, 30012)
        for port_key in p10 p11 p12; do
            port=${port_key#p}
            port="300${port}"
            shard_key="oss120b_tooluse_${port_key}"
            PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                nohup python scripts/experiments/shard_runner.py \
                "$shard_key" "$port" results/ex_w8_crossmodel \
                --host 127.0.0.1 --split all \
                > "/tmp/${shard_key}_boost.log" 2>&1 &
            echo "[$(date '+%H:%M:%S')] Launched ${shard_key} (port ${port}, 144)"
        done

        # 145 endpoints (ports 30003, 30005, 30006, 30007)
        for port in 30003 30005 30006 30007; do
            shard_key="oss120b_tooluse_145p${port}"
            PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                nohup python scripts/experiments/shard_runner.py \
                "$shard_key" "$port" results/ex_w8_crossmodel \
                --host 127.0.0.1 --split all \
                > "/tmp/${shard_key}_boost.log" 2>&1 &
            echo "[$(date '+%H:%M:%S')] Launched ${shard_key} (port ${port}, 145)"
        done

        # 3 extra runners on highest-bandwidth ports (145 has faster response)
        for port in 30003 30005 30006; do
            shard_key="oss120b_tooluse_145p${port}"
            PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                nohup python scripts/experiments/shard_runner.py \
                "$shard_key" "$port" results/ex_w8_crossmodel \
                --host 127.0.0.1 --split all \
                > "/tmp/${shard_key}_boost2.log" 2>&1 &
            echo "[$(date '+%H:%M:%S')] Launched ${shard_key} extra (port ${port}, 145)"
        done

        echo ""
        echo "=============================================="
        echo "[$(date '+%H:%M:%S')] Transition complete!"
        echo "  Killed: ~10 direct runners"
        echo "  Launched: 10 additional tooluse runners"
        echo "  Total tooluse: ~17 runners (7 existing + 10 new)"
        echo "=============================================="

        # Final status
        sleep 5
        tooluse_count=$(ps aux | grep 'shard_runner.*oss120b_tooluse' | grep -v grep | wc -l)
        echo "[$(date '+%H:%M:%S')] Active tooluse runners: ${tooluse_count}"

        exit 0
    fi

    sleep "$CHECK_INTERVAL"
done
