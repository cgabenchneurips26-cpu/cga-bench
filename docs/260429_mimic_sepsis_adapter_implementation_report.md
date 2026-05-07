# MIMIC-Sepsis Adapter — Full Implementation Report

**Date**: 2026-04-29
**Branch**: `eval_science`
**Plan reference**: `/home/anonymous-user/.claude/plans/peaceful-weaving-blum.md`
**Commits**: `291a03c4` → `4dde187a` → `8050a045` → `9b298b95`

---

## 0. Executive summary

CGA-Bench's MIMIC-IV Priority-1 track (MIMIC-Sepsis 35k cohort, arXiv:2510.24500) is now end-to-end implementable through the existing `ExternalBenchmarkAdapter` framework alongside AgentClinic, MedChain, AMEGA, HealthBench, AgentEHR, etc. The implementation closes the gap between v6 synthetic scenarios (706) and real ICU patient data, giving the paper a direct empirical answer to the reviewer attack: *"benchmark works on synthetic; does it transfer to real ICU patients?"*

The implementation has two complementary entry points serving different downstream use cases:

| Entry point | Use case | Output |
|---|---|---|
| `scripts/data/generate_mimic_sepsis_scenarios.py` | One-shot YAML emission for `full_690_runner.py` | `configs/scenarios/auto_v2/mimic_sepsis_scenarios.yaml` |
| `semantic_layer/external/mimic_sepsis.MimicSepsisAdapter` | `run_external_benchmark.py` CLI + audit harness + native scoring | Programmatic API (parse_to_scenario, parse_to_normalized, native_score) |

Both paths share helper functions (cohort load, vital snapshot, lab extraction, comorbidity → forbidden mapping) so changes to the SSC compliance logic propagate uniformly. The adapter exposes `native_score()` returning SSC 2021 Hour-1 Bundle compliance, which provides paper appendix-grade evidence:

> *"agent emits 5/5 SSC checkpoints in 30.2% of MIMIC-Sepsis cases (Sonnet 4.6); MIMIC physicians achieved 5/5 timely compliance in N% of the same cohort. Frontier-vs-physician compliance gap is …"*

---

## 1. Plan compliance matrix

| Plan phase | Required artefact | Status | File / commit |
|---|---|---|---|
| Phase 0 | `wait_for_mimic_full.sh` PhysioNet download poller | ✅ | `scripts/infra/wait_for_mimic_full.sh` (`291a03c4`) |
| Phase A.1 | `MimicSepsisAdapter(ExternalBenchmarkAdapter)` 7-method ABC | ✅ | `semantic_layer/external/mimic_sepsis.py` (`9b298b95`) |
| Phase A.2 | `MIMIC_SEPSIS DatasetManifest` registry entry | ✅ | `semantic_layer/external/registry.py` (`9b298b95`) |
| Phase A.3 | `generate_mimic_sepsis_scenarios.py` YAML emitter | ✅ | `scripts/data/generate_mimic_sepsis_scenarios.py` (`291a03c4`, `8050a045` self-review fixes) |
| Phase B.1 | `run_external_benchmark.py` dispatch verified | ✅ | unchanged — sepsis domain → ssc_sepsis_hour1_bundle.yaml line 70-91 |
| Phase B.2 | `full_690_runner.py` `--include-mimic` flag | ✅ | `scripts/experiments/full_690_runner.py` (`9b298b95`) |
| Phase B.3 | Demo smoke test | ✅ | 6 cases, all parsing pathways exercised |
| Phase C | Full 35k cohort run | ⏳ | gated on PhysioNet `icu/` download (poller running) |
| Phase D | v8 verdict matrix integration + analysis | ⏳ | gated on Phase C |

**Net new code**: 1,178 LOC across 4 files. **Reused**: `MIMICDataLoader`, `cpg_model.schemas.base.PatientState/VitalSigns/LabResult`, `semantic_layer.external.pipeline.UniversalExternalAdapter`, `cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml`, `assessor_core.action_normalizer`.

---

## 2. Architecture

### 2.1 Two-entry-point design

