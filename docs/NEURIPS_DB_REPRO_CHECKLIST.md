# NeurIPS 2026 Datasets & Benchmarks — Reproducibility Checklist

*Prepared for the anonymous-review artefact submission. Mirrors the NeurIPS D&B
official checklist structure; update cells as work progresses.*

**Submission version**: CGA-Bench v6.0
**Last updated**: 2026-04-21

---

## A. Dataset Accessibility

| # | Item | Status | Evidence / Location |
|---|---|---|---|
| A1 | Dataset is publicly accessible during review | ⚠ PENDING | Anonymous hosting (anonymous.4open.science or anon GitHub org) to be set up. |
| A2 | Dataset has a persistent identifier (DOI) | ⚠ PENDING | Zenodo deposit scheduled for camera-ready; `.zenodo.json` skeleton prepared. |
| A3 | Dataset is under an open license | ✅ DONE | CC-BY 4.0 — see `LICENSE`, `croissant.json`. |
| A4 | Dataset can be downloaded by any reviewer without personal request | ⚠ PENDING | Depends on A1. |
| A5 | Dataset will remain accessible for ≥ 5 years | ✅ DONE (commitment) | Maintenance plan in `docs/MAINTENANCE.md`; Zenodo guarantees indefinite archival. |

---

## B. Metadata

| # | Item | Status | Evidence / Location |
|---|---|---|---|
| B1 | Croissant metadata file | ✅ DONE | `croissant.json` at repo root (v6.0). |
| B2 | Croissant validator passes | ⚠ PENDING | Run `python -m mlcroissant.scripts.validate --jsonld croissant.json`; expected clean. See `docs/CROISSANT_VALIDATION_REPORT.md` §4. |
| B3 | Datasheet for Datasets (Gebru et al.) | ✅ DONE | `DATASHEET.md`. |
| B4 | CITATION.cff | ✅ DONE | `CITATION.cff` (anonymous fields to populate at camera-ready). |
| B5 | License explicit in multiple places | ✅ DONE | `LICENSE`, `croissant.json`, `README.md`, `.zenodo.json`. |
| B6 | Version history / CHANGELOG | ⚠ PENDING | Introduce `CHANGELOG.md` at first public release. |

---

## C. Responsible AI

| # | Item | Status | Evidence / Location |
|---|---|---|---|
| C1 | Intended uses documented | ✅ DONE | `docs/RAI.md` §1. |
| C2 | Out-of-scope uses documented | ✅ DONE | `docs/RAI.md` §2. |
| C3 | Risks and mitigations | ✅ DONE | `docs/RAI.md` §3. |
| C4 | MIMIC-IV compliance statement | ✅ DONE | `docs/RAI.md` §4. |
| C5 | Human-subjects / IRB status | ✅ DONE | `docs/RAI.md` §5. |
| C6 | Bias and representation statement | ✅ DONE | `docs/RAI.md` §6. |
| C7 | Feedback / incident-reporting channels | ✅ DONE | `docs/RAI.md` §8. |
| C8 | Maintenance plan | ✅ DONE | `docs/MAINTENANCE.md`. |

---

## D. Reproducibility of Reported Numbers

| # | Item | Status | Evidence / Location |
|---|---|---|---|
| D1 | Full code to regenerate dataset is public | ✅ DONE | All scripts in repository; no private blobs. |
| D2 | Full code to regenerate reported metrics is public | ✅ DONE | `scripts/experiments/`, `scripts/ablations/`, `scripts/compute_bayes_error.py`, etc. |
| D3 | Deterministic runs with seed | ✅ DONE | `RNG_SEED=42` across scripts; bootstrap CIs stable across seeds. |
| D4 | Environment file / lock | ✅ DONE | `requirements.lock` (pinned), `pyproject.toml` (dev extras). |
| D5 | Hardware requirements documented | ⚠ PARTIAL | README mentions vLLM endpoints; explicit GPU / RAM minimums to add. |
| D6 | Reported numbers reproducible from repo | ✅ DONE | See `docs/attack_gap_exp_exp/260421_p0_defense_implementation_report.md` §10 for six command-line reproduction recipes. |
| D7 | Scoring-agent isolation verified at runtime | ✅ DONE | `OracleAgent.get_independence_verification()`, `scripts/ci/leakage_scan.py`. |
| D8 | Fairness checks across agents | ✅ DONE | `tests/test_fairness/`, budget-matched evaluation in `eval_harness/`. |

