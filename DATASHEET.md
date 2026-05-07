# Datasheet for CGA-Bench

*Following the "Datasheets for Datasets" framework (Gebru et al., 2021).*

**Dataset name**: CGA-Bench (Clinical Guideline Adherence Benchmark)
**Version**: 7.3 (legacy V6 snapshot retained — see Subset Naming)
**Date of this datasheet**: 2026-05-06
**Corresponding author**: Anonymous (NeurIPS 2026 D&B Track, double-blind review)

---

## 1. Motivation

### Subset Naming

CGA-Bench is composed of several episode subsets that share a common
substrate (the V7.3 SGSC source-grounded substrate). Throughout this
datasheet and the rest of the submission we refer to the subsets by
their **reader-facing names**; their internal labels (used in scripts
and the `evidence_pack/` JSON keys) are listed for cross-reference.

| Reader-facing name | Internal label | Episodes | Definition |
|---|---|---:|---|
| **V7.3 SGSC** (umbrella) | V7.3 SGSC | (variable) | Source-grounded substrate. Mechanically compiled from CPG citations. Parent of the three subsets below. |
| **source-grounded subset** | V7.3 Full | 11,286 | 9 models × 418 SGSC scenarios × 3 runs (`\vSevenThreeNEpisodes`). Default SGSC episode pool. |
| **graph-anchored subset** | V7.3 Cat A | 1,215 | Source-grounded subset filtered to scenarios whose every `expected_action` is traceable in the CPG-graph vocabulary (`\vSevenThreeCatAEpisodesCorr`). |
| **profile-expanded subset** | V7.3 Expanded | 18,360 | Source-grounded substrate × patient profile combinations. |
| **typed-CwT baseline** | V6 Phase B typed-CwT @ 1.14× | 76,464 (auto-expanded subset, deviation channel removed) | Comparison baseline for SGSC variance amplification. |

The internal labels remain in the macro generators
(`scripts/experiments/generate_v73_auto_numbers.py`,
`compute_v73_paper_macros.py`, etc.) and in
`evidence_pack/analysis/v73_family_suite_detection.json` so the paper
macros stay regenerable; treat them as synonyms of the reader-facing
names.

### For what purpose was the dataset created?
CGA-Bench was created to evaluate whether large-language-model agents correctly follow
time-sensitive clinical treatment protocols extracted from published medical guidelines
(Clinical Practice Guidelines, CPGs). Existing medical AI benchmarks largely measure
terminal outcomes (diagnosis, final-answer correctness) and do not probe the *trajectory*
of actions against the structured requirements, deadlines, and contraindications that
real guidelines impose. CGA-Bench fills this gap by providing:

- 25 CPG graphs encoding 1,049 template-level typed constraints (REQUIRED, FORBIDDEN, BEFORE, WITHIN).
- 706 evaluation scenarios (107 manual + 599 auto-generated).
- 16,944 agent episode traces (8 models × 706 scenarios × 3 runs) with per-step violation labels.
- A scoring system with enforced scoring-agent information separation to prevent evaluation leakage.

### Who created this dataset and on behalf of what entity?
The dataset was created by the CGA-Bench Authors (identities withheld for double-blind review).
Author affiliations and funding sources will be disclosed in the camera-ready version.

### Who funded the creation of the dataset?
Funding acknowledgement is withheld for double-blind review. No commercial entity
directed the scenario content or scoring design.

### Any other comments?
The benchmark explicitly decouples scoring modules (`cpg_engine/`, `assessor_core/`) from
agent-accessible modules (`agent_runner/`, `agent_rules/`) to prevent agents from learning
the scoring rules at test time. See `CLAUDE.md` (Architecture: Scoring-Agent Separation).

---

## 2. Composition

### What do the instances that comprise the dataset represent?

Five primary instance types:

| Instance type | Count | What each instance represents |
|---|---|---|
| **CPG graph** | 25 | A directed graph encoding one clinical guideline (e.g., SSC 2021 Hour-1 Bundle) with per-node allowed / mandatory / forbidden actions and deadlines. |
| **Typed constraint** | 1,049 template / 825 de-duplicated | A single (action, type, deadline, source-clause) tuple derived from a CPG graph. |
| **Scenario** | 706 (107 manual + 599 auto) | A patient description with initial vitals / labs / comorbidities, the target CPG graph, and the expected / forbidden action sets. |
| **Episode trace** | 16,944 | One completed agent-environment interaction: sequence of actions, observations, timestamps, token usage, final state, violations extracted against the target CPG graph. |
| **Verdict record** | 101,664 | Per-episode verdicts from 6 evaluators (DxEM, AC-Proxy, MAB-Proxy, C2≥0.7, ACov≥0.5, CGA-Bench TCC). |

