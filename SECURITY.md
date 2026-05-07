# Security Policy

CGA-Bench is a research artefact; it does NOT process production patient data.
Nonetheless we take the integrity and the research-hygiene properties of the
benchmark seriously, and we welcome responsible-disclosure reports for the
following classes of issue.

---

## Supported Versions

| Version | Supported |
|---|---|
| 6.x (current) | Yes |
| 5.x | Best-effort until 2026-12-31 |
| < 5 | No |

---

## What Counts as a Security / Integrity Issue

| Category | Example |
|---|---|
| Evaluation leakage | A path by which an agent could read scoring-module state at test time. |
| Canary exposure | A scorer-internal string surfaces in an agent-visible observation. |
| De-anonymization | A commit, config, or log leaks author identity during the double-blind review period. |
| Supply-chain risk | A dependency is compromised or silently replaced. |
| Reproducibility tampering | A reported number cannot be regenerated from the committed repository state. |
| Data integrity | A scenario file has been altered in a way that would change reported metrics. |
| CI bypass | A PR path that can merge without passing the anonymization guard, leakage scan, or full test suite. |

Issues that are **out of scope** here (but still valid as normal bug reports)
include UI papercuts, docs typos, test flakes with no safety implication, and
requests for new features.

---

## How to Report

### During NeurIPS 2026 D&B review (anonymous phase)

Use the confidential comment channel on OpenReview. Identify the issue class
from the table above; reviewers will escalate to the area chair if necessary.

### Post-publication

Preferred: open a **private security advisory** on GitHub (Settings → Security
→ New draft security advisory). Reviewers with write access will respond.

Alternatively, email the maintainer contact listed in `CITATION.cff`
(populated at camera-ready).

---

## Disclosure Timeline

We follow a **90-day responsible-disclosure** window:

| Day | Action |
|---|---|
| 0 | Report received; acknowledgement within 3 business days. |
| 1–14 | Triage; determine severity; assign an internal ticket. |
| 14–60 | Fix developed, tested, reviewed. |
| 60–90 | Coordinated release; advisory published with credit to the reporter if they wish. |
| 90+ | If no fix is possible, public disclosure of the known issue with mitigations. |

For issues that affect a reported paper result, we will additionally:
- Post an erratum in `CHANGELOG.md` and update `croissant.json`
  `dateModified`.
- Cross-reference the Zenodo record with an update.
- Notify the relevant conference contact (NeurIPS 2026 D&B chairs) when
  affecting the published version.

---

## Scope of Remediation

We commit to:
- **Fix** scorer-agent separation breaches as top priority.
- **Document** reproducibility issues openly in the changelog; regenerate
  affected numbers where feasible.
- **Revoke** and **reissue** Zenodo deposits when data integrity is affected
  (old DOI retained with a superseded-by link).

We do NOT commit to:
- Fixing issues in third-party forks or derivative datasets.
- Modifying published paper text (handled via the venue's erratum process).

---

## Credit

Responsible reporters are credited in:
- A dedicated section of the `CHANGELOG.md` entry that closes the issue.
- The GitHub security advisory (if they consent).
- The paper's acknowledgements on subsequent re-submissions.

---

## Anti-Retaliation

Good-faith security research that follows this policy will NOT be met with
legal action. We are a research group, not a commercial vendor; we want the
benchmark to be correct, and reporters help us get there.

---

*Last updated 2026-04-21. Policy subject to revision at major version bumps
(6.x → 7.x).*
