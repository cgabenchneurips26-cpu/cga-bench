# CGA-Bench × MIMIC-IV Experiment Plan (NeurIPS D&B v18 Camera-Ready Augmentation)

> **For Claude Code.** Read this entire file before writing any code. Treat it as a contract.
> The owner is NOT looking for "I'll help you think through this" — implement it.

## Context (Read First)

We have a NeurIPS 2026 D&B Track submission `main_final_v18.pdf` (CGA-Bench: trace-conformance auditing of clinical-agent evaluators). The two largest reviewer threats are:

1. **"Engine-synthetic scenarios → numbers are generation artifacts"** (acknowledged in §6 Limitations).
2. **"No construct validity probe against real-world data"** (Alaa et al. ICML 2025 [8] cited but not addressed).

`App. AQ.1` pre-registered a MIMIC-IV retrospective re-scoring as "the load-bearing real-data probe" but kept it deferred. Deadline 2026-05-06. Today is 2026-04-30. **6 calendar days. No more deferrals.**

MIMIC-IV v3.1 is downloaded (PhysioNet credentialed access, owner-side). Do not re-download. Do not commit raw PHI to any tracked path. All MIMIC-IV-derived intermediate files go under `data/mimic_iv_local/` (gitignored) and only aggregate statistics + episode IDs go into `evidence_pack/mimic_iv/`.

## Hard Rules (Will be checked at code review)

These come from the project's `KNOWN_ISSUES.md` and prior incidents. Any violation = full rollback.

- **No inflated numbers.** Every reported metric must trace to a single deterministic script under `scripts/experiments/mimic/`. No hand-calculated numbers in tables. Add to `scripts/experiments/generate_final_numbers.py` as the single source of truth.
- **All paper-cited numbers go through `\newcommand` macros** in `evidence_pack/analysis/v6_full_macros.json` → re-rendered into `main_final_v18.tex`. No hardcoded numerals in tex.
- **Every script writes a JSON summary** to `evidence_pack/mimic_iv/{phase}/{script_name}.summary.json` with: `n_episodes`, `n_excluded`, `exclusion_breakdown`, `seed`, `git_sha`, `mimic_version`, `wall_time_s`. If you skip this, the phase is incomplete.
- **If a sanity-check gate fails (defined per phase below), HALT. Append to `KNOWN_ISSUES.md`.** Do not silently "fix" by tuning thresholds. Do not "interpret" the failure away.
- **No new external dependencies** beyond what's already in `requirements.txt` (psycopg2, pandas, numpy, scipy, statsmodels, scikit-learn, lifelines). If you genuinely need one, ask first.
- **Solver-invariance check survives.** Phase 2's TCC verdicts must match between the ILP and tiered solver to within 0 verdict flips on the MIMIC-IV cohort, same as the 19,062-episode invariance reported in App. Q. If it doesn't, halt.
- **Clinical claims off-limits.** Output framing is "observation-level mis-certification" only. Never write "TCC is clinically safer." Match §4.3 / §6 hedging exactly.
- **Action normalizer is a known weak point.** App. AT showed strict-vs-current gap of 3.81pp on synthetic. On MIMIC-IV the gap could be larger because real-world drug strings are messier. Always report metrics under both `--normalizer-mode=current` AND `--normalizer-mode=strict` and flag any divergence > 8pp as a Phase 2 sanity-gate failure.

## Existing Code You Must Re-Use (Not Re-Implement)

| Existing module | Reuse for |
|---|---|
| `cpg_engine/` | CDE constraint derivation, do not modify |
| `assessor_core/` | TCC + 4-projection scoring, do not modify |
| `scripts/experiments/run_external_benchmark.py` (L820–L983) | Domain detection lexicon, reuse `detect_domain` |
| `scripts/experiments/phase1_rescore.py` | Re-scoring template, mimic the structure |
| `scripts/experiments/generate_final_numbers.py` | Add MIMIC-IV section at the end |
| `scripts/ci/leakage_scan.py` | Run on every artifact you produce (canary tokens) |
| `agent_rules/` (13 files) | DO NOT touch — code-distance audit (App. AD) depends on it |
| `evidence_pack/verdicts/` schema | New file `evidence_pack/verdicts/verdict_matrix_mimic_iv.parquet` follows the same schema |

