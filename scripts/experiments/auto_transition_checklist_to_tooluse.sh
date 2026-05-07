#!/bin/bash
# =============================================================
# Auto-Transition: oss120b_checklist → oss120b_tooluse
# =============================================================
# Monitors oss120b_checklist progress. When it reaches 706/706,
# kills all checklist runners and launches replacement tooluse
# runners to further accelerate the bottleneck scaffold.
# =============================================================

RESULTS_DIR="${CGA_BENCH_ROOT}/cga_bench/results/ex_w8_crossmodel"
CGA_DIR="${CGA_BENCH_ROOT}/cga_bench"
TARGET=706
CHECK_INTERVAL=60

echo "[$(date '+%H:%M:%S')] Auto-transition monitor started (checklist → tooluse)"
echo "[$(date '+%H:%M:%S')] Watching oss120b_checklist for ${TARGET}/706 completion"

while true; do
    # Count UNIQUE scenario_ids (not raw file count — prevents dedup false-positive)
    count=$(python3 -c "
import json, os, glob
d = '${RESULTS_DIR}/oss120b_checklist'
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

    echo "[$(date '+%H:%M:%S')] oss120b_checklist: ${count}/${TARGET}"

    if [ "$count" -ge "$TARGET" ]; then
        echo ""
        echo "=============================================="
        echo "[$(date '+%H:%M:%S')] CHECKLIST COMPLETE! Starting transition..."
        echo "=============================================="

        # Step 1: Kill all checklist runners
        echo "[$(date '+%H:%M:%S')] Killing checklist shard_runners..."
        pids_shard=$(ps aux | grep 'shard_runner.*oss120b_checklist' | grep -v grep | awk '{print $2}')
        if [ -n "$pids_shard" ]; then
            echo "$pids_shard" | xargs kill 2>/dev/null
            echo "[$(date '+%H:%M:%S')] Killed $(echo "$pids_shard" | wc -w) shard_runner checklist processes"
        fi

        echo "[$(date '+%H:%M:%S')] Killing checklist full_690_runners..."
        pids_full=$(ps aux | grep 'full_690_runner.*oss120b_checklist' | grep -v grep | awk '{print $2}')
        if [ -n "$pids_full" ]; then
            echo "$pids_full" | xargs kill 2>/dev/null
            echo "[$(date '+%H:%M:%S')] Killed $(echo "$pids_full" | wc -w) full_690_runner checklist processes"
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
            PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                nohup python scripts/experiments/shard_runner.py \
                "$shard_key" "$port" results/ex_w8_crossmodel \
                --host 127.0.0.1 --split all \
                > "/tmp/${shard_key}_ck_boost.log" 2>&1 &
            echo "[$(date '+%H:%M:%S')] Launched ${shard_key} (port ${port}, 144)"
        done

        # 145 endpoints (ports 30003, 30005, 30006, 30007)
        for port in 30003 30005 30006 30007; do
            shard_key="oss120b_tooluse_145p${port}"
            PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                nohup python scripts/experiments/shard_runner.py \
                "$shard_key" "$port" results/ex_w8_crossmodel \
                --host 127.0.0.1 --split all \
                > "/tmp/${shard_key}_ck_boost.log" 2>&1 &
            echo "[$(date '+%H:%M:%S')] Launched ${shard_key} (port ${port}, 145)"
        done

        # 4 extra runners on 144 original endpoint (port 30008)
        for i in 1 2 3 4; do
            shard_key="oss120b_tooluse_p10"
            PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                nohup python scripts/experiments/shard_runner.py \
                "$shard_key" 30008 results/ex_w8_crossmodel \
                --host 127.0.0.1 --split all \
                > "/tmp/oss120b_tooluse_p8_ck${i}.log" 2>&1 &
            echo "[$(date '+%H:%M:%S')] Launched tooluse on port 30008 #${i} (144)"
        done

        echo ""
        echo "=============================================="
        echo "[$(date '+%H:%M:%S')] Transition complete!"
        echo "  Killed: ~11 checklist runners"
        echo "  Launched: 11 additional tooluse runners"
        echo "=============================================="

        sleep 5
        tooluse_count=$(ps aux | grep 'shard_runner.*oss120b_tooluse' | grep -v grep | wc -l)
        react_count=$(ps aux | grep -E '(shard_runner|full_690_runner).*oss120b_react' | grep -v grep | wc -l)
        echo "[$(date '+%H:%M:%S')] Active tooluse runners: ${tooluse_count}"
        echo "[$(date '+%H:%M:%S')] Active react runners: ${react_count}"

        exit 0
    fi

    sleep "$CHECK_INTERVAL"
done
