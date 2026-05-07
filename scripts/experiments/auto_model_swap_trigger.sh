#!/bin/bash
# Monitors oss120b completion across all 4 scaffolds.
# When all hit 706/706, triggers model_swap_after_oss120b.sh

RESULTS_DIR="results/ex_w8_crossmodel"
LOG="/tmp/auto_model_swap_trigger.log"

log() { echo "[$(date +%H:%M:%S)] $1" | tee -a "$LOG"; }

count_unique() {
    python3 -c "
import json, glob, os
d = '${RESULTS_DIR}/$1'
s = set()
for f in glob.glob(os.path.join(d, '*.json')):
    bn = os.path.basename(f)
    if bn.startswith('checkpoint') or bn == 'model_summary.json': continue
    try:
        data = json.load(open(f))
        sid = data.get('scenario_id', '')
        if sid: s.add(sid)
    except: pass
print(len(s))
" 2>/dev/null
}

log "Auto model-swap trigger started"
log "Waiting for all oss120b scaffolds to reach 706/706..."

while true; do
    r=$(count_unique oss120b_react)
    d=$(count_unique oss120b_direct)
    c=$(count_unique oss120b_checklist)
    t=$(count_unique oss120b_tooluse)
    log "react=${r} direct=${d} checklist=${c} tooluse=${t}"

    if [ "$r" -ge 706 ] && [ "$d" -ge 706 ] && [ "$c" -ge 706 ] && [ "$t" -ge 706 ]; then
        log "ALL OSS120B SCAFFOLDS COMPLETE! Triggering model swap..."
        bash scripts/experiments/model_swap_after_oss120b.sh 2>&1 | tee -a "$LOG"
        break
    fi

    sleep 300
done

log "Auto model-swap trigger exiting."