## Cohort Definitions (Lock these before any scoring)

We use **published, externally-validated definitions** to avoid the "we engineered the cohort to match the conclusion" critique.

### Sepsis cohort (Phases 2–5 substrate)

- **Sepsis-3 onset** (Singer 2016): earliest `t0` where `SOFA Δ ≥ 2` co-occurs with suspected infection (antibiotic order + culture within ±24h).
- Use the **MIMIC-Sepsis preprocessing pipeline** (arXiv 2510.24500) for cohort extraction. Their public code at https://github.com/[check] gives a 35,239-patient cohort. Reuse it; do not re-derive Sepsis-3 logic.
- Sub-restrict to first ICU stay per patient, age ≥ 18, `los_icu ≥ 24h` (so Hour-1 bundle has a defined window). Document each exclusion with N and %.
- Target N: **5,000–10,000 episodes** after exclusion. If N < 3,000 something is wrong with the join. If N > 15,000 the exclusions weren't applied.

### Stroke cohort (Phase 4 πterm/πntim witness mining only — no full scoring)

- ICD-10 I63.* + `last_known_well` from notes (limited recall, but enough for matched-pair examples).
- Target N: ~500 ischemic-stroke admissions with documented arrival + tPA decision time.

## Action Vocabulary Mapping (Critical Path)

This is the most failure-prone step. Tripathi et al. (medRxiv 2026-04-23) used MedGemma-based dual-classifier normalization on the same problem. **Do not re-do their work** — use rule-based normalization first, accept ~85% coverage, and document the gap.

```
data/mimic_iv_local/action_mapping.yaml
  - canonical_action: administer_antibiotics
    mimic_sources:
      - prescriptions.drug LIKE 'vancomycin%' AND route IN ('IV','IVPB')
      - prescriptions.drug LIKE 'piperacillin/tazobactam%'
      - emar.medication MATCHES (regex from the same prefix list as App. E)
    timing_field: prescriptions.starttime
    confidence: high
```

Write a coverage report `evidence_pack/mimic_iv/phase0/mapping_coverage.json` showing per-canonical-action: `n_mimic_events_matched`, `n_unmatched_string_buckets`, `top_10_unmatched_strings`. If `n_unmatched_string_buckets > 30` for any sepsis-Hour-1 action (`administer_antibiotics`, `obtain_blood_culture`, `measure_lactate`, `iv_crystalloid_bolus`), HALT and ask owner.

---

# Phase 0 — Setup & Sanity (Day 1, 4/30 evening)

**Goal:** Prove we can read MIMIC-IV, extract a sepsis cohort matching published numbers (±5% N), and map actions with documented coverage.

## Tasks

```
scripts/experiments/mimic/phase0_setup.py
  - Connect to local MIMIC-IV (postgres on localhost:5432, schema mimiciv).
  - Run sepsis-3 cohort SQL (use mimic-code repo's sepsis3.sql verbatim).
  - Apply exclusions, write data/mimic_iv_local/cohort_sepsis3.parquet.
  - Report: total N, excluded N per reason.
  - Sanity gate A: 5,000 ≤ N_final ≤ 10,000.
  - Sanity gate B: median age 60–75, female fraction 40–55%, in-hospital mortality 18–32%
    (broad SEP-1 literature ranges; Rhee 2017 IDSA 2017).

scripts/experiments/mimic/phase0_action_mapping.py
  - Build data/mimic_iv_local/action_mapping.yaml from prescriptions + procedureevents + chartevents.
  - For each of the 4 SSC Hour-1 actions, count matched events per episode.
  - Write evidence_pack/mimic_iv/phase0/mapping_coverage.json.
  - Sanity gate C: ≥85% of episodes have all 4 Hour-1 action types representable
    (i.e., either matched or definitively absent).
```

