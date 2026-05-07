# CGA-Bench: Clinical Guideline Adherence Benchmark

CGA-Bench evaluates how well LLM agents adhere to time-sensitive clinical
treatment protocols from medical guidelines (CPGs).  It prevents "evaluation
leakage" through strict architectural separation between the scoring system
and the agent-accessible components.

## Subset Naming

Throughout this submission, episode subsets are referred to by their
**reader-facing** names. Internal labels (still used in scripts, macro
files, and `evidence_pack/` JSON keys for backward-compatible regeneration)
map as follows:

| Reader-facing name | Internal label | Episodes | Source / definition |
|---|---|---:|---|
| **V7.3 SGSC** (umbrella) | V7.3 SGSC | (variable) | Source-grounded substrate. Mechanically compiled from CPG citations. Parent of the three subsets below. |
| **source-grounded subset** | V7.3 Full | 11,286 | 9 models × 418 SGSC scenarios × 3 runs. Default SGSC episode pool (`\vSevenThreeNEpisodes`). |
| **graph-anchored subset** | V7.3 Cat A | 1,215 | Source-grounded subset filtered to scenarios whose every `expected_action` is traceable in the CPG-graph vocabulary (`\vSevenThreeCatAEpisodesCorr`). |
| **profile-expanded subset** | V7.3 Expanded | 18,360 | Source-grounded substrate × patient profile combinations. |
| **typed-CwT baseline** | V6 Phase B typed-CwT @ 1.14× | 76,464 (auto-expanded subset, deviation channel removed) | Comparison baseline for SGSC variance amplification. |

When reading the source code or evidence-pack JSON, treat the internal
labels as synonyms; the prose in this README, `DATASHEET.md`,
`SUBMISSION_NOTES.md`, and the paper uses only the reader-facing names.

## Overview

- **25 Clinical Domains**: 20 core + 5 held-out CPG guideline graphs
- **706 Scenarios**: 107 manual + 599 auto-generated across all domains
- **8 Models Evaluated**: oss120b, qwen35b, qwen27b, qwen4b, qwen397b, gemma31b, nemotron30b, deepseek_r1_7b
- **16,944 Episodes**: 706 scenarios x 8 models x 3 runs
- **5 Violation Types**: OMISSION, COMMISSION, TIMING, SEQUENCE, DEVIATION
- **Scoring-Agent Separation**: agents cannot access the scoring engine
- **Budget-Matched Evaluation**: identical token/call budgets for all agents

## NeurIPS 2026 D&B Submission Artefacts

| Artefact | Location | Purpose |
|---|---|---|
| **License** | [`LICENSE`](./LICENSE) | CC-BY 4.0 |
| **Datasheet** | [`DATASHEET.md`](./DATASHEET.md) | Gebru et al. (2021) datasheet |
| **Responsible AI** | [`docs/RAI.md`](./docs/RAI.md) | Intended uses, risks, MIMIC compliance |
| **Croissant metadata** | [`croissant.json`](./croissant.json) | MLCommons descriptor (v7.3, mlcroissant-validated) |
| **CITATION** | [`CITATION.cff`](./CITATION.cff) | Machine-readable citation |
| **Zenodo deposit** | [`.zenodo.json`](./.zenodo.json) | DOI-archive metadata |
| **Maintenance plan** | [`docs/MAINTENANCE.md`](./docs/MAINTENANCE.md) | 3-year maintenance commitment |
| **Hardware** | [`docs/HARDWARE.md`](./docs/HARDWARE.md) | Reproduction hardware profile |
| **Reproducibility** | [`docs/NEURIPS_DB_REPRO_CHECKLIST.md`](./docs/NEURIPS_DB_REPRO_CHECKLIST.md) | D&B requirements checklist |
| **Changelog** | [`CHANGELOG.md`](./CHANGELOG.md) | Release notes (v6.0) |
| **Paper traceability** | [`docs/PAPER_TRACEABILITY.md`](./docs/PAPER_TRACEABILITY.md) | Macro -> script -> JSON provenance map |

### Quick verification (no GPU needed)

```bash
# 1. Full test suite
PYTHONPATH=. pytest tests/

# 2. Canary-leakage scan (scoring-agent isolation)
python scripts/ci/leakage_scan.py --dir . --canaries 200

# 3. Source traceability audit
PYTHONPATH=. python scripts/ci/audit_sources.py

# 4. Citation consistency audit
PYTHONPATH=. python scripts/ci/audit_citations.py
```

