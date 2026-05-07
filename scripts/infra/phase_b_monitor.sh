#!/usr/bin/env bash
# Phase B live monitor — episodes per model, worker count, GPU utilisation.
#
# Usage:
#   bash scripts/infra/phase_b_monitor.sh           # one-shot
#   watch -n 30 'bash scripts/infra/phase_b_monitor.sh'   # continuous

set -uo pipefail

ROOT=/home/anonymous-org/anonymous-project/AnonProject/cga_bench
OUTPUT_145=/home/anonymous-org/results/full_v6b
OUTPUT_146=/home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/full_v6b
TARGET=9558

printf "=== Phase B Status @ %s ===\n\n" "$(date '+%F %T %Z')"

printf "%-16s %8s %8s %5s %s\n" "MODEL" "EPS" "TARGET" "PCT" "WORKERS"
total_eps=0; total_workers=0
for m in qwen4b qwen27b qwen35b oss120b deepseek_r1_7b gemma31b; do
  eps=$(sudo -n -u anonymous-org ssh -o ConnectTimeout=3 127.0.0.1 \
    "find $OUTPUT_145/$m -maxdepth 1 -name '*.json' 2>/dev/null | wc -l" 2>/dev/null)
  eps=${eps:-0}
  workers=$(sudo -n -u anonymous-org ssh -o ConnectTimeout=3 127.0.0.1 \
    "ps aux | grep 'full_690_runner.py $m ' | grep -v grep | wc -l" 2>/dev/null)
  workers=${workers:-0}
  pct=$(( 100 * eps / TARGET ))
  printf "%-16s %8d %8d %4d%% %d (145)\n" "$m" "$eps" "$TARGET" "$pct" "$workers"
  total_eps=$(( total_eps + eps ))
  total_workers=$(( total_workers + workers ))
done
OUTPUT_144=/home/anonymous-user/cga_bench/results/full_v6b
for m in qwen397b nemotron30b; do
  eps_146=$(find $OUTPUT_146/$m -maxdepth 1 -name '*.json' 2>/dev/null | wc -l)
  eps_144=$(sudo -n -u anonymous-org ssh -o ConnectTimeout=3 [email-redacted] \
    "find $OUTPUT_144/$m -maxdepth 1 -name '*.json' 2>/dev/null | wc -l" 2>/dev/null)
  eps_144=${eps_144:-0}
  # Take the max — 144 is now ground-truth (workers migrated 15:40 UTC)
  eps=$(( eps_146 > eps_144 ? eps_146 : eps_144 ))
  workers=$(sudo -n -u anonymous-org ssh -o ConnectTimeout=3 [email-redacted] \
    "ps aux | grep 'full_690_runner.py $m ' | grep -v grep | wc -l" 2>/dev/null)
  workers=${workers:-0}
  pct=$(( 100 * eps / TARGET ))
  printf "%-16s %8d %8d %4d%% %d (144 co-located, 146=%d 144=%d)\n" "$m" "$eps" "$TARGET" "$pct" "$workers" "$eps_146" "$eps_144"
  total_eps=$(( total_eps + eps ))
  total_workers=$(( total_workers + workers ))
done

target_total=$(( 8 * TARGET ))
total_pct=$(( 100 * total_eps / target_total ))
printf "%-16s %8d %8d %4d%% %d total\n" "==TOTAL==" "$total_eps" "$target_total" "$total_pct" "$total_workers"

printf "\n--- 145 GPU ---\n"
sudo -n -u anonymous-org ssh -o ConnectTimeout=3 127.0.0.1 \
  "nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader,nounits" 2>/dev/null

printf "\n--- 144 GPU ---\n"
sudo -n -u anonymous-org ssh -o ConnectTimeout=3 [email-redacted] \
  "nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader,nounits" 2>/dev/null
