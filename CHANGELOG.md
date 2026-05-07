# CHANGELOG

All notable changes to CGA-Bench are documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [6.0] — 2026-04-10

First release accompanying the NeurIPS 2026 Datasets & Benchmarks Track submission.

### Added
- 25 clinical practice guideline graphs (20 core + 5 held-out) with full
  source traceability (`cpg_model/graphs/*.yaml`, `evidence_pack/guideline_cards.yaml`).
- 706 evaluation scenarios (107 manually authored + 599 auto-generated via
  constraint derivation engine).
- 1,049 typed constraints (REQUIRED, FORBIDDEN, BEFORE, WITHIN) exported to
  `constraints/constraints_export.json` (825 de-duplicated).
- 16,944 agent episode traces across 8 models (oss120b, qwen27b, qwen35b, qwen4b,
  qwen397b, gemma31b, nemotron30b, deepseek_r1_7b), 3 runs per scenario.
- Full scoring-agent information separation between `cpg_engine/`,
  `assessor_core/` (scoring-only) and `agent_runner/`, `agent_rules/`,
  `tool_api/`, `scenario_engine/` (agent-accessible).
- Runtime independence verification:
  `OracleAgent(OracleConfig()).get_independence_verification()`.
- CI canary-leakage scan covering 200 canary strings
  (`scripts/ci/leakage_scan.py`).
- MLCommons Croissant metadata (`croissant.json`) with `cr:` and `rai:` contexts.
- Datasheet for Datasets (Gebru et al., 2021) — `DATASHEET.md`.
- Responsible AI statement — `docs/RAI.md`.
- Maintenance plan — `docs/MAINTENANCE.md`.
- Zenodo deposit skeleton — `.zenodo.json`.
- Citation File Format — `CITATION.cff`.
- NeurIPS D&B reproducibility checklist — `docs/NEURIPS_DB_REPRO_CHECKLIST.md`.
- Anonymization guard CI script — `scripts/ci/anonymization_scan.sh`.
- Pre-submission anonymization tool — `scripts/prepare_anonymous_repo.py`
  (produces `anonymous_repo/` with PII / identifiers stripped).
- Empirical Bayes-error results for Theorem 3.4 v2 (paper Section 3 + appendix).
- Construct-validity defense experiments (X1 context-swap, X2 violation-event
  ablation + placebo, X9 4×3 grid re-analysis). See
  `docs/attack_gap_exp_exp/260421_p0_defense_implementation_report.md`.

### Dataset statistics
- Scenarios: 706 (107 manual + 599 auto; 23 `*_scenarios.yaml` files).
- Models benchmarked: 8 (oss120b through deepseek_r1_7b).
- Total episodes: 16,944 logical; ~23.8k JSON files (per-evaluator artefacts).
- Evaluators: 6 (DxEM, AC-Proxy, MAB-Proxy, C2≥0.7, ACov≥0.5, CGA-Bench TCC).
- RAG corpus: 25 parsed clinical documents under `cpg_sources/`.
- Held-out gold set: 338 instances (train/dev/test in
  `data_release/v1.0/gold_set/`).

### Known limitations
- Constraint-derivation engine over-generates by 81.6% relative to manual
  authoring; paper reports both `825` (de-duplicated) and `1,049` (template-level)
  counts.
- Simulator uses a deterministic 5-minute time step, which collapses π_nctx and
  π_nord Bayes-error measurements in this corpus (documented in the Theorem
  3.4 v2 corollary).
- 5.9% of single-hard-violation episodes are orphan cases (violation_event
  action not in `ep.actions`); honest aggregates in the paper exclude them.
- English-only; US-centric guideline corpus in the core set.
- Pediatrics, obstetrics, psychiatry, oncology are out of scope in v6.0.

### Documentation
- README with quick-start for benchmark, scenario listing, and external-benchmark
  evaluation.
- `KNOWN_ISSUES.md` covering recurring integration pitfalls.
- `.claude/rules/` directory containing per-module quick reference cards.
- Per-guideline provenance in `evidence_pack/guideline_cards.yaml`.

### Reproducibility
- `RNG_SEED=42` is the canonical seed across scripts.
- Six command-line recipes in
  `docs/attack_gap_exp_exp/260421_p0_defense_implementation_report.md` §10
  regenerate the paper's defense numbers.
- Full test suite: 3,185+ tests across 24 categories (`tests/`).

---

## Upcoming (next releases)

Planned additions (not yet committed):
- X3 cross-annotator TCC dataset (author-B recruitment in progress).
- X5 independent Oracle rule author (pair-encoding validation).
- X7 MIMIC-IV propensity-matching analysis (pending PhysioNet credentialing).
- X10 adversarial pair construction (50 trajectory pairs that force 3-way
  disagreement among TCC / AC-Proxy / morphology).
- Additional CPG graphs beyond the core 25 (pediatric hypoglycemia, postpartum
  hemorrhage under consideration).
- New-model benchmark row for future frontier LLM releases (on request or
  annually).
