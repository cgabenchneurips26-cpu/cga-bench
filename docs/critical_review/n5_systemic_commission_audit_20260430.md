# N5 Systemic COMMISSION Audit — 2026-04-30

## 1. Bug Class Definition

The bug class is a **schema-vocabulary mismatch** in scripts that filter the `viol_types` field of `verdict_matrix_v6.json` per-episode entries. The verdict matrix encodes violation types using the constraint-layer vocabulary `{WITHIN, FORBIDDEN, BEFORE}` — uppercase, matching the CPG graph constraint types. Several scripts were written using the *assessor-layer* vocabulary `{COMMISSION, TIMING, SEQUENCE, OMISSION, DEVIATION}` — a different enumeration that maps many-to-one into the constraint layer. Any script that reads `ep.get("viol_types")` from verdict_matrix and then compares against `"COMMISSION"` will silently produce zero for the filtered count, because the literal `"COMMISSION"` never appears in that field. The bug is silent: no exception is raised, no warning is emitted, and the resulting macro or statistic is injected into paper outputs as `0`.

## 2. Schema Confirmation

`evidence_pack/analysis/verdict_matrix_v6.json` per-episode entries carry `viol_types` as a list of strings. The confirmed vocabulary — established by sampling 200 episodes and by reading the producer script `verdict_matrix_v4.py` (line 348: `"viol_types": sorted({v["constraint_type"] for v in r.v4_viols})`) — is:

| Token | Meaning | Assessor-layer equivalent |
|---|---|---|
| `WITHIN` | Timing constraint violated | `TIMING` |
| `FORBIDDEN` | Forbidden action performed | `COMMISSION` |
| `BEFORE` | Sequence constraint violated | `SEQUENCE` |

`COMMISSION`, `OMISSION`, `TIMING`, `SEQUENCE`, and `DEVIATION` do **not** appear in this field. Those tokens appear only in `violation_events[*].violation_type` inside raw episode JSON files — a completely separate channel.

## 3. Full Inventory

