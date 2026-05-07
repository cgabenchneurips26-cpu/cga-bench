> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# NeurIPS 2026 Submission Requirements — ED Track

> **Last updated**: 2026-04-01
> **Purpose**: Authoritative reference for CGA-Bench NeurIPS 2026 ED track submission.

---

## 1. Key Deadlines

| Milestone | Date | Notes |
|-----------|------|-------|
| **Abstract submission** | **May 4, 2026** AOE | Title + 200-word abstract on OpenReview |
| **Full paper + code + data** | **May 6, 2026** AOE | PDF + supplementary + code/data links |
| Paper checklist | Due with full paper | 16 mandatory items |
| Reviews released | ~July 2026 | Double-blind by default |
| Author rebuttal | ~Aug 2026 | |
| Decision notification | ~Sep 2026 | |
| Camera-ready | ~Oct 2026 | |

---

## 2. Track: Evaluations & Datasets (ED)

**Formerly "Datasets & Benchmarks" (D&B)**. Renamed in 2026 to reflect expanded scope.

### Scope
- Evaluation methodology as a scientific object
- Benchmark design, metrics, and experimental protocols
- Dataset creation with documentation and responsible AI considerations

### Review Criteria (ED-specific)
1. **Novelty of evaluation methodology** (not just new data)
2. **Rigor of experimental design** (statistical validity, reproducibility)
3. **Breadth of impact** (cross-domain applicability)
4. **Data/code quality** (documentation, licensing, accessibility)
5. **Responsible AI considerations** (bias, fairness, safety)

### Key Differences from Main Track
- Emphasizes evaluation methodology contribution over algorithmic novelty
- Mandatory code + data release (desk rejection for non-compliance)
- Croissant metadata required for new datasets
- Can use `[eandd]` option in `\usepackage[eandd]{neurips_2026}`

---

## 3. Formatting Requirements

| Parameter | Value |
|-----------|-------|
| Page limit (content) | **9 pages** |
| References | Unlimited (not counted) |
| Appendix | Unlimited (not counted, but reviewers not required to read) |
| Style file | `neurips_2026.sty` |
| ED track option | `\usepackage[eandd]{neurips_2026}` |
| Column format | Single column |
| Font size | 10pt |
| Paper size | Letter (8.5 x 11 inches) |
| Margins | Default from style file |
| Line numbering | Required for review (`\usepackage[final]{neurips_2026}` for camera-ready only) |

### Supplementary Material
- Submitted as a single ZIP file
- Can include: additional figures, tables, proofs, code, data samples
- Must be self-contained (reviewers may not access external links during review)
- No page limit for supplementary

---

## 4. Code and Data Submission

### Code Release (MANDATORY for benchmarks)
- Must be accessible at submission time (anonymous GitHub, Zenodo, etc.)
- Desk rejection if code not provided for benchmark papers
- License must be clearly stated (MIT, Apache-2.0, etc.)
- README with reproduction instructions required

### Data Release
- New datasets must include Croissant metadata (JSON-LD format)
  - Core fields: name, description, distribution, recordSet
  - Responsible AI extension: fairness, privacy, safety documentation
- MIMIC-IV: PhysioNet credentialization explicitly accepted
  - Include instructions for obtaining access
  - Do NOT redistribute MIMIC data directly