## Deliverables

- [ ] `data/mimic_iv_local/cohort_sepsis3.parquet`
- [ ] `evidence_pack/mimic_iv/phase0/cohort_summary.json`
- [ ] `evidence_pack/mimic_iv/phase0/mapping_coverage.json`
- [ ] `KNOWN_ISSUES.md` updated with any unmapped action strings >30 occurrences

## Stop conditions

If any sanity gate fails, HALT and write a detailed diagnosis to `KNOWN_ISSUES.md`. Do not proceed to Phase 1.

---

# Phase 1 — App. Z Patient-Level Distribution Check (Day 2, 5/1)

**Goal:** Replace `App. Z`'s literature-anchored 90%-ranges with patient-level percentiles from MIMIC-IV. Headline metrics (M90, IQRov, [p5,p95]⊆) should remain or only mildly degrade.

## Tasks

```
scripts/experiments/mimic/phase1_distribution_check.py
  - For each of the 24 observables in evidence_pack/analysis/real_cohort_reference.yaml:
    - Compute MIMIC-IV patient-level [p5, p25, p50, p75, p95] from cohort_sepsis3.parquet
      (and from a stroke ICD-10 cohort for stroke observables, AKI cohort for AKI rows).
    - Recompute M90 / IQRov / [p5,p95]⊆ against engine medians (unchanged from App. Z).
  - Output: evidence_pack/mimic_iv/phase1/distribution_check_patient_level.json
  - Update generate_final_numbers.py to emit patient-level versions of:
    \PhaseOneMNinetyRate{}, \PhaseOneIQROvRate{}, \PhaseOneStrictContainRate{}
```

## Sanity gates

- M90 (patient-level) ≥ 80%. If lower, the engine truly mismatches reality and we must report it honestly.
- Per-observable disagreement: flag any observable where engine median falls outside MIMIC-IV [p5, p95]. **Report flagged observables in the new App. Z table; do not hide them.**

## Deliverables

- [ ] Patient-level Table 27 replacement (LaTeX): `tex/appendix_Z_patient_level.tex`
- [ ] Side-by-side App. Z table: literature-anchor column + MIMIC-IV-anchor column. Two columns, both reported.
- [ ] `\PhaseOneM90PatientLevel{}` macro in `v6_full_macros.json`
- [ ] One paragraph addition to App. Z body: "On the same 24 observables, replacing literature anchors with MIMIC-IV patient-level percentiles yields M90 = X%, IQRov = Y%, [p5,p95]⊆ = Z%. The disagreements with the literature-anchor version are: [enumerate]."

## Time budget: 1 day

---

# Phase 2 — TCC Retrospective Scoring on MIMIC-IV Sepsis (Days 3–4, 5/2–5/3)

**This is the load-bearing experiment.** App. AQ.1 promised it; we are now executing it.

**Goal:** Score real clinician trajectories from the MIMIC-IV sepsis cohort under all 6 evaluators (TOM, ASC, CwT, PAF, ACov, TCC). Show the same projection-blindness pattern from Table 1 holds qualitatively on real trajectories.

## Tasks