### Submission-ready copy

To produce a minimal reproducibility archive (strips ~93% of dev artifacts):

```bash
python scripts/submission/prepare_submission.py \
    --source . \
    --dest ../cga_bench_submission \
    --keep-model-sample qwen4b

# Dry-run (prints what would be removed, no changes):
python scripts/submission/prepare_submission.py \
    --source . --dest ../cga_bench_submission --dry-run

# Re-verify an existing copy:
python scripts/submission/prepare_submission.py \
    --source . --dest ../cga_bench_submission --verify-only
```

**Rename requirement**: the output directory must be named `cga_bench`
when deployed, since all internal imports use `from cga_bench.*`.

## Installation

### Requirements

- **Python**: **3.10 or newer** (uses `int | None` PEP-604 union syntax and
  PEP-585 `list[T]` generics throughout). Tested on 3.11 / 3.12 / 3.13.
  Python 3.8 / 3.9 will fail at import with `TypeError: 'type' object is
  not subscriptable` or `unsupported operand type(s) for |`.
- Linux or macOS. The Docker images in `Dockerfile.scorer` /
  `Dockerfile.agent` use Python 3.11.
- ~50 GB disk for full 706 x 8 x 3 runs; ~500 MB to just install + run
  a single scenario.

### Setup

```bash
# Use a fresh venv with Python >= 3.10:
python3.11 -m venv .venv && source .venv/bin/activate

# Pinned reproducible environment (preferred for paper reproduction):
pip install -r requirements.lock

# Or split installs by role:
pip install -r requirements-scorer.txt   # pydantic / yaml / pyarrow / lifelines
pip install -r requirements-agent.txt    # pydantic / yaml / httpx

# Development extras (pytest, ruff, mypy) are not packaged. Install
# directly:
pip install pytest pytest-asyncio ruff mypy
```

There is no `pyproject.toml` or `setup.py` in this submission tree.
The package is consumed via `PYTHONPATH=..` from the parent directory
of `cga_bench/` — see "Verifying the install" below.

### Verifying the install

`cga_bench` imports as an absolute package (e.g.
`from cga_bench.cpg_engine.engine import ...`). That means the **parent
directory of `cga_bench/` must be on `PYTHONPATH`**, not `cga_bench/`
itself.

```bash
# From inside cga_bench/, use PYTHONPATH=..:
cd cga_bench
PYTHONPATH=.. python -c "
from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.assessor_core.violations import ViolationExtractor
from cga_bench.agent_runner.rag_agent import RAGAgent
print('imports OK')
"

# Smoke run with the bundled qwen4b sample (no API calls):
PYTHONPATH=.. pytest tests/test_schemas tests/test_isolation -q --tb=line

# Mock-LLM benchmark smoke (no API calls, no GPU):
PYTHONPATH=.. python run_benchmark.py --scenario septic_shock_basic --agent rag_gpt4 --mock-llm

# Bundled verifier (11 critical files + 25 graphs + 19 module imports):
PYTHONPATH=.. python scripts/submission/prepare_submission.py \
    --source . --dest . --verify-only
```

**Pytest exception**: pytest auto-adds the rootdir's parent to
`sys.path` when it sees a top-level `conftest.py`, so `make test`,
`make test-fast`, and other Makefile targets work with `PYTHONPATH=.`
as written. For non-pytest invocations, prefer `PYTHONPATH=..`.

If you cloned the **submission tree** (`cga_bench_submission/`), regenerate
or rename it to `cga_bench/` first (all imports are `from cga_bench.*`):

```bash
mv cga_bench_submission cga_bench   # or: ln -s cga_bench_submission cga_bench
```

## Quick Start

### 1. Run a single scenario

```bash
# Single scenario with specific agent
python run_benchmark.py --scenario septic_shock_basic --agent rag_gpt4

# List available scenarios, agents, experiments
python run_benchmark.py --list-scenarios
python run_benchmark.py --list-agents
```

### 2. Run the full benchmark (706 scenarios x 8 models x 3 runs)