### How many instances are there in total?
See the table above. Aggregated into a Croissant-JSON dataset with five RecordSets
(`constraints`, `cpg_nodes`, `scenarios`, `episodes`, `verdict_matrix`).

### Does the dataset contain all possible instances?
No. Scenarios cover 25 clinical domains that span common emergency-department and ICU
pathologies. Pediatric, obstetric, and psychiatric domains are intentionally out-of-scope
for the core set. See `cpg_model/graphs/` for the full domain list.

### What data does each instance consist of?
- **CPG graph**: YAML with `nodes`, `edges`, per-node `allowed_actions`, `mandatory_actions`, `forbidden_actions`, `deadlines`, `source_guideline`, `source_section`, `evidence_level`.
- **Scenario**: YAML with `scenario_id`, `graph_id`, `patient_state`, `expected_actions`, `forbidden_actions`, `source_type` (manual|auto).
- **Episode trace**: JSON with `actions[]` (ordered list of `{action_id, args, timestamp_minutes, justification}`), `observations[]`, `violations[]`, `score`, `termination_reason`, `token_counts`.
- **Verdict record**: per-evaluator pass/fail + hard/critical violation flags.

### Is there a label or target associated with each instance?
Yes. Each **episode** carries:
- `compliance_score` (0.0–1.0, continuous)
- `violations_by_type` (counts per OMISSION/COMMISSION/TIMING/SEQUENCE/DEVIATION)
- Six binary verdicts (one per evaluator: DxEM, AC-Proxy, MAB-Proxy, C2≥0.7, ACov≥0.5, CGA-Bench)

### Is any information missing from individual instances?
Not systematically. Some auto-generated scenarios may omit rare lab results if the
underlying CPG does not reference them. Constraint-derivation-engine over-generation of
81.6% vs manual is documented in the paper; this is a property of the engine, not a
per-instance field.

### Are relationships between individual instances made explicit?
Yes.
- `scenario.graph_id → cpg_graph.graph_id` (scenario targets one guideline)
- `constraint.graph_id, constraint.node_id → cpg_nodes` (provenance)
- `episode.scenario_id → scenario.scenario_id` (traceability)
- `episode.violations[].constraint_id → constraint.constraint_id` (blame assignment)

### Are there recommended data splits?
Yes, for the entity-linking gold set only:
- `data_release/v1.0/gold_set/train.jsonl` (~70%)
- `data_release/v1.0/gold_set/dev.jsonl` (~15%)
- `data_release/v1.0/gold_set/test.jsonl` (~15%)

The main 706 scenarios are **not** split into train/dev/test because the benchmark is
**evaluation-only** (zero-shot or retrieval-augmented). Model developers must not train
on these scenarios.

