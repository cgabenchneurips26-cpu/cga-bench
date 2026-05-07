# Responsible AI Statement — CGA-Bench

*Prepared for NeurIPS 2026 Datasets & Benchmarks Track, following the NeurIPS Ethics
Review guidelines and the MLCommons Croissant RAI specification.*

**Document version**: 1.0 (2026-04-21)

---

## 1. Intended Uses

CGA-Bench is an **evaluation-only research benchmark** for measuring the guideline-
adherence of LLM agents operating in clinical decision-support settings. Concretely:

- Comparing agent architectures (RAG, Planner, Reflection, Oracle) on Clinical
  Practice Guideline (CPG) conformance.
- Studying trajectory-level violations (OMISSION / COMMISSION / TIMING / SEQUENCE /
  DEVIATION) as a complement to terminal-answer metrics.
- Investigating scoring-agent information isolation and evaluation leakage.
- Benchmarking process-reward models, tool-use safety, and clinical reasoning in a
  reproducible setting.

---

## 2. Out-of-Scope Uses (DO NOT USE FOR)

| Prohibited use | Reason |
|---|---|
| Direct clinical decision-making without human oversight | Scenarios are synthetic and simplified; agent performance on CGA-Bench does NOT translate to real-world safety. |
| Training production clinical systems without independent validation | Benchmark is evaluation-only; training on CGA-Bench invalidates it as a benchmark and offers no guarantee of clinical correctness. |
| Substitute for clinical judgment | CGA-Bench does not replace a credentialed clinician. |
| Patient-facing applications without regulatory approval | Use in patient-facing tools requires FDA/EMA/KFDA-equivalent clearance, IRB approval, and independent clinical validation. |
| Treatment recommendations for real patients | CGA-Bench scenarios are simulated and do not cover all clinical edge cases. |
| Claims of superhuman medical performance | High benchmark scores reflect protocol adherence on simulated cases, not clinical superiority. |

---

## 3. Risks and Mitigations

### 3.1 Risk: Benchmark misuse to imply clinical safety

**Mitigation**: The README, LICENSE, datasheet, and this RAI document all state
explicitly that CGA-Bench is evaluation-only and is not validated for real-world
deployment. Paper framing emphasizes that CGA scores are **necessary but not sufficient**
for clinical use.

### 3.2 Risk: Over-reliance on synthetic scenarios

**Mitigation**: 106 of 706 scenarios are authored manually by clinical informaticists
against named guideline protocols; the remaining 599 are auto-generated but validated
against the CPG constraint set. Known limitations (engine over-generation 81.6%, 25
domains only, English-only) are disclosed in the paper, datasheet, and Croissant
metadata.

### 3.3 Risk: Evaluation leakage / spec gaming

**Mitigation**:
- **Scoring-Agent Separation** enforced at the module level: `cpg_engine/` and
  `assessor_core/` are forbidden imports for any agent code.
- Runtime verification:
  `python -c "from cga_bench.agent_runner.oracle_agent import OracleAgent; print(OracleAgent(OracleConfig()).get_independence_verification())"`.
- CI-enforced canary leakage scan (`scripts/ci/leakage_scan.py` with 10–200 canaries).
- Oracle agent uses `agent_rules/decision_table.py` (independent re-encoding), never
  `cpg_engine/`.

### 3.4 Risk: Encoding-author bias (Oracle = upper bound attack)

**Mitigation**: The paper (Section on defense experiments) runs context-swap (X1) and
causal-intervention (X2) experiments to show TCC verdicts are driven by patient-state-
specific features, not by the author's encoding. An independent-rule-author experiment
(X5) is planned for post-acceptance to further disambiguate.

### 3.5 Risk: Demographic bias propagation

**Mitigation**: CGA-Bench scoring is patient-state-centric (vitals, labs, comorbidities)
and does **not** condition on race / sex / age for the adherence decision itself — it
scores against the CPG's clinical criteria, which are themselves subject to the
well-documented bias of Western clinical-guideline authorship. Users wishing to probe
demographic fairness should stratify agent outputs by the scenario metadata (`sex`,
`age_bucket`) and apply their own fairness analysis; CGA-Bench does not claim to audit
guideline-level bias.

### 3.6 Risk: Simulator artifacts leaking into findings

**Mitigation**: The 5-minute deterministic time-step is explicitly documented as a
corpus-specific property in Theorem 3.4 v2 and its corollaries. Findings that depend
critically on this (e.g., π_nctx ≈ π_nord) are flagged as simulator-dependent rather
than universal.

### 3.7 Risk: Paper's "A1 TCC = morphology" reviewer concern

