#!/bin/bash
# Model swap: after oss120b completes all 4 scaffolds,
# swap GPU containers for qwen35b (38+1 scenarios) and gemma31b (1 scenario).
#
# Server 144 (anonymous-user): stop oss120b GPU 4-7, start qwen35b GPU 4-7
# Server 145 (anonymous-org): stop oss120b GPU 0-1, start gemma31b GPU 0

set -e
SSH_KEY="/tmp/anonymous-org_key"
SSH_144="ssh -i $SSH_KEY -o StrictHostKeyChecking=no [email-redacted]"
SSH_145="ssh -i $SSH_KEY -o StrictHostKeyChecking=no [email-redacted]"
RESULTS_DIR="results/ex_w8_crossmodel"
PYTHONPATH="${CGA_BENCH_ROOT}"
LOG="/tmp/model_swap.log"

log() { echo "[$(date +%H:%M:%S)] $1" | tee -a "$LOG"; }

# ---- Step 0: Verify oss120b completion ----
log "=== MODEL SWAP SCRIPT ==="
log "Step 0: Verifying oss120b completion..."

for scaffold in oss120b_react oss120b_direct oss120b_checklist oss120b_tooluse; do
    count=$(python3 -c "
import json, glob, os
d = '${RESULTS_DIR}/${scaffold}'
scenarios = set()
for f in glob.glob(os.path.join(d, '*.json')):
    bn = os.path.basename(f)
    if bn.startswith('checkpoint') or bn == 'model_summary.json': continue
    try:
        data = json.load(open(f))
        sid = data.get('scenario_id', '')
        if sid: scenarios.add(sid)
    except: pass
print(len(scenarios))
" 2>/dev/null)
    log "  ${scaffold}: ${count}/706"
    if [ "$count" -lt 706 ]; then
        log "ERROR: ${scaffold} not complete (${count}/706). Aborting."
        exit 1
    fi
done
log "All oss120b scaffolds verified complete."

# ---- Step 1: Kill all remaining oss120b runners ----
log "Step 1: Killing remaining oss120b runners..."
pkill -f "shard_runner.py oss120b" || true
sleep 3
remaining=$(pgrep -f "shard_runner.py oss120b" | wc -l)
log "  Remaining oss120b runners: ${remaining}"

# ---- Step 2: Swap containers on 144 (qwen35b) ----
log "Step 2: Container swap on 144 (qwen35b)..."

# Stop oss120b containers using GPU 4-7
log "  Stopping oss120b-amega (GPU 4-5) and oss120b-accel-67 (GPU 6-7)..."
$SSH_144 "docker stop oss120b-amega oss120b-accel-67" 2>&1 | while read line; do log "  144: $line"; done

# Start qwen35b containers (already configured, just need docker start)
log "  Starting qwen35b containers (GPU 4-7, ports 8013-8016)..."
$SSH_144 "docker start qwen35-35b-gpu4 qwen35-35b-gpu5 qwen35-35b-gpu6 qwen35-35b-gpu7" 2>&1 | while read line; do log "  144: $line"; done

# ---- Step 3: Swap container on 145 (gemma31b) ----
log "Step 3: Container swap on 145 (gemma31b)..."

# Stop one oss120b container to free GPU 0-1
log "  Stopping oss120b-145-01 (GPU 0-1, port 30003)..."
$SSH_145 "docker stop oss120b-145-01" 2>&1 | while read line; do log "  145: $line"; done

# Create gemma31b container on GPU 0, port 30003
log "  Creating gemma31b container on GPU 0, port 30003..."
$SSH_145 "docker run -d --name gemma31b-react-fill \
    --gpus '\"device=0\"' \
    -p 30003:8000 \
    -v /home/anonymous-org/.cache/huggingface:/root/.cache/huggingface \
    vllm/vllm-openai:gemma4 \
    --model google/gemma-4-31b-it \
    --tensor-parallel-size 1 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.9 \
    --api-key not_needed \
    --trust-remote-code \
    --enforce-eager" 2>&1 | while read line; do log "  145: $line"; done

# ---- Step 4: Wait for endpoints to be ready ----
log "Step 4: Waiting for endpoints to become healthy..."

wait_for_endpoint() {
    local host=$1
    local port=$2
    local name=$3
    local max_wait=300  # 5 min
    local elapsed=0
    while [ $elapsed -lt $max_wait ]; do
        if curl -s --max-time 5 "http://${host}:${port}/v1/models" >/dev/null 2>&1; then
            log "  ${name} (${host}:${port}) is READY"
            return 0
        fi
        sleep 10
        elapsed=$((elapsed + 10))
        log "  Waiting for ${name} (${host}:${port})... ${elapsed}s"
    done
    log "  WARNING: ${name} (${host}:${port}) not ready after ${max_wait}s"
    return 1
}

# Wait for qwen35b endpoints (144:8013-8016)
for port in 8013 8014 8015 8016; do
    wait_for_endpoint 127.0.0.1 $port "qwen35b-gpu$((port-8009))" &
done

# Wait for gemma31b endpoint (145:30003)
wait_for_endpoint 127.0.0.1 30003 "gemma31b" &

wait
log "All endpoints checked."

# ---- Step 5: Launch gap-fill runners ----
log "Step 5: Launching gap-fill runners..."

# qwen35b react (38 missing) - 4 endpoints × 3 runners = 12 runners
for port in 8013 8014 8015 8016; do
    key="qwen35b_react_p$((port-8000))"
    log "  Launching 3x ${key} on 144:${port}"
    for i in 1 2 3; do
        PYTHONPATH="${PYTHONPATH}" nohup python scripts/experiments/shard_runner.py \
            "${key}" "${port}" "${RESULTS_DIR}" \
            --host 127.0.0.1 --split all \
            >> "/tmp/shard_${key}_${i}.log" 2>&1 &
    done
done

# qwen35b direct (1 missing) - 1 endpoint × 1 runner
log "  Launching 1x qwen35b_direct_p13 on 144:8013"
PYTHONPATH="${PYTHONPATH}" nohup python scripts/experiments/shard_runner.py \
    qwen35b_direct_p13 8013 "${RESULTS_DIR}" \
    --host 127.0.0.1 --split all \
    >> "/tmp/shard_qwen35b_direct_p13.log" 2>&1 &

# gemma31b react (1 missing) - 1 endpoint × 1 runner
log "  Launching 1x gemma31b_react_p03 on 145:30003"
PYTHONPATH="${PYTHONPATH}" nohup python scripts/experiments/shard_runner.py \
    gemma31b_react_p03 30003 "${RESULTS_DIR}" \
    --host 127.0.0.1 --split all \
    >> "/tmp/shard_gemma31b_react_p03.log" 2>&1 &

log "Launched 14 runners total (12 qwen35b_react + 1 qwen35b_direct + 1 gemma31b_react)"

# ---- Step 6: Monitor completion ----
log "Step 6: Monitoring gap-fill completion..."

while true; do
    qr=$(python3 -c "
import json, glob, os
d1 = '${RESULTS_DIR}/qwen35b_react'
d2 = '${RESULTS_DIR}/qwen35b_react_s2'
s = set()
for d in [d1, d2]:
    if not os.path.isdir(d): continue
    for f in glob.glob(os.path.join(d, '*.json')):
        bn = os.path.basename(f)
        if bn.startswith('checkpoint') or bn == 'model_summary.json': continue
        try:
            data = json.load(open(f))
            sid = data.get('scenario_id', '')
            if sid: s.add(sid)
        except: pass
print(len(s))
" 2>/dev/null)

    qd=$(python3 -c "
import json, glob, os
d = '${RESULTS_DIR}/qwen35b_direct'
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
" 2>/dev/null)

    gr=$(python3 -c "
import json, glob, os
d = '${RESULTS_DIR}/gemma31b_react'
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
" 2>/dev/null)

    log "  qwen35b_react: ${qr}/706 | qwen35b_direct: ${qd}/706 | gemma31b_react: ${gr}/706"

    if [ "$qr" -ge 706 ] && [ "$qd" -ge 706 ] && [ "$gr" -ge 706 ]; then
        log "ALL W8 TRACKS COMPLETE!"
        log "=== MODEL SWAP FINISHED ==="
        break
    fi

    sleep 120
done
