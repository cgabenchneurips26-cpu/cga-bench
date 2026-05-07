# SGSC-8 Bridge Template: v6 Clinician Verdicts → v7 Atom Evidence

> **Document type**: TEMPLATE — all `{GUIDELINE}_XXX` atom IDs are placeholders.
> Replace with actual IDs once SGSC-3 atom proposals arrive (Day 2).
>
> **Purpose**: Map "clinician said action X was inappropriate in trajectory Y"
> to "atom Z's constraint was violated" for NeurIPS App.~Z.7 provenance claims.
>
> **Status**: Awaiting SGSC-3 output. Do NOT edit atom_id columns until Day 2
> atom proposal results are confirmed.
>
> **Author**: Tooling team, 2026-04-30.
> **Related docs**:
> - `docs/sgsc/260430_scn012_bridge.md` — SCN-012 worked example (D5)
> - `docs/sgsc/260430_sgsc_composition.md` — R4 Bridge protocol, Day-by-day plan
> - `clinician_validation/result/` — raw rater submissions

---

## 1. Purpose and Scope

### 1.1 What This Template Is

This document is a **pre-population frame** for the SGSC-8 clinician bridge
mapping step. It establishes the mapping protocol, column definitions, and
worked example so that when SGSC-3 atom proposal results arrive, the team can
fill in actual atom IDs without re-designing the structure.

All atom IDs in this document use the placeholder format `{GUIDELINE}_XXX`
(e.g., `{pe}_003`, `{sepsis}_007`). These must be replaced with the canonical
`atom_id` values emitted by `atom_proposer` before any paper citation.

### 1.2 Clinician Data in Scope

| Rater | Specialty / Experience | Data available | Format |
|-------|------------------------|----------------|--------|
| rater_015 | Family Medicine, 11–20 years | Apr 29 (submitted) | CSV + JSON |
| rater_030 | TBD | Apr 30 (expected) | CSV + JSON |

Both raters reviewed **v6 trajectories**: episodes drawn from the
706-scenario × 8-model × 3-run corpus (16,944 episodes total). Their verdicts
are expressed in **Korean** and cover per-action ratings plus overall adherence
scores.

The SCN-012 PE scoring gap analysis (`clinician_validation/result/SCN-012_PE_scoring_gap_analysis.md`)
is a primary anchor case and is treated as the reference example throughout
this template (see Section 6).

### 1.3 Target Output: App.~Z.7 Atom Provenance

NeurIPS App.~Z.7 must demonstrate that at least a representative subset of
v7 atoms are supported by independent clinician adjudication, not solely by
automated scoring. This bridge mapping is the evidentiary chain that makes
that claim defensible:

```
clinician verdict (v6 trajectory) → atom_id (v7 corpus) → constraint type → paper claim
```

Phase H `ClinicianValidationPacket` (100/100/60/60 structure) is the
downstream consumer of the evidence assembled here.

---

## 2. v6 Clinician Data Inventory

### 2.1 Per-Rater Data Fields

Each clinician submission file contains the following fields. These are the
source columns for the mapping table in Section 3.

| Field | Type | Description |
|-------|------|-------------|
| `scenario_id` | string | v6 scenario identifier (e.g., `SCN-012`, `stemi_rv_trap_001`) |
| `action_id` | string | Agent action from the trajectory (normalized or raw) |
| `rating` | int 1–5 | Per-action clinical appropriateness (1=inappropriate, 5=appropriate) |
| `verdict_text` | string (Korean) | Free-text justification from rater |
| `adherence_score` | int 1–5 | Overall scenario adherence score (Q1) |
| `trainee_acceptable` | int 1–5 | Would this be acceptable from a trainee? (Q3) |
| `worst_severity` | enum | minor / moderate / major / catastrophic (Q4) |

### 2.2 Data Locations

```
clinician_validation/submissions/rater_015/          # raw JSON per scenario
clinician_validation/submissions/rater_030/          # expected Apr 30
clinician_validation/result/SCN-012_PE_scoring_gap_analysis.md
clinician_validation/result/                         # per-scenario summary CSVs
```

