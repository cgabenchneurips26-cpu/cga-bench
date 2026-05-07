> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# Episode Run Environment Report

**Date**: 2026-04-03

## 1. GPU Status (Local A100 x 8)

| GPU | Model | Port | Status |
|-----|-------|------|--------|
| 0-1 | openai/gpt-oss-120b (TP=2) | 28000 | SERVING |
| 2 | Qwen3.5-35B-A3B-FP8 | 8015 | SERVING |
| 3 | Qwen3.5-35B-A3B-FP8 | 8017 | SERVING (duplicate) |
| 4-5 | Qwen3.5-27B-FP8 | 28010 | SERVING |
| 6 | unknown | - | Occupied |
| 7 | Qwen3-4B-Instruct-2507 | 8101 | SERVING |

External: <external-gpu-host>:30001 (Qwen3.5-397B) — **CONNECTION FAILED** at time of check.

## 2. Existing Code Structure

| File | Role |
|------|------|
| `scripts/experiments/clean_slate_runner.py` | Core: model-specific runner, scenario iteration, checkpointing |
| `scripts/experiments/clean_slate_parallel.sh` | 4 models nohup parallel launcher |
| `scripts/experiments/launch_clean_slate.sh` | Alternative nohup launcher |
| `scripts/experiments/rescore_clean_slate.py` | Post-run rescoring |
| `run_benchmark.py` | Single scenario executor (needs cga_bench.* imports) |

Pattern: `clean_slate_runner.py MODEL_KEY` → iterates SCENARIOS × 3 runs → subprocess calls.

## 3. Existing Results

180 episodes (4 models × 15 scenarios × 3 runs) in results/clean_slate_rescored/

## 4. Execution Matrix (690 scenarios)

690 scenarios × 5 models × 3 runs = **10,350 episodes**

| Model | Port | Episodes | Est. Time |
|-------|------|----------|-----------|
| Qwen3.5-397B | ext:30001 | 2,070 | ~172h |
| gpt-oss-120b | 28000 | 2,070 | ~103h |
| Qwen3.5-35B | 8013/8015 | 2,070 | ~69h |
| Qwen3.5-27B | 28010 | 2,070 | ~69h |
| Qwen3-4B | 8101 | 2,070 | ~34h |

Wall-clock (4 local parallel): ~103h (4.3 days)
Wall-clock (+ 397B separate): ~172h (7.2 days)

## 5. Required Changes

1. clean_slate_runner.py SCENARIOS: 15 → 690
2. clean_slate_runner.py MODELS: add qwen397b
3. configs/agents/clean_slate_qwen397b.yaml: create
4. External server health check: <external-gpu-host>:30001
5. Port mismatch: clean_slate_qwen35b.yaml uses 8013 but model on 8015

## 6. Dry Run Commands

```bash
export PYTHONPATH=${CGA_BENCH_ROOT}
for model in oss120b qwen35b qwen27b qwen4b; do
  python scripts/experiments/clean_slate_runner.py $model --dry-run
done
```

## 7. Monitoring

```bash
watch -n 60 'for d in results/full_690/*/; do echo "$d: $(ls $d/*.json 2>/dev/null | wc -l)"; done'
tail -f results/full_690/log_*.txt | grep -i "error\|fail\|timeout"
watch -n 10 nvidia-smi
```