**Mitigation**: Three orthogonal experiments (X1 context-swap, X2 violation-event
ablation + placebo, Theorem 3.4 v2's π-measurability argument) jointly show the TCC
evaluator is NOT reducible to a patient-state-blind morphology classifier. See the
P0 defense implementation report (`docs/attack_gap_exp_exp/260421_p0_defense_implementation_report.md`).

---

## 4. MIMIC-IV Compliance Statement

CGA-Bench uses the **MIMIC-IV demo** (PhysioNet Credentialed Health Data License 1.5.0),
which is openly redistributable. Scenarios are derived from MIMIC-IV demo with synthetic
augmentation and abstraction. The benchmark does NOT redistribute:

- Full MIMIC-IV (credentialed-access-only).
- Unmodified MIMIC-IV records.
- Any MIMIC-IV record at a granularity that would reconstruct a specific demo patient.

Researchers wishing to extend the patient-state distribution using full MIMIC-IV must
obtain PhysioNet credentialing independently. See
[https://physionet.org/content/mimiciv](https://physionet.org/content/mimiciv) for
access.

**Safe-harbor de-identification**: MIMIC-IV is de-identified under HIPAA Safe Harbor by
its curators (MIT LCP). CGA-Bench does not re-identify any patient and does not add
identifying attributes.

---

## 5. Human Subjects / IRB Status

**Core dataset (scenarios, CPG graphs, episodes)**: No human subjects involved. All
patient data is synthetic or from the pre-de-identified MIMIC-IV demo release. IRB
review is not applicable.

**Clinician-pairwise-preference sub-study (Experiment B)**: A separate study with
attending-physician reviewers is under a distinct protocol. See
`clinician_validation/README.md` for protocol details. Participant recruitment and
informed-consent procedures follow the hosting institution's IRB guidance; consent
forms and demographic-aggregate statistics will be published with the camera-ready.

**Author-B encoding (Experiment X3)**: Independent rule-encoding exercise by a second
clinical informaticist. Labor is compensated; no patient data involved.

---

## 6. Bias and Representation

| Dimension | Representation in CGA-Bench | Known gaps |
|---|---|---|
| Clinical specialty | Emergency medicine, ICU, acute cardiovascular, acute respiratory, sepsis, stroke, AKI, GI bleed, hyperkalemia, DKA, anaphylaxis, cardiac arrest, transfusion (25 domains) | Pediatrics, obstetrics, psychiatry, oncology, outpatient chronic care NOT covered |
| Guideline source | US (AHA, ADA, ACG, AABB), international (SSC, KDIGO, ESC, ATS/IDSA, GOLD), ACLS | Non-Western guidelines underrepresented |
| Language | English | No non-English clinical text |
| Patient demographics | Synthetic + MIMIC-IV demo (US urban academic center distribution) | Does not reflect global demographics |
| Socioeconomic context | Implicit in MIMIC-IV demo seeding | No explicit SES stratification |

Users should treat CGA-Bench as a starting point for conformance evaluation and
combine it with locale-appropriate benchmarks before drawing policy conclusions.

---

## 7. Transparency Artifacts

| Artifact | Path | Purpose |
|---|---|---|
| Dataset card | `DATASHEET.md` | Gebru-style datasheet |
| Croissant metadata | `croissant.json` | MLCommons dataset descriptor + RAI fields |
| License | `LICENSE` | CC-BY 4.0 |
| Guideline provenance | `evidence_pack/guideline_cards.yaml` | Per-graph source attribution |
| Leakage scan log | `evidence_pack/leakage_scan_200canaries.log` | Empirical isolation verification |
| Paper appendix | `paper/appendix.tex` | Full reproducibility details |
| Defense implementation report | `docs/attack_gap_exp_exp/260421_p0_defense_implementation_report.md` | Construct-validity analysis |

---

## 8. Feedback and Incident Reporting

**During anonymous review**: submit comments via OpenReview on the NeurIPS 2026
submission.

**Post-publication**: open a GitHub issue in the public repository. Security-relevant
issues (e.g., suspected evaluation leakage) should be reported via a pinned `SECURITY.md`
contact with 90-day responsible-disclosure window.

The authors commit to acknowledging all ethics-relevant reports within 14 days and
publishing erratum entries in `croissant.json` where applicable.

---

## 9. Accountability

The CGA-Bench Authors accept responsibility for the dataset's curation, documented
limitations, and ongoing maintenance. Camera-ready identities will include a primary
maintainer contact. During anonymous review, accountability flows through OpenReview.

---

*End of Responsible AI statement.*