### 2.3 Known High-Signal Cases (pre-fill candidates for Day 2)

The following cases are known in advance to have strong clinician signal and
likely v7 atom coverage. These should be mapped first when SGSC-3 results arrive.

| scenario_id | Rater | Key finding | Expected v7 guideline |
|-------------|-------|-------------|----------------------|
| SCN-012 | rater_015 | Zero thrombolysis + zero alternative in massive PE | `pulmonary_embolism` |
| stemi_rv_trap_* | rater_015/030 | Nitrate trap (RV infarct contraindication) | `aha_chest_pain_evaluation` |
| sepsis_esrd_* | rater_030 | Fluid overload omission in ESRD | `ssc_sepsis_hour1_bundle` |
| dka_hyperkalemia_* | rater_015 | K⁺>5.5 bypass not flagged | `ada_dka_management` |

---

## 3. Mapping Protocol: Trajectory → Atom

### 3.1 Column Definitions

The primary mapping artifact is the table below. One row = one
(clinician verdict, v7 atom) pair. Multiple rows may share the same
`v6_scenario_id` (1:N) or the same `v7_atom_id` (N:1).

| v6_scenario_id | v6_action_id | clinician_rating | clinician_verdict (Korean) | → v7_atom_id | v7_constraint_type | mapping_confidence | notes |
|---|---|---|---|---|---|---|---|
| *(placeholder)* | *(placeholder)* | *(1–5)* | *(Korean text)* | `{guideline}_XXX` | REQUIRED / FORBIDDEN / ALTERNATIVE | high / medium / low | |

### 3.2 Mapping Rules

**Rule M1 — Direct 1:1 match**: When `v6_action_id` (after normalization via
`ActionNormalizer`) equals `atom.action.canonical_id`, create a single mapping
row. `mapping_confidence = high`.

**Rule M2 — 1:N expansion**: When a single clinician verdict covers multiple
constraint types on the same action (e.g., "antibiotics timing wrong" implies
both a TIMING atom and a SEQUENCE atom), create one row per atom. Set
`mapping_confidence = medium` and note the expansion reason.

Example:
```
verdict: "혈액배양 전에 항생제 투여" (antibiotics given before blood culture)
→ {sepsis}_timing_001  (TIMING constraint violated)
→ {sepsis}_seq_002     (SEQUENCE constraint violated: blood_culture BEFORE antibiotics)
```

