# Expansion v7 Runner State — 2026-04-23 09:20 UTC

## Overview
Expansion v7 runs **new CPG guidelines** (auto-generated, beyond core-20 + held-out-5) across multiple models.
Results dir: `results/expansion_v7/{model_key}/`

## Architecture Change (this session)
- **Before**: All 10 runners on 146 → vLLM servers on 144/145 via network
- **After**: 5 runners on 145 (localhost to 145 vLLM) + 5 runners on 146
- **Reason**: vLLM `waiting=0` everywhere — CPU-side bottleneck (RAG doc loading 868 docs, JSON parse, scoring), not GPU. Moving runners to 145 eliminates network latency and distributes CPU load.

## 145 Runners (5) — run ON 145 server
Code location: `/home/anonymous-org/bench_ws/cga_bench/`
PYTHONPATH: `/home/anonymous-org/bench_ws:/home/anonymous-org/bench_ws/cga_bench`
Results: `/home/anonymous-org/bench_ws/cga_bench/results/expansion_v7/`

| Model Key | vLLM Port | Workers | Log |
|-----------|-----------|---------|-----|
| oss120b | localhost:30005 | 20 | /tmp/exp_oss120b.log |
| oss120b_exp2 | localhost:30015 | 20 | /tmp/exp_oss120b_exp2.log |
| oss120b_exp3 | localhost:30025 | 20 | /tmp/exp_oss120b_exp3.log |
| deepseek_r1_7b_exp1 | localhost:30039 | 40 | /tmp/exp_deepseek_exp1.log |
| deepseek_r1_7b_exp2 | localhost:30049 | 40 | /tmp/exp_deepseek_exp2.log |

### How to restart 145 runners
```bash
ssh -i /tmp/anonymous-org_key [email-redacted] '
cd /home/anonymous-org/bench_ws/cga_bench
export PYTHONPATH=/home/anonymous-org/bench_ws:/home/anonymous-org/bench_ws/cga_bench

nohup /home/anonymous-org/anaconda3/bin/python3 scripts/experiments/expansion_runner.py oss120b --host localhost --port 30005 --workers 20 --output-dir results/expansion_v7 > /tmp/exp_oss120b.log 2>&1 &
nohup /home/anonymous-org/anaconda3/bin/python3 scripts/experiments/expansion_runner.py oss120b_exp2 --host localhost --port 30015 --workers 20 --output-dir results/expansion_v7 > /tmp/exp_oss120b_exp2.log 2>&1 &
nohup /home/anonymous-org/anaconda3/bin/python3 scripts/experiments/expansion_runner.py oss120b_exp3 --host localhost --port 30025 --workers 20 --output-dir results/expansion_v7 > /tmp/exp_oss120b_exp3.log 2>&1 &
nohup /home/anonymous-org/anaconda3/bin/python3 scripts/experiments/expansion_runner.py deepseek_r1_7b_exp1 --host localhost --port 30039 --workers 40 --output-dir results/expansion_v7 > /tmp/exp_deepseek_exp1.log 2>&1 &
nohup /home/anonymous-org/anaconda3/bin/python3 scripts/experiments/expansion_runner.py deepseek_r1_7b_exp2 --host localhost --port 30049 --workers 40 --output-dir results/expansion_v7 > /tmp/exp_deepseek_exp2.log 2>&1 &
'
```

### How to check 145 runner status
```bash
ssh -i /tmp/anonymous-org_key [email-redacted] '
ps aux | grep expansion_runner | grep -v grep
for f in /tmp/exp_oss120b.log /tmp/exp_oss120b_exp2.log /tmp/exp_oss120b_exp3.log /tmp/exp_deepseek_exp1.log /tmp/exp_deepseek_exp2.log; do
    name=$(basename "$f" .log | sed "s/exp_//")
    prog=$(grep "Progress:" "$f" 2>/dev/null | tail -1)
    echo "$name: $prog"
done
'
```

### How to rsync results BACK from 145 to 146
```bash
# Run from 146
for model in oss120b oss120b_exp2 oss120b_exp3 deepseek_r1_7b_exp1 deepseek_r1_7b_exp2; do
  rsync -az \
    -e "ssh -i /tmp/anonymous-org_key" \
    [email-redacted]:/home/anonymous-org/bench_ws/cga_bench/results/expansion_v7/$model/ \
    /home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/expansion_v7/$model/
done
```

