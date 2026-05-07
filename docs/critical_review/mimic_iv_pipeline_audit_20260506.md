# MIMIC-IV Scoring Pipeline Audit Report

> **Date**: 2026-05-06
> **Branch**: `eval_science`
> **Scope**: `scripts/experiments/mimic/phase0-phase6` pipeline integrity
> **Verdict**: **PAPER-BLOCKING** — 3 bugs + stale results invalidate all 18 TeX macros

---

## 1. Executive Summary

The MIMIC-IV evaluation pipeline (`scripts/experiments/mimic/`) generates construct validity
evidence for CGA-S, producing 18 TeX macros used in the paper (e.g., `\MimicIvTccAuc`,
`\MimicIvTccOr`). This audit found **3 code bugs** and **1 staleness issue** that together
mean the current `evidence_pack/mimic_iv/` results are unreliable.

**All 18 paper macros derived from MIMIC-IV are suspect until a clean re-run.**

---

## 2. Findings

### 2.1 STALE RESULTS — Severity: HIGH

**Evidence**: Phase 2/3 summary JSONs record `git_sha: "6fefe582"`. Current HEAD is `3a095252`.

Between these commits, **5 scoring-relevant changes** landed:

| Commit | Change |
|--------|--------|
| `2fbb3da0` | `feat(assessor+engine): alpha-1..5 ActionNormalizer N1-N5 + B3 forbidden symmetric normalization` |
| `c9afe414` | `feat(action-normalizer): CAV overlay loader for vocabulary extension` |
| `89afc9f1` | `feat(core): SGSC v7 schema + loader hooks` |
| `034e2a33` | `feat(constraint-derivation): authority-tier provenance for E9 audit` |
| `eec85430` | `data(graphs): authority-provenance backfill for auto/* graphs` |

The ActionNormalizer received N1-N5 rule changes and a CAV overlay loader. The MIMIC-IV
`verdict_matrix_mimic_iv.parquet` was generated **before** these changes, so every verdict
in the matrix may differ under the current normalizer.

**Impact**: All downstream phases (Phase 2 aggregate → Phase 3 predictive validity → Phase 5
clinician leaderboard → Phase 6 integrate) inherit stale data.

---

### 2.2 BUG: Deterministic Replay Missing Arguments — Severity: HIGH

**File**: `scripts/experiments/mimic/phase2_score_trajectories.py:786-790`

```python
# CURRENT (BROKEN)
ep_replay = _score_one_episode(
    cohort_row=cohort_row,
    actions=actions_replay,
    patient_state=_build_patient_state(
        cohort_row, root=root, onset_time=onset_time
    ),
    cpg_engine=cpg_engine,
    normalizer=normalizer,
    # extractor=    ← MISSING
    # scorer_config= ← MISSING
)
```

`_score_one_episode()` declares `extractor` and `scorer_config` as **required keyword-only**
arguments (line 376-387). This call raises `TypeError` at runtime.

**Consequence**: The deterministic replay gate (`_check_deterministic_replay`) has **never
successfully executed**. The contract claims "re-run scoring on 100-episode sample, verdict
flips must be 0" — this was never verified.

The existing results were likely generated with `--skip-replay-gate` or `--skip-gates`.

---

### 2.3 BUG: All Actions Typed as GIVE_MEDICATION — Severity: MEDIUM

**File**: `scripts/experiments/mimic/phase2_score_trajectories.py:396-403`

```python
action_objs = [
    Action(
        type=ActionType.GIVE_MEDICATION,  # ← ALWAYS GIVE_MEDICATION
        action_id=normalizer.normalize(a["action_id"]) if normalizer else a["action_id"],
        args=a.get("args", {}),
        timestamp_minutes=a["timestamp_minutes"],
        justification=None,
    )
    for a in actions
]
```

Canonical actions and their correct types:

| Canonical Action | Correct ActionType | Currently Assigned |
|------------------|--------------------|-------------------|
| `administer_antibiotics` | `GIVE_MEDICATION` | `GIVE_MEDICATION` ✓ |
| `obtain_blood_culture` | `ORDER_LAB` | `GIVE_MEDICATION` ✗ |
| `measure_lactate` | `ORDER_LAB` | `GIVE_MEDICATION` ✗ |
| `iv_crystalloid_bolus` | `GIVE_MEDICATION` | `GIVE_MEDICATION` ✓ |
| `start_vasopressor_if_hypotensive` | `GIVE_MEDICATION` | `GIVE_MEDICATION` ✓ |

2 of 5 canonical actions are mis-typed. If `ViolationExtractor` or `EVALUATOR_REGISTRY`
verdict functions branch on `action.type`, violation detection is distorted for lab-order
actions.

---

### 2.4 SCORER CONFIG DIVERGENCE — Severity: MEDIUM

**MIMIC-IV Phase 2** hardcodes its own `ViolationExtractorConfig` at line 488-505.
**Main benchmark** (`run_benchmark.py:388-412`) defines `get_default_violation_extractor_config()`.

**Diff**:

| `harm_severity_mappings` | Main Benchmark | MIMIC-IV Phase 2 |
|--------------------------|----------------|------------------|
| `antibiotic` | MAJOR | MAJOR |
| `lactate` | MODERATE | MODERATE |
| `blood_culture` | MODERATE | MODERATE |
| `vasopressor` | MAJOR | MAJOR |
| `crystalloid` | MODERATE | MODERATE |
| **`ecg`** | **MAJOR** | **MISSING** |
| **`troponin`** | **MODERATE** | **MISSING** |
| **`cath_lab`** | **SEVERE** | **MISSING** |
| **`nitro`** | **SEVERE** | **MISSING** |
| **`aspirin`** | **MODERATE** | **MISSING** |
| fallback `""` | MINOR | MINOR |