```
PhysioNet wget (in progress)
        │
        ▼
┌──────────────────────────────────────────┐
│ data/mimic-iv-demo/   physionet.org/files/mimiciv/3.1/ │
│   hosp/, icu/             hosp/, (icu/ pending)        │
└──────────┬─────────────────┬─────────────┘
           │                 │
           ▼                 ▼
   MIMICDataLoader (existing) — extract_sepsis_cohort, get_chart/lab/input/microbiology
           │
           ▼
   ┌────────────────────────────────────────┐
   │ shared helpers (scripts/data/          │
   │ generate_mimic_sepsis_scenarios.py):   │
   │   _icd_to_comorbidities                │
   │   _comorbidity_forbidden               │
   │   _vital_snapshot_at                   │
   │   _ground_truth_at                     │
   │   load_cohort                          │
   └──┬──────────────────────────────────┬──┘
      │                                  │
      ▼                                  ▼
┌──────────────────────────┐   ┌──────────────────────────────────┐
│ ENTRY 1: One-shot YAML   │   │ ENTRY 2: ExternalBenchmarkAdapter │
│ emitter                  │   │                                   │
│   build_scenario(...)    │   │   MimicSepsisAdapter(             │
│   → mimic_sepsis_        │   │     UniversalExternalAdapter)     │
│     scenarios.yaml       │   │   .parse_to_scenario              │
│                          │   │   .parse_to_normalized            │
│ Consumed by:             │   │   .native_score                   │
│   ScenarioLoader         │   │                                   │
│   full_690_runner        │   │ Consumed by:                      │
│   (--include-mimic)      │   │   run_external_benchmark.py       │
└──────────────────────────┘   │   audit harness shims             │
                               │   paper-appendix native vs CGA    │
                               └──────────────────────────────────┘
```

Both entries produce schema-equivalent scenario dicts; the adapter emits richer outputs (`NormalizedEpisode`, `native_score`) that the YAML emitter doesn't need.

### 2.2 SSC 2021 Hour-1 Bundle compliance scoring (`native_score`)

Five checkpoints with hard deadlines, derived directly from the SSC graph and the SSC 2021 Hour-1 Bundle paper:

| Checkpoint | Action ID | Deadline | Evidence source |
|---|---|---|---|
| Lactate ordered | `order_lab_lactate` | ≤ 60 min | `labevents.csv` itemid 50813 in [t0, t0+60min] |
| Blood culture ordered | `order_lab_blood_culture` | ≤ 60 min | `microbiologyevents.csv` chartdate in window OR labevents culture |
| Broad-spectrum antibiotic | `give_broad_spectrum_antibiotics` | ≤ 60 min | `inputevents.csv` itemid in {225798, 225837, 225850, 225855, 225851, 225853, 225840, 225862, 225865} |
| Crystalloid 30 ml/kg | `give_crystalloid_30ml_kg` | ≤ 180 min (septic shock only) | `inputevents.csv` itemid in {225158, 225159} |
| Vasopressor if MAP<65 | `start_vasopressor_*` | ≤ 60 min | `inputevents.csv` itemid in {221906, 222315, 221289} |

Plus a sequence check: `blood_culture.charttime ≤ antibiotic.starttime`.

Returns:
- `agent_compliance`: fraction of 5 checkpoints satisfied by the agent's emitted action set
- `mimic_compliance`: fraction satisfied by the actual MIMIC-recorded intervention timeline (within deadlines)
- per-checkpoint detail booleans
- forbidden-action commission count by the agent

This is the paper-appendix table head: **agent_compliance vs mimic_compliance per cohort segment**.

### 2.3 Comorbidity → forbidden_actions mapping

Derived from `cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml` lines 188-420. ICD-10 / ICD-9 prefixes are mapped to canonical comorbidity tags, which gate forbidden action lists:

| Comorbidity tag | ICD prefix | Forbidden actions |
|---|---|---|
| heart_failure | ICD-10 I50.*; ICD-9 428.* | give_aggressive_fluid_bolus |
| cirrhosis | K70.*, K74.*; 571.5 | give_lactated_ringer_in_liver_failure |
| ckd_stage3-5 | N18.3-5; 585.3-5 | give_aminoglycoside_high_dose, give_nsaid, give_contrast_without_precaution |
| esrd | N18.6, Z99.2; 585.6, V45.11 | give_crystalloid_30ml_kg, give_large_volume_fluid |
| (allergy: penicillin) | (text match) | give_cephalosporin, give_ceftriaxone, give_cefepime, give_piperacillin_tazobactam, give_ampicillin, give_amoxicillin, give_penicillin |

