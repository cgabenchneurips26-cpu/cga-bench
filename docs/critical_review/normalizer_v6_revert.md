# Normalizer v6 Patch — Failure Analysis & Revert (2026-04-26)

Detailed account of an attempted bug-fix that turned out to be **wrong**,
the diagnostic process that revealed it, and lessons for future work.

---

## 1. Original motivation

deepseek r1 7B Phase A v6 results showed C1 path_selection = 0.675
(compared to qwen4b 0.881). Investigation found 1526 DEVIATION events
across 200 episodes / 588 unique action_ids. Common patterns:

| action_id (deviation) | count | suspicion |
|---|---:|---|
| `order_lab_unknown` | 59 | LLM emitted ambiguous lab |
| `give_iv_fluids` | 34 | already mapped |
| `order_stat_ct_head` | 32 | already canonical |
| `reassess_perfusion` | 30 | suspected synonym |
| `obtain_12_lead_ecg` | 21 | scenario-specific, not synonym |
| `give_oxygen` | 17 | suspected synonym |
| `give_oxygen_high_flow` | 17 | suspected variant |
| `assess_baseline_estimated_*_filtration_rate` | 17 | egfr expansion |
| `monitor_serum_creatinine_48_72h` | 17 | already canonical |

Hypothesis: many of these are *string-level alias collisions* — same
clinical concept emitted with different surface strings. Adding direct
mappings should canonicalize them and reduce DEVIATION count, recovering
deepseek's C1 score (predicted 0.675 → ~0.75-0.80).

## 2. What was added (commit cc02ed76)

16 new direct mappings in `_DEFAULT_DIRECT_MAPPINGS`:

```python
# Oxygen (6)
"give_oxygen": "give_supplemental_oxygen",
"give_oxygen_high_flow": "give_supplemental_oxygen",
"give_oxygen_supplemental": "give_supplemental_oxygen",
"administer_oxygen": "give_supplemental_oxygen",
"apply_oxygen": "give_supplemental_oxygen",
"start_oxygen_therapy": "give_supplemental_oxygen",
# Consultation (5)
"consult_specialist_general": "request_consultation",
"request_specialist_consult": "request_consultation",
"request_neurology_consultation": "neurology_consult",
"request_cardiology_consultation": "cardiology_consult",
"request_neurosurgery_consultation": "neurosurgery_consult",
# Reassessment (3)
"reassess_perfusion": "reassess_vital_signs",
"reassess_hemodynamic_status": "reassess_vital_signs",
"reassess_neurologic_status": "reassess_vital_signs",
# Monitoring (3)
"order_lab_blood_pressure_monitor": "apply_continuous_monitoring",
"order_continuous_monitoring": "apply_continuous_monitoring",
"monitor_continuously": "apply_continuous_monitoring",
```

27/27 normalizer unit tests passed. Sync to 144 + 145 done.

## 3. Critical question that exposed the failure

User asked: *"기존에 한거는어떻게하는데?"* — "What about previously-completed
episodes? Do we re-score them?"

This forced us to build a post-hoc rescore tool to validate the change
on existing data before committing to the new normalizer for the rest
of Phase B.

## 4. Rescore tool development

Built `scripts/experiments/rescore_v6.py`:

- Loads existing episode JSON
- Reconstructs `EpisodeLog` with action sequence
- Replays through `ClinicalEnvironment` to evolve `state_history`
  (initial state → step → step → ... — preserves time, lab delays,
  medication effects)
- Re-runs `ViolationExtractor` + `HarmScorer` with new normalizer
- Compares old vs new compliance scores

First version used static initial-state replication (per
rescore_clean_slate.py template) — produced -0.0887 mean delta on 30
sample episodes (28/30 worsened). This was **systematic worsening**, not
a normalizer effect — caused by missing state evolution.

Second version added proper `env.step(action)` replay, populating
`env.state_history` correctly. Same 30-episode sample: STILL **-0.0887**
mean delta (28/30 worsened). State replay was correct; the worsening
came from elsewhere.

## 5. Diagnosis

Inspected one specific episode:

```
=== aabb_t_basic_cardiac_liberal_threshold_qwen397b_r0 ===
v1 violation_events:                          (4 deviations)
  deviation order_lab_cbc                  @ transfusion_assessment
  deviation order_lab_type_and_screen      @ transfusion_assessment
  deviation order_lab_reticulocyte_count   @ transfusion_assessment
  deviation order_lab_thromboelastography  @ transfusion_assessment

v6 violation_events:                          (5 deviations — +1)
  deviation order_lab_cbc                  @ transfusion_assessment
  deviation order_lab_type_and_screen      @ transfusion_assessment
  deviation order_lab_reticulocyte_count   @ transfusion_assessment
  deviation order_lab_thromboelastography  @ transfusion_assessment
  deviation reassess_vital_signs           @ transfusion_assessment   ← NEW
```