```
scripts/experiments/mimic/phase2_score_trajectories.py
  - Input: cohort_sepsis3.parquet + action_mapping.yaml.
  - For each episode:
    1. Build trace τ = [(action, timestamp, patient_state)] using sepsis-3 onset as t=0.
    2. Run cpg_engine on the SSC 2021 graph with the patient context.
    3. Score with all 6 evaluators via assessor_core.evaluate_all().
    4. Persist to evidence_pack/verdicts/verdict_matrix_mimic_iv.parquet.
  - Match the schema of evidence_pack/verdicts/verdict_matrix.parquet exactly.

scripts/experiments/mimic/phase2_aggregate.py
  - Compute Table 1 analog: pass rate, FA, BSRcond, FA_n, median dG per evaluator.
  - Compute strict 3-way consensus FA (ASC ∩ CwT ∩ PAF) — match §5.3 framing.
  - Compute verdict-flip prevalence (= one-evaluator-pair flips).
  - Output: evidence_pack/mimic_iv/phase2/table1_mimic_iv.json
           tex/appendix_AQ_mimic_iv_table.tex (replicated Table 1 layout, MIMIC-IV column).
```

## Sanity gates (CRITICAL — these distinguish honest signal from artifact)

- **Solver invariance:** ILP vs tiered solver must produce 0 verdict flips on MIMIC-IV (matches the App. Q invariance result on synthetic). If non-zero, dG cost function or solver has a real-data edge case → halt.
- **Normalizer invariance:** Run with `--normalizer-mode=current` and `--normalizer-mode=strict`. Per-evaluator pass-rate gap must be ≤ 8pp. If larger, the action mapping is leaking, not the evaluator. Halt.
- **Pass-rate plausibility:** ASC pass rate on MIMIC-IV in [40%, 80%] is expected. CwT pass rate < ASC pass rate is expected (CwT is stricter). If TCC pass rate > CwT pass rate on MIMIC-IV, something is structurally inverted — halt.
- **Bundle compliance prior:** Independent SEP-1 literature places real-cohort all-or-none Hour-1 bundle compliance in roughly 30–70%. Our `CwT pass rate` should fall in this band as a sanity check (it is the closest CGA-Bench evaluator to SEP-1 binary scoring). If `CwT pass rate ∉ [25%, 75%]`, the action mapping or timing extraction is suspect. Halt.

## Deliverables

- [ ] `evidence_pack/verdicts/verdict_matrix_mimic_iv.parquet` (one row per episode × evaluator)
- [ ] `tex/appendix_AQ_mimic_iv_table.tex` — Table 1 layout, MIMIC-IV column added or as new table
- [ ] One updated sentence in §5.3: "The same pattern replicates on N = [X] real-clinician trajectories from MIMIC-IV (App. AQ.1): strict consensus FA = Y%, projection ordering preserved."
- [ ] Macros: `\MimicIvNEpisodes{}`, `\MimicIvAscFa{}`, `\MimicIvCwtFa{}`, `\MimicIvPafFa{}`, `\MimicIvTccFa{}`, `\MimicIvStrictConsensusFa{}`

## Time budget: 2 days (extraction is the slow step)

---

# Phase 3 — Predictive (Criterion) Validity vs In-Hospital Mortality (Day 5, 5/4)

**This is the construct-validity payload.** Alaa et al. (ICML 2025) defined criterion validity as "benchmark score predicts real-world clinical outcome." We adapt it to evaluators.

**Goal:** Show that TCC's pass/fail verdict carries more predictive signal for 28-day in-hospital mortality than ASC/PAF/CwT do, after adjusting for confounders.

## Tasks

```
scripts/experiments/mimic/phase3_predictive_validity.py
  - Input: verdict_matrix_mimic_iv.parquet + cohort with mortality outcome.
  - Confounders: age, sex, SOFA at sepsis onset, Charlson comorbidity index,
    admission source (ED vs ward vs ICU transfer).
  - For each evaluator m ∈ {ASC, PAF, CwT, TCC}:
    - Fit logistic regression: y_mortality ~ I(m=fail) + confounders
    - Report: OR with 95% CI, AUC, AUC bootstrap CI (B=1000, stratified by mortality).
  - Compare AUC pairwise via DeLong's test (paired ROC).
  - Compute NRI for adding TCC fail-flag to a model that already includes ASC fail-flag.
  - Sensitivity analysis: re-run with septic-shock subset only (lactate ≥ 4 OR vasopressor),
    where SEP-1 literature shows the strongest bundle-mortality association.
```

