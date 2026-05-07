#!/bin/bash
# Full-scale benchmark execution with auto Round 2 launch
# Usage: bash scripts/run_all_benchmarks.sh
set -euo pipefail

cd "$(dirname "$0")/.."
export VLLM_URL=http://localhost:8013/v1
export VLLM_MODEL=Qwen/Qwen3.5-35B-A3B-FP8
export PYTHONPATH=.

AC_PID=$(cat logs/agentclinic.pid 2>/dev/null || echo "0")
MAB_PID=$(cat logs/medagentbench.pid 2>/dev/null || echo "0")

echo "$(date '+%H:%M:%S') Round 1 already running: AC=$AC_PID MAB=$MAB_PID"
echo "$(date '+%H:%M:%S') Waiting for Round 1 to finish..."

# Wait for Round 1
while kill -0 "$AC_PID" 2>/dev/null || kill -0 "$MAB_PID" 2>/dev/null; do
    AC_DONE=$(python3 -c "import json; d=json.load(open('results/agentclinic_full_321.json')); print(len(d.get('results',[])))" 2>/dev/null || echo "?")
    MAB_DONE=$(python3 -c "import json; d=json.load(open('results/medagentbench_full_300.json')); print(len(d.get('results',[])))" 2>/dev/null || echo "?")
    AC_ALIVE=$(kill -0 "$AC_PID" 2>/dev/null && echo "RUN" || echo "DONE")
    MAB_ALIVE=$(kill -0 "$MAB_PID" 2>/dev/null && echo "RUN" || echo "DONE")
    echo "$(date '+%H:%M:%S') AC=$AC_DONE/321[$AC_ALIVE]  MAB=$MAB_DONE/300[$MAB_ALIVE]"
    sleep 60
done

echo ""
echo "$(date '+%H:%M:%S') ========== Round 1 COMPLETE =========="

# Show Round 1 results
for f in results/agentclinic_full_321.json results/medagentbench_full_300.json; do
    python3 -c "
import json
d = json.load(open('$f'))
r = d.get('results', [])
s = d.get('summary', {})
failed = d.get('failed_scenario_ids', [])
print(f'  $f: {len(r)} done, {len(failed)} failed, coverage={s.get(\"avg_action_coverage\",0):.1%}')
" 2>/dev/null || echo "  $f: not found"
done

echo ""
echo "$(date '+%H:%M:%S') ========== Launching Round 2 =========="

# Round 2: MedChain (1216) || HealthBench (1000)
nohup python run_external_benchmark.py \
  --benchmark medchain \
  --agent rag_vllm \
  --limit 12163 \
  --sample-indices evidence_pack/sampling/medchain_sample_indices.json \
  --save-every 50 \
  --episode-timeout 300 \
  --output results/medchain_sample_1216.json \
  > logs/medchain_sample.log 2>&1 &
echo $! > logs/medchain.pid
MC_PID=$!
echo "$(date '+%H:%M:%S') MedChain launched: PID=$MC_PID"

nohup python scripts/e2e_healthbench.py \
  --sample-indices evidence_pack/sampling/healthbench_sample_indices.json \
  --save-every 20 \
  --output results/healthbench_sample_1000.json \
  --endpoint http://localhost:8013/v1 \
  > logs/healthbench_1000.log 2>&1 &
echo $! > logs/healthbench.pid
HB_PID=$!
echo "$(date '+%H:%M:%S') HealthBench launched: PID=$HB_PID"

echo ""
echo "$(date '+%H:%M:%S') Round 2 running. Monitor with:"
echo "  tail -f logs/medchain_sample.log"
echo "  tail -f logs/healthbench_1000.log"

# Wait for Round 2
while kill -0 "$MC_PID" 2>/dev/null || kill -0 "$HB_PID" 2>/dev/null; do
    MC_DONE=$(python3 -c "import json; d=json.load(open('results/medchain_sample_1216.json')); print(len(d.get('results',[])))" 2>/dev/null || echo "?")
    HB_DONE=$(python3 -c "import json; d=json.load(open('results/healthbench_sample_1000.json')); print(len(d))" 2>/dev/null || echo "?")
    MC_ALIVE=$(kill -0 "$MC_PID" 2>/dev/null && echo "RUN" || echo "DONE")
    HB_ALIVE=$(kill -0 "$HB_PID" 2>/dev/null && echo "RUN" || echo "DONE")
    echo "$(date '+%H:%M:%S') MC=$MC_DONE/1216[$MC_ALIVE]  HB=$HB_DONE/1000[$HB_ALIVE]"
    sleep 60
done

echo ""
echo "$(date '+%H:%M:%S') ========== Round 2 COMPLETE =========="
echo "$(date '+%H:%M:%S') ========== ALL BENCHMARKS DONE =========="

# Final summary
echo ""
echo "Final Results:"
for f in results/agentclinic_full_321.json results/medagentbench_full_300.json results/medchain_sample_1216.json; do
    python3 -c "
import json
d = json.load(open('$f'))
r = d.get('results', [])
failed = d.get('failed_scenario_ids', [])
print(f'  $f: {len(r)} completed, {len(failed)} failed')
" 2>/dev/null || echo "  $f: not found"
done

python3 -c "
import json
d = json.load(open('results/healthbench_sample_1000.json'))
print(f'  results/healthbench_sample_1000.json: {len(d)} completed')
" 2>/dev/null || echo "  results/healthbench_sample_1000.json: not found"