### Are there any errors, sources of noise, or redundancies?
Known:
- Constraint-derivation engine over-generates relative to manual encoding by 81.6%
  (reported in the paper's engine fidelity analysis).
- Paper reports 1,049 template-level constraints which include double-counts of
  REQUIRED actions that also have WITHIN deadlines; the de-duplicated export is 825.
- π_nctx ≈ π_nord in the empirical Bayes-error table is a corpus-specific consequence
  of the simulator's deterministic 5-minute time step (documented in Theorem 3.4 v2).
- 5.9% of single-hard-violation episodes are "orphan cases" where the violation_event
  action is synthesized by the assessor without a matching entry in `ep.actions`.

### Is the dataset self-contained, or does it link to external resources?
Mostly self-contained. External dependencies:
- **MIMIC-IV demo** (PhysioNet Credentialed Health Data License 1.5.0): used to seed
  the patient-state distribution. Demo is openly licensed; full MIMIC-IV requires
  PhysioNet credentialing. CGA-Bench **does not redistribute** MIMIC-IV; scenarios are
  derivative with synthetic augmentation.
- **Clinical practice guideline source documents**: paraphrased in RAG corpus under
  fair-use research exemption. Original guideline PDFs are not redistributed.

### Does the dataset contain confidential data?
No. All patient descriptions are synthetic or derived from the de-identified MIMIC-IV
demo release.

### Does the dataset contain data that might be offensive, insulting, threatening, or cause anxiety?
No.

### Does the dataset identify any subpopulations?
Scenarios stratify by clinical domain (e.g., sepsis, stroke, heart failure). No
demographic subpopulation stratification (age/sex/race) is built into the core scoring
because guideline adherence is assessed against clinical state, not patient demographics.

### Is it possible to identify individuals from the dataset?
No. All patient data is synthetic or from the MIMIC-IV demo (already de-identified under
HIPAA Safe Harbor).

### Does the dataset contain sensitive data (SSN, financial, health info, etc.)?
Synthetic health data only. No real patient identifiers.

---

## 3. Collection Process

### How was the data acquired?

| Component | Method |
|---|---|
| CPG graphs | Manually curated by domain experts from published guidelines (SSC 2021, AHA 2019/2021/2022, KDIGO, ADA, ATS/IDSA, ESC, GOLD, ACG, ACLS, AABB, and others). Each node links back to specific guideline sections with evidence level. |
| Manual scenarios (107) | Authored by clinical informaticists following the target CPG's decision pathway. |
| Auto-generated scenarios (599) | Produced by the constraint-derivation engine from the graph node structure; clinical review for validity. |
| Agent episodes (16,944) | Programmatic evaluation: 8 LLM models × 706 scenarios × 3 independent runs with `RNG_SEED` control. |

### What mechanisms or procedures were used to collect the data?
- YAML/JSON schema validation (`tests/test_schemas/`).
- Programmatic fairness / isolation / exit-criteria tests (`tests/test_fairness/`, `tests/test_isolation/`).
- Canary leakage scan (`scripts/ci/leakage_scan.py`) with 10–200 canary strings verifying no scorer signal is visible to agents.

### Who was involved in the data collection process?
Domain-expert clinical informaticists authored the CPG graphs and manual scenarios.
Engineering authors implemented the scoring engine, scenario engine, and evaluation
harness. Specific roles and compensation are withheld for double-blind review.

### Over what timeframe was the data collected?
CPG graph curation and scenario authoring: 2025-Q4 through 2026-Q1.
Episode collection (benchmark runs): 2026-Q2 (March–April 2026).

### Were any ethical review processes conducted?
No human subjects were involved (all patient data is synthetic or from the
pre-de-identified MIMIC-IV demo). IRB review was therefore not applicable. For the
clinician-pairwise-preference sub-study (Experiment B), a separate protocol is in
progress; see `clinician_validation/README.md`.

### Did you collect the data from the individuals directly or via third parties?
Not applicable. No individual-level primary data collection.

### Were the individuals notified / did they consent?
Not applicable.

### Has an analysis of the potential impact been conducted?
Yes. See `docs/RAI.md` for the Responsible AI assessment (intended uses, out-of-scope
uses, risks, mitigations, MIMIC compliance).

---

## 4. Preprocessing / Cleaning / Labeling

### Was any preprocessing / cleaning / labeling of the data done?
Yes:
- Action IDs normalized via `assessor_core/action_normalizer.py` (500+ direct mappings + pattern rules + fuzzy Jaccard matching ≥ 0.7).
- Episodes with tool-call errors or max-step timeouts retained with `termination_reason` label; not dropped.
- Orphan violations (event action not in `ep.actions`) flagged; honest aggregates in the paper exclude them.
- Rule-based violation extraction follows `assessor_core/violations.py` with externally injected `HarmSeverityMapping` and `TimingSeverityThreshold` (no hardcoded defaults — see the "No Hardcoded Defaults" design principle in CLAUDE.md).

### Was the raw data saved in addition to the preprocessed data?
Yes. Raw episode JSON files are retained at `results/full_706_v5/{model}/` alongside
derived artefacts under `evidence_pack/`.

### Is the software used to preprocess / clean / label available?
Yes. All scripts live in the repository:
- `assessor_core/` — violation extraction, normalization
- `scripts/ablations/`, `scripts/experiments/` — ablations and defense experiments
- `scripts/ci/audit_sources.py`, `audit_citations.py`, `leakage_scan.py` — CI gates

---

## 5. Uses

### Has the dataset been used for any tasks already?
Yes. Primary use in the NeurIPS 2026 paper: comparing 8 LLM agents (oss120b, qwen27b,
qwen35b, qwen4b, qwen397b, gemma31b, nemotron30b, deepseek_r1_7b) on CGA-Bench and
against 6 competing evaluators.

### Is there a repository that links to papers or systems that use the dataset?
The paper and this repository are the first. A leaderboard / usage tracker will be added
post-acceptance.

### What (other) tasks could the dataset be used for?
- Process-reward modeling training (with proper train/test split construction).
- Safety-critical tool-use evaluation.
- Guideline retrieval (IR) benchmarks.
- CPG graph extraction research (graph structures are publicly released).
- Clinician–AI interaction studies (trajectory-level transparency).

### Is there anything about the composition of the dataset that might impact future uses?
- **Evaluation-only use**: the 706 scenarios should not be used as training data for
  models that will later be evaluated on CGA-Bench. Doing so invalidates the benchmark.
- **Engine over-generation**: researchers aggregating against the full 1,049 template
  count should be aware of the 81.6% over-generation vs manual and report against the
  825 de-duplicated constraints when appropriate.
- **Simulator determinism**: the 5-minute deterministic time step affects theoretical
  blindness results for π_nctx projections (documented in Theorem 3.4 v2).

### Are there tasks for which the dataset should NOT be used?
- Direct clinical decision-making without human oversight.
- Training production clinical systems without independent validation.
- Substitute for clinical judgment.
- Patient-facing applications without regulatory approval.
- Any use that implies CGA-Bench scores translate directly to real-world safety.

---

## 6. Distribution

### Will the dataset be distributed to third parties outside the entity creating it?
Yes, publicly, under CC-BY 4.0 (see `LICENSE`).

### How will the dataset be distributed?
- **Anonymous review phase**: anonymous GitHub / `anonymous.4open.science`.
- **Camera-ready and beyond**: public GitHub repository + Zenodo archive with DOI.
- **Croissant metadata**: `croissant.json` in the repository root.

### When will the dataset be distributed?
- v6.0 metadata: 2026-04-10 (embedded in this repository).
- Public release: upon NeurIPS 2026 acceptance.

### Will the dataset be distributed under a copyright or other IP license?
Yes. **CC-BY 4.0** (Creative Commons Attribution 4.0 International). See `LICENSE`.

### Will the dataset be distributed under any Terms of Use, export controls, regulatory restrictions?
The dataset itself carries CC-BY 4.0 with no additional ToU. Derivative patient data is
synthesized or from MIMIC-IV demo (open). Full MIMIC-IV access (if researchers wish to
extend the corpus) remains gated by PhysioNet credentialing.

---

## 7. Maintenance

### Who will be supporting/hosting/maintaining the dataset?
CGA-Bench Authors (identities disclosed in camera-ready version).

### How can the owner/curator/manager of the dataset be contacted?
During review: via OpenReview comments on the submission.
After publication: GitHub issues on the public repository + contact email in
`CITATION.cff`.

### Is there an erratum?
None as of 2026-04-21. Errata will be tracked as pinned GitHub issues and reflected
in `croissant.json`'s `dateModified` field.

### Will the dataset be updated?
Yes. Planned updates:
- New CPG graphs (beyond the 25 core + 5 held-out) on a rolling basis.
- New model episodes as frontier models are released.
- Bug fixes to constraint encodings, scenario data, or normalizer rules.

Semantic versioning: **major** for breaking schema changes, **minor** for additive
releases, **patch** for bug fixes. Current version: 6.0.

### If the dataset relates to people, are there applicable limits on the retention of data associated with the instances?
Not applicable (synthetic or pre-de-identified data).

### Will older versions of the dataset continue to be supported/hosted/maintained?
Yes. Each release is archived on Zenodo with a persistent DOI; older versions will
remain accessible under their original DOI.

### If others want to extend/augment/build on/contribute to the dataset, is there a mechanism for them to do so?
Yes. Contribution guide: `CONTRIBUTING.md` (to be added with camera-ready). Pull
requests welcome for new CPG graphs, scenario additions, and bug fixes. Substantial
contributions will be credited in the repository's `CONTRIBUTORS.md`.

---

*End of datasheet.*