```bash
# Single model
PYTHONPATH=. python scripts/experiments/full_690_runner.py oss120b results/full_706_v5

# Dry run (1 scenario x 1 run)
PYTHONPATH=. python scripts/experiments/full_690_runner.py oss120b --dry-run

# Available models: oss120b, qwen35b, qwen27b, qwen4b, qwen397b, gemma31b, nemotron30b, deepseek_r1_7b
```

### 3. Run NeurIPS experiments

```bash
python run_neurips_experiment.py --config configs/experiments/neurips_main.yaml

# Specific baseline
python run_neurips_experiment.py --config configs/experiments/neurips_main.yaml --baseline rag_only

# Fairness verification only
python run_neurips_experiment.py --config configs/experiments/neurips_main.yaml --verify-only
```

### 4. Evaluate external benchmarks

```bash
python run_external_benchmark.py --benchmark agentclinic --agent llm_assist --limit 10

# With vLLM backend
python run_external_benchmark.py --benchmark agentclinic \
  --llm-model "Qwen/Qwen3-30B" --llm-backend vllm \
  --llm-endpoint "http://localhost:8013/v1"
```

## Architecture

### Core Design: Scoring-Agent Separation

Agents **cannot** access the scoring modules (`cpg_engine/`, `assessor_core/`).
This is verified at CI time by `scripts/ci/leakage_scan.py` and at runtime by
`eval_harness/fairness_verifier.py` (AST-based source scanning).

```
SCORING SYSTEM (server-side only, agent access forbidden)
├── cpg_engine/          G(s_t) → (A_G, M_G, F_G, D_G)
├── assessor_core/       Violation extraction + harm scoring
└── cpg_model/graphs/    25 YAML guideline definitions

AGENT SYSTEM (agent-accessible)
├── agent_runner/        RAG, Planner, Reflection, Oracle agents
├── agent_rules/         Independent decision tables (11 domains)
├── tool_api/            Scenario API (labs, meds, imaging)
└── scenario_engine/     Gym-like clinical simulation

SHARED (limited access)
├── cpg_model/schemas/   Core types: Action, PatientState, Violation
└── eval_harness/        Episode runner, budget enforcement, fairness
```

### Module Dependency Hierarchy

```
Layer 0 (leaf — zero internal deps):
    cpg_model/schemas/base.py, agent_rules/decision_table.py,
    agent_runner/llm_provider.py

Layer 1:
    cpg_engine/node_types.py, scenario_engine/environment.py,
    tool_api/base.py, assessor_core/harm_scorer.py,
    agent_rules/*_rules.py (11 domain tables)

Layer 2:
    cpg_engine/engine.py, agent_runner/base_agent.py,
    eval_harness/scenario_loader.py

Layer 3:
    assessor_core/violations.py, agent_runner/{rag,planner,reflection,oracle}_agent.py,
    semantic_layer/llm_assist_agent.py

Layer 4:
    assessor_core/evaluation_loop.py, eval_harness/pipeline.py

Layer 5:
    eval_harness/runner.py (top-level integration)

Layer 6 (entry points):
    run_benchmark.py, run_external_benchmark.py, run_neurips_experiment.py
```

### Directory Structure

