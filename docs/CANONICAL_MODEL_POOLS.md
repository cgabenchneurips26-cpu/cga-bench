# Canonical Model Pools — Single Source of Truth

> **Updated**: 2026-05-06. Read this FIRST in every new session.

## The 4 Model Sets

```
OPEN_9  = {oss120b, qwen27b, qwen35b, qwen4b, qwen397b, gemma31b, nemotron30b, deepseek_r1_7b, llama4scout}
ALLM_H  = {allm_h}                          # oracle upper-bound, NOT an LLM
FRONTIER = {claude_opus47, claude_sonnet46, gemini25pro, gemini25flash, gpt54, gpt54mini}
OPEN_8  = OPEN_9 - {llama4scout}             # legacy v6base, DO NOT USE for new work
```

## Data Pools (verified 2026-05-06)

### Active directories (`results/`)

```
results/
├── _archive/                  # 28 archived dirs (smoke, pilot, legacy, etc.)
├── ex_w8_crossmodel_v5/       # W8 scaffold experiment
├── full_706_v5/               # P-V5: legacy paper original
├── full_v6a_706/              # P-A:  current canonical (paper §3)
├── full_v6b/                  # P-B:  Phase B expanded (paper appendix)
├── v73_frontier/              # P-FR: frontier closed-weight
└── v73_full_with_allmh/        # P-V73: SGSC cross-corpus (paper §4)
```

| Pool ID | Directory | Scenarios | Models | Per-Model | Total | Paper |
|---------|-----------|-----------|--------|-----------|-------|-------|
| **P-A** | `full_v6a_706/` | 706 manual | OPEN_9 + ALLM_H = **10** | 2,118 | 21,180 | superset |
| **P-A9** | same, filtered | 706 | OPEN_9 = **9** | 2,118 | **19,062** | **§3 headline** |
| **P-B** | `full_v6b/` | 3,187 (706+2,481 auto) | OPEN_8 + ALLM_H = **9** | ~9,558 | ~76,470 | §App sensitivity |
| **P-V73** | `v73_full_with_allmh/` | 419 SGSC atoms | OPEN_9 + ALLM_H = **10** | 1,254 | 12,540 | §4 superset |
| **P-V73-9** | same, filtered | 419 | OPEN_9 = **9** | 1,254 | **11,286** | §4 headline |
| **P-FR** | `v73_frontier/` | 418 SGSC atoms | FRONTIER = **6** | 1,254 target | ~6,129 | §4 frontier |
| **P-V5** | `full_706_v5/` | 706 | OPEN_9 = **9** | 2,118 | 19,062 | legacy |
| **P-W8** | `ex_w8_crossmodel_v5/` | 706 | 3 models × 4 scaffolds | ~706 | ~8,472 | §App scaffold |

### Key gaps
- **Phase B**: llama4scout = 0 episodes (OPEN_8 only, not OPEN_9)
- **Frontier**: gemini25pro = 106/1,254, gemini25flash = 1,007/1,254 (incomplete)

## Paper TeX Chain (active: main_final_v18.tex)

```
main_final_v18.tex
  └── auto_numbers.tex          ← \numModels{9}, \numEpisodes{19,062} = P-A9
       └── auto_numbers_sgsc.tex
       └── auto_numbers_v6base.tex   ← \v6baseNModels{8} = legacy OPEN_8 pool
       └── auto_numbers_v73_*.tex
  └── bayes_error_macros.tex    ← \bayesErrNEpisodes{19,062} = P-A9 (recomputed 2026-05-06)
```

**`auto_numbers_v2.tex` is DEAD** — only referenced by v14/v16 (not v18).

## Script → Pool Mapping

| Script | Filter Variable | Pool | Models |
|--------|----------------|------|--------|
| `_episode_cache.py` | `COMPLETE_MODELS` | P-A9 | **9** (fixed 2026-05-06) |
| `verdict_matrix_v5.py` | `COMPLETE_MODELS` | P-A9 | **9** |
| `compute_bayes_error.py` | imports _episode_cache | P-A9 | **9** (fixed 2026-05-06) |
| `verify_friedman_eta.py` | `COMPLETE_MODELS` | P-A9 | **9** (fixed 2026-05-06) |
| `compute_cga_s_clean.py` | `VALID_OPEN` | P-A (10) | **10** (includes allm_h) |
| `compute_cga_s_clean.py` | `VALID_FRONTIER` | P-FR | **6** |
| `package_hf_dataset.py` | `PAPER_MODELS` | P-A9 | **9** (fixed 2026-05-06) |
| `normalizer_ablation_multimodel.py` | `COMPLETE_MODELS` | P-A9 | **9** (fixed 2026-05-06) |

## Quick Decision Table

| Question | Answer |
|----------|--------|
| Paper headline models/episodes? | **9 / 19,062** (P-A9) |
| Which results dir for paper? | `full_v6a_706` filtered to OPEN_9 |
| Include allm_h in rankings? | **No** for LLM comparisons, **Yes** for CGA-S cross-corpus |
| Include deepseek_r1_7b? | **Yes** — promoted from W8 exclusion to OPEN_9 |
| Bayes-floor episodes? | **19,062** (recomputed 2026-05-06 from 7→9 models) |
| Phase B has llama4scout? | **No** — 0 episodes. Phase B = OPEN_8 + ALLM_H |
| Frontier complete? | **No** — gemini25pro(106), gemini25flash(1007) incomplete |

## Legacy Names (do NOT use)

| Legacy | Meaning | Current |
|--------|---------|---------|
| "W8" | 7-model filter (excluded deepseek) | → use OPEN_9 |
| "v6base 8-model" | 8-model (excluded llama4scout) | → use P-A9 (9-model) |
| "14,826 episodes" | 7×2,118 | → **19,062** = 9×2,118 |
| "16,944 episodes" | 8×2,118 | → **19,062** = 9×2,118 |
