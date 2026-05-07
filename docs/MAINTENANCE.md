# CGA-Bench Maintenance Plan

**Document version**: 1.0 (2026-04-21)
**Target venue**: NeurIPS 2026 Datasets & Benchmarks Track

NeurIPS D&B reviewers expect an explicit maintenance commitment. This document records
the maintenance strategy, responsible parties (redacted during anonymous review), update
cadence, and deprecation policy for the CGA-Bench benchmark.

---

## 1. Maintenance Commitment

The CGA-Bench Authors commit to maintaining this benchmark for a **minimum of 3 years
post-publication** (through at least 2029). Maintenance covers:

- **Bug fixes**: constraint-encoding errors, scenario-data errors, scoring bugs,
  normalizer misses.
- **New CPG graphs**: rolling additions beyond the 25 core + 5 held-out (see §3).
- **New model benchmarks**: re-running the full 706-scenario × 3-run matrix for newly
  released frontier models upon request or on an annual cadence.
- **Documentation**: keeping `README.md`, `DATASHEET.md`, `docs/RAI.md`, and
  `croissant.json` synchronized with the code/data state.

---

## 2. Versioning Policy

Semantic versioning: `MAJOR.MINOR.PATCH`.

| Component | What counts as MAJOR | What counts as MINOR | What counts as PATCH |
|---|---|---|---|
| CPG graphs | Breaking change to an existing constraint's semantics | Added graph or added node to existing graph | Metadata / provenance fix that does not change verdicts |
| Scenarios | Removed or fundamentally restructured scenario | Added scenario | Typo / metadata-only fix |
| Scoring | Changed formula or thresholds | Added new sub-metric (opt-in) | Implementation fix with identical output |
| Croissant | Removed or renamed a field | Added field | Description / typo fix |

**Re-running requirement**: any MAJOR bump in CPG graphs or scoring requires re-running
the full 706-scenario × 3-run benchmark matrix. Episode files for superseded versions
remain accessible on Zenodo under the original DOI.

**Current version**: `6.0` (2026-04-10).

---

## 3. Update Cadence

| Update class | Cadence | Trigger |
|---|---|---|
| Critical bug fix (PATCH) | As needed, within 7 days of verified report | GitHub issue labelled `critical` |
| Regular bug fix (PATCH) | Monthly | GitHub issue triage |
| Additive CPG / scenario (MINOR) | Quarterly | Domain-expert contributions |
| Breaking change (MAJOR) | At most annually | Collective review |
| Model re-benchmark | Annually | Calendar-driven |
| Croissant metadata sync | Automatic with any of the above | Tied to release tag |

---

## 4. Responsibilities

### During anonymous review (current phase)

- Accountability flows through **OpenReview** on the NeurIPS 2026 submission.
- Ethics-relevant reports acknowledged within 14 days.
- No individual author identities disclosed until camera-ready.

### Post-publication

- **Primary maintainer**: designated author contact with ORCID, to be listed in
  `CITATION.cff` and `README.md` at camera-ready.
- **Secondary maintainer**: at least one co-maintainer for bus-factor robustness.
- **Contributor list**: `CONTRIBUTORS.md` (to be added with camera-ready).

### Maintenance channels

- **GitHub issues**: general bugs and feature requests.
- **GitHub discussions**: community questions.
- **Security contact**: `SECURITY.md` with 90-day responsible-disclosure window
  (added at camera-ready).

---

## 5. Deprecation and Archival

- **Superseded versions** remain archived on Zenodo under their original DOI
  **indefinitely**. No deletion.
- **Deprecation notice**: if a scenario or constraint is retired, a migration note
  appears in the release's `CHANGELOG.md` and in `croissant.json`'s `dateModified`.
- **Breaking changes** trigger a MAJOR bump and a 6-month overlap window where both
  old and new versions are maintained.

---

## 6. Contribution Process (post-publication)

1. Fork the public repository.
2. Open an issue describing the proposed change (new CPG graph, scenario, or bug fix).
3. Submit a pull request referencing the issue.
4. Clinical review (for CPG / scenario content) by at least one domain expert.
5. CI checks must pass:
   - `scripts/ci/audit_sources.py` (source traceability)
   - `scripts/ci/audit_citations.py` (citation consistency)
   - `scripts/ci/leakage_scan.py --canaries 200` (information isolation)
   - `pytest tests/` (full suite, 3185+ tests)
6. Squash-merge on approval.

Substantial contributions credited in `CONTRIBUTORS.md`. Algorithmic contributions
may qualify for co-authorship on subsequent publication at the maintainers'
discretion.

---

## 7. Breaking-Change Governance

A breaking change requires:

1. An RFC issue (GitHub) open for **≥ 4 weeks** of public comment.
2. Sign-off from at least two maintainers plus one domain expert.
3. A migration script in `scripts/migrations/` that converts v(N) data to v(N+1).
4. A CHANGELOG entry describing the rationale, scope, and migration path.
5. A new Zenodo DOI for the post-break version; the pre-break DOI remains
   available.

---

## 8. End-of-Life Policy

If maintenance is ever discontinued, the maintainers commit to:

- A **minimum 12-month public notice** on the repository README.
- Transfer of the repository / Zenodo records to a suitable archival host
  (e.g., MLCommons, PhysioNet, or Hugging Face) before repository archival.
- Final `CHANGELOG.md` entry marking the end-of-life version.

The benchmark is explicitly **never deleted**; at worst it is archived read-only.

---

*End of maintenance plan.*