## Framing (READ BEFORE WRITING ANY TEXT)

**This is NOT a clinical-safety claim.** This is "evaluator-discriminative power, validated externally via outcome correlation as a discriminator-quality proxy." Every sentence in App. AQ.3 (new) must reinforce this. The exact language:

> "We use 28-day in-hospital mortality as an external discriminator-quality proxy following Alaa et al.'s criterion-validity protocol. We do not claim TCC verdicts identify causally harmful trajectories. We claim that TCC verdicts carry residual predictive signal for an external clinical outcome, beyond what ASC/PAF/CwT verdicts capture, after adjustment. This is consistent with Theorem 1's information-theoretic claim and inconsistent with the alternative hypothesis 'TCC violations are catalogue artifacts statistically unrelated to patient state.'"

## Sanity gates

- All 4 evaluators should show OR > 1 for fail → mortality (basic SEP-1 literature replication). If any evaluator's OR is < 1 or non-significant on N > 5000, the cohort or outcome extraction is wrong. Halt.
- Mortality base rate in cohort: 18–32%. Outside this range → halt.
- ASC OR ≈ 1.2–1.6 expected (literature). TCC OR > ASC OR is the working hypothesis. **If TCC OR < ASC OR, report it honestly and rewrite the contribution claim.** Don't bury it.

## Deliverables

- [ ] New appendix: `tex/appendix_AQ3_predictive_validity.tex`
- [ ] Table: 4 rows (one per evaluator) × columns {OR, 95% CI, AUC, AUC CI, ΔAUC vs ASC, DeLong p}
- [ ] Forest plot: `evidence_pack/mimic_iv/phase3/forest_plot_or.pdf`
- [ ] Updated §1 contribution 3 (Sensitivity audit) → add a fourth probe: "external criterion validity via 28-day mortality on N=[X] MIMIC-IV sepsis episodes"
- [ ] Macros: `\MimicIvTccOr{}`, `\MimicIvTccAuc{}`, `\MimicIvTccVsAscDeltaAuc{}`, `\MimicIvTccVsAscDeLongP{}`

## Time budget: 1 day (statistical analysis is fast once verdict matrix exists)

---

# Phase 4 — Real Witness Pairs for Lemma 1 (Day 6 morning, 5/5)

**Goal:** Augment App. B.3 Table 3 with episode IDs from MIMIC-IV (not just synthetic CGA-Bench releases) for each of the 4 separating projections. Strengthens distributional non-vacuousness of Theorem 1.

## Tasks

```
scripts/experiments/mimic/phase4_witness_pairs.py
  - For Case (ii) πaset (action multiset): mine pairs of sepsis episodes where
    set(actions) is identical, but timing of administer_antibiotics differs by
    > 60 min across the SSC Hour-1 deadline. Should yield O(100) pairs given
    the 30-70% bundle compliance prior.
  - For Case (iv) πnctx (no context): mine pairs receiving the same ANTICOAG
    or vasopressor where one patient has a contraindication state (allergy,
    bleeding, INR) and the other does not. ICD-10 + lab joins.
  - For Case (i) πterm and Case (iii) πnord: opportunistic mining; report
    "available in MIMIC-IV: [Y/N], representative episode IDs: [list]" only.
    Do not force these if the data don't naturally yield them.
  - Output: evidence_pack/mimic_iv/phase4/witness_pairs_mimic_iv.json
           with subject_id + hadm_id + stay_id (PhysioNet credentialed-only release).
```

## Hard constraint

We CANNOT publicly release MIMIC-IV episode IDs except through PhysioNet's credentialed-access channel. The paper appendix lists hashed IDs only. Add a sentence: "Full episode IDs released to credentialed researchers via the supplementary CGA-Bench MIMIC-IV addendum, gated by PhysioNet credentialing."

