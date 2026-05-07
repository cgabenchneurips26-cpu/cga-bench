#!/bin/bash
# Clean Slate Parallel Runner
# Launches 4 model runs in parallel background processes
# Usage: bash scripts/experiments/clean_slate_parallel.sh

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTDIR="results/clean_slate_${TIMESTAMP}"
mkdir -p "$OUTDIR"

echo "============================================"
echo "Clean Slate Parallel Experiment"
echo "Output: $OUTDIR"
echo "Time: $(date)"
echo "============================================"

# Health check all models
echo "Health checking models..."
for port in 28000 8013 28010 8101; do
    if curl -s --connect-timeout 3 http://localhost:$port/v1/models -H "Authorization: Bearer sk-no-key-required" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        echo "  Port $port: OK"
    else
        echo "  Port $port: FAILED - aborting"
        exit 1
    fi
done

cd ${CGA_BENCH_ROOT}/cga_bench
export PYTHONPATH=${CGA_BENCH_ROOT}
PYTHON=/home/anonymous-org/anaconda3/bin/python3.13

# Launch each model in parallel
echo ""
echo "Launching 4 models in parallel..."

$PYTHON scripts/experiments/clean_slate_runner.py oss120b \
    > "$OUTDIR/log_oss120b.txt" 2>&1 &
PID1=$!
echo "  oss120b: PID $PID1"

$PYTHON scripts/experiments/clean_slate_runner.py qwen35b \
    > "$OUTDIR/log_qwen35b.txt" 2>&1 &
PID2=$!
echo "  qwen35b: PID $PID2"

$PYTHON scripts/experiments/clean_slate_runner.py qwen27b \
    > "$OUTDIR/log_qwen27b.txt" 2>&1 &
PID3=$!
echo "  qwen27b: PID $PID3"

$PYTHON scripts/experiments/clean_slate_runner.py qwen4b \
    > "$OUTDIR/log_qwen4b.txt" 2>&1 &
PID4=$!
echo "  qwen4b: PID $PID4"

echo ""
echo "All launched. PIDs: $PID1 $PID2 $PID3 $PID4"
echo "Monitor: tail -f $OUTDIR/log_*.txt"
echo ""

# Wait for all
echo "Waiting for completion..."
wait $PID1; echo "  oss120b: exit $?"
wait $PID2; echo "  qwen35b: exit $?"
wait $PID3; echo "  qwen27b: exit $?"
wait $PID4; echo "  qwen4b: exit $?"

echo ""
echo "============================================"
echo "All models complete at $(date)"
echo "Results in: $OUTDIR"
echo "============================================"

# Quick summary
for model in oss120b qwen35b qwen27b qwen4b; do
    if [ -f "$OUTDIR/$model/model_summary.json" ]; then
        echo "  $model: $(cat $OUTDIR/$model/model_summary.json | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f"{d[\"total_episodes\"]}/{d[\"expected_episodes\"]} episodes, CGA mean={d.get(\"cga_mean\",\"N/A\")}")')"
    else
        echo "  $model: NO SUMMARY (check logs)"
    fi
done