```
cga_bench/
├── cpg_engine/               # CPG graph evaluation engine
│   ├── engine.py             # G(s_t) → (A_G, M_G, F_G, D_G)
│   ├── node_types.py         # Graph node definitions
│   ├── stepper.py            # Step-by-step state transitions
│   ├── temporal_constraints.py
│   ├── reachability.py
│   └── applicability.py
│
├── cpg_model/                # Schemas + 25 YAML guideline graphs
│   ├── schemas/
│   │   ├── base.py           # Action, PatientState, VitalSigns, CGAScore, ViolationType
│   │   ├── contracts.py
│   │   └── conformance.py
│   └── graphs/               # 25 YAML files (20 core + 5 held-out)
│
├── assessor_core/            # Violation detection + scoring
│   ├── violations.py         # ViolationExtractor (5 violation types)
│   ├── harm_scorer.py        # HarmScorer → CGAScore (C1-C5 sub-scores)
│   ├── action_normalizer.py  # 500+ direct mappings + pattern rules + fuzzy matching
│   ├── evaluation_loop.py    # Closed-loop evaluation orchestration
│   ├── event_log.py          # Immutable event sourcing
│   ├── state_reducer.py      # Action → PatientState transitions
│   ├── dual_track_evaluator.py
│   ├── episode_risk_scorer.py
│   ├── expected_actions_guard.py
│   ├── clinical_interaction_detector.py
│   └── dka_violation_detector.py
│
├── agent_runner/             # Agent implementations
│   ├── base_agent.py         # Abstract agent interface
│   ├── rag_agent.py          # RAG agent (BM25/Dense/Hybrid retrieval)
│   ├── oracle_agent.py       # Rule-based oracle (agent_rules only, never cpg_engine)
│   ├── planner_agent.py      # Multi-step planning agent
│   ├── reflection_agent.py   # Self-reflection agent
│   ├── llm_provider.py       # Multi-backend: OpenAI, Anthropic, vLLM, Mock
│   └── rag_corpus/           # 25 domain retrieval documents
│
├── agent_rules/              # Independent rule system (11 domain tables)
│   ├── decision_table.py     # Abstract base class
│   ├── sepsis_rules.py       # SSC 2021
│   ├── chest_pain_rules.py   # AHA 2021
│   ├── stroke_rules.py       # AHA 2019
│   ├── heart_failure_rules.py # AHA 2022
│   ├── aki_rules.py          # KDIGO
│   ├── dka_rules.py          # ADA
│   ├── pe_rules.py           # ESC PE 2019
│   ├── af_rules.py           # ESC AF 2020
│   ├── copd_rules.py         # GOLD COPD 2024
│   ├── gi_bleeding_rules.py  # ACG 2023
│   └── htn_emergency_rules.py # AHA 2017
│
├── scenario_engine/          # Clinical simulation
│   └── environment.py        # Gym-like: reset() / step(action) → (obs, reward, done, info)
│
├── eval_harness/             # Experiment orchestration
│   ├── runner.py             # Episode execution + experiment management
│   ├── scenario_loader.py    # YAML → Scenario
│   ├── budget_enforcer.py    # Token/call budget tracking
│   ├── fairness_verifier.py  # AST-based agent isolation verification
│   ├── pipeline.py           # Post-scoring pipeline
│   ├── clinician_alignment.py
│   ├── comparison.py
│   ├── report_generator.py
│   └── environment_snapshot.py
│
├── semantic_layer/           # Semantic analysis
│   ├── llm_assist_agent.py   # LLM-Assist agent (external benchmarks)
│   ├── cpg_parser.py         # CPG document parser
│   ├── constraint_synthesizer.py
│   ├── action_normalizer.py  # Semantic action normalization
│   ├── semantic_validator.py
│   ├── conformance/          # Declare conformance checking
│   ├── export/               # XES/OCEL/MTL process mining export
│   ├── external/             # External benchmark adapters (AgentClinic, MedAgentBench, HealthBench, etc.)
│   ├── mining/               # Pathway pattern mining
│   ├── ontology/             # Medical ontology mapping (LOINC, SNOMED-CT, RxNorm)
│   └── terminology/          # Terminology grounding (UCUM, coding systems)
│
├── env/                      # Environment adapters
│   ├── core/                 # Actions, episode runner, state
│   └── adapters/             # Benchmark-specific adapters
│
├── tool_api/                 # Scenario API (labs, medications, imaging)
│
├── audit/                    # Evaluator audit harness
│   ├── evaluator_base.py
│   ├── separating_pairs.py
│   └── shims/                # Evaluator shims (AC, MAB, C2, ACov, DxEM, V4-Hard)
│
├── configs/
│   ├── scenarios/            # 23 scenario YAML files
│   ├── agents/               # 75 agent config YAML files
│   └── experiments/          # 15 experiment config YAML files
│
├── scripts/
│   ├── experiments/          # 60+ experiment scripts (E1-E5, EX-1 to EX-39, CRES, W8, etc.)
│   ├── ci/                   # CI scripts (audit_sources, audit_citations, leakage_scan, validate_cpg_schema)
│   ├── audit/                # Audit scripts (build_index, compute_bayes_error, evaluator_audit)
│   ├── submission/           # Submission copy preparation
│   └── ...                   # Infra, repro, analysis, ablation utilities
│
├── tests/                    # 1,770+ tests across 30+ categories
│
├── data/
│   ├── mimic-iv-demo/        # MIMIC-IV demo dataset
│   └── external_benchmarks/  # 8 external benchmark datasets
│
├── evidence_pack/            # 85+ subdirs of experiment results + paper macros
│
├── paper/                    # NeurIPS 2026 paper
│   ├── main_final_v17.tex    # Main paper
│   ├── appendix.tex          # Appendix
│   ├── auto_numbers.tex      # 100+ auto-generated macros
│   └── figures/              # 6 figures + 5 generation scripts
│
├── _archive/                # Archived legacy code (see _archive/ARCHIVE_LOG.md)
│
├── run_benchmark.py          # Main entry point
├── run_external_benchmark.py # External benchmark evaluation
└── run_neurips_experiment.py  # NeurIPS experiment pipeline
```