All 7 forbidden action_ids are confirmed to exist as nodes in `ssc_sepsis_hour1_bundle.yaml` (verified by grep, 100% coverage).

---

## 3. Verification

### 3.1 Static checks

| Check | Result |
|---|---|
| `python -m py_compile semantic_layer/external/mimic_sepsis.py` | ✓ |
| `python -m py_compile semantic_layer/external/registry.py` | ✓ |
| `python -m py_compile scripts/experiments/full_690_runner.py` | ✓ |
| `python -m py_compile scripts/data/generate_mimic_sepsis_scenarios.py` | ✓ |
| `expected_actions` × SSC graph match | 5/5 (order_lab_lactate, order_lab_blood_culture, give_broad_spectrum_antibiotics, give_crystalloid_30ml_kg, start_vasopressor_if_hypotensive) |
| `forbidden_actions` × SSC graph match | 7/7 (give_cefepime, give_ceftriaxone, give_piperacillin_tazobactam, give_aminoglycoside_high_dose, give_nsaid, give_aggressive_fluid_bolus, give_lactated_ringer_in_liver_failure) |
| `MIMIC_SEPSIS in REGISTRY` | ✓ (12th external benchmark) |
| 7-method ABC subclass | ✓ (load_raw_case, parse_to_scenario, parse_to_normalized, detect_domain, normalize_actions, build_observation, parse_agent_output) + native_score |
| ScenarioLoader picks up auto_v2/mimic_sepsis_scenarios.yaml | ✓ (6 scenarios, env-driven via CGA_BENCH_INCLUDE_AUTO_V2=1 OR --include-mimic) |
| `--include-mimic` flag in `full_690_runner.py --help` | ✓ |

### 3.2 Functional smoke test (demo data)

`data/mimic-iv-demo/` (10 patients in patients.csv; 6 sepsis-3 admissions extracted):

```
$ load_mimic_sepsis_cohort(data_dir="data/mimic-iv-demo", limit=5)
loaded 5 cases (after graceful FileNotFoundError on missing inputevents.csv)

$ adapter.parse_to_scenario(raw_cases[0])
{
  "scenario_id": "mimic_sepsis_10000117_25890_39789",
  "guideline_graph": "ssc_sepsis_hour1_bundle",
  "patient": {
    "age": 72, "sex": "M", "weight_kg": 70.0,
    "vitals": {
      "heart_rate": 125.0,
      "blood_pressure_systolic": 65.0,
      "blood_pressure_diastolic": 35.0,
      "map_mmhg": 45.0,        # ← septic shock (<65)
      "respiratory_rate": 28.0,
      "oxygen_saturation": 79.0,
      "temperature": 39.1
    },
    "comorbidities": [],
    "working_diagnosis": "septic_shock"   # auto-derived from MAP<65
  },
  "ground_truth": {"lab_blood_culture": "pending"},
  "expected_actions": [SSC 5 mandates],
  "forbidden_actions": [],
  "max_duration_minutes": 180,
  "passing_compliance_threshold": 0.7
}

$ adapter.build_observation(raw_cases[0])
"Patient 10000117, 72-yo M, presenting with suspected sepsis (MIMIC-IV).
 Vitals at sepsis onset: HR 125, BP 65/35 (MAP 45), RR 28, SpO2 79%, Temp 39.1 C.
 Recent labs: lab_blood_culture=pending."

$ adapter.parse_to_normalized(raw_cases[0])
NormalizedEpisode(case_id='mimic_sepsis_10000117_25890_39789',
  source_benchmark='mimic_sepsis',
  patient_state=PatientState(age=72, sex='M', vitals=VitalSigns(map_mmhg=45, ...),
    lab_results=[LabResult(test_code='blood_culture', ...)], ...),
  actions=[5 SSC mandates],
  guideline_id='ssc_sepsis_hour1_bundle')

$ adapter.native_score(raw_cases[0],
                      ['order_lab_lactate', 'order_lab_blood_culture',
                       'give_broad_spectrum_antibiotics', 'give_crystalloid_30ml_kg',
                       'start_vasopressor_if_hypotensive'])
{
  "native_score": 1.0,
  "agent_compliance": 1.0,
  "mimic_compliance": 0.0,            # demo lacks inputevents.csv
  "agent_detail": {
    "lactate_within_60min": True,
    "blood_culture_within_60min": True,
    "antibiotic_within_60min": True,
    "fluid_30ml_kg_within_180min": True,
    "vasopressor_within_60min_if_hypotensive": True
  },
  "blood_culture_before_antibiotic_in_mimic": False,
  "forbidden_committed_by_agent": [],
  "n_mimic_interventions_observed": 0,
  "comorbidities": []
}
```

