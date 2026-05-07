#!/usr/bin/env bash
# v73_progress.sh — Quick progress dashboard for v7.3 SGSC experiment
# Usage: bash scripts/infra/v73_progress.sh [--watch]
set -euo pipefail

BENCH="/home/anonymous-org/anonymous-project/AnonProject/cga_bench"
RESULTS="${BENCH}/results/v73_full"

show_progress() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') — v7.3 SGSC Experiment Progress"
    echo "========================================================================"

    python3 -c "
import json, os, glob

TARGET = 627  # per shard: 209 scenarios × 3 runs
models = ['qwen397b','qwen4b','deepseek_r1_7b','qwen27b','gemma31b','nemotron30b']

print(f'{\"Model\":<16} {\"S1\":>8} {\"S2\":>8} {\"Files\":>7} {\"Progress\":>10}')
print('-' * 55)

total_s1 = total_s2 = total_f = 0
for m in models:
    d = '${RESULTS}/' + m
    s1 = s2 = 0
    for shard, var in [('s1of2', 's1'), ('s2of2', 's2')]:
        try:
            data = json.load(open(f'{d}/checkpoint_{shard}.json'))
            val = data.get('count', len(data.get('completed', [])))
            exec(f'{var} = {val}')
        except: pass

    files = len([f for f in os.listdir(d) if f.endswith('.json') and not f.startswith('checkpoint') and f != 'model_summary.json']) if os.path.isdir(d) else 0
    pct = (s1 + s2) / (TARGET * 2) * 100
    bar = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
    print(f'{m:<16} {s1:>5}/{TARGET} {s2:>5}/{TARGET} {files:>7} {pct:>5.1f}% {bar}')
    total_s1 += s1; total_s2 += s2; total_f += files

print('-' * 55)
total_pct = (total_s1 + total_s2) / (TARGET * 2 * len(models)) * 100
print(f'{\"TOTAL\":<16} {total_s1:>5}    {total_s2:>5}    {total_f:>7} {total_pct:>5.1f}%')
print(f'Target: 6 models × 1254 episodes = 7,524 total')
" 2>/dev/null

    echo ""
    echo "Workers:"
    s1=$(ps aux | grep 'full_v73_runner' | grep 'shard 1/2' | grep -v grep | wc -l)
    s2=$(ps aux | grep 'full_v73_runner' | grep 'shard 2/2' | grep -v grep | wc -l)
    echo "  Shard 1/2: ${s1} workers | Shard 2/2: ${s2} workers | Total: $((s1 + s2))"
    echo ""
}

if [ "${1:-}" = "--watch" ]; then
    while true; do
        clear
        show_progress
        sleep 60
    done
else
    show_progress
fi