The main benchmark has **5 additional severity mappings** (ecg, troponin, cath_lab, nitro,
aspirin) that MIMIC-IV Phase 2 lacks. For SSC Hour-1 sepsis episodes these specific mappings
are unlikely to trigger (they're chest pain / ACS patterns), so the practical impact on
the current sepsis-only cohort is **low**. However, if the MIMIC-IV cohort is ever expanded
beyond sepsis, these missing mappings would cause scoring divergence.

The `HarmScorerConfig` (severity_weights, guideline_strength_weights, violation_type_weights)
is **identical** between both — no divergence there.

---

### 2.5 CwT = 0.0% Gate Bypass — Severity: LOW

Phase 2 sanity gate requires `CWT_LOWER (0.25) <= cwt <= CWT_UPPER (0.75)`.
Actual CwT pass rate = 0.0%. The results exist, meaning `--skip-gates` was used.

This is a known characteristic of retrospective clinical data (real clinicians don't
perfectly follow time-sensitive protocols), but the bypass should be documented.

---

## 3. Current MIMIC-IV Result Values (suspect)

From `evidence_pack/mimic_iv/`:

| Metric | Value | Source Phase |
|--------|-------|-------------|
| N episodes | 500 | Phase 2 |
| TCC pass rate | 0.414 | Phase 2 |
| ASC pass rate | 0.344 | Phase 2 |
| CwT pass rate | **0.000** | Phase 2 |
| PAF pass rate | 0.510 | Phase 2 |
| Strict consensus (ASC∩CwT∩PAF) | **0.000** | Phase 2 |
| Median compliance | **0.000** | Phase 2 |
| TCC OR (predictive validity) | 1.379 | Phase 3 |
| TCC AUC | 0.654 | Phase 3 |
| NRI (TCC vs ASC) | 0.196 | Phase 3 |

---

## 4. Fix Plan

### Fix 1: Deterministic Replay Args (Bug 2.2)

Add missing `extractor` and `scorer_config` to the replay path.

```python
# FIXED
ep_replay = _score_one_episode(
    cohort_row=cohort_row,
    actions=actions_replay,
    patient_state=_build_patient_state(
        cohort_row, root=root, onset_time=onset_time,
        vitals_at_onset=_resolve_vitals_at_onset(
            chartevents_by_hadm, int(cohort_row["hadm_id"]), onset_time
        ),
        labs_at_onset=_resolve_labs_at_onset(
            labs_by_hadm, int(cohort_row["hadm_id"]), onset_time
        ),
    ),
    cpg_engine=cpg_engine,
    normalizer=normalizer,
    extractor=extractor,
    scorer_config=scorer_config,
)
```

### Fix 2: ActionType Mapping (Bug 2.3)

Add a canonical-action → ActionType lookup:

```python
ACTION_TYPE_MAP: dict[str, ActionType] = {
    "administer_antibiotics": ActionType.GIVE_MEDICATION,
    "obtain_blood_culture": ActionType.ORDER_LAB,
    "measure_lactate": ActionType.ORDER_LAB,
    "iv_crystalloid_bolus": ActionType.GIVE_MEDICATION,
    "start_vasopressor_if_hypotensive": ActionType.GIVE_MEDICATION,
}
```

### Fix 3: Import Scorer Config from Main Benchmark (Bug 2.4)

Replace the hardcoded `_build_extractor_and_scorer_config()` with an import:

```python
from run_benchmark import (
    get_default_violation_extractor_config,
    get_default_harm_scorer_config,
)
```

### Fix 4: Re-run Phase 0-6

After code fixes, execute the full pipeline:
```bash
PYTHONPATH=. python scripts/experiments/mimic/phase0_setup.py
PYTHONPATH=. python scripts/experiments/mimic/phase0_action_mapping.py
PYTHONPATH=. python scripts/experiments/mimic/phase2_score_trajectories.py
PYTHONPATH=. python scripts/experiments/mimic/phase2_aggregate.py
PYTHONPATH=. python scripts/experiments/mimic/phase3_predictive_validity.py
PYTHONPATH=. python scripts/experiments/mimic/phase4_witness_pairs.py
PYTHONPATH=. python scripts/experiments/mimic/phase5_clinician_leaderboard.py
PYTHONPATH=. python scripts/experiments/mimic/phase6_integrate.py
```

Verify that:
- New `git_sha` matches current HEAD
- Deterministic replay gate passes (0 flips)
- CwT pass rate is documented (if still 0%, document explicitly why)
- All 18 paper macros update consistently

---

## 5. Risk Assessment

| If we do nothing | Consequence |
|------------------|-------------|
| Submit paper as-is | Reviewer can reproduce Phase 2, get different numbers. 18 macros don't match reproducible output. |
| Fix bugs, skip re-run | Code is correct but evidence_pack is still stale. Same reproducibility risk. |
| Fix bugs + re-run | Clean state. Numbers may change (especially TCC OR/AUC). Need to verify Phase 3 signal survives. |

**Recommendation**: Fix + re-run is the only defensible path. If Phase 3 predictive validity
degrades after the fix (e.g., TCC AUC drops below 0.55 or OR confidence interval crosses 1.0),
consider dropping MIMIC-IV from the paper rather than presenting stale results.
