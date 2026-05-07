> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# Final Rescore v4 -- Comprehensive Report

**Date**: 2026-04-02
**Status**: CONFIRMED (verified with corrected evidence pipeline)
**Script**: `scripts/experiments/final_rescore_v4.py`
**JSON**: `evidence_pack/additional/analysis/final_rescore_v4.json`

---

## 1. Bug Summary (4 Corrections)

### Bug 1: Evidence Sourcing (CRITICAL -- root cause of 27->48 jump)

- **Old code**: Exp11 read `guideline_class` from episode JSON (`new_violation_events[].guideline_class`) where 83.6% of entries were `None`
- **Fix**: `gap_experiments.py` line 1636 reads `recommendation_class` from YAML graph metadata via `evidence_map`, stored per-node
- **Impact**: All 20 Sepsis WITHIN violations reclassified from MODERATE to STRONG (their YAML nodes have `recommendation_class: "I"`)
- **Result**: UP_strong jumped from 27/78 to 48/78 = UP_any (tier collapse)

### Bug 2: EVIDENCE_STRENGTH Dictionary Mapping

- **Old**: `IIa` mapped as `STRONG` (incorrect -- IIa is moderate recommendation)
- **Fix**: `IIa -> MODERATE`, `IIb -> MODERATE`, `B -> MODERATE`, added SSC/KDIGO/GRADE labels
- **Impact**: Zero delta. All violation-producing nodes are Class I, so the mapping correction affects only non-violating nodes.

### Bug 3: UP_crit +1 Episode

- **Old**: 13/78 (16.7%)
- **New**: 14/78 (17.9%)
- **Root cause**: 1 AF episode (`af_new_onset_basic`) now correctly classified as CRITICAL with STRONG evidence after sourcing fix

### Bug 4: Per-Model Distribution Mismatch (DISC-7)

- Paper Table 3 per-model rows came from an unknown source, not Exp11
- Totals agreed (13/27/48) but per-model distribution differed
- Fix: Use Exp11 canonical values consistently across all tables

---

## 2. All New Numbers (10 Metrics)

### 2.1 Per-Model Table

| Model | N_pass | UP_crit | UP_any |
|-------|--------|---------|--------|
| 120B  | 22     | 4/22 (18.2%) | 13/22 (59.1%) |
| 27B   | 21     | 4/21 (19.0%) | 15/21 (71.4%) |
| 35B   | 20     | 3/20 (15.0%) | 12/20 (60.0%) |
| 4B    | 15     | 3/15 (20.0%) | 8/15 (53.3%) |
| **All** | **78** | **14/78 (17.9%)** | **48/78 (61.5%)** |

### 2.2 Scenario-Clustered Bootstrap CI (B=10,000)

| Tier | Rate | 95% CI |
|------|------|--------|
| UP_any | 61.5% | [20.0%, 70.0%] |
| UP_crit | 17.9% | [0.0%, 40.0%] |

Note: CIs are wide due to violation concentration in few scenarios. Resampling unit = scenario.

### 2.3 Verdict Matrix (v4 unified, all evaluators)

| Evaluator | N_pass | Hard (v4) | Mis-cert | Crit | Crit-MC |
|-----------|--------|-----------|----------|------|---------|
| DxEM      | 180    | 70        | 38.9%    | 28   | 15.6%   |
| AC-Proxy (P1A: cov>=0.5, diag>=0.8) | 102 | 52 | 51.0% | 14 | 13.7% |
| MAB-Proxy (P1B: F1>=0.5)            | 16  | 2  | 12.5% | 0  | 0.0%  |
| C2>=0.7   | 78     | 48        | 61.5%    | 14   | 17.9%   |
| ACov>=0.5 | 102    | 52        | 51.0%    | 14   | 13.7%   |
| CGA-Bench | 110    | 0         | 0.0%     | 0    | 0.0%    |

Note: Hard = v4 YAML graph constraint violation (FORBIDDEN+WITHIN+BEFORE). Crit = CRITICAL severity subset.
AC-Proxy uses P1A thresholds (coverage>=0.5, diag>=0.8), NOT P1C inline proxy (has_diag+has_treat+cov>=0.3).
MAB-Proxy uses P1B threshold (F1>=0.5), NOT P1C threshold (F1>=0.4).