## Supported Clinical Guidelines (25 graphs)

### Core guidelines (20)

| Guideline | Graph File | Key Scenarios |
|-----------|------------|---------------|
| SSC 2021 Sepsis Hour-1 | `ssc_sepsis_hour1_bundle.yaml` | Hour-1 Bundle, Septic Shock |
| AHA 2021 Chest Pain | `aha_chest_pain_evaluation.yaml` | STEMI, NSTEMI, RV Infarct Trap |
| AHA 2019 Stroke | `aha_stroke_2019.yaml` | tPA Eligibility, Thrombectomy |
| AHA 2022 Heart Failure | `aha_heart_failure_2022.yaml` | HFrEF, ADHF, Cardiogenic Shock |
| KDIGO AKI | `kdigo_aki_full.yaml` | AKI Stages, RRT Indications |
| ADA DKA | `ada_dka_management.yaml` | DKA Management, Insulin Drip |
| Universal Clinical Safety | `universal_clinical_safety.yaml` | Domain-independent evaluation |
| ESC AF 2020 | `atrial_fibrillation.yaml` | Rate/Rhythm Control, Anticoagulation |
| ATS/IDSA CAP 2019 | `cap_pneumonia.yaml` | Inpatient CAP, Severe CAP ICU |
| GOLD COPD 2024 | `copd_exacerbation.yaml` | Acute Exacerbation, NIV/Intubation |
| ACG GI Bleeding 2023 | `gi_bleeding.yaml` | Hemodynamic Instability, Endoscopy |
| AHA HTN Crisis 2017 | `hypertensive_emergency.yaml` | IV Antihypertensives |
| KDIGO Contrast AKI | `kdigo_contrast_aki.yaml` | Risk Stratification, Pre-hydration |
| ESC PE 2019 | `pulmonary_embolism.yaml` | Risk Stratification, Thrombolysis |
| AHA/ACLS 2020 | `acls_cardiac_arrest.yaml` | Cardiac Arrest Management |
| WAO/EAACI Anaphylaxis | `anaphylaxis_management.yaml` | Epinephrine, Airway Management |
| GINA Asthma 2023 | `gina_asthma_exacerbation.yaml` | Acute Exacerbation, Status Asthmaticus |
| IDSA Meningitis 2021 | `idsa_meningitis.yaml` | Empiric Antibiotics, Dexamethasone |
| NCS/ACEP Status Epilepticus 2016 | `status_epilepticus.yaml` | Benzodiazepines, Refractory SE |
| AACT Toxicology | `toxicology_management.yaml` | Acetaminophen, Opioid, TCA Overdose |

### Held-out guidelines (5)

| Guideline | Graph File | Scenarios |
|-----------|------------|-----------|
| AABB Transfusion 2024 | `aabb_transfusion.yaml` | RBC Transfusion, Massive Protocol |
| ABA Burn Resuscitation | `aba_burn_resuscitation.yaml` | Parkland Formula, Escharotomy |
| ACOG Obstetric Hemorrhage | `acog_obstetric_hemorrhage.yaml` | Postpartum Hemorrhage, Uterotonics |
| APA Agitation Management | `apa_agitation_management.yaml` | Pharmacologic Intervention |
| PALS Pediatric Emergency | `pals_pediatric_emergency.yaml` | Pediatric Shock, Cardiac Arrest |

## Violation Types

| Type | Description | Example |
|------|-------------|---------|
| **OMISSION** | Missing mandatory action | Lactate not ordered |
| **COMMISSION** | Performed forbidden action | Nitroglycerin given in RV infarct |
| **TIMING** | Deadline exceeded | ECG not obtained within 10 min |
| **SEQUENCE** | Order dependency violated | Antibiotics before blood cultures |
| **DEVIATION** | Off-protocol action | Action not in allowed set |

