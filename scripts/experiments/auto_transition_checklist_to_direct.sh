#!/bin/bash
# Auto-transition: when oss120b_checklist hits 706 unique scenarios,
# kill checklist runners and redirect to oss120b_direct gap-fill.
# Freed endpoints: 144:30010/30011/30012, 145:30003/30005

RESULTS_DIR="results/ex_w8_crossmodel"
CHECKLIST_DIR="${RESULTS_DIR}/oss120b_checklist"
DIRECT_DIR="${RESULTS_DIR}/oss120b_direct"
TARGET=706
PYTHONPATH="${CGA_BENCH_ROOT}"
LOG="/tmp/auto_transition_checklist_to_direct.log"

log() { echo "[$(date +%H:%M:%S)] $1" | tee -a "$LOG"; }

log "Auto-transition monitor started (checklist -> direct)"
log "Watching oss120b_checklist for ${TARGET} unique scenarios"

while true; do
    # Count unique scenarios in checklist
    count=$(python3 -c "
import json, os, glob
d = '${CHECKLIST_DIR}'
files = glob.glob(os.path.join(d, '*.json'))
scenarios = set()
for f in files:
    bn = os.path.basename(f)
    if bn.startswith('checkpoint') or bn == 'model_summary.json': continue
    try:
        data = json.load(open(f))
        sid = data.get('scenario_id', '')
        if sid: scenarios.add(sid)
    except: pass
print(len(scenarios))
" 2>/dev/null)

    log "oss120b_checklist: ${count}/${TARGET} unique scenarios"

    if [ "$count" -ge "$TARGET" ]; then
        log "CHECKLIST COMPLETE! Transitioning to direct gap-fill..."

        # Check how many direct scenarios still needed
        direct_count=$(python3 -c "
import json, os, glob
d = '${DIRECT_DIR}'
files = glob.glob(os.path.join(d, '*.json'))
scenarios = set()
for f in files:
    bn = os.path.basename(f)
    if bn.startswith('checkpoint') or bn == 'model_summary.json': continue
    try:
        data = json.load(open(f))
        sid = data.get('scenario_id', '')
        if sid: scenarios.add(sid)
    except: pass
print(len(scenarios))
" 2>/dev/null)

        remaining=$((TARGET - direct_count))
        log "oss120b_direct: ${direct_count}/${TARGET} (${remaining} remaining)"

        if [ "$remaining" -le 0 ]; then
            log "Direct is also complete! No transition needed."
            break
        fi

        # Kill checklist runners
        log "Killing checklist runners..."
        pkill -f "shard_runner.py oss120b_checklist" || true
        sleep 5

        # Clean stale claim files in direct output
        log "Cleaning stale claim files in direct..."
        find "${DIRECT_DIR}" -name "*.claim" -mmin +10 -delete 2>/dev/null || true

        # Launch direct runners on freed endpoints
        # 144: 30010, 30011, 30012
        for port in 30010 30011 30012; do
            key="oss120b_direct_p${port#300}"
            log "Launching 3x ${key} on 144:${port}"
            for i in 1 2 3; do
                PYTHONPATH="${PYTHONPATH}" nohup python scripts/experiments/shard_runner.py \
                    "${key}" "${port}" "${RESULTS_DIR}" \
                    --host 127.0.0.1 --split all \
                    >> "/tmp/shard_direct_${key}_${i}.log" 2>&1 &
            done
        done

        # 145: 30003, 30005
        for port in 30003 30005; do
            key="oss120b_direct_145p${port}"
            log "Launching 3x ${key} on 145:${port}"
            for i in 1 2 3; do
                PYTHONPATH="${PYTHONPATH}" nohup python scripts/experiments/shard_runner.py \
                    "${key}" "${port}" "${RESULTS_DIR}" \
                    --host 127.0.0.1 --split all \
                    >> "/tmp/shard_direct_${key}_${i}.log" 2>&1 &
            done
        done

        log "Launched 15 direct runners on 5 endpoints"
        log "Combined with 9 existing direct runners = 24 total"
        log "Transition complete!"
        break
    fi

    sleep 120
done

log "Monitor exiting."