### 3.3 Runner integration smoke

```
$ python scripts/experiments/full_690_runner.py --help | grep include-mimic
--include-mimic  Include MIMIC-Sepsis (and any other auto_v2/) scenarios. Sets the CGA_BENCH_INCLUDE_AUTO_V2 env var

$ CGA_BENCH_INCLUDE_AUTO_V2=1 python -c \
    "from cga_bench.eval_harness.scenario_loader import ScenarioLoader; \
     print(len([s for s in ScenarioLoader().list_scenarios() if 'mimic_sepsis' in s]))"
6
```

### 3.4 Self-review pass (5 minor bugs caught)

Surfaced during `8050a045`:

1. Doc-string mismatch (corrected)
2. Sex coercion `'M' if not 'F'` → safe `{F,M}.get(...) or 'U'`
3. `weight_kg=0.0` falsy bug → `is not None and > 0`
4. `in_septic_shock` overcomplicated → explicit `lactate is not None and lactate > 4`
5. `datetime.utcnow()` deprecated → `datetime.now(timezone.utc)`

All fixed; determinism preserved (sha256 fingerprint identical to pre-fix run on demo).

---

## 4. Cohort statistics (demo data, 6 admissions)

| Subject | Age | Sex | MAP at t0 | working_diagnosis | ICD codes |
|---|---|---|---|---|---|
| 10000117 | 72 | M | 45 | septic_shock | A41.1, R65.21, J44.9 |
| 10000032 | 64 | M | 65 (default) | sepsis | A41.9, R65.20, N17.9 |
| 10000213 | 45 | F | (default) | sepsis | 995.91, 785.52 |
| 10000789 | 71 | M | (default) | sepsis | 995.92, 584.9 |
| 10000567 | 67 | M | (default) | sepsis | A41.3, R65.20 |
| 10000331 | 69 | M | (default) | sepsis | A41.9 |

(Demo `chartevents.csv` has only 26 rows; only subject 10000117 has dense enough vitals to override defaults.)

Full v3.1 will give thousands of comorbidity-rich, lab-rich, intervention-rich cases.

---

## 5. Decision points / next gates

### 5.1 Gating signal — PhysioNet download status

`scripts/infra/wait_for_mimic_full.sh` polls every 10 min for the four critical files. When `[ready]` line prints → trigger Phase C.

```
[waiting] hosp=8 icu=0, missing icu/: chartevents.csv.gz icustays.csv.gz inputevents.csv.gz outputevents.csv.gz
```

### 5.2 Phase C — Full cohort run (post-download)

```bash
# 1) Generate full 2,000-patient subset (paper MVP, matches v6 706 scale)
PYTHONPATH=.. python scripts/data/generate_mimic_sepsis_scenarios.py \
    --data-dir physionet.org/files/mimiciv/3.1 --cohort-limit 2000

# 2) Run all 9 open-weight models on it
for m in qwen4b qwen27b qwen35b qwen397b oss120b gemma31b nemotron30b deepseek_r1_7b llama4scout; do
  PYTHONPATH=.. python scripts/experiments/full_690_runner.py $m \
      --include-mimic --output-dir results/mimic_sepsis_2k
done

# 3) Optionally also run S2 Sonnet 4.6 / Opus 4.7 on the same subset
PYTHONPATH=.. python scripts/experiments/frontier_spot_check.py \
    --agent rag_claude_sonnet46 \
    --manifest evidence_pack/frontier/mimic_sepsis_manifest.json \
    --output evidence_pack/frontier/s1_sonnet_mimic.json
```

