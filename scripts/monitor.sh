#!/bin/bash
# Usage: bash scripts/monitor.sh         (one-shot)
#        watch -n 60 bash scripts/monitor.sh  (continuous)
cd "$(dirname "$0")/.."

echo "=== $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""

# Round 1
echo "Round 1 (COMPLETE):"
for f in results/agentclinic_full_321.json results/medagentbench_full_300.json; do
  [ -f "$f" ] && python3 -c "
import json; d=json.load(open('$f'))
r=d.get('results',[]); fl=d.get('failed_scenario_ids',[])
s=d.get('summary',{})
print(f'  $(basename $f): {len(r)} done, {len(fl)} fail, cov={s.get(\"avg_action_coverage\",0):.1%}')
" 2>/dev/null || echo "  $f: missing"
done

echo ""
echo "Round 2 (RUNNING):"

# MedChain shard1
if [ -f results/medchain_sample_1216.json ]; then
  python3 -c "import json;d=json.load(open('results/medchain_sample_1216.json'));r=d.get('results',[]);fl=d.get('failed_scenario_ids',[]);print(f'  MC-shard1: {len(r)}/608 done, {len(fl)} fail')" 2>/dev/null
else
  echo "  MC-shard1: $(grep -c 'Actions:' logs/medchain_sample.log 2>/dev/null || echo 0) (log)"
fi

# MedChain shard2
if [ -f results/medchain_shard2_608.json ]; then
  python3 -c "import json;d=json.load(open('results/medchain_shard2_608.json'));r=d.get('results',[]);fl=d.get('failed_scenario_ids',[]);print(f'  MC-shard2: {len(r)}/608 done, {len(fl)} fail')" 2>/dev/null
else
  echo "  MC-shard2: $(grep -c 'Actions:' logs/medchain_shard2.log 2>/dev/null || echo 0) (log)"
fi

# HealthBench
if [ -f results/healthbench_sample_1000.json ]; then
  python3 -c "import json;d=json.load(open('results/healthbench_sample_1000.json'));print(f'  HealthBench: {len(d)}/1000 done')" 2>/dev/null
else
  echo "  HealthBench: $(grep -c 'Rubric Track A:' logs/healthbench_1000.log 2>/dev/null || echo 0) (log)"
fi

echo ""
echo "Processes:"
for name_pid in "MC1:$(cat logs/medchain.pid 2>/dev/null)" "MC2:$(cat logs/medchain_shard2.pid 2>/dev/null)" "HB:$(cat logs/healthbench.pid 2>/dev/null)"; do
  name=${name_pid%%:*}; pid=${name_pid##*:}
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && echo "  $name (PID $pid): RUNNING" || echo "  $name: STOPPED"
done

echo ""
echo "GPU:"
nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader 2>/dev/null