## Deliverables

- [ ] Updated `tex/appendix_B3_witness_pairs.tex` — add MIMIC-IV columns to Table 3
- [ ] New supplementary file `supplementary/mimic_iv_witness_pairs.json.gpg` (encrypted, key shared via DUA)
- [ ] One sentence in §3.4 paragraph "Quantitative implication": "Witness pairs are not exclusively synthetic — App. B.3 Table 3 lists matched pairs from MIMIC-IV for Cases (ii) and (iv)."

## Time budget: 0.5 day

---

# Phase 5 — Real Clinicians as a Comparator on the Leaderboard (Day 6 afternoon, 5/5)

**Goal:** Add a "Human-Clinicians (MIMIC-IV)" pseudo-model to Fig. 7 ranking-flip chart. High visual impact; modest implementation effort because verdict_matrix_mimic_iv already exists from Phase 2.

## Tasks

```
scripts/experiments/mimic/phase5_clinician_leaderboard.py
  - Treat MIMIC-IV cohort as a single "model" called "Human-Clinicians (MIMIC-IV)".
  - Compute its per-evaluator pass rate.
  - Insert into the existing 8-model rank matrix (Table 29) as row 9.
  - Re-render Fig. 7 with 9 trajectories (existing 8 + Human).
  - Recompute Kendall's W for the 9-row table.
```

## Framing (CRITICAL)

This is **not** "LLMs vs humans" benchmarking. The MIMIC-IV "Human-Clinicians" pseudo-model is the *aggregate behaviour distribution of real clinicians*, not a controlled comparator. Frame it explicitly as:

> "We add an aggregate Human-Clinicians (MIMIC-IV) row not as a head-to-head clinical comparator but as a fixed-distribution reference point illustrating that the projection-induced rank disagreement persists across the LLM-vs-clinician axis: even the real-clinician aggregate's rank reverses across evaluators (rank [X] under ASC vs rank [Y] under TCC)."

## Sanity gates

- Human-Clinicians ASC pass rate is likely high (~70%+) because MIMIC-IV represents care that did get delivered. CwT pass rate should be lower. If Human ASC pass rate is < any LLM's ASC pass rate, there's a cohort/mapping issue. Halt.
- Do NOT report an absolute "LLMs are X% worse than humans" number. Frame only as rank-reversal.

## Deliverables

- [ ] Updated `figures/fig7_ranking_bump_chart.pdf` with 9th line (Human)
- [ ] Updated Table 29 (App. AB) with 9th row
- [ ] Updated W statistic + CI (will likely tighten or stay similar; report honestly)
- [ ] Macros: `\HumanRankAsc{}`, `\HumanRankTcc{}`, `\HumanAscPassRate{}`, `\HumanTccPassRate{}`

## Time budget: 0.5 day

---

# Phase 6 — Paper Integration & Final Audit (Day 7, 5/6 — submission day)

**Goal:** Wire all macros, all new appendix sections, all updated tables and figures into `main_final_v18.tex`. Run the full pre-flight audit. Submit.

## Tasks

```
scripts/experiments/mimic/phase6_integrate.py
  - Re-run scripts/experiments/generate_final_numbers.py end-to-end. Diff against
    the pre-MIMIC-IV macro set; any non-MIMIC-IV macro that changed is a bug.
  - Verify no orphaned \MimicIv* macros (macros defined but not used in tex).
  - Verify no missing \MimicIv* macros (macros used in tex but not defined).
  - Run the canary leakage scan (scripts/ci/leakage_scan.py) over the new
    evidence_pack/mimic_iv/ tree.

scripts/experiments/mimic/phase6_pre_flight.py
  - Verify all 5 phase summary JSONs exist.
  - Verify cohort_sepsis3.parquet hash logged in evidence_pack/mimic_iv/MANIFEST.json.
  - Run the test suite: pytest tests/test_mimic_iv_*.py.
  - Confirm git_sha is clean (no uncommitted changes outside data/ which is gitignored).
```