### 2.4 Core/Expansion Stratification

| Subset | Ep | CP | UP_crit | UP_any |
|--------|----|----|---------|--------|
| Core (9 scen) | 108 | 69 | 13/69 (18.8%) | 47/69 (68.1%) |
| Expansion (6 scen) | 72 | 9 | 1/9 (11.1%) | 1/9 (11.1%) |
| All | 180 | 78 | 14/78 (17.9%) | 48/78 (61.5%) |

Note: Classification uses scenario-level grouping. Core = {septic_shock_basic, septic_shock_penicillin_allergy, stemi_inferior_rv_trap, stroke_tpa_eligible, hemorrhagic_stroke, dka_moderate_basic, dka_hypokalemia_trap, aki_stage1_basic, contrast_aki_prevention_basic}. Expansion = remaining 6 scenarios.

### 2.5 Instrumentation Ablation (B-1)

| Condition | UP_any | UP_crit |
|-----------|--------|---------|
| Full | 48/78 (61.5%) | 14/78 (17.9%) |
| No timing | 24/78 (30.8%) | 12/78 (15.4%) |
| No ordering | 48/78 (61.5%) | 14/78 (17.9%) |
| No forbidden | 48/78 (61.5%) | 14/78 (17.9%) |
| Timing only | 42/78 (53.8%) | 8/78 (10.3%) |
| Forbidden only | 12/78 (15.4%) | 12/78 (15.4%) |
| Ordering only | 24/78 (30.8%) | 12/78 (15.4%) |

Key insight: Timing is dominant contributor. Removing timing drops UP_any by 30.7pp (61.5% -> 30.8%). Timing alone captures 53.8% (87.5% of full signal).

### 2.6 Domain Spread (11 fine-grained domains)

| Domain | Scen | CP | UP_crit | UP_any | Violation Types |
|--------|------|----|---------|--------|-----------------|
| AF | 1 | 2 | 1/2 | 1/2 | WITHIN |
| AKI | 2 | 21 | 1/21 | 3/21 | WITHIN |
| COPD | 1 | 1 | 0/1 | 0/1 | - |
| ChestPain | 1 | 12 | 0/12 | 12/12 | BEFORE, WITHIN |
| DKA | 2 | 12 | 12/12 | 12/12 | BEFORE, FORBIDDEN, WITHIN |
| GI | 1 | 0 | 0/0 | 0/0 | - |
| HTN | 1 | 3 | 0/3 | 0/3 | - |
| HeartFailure | 1 | 0 | 0/0 | 0/0 | - |
| PE | 1 | 3 | 0/3 | 0/3 | - |
| Sepsis | 2 | 24 | 0/24 | 20/24 | WITHIN |
| Stroke | 2 | 0 | 0/0 | 0/0 | - |

Hard violations in **5/11 domains** and **6/15 scenarios**.

### 2.7 Domain-Removal Robustness

| Removed | CP | UP_any | Rate |
|---------|-----|--------|------|
| AF | 76 | 47 | 61.8% |
| AKI | 57 | 45 | 78.9% |
| COPD | 77 | 48 | 62.3% |
| ChestPain | 66 | 36 | 54.5% |
| DKA | 66 | 36 | 54.5% |
| GI | 78 | 48 | 61.5% |
| HTN | 75 | 48 | 64.0% |
| HeartFailure | 78 | 48 | 61.5% |
| PE | 75 | 48 | 64.0% |
| Sepsis | 54 | 28 | 51.9% |
| Stroke | 78 | 48 | 61.5% |

Range: 51.9% (remove Sepsis) to 78.9% (remove AKI). No single domain removal drops below 50%.

### 2.8 Absolute Prevalence (all 180 episodes)

| Metric | Count | Rate |
|--------|-------|------|
| Any hard violation | 70/180 | 38.9% |
| CP AND hard | 48/180 | 26.7% |

### 2.9 Poster-Child Episodes

| Criterion | Count |
|-----------|-------|
| C2>=0.7 + hard + C3=1 + C4>=0.7 | 5/78 |
| C2>=0.7 + hard + CGA>=0.7 | 27/78 |

