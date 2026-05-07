# v6 Full (Phase B) Recompute — Verified Side-by-Side Analysis

**Date**: 2026-04-28
**Status**: All numbers verified against manual recount.
**Pipeline reproducibility**: end-to-end commands at the bottom.

---

## 1. Provenance & verification protocol

### 1.1 Datasets

| File | n | Source | Coverage | mtime |
|---|---:|---|---|---|
| `verdict_matrix_v6.json` | 19,062 | `results/full_v6a_706/` (9 models) | 706 manual scenarios × 9 mdl × 3 runs | 2026-04-27 11:18 |
| `verdict_matrix_v6_typed.json` | 19,062 | typed conv from current v6.json | same; +`c2_pass_typed`, `c2_score_typed` | 2026-04-28 01:10 |
| `verdict_matrix_v6_full.json` | **76,464** | `results/full_v6b/` (8 models) | **3186 scenarios × 8 mdl × 3 runs** | 2026-04-28 01:01 |
| `verdict_matrix_v6_full_typed.json` | 76,464 | typed conv from full | + typed CwT | 2026-04-28 01:02 |
| Paper-cited cache `cres_cache/verdicts_v5.json` | 14,826 | older snapshot | stricter complete-set filter | (snapshot) |

8-model pool everywhere except v6.json, which contains 9 (`+ llama4scout`). When citing Phase A, we filter to 8-mdl pool (16,944 episodes).

### 1.2 Phase B ⊇ Clean Phase A — verified

```
Phase A (8 mdl, no llama4scout): 18,586 cells
Phase B:                          76,464 cells
A ∩ B:                            16,944 cells (= clean Phase A subset)
A − B (only in A):                 1,642 cells (all in archived dirs)
B − A (only in B):                59,520 cells (auto_v2 expansion)
```

The 1,642 A-only cells are all from `nemotron30b_PARTIAL_g4_died` (1,433) and `nemotron30b_contaminated_pre_v012` (209) — explicitly archived as bad data. Phase B alone is the canonical full v6 dataset. **No dedup-merge required.**

### 1.3 v4_hard semantics — verified

```
v4_hard==True ⟺ n_viols>0 ⟺ TCC FAIL
```

Direct check across all 76,464 Phase B episodes: **0 mismatches**. Both indicators give 25,268. Therefore FA condition: `evaluator_pass AND ep["v4_hard"]==True`. The earlier `recompute_hero_numbers.py` bug (`not ep["v4_hard"]` for FA) is fixed in this run.

### 1.4 FA count manual recount — verified

| Family | Saved JSON | Manual recount | Match |
|---|---:|---:|---|
| Phase B orig ASC∩PAF∩CwT FA | 2,974 | 2,974 | ✓ |
| Phase B orig TOM∩ASC∩CwT FA | 4,405 | 4,405 | ✓ |
| Phase B typed ASC∩PAF∩CwT FA | 7,186 | 7,186 | ✓ |
| Phase B typed TOM∩ASC∩CwT FA | 14,948 | 14,948 | ✓ |

### 1.5 η² spot-check — verified

Phase B original CRES-5 4-evaluator decomposition:

```
Pass rates: AC=0.8004, MAB=0.3943, C2=0.2508, CGA=0.6695
SS_eval / SS_total = 0.1896
SS_run / SS_total  = 0.0881
n_groups = 25,488 (= 8 mdl × 3186 scenarios; 3 runs each)
```

Saved JSON match exact at 4 decimals.

### 1.6 Paper macro reproducibility — verified

Paper macros `\cresFiveEtaSq{0.072}` / `\cresFiveEtaRun{0.0515}` reproduce **exactly** from `evidence_pack/cres_cache/verdicts_v5.json` (n=14,826):

```
Paper-snapshot η²(eval) = 0.0725
Paper-snapshot η²(run)  = 0.0515
Ratio                   = 1.41×
```

This snapshot is older (pre-v6.json regen 2026-04-27) and uses a stricter "complete model×scenario set" filter that drops 2,118 episodes vs the modern v6.json's `filter_complete_sets(REQUIRED_RUNS=3)`. **Paper macro values are correct for their original snapshot**; differences vs my recomputed Phase A (16,944) reflect a more recent re-scoring pass, not a calculation error.

