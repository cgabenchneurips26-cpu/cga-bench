#!/usr/bin/env bash
# Quick progress check for v7.3 expanded benchmark run.
# Usage: bash scripts/infra/v73_expanded_progress.sh
set -euo pipefail

RESULTS_DIR="results/v73_expanded"
MODELS="qwen4b deepseek_r1_7b qwen27b qwen35b gemma31b nemotron30b qwen397b"
PER_MODEL=2040
NUM_MODELS=7
TARGET=$((PER_MODEL * NUM_MODELS))

echo "=== v7.3 Expanded Progress @ $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""

grand=0
for model in $MODELS; do
  alive=$(pgrep -f "full_v73_expanded_runner.py $model" | head -1 || true)
  if [ -n "$alive" ]; then status="ALIVE"; else status="DEAD "; fi
  count=$(find "${RESULTS_DIR}/${model}/" -name "*.json" -not -name "checkpoint*" 2>/dev/null | wc -l)
  pct=$(echo "scale=1; $count * 100 / $PER_MODEL" | bc)
  printf "[%s] %-15s %5d / %d  (%5.1f%%)\n" "$status" "$model" "$count" "$PER_MODEL" "$pct"
  grand=$((grand + count))
done

echo "---"
gpct=$(echo "scale=1; $grand * 100 / $TARGET" | bc)
printf "TOTAL: %d / %d  (%.1f%%)\n" "$grand" "$TARGET" "$gpct"

# Estimate completion based on oldest result file
first_file=$(find "${RESULTS_DIR}" -name "*.json" -not -name "checkpoint*" -printf '%T+ %p\n' 2>/dev/null | sort | head -1 | cut -d' ' -f2)
if [ -n "$first_file" ]; then
  start_epoch=$(stat -c %Y "$first_file" 2>/dev/null || echo 0)
  now_epoch=$(date +%s)
  elapsed_s=$((now_epoch - start_epoch))
  if [ "$elapsed_s" -gt 60 ] && [ "$grand" -gt 5 ]; then
    rate=$(echo "scale=0; $grand * 3600 / $elapsed_s" | bc)
    remain=$((TARGET - grand))
    eta_h=$(echo "scale=1; $remain / $rate" | bc)
    elapsed_h=$(echo "scale=1; $elapsed_s / 3600" | bc)
    echo "Rate: ~${rate} ep/h | Elapsed: ${elapsed_h}h | ETA: ~${eta_h}h remaining"
  fi
fi