| Script | Line(s) | Token(s) used | Data channel | Class |
|---|---|---|---|---|
| `scripts/experiments/refresh_paper_macros.py` | 212 | `{"COMMISSION"}` vs `viol_types` | verdict_matrix `viol_types` | **A — FIXED** (commit d5ada272) |
| `scripts/experiments/compute_table26_bsr_per_model.py` | 209 | `{"COMMISSION"}` vs `viol_types` | verdict_matrix `viol_types` | **A — ACTIVE BUG** |
| `scripts/experiments/exp_e30_non_timing_trap.py` | 208 | `"FORBIDDEN"`, `"BEFORE"` in `viol_types` | verdict_matrix `viol_types` | **Correct vocabulary — safe** |
| `scripts/experiments/exp_e39e_safety_core_overlay.py` | 105–106 | `"FORBIDDEN"`, `"BEFORE"` in `viol_types` | verdict_matrix `viol_types` | **Correct vocabulary — safe** |
| `scripts/experiments/exp_e39c_node_authority_spotcheck.py` | 129 | `{"FORBIDDEN": 0, "WITHIN": 1, "BEFORE": 2}` priority dict | verdict_matrix `viol_types` | **Correct vocabulary — safe** |
| `scripts/experiments/exp_exact_dg.py` | 72–81 | `VIOL_TYPE_TO_TIER` mapping includes both `"FORBIDDEN"` and `"COMMISSION"` as aliases → `"forbid"` | verdict_matrix `viol_types` | **Defensive alias — safe** (COMMISSION key is dead but FORBIDDEN is correctly handled; no count is silently zeroed) |
| `scripts/experiments/exp_e2_bsr.py` | 156 | reads `ep.get("viol_types", [])` verbatim, no comparison | verdict_matrix `viol_types` | **Pass-through — safe** |
| `scripts/experiments/exp_strict_consensus_fa.py` | 93–94 | reads `viol_types` into Counter verbatim | verdict_matrix `viol_types` | **Pass-through — safe** |
| `scripts/experiments/exp_e39g_s2_diversity.py` | 171 | reads `viol_types` into Counter verbatim | verdict_matrix `viol_types` | **Pass-through — safe** |
| `scripts/experiments/ws6_select_poster_children.py` | 177–182 | lowercases then checks `"forbidden"`, `"within"`, `"within"`, `"commission"` | verdict_matrix `viol_types` | **Partial bug** (see §4) |
| `scripts/experiments/exp_e39b_threshold_sweep.py` | 104–117 | reads `viol_types` verbatim, no comparison | verdict_matrix `viol_types` | **Pass-through — safe** |
| `scripts/experiments/exp_e39_high_authority_core.py` | 656–669 | reads `viol_types` verbatim | verdict_matrix `viol_types` | **Pass-through — safe** |
| `scripts/experiments/exp_e27_timing_stress.py` | 274 | reads `per_episode`, filters on `"WITHIN"` only | verdict_matrix `viol_types` | **Correct vocabulary — safe** |
| `scripts/experiments/aggregate_ex_w8_crossmodel.py` | 78,153 | `HARD_VIOL_TYPES = {"commission","timing","sequence"}` but reads from `violation_events` via `_classify_violation_type` | raw episode `violation_events` | **B — different channel, safe** |
| `scripts/experiments/aggregate_heldout_v6.py` | 24,62 | `HARD_VIOL_TYPES = {"commission","timing","sequence"}` with substring check | raw episode data | **B — safe** |
| `scripts/experiments/_episode_cache.py` | 46,132 | `HARD_VIOL_TYPES = {"commission","timing","sequence"}` via `_classify_violation_type` | raw episode `violation_events` | **B — safe** |
| `scripts/experiments/exp_e18_artifact_mimic.py` | 95–116 | uses `_classify_violation_type` on `violation_events` | raw episode `violation_events` | **B — safe** |
| `scripts/experiments/exp_e23_artifact_mimic_ablation.py` | 98,106–107 | uses `_classify_violation_type` on `violation_events` | raw episode `violation_events` | **B — safe** |
| `scripts/experiments/exp_e24_fa_severity.py` | 83–94 | uses `_classify_violation_type` on `violation_events` | raw episode `violation_events` | **B — safe** |
| `scripts/experiments/exp_e29_heldout_domain.py` | 91–95 | uses `_classify_violation_type` via `.upper().strip()` | raw episode `violation_events` | **B — safe** |
| `scripts/experiments/exp_e21_model_diversity.py` | 78,170 | lowercase `HARD_VIOL_TYPES` via `_classify_violation_type` | raw episode `violation_events` | **B — safe** |
| `scripts/experiments/exp_e37_scaffold_three_way.py` | 62 | lowercase `HARD_VIOL_TYPES` | raw episode `violation_events` | **B — safe** |
| `scripts/experiments/exp_e3_instrumentation_ablation.py` | 80–110 | `"FORBIDDEN"/"WITHIN"/"BEFORE"` used in verdict_matrix context | verdict_matrix `viol_types` | **Correct vocabulary — safe** |
| `scripts/experiments/verdict_matrix_v4.py` | 229–265 | producer — writes `constraint_type` which IS `FORBIDDEN/WITHIN/BEFORE` | producer, not consumer | **D — safe** |
| `scripts/experiments/verdict_matrix_v5.py` | 73–81 | maps lowercase→uppercase (`"commission"→"FORBIDDEN"`) in producer | producer | **D — safe** |
| `scripts/cp3_validate.py` | 67 | uses `.upper()` before comparison | raw episode | **C — safe** |
| `scripts/compute_bayes_error.py` | 45–48 | imports `HARD_VIOL_TYPES` from `_episode_cache`; reads `violation_events` | raw episode `violation_events` | **B — safe** |
| `scripts/pre_post_fix_comparison.py` | 333 | `violations_by_type` dict, lowercase | raw episode dict | **B — safe** |
| `scripts/experiments/analyze_clinician_absolute.py` | 719,1007 | lowercase tuple | raw episode | **B — safe** |
| `scripts/experiments/generate_appendix_tables.py` | 383,448,456 | lowercase | raw episode | **B — safe** |
| `scripts/experiments/exp_e39d_severity_overlay.py` | 78 | uses imported `HARD_VIOLATION_TYPES` (lowercase) | raw episode | **B — safe** |
| `scripts/generate_canonical_numbers.py` | 130–132 | `census.get("FORBIDDEN",...)` — reads from `v3_constraint_audit.json`, not verdict_matrix `viol_types` | constraint audit JSON | **D — safe** |

## 4. High-Risk Findings

### Finding 1 — CRITICAL: `compute_table26_bsr_per_model.py:209`

**File:** `scripts/experiments/compute_table26_bsr_per_model.py`
**Line:** 209
**Code:**
```python
types = set(ep.get("viol_types") or [])   # reads verdict_matrix per_episode
...
if types == {"COMMISSION"}:                # BUG: never matches; actual token is "FORBIDDEN"
    n_non_timing_forbid_only += 1
```

**What it does:** This is the `emit_main_body_macros()` function. It iterates over all per-episode entries from `verdict_matrix_v6.json`, classifies each episode into timing-only (`{"WITHIN"}`), non-timing natural, non-timing FORBIDDEN-only, or non-timing BEFORE-only buckets. Line 209 specifically counts episodes whose sole violation type is a forbidden-action violation — but uses the wrong token `"COMMISSION"` instead of `"FORBIDDEN"`, so `n_non_timing_forbid_only` is always `0`.

**What it writes:** The counter directly populates macro `\nonTimingForbiddenOnly` at line 261:
```python
macros["nonTimingForbiddenOnly"] = fmt_int(n_non_timing_forbid_only)
```
This macro is then injected directly into `paper/auto_numbers.tex`, `paper/auto_numbers_v6.tex`, and `paper/auto_numbers_v18.tex` (lines 51–53 and `patch_auto_numbers()` at line 267). The paper cites `\nonTimingForbiddenOnly` in claims about how many episodes contain only non-timing forbidden-action violations — a key claim for Section 5 / Table 1.