## 146 Runners (5) — run on 146 (local machine)
Results: `/home/anonymous-org/anonymous-project/AnonProject/cga_bench/results/expansion_v7/`

| Model Key | vLLM Endpoint | Workers | Log |
|-----------|---------------|---------|-----|
| qwen397b | 127.0.0.1 | 12 | /tmp/exp_qwen397b.log |
| qwen397b_react_s2 | 127.0.0.1 | 12 | /tmp/exp_qwen397b_s2.log |
| qwen35b_a3b_local | localhost:28003 | 24 | /tmp/exp_qwen35b.log |
| deepseek_r1_7b_local1 | localhost:30059 | 40 | /tmp/exp_deepseek_local1.log |
| deepseek_r1_7b_local2 | localhost:30069 | 40 | /tmp/exp_deepseek_local2.log |

### How to restart 146 runners
```bash
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench
nohup env PYTHONPATH=. python3 scripts/experiments/expansion_runner.py qwen397b --host 127.0.0.1 --port 30001 --workers 12 --output-dir results/expansion_v7 > /tmp/exp_qwen397b.log 2>&1 &
nohup env PYTHONPATH=. python3 scripts/experiments/expansion_runner.py qwen397b_react_s2 --host 127.0.0.1 --port 30002 --workers 12 --output-dir results/expansion_v7 > /tmp/exp_qwen397b_s2.log 2>&1 &
nohup env PYTHONPATH=. python3 scripts/experiments/expansion_runner.py qwen35b_a3b_local --host localhost --port 28003 --workers 24 --output-dir results/expansion_v7 > /tmp/exp_qwen35b.log 2>&1 &
nohup env PYTHONPATH=. python3 scripts/experiments/expansion_runner.py deepseek_r1_7b_local1 --host localhost --port 30059 --workers 40 --output-dir results/expansion_v7 > /tmp/exp_deepseek_local1.log 2>&1 &
nohup env PYTHONPATH=. python3 scripts/experiments/expansion_runner.py deepseek_r1_7b_local2 --host localhost --port 30069 --workers 40 --output-dir results/expansion_v7 > /tmp/exp_deepseek_local2.log 2>&1 &
```

## Dedup Strategy
- Each model_key has its own subdirectory + checkpoint.json
- No overlap between 145 and 146 model_key sets
- Checkpoint tracks completed scenario_ids — restart automatically skips done ones
- "skip" count = scenarios already completed in prior runs (v6 scaffolds or earlier expansion batches)

## vLLM Server Map (unchanged)
| Server | Port | Model | TP | GPUs |
|--------|------|-------|----|------|
| 144 | 30001 | Qwen3.5-397B-A17B-FP8 | 4 | 0-3 |
| 144 | 30002 | Qwen3.5-397B-A17B-FP8 | 4 | 4-7 |
| 145 | 30005 | openai/gpt-oss-120b | 2 | 0-1 |
| 145 | 30015 | openai/gpt-oss-120b | 2 | 2-3 |
| 145 | 30025 | openai/gpt-oss-120b | 2 | 4-5 |
| 145 | 30039 | DeepSeek-R1-Distill-Qwen-7B | 1 | 6 |
| 145 | 30049 | DeepSeek-R1-Distill-Qwen-7B | 1 | 7 |
| 146 | 28003 | Qwen3.5-35B-A3B | 1 | GPU 2 |
| 146 | 30059 | DeepSeek-R1-Distill-Qwen-7B | 1 | GPU 6 |
| 146 | 30069 | DeepSeek-R1-Distill-Qwen-7B | 1 | GPU 7 |

## Worker Sizing Rationale
- oss120b (>=70B): 10 → **20** (vLLM was starved at 10)
- deepseek (7B): 20 → **40** (light model, high concurrency)
- qwen397b (>=200B): 6 → **12** (slow model but vLLM had headroom)
- qwen35b_a3b (35B): 12 → **24** (was only 3 running requests)

## Post-completion Checklist
1. rsync 145 results back to 146 (see command above)
2. Verify episode counts per model_key match target (~560-680 new scenarios × 3 runs)
3. Merge with existing v6 scaffold results for analysis