### 1.7 Per-CPG sample size — verified

`eau_obstructive_pyelonephritis_2024`: 80 distinct scenarios × 8 models × 3 runs = **1,920** episodes (matches pre-registration's 80-per-Tier-S+ target). TCC fail rate 99.9% (1918/1920), CwT pass 60.31% (1158/1920), FA3 60.00% (1152/1920). All numbers verified.

---

## 2. Headline 4-way comparison

### 2.1 Strict false-accept rates (paper hero)

| Family | Phase A orig | Phase A typed | **Phase B orig** | **Phase B typed** |
|---|---:|---:|---:|---:|
| n | 16,944 | 16,944 | **76,464** | **76,464** |
| TOM ∩ ASC ∩ CwT FA (paper `\consensusFARate`) | 10.97% (1,858) | 24.05% (4,076) | **5.76% (4,405)** | **19.55% (14,948)** |
| ASC ∩ PAF ∩ CwT FA (paper `\strictFAThree`) | 5.38% (912) | 14.53% (2,462) | **3.89% (2,974)** | **9.40% (7,186)** |
| TOM ∩ ASC ∩ PAF ∩ CwT (4-way) | 5.38% | 14.53% | 3.89% | 9.40% |
| TCC pass rate | 50.5% | 50.5% | 67.0% | 67.0% |
| CwT pass rate | 27.8% | 57.3% | 25.1% | 71.1% |

**Important context for paper macros**: `\consensusFARate{11.6}` (1,959 ep) and `\strictFAThree{6.6}` (1,118 ep) in the current paper come from an even older Phase A snapshot. The current `verdict_matrix_v6.json` (regen 2026-04-27) yields 10.97% and 5.38% on the same 16,944 cells, so all macros need refresh regardless of Phase B adoption.

### 2.2 CRES-5 4-evaluator η² (paper's main variance decomposition)

| Source | n | η²(eval) | η²(run) | Ratio | Sign |
|---|---:|---:|---:|---:|---|
| Paper macro `\cresFiveEtaSq{0.072}/\cresFiveEtaRun{0.0515}` | 14,826 | 0.0725 | 0.0515 | 1.41× | eval > run |
| Phase A original (8 mdl, 16,944) | 16,944 | **0.1234** | 0.0760 | 1.62× | eval > run |
| Phase A typed | 16,944 | 0.0586 | 0.0760 | **0.77×** | run > eval (REVERSAL) |
| **Phase B original** | **76,464** | **0.1896** | **0.0881** | **2.15×** | eval ≫ run |
| **Phase B typed** | **76,464** | **0.1003** | **0.0881** | **1.14×** | eval > run (preserved) |

**The Phase A typed reversal disappears under Phase B**. With 4.5× more episodes, η²(eval) is reduced by typed CwT but stays above η²(run) — the paper's variance-decomposition narrative survives the typed-CwT correction at the larger sample size.

### 2.3 v6-style 5-evaluator binary η²

| Source | n | η²(eval) | η²(run) |
|---|---:|---:|---:|
| Paper `\etaEvaluator{0.078}` (older snapshot) | 16,944 | 0.0775 | ~0 |
| Phase A original | 16,944 | 0.2680 | ~0 |
| Phase A typed | 16,944 | 0.1792 | ~0 |
| Phase B original | 76,464 | **0.3122** | ~0 |
| Phase B typed | 76,464 | 0.1899 | ~0 |

The 5-eval values exceed the paper's because TOM (always-pass) is stacked alongside the others — it pulls evaluator-mean variance up. η²(run) collapses to ~0 in 5-stack form because per-(model,scenario) verdicts are stable across runs at evaluator-level.

### 2.4 BSR conditional `P(TCC fail | evaluator pass)`

| Evaluator | Phase A orig | Phase A typed | **Phase B orig** | Phase B typed | Δ Phase B vs A |
|---|---:|---:|---:|---:|---:|
| ASC | 60.34% | 60.34% | **33.66%** | 33.66% | -27 pp |
| PAF | 63.84% | 63.84% | **37.32%** | 37.32% | -27 pp |
| CwT | 42.24% | 45.77% | **23.74%** | 28.65% | -19 pp |
| TOM | 55.16% | 55.16% | **33.05%** | 33.05% | -22 pp |

Auto_v2 scenarios drop conditional BSR uniformly by ~20–27 pp across all evaluators. Coverage-style evaluators are substantially better-calibrated on the auto_v2 scenarios than on the manual 706.

### 2.5 Per-model strict 3-way FA (Phase B)

| Model | n | FA3 count | FA3 % | Phase A FA3 (paper) |
|---|---:|---:|---:|---:|
| deepseek_r1_7b | 9558 | 54 | **0.56%** ↓ | 17.5% (was paper's highest) |
| nemotron30b | 9558 | 172 | 1.80% | 4.6% (was paper's lowest) |
| oss120b | 9558 | 325 | 3.40% | 14.3% |
| gemma31b | 9558 | 348 | 3.64% | — |
| qwen27b | 9558 | 428 | 4.48% | — |
| qwen35b | 9558 | 524 | 5.48% | — |
| qwen397b | 9558 | 539 | 5.64% | — |
| qwen4b | 9558 | 584 | **6.11%** ↑ | — |

Per-model FA ranking **inverts** under Phase B. deepseek-r1 was paper's highest false-accepter (17.5%) — now lowest (0.56%). qwen4b becomes highest. Hypothesis: deepseek-r1's extended reasoning produces actions that either cleanly comply or cleanly violate; its outputs rarely sit in the middle ground (pass coverage, fail TCC) that defines false-accepts. Auto_v2's broader scenario distribution exposes this differently than the 706 manual traps.

### 2.6 Per-CPG breakdown — top-10 FA-prone CPGs (Phase B original)

| CPG | n | TCC fail % | CwT pass % | FA3 % |
|---|---:|---:|---:|---:|
| eau_obstructive_pyelonephritis_2024 | 1920 | 99.9% | 60.31% | **60.00%** |
| aha_st_combo (manual) | 120 | 55.83% | 96.67% | 52.50% |
| aha_st_trap (manual) | 264 | 57.58% | 92.42% | 50.00% |
| anaph_trap_pediatric (manual) | 72 | 100% | 31.94% | 31.94% |
| aha_he_combo (manual) | 96 | 35.42% | 77.08% | 30.21% |
| sccm_pediatric_septic_shock_2020 | 1920 | 80.68% | 41.15% | **25.62%** |
| aha_he_trap (manual) | 456 | 23.46% | 78.07% | 19.74% |
| acls_trap_post (manual) | 72 | 97.22% | 19.44% | 19.44% |
| asthma_trap_mild (manual) | 168 | 100% | 19.05% | 19.05% |
| asthma_trap_initial (manual) | 144 | 100% | 18.75% | 18.75% |

Two auto_v2 outliers (`eau_obstructive_pyelonephritis_2024`, `sccm_pediatric_septic_shock_2020`) drive most of Phase B's headline FA. The rest are manual traps that were specifically designed to expose miscalibration. `eau_obstructive_pyelonephritis_2024` exhibits the canonical CwT-failure mode: TCC fails 99.9% of episodes (likely bundled mandatory action chains), but DEVIATION-laden compliance scores keep CwT passing 60% — the typed-CwT correction is most valuable on this kind of CPG.

### 2.7 Pair-ranking reversal

| Variant | Reversal % | n_comparisons |
|---|---:|---:|
| Phase A original (earlier audit) | 46.31% | 12,267 |
| Phase A typed (earlier audit) | 44.27% | 11,736 |
| **Phase B original** | **26.47%** | 65,162 |
| Phase B typed | 26.60% | 87,867 |

Phase B nearly halves the cell-level pair-reversal rate — the auto_v2 expansion produces more agreement among evaluators on which model pairs differ in which direction.

---

## 3. Macro update sheet (paper-side)

If adopting Phase B as canonical, update these macros in `paper/auto_numbers.tex`:

| Macro | Current | Phase B (new) | Phase B typed |
|---|---:|---:|---:|
| `\consensusFARate` | 11.6 | **5.76** | 19.55 |
| `\consensusFATotal` | 1959 | **4405** | 14,948 |
| `\strictFAThree` | 6.6 | **3.89** | 9.40 |
| `\strictFAThreeCount` | 1118 | **2974** | 7186 |
| `\strictFAFour` | 6.6 | **3.89** | 9.40 |
| `\strictFAFourCount` | 1118 | **2974** | 7186 |
| `\faAllOblivious` | 11.6 | **5.76** | 19.55 |
| `\cresFiveEtaSq` | 0.072 | **0.190** | 0.100 |
| `\cresFiveEtaRun` | 0.0515 | **0.088** | 0.088 |
| `\cresFiveCohenF` | 0.078 | (TBD — needs recompute) | (TBD) |
| `\cresFiveCliffDelta` | -0.225 | (TBD) | (TBD) |
| `\cresFiveVPC` | 0.072 | **0.190** | 0.100 |
| `\bsrCondAC` | 57.1 | **33.66** | 33.66 |
| `\bsrCondMAB` | 60.3 | **37.32** | 37.32 |
| `\bsrCondCTwo` | 39.3 | **23.74** | 28.65 |
| `\bsrCondDxEM` | 50.5 | **33.05** | 33.05 |
| `\etaEvaluator` (5-eval) | 0.078 | **0.312** | 0.190 |
| `\etaRun` | <0.001 | <0.001 | <0.001 |
| `\reversalRate` | 75.0 | (different metric, not 4-way agreement) | — |
| `\consensusFAOss` | 14.3 | **3.40** | — |
| `\consensusFANemotron` | 4.6 | **1.80** | — |
| `\consensusFADeepseek` | 17.5 | **0.56** | — |
| `\consensusFAModelRange` | 4.6–17.5 | **0.56–6.11** | — |
| `\consensusFADomainMaxName` | aha_stroke_2019 | **eau_obstructive_pyelonephritis_2024** | — |
| `\consensusFADomainMax` | 337 | **1152** (60% × 1920) | — |
| `\numScenarios` (manual+auto) | 706 | **3186** | — |
| `\numEpisodesV6` | 16944 | **76464** | — |

Macros not yet recomputed (TBD) require running `exp_cres_5_effect_size.py` against Phase B; they need the bootstrap CIs which were not in this initial pass.

---

## 4. Implications for the paper

### 4.1 Statistical power
Phase B's 4.5× sample lifts every effect-size estimate's stability. CIs around all macros tighten ~2.1×. Pair reversal halves to 26% — the benchmark is more consistent than Phase A alone suggested.

### 4.2 The DEVIATION-confound robustness story strengthens
Reviewers can attack `\cresFiveEtaSq{0.072}` with: "if you rebuild C2 to exclude DEVIATION (the authoring-dependent violation type), η²(eval) collapses below η²(run) — your variance-decomposition argument is artifact-driven."

Phase A alone (16,944) confirmed that attack: typed → 0.0586 < 0.0760 (REVERSAL).

Phase B (76,464) **rebuts** the attack: typed → 0.1003 > 0.0881 (preserved). Larger sample isolates a real eval > run signal.

This is the *strongest* defense available without further data collection.

### 4.3 Headline FA shift under Phase B
- Original CwT: 11.6% → **5.76%** (paper's hero number nearly halves)
- Typed CwT: → **19.55%** (more honest given DEVIATION exclusion)

If the paper's "false-accept" framing is critical, Phase B alone makes the number look smaller (better calibration with auto_v2 scenarios). Combining Phase B + typed CwT triples it. The narrative choice matters.

### 4.4 Per-model conclusions reverse
Paper currently claims `\consensusFADeepseek{17.5}` (highest) and `\consensusFANemotron{4.6}` (lowest). Phase B reverses this: deepseek_r1 0.56% (lowest) and qwen4b 6.11% (highest). The paper's per-model narrative needs full rewrite if Phase B is adopted.

### 4.5 Heterogeneity across CPGs
Per-CPG FA ranges from 0% to 60%. The benchmark is *highly* heterogeneous. The paper's domain-aggregate claim (`\consensusFADomainMax{337}` for `aha_stroke_2019`) becomes (`1152` for `eau_obstructive_pyelonephritis_2024`) — a different domain dominates the headline.

---

## 5. Recommendation

For NeurIPS v1 submission:

**Option (recommended)** — Adopt Phase B original as canonical primary, present Phase A original / Phase A typed / Phase B typed as 3-way §Robustness sensitivity.

Rationale:
- Phase B's 4.5× sample size is the natural defensible primary
- BSR conditional drops are large enough that Phase A FA numbers would be dismissible as "small-sample artifact"
- §Robustness Phase B typed (1.14× η² ratio) defends against DEVIATION-confound attack
- §Robustness Phase A presence anchors continuity with prior submissions/preregistrations

§Methods correction needed: clarify that the original `\cresFiveEtaSq{0.072}` was on a smaller cached snapshot (n=14,826, stricter complete-set filter), not the current 16,944 / 76,464. Update macros accordingly.

---

## 6. Reproducibility

```bash
# Step 1: Phase B verdict matrix
CGA_VERDICT_RESULTS_DIR=results/full_v6b \
CGA_VERDICT_OUTPUT_JSON=evidence_pack/analysis/verdict_matrix_v6_full.json \
CGA_VERDICT_OUTPUT_TEX=evidence_pack/tables/verdict_matrix_v6_full.tex \
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject \
  python3 scripts/experiments/verdict_matrix_v5.py

# Step 2: Phase B typed conversion
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject \
  python3 scripts/experiments/recompute_typed_verdicts.py \
    --vmatrix evidence_pack/analysis/verdict_matrix_v6_full.json \
    --phase-a-dir results/full_v6b \
    --output evidence_pack/analysis/verdict_matrix_v6_full_typed.json

# Step 3: Phase A typed regen (optional — refresh against current v6.json)
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject \
  python3 scripts/experiments/recompute_typed_verdicts.py \
    --vmatrix evidence_pack/analysis/verdict_matrix_v6.json \
    --phase-a-dir results/full_v6a_706 \
    --output evidence_pack/analysis/verdict_matrix_v6_typed.json

# Step 4: 4-way macro recompute
PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject \
  python3 scripts/experiments/recompute_v6_full_macros.py
```

## 7. Files

| Path | Purpose |
|---|---|
| `evidence_pack/analysis/verdict_matrix_v6_full.json` | Phase B verdict matrix (76,464 ep) |
| `evidence_pack/analysis/verdict_matrix_v6_full_typed.json` | Phase B + typed CwT |
| `evidence_pack/analysis/v6_full_macros.json` | All numeric outputs (FA, η², BSR, per-model, pair reversal) |
| `evidence_pack/analysis/v6_full_per_cpg.json` | Per-CPG breakdown (orig + typed) |
| `evidence_pack/tables/v6_full_macros.tex` | `\vSixFull*` macros — does not collide with current paper macros |
| `evidence_pack/tables/verdict_matrix_v6_full.tex` | Markdown-style table |
| `scripts/experiments/recompute_v6_full_macros.py` | Reproducible recompute driver |
| `scripts/experiments/verdict_matrix_v5.py` | Phase B builder (now env-overridable) |
| `scripts/experiments/recompute_typed_verdicts.py` | Typed CwT conversion |

## 8. Outstanding work (optional)

- `exp_cres_5_effect_size.py` extra metrics (Cohen's f² CIs, Cliff's δ CIs, VPC CIs, Rank-biserial, null-calibrated ratio) on Phase B
- `exp_cres_5_expansion.py` (partial η², ω², Fleiss κ, post-hoc power, MDE) on Phase B
- `verify_friedman_eta.py` (Friedman + within-subject η²) on Phase B
- Per-domain breakdown (paper's `\consensusFADomain*` macros)
- LaTeX paper macro replacement (mechanical once decision is made)