---

## E. Testing Infrastructure

| # | Item | Status | Evidence / Location |
|---|---|---|---|
| E1 | Unit tests | ✅ DONE | 3,185+ tests across 24 categories (`tests/`). |
| E2 | End-to-end tests | ✅ DONE | `tests/test_e2e/`. |
| E3 | Golden agent smoke test | ✅ DONE | `tests/test_golden/`. |
| E4 | Isolation tests | ✅ DONE | `tests/test_isolation/`. |
| E5 | CI status | ⚠ VERIFY | GitHub Actions workflow to be verified live at anonymous host. |
| E6 | Tests pass on clean clone | ⚠ VERIFY | Run on clean env before submission. |

---

## F. Anonymization (Double-Blind Review)

| # | Item | Status | Evidence / Location |
|---|---|---|---|
| F1 | No author names in README / LICENSE / paper | ✅ DONE | README grep clean; LICENSE says "CGA-Bench Authors"; paper says "Anonymous Authors". |
| F2 | No author emails in repo | ✅ DONE | Grep clean. |
| F3 | No affiliation strings | ✅ DONE | Grep clean. |
| F4 | No identifying absolute paths | ❌ FAIL — FIX BEFORE SUBMISSION | `/home/anonymous-org/anonymous-project/` leaks a username in CLAUDE.md, the P0 defense report, and `tests/test_e2e/test_e2e_comprehensive_pipeline.py`. See `docs/ANONYMIZATION_SCAN_REPORT.md` for the full list and proposed fix. |
| F5 | No identifying Git metadata | ⚠ VERIFY | `git log --format="%an %ae"` should show non-identifying author or be squashed / reset for anonymous upload. |
| F6 | No identifying data-release metadata | ✅ DONE | `data_release/v1.0/DATA_GOVERNANCE.md` does not reference authors; verify in scan. |
| F7 | Croissant `url` uses anonymous placeholder | ✅ DONE | `"url": "https://github.com/anonymous/cga-bench"`. |
| F8 | Zenodo metadata anonymized | ✅ DONE | `.zenodo.json` creator field is generic placeholder. |

---

## G. Paper-Side Artefacts

| # | Item | Status | Evidence / Location |
|---|---|---|---|
| G1 | Paper has Ethics section or equivalent RAI note | ⚠ VERIFY | Cross-reference `paper/main_final_v17.tex` against `docs/RAI.md`. |
| G2 | Paper cites the MIMIC-IV upstream | ⚠ VERIFY | Check bibliography includes MIMIC-IV demo. |
| G3 | Paper cites guideline sources | ✅ DONE | Per-constraint `source_guideline` captured in `evidence_pack/guideline_cards.yaml`. |
| G4 | Paper's evaluation description matches scoring module | ✅ DONE | Scoring modules follow paper Section 3. |
| G5 | Paper appendix describes reproducibility | ⚠ PARTIAL | §Reproducibility in appendix to confirm. |

---

## H. Known Gaps (to resolve before camera-ready)

1. **Anonymous hosting** (A1, A4) — set up `anonymous.4open.science` upload or anonymous GitHub org; confirm reviewer downloadability.
2. **Croissant validator clean-run** (B2) — run `mlcroissant` validator; capture log; fix any errors; commit the log.
3. **Absolute-path anonymization** (F4) — replace `${CGA_BENCH_ROOT}` with relative paths or `$REPO_ROOT` in README / docs / tests. See `docs/ANONYMIZATION_SCAN_REPORT.md`.
4. **Git history** (F5) — decide: preserve git history (with care that commits are anonymized) OR squash-reset for anonymous upload.
5. **Zenodo deposit** (A2) — execute at camera-ready using `.zenodo.json` skeleton.
6. **CI status badge** (E5) — verify GitHub Actions runs on anonymous host.
7. **CHANGELOG.md** (B6) — author the first entry with v6.0 release notes.
8. **Hardware requirement document** (D5) — author `docs/HARDWARE.md` or append to README.
9. **Ethics / RAI paper section** (G1) — confirm paper Section X references `docs/RAI.md`.
10. **Reproducibility appendix** (G5) — confirm or extend paper's Appendix section.

---

*End of checklist.*
