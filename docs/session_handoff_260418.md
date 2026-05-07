# Session Handoff — 2026-04-18 00:45 UTC

## Last Commit
- **Hash**: `a5b63bc4` on `eval_science`
- **Content**: EX-D1 projection ablation + W8 infra + paper edits P1-P9 (28 files, 443K+ insertions)

## What Was Completed This Session
1. **Git commit** of all pending work (EX-D1, W8 configs, P1-P9 paper edits)
2. **Experiment analysis** (EX-37/38/39/D1/HealthBench) — all results verified
3. **Background experiments ALL finished**:
   - Temp sweep: 8/8 (4 qwen35b + 4 gemma31b)
   - AMEGA: 9/9 (3 models x 3 runs x 24 scenarios)
   - HealthBench: 800/800 (gemma 2x200 + qwen 2x200)
   - Regression tests: 469 passed

## What Needs To Be Done Next (Ordered by Priority)

### 1. W8 Cross-Model GPU Runs (URGENT — GPUs idle)
**All 10 endpoints are UP but returning empty model lists** — containers likely need restart.

| Endpoint | Model | Docker Container | GPU |
|----------|-------|-----------------|-----|
| 144:8017 | Qwen3.5-35B TP=1 | (check docker ps) | GPU 0 |
| 144:8018 | Qwen3.5-35B TP=1 | (check docker ps) | GPU 1 |
| 144:8019 | Qwen3.5-35B TP=1 | (check docker ps) | GPU 2 |
| 144:8020 | Qwen3.5-35B TP=1 | (check docker ps) | GPU 3 |
| 144:30008 | oss120b TP=2 | oss120b-amega | GPU 4-5 |
| 144:30009 | Qwen3.5-35B TP=2 | qwen35b-amega | GPU 6-7 |
| 145:30003 | gemma-4-31b TP=2 | (check) | GPU 0-1 |
| 145:30005 | gemma-4-31b TP=2 | (check) | GPU 4-5 |
| 145:30006 | gemma-4-31b TP=2 | (check) | GPU 2-3 |
| 145:30007 | gemma-4-31b TP=2 | (check) | GPU 6-7 |

**W8 schedule** (3 models x 3 scaffolds = 9 cells, ~500 episodes each):
```
qwen35b:  8017→react, 8018→direct, 8019→checklist
oss120b:  30008→react, 30008→direct(chain), 30008→checklist(chain)
gemma31b: 145:30003→react, 145:30003→direct(chain), 145:30003→checklist(chain)
```

**Chain launcher**: `scripts/experiments/chain_w8_crossmodel.sh` (already committed)
**MODELS entries**: Already in `scripts/experiments/full_690_runner.py`
**YAML configs**: All 6 new configs committed in `configs/agents/`

### 2. W8 Aggregation Script (NOT YET CREATED)
- File: `scripts/experiments/aggregate_ex_w8_crossmodel.py` (~200 lines)
- Computes: CGA mean±SD per cell, cross-scaffold Jaccard, cross-model Jaccard, defense ratio
- Output: `evidence_pack/ex_w8_crossmodel/matrix.json` + LaTeX table + macros

### 3. Zenodo DOI (NeurIPS DESK REJECTION BLOCKER)
- Need persistent DOI for dataset
- Use `scripts/hf_upload.py` or Zenodo REST API
- Must be valid by May 4

### 4. LICENSE File
- Already in untracked: `LICENSE` (check if correct license type)
- Commit to repo

## Experiment Result Locations

| Experiment | Location | Status |
|-----------|----------|--------|
| EX-37 scaffold | `evidence_pack/ex37_scaffold_three_way/ex37_results.json` | DONE |
| EX-38 temp sweep | `results/defense_temp/agentclinic_{qwen35b,gemma31b}_t{0_0,0_1,0_3,0_7}.json` | DONE |
| EX-39 AMEGA | `results/amega_{gemma4_31b,oss120b,qwen35b}_run{1,2,3}.json` | DONE |
| EX-D1 projection | `evidence_pack/ex_d1_projection_ablation/` | DONE |
| HealthBench | `reports/healthbench_e2e/healthbench_{gemma31b,qwen35b}_{200,shard2_200}.json` | DONE |
| W8 cross-model | `results/ex_w8_crossmodel/` | NOT STARTED |

## Key Numbers for Quick Reference
- EX-D1 Shapley: pi_aset=-0.1522 (dominant), pi_term=+0.0221, pi_nctx=0.0, pi_ntim=-0.003
- EX-37: flip delta=2.3pp, Jaccard=0.34, McNemar p=0.032
- EX-38 qwen35b: T0.0→0.091, T0.1→0.094, T0.3→0.143, T0.7→0.184 (monotonic)
- EX-38 gemma31b: flat ~0.01 across all temps
- EX-39 AMEGA: qwen35b best (0.029), gemma/oss near zero
- HealthBench gemma: composite 0.579±0.188 (400 ep)