**Severity:** CRITICAL — identical bug class to the just-fixed `refresh_paper_macros.py:212`, same output destination (`auto_numbers.tex`), same macro name (`\nonTimingForbiddenOnly`). The two scripts are parallel implementations of the same paper macro injection; both were affected.

**Fix:** Change line 209 from `if types == {"COMMISSION"}:` to `if types == {"FORBIDDEN"}:`.

---

### Finding 2 — LOW: `ws6_select_poster_children.py:179`

**File:** `scripts/experiments/ws6_select_poster_children.py`
**Lines:** 177–182
**Code:**
```python
viol_types_lower = [v.lower() for v in viol_types]
has_forbidden = "forbidden" in viol_types_lower or "commission" in viol_types_lower
has_timing   = "timing"    in viol_types_lower or "within"    in viol_types_lower
has_sequence = "sequence"  in viol_types_lower
```

**What it does:** Selects "poster child" case studies for the paper. It reads `viol_types` from verdict_matrix, lowercases, then checks for both vocabulary systems (`"forbidden" or "commission"`, `"timing" or "within"`). The `"commission"` check is a dead alias — it never matches since verdict_matrix always carries `"FORBIDDEN"` (which maps to `"forbidden"` after lowercasing). The `"forbidden"` check correctly catches all actual forbidden-action episodes.

**Effect:** The `has_forbidden` flag correctly identifies all FORBIDDEN episodes via the `"forbidden"` branch. The `"commission"` branch is dead code but does not cause miscounting — it's OR-logic with a working branch. Similarly `has_sequence` misses `"before"` (sequence violations appear as `"BEFORE"` in verdict_matrix), so episodes with pure BEFORE violations will not be flagged as `has_sequence`.

**Output destination:** `evidence_pack/` case study selection JSON — not directly injected into `auto_numbers.tex`. Internal analysis only.

**Severity:** LOW — `has_forbidden` is correctly covered; `has_sequence` is slightly incorrect (misses `"BEFORE"` episodes) but this affects only poster-child selection heuristics, not paper numbers. The `"commission"` dead alias is confusing but not harmful.

**Fix:** Replace with:
```python
has_forbidden = "forbidden" in viol_types_lower   # "commission" is dead alias
has_timing    = "within"    in viol_types_lower    # "timing" is dead alias
has_sequence  = "before"    in viol_types_lower    # "sequence" is dead alias
```

---

## 5. Conclusion

**Is the `refresh_paper_macros.py` bug isolated or systemic?**

The bug is **partially systemic but contained to two scripts**. The root cause — writing assessor-layer vocabulary (`COMMISSION/TIMING/SEQUENCE`) when comparing against verdict_matrix constraint-layer vocabulary (`FORBIDDEN/WITHIN/BEFORE`) — appears in exactly two paper-feeding scripts:

| Rank | Script | Macro affected | Severity |
|---|---|---|---|
| 1 | `scripts/experiments/compute_table26_bsr_per_model.py:209` | `\nonTimingForbiddenOnly` in `auto_numbers.tex` | **CRITICAL** |
| 2 | `scripts/experiments/refresh_paper_macros.py:212` | `\nonTimingForbiddenOnly` in `auto_numbers.tex` | CRITICAL — **FIXED** d5ada272 |
| 3 | `scripts/experiments/ws6_select_poster_children.py:182` | poster child `has_sequence` flag | LOW — internal only |

**One-line fixes:**

- `compute_table26_bsr_per_model.py:209` — change `{"COMMISSION"}` → `{"FORBIDDEN"}`
- `ws6_select_poster_children.py:182` — change `"sequence" in viol_types_lower` → `"before" in viol_types_lower` (and remove dead `"commission"` / `"timing"` aliases)

The ~60 other verdict_matrix readers are safe: they either use the correct constraint-layer vocabulary (`FORBIDDEN/WITHIN/BEFORE`), read from the separate `violation_events` channel via `_classify_violation_type()`, or are pass-through aggregators that do not filter on specific type tokens.

## 6. Out of Scope — Scripts Safe by Construction (Class B)

The following scripts reference `commission/omission/timing/sequence/deviation` (lowercase) but operate exclusively on `violation_events[*].violation_type` from raw episode JSON — a distinct channel with distinct vocabulary. They are immune to the verdict_matrix viol_types bug by architectural separation:

`aggregate_ex_w8_crossmodel.py`, `aggregate_heldout_v6.py`, `_episode_cache.py`, `compute_bayes_error.py`, `exp_e18_artifact_mimic.py`, `exp_e21_model_diversity.py`, `exp_e23_artifact_mimic_ablation.py`, `exp_e24_fa_severity.py`, `exp_e29_heldout_domain.py`, `exp_e37_scaffold_three_way.py`, `recompute_v6_full_severity.py`, `pre_post_fix_comparison.py`, `analyze_clinician_absolute.py`, `generate_appendix_tables.py`, `_swap_scorer.py`, `phase1_rescore.py`, `cross_validation.py`, `ws6_error_taxonomy.py`, `exp_e39_amega_cross_benchmark.py`, `p8_clinician_survey.py`.