The `reassess_vital_signs` deviation appeared because:
1. LLM emitted `reassess_perfusion` (scenario action)
2. v1 normalizer: `reassess_perfusion` → fuzzy-matched something in
   transfusion_assessment node's allowed_set → **NOT a deviation**
3. v6 normalizer: `reassess_perfusion` → forced to `reassess_vital_signs`
   via my new direct_mapping → `reassess_vital_signs` is NOT in
   transfusion_assessment's allowed_set → **NEW deviation**

My "alias" was wrong: **`reassess_perfusion` and `reassess_vital_signs`
are different clinical concepts**, not synonyms.

- `reassess_perfusion`: re-evaluate circulation/tissue perfusion
  (capillary refill, peripheral pulses, lactate trend)
- `reassess_vital_signs`: re-measure HR, BP, RR, SpO2, T

A reassessment of perfusion is a more SPECIFIC action than reassessment
of all vital signs; collapsing them loses information.

Same defect for:
| Lost specificity | "Synonym" target |
|---|---|
| reassess_perfusion | ≠ reassess_vital_signs |
| reassess_hemodynamic_status | ≠ reassess_vital_signs |
| reassess_neurologic_status | ≠ reassess_vital_signs |
| give_oxygen_high_flow (specific intervention) | ≠ give_supplemental_oxygen |
| order_lab_blood_pressure_monitor | ≠ apply_continuous_monitoring |

## 6. Why the v1 fuzzy/pattern matching was already correct

Action normalizer's pipeline:
1. `_DEFAULT_DIRECT_MAPPINGS` → exact-match lookup (HIGHEST priority)
2. `_DEFAULT_PATTERN_RULES` → regex-based transformations
3. Abbreviation expansion (egfr → estimated_glomerular_filtration_rate)
4. Fuzzy match against allowed_actions (Jaccard ≥ 0.7)

Steps 2-4 already handled `reassess_perfusion` correctly: the runtime
allowed_set at transfusion_assessment node DID contain a similar action
(maybe `monitor_perfusion_q15min` or similar), and fuzzy match found it
above 0.7 threshold. So at runtime, the action got a DIFFERENT canonical
form per scenario, contextually.

**My direct_mapping forced one global canonical, breaking the contextual
match**. This is why it hurt instead of helped.

## 7. Lesson learned

**Direct mappings should only be used for *literal string aliases*** —
i.e., when two strings refer to the *exact same clinical concept* with no
loss of specificity. Examples that ARE legit:
- `iv_fluid_bolus` → `give_crystalloid_30ml_kg` (literal procedure rephrasing)
- `give_normal_saline` → `give_crystalloid_fluid` (one is a kind of the other,
  but in this codebase they're treated as substitutable)

Examples that are NOT legit (what I added):
- `reassess_perfusion` → `reassess_vital_signs` (different concept)
- `give_oxygen_high_flow` → `give_supplemental_oxygen` (specificity loss)

**The fuzzy + pattern matching already handles ambiguous cases
contextually.** Don't override it with global direct_mappings unless
the alias is truly literal.

## 8. Action taken (this commit)

- All 16 added mappings REMOVED.
- Note left in `_DEFAULT_DIRECT_MAPPINGS` warning future contributors.
- `scripts/experiments/rescore_v6.py` (state-replay rescore tool)
  PRESERVED for future v2 work.
- This document captures the failure mode for future reference.

## 9. Open questions for v2 benchmark

1. **CYAS allowed_actions standard** (see
   `cpg_yaml_observer_dependence.md`) should explicitly enumerate
   acceptable variants per scenario, eliminating fuzzy match guesswork.
2. **Empirical alias mining**: if a corpus of episodes consistently emits
   action X that the runtime accepts via fuzzy match for canonical Y,
   X→Y is a SAFE direct_mapping. The 16 we added were not validated
   against this empirical signal.
3. **Inter-rater κ on `allowed_actions`**: required to bound the
   benchmark's observer-dependence quantitatively.

## 10. Implications for current paper

- DEVIATION rate as currently measured is honest (no v6 normalizer
  patch contamination).
- Phase A + Phase B episodes use consistent v1 normalizer.
- deepseek r1 C1 = 0.675 stays. Honest reporting in §Discussion:
  "Reasoning models trade strict protocol adherence for broader
  clinical exploration; some of this is real model behavior, some is
  benchmark-level allowed_actions sensitivity (Appendix C)."
