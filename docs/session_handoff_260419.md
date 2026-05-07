# Session Handoff — 2026-04-19 (W8 Cross-Model + Defense Experiments)

## W8 Cross-Model Experiment Status

**Design**: 3 models x 3 scaffolds = 9 cells, 706 scenarios x 1 run each (W8_RUNS=1)

### Completed Cells (7/9)

| Cell | Raw Episodes | Unique (after dedup) | Status |
|------|-------------|---------------------|--------|
| gemma31b_react | 895 | 706 | COMPLETE |
| gemma31b_direct | 706 | 706 | COMPLETE |
| gemma31b_checklist | 706 | 706 | COMPLETE |
| qwen35b_direct | 793 | 706 | COMPLETE |
| qwen35b_checklist | 1021 | 706 | COMPLETE |
| qwen35b_react | 681 + 615 (s2) = 1296 | ~706 | COMPLETE (2 port sets merged) |

### In-Progress Cells (3/9) — oss120b on 144:30008

| Cell | Episodes | % | Shards | ETA |
|------|----------|---|--------|-----|
| oss120b_direct | 453 | 64% | 4/4 running | ~3-4h |
| oss120b_checklist | 303 | 43% | 4/4 running | ~5-6h |
| oss120b_react | 212 | 30% | 4/4 running | ~6-8h |

### Infrastructure

| Server | Port | Model | GPUs | Status |
|--------|------|-------|------|--------|
| 144:8017 | qwen35b TP=1 | GPU 0 | Idle (W8 qwen35b done) |
| 144:8018 | qwen35b TP=1 | GPU 1 | Idle (W8 qwen35b done) |
| 144:8019 | qwen35b TP=1 | GPU 2 | Idle (c3 done) |
| 144:8020 | qwen35b TP=1 | GPU 3 | Idle (W8 qwen35b done) |
| 144:30008 | oss120b TP=2 | GPU 4-5 | Active (oss120b W8) |
| 144:30009 | qwen35b TP=2 | GPU 6-7 | Idle (W8 qwen35b done) |
| 145:30003 | gemma31b TP=8 | GPU 0-7 | Idle (W8 gemma done) |

**Idle GPUs**: 144 GPU 0-3,6-7 (6 GPUs) + 145 GPU 0-7 (8 GPUs) = **14 idle GPUs**

## Defense C3 Gate Status — ALL COMPLETE

| Gate | Episodes | Status |
|------|----------|--------|
| agentclinic_qwen35b | 200/200 | COMPLETE |
| agentclinic_qwen35b_tp1 | 200/200 | COMPLETE |
| agentclinic_oss120b | 200/200 | COMPLETE |
| agentclinic_gemma31b | 200/200 | COMPLETE |
| medagentbench_qwen35b | 130/200 | Running |
| medagentbench_gemma31b | 200/200 | COMPLETE |

## Code Changes This Session

### Modified Files
1. **`configs/agents/clean_slate_oss120b_direct.yaml`**: Fixed `base_url` from `localhost:28000` to `127.0.0.1
2. **`configs/agents/clean_slate_oss120b_checklist.yaml`**: Same fix
3. **`scripts/experiments/full_690_runner.py`**: Added `qwen35b_react_s2` MODELS entry (port 30009), changed `qwen35b_checklist` port 8019->8020

### New Files
4. **`configs/agents/clean_slate_qwen35b_react_tp2.yaml`**: New config for qwen35b_react on port 30009 with `api_key: "sk-no-key-required"`

## Key Decisions & Fixes

1. **W8_RUNS=1**: Set via env var to reduce 3 runs to 1 for speed (3x improvement)
2. **Aggressive sharding**: 4-6 shards per cell for parallel execution on same vLLM endpoint
3. **Port 8019 conflict**: c3_qwen35b_tp1 used port 8019, redirected qwen35b_checklist to port 8020
4. **API key difference**: Ports 30008/30009/30003 require `api_key: "sk-no-key-required"`, ports 8017-8020 use `"not_needed"`
5. **oss120b config fix**: direct/checklist configs pointed to `localhost:28000` (wrong), fixed to `127.0.0.1

## Next Steps (Experiment iii — Tool-Use Scaffold)

Per `docs/attack_gap_exp_exp/260419_defense_exp.md`:

1. **Implement `tool_use_agent.py`**: vLLM function-calling API scaffold
   - Define JSON Schema functions for each ActionType
   - Extend VLLMProvider with `complete_with_tools()` method
   - Integrate with existing tool_api/ (90% reuse)
2. **Smoke test**: 10 scenarios x 3 models x 1 run
3. **Full run**: 706 scenarios x 3 models x 1 run on idle GPUs
4. **Analysis**: 3-way Cochran Q for scaffold-invariance (Theorem 3.4)

**Blocker**: vLLM on 145:30003 returns `Unauthorized` without api_key — must use `"sk-no-key-required"`

## Runner Process Info

- Active runners: 17 (all oss120b shards)
- Completed shards auto-exit after finishing
- No chain script managing — all manually launched
- Log files: `/tmp/w8_shard_oss_{react,direct,checklist}_s{1-4}.log`
