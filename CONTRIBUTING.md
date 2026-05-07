# Contributing to CGA-Bench

Thank you for your interest in contributing. CGA-Bench is an open research
benchmark; we welcome bug reports, corrections to clinical encoding, new CPG
graphs, additional scenarios, and bug fixes. During the NeurIPS 2026 D&B
double-blind review period, all contributor interactions flow through OpenReview
rather than this repository; the guidance below applies once the public repo is
live post-publication.

---

## 1. Code of Conduct

CGA-Bench adopts the [Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
All participants are expected to follow it.

---

## 2. Ways to Contribute

### 2.1 Bug reports
Open a GitHub issue with:
- A clear title (`bug(<area>): <symptom>`).
- Reproduction steps with a minimal command.
- Expected vs observed behaviour.
- Environment (Python version, OS, GPU if relevant).

### 2.2 Clinical encoding corrections
If you spot an error in a CPG graph (wrong deadline, missing contraindication,
out-of-date guideline citation):
- File a `bug(cpg)` issue referencing the specific node and source clause.
- Attach the original guideline section (paste / screenshot / DOI) as evidence.
- Reviewers include at least one domain expert before merging.

### 2.3 New CPG graphs
We welcome additions to the 25-graph core set. Requirements:
- Authored from a published, peer-reviewed clinical practice guideline.
- Uses the canonical YAML schema in `cpg_model/schemas/`.
- Every node carries `source_guideline`, `source_section`, `evidence_level`.
- Accompanied by ≥ 3 manually authored scenarios exercising the graph.
- Passes the CI gate: `scripts/ci/audit_sources.py`, `audit_citations.py`,
  `leakage_scan.py`, full pytest.

### 2.4 New scenarios
Manual scenarios must reference an existing graph and cover an edge case
that the auto-generated set does not. Auto-generated scenario contributions
should be accompanied by the derivation config used to produce them.

### 2.5 Bug fixes
Small fixes that do not change output numbers are fast-tracked. Any change
that *could* change reported metrics requires:
- A reproducibility diff: before/after metrics table.
- Updated evidence_pack artefacts if relevant.
- Reviewer sign-off from at least two maintainers.

---

## 3. Pull Request Process

1. **Fork** the repository and create a topic branch:
   ```bash
   git checkout -b feat/<brief-description>
   ```
2. **Implement** the change. Follow conventions:
   - Python: ruff + mypy clean (`ruff check . && mypy src/`).
   - Type-hints on every function (per the project's Python rules).
   - Google-style docstrings.
   - Function length ≤ 30 lines; cyclomatic complexity ≤ 10.
   - No hardcoded defaults; inject via `*Config` dataclasses.
   - Scoring ↔ agent module separation MUST be preserved.
3. **Test**:
   ```bash
   PYTHONPATH=. pytest tests/ -v
   bash scripts/ci/anonymization_scan.sh
   python scripts/ci/leakage_scan.py --dir . --canaries 200
   ```
4. **Commit** using the project's commit trailer format (see
   `/home/anonymous-org/.claude/CLAUDE.md` `<commit_protocol>` or paste the template
   below in your commit message):
   ```
   <type>(<scope>): <subject>

   <body paragraph(s)>

   Constraint: <active constraint>
   Rejected: <alternative> | <reason>
   Confidence: high | medium | low
   Scope-risk: narrow | moderate | broad
   Directive: <instruction for future modifiers>
   Not-tested: <edge case not covered>
   ```
   Valid `<type>`: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.
5. **Push** and open a pull request against `main` with a clear
   description of what changed and why. Reference the originating issue.
6. **Review**:
   - CI must be green.
   - At least one maintainer review (for code); at least one domain expert
     (for clinical content).
   - For changes touching scoring, a second maintainer review plus the
     leakage-scan log must be attached.
7. **Merge**: squash-merge is the default; merge-commit allowed for PRs that
   preserve meaningful history.

---

## 4. Developer Setup

```bash
# Python 3.11+ recommended
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"

# Verify setup
PYTHONPATH=. pytest tests/ -x --tb=short
bash scripts/ci/anonymization_scan.sh
```

For GPU-backed model runs, see `docs/HARDWARE.md`.

---

## 5. Scope Boundaries

Contributions that fall within scope:
- New CPG graphs from published guidelines.
- New scenarios exercising edge cases.
- Bug fixes in scoring, normalizer, or scenario engine.
- New evaluator implementations (following the scoring interface).
- Documentation improvements.
- CI / infrastructure enhancements.

Contributions that are **out of scope**:
- Weakening the scoring ↔ agent information separation.
- Adding data subject to uncleared IP / licensing restrictions.
- Agents trained on CGA-Bench scenarios (benchmark must remain
  evaluation-only; any training corpus must be provably disjoint).
- Changes that entangle `cpg_engine/` or `assessor_core/` with
  agent-facing code paths.

---

## 6. Licensing of Contributions

By contributing, you agree that your contribution will be licensed under
[CC-BY 4.0](./LICENSE) (the same license as the rest of the benchmark).

---

## 7. Recognition

Substantial contributions (new graphs, major scenario packs, significant
bug fixes) will be credited in `CONTRIBUTORS.md` and, at maintainer
discretion, may qualify for co-authorship on subsequent publications
that use the contributed artefact.

---

## 8. Contact

During anonymous review: via OpenReview.
Post-publication: GitHub issues are the primary channel.
Security-sensitive reports: `SECURITY.md`.

Thanks again for helping CGA-Bench stay accurate and useful!
