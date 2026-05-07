# Session Status — 2026-04-21 09:30 KST

## GPU Utilization: 16/16 Active

### Host 144 (H200 × 8)
| GPUs | Container | Port | Model | Task | Progress |
|------|-----------|------|-------|------|----------|
| 0-3 | qwen3.5-397b-2 | 30002 | Qwen3.5-397B-A27B-FP8 | W8 direct→tooluse (G chain) | 237/2118 direct |
| 4-7 | nemotron30b | 30003 | NVIDIA-Nemotron-3-Nano-30B-A3B-FP8 | W8 react→direct→checklist→tooluse | 62/2118 react |

### Host 145 (A100 × 8)
| GPUs | Container | Port | Model | Task | Progress |
|------|-----------|------|-------|------|----------|
| 0-1 | qwen27b | 30003 | Qwen3.5-27B-FP8 | W8 react→direct (main chain) | 156/2118 react |
| 2-3 | qwen27b_s2 | 30007 | Qwen3.5-27B-FP8 | W8 checklist→tooluse (S2 chain) | 46/2118 checklist |
| 4-5 | qwen4b | 30006 | Qwen3-4B-Instruct-2507 | W8 react→direct (main chain) | 479/2118 react |
| 6-7 | qwen4b_s2 | 30008 | Qwen3-4B-Instruct-2507 | W8 checklist→tooluse (S2 chain) | 86/2118 checklist |

## W8 Scaffold Expansion (3→7 models)

### Already Complete (3 models from prior session)
- oss120b: 4 scaffolds × 2118 = 8,472 episodes ✅
- qwen35b: 4 scaffolds × 2118 = 8,472 episodes ✅
- gemma31b: 4 scaffolds × 2118 = 8,472 episodes ✅

### Running Now (4 models)
| Model | react | direct | checklist | tooluse | Total | ETA |
|-------|-------|--------|-----------|---------|-------|-----|
| qwen397b | 145 (paused) | 237 (running) | 0 | 0 | 382/8472 | Slowest — 397B model |
| qwen27b | 156 (running) | 0 | 46 (S2) | 0 | 202/8472 | ~20h |
| qwen4b | 479 (running) | 0 | 86 (S2) | 0 | 565/8472 | ~12h |
| nemotron30b | 62 (running) | 0 | 0 | 0 | 62/8472 | ~8h (3B active, fast) |

### Parallelization Strategy
- **qwen27b / qwen4b**: 2 endpoints each — main chain does react→direct, S2 chain does checklist→tooluse in parallel. Symlinks ensure canonical output dirs.
- **qwen397b**: G chain on 144:30002 (direct→tooluse). F chain (react+checklist) paused — resumes after nemotron30b finishes on 144:30003.
- **nemotron30b**: Deployed on 144 H200 (FP8 requires compute capability 89). Auto-chains to qwen397b F chain + held-out after completion.

## Auto-Chain Pipeline
```
nemotron30b W8 (4 scaffolds, 144:30003)
  → stop nemotron30b
  → restart qwen397b on 144:30003 GPU 4-7
  → resume F chain (react from 145/2118, then checklist)
  → qwen397b held-out (175 remaining episodes)
```

## Held-out Domain Status
| Model | Episodes | Status |
|-------|----------|--------|
| oss120b | 199 | ✅ Complete |
| qwen35b | 198 | ✅ Complete |
| qwen27b | 198 | ✅ Complete |
| qwen4b | 198 | ✅ Complete |
| gemma31b | 198 | ✅ Complete |
| nemotron30b | 198 | ✅ Complete |
| deepseek_r1_7b | 198 | ✅ Complete (excluded from macro — not in COMPLETE_MODELS) |
| **qwen397b** | **23/198** | ⏳ Auto-chained after W8 |
| biomed8b | 0 | ❌ Never run |

**After qwen397b completes**: 8 models × 198 = 1,584 episodes (update macro from 1,188)

## Dedup / Overlap Prevention
- All `_s2` output dirs are symlinks to canonical dirs (verified)
- No scaffold overlap between main and S2 chains
- Checkpoint/claim system prevents duplicate episode execution
- qwen4b has 2 processes on react (harmless — claim dedup)

## Key Files Modified This Session
- `scripts/experiments/full_690_runner.py` — added S2 MODELS entries, fixed nemotron30b to 144:30003
- `configs/agents/clean_slate_*_s2.yaml` — S2 configs pointing to new ports
- `configs/agents/clean_slate_nemotron30b_*.yaml` — updated to 144:30003
- `configs/agents/clean_slate_qwen397b_{react,checklist}.yaml` — updated to 30003 for F chain restart
- `scripts/experiments/launch_nemotron30b_w8_144.sh` — full auto-chain script
- `scripts/experiments/launch_qwen{27b,4b}_s2_w8.sh` — S2 chain scripts
- `scripts/experiments/poll_s2_endpoints.sh` — auto-detect and launch S2 chains

## Critical Notes
- nemotron30b FP8 CANNOT run on 145 A100s (capability 80 < required 89) — must use 144 H200s
- 144 GPU assignment was inverted: qwen3.5-397b-2 is on GPU 0-3 (not 4-7)
- `qwen397b_direct_s2_old/` cleaned up (was real dir before symlink swap)