## Scoring System

### CGA Score Computation

```
Compliance = 1 - sum(w_i) / max_possible_score
w_i = severity x guideline_strength x preventability x violation_type_weight
```

### Sub-construct Scores (C1-C5)

| Score | Description |
|-------|-------------|
| C1 | Path Selection: actions within allowed set |
| C2 | Mandatory Completion: required actions performed |
| C3 | Forbidden Avoidance: contraindicated actions avoided |
| C4 | Timing Compliance: deadlines met |
| C5 | Sequence Integrity: correct action order |

### Severity Weights

| Level | Weight | Type | Weight |
|-------|--------|------|--------|
| MINOR | 0.1 | OMISSION | 0.7 |
| MODERATE | 0.4 | COMMISSION | 1.0 |
| MAJOR | 0.7 | TIMING | 0.5 |
| SEVERE | 0.9 | SEQUENCE | 0.6 |
| CATASTROPHIC | 1.0 | DEVIATION | 0.3 |

## Agent Types

| Agent | Uses LLM | Uses cpg_engine | Uses agent_rules | Budget-Matched |
|-------|----------|-----------------|------------------|----------------|
| RAGAgent | Yes | **No** | No | Yes |
| PlannerAgent | Yes | **No** | Yes | Yes |
| ReflectionAgent | Yes | **No** | Yes | Yes |
| OracleAgent | No | **Never** | Yes | N/A |
| LLMAssistAgent | Yes | **No** | No | Yes |

## Paper Experiments

The paper (`paper/main_final_v17.tex`) is backed by 60+ experiment scripts
in `scripts/experiments/`, each producing results in `evidence_pack/` that
feed into `paper/auto_numbers.tex` (~100 macros).

### Main experiments (E1-E5)

| Experiment | Script | Output |
|------------|--------|--------|
| E1: Verdict Flip | `exp_e1_verdict_flip.py` | `evidence_pack/exp_e1_verdict_flip.json` |
| E1: Matched-Pair Perturbation | `exp_orthogonal_perturbation.py` | `evidence_pack/exp_orthogonal_perturbation.json` |
| E2: BSR | `exp_e2_bsr.py` | `evidence_pack/exp_e2_bsr.json` |
| E3: Instrumentation Ablation | `exp_e3_instrumentation_ablation.py` | `evidence_pack/exp_e3_instrumentation_ablation.json` |
| E4: Operating Point | `exp_e4_operating_point.py` | `evidence_pack/exp_e4_operating_point.json` |
| E5: Evaluator Expansion | `exp_e5_evaluator_expansion.py` | `evidence_pack/exp_e5_evaluator_expansion.json` |

### Appendix experiments (EX-1 to EX-39, CRES, W8, D1)

See `scripts/experiments/` for full listing.  Each script is self-contained
and writes results to `evidence_pack/`.

### Figure generation

| Figure | Script |
|--------|--------|
| Figure 2 (theorem) | `paper/figures/make_figure2_theorem.py` |
| Figure 3 (CDE) | `paper/figures/make_figure3_cde.py` |
| Figure 4 (ranking) | `paper/figures/make_figure4_ranking.py` |
| Figure 5 (E1 heatmap) | `paper/figures/make_figure5_e1_only.py` |
| Figure 6 (W8 heatmap) | `paper/figures/make_figure6_w8_aofa_heatmap.py` |

## Testing

1,770+ tests across 30+ categories:

```bash
# Full test suite
PYTHONPATH=. pytest tests/ -v

# By category
PYTHONPATH=. pytest tests/test_e2e/ -v          # End-to-end scenarios
PYTHONPATH=. pytest tests/test_engine/ -v        # CPG engine
PYTHONPATH=. pytest tests/test_assessor/ -v      # Violation detection + scoring
PYTHONPATH=. pytest tests/test_agents/ -v        # Agent implementations
PYTHONPATH=. pytest tests/test_agent_rules/ -v   # Decision tables
PYTHONPATH=. pytest tests/test_golden/ -v        # Golden pair snapshots
PYTHONPATH=. pytest tests/test_isolation/ -v     # Scorer-Agent isolation
PYTHONPATH=. pytest tests/test_external/ -v      # External benchmark integration
PYTHONPATH=. pytest tests/test_audit/ -v         # Evaluator audit
```

