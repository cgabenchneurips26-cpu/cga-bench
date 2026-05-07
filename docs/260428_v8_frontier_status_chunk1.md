# v8 Frontier Expansion — Progress Report (Chunk 1)

**Date**: 2026-04-28 06:12 UTC
**Branch**: `eval_science`
**Session goal**: stand up parallel tracks (Track 1 GPU baseline complete + Track 2 S1 frontier pilot) and queue the v8 build phase.

## Current state

### Track 2 — S1 Sonnet 4.6 pilot (Anthropic API)

- **Status**: ACTIVE — 18/706 episodes complete, 4 worker pool, ~80s/episode
- **Process**: pid wheel through `frontier_spot_check.py --agent rag_claude_sonnet46 --workers 4 --runs 1`
- **Output**: `evidence_pack/frontier/s1_sonnet/{scenario_id}_r0.json` (per-scenario incremental writes)
- **Combined**: `evidence_pack/frontier/s1_sonnet.json` (final summary, written at end)
- **Log**: `evidence_pack/frontier/s1_sonnet.log` (live stdout via python -u)
- **Cost run rate**: actual 18,000–20,000 tokens/episode (smoke test: 20,447 tokens) → projected ~$70–85 final, well under env-cap $200
- **ETA**: 706 / (4 workers × 60-80s/ep) ≈ ~3 hours remaining (slower than 8-worker 2h estimate; chose 4 workers after 8-worker run hung on parallel ScenarioLoader init)

### Track 1 — v7 baseline 4 missing models on 145 + 144

User goal: rebuild v7 baseline 9-model complete (currently 5 models) so v8 = v6 ∪ v7 has consistent 9-model coverage on all 942 scenarios.

vLLM launch attempted on 16 GPUs (145 ×8 A100 80GB + 144 ×8 H200 143GB) for the 4 missing models. Results:

| Model | Endpoint | Status | Blocker |
|---|---|---|---|
| **qwen4b** ×2 (145 GPU 2,3) | 30206 / 30207 | ✅ HEALTHY | none |
| **gemma-4-31b-it** ×2 (145) ×4 (144) | 30210-13, 30310-13 | ❌ FAILED | Transformers does not recognize model type `gemma4`; vLLM 0.19.0 ships an older transformers and cannot load it without an env-level upgrade |
| **nemotron30b** ×2 (145) ×4 (144) | 30220-21, 30320-23 | ❌ FAILED | A100 (compute capability 8.0) cannot run `modelopt` FP8 quantization (needs 8.9+, i.e. H100/H200); 144's H200 hits a different vLLM-version blocker (`NemotronHForCausalLM` arch not inspectable) |
| **llama4scout** TP=2 (145 GPU 0,1) | 30201 | ❌ OOM | 109B-param MoE needs >160 GB; A100 ×2 = 160 GB exactly; would need TP=4 on 145 (4 A100s) or TP=2 on 144 (H200) but llama4scout weights NOT cached on 144 (~50 GB download) |

Track 1 infra status: only **qwen4b** runnable. Other 3 models blocked by environment / capability issues that are not fixable inside the current session without (a) upgrading transformers on 145 (risk: breaks vLLM), (b) upgrading vLLM on 144, or (c) using TP=4 for llama4scout (re-arrangement of 145 GPU map).

### Track 1 — qwen4b expansion run (active GPU work)

- **Status**: ACTIVE — 2 expansion_runner processes spawned, both healthy on 145:30206 and 145:30207
- **Workload**: 236 v7 expansion scenarios × 3 runs = 708 episodes per endpoint (claim-file dedup splits work between the two)
- **Workers**: 16 per endpoint = 32 effective concurrent decode slots
- **Output**: `results/expansion_v7/qwen4b/{sid}_qwen4b_r{idx}_{ts}.json`
- **Log**: `evidence_pack/expansion_v7_track1_logs/qwen4b_3020{6,7}.log`
- **GPU footprint**: 145 GPUs 2-3 loaded (75.8 GB each, 0.92 utilization). GPUs 0,1,4-7 idle (failed launches).
- **ETA**: 708 episodes / 32 workers / ~30s per 4B episode ≈ ~11 minutes wall-clock

### GPU utilization snapshot (2026-04-28 06:12 UTC)

```
145 (A100 80GB):
  GPU 0:    0 MB used (llama4scout failed-OOM, slot empty)
  GPU 1:    0 MB used (llama4scout failed-OOM, slot empty)
  GPU 2:    75803 MB (qwen4b_a)  ← active
  GPU 3:    75803 MB (qwen4b_b)  ← active
  GPU 4:    0 MB used (gemma31b failed-transformers, slot empty)
  GPU 5:    0 MB used (gemma31b failed-transformers, slot empty)
  GPU 6:    0 MB used (nemotron failed-capability, slot empty)
  GPU 7:    0 MB used (nemotron failed-capability, slot empty)

144 (H200 143GB):
  GPU 0-7:  0 MB all (every load failed; slot empty)
```

So the user's concern was valid — **2/16 GPUs active, 14/16 idle**. qwen4b GPUs only at high utilization once expansion_runner saturates them.

## Decisions deferred (need user direction)

1. **Track 1 partial vs full**: do we accept v7 baseline 6/9 (existing 5 + qwen4b) and proceed to v8 frontier expansion, or block on getting gemma31b/nemotron30b/llama4scout running? Each fix is 30+ min:
   - gemma: transformers upgrade (risky; breaks vLLM)
   - nemotron 145: skip (A100 cannot run modelopt FP8)
   - nemotron 144: vLLM upgrade or different model variant
   - llama4scout 145: TP=4 reconfig (uses 4 GPUs for 1 model)
   - llama4scout 144: download ~50 GB then TP=2

2. **v7 baseline scope**: if Track 1 is incomplete, does v8 frontier expansion still make sense as 942-scenario or fall back to 706-scenario v6-only?

## Files committed (this session, two chunks)

Chunk 1 (commit `ad830fda`):
- `secrets/{.gitignore,README.md,frontier_api_keys.env.example}`
- `docs/specs/frontier_expansion_plan_rev2_backup.md`

Chunk 2 (commit `2f59d88e`):
- `agent_runner/frontier_env_loader.py`
- `configs/agents/rag_{claude_sonnet46,claude_opus47,gpt55pro,gemini3pro}.yaml`
- `scripts/experiments/extract_w8_706_manifest.py`
- `evidence_pack/frontier/{w8_706_manifest.json,pre_registration.md}`
- `scripts/infra/launch_vllm_v8_track1_{145,144}.sh`

Chunk 3 (this commit, pending):
- `scripts/experiments/frontier_spot_check.py` (S1-S4 frontier runner)
- `scripts/infra/launch_vllm_v8_track1_nemotron.sh` (post-fix, --trust-remote-code added; still blocked by GPU capability)
- `evidence_pack/frontier/s1_sonnet_smoke{.json,/}` (smoke-test output, CGA=0.833 / 20447 tokens / 91s)

## Next user gates

- **G1 (S1 sonnet completion ~3h)**: review S1 output schema vs v6 baseline. Decide go/no-go for S2 (Opus 4.7, ~$353).
- **G2 (Track 1 qwen4b completion ~10 min)**: confirm v7 expansion + qwen4b joined as 6th model. Then decide on G2a (push remaining 3 missing models, ~30 min infra fix per model) vs G2b (proceed to v8 frontier expansion with 6-model v7 baseline).
- **G3 (post all 4 frontier stages S1+S2+S3+S4)**: full analysis (A through F enhancements), paper integration.