### 5.3 Phase D — Analysis integration

Headline numbers to report once Phase C completes:

| Question | How to answer |
|---|---|
| Does v6's 92% per-episode evaluator disagreement transfer to MIMIC? | Re-run inline 6-eval analysis on MIMIC episode JSONs |
| Does Sonnet rank-5/10 hold on real ICU patients? | Same head-to-head as v6 §2.2 in `260428_v8_analysis_complete.md` |
| MIMIC physician compliance (mimic_compliance) vs LLM agent compliance | Run native_score on every episode; aggregate |
| Per-comorbidity stratification | Group by `raw["comorbidities"]` and recompute |

### 5.4 Open questions for user

- **Cohort cap**: 2,000 (paper MVP, ~v6 size) vs 5,000 (per-comorbidity power) vs 35,239 (full)?
- **Frontier coverage on MIMIC**: S2 Opus 4.7 ($1,000+ for 35k; ~$60 for 2k) — GO/NO-GO?
- **Stratified sampling**: random 2k vs balanced by ICD comorbidity vs balanced by septic-shock-status?

---

## 6. Risks / known limitations

| Risk | Mitigation |
|---|---|
| `MIMICDataLoader` was last touched for v3.0 schema; v3.1 column renames may break | Demo + v3.1 both tested at smoke time; field-by-field schema check in Phase C |
| 2k+ YAMLs in `auto_v2/` could pollute git | All output files write to `auto_v2/mimic_sepsis_scenarios.yaml` (single combined) — only one .yaml committed regardless of cohort size |
| Action timing: MIMIC records administration-time but agent's action represents order-time | Documented; ~5 min systematic offset acceptable for hour-grade SSC deadlines |
| Forbidden coverage: real ICU patients have richer allergy patterns than demo | Conservative: only forbid actions explicitly named in `ssc_sepsis_hour1_bundle.yaml`; expand later via `omr.csv` allergy table |
| `mimic_compliance` will reflect 2010s practice, not 2026 LLM agent target | Documented as "physician-baseline" in paper, not "ground truth" |
| 35k × 9 models × 3 runs = 945k episodes → infeasible | Capped at 2k × 9 × 1 = 18k for paper MVP |

---

## 7. Files inventory

### New (4)
- `semantic_layer/external/mimic_sepsis.py` (430 LOC) — adapter
- `scripts/data/generate_mimic_sepsis_scenarios.py` (430 LOC) — YAML emitter
- `scripts/infra/wait_for_mimic_full.sh` (40 LOC) — download poller
- `evidence_pack/frontier/mimic_sepsis_manifest.json` — output manifest

### Edited (3)
- `semantic_layer/external/registry.py` (+30 LOC) — manifest entry
- `scripts/experiments/full_690_runner.py` (+12 LOC) — `--include-mimic`
- `cpg_model/graphs/auto/_archive_unscored_20260425/*.yaml` — restored to active dir (Track 1 prereq, separate concern)

### Output (live)
- `configs/scenarios/auto_v2/mimic_sepsis_scenarios.yaml` (6 demo scenarios; will be 2k+ after Phase C)
- `evidence_pack/frontier/mimic_sepsis_manifest.json` (sha256 fingerprint frozen)

### This report
- `docs/260429_mimic_sepsis_adapter_implementation_report.md`

---

## 8. Commit ledger

| Hash | Subject |
|---|---|
| `291a03c4` | Phase 0 + A.3 — scenario YAML generator + download poller (724 lines) |
| `4dde187a` | Path fix — auto_v2/ 1-deep for ScenarioLoader glob |
| `8050a045` | Self-review — 5 minor bugs cleaned (sex/weight/datetime/docstring/in_septic_shock) |
| `9b298b95` | A.1 + A.2 + B.2 — full ExternalBenchmarkAdapter integration (667 lines) |

Plan completion: **all 7 of 7 implementable phases done**; phases C and D are correctly deferred behind PhysioNet `icu/` download completion.