**Rule M3 — N:1 convergence**: When multiple clinician comments across
different actions all point to the same atom (e.g., multiple "should have
given thrombolysis" references for the same patient), create one row for the
atom with a comma-separated list of `v6_action_id` values. Set
`mapping_confidence = high` if ≥ 2 independent rater comments agree.

**Rule M4 — UNMAPPED**: When a clinician comment refers to an action not
present in the v7 atom set for that guideline, mark the row:
- `v7_atom_id = UNMAPPED`
- `v7_constraint_type = N/A`
- `mapping_confidence = low`
- `notes`: flag for atom_proposer review (may indicate a missing atom)

UNMAPPED rows feed the Day 3 atom gap analysis; do not discard them.

### 3.3 Pre-populated Placeholder Rows

The rows below use placeholder atom IDs. Fill actual IDs after SGSC-3 output.

| v6_scenario_id | v6_action_id | clinician_rating | clinician_verdict | → v7_atom_id | v7_constraint_type | mapping_confidence | notes |
|---|---|---|---|---|---|---|---|
| SCN-012 | `give_systemic_thrombolysis` (absent) | 1 | "thrombolysis 시행되지 않음" | `{pe}_001` | REQUIRED | high | See Section 6; pe.001 placeholder |
| SCN-012 | `surgical_embolectomy` (absent) | 1 | "embolectomy 검토했어야" | `{pe}_003` | ALTERNATIVE | high | Alternative path; pe.003 placeholder |
| SCN-012 | `assess_wells_score` | 2 | "고위험에 저위험 검사" | `{pe}_guard_001` | GUARD | medium | Inappropriate in shock; new atom TBD |
| stemi_rv_trap_* | `give_nitroglycerin` | 1 | "RV 경색 금기약 투여" | `{aha_chest}_forb_001` | FORBIDDEN | high | RV infarct nitroglycerin trap |
| sepsis_esrd_* | `give_crystalloid_30ml_kg` | 2 | "ESRD 환자 과도한 수액" | `{sepsis}_guard_002` | GUARD | medium | ESRD bypass; fluid overload risk |
| dka_hyperkalemia_* | `give_insulin` (absent) | 1 | "K⁺>5.5 에서 인슐린 안 씀" | `{dka}_001` | REQUIRED | medium | Conditional on K⁺ threshold |

---

## 4. Phase H Validation Packet Integration

The `ClinicianValidationPacket` produced by `sgsc/validation_packet.py` has
four item buckets (100 atoms / 100 constraints / 60 scenarios / 60 traces).
The bridge mapping provides external validation evidence that flows into each
bucket as described below.

### 4.1 Atoms Bucket (target: 100 items)

For each atom that appears in the mapping table (Section 3), the bridge
provides a `source_excerpt` field for the corresponding `ClinicianReviewItem`:

```
source_excerpt = f"[Clinician rater_{id}: rating={rating}] {verdict_text_translated}"
```

This excerpt supplements the guideline quote from `SourceReference.quote`.
When both a guideline quote and a clinician rating exist for the same atom,
the `display_payload` gains a `clinician_validation` sub-dict:

```json
{
  "clinician_validation": {
    "rater_id": "rater_015",
    "rating": 1,
    "verdict_translated": "Thrombolysis not performed in hemodynamically unstable patient",
    "mapping_confidence": "high"
  }
}
```

Atoms backed by at least one `mapping_confidence = high` row are candidates
for the 30-atom spot-check (Day 3, Section 7).

### 4.2 Constraints Bucket (target: 100 items)

Each `DerivedConstraint` that corresponds to a clinician-flagged action gains
a `clinician_evidence` annotation in the constraint dict before it is written
to `harness_report.constraints_path`. The annotation carries:

- `rater_id`: source rater
- `v6_scenario_id`: originating trajectory
- `clinician_rating`: 1–5 score
- `mapping_confidence`: from Rule M1–M4

Constraints with `clinician_evidence` satisfy the App.~Z.7 requirement for
"independent clinical validation of constraint encoding".

### 4.3 Scenarios Bucket (target: 60 items)

The `adherence_score` from clinician Q1 feeds `scenario.difficulty_calibration`
in the public scenario dict. High disagreement between `adherence_score` and
the v7 CGA score flags a scenario for the Day 3 gap analysis:

```python
flag_for_review = abs(adherence_score_normalized - cga_score) > 0.4
```

where `adherence_score_normalized = (adherence_score - 1) / 4` (maps 1–5 → 0.0–1.0).

### 4.4 Traces Bucket (target: 60 traces)

The per-action `rating` array from each clinician submission is the ground
truth for `ClinicianReviewItem` of type `trace`. The `trace_summary` field in
`display_payload` is populated with:

```json
{
  "n_actions": 12,
  "n_flagged_inappropriate": 5,
  "clinician_adherence": 1,
  "worst_severity": "major",
  "actions": [
    {"action_id": "assess_wells_score", "rating": 2, "verdict": "고위험에 저위험 검사"},
    ...
  ]
}
```

This provides the `trace`-type reviewer with per-action ground truth so they
can assess whether the v7 violation verdict matches clinical judgment (per
`_TRACE_QUESTIONS`).

---

## 5. Clinician Communication Protocol

The following template message (Korean) should be sent to rater_015 and
rater_030 when Phase H spot-check requests are ready (Day 3, after 30-atom
selection).

### 5.1 Message Template (Korean)

---

안녕하세요 선생님,

지난번에 v6 시나리오들을 검토해 주셔서 감사합니다. 선생님의 평가가 현재
진행 중인 v7 데이터셋 개선 작업에 직접 활용되고 있어서 연락드립니다.

**v6 → v7 변경 사항**

기존에 검토하신 시나리오들은 수작업으로 작성된 706개 시나리오(v6)에
기반합니다. v7에서는 *RecommendationAtom*이라는 구조화된 형식으로 각 임상
가이드라인의 핵심 권고 사항을 자동으로 인코딩합니다. 각 atom은 다음을
포함합니다:

- 임상 행동 (`action.canonical_id`)
- 제약 유형 (REQUIRED / FORBIDDEN / ALTERNATIVE)
- 원문 가이드라인 인용문과 근거 수준

**선생님의 v6 평가가 여전히 유효한 이유**

선생님께서 "부적절하다"고 평가하신 행동들은 v7 atom 인코딩의 **외부
검증 근거**로 직접 활용됩니다. 예를 들어, SCN-012에서 "thrombolysis 시행되지
않음"이라고 지적하신 내용은 v7 `pe.001` atom(ESC 2019 Class I, REQUIRED)의
임상 타당성을 뒷받침하는 독립적 증거입니다.

**추가 검토 요청 (30개 atom)**

SGSC-3 atom 제안 결과를 바탕으로 임상 도메인별로 선별된 30개 atom에 대해
간략한 추가 검토를 부탁드릴 예정입니다. 항목당 약 5분, 총 2–3시간 소요
예상입니다. 구체적인 내용은 별도 파일로 전달해 드리겠습니다.

감사합니다.

---

### 5.2 Translation Note for Paper

When citing clinician verdicts in App.~Z.7, provide both the original Korean
and an English translation. Format:

```
Original: "고위험 상황에 저위험 상태 검사 시행, thrombolysis 시행되지 않음."
Translation: "Low-risk screening tests performed in a high-risk situation; thrombolysis not performed."
```

---

## 6. SCN-012 Worked Example

This section provides a fully resolved mapping for the SCN-012 saddle PE case
as the reference pattern for all other cases. The actual atom IDs (`pe.001`–
`pe.005`) are pre-confirmed from `docs/sgsc/260430_scn012_bridge.md` and are
not placeholders.

### 6.1 v6 Trajectory Summary

| Field | Value |
|-------|-------|
| Scenario | Saddle PE, bilateral, massive RV failure |
| Model | qwen4b run 1 |
| Actions | 12 total, 0 thrombolysis, 0 embolectomy, 0 anticoagulation |
| v6 CGA score | **1.000** (spuriously perfect — conditional rules never evaluated) |
| Clinician adherence (Q1) | **1 / 5** |
| Clinician worst severity | **major** |
| Clinician verdict | "고위험 상황에 저위험 상태 검사 시행, thrombolysis 시행되지 않음." |

### 6.2 Completed Mapping Table

| v6_scenario_id | v6_action_id | clinician_rating | clinician_verdict | → v7_atom_id | v7_constraint_type | mapping_confidence | notes |
|---|---|---|---|---|---|---|---|
| SCN-012 | `give_systemic_thrombolysis` (absent) | 1 | "thrombolysis 시행되지 않음" | `pe.001` | REQUIRED | high | Rule M1: exact canonical_id match; ESC 2019 Class I |
| SCN-012 | `give_systemic_thrombolysis` (absent) | 1 | "recent_surgery 금기 고려" | `pe.002` | FORBIDDEN | high | Rule M2 expansion from same verdict; GUARD_TRUE active |
| SCN-012 | `surgical_embolectomy` (absent) | 1 | "embolectomy 검토했어야" | `pe.003` | ALTERNATIVE | high | Rule M1: clinician named alternative explicitly |
| SCN-012 | `catheter_directed_thrombolysis` (absent) | 1 | "catheter-directed therapy 미시행" | `pe.004` | ALTERNATIVE | medium | Rule M2 expansion; implied by rater_015 comment |
| SCN-012 | `consult_interventional_radiology` (absent) | 1 | "IR 협진 없음" | `pe.005` | REQUIRED | medium | Rule M2 expansion; prerequisite for pe.003/pe.004 |
| SCN-012 | `assess_wells_score` | 2 | "고위험에 저위험 검사" | UNMAPPED | N/A | low | No v7 atom for Wells-in-shock; flag for atom_proposer |
| SCN-012 | `order_lab_d_dimer` | 2 | "confirmed PE에서 불필요" | UNMAPPED | N/A | low | No v7 atom for redundant D-dimer; flag for atom_proposer |

### 6.3 Conflict Resolution (pe.001 ∩ pe.002)

pe.001 (REQUIRED) and pe.002 (FORBIDDEN) share `canonical_id =
give_systemic_thrombolysis`. The `counterfactual_compiler` detects this as an
exclusion-pair and emits a `CONFLICT`-type `CoverageItem`. Clinician evidence
supports both atoms simultaneously, demonstrating the real-world occurrence of
the REQUIRED ∩ FORBIDDEN overlap.

This is the primary evidence for the paper's CONFLICT-type coverage claim.
Full details: `docs/sgsc/260430_scn012_bridge.md`.

---

## 7. Validation Checklist (Day 2–3)

Work through this checklist in order. Items are sequenced on SGSC-3 atom
results arriving at the start of Day 2.

- [ ] **SGSC-3 complete**: Atom proposals received for all 14 guidelines
- [ ] **atom_id cross-reference**: Replace all `{GUIDELINE}_XXX` placeholders
  in Section 3 with actual `atom_id` values from SGSC-3 output
- [ ] **Direct match audit (Rule M1)**: Verify that `v6_action_id` values for
  `mapping_confidence = high` rows match `atom.action.canonical_id` via
  `ActionNormalizer` (run `scripts/ci/audit_action_normalizer.py` if needed)
- [ ] **UNMAPPED catalogue**: Collect all UNMAPPED rows into a separate list
  and file as atom_proposer feedback for Day 3 re-run candidates
- [ ] **30-atom spot-check selection**: Stratified sample — 2–3 atoms per
  guideline across the 14-guideline SGSC core set; prefer atoms with at least
  one `mapping_confidence = high` row as anchor
- [ ] **Clinician communication sent**: Forward Korean message template
  (Section 5.1) to rater_015 and rater_030 with the 30-atom review packet
- [ ] **Phase H validation_packet populated**: Run `build_validation_packet()`
  with `clinician_evidence` annotations injected into constraint dicts
  (Section 4.2); verify `packet.json` and `clinician_review_form.csv` written
  to `evidence_pack/phase_h/`
- [ ] **App.~Z.7 draft paragraph written**: Cite atom_ids, rater IDs,
  mapping_confidence levels, and UNMAPPED count; reference this document as
  source

---

## Cross-Reference Index

| Artefact | Location | Role in bridge |
|----------|----------|----------------|
| SCN-012 detailed bridge | `docs/sgsc/260430_scn012_bridge.md` | D5 worked example; pe.001–pe.005 specs |
| SGSC composition plan | `docs/sgsc/260430_sgsc_composition.md` | R4 Bridge protocol; Day-by-day critical path |
| Atom schema | `sgsc/schemas/atom.py` | `RecommendationAtom`, `AtomConstraint.type`, `ScenarioHooks` |
| Coverage schema | `sgsc/schemas/coverage.py` | `CoverageType` enum: RECOMMENDATION, GUARD, ALTERNATIVE |
| Validation packet | `sgsc/validation_packet.py` | `build_validation_packet()`, `ClinicianReviewItem` structure |
| Action normalizer | `assessor_core/action_normalizer.py` | Rule M1 canonical_id matching |
| Clinician submissions | `clinician_validation/submissions/` | Raw rater_015 / rater_030 JSON |
| PE gap analysis | `clinician_validation/result/SCN-012_PE_scoring_gap_analysis.md` | rater_015 per-action judgments |

---

*Document version: v1.0-template, 2026-04-30*
*Next update: Day 2 — replace placeholder atom IDs with SGSC-3 output; verify Section 3 mapping table*