## Updates to existing sections of main_final_v18.tex

- [ ] §1 Contributions: contribution 3 grows by one line (criterion-validity probe added)
- [ ] §1 Limitations preview: change "deferred" → "executed; results in App. AQ.1–AQ.3"
- [ ] §2 Related Work: add one sentence comparing to Tripathi et al. medRxiv 2026 SEP-1 fuzzy compliance pipeline (different metric class: graded fuzzy vs binary trace-conformance)
- [ ] §3.4 Quantitative implication paragraph: add "MIMIC-IV witness-pair instantiation in App. B.3"
- [ ] §5.3: add MIMIC-IV replication sentence (one sentence, two macros)
- [ ] §5.5 Robustness Summary: add a 4th paragraph "External criterion validity"
- [ ] §6 Limitations: rewrite the "load-bearing real-data probe is the pre-registered MIMIC-IV re-scoring" paragraph in past tense, summarising the 5 findings in 3 sentences
- [ ] App. AQ.1 (existing, deferred): replace deferred-status header with executed-status results
- [ ] App. AQ.3 (NEW): predictive validity table, forest plot, methodology paragraph
- [ ] App. Z: dual-column table (literature-anchor + patient-level)
- [ ] App. B.3 Table 3: MIMIC-IV columns added
- [ ] App. AB Table 29: 9th row
- [ ] Fig. 7: 9 trajectories

## Final checklist before submission

- [ ] `make reproduce` Docker build passes
- [ ] All 5 phase scripts run end-to-end on a fresh checkout (pinned MIMIC-IV access excluded)
- [ ] `pytest -x tests/` exits 0
- [ ] `scripts/ci/leakage_scan.py` reports 0 hits
- [ ] PDF compiles without warnings
- [ ] Page count ≤ NeurIPS limit (verify after additions; cut from existing optional appendix material if needed — e.g., shorten App. AY)
- [ ] Author-side privacy review: no MIMIC-IV episode IDs visible in main text or unencrypted appendix
- [ ] Updated `KNOWN_ISSUES.md` reflects the 5 phases as resolved or with remaining caveats clearly stated

## Time budget: 1 day

---

# Daily Standup Format (For Owner)

At end of each day, append to `docs/mimic_iv_daily_log.md`:

```
## YYYY-MM-DD (Phase X)
- Completed: [bullet list of deliverable checkboxes flipped]
- Sanity gate results: [PASS / FAIL / N/A per gate]
- New entries in KNOWN_ISSUES.md: [list]
- Hours spent: [number]
- Tomorrow's blocker risk: [description, if any]
- Numbers (if applicable): [3-5 key macros that became available today]
```

The owner reads this. Inflated language wastes their time.

---

# Anti-Patterns (Will Get Reverted)

- "I think the result looks reasonable" without sanity-gate verification.
- "I tuned the threshold to make it pass" — that's the inverse of the project pattern.
- New SQL written by hand for sepsis-3 instead of reusing mimic-code.
- "MedGemma normalization" added as a dependency without asking.
- Numbers in tex that don't trace to a `\newcommand`.
- Commits to `agent_rules/` (App. AD code-distance audit will break).
- Episode IDs in unencrypted appendix material.
- Any phrase suggesting "TCC is clinically safer/better."
- Skipping `KNOWN_ISSUES.md` updates because "it's a small thing."

# When to Ask the Owner

- Sanity gate fails with no obvious cause.
- Action mapping coverage < 85% on any Hour-1 action.
- TCC pass rate inverts vs CwT pass rate.
- AUC for any evaluator's mortality-prediction is below 0.55 (catastrophic — outcome extraction is wrong).
- Page-limit overflow after Phase 6 integration.

Otherwise: execute, log, ship.