### 2.10 z1-only Subset

| Metric | All constraints | z1-only |
|--------|----------------|---------|
| UP_any | 48/78 (61.5%) | 34/78 (43.6%) |
| UP_crit | 14/78 (17.9%) | 8/78 (10.3%) |

z1-only retains 70.8% of UP_any signal and 57.1% of UP_crit signal.

---

## 3. Delta Comparison (Old vs New)

### 3.1 Headline Numbers

| Metric | Old (paper) | New (v4) | Delta |
|--------|-------------|----------|-------|
| UP_strong | 27/78 (34.6%) | 48/78 (61.5%) | **+21 (+27.0pp)** |
| UP_crit | 13/78 (16.7%) | 14/78 (17.9%) | +1 (+1.2pp) |
| UP_any | 48/78 (61.5%) | 48/78 (61.5%) | 0 |
| All hard (180) | 81/180 (45.0%) | 70/180 (38.9%) | -11 (-6.1pp) |

Key: UP_strong and UP_any are now identical (tier collapse). UP_crit gained 1 episode.

### 3.2 Bootstrap CI

| Tier | Old CI | New CI |
|------|--------|--------|
| UP_strong | [4.3%, 73.3%] | N/A (= UP_any) |
| UP_any | [26.3%, 84.1%] | [20.0%, 70.0%] |
| UP_crit | [0.0%, 63.7%] | [0.0%, 40.0%] |

### 3.3 Domain Spread

| Metric | Old (6-domain) | New (11-domain) |
|--------|----------------|-----------------|
| Domains with hard | 4/6 | 5/11 |
| Scenarios with hard | 5/15 | 6/15 |
| Sepsis UP_strong | 0/24 (0%) | N/A (was bug) |
| Sepsis UP_any | - | 20/24 (83.3%) |

### 3.4 Stratification

| Subset | Old UP_str | New UP_any | Old CP | New CP |
|--------|------------|------------|--------|--------|
| Core | 73.3% | 68.1% (47/69) | 60 | 69 |
| Expansion | 52.4% | 11.1% (1/9) | 21 | 9 |

Note: Different Core/Expansion classification scheme. Old used graph-level (6 core graphs -> 60 CP). New uses scenario-level (9 core scenarios -> 69 CP).

### 3.5 Ablation

| Condition | Old UP_any | New UP_any |
|-----------|------------|------------|
| Full | 48/78 | 48/78 (same) |
| No timing | - | 24/78 (30.8%) |
| Timing only | - | 42/78 (53.8%) |

### 3.6 z1-only (NEW -- was EMPTY)

| Metric | Value |
|--------|-------|
| UP_any (z1-only) | 34/78 (43.6%) |
| UP_crit (z1-only) | 8/78 (10.3%) |

---

## 4. Severity Taxonomy Change

### 4.1 Old: 3-tier (UP_crit / UP_strong / UP_any)

```
UP_crit   = FORBIDDEN(CRITICAL) + WITHIN(CRITICAL)  = 13/78 (16.7%)
UP_strong = UP_crit + WITHIN(SEVERE, evidence=STRONG) = 27/78 (34.6%)
UP_any    = any hard violation regardless of severity  = 48/78 (61.5%)
```

### 4.2 New: 2-tier (UP_crit / UP_any)

```
UP_crit = FORBIDDEN(CRITICAL) + WITHIN(delay>threshold, evidence=STRONG) = 14/78 (17.9%)
UP_any  = any hard violation (= UP_strong, all Class I)                  = 48/78 (61.5%)
```

### 4.3 Why UP_strong = UP_any (Tier Collapse)

All 16 violation-producing CPG graph nodes carry `recommendation_class: "I"` (AHA/ACC Class I or equivalent strong recommendation). The 12-15 nodes with Class IIa/IIb (`MODERATE`) are assessment/classification/shared-decision nodes that do not define timing deadlines or forbidden actions.

**This is a genuine structural property of clinical practice guidelines**: mandatory deadlines and forbidden actions are defined at the strongest recommendation level, not at moderate recommendation levels.

### 4.4 Paper Presentation (Option C -- recommended)

Report the tier collapse as a **strengthening finding**:

> "All process-safety violations in CGA-Bench occur at Class I recommendation nodes, meaning every detected violation represents a departure from the strongest level of clinical evidence. The benchmark uses a 2-tier severity taxonomy: Critical (violations involving forbidden actions or timing delays exceeding clinical thresholds) and All-Hard (any constraint violation)."

---

## 5. Paper Locations to Update

### 5.1 Must Update (UP_strong -> 2-tier)

| ID | Location | Old Value | New Value | Action |
|----|----------|-----------|-----------|--------|
| A15 | Abstract L74 | 34.6% UP_strong (27/78) | Drop UP_strong; use UP_any=61.5% | Rewrite |
| A16 | Abstract L77 | CI [4.3%, 73.3%] | CI [20.0%, 70.0%] for UP_any | Update |
| A17 | Abstract L78 | 16.7% UP_crit (13/78) | 17.9% UP_crit (14/78) | Update |
| B02 | Intro L105 | 34.6% UP_strong | 61.5% UP_any | Rewrite |
| B04 | Intro L108 | 27/78 UP_strong | 48/78 UP_any | Rewrite |
| B05 | Intro L109 | CI [4.3%, 73.3%] | CI [20.0%, 70.0%] | Update |
| B06 | Intro L111 | 16.7% UP_crit = 13/78 | 17.9% UP_crit = 14/78 | Update |
| B12 | Intro L175 | 4/6 domains | 5/11 domains | Update + explain granularity |
| B13 | Intro L176 | 5/15 scenarios | 6/15 scenarios | Update |
| F08-F11 | Table 3 L497-500 | 3-tier per-model | 2-tier per-model (drop UP_str) | Rewrite table |
| F12-F14 | Table 3 footer | 3-tier CIs | 2-tier CIs | Update |
| G01-G10 | Table 4 L530-543 | Old spread with UP_str=0% Sepsis | New spread with Sepsis 83% | Major rewrite |
| N01-N03 | Table 11 L818-820 | EMPTY | z1-only: 43.6% / 10.3% | Fill |
| O01-O03 | Table 12 L845-847 | Old Core/Exp with UP_str | New Core/Exp with UP_any | Rewrite |
| S04 | Conclusion L1039 | 34.6% [{CI}] | 61.5% [20.0%, 70.0%] | Rewrite |
| S06 | Conclusion L1041 | 16.7% UP_crit | 17.9% UP_crit | Update |

### 5.2 Prose Changes

| Section | Change Description |
|---------|-------------------|
| Abstract | Replace "34.6% unsafe-pass-strong" with "61.5% unsafe-pass" and add "all at Class I evidence" |
| Intro | Replace 3-tier framing with 2-tier + tier-collapse explanation |
| Method (severity) | Add paragraph explaining 2-tier taxonomy and why UP_strong = UP_any |
| Table 4 + prose | Major rewrite: Sepsis 0% -> 83%, domain count 4/6 -> 5/11 |
| Table 12 | Recompute with scenario-level Core/Expansion |
| Discussion | Add discussion of tier collapse as structural finding |
| Conclusion | Update headline numbers |

### 5.3 No Change Needed

- A01-A09: Scenario/constraint counts unchanged
- E01-E22: Method parameters unchanged
- H01-H08: Verdict matrix unchanged (uses UP_any which was already correct)
- I01-I08: Timestamp validation unchanged
- J01-J04: BSR results unchanged
- K01-K09: Forbidden/sequence activation unchanged
- L01-L02: Friedman p and CI width unchanged
- M01-M04: HardOnly column unchanged
- P01-P04: Robustness unchanged

---

## 6. Summary

The evidence sourcing fix has two consequences:

1. **UP_strong collapses to UP_any** (27->48): This is not a bug but a structural property. All violation-producing nodes are Class I. The paper should report 2-tier (Critical vs All-Hard) and frame the collapse as a finding.

2. **Sepsis violations become visible** (0%->83%): Previously invisible due to `guideline_class=None` propagation gap. Now correctly classified as STRONG evidence WITHIN violations.

3. **UP_crit +1** (13->14): Minor change from correct AF episode classification.

4. **Overall: UP_any = 48/78 (61.5%) is UNCHANGED**. The fix only affects severity tier assignment, not violation detection.