### Anonymous Submission
- Use [Anonymous GitHub](https://anonymous.4open.science) for code during review
- **Preferred data platforms**: Harvard Dataverse, Kaggle, HuggingFace, OpenML (NOT Zenodo)
- Remove author names from code comments and documentation
- Supplementary code can use anonymous placeholder names

---

## 5. Paper Checklist (16 Items, MANDATORY)

Desk rejected if checklist missing. Must be filled as appendix section.

| # | Item | CGA-Bench Status |
|---|------|------------------|
| 1 | Claims match evidence | Friedman p=8.1e-05, CI overlap documented |
| 2 | Limitations discussed | Oracle ceiling, 4 OSS models only |
| 3 | Theory assumptions stated | N/A (empirical) |
| 4 | Reproducibility: code | Anonymous GitHub + HuggingFace/Dataverse |
| 5 | Reproducibility: data | PhysioNet MIMIC-IV (credentialized) |
| 6 | Experimental details | 180 episodes, 15 scenarios, 3 runs |
| 7 | Error bars/CI | Bootstrap 95% CI on all metrics |
| 8 | Statistical tests | Friedman + Holm-Bonferroni, LOSO |
| 9 | Computational resources | Token budgets documented per model |
| 10 | New assets: license | MIT License |
| 11 | New assets: consent | MIMIC-IV IRB-approved de-identified data |
| 12 | New assets: PII | No PII (MIMIC de-identified) |
| 13 | Crowdsourcing details | N/A (no crowdsourcing in current submission) |
| 14 | IRB/ethics approval | PhysioNet DUA covers MIMIC usage |
| 15 | Broader impacts | Clinical safety evaluation benefits |
| 16 | LLM usage declaration | Must declare if LLM used in writing/code |

---

## 6. Ethics Review

### Automatic Flags
- Medical/clinical data usage
- Potential for dual-use (clinical decision support)
- Patient data (even de-identified)

### CGA-Bench Mitigations
- MIMIC-IV is IRB-approved, de-identified, publicly available (with DUA)
- Benchmark evaluates safety (not deploys clinical systems)
- No real patient interaction or clinical deployment
- Clear disclaimer: "Not for clinical use"

### Ethics Statement Template
```
This work uses the MIMIC-IV demo dataset, which contains de-identified
clinical data approved for research use under PhysioNet's Data Use
Agreement. Our benchmark evaluates AI safety in clinical contexts but
does not constitute a clinical decision support system. All evaluations
are retrospective and do not involve real patient care.
```

---

## 7. Double-Blind Review

### Default for ED Track (2026)
- ED track now defaults to double-blind (changed from 2025)
- Single-blind optional only for dataset-only submissions that require data inspection

### Anonymization Checklist
- [ ] Author names removed from PDF
- [ ] Acknowledgments section removed or anonymized
- [ ] Self-citations in third person ("Smith et al. [2024] showed...")
- [ ] Code repository anonymized
- [ ] No identifying information in supplementary materials
- [ ] Model names/URLs anonymized if custom-trained

---

## 8. Camera-Ready Requirements

| Item | Requirement |
|------|-------------|
| Style option | `\usepackage[final]{neurips_2026}` |
| Author names | Added back |
| Page limit | 10 pages (1 extra from review version) |
| Acknowledgments | Restored |
| Code DOI | Permanent DOI on preferred platform (Dataverse, HuggingFace, Kaggle, OpenML) |
| Croissant metadata | Final version with all fields |
| License file | In repository root |

---

## 9. CGA-Bench Submission Checklist

### P0 (Must have by May 4 abstract deadline)
- [x] 9-page paper with `[eandd]` option
- [x] 200-word abstract
- [ ] OpenReview account and submission form

### P0 (Must have by May 6 full paper deadline)
- [x] Full paper PDF
- [x] Paper checklist (16 items) as appendix
- [ ] Anonymous GitHub with reproduction instructions
- [ ] Zenodo DOI for code/data
- [ ] LICENSE file in repository root
- [ ] Croissant metadata JSON-LD
- [x] Statistical evidence (Friedman, LOSO, bootstrap CI)
- [x] 180 episodes, 4 models, 15 scenarios

### P1 (Strengthen submission)
- [ ] Frontier model results (GPT-4o, Claude) — addresses "only OSS models" limitation
- [ ] Effect size reporting (Cohen's d or equivalent)
- [x] BSR analysis (5.1% overall)
- [x] Cross-benchmark comparison (17,784 episodes)
- [ ] Clinician validation (Experiment B, 25 trace pairs)

### P2 (Nice to have)
- [ ] Interactive demo
- [ ] HuggingFace dataset card
- [ ] Leaderboard website

---

## 10. Formatting Quick Reference

```latex
\documentclass{article}
\usepackage[eandd]{neurips_2026}  % ED track
% \usepackage[final, eandd]{neurips_2026}  % Camera-ready

\title{CGA-Bench: Clinical Guideline Adherence Benchmark\\
for Medical AI Agent Evaluation}

\author{
  % Anonymous for review
}

\begin{document}
\maketitle
\begin{abstract}
% 200 words max for OpenReview, can be longer in paper
\end{abstract}

% ... 9 pages of content ...

% References (unlimited, not counted)
\bibliography{references}

% Appendix (unlimited, not counted)
\appendix
\section{Paper Checklist}
% 16 mandatory items

\section{Supplementary Material}
% Additional figures, tables, proofs
\end{document}
```

---

*This document is maintained as a reference for the CGA-Bench NeurIPS 2026 submission. Verify against official NeurIPS 2026 CFP before final submission.*