## vLLM Launch Standard

Always launch vLLM servers with these options for benchmark evaluation:

```bash
vllm serve <MODEL_ID> \
  --port <PORT> \
  --tensor-parallel-size <TP> \
  --gpu-memory-utilization 0.92 \
  --max-model-len 8192 \
  --max-num-seqs 256 \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --api-key sk-no-key-required
```

See `.claude/rules/vllm-launch.md` for rationale and worker concurrency
guidelines per model size.

## Configuration

### Scenario config

```yaml
# configs/scenarios/sepsis_scenarios.yaml
scenarios:
  septic_shock_hour1:
    scenario_id: "septic_shock_hour1"
    guideline_graph: "ssc_sepsis_hour1"
    patient:
      vitals:
        map_mmhg: 62
    expected_actions:
      - "order_lab_lactate"
      - "order_lab_blood_culture"
      - "give_broad_spectrum_antibiotics"
    deadlines:
      order_lab_lactate: 60
      give_broad_spectrum_antibiotics: 60
```

### CPG graph config

```yaml
# cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml
graph_id: "ssc_sepsis_hour1"
guideline_name: "SSC 2021 Hour-1 Bundle"
metadata:
  doi: "10.1007/s00134-021-06506-y"
nodes:
  septic_shock_bundle:
    mandatory_actions:
      - "order_lab_lactate"
      - "order_lab_blood_culture"
    deadlines:
      order_lab_lactate: 60
    required_prior_actions:
      give_broad_spectrum_antibiotics:
        - "order_lab_blood_culture"
    source_guideline: "SSC 2021"
```

## Environment Variables

```bash
PYTHONPATH=.                    # Required for module imports
OPENAI_API_KEY=<key>            # For OpenAI-based agents
ANTHROPIC_API_KEY=<key>         # For Anthropic-based agents
VLLM_ENDPOINT=http://localhost:8013/v1
VLLM_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
```

## Development

```bash
ruff check .          # Lint
ruff format .         # Format
mypy .                # Type check
PYTHONPATH=. pytest tests/ --cov=.  # Test coverage
```

## CI Scripts

```bash
# Source traceability audit (YAML graph source_guideline fields)
PYTHONPATH=. python scripts/ci/audit_sources.py

# Citation consistency audit (README <-> YAML graph guideline names)
PYTHONPATH=. python scripts/ci/audit_citations.py

# Canary leakage scan (scorer-agent information isolation)
python scripts/ci/leakage_scan.py --dir . --canaries 10

# CPG schema validation
PYTHONPATH=. python scripts/ci/validate_cpg_schema.py
```

## Known Issues

See [`KNOWN_ISSUES.md`](./KNOWN_ISSUES.md) for recurring problem patterns,
Qwen prompt sensitivity rules, and checklists for adding new scenarios or
models.

## References

### Core Guidelines
- [Surviving Sepsis Campaign 2021](https://doi.org/10.1007/s00134-021-06506-y)
- [AHA/ACC Chest Pain 2021](https://doi.org/10.1161/CIR.0000000000001029)
- [AHA/ASA Stroke 2019](https://doi.org/10.1161/STR.0000000000000211)
- [AHA Heart Failure 2022](https://doi.org/10.1161/CIR.0000000000001063)
- [KDIGO AKI 2012](https://doi.org/10.1038/kisup.2012.1)
- [ADA DKA Management 2024](https://doi.org/10.2337/dc24-S015)

### Expansion Guidelines
- [ESC Atrial Fibrillation 2020](https://doi.org/10.1093/eurheartj/ehaa612)
- [ATS/IDSA CAP 2019](https://doi.org/10.1164/rccm.201908-1581ST)
- [GOLD COPD 2024](https://goldcopd.org/2024-gold-report/)
- [ACG GI Bleeding 2023](https://doi.org/10.14309/ajg.0000000000002296)
- [AHA Hypertensive Crisis 2017](https://doi.org/10.1161/HYP.0000000000000065)
- [ESC Pulmonary Embolism 2019](https://doi.org/10.1093/eurheartj/ehz405)

## License

CC-BY 4.0
