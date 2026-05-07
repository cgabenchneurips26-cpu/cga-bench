#!/bin/bash
# =============================================================
# Auto-Transition: oss120b_direct → oss120b_checklist
# =============================================================
# When direct reaches 706 unique scenarios, kills direct runners
# and launches replacement checklist runners on freed endpoints.
# Uses unique scenario counting (not raw file count) to prevent
# dedup false-positive.
# =============================================================

RESULTS_DIR="${CGA_BENCH_ROOT}/cga_bench/results/ex_w8_crossmodel"
CGA_DIR="${CGA_BENCH_ROOT}/cga_bench"
TARGET=706
CHECK_INTERVAL=120

echo "[$(date '+%H:%M:%S')] Auto-transition monitor started (direct → checklist)"
echo "[$(date '+%H:%M:%S')] Watching oss120b_direct for ${TARGET} unique scenarios"

while true; do
    # Count UNIQUE scenario_ids (not raw file count)
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

    echo "[$(date '+%H:%M:%S')] oss120b_direct: ${count}/${TARGET} unique scenarios"

    if [ "$count" -ge "$TARGET" ]; then
        echo ""
        echo "=============================================="
        echo "[$(date '+%H:%M:%S')] DIRECT COMPLETE! Starting transition to checklist..."
        echo "=============================================="

        echo "[$(date '+%H:%M:%S')] Killing direct shard_runners..."
        pids=$(ps aux | grep 'shard_runner.*oss120b_direct' | grep -v grep | awk '{print $2}')
        if [ -n "$pids" ]; then
            echo "$pids" | xargs kill 2>/dev/null
            echo "[$(date '+%H:%M:%S')] Killed $(echo "$pids" | wc -w) direct runners"
        fi

        sleep 3

        # Clean stale claim files in checklist
        find "${RESULTS_DIR}/oss120b_checklist/" -name '.claim_*' -delete 2>/dev/null
        find "${RESULTS_DIR}/oss120b_checklist/" -name 'checkpoint*.json' -delete 2>/dev/null
        echo "[$(date '+%H:%M:%S')] Cleaned checklist claims/checkpoints"

        echo "[$(date '+%H:%M:%S')] Launching checklist runners on freed endpoints..."
        cd "$CGA_DIR"

        # 144:30008 (was direct) → 3 checklist runners
        for s in 1 2 3; do
            PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                nohup python scripts/experiments/shard_runner.py \
                oss120b_checklist_p10 30008 results/ex_w8_crossmodel \
                --host 127.0.0.1 --split all \
                > "/tmp/oss120b_checklist_p8_tx${s}.log" 2>&1 &
        done

        # 145:30006, 145:30007 (were direct) → 6 checklist runners
        for port in 30006 30007; do
            for s in 1 2 3; do
                PYTHONPATH=${CGA_BENCH_ROOT} W8_RUNS=1 \
                    nohup python scripts/experiments/shard_runner.py \
                    oss120b_checklist_145p${port} ${port} results/ex_w8_crossmodel \
                    --host 127.0.0.1 --split all \
                    > "/tmp/oss120b_checklist_145p${port}_tx${s}.log" 2>&1 &
            done
        done

        sleep 3
        checklist_count=$(ps aux | grep 'shard_runner.*oss120b_checklist' | grep -v grep | wc -l)

        echo ""
        echo "=============================================="
        echo "[$(date '+%H:%M:%S')] Transition complete!"
        echo "  Killed: direct runners"
        echo "  Launched: 9 new checklist runners"
        echo "  Total checklist runners now: ${checklist_count}"
        echo "=============================================="

        exit 0
    fi

    sleep "$CHECK_INTERVAL"
done
