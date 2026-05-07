# Evidence Pack

CGA-Bench experimental results and analysis — single source of truth.

> **Last updated**: 2026-04-21 | **Pipeline**: v5 (strict scoring, 7 models)

## Quick Navigation

| What you need | Where to look |
|---------------|---------------|
| **Full experiment catalogue** | [`INDEX.md`](INDEX.md) — intent, result, significance for all 87 directories |
| **Paper numbers** | [`PAPER_NUMBER_SOURCE.md`](PAPER_NUMBER_SOURCE.md) — authoritative reference |
| **LaTeX macros** | `auto_numbers_v2.tex` (main), per-experiment `*_macros.tex` files |
| **Canonical numbers (JSON)** | [`canonical_numbers.json`](canonical_numbers.json) |
| **Claim verification** | [`claim_verification_v5.md`](claim_verification_v5.md) |

## Corpus Summary

| Item | Value |
|------|-------|
| Main episodes | **14,826** (7 models x 706 scenarios x 3 runs) |
| W8 episodes | **8,472** (3 models x 4 scaffolds x 706 scenarios; expanding to 7 models) |
| Models (complete) | oss120b, qwen27b, qwen35b, qwen4b, qwen397b, gemma31b, nemotron30b |
| CPG graphs | **25** (20 core + 5 held-out) |
| Scenarios | **690** (107 manual + 583 auto-generated) |
| Constraints | **1,358** (230 hard / 1,128 soft) |
| Total experiment dirs | **87** |

## Directory Structure

```
evidence_pack/
  INDEX.md                   # Comprehensive experiment index (START HERE)
  PAPER_NUMBER_SOURCE.md     # Authoritative paper numbers
  canonical_numbers.json     # Programmatic number source
  claim_verification_v5.md   # Per-claim evidence trail

  cres_{1a..13}/             # CRES defense suite (14 experiments)
  cres_cache/                # Shared verdict lookup tables

  ex{1..38}_*/               # Numbered experiments (34 complete)
  ex_w8_crossmodel/          # Scaffold independence (4-scaffold, cross-model)
  ex_x{1,2,9}_*/             # Causal intervention experiments
  ex_d1_projection_ablation/ # Theorem 3.4 empirical validation

  heldout_v1/                # Held-out domain evaluation
  normalizer_ablation/       # Normalizer mode ablation
  theorem_v2/                # Theoretical proofs + Bayes error

  analysis/                  # 80+ core analysis JSONs
  figures/                   # 50+ publication-ready figures
  tables/                    # 40+ LaTeX table definitions
  case_studies/              # 5 exemplar episodes
  clinician_review/          # Clinical rule audit (300+ critical rules)
  experiments/               # Clinician protocol materials
  sampling/                  # Reproducibility sample indices

  ws{4,5,6}_*                # Workspace experiments (variance, contamination, taxonomy)
  omission_*/                # Root-cause diagnosis
  deep_diagnosis/            # Fix catalogues
  fix_actions*/              # Normalizer corrections
```

## Data Provenance

> **Current pipeline**: v5 (strict scoring, 7 complete models, Apr 2026)
>
> Files from the Pre-R1-R5 pipeline (early March 2026) are retained for
> historical reference but marked STALE. See the Deprecation Notes section
> in [`INDEX.md`](INDEX.md) for the full list.
>
> **For the NeurIPS 2026 paper, use ONLY v5 pipeline outputs.**

### Key v5 Sources

| Purpose | File |
|---------|------|
| All paper numbers | `PAPER_NUMBER_SOURCE.md` |
| V5 evidence summary | `evidence_summary_v5.md` |
| Statistical robustness | `analysis/robustness_clean_v2.json` |
| Bootstrap-swapped ranks | `analysis/bsr_results.json` |
| C1-C5 subconstruct profiles | `analysis/subconstruct_profiles.json` |
| Verdict matrix | `cres_cache/verdicts_v5.json` |

### Stale Files (Do Not Use for Paper)

| File | Reason |
|------|--------|
| `FINAL_NUMBERS.md` | Pre-R1-R5 scoring (4 models, lenient) |
| `VERDICT_TABLE.md` | Pre-R1-R5 claim verdicts |
| `cga_bench_full_briefing.md` | Pre-R1-R5 overview |
| `analysis/15scenario_unified.json` | 15-scenario pilot (superseded by 706) |
| `analysis/composite_metric.json` | Pre-R1-R5 composite formula |

## File Naming Conventions

| Pattern | Meaning |
|---------|---------|
| `*_results.json` | Machine-readable experiment output |
| `*_macros.tex` | LaTeX `\providecommand` for paper integration |
| `*_report.md` | Human-readable experiment report |
| `ex{N}_*` | Numbered experiment series |
| `cres_{id}_*` | CRES defense experiment |
| `ws{N}_*` | Workspace experiment |

## Experiment Categories

| Category | Count | Description |
|----------|-------|-------------|
| CRES Defense | 14 | Reviewer rebuttal experiments |
| Numbered (EX1-38) | 34 | Benchmark property validation |
| Extended (W8, X, D1) | 5 | Cross-model, causal, projection |
| Held-out / Normalizer | 5 | Generalization and robustness |
| Workspace (WS4-6) | 3 | Variance, contamination, taxonomy |
| Theory | 1 | Theorem 3.4 proofs + empirics |
| Validation & Audit | 9 | Verification suites |
| **Total** | **71** | |

See [`INDEX.md`](INDEX.md) for the complete catalogue with intent, result,
and significance for every experiment.
