# Anonymization Scan Report — Pre-Submission

**Scan date**: 2026-04-21
**Target submission**: NeurIPS 2026 Datasets & Benchmarks Track
**Status**: ❌ ONE REAL LEAK + several items to verify

---

## 1. Executive Finding

One class of real anonymization leak found: **absolute filesystem paths containing a
username (`anonymous-user`) in the shipped documentation and test files**. This leaks the system
user identity of the dataset author. It MUST be fixed before anonymous submission.

Everything else (README, LICENSE, paper, Croissant metadata, Zenodo skeleton) passes
the scan with no identifiers leaking.

---

## 2. Detailed Findings

### 2.1 ❌ FAIL — Username in absolute paths

**Pattern**: `${CGA_BENCH_ROOT}`

**Locations found**:

| File | Lines | Sample |
|---|---|---|
| `CLAUDE.md` | 39, 43, 47, 51 | `PYTHONPATH=${CGA_BENCH_ROOT} \` |
| `docs/attack_gap_exp_exp/260421_p0_defense_implementation_report.md` | 490, 494, 498, 502, 506, 508, 512 | same `PYTHONPATH=...` pattern |
| `tests/test_e2e/test_e2e_comprehensive_pipeline.py` | 21 | `sys.path.insert(0, "${CGA_BENCH_ROOT}")` |
| `docs/scenario_expansion/episode_690_run.md` | multiple | path references |
| `docs/cres_4_design.md` | multiple | path references |
| `docs/attack_gap_exp_exp/260416_session_status.md` | multiple | path references |
| `docs/attack_gap_exp_exp/260418_defence_exp_2.md` | multiple | path references |
| `docs/attack_gap_exp_exp/260421_heldout.md` | multiple | path references |
| `docs/ANNOTATION_GUIDE_ACTION_NORMALIZATION.md` | multiple | path references |
| `AUDIT_CHECKLIST.md` | multiple | path references |

**Risk**: A reviewer copying any of these strings into a search engine, combined with
the `anonymous-org` directory name and `anonymous-project` repo name, could materially narrow
the author pool and potentially de-anonymize the submission.

### 2.2 Proposed Fix (two-step)

**Step 1 — Replace absolute paths with a repo-relative placeholder**

For documentation and instructional commands:

```diff
-PYTHONPATH=${CGA_BENCH_ROOT} \
+PYTHONPATH=$(pwd) \
   python scripts/experiments/full_690_runner.py oss120b results/full_706_v5
```

Or, for a repo with a canonical parent path, use `${CGA_BENCH_ROOT}`:

```diff
-PYTHONPATH=${CGA_BENCH_ROOT} \
+PYTHONPATH=${CGA_BENCH_ROOT:-$(pwd)} \
   python scripts/experiments/full_690_runner.py oss120b results/full_706_v5
```

For code:

```diff
-sys.path.insert(0, "${CGA_BENCH_ROOT}")
+from pathlib import Path
+sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
```

**Step 2 — Add a CI guard**

Add a pre-commit hook or CI step that fails on any occurrence of the forbidden
substring:

```bash
# scripts/ci/anonymization_scan.sh
#!/bin/bash
set -euo pipefail

FORBIDDEN_PATTERNS=(
    "/home/anonymous-org/"
    "anonymous-project"
    "anonymous-user"           # case-sensitive; trips `anonymous-user` as a username anywhere
)

for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    matches=$(git grep -n --untracked -- "$pattern" || true)
    if [[ -n "$matches" ]]; then
        echo "❌ Anonymization leak: pattern '$pattern' found:"
        echo "$matches"
        exit 1
    fi
done
echo "✅ Anonymization scan passed."
```

Wire this into `.github/workflows/ci.yml` or `lefthook.yml`.

### 2.3 ✅ PASS — README / LICENSE / paper

- `README.md` grep for `@gmail|@anonymous-org|University|Korea|KAIST|Seoul|anonymous-org|researcher_|Copyright...` → **no hits**.
- `LICENSE` → "Copyright (c) 2026 CGA-Bench Authors" (generic).
- `paper/main_final_v17.tex` → `\author{Anonymous Authors}` ✅.

### 2.4 ✅ PASS — Croissant / Zenodo

- `croissant.json`: `creator = CGA-Bench Authors`, `url = github.com/anonymous/cga-bench`.
- `.zenodo.json`: all personal fields wrapped in `_comment` placeholders; `creators` is generic.
- `CITATION.cff`: `authors = [CGA-Bench Authors]`, explicit note that real names come at camera-ready.

### 2.5 ⚠ VERIFY — Git history

Not fixable by file edits alone. Recommended actions (user-performed):

```bash
# Check who has been committing:
git log --format="%an <%ae>" | sort -u

# If real names appear, options are:
#   1. Keep git history if commit authors are institutional / generic aliases.
#   2. Filter-repo / squash-reset for anonymous upload:
#      git filter-repo --mailmap <path-to-generic-mailmap.txt>
#   3. For anonymous.4open.science, history is stripped automatically on upload.
```

At minimum, the final "anonymous upload" snapshot should not contain commit author
metadata that narrows the author pool.

### 2.6 ⚠ VERIFY — Binary / auxiliary artefacts

- `evidence_pack/leakage_scan_200canaries.log`: verify it does not contain personal
  paths (the leakage scan is scoped to canary strings, not usernames, so should be
  clean — confirm).
- `paper/main_final_v17.pdf` and other PDFs in `paper/`: if any compiled PDF embeds
  author metadata via `\hypersetup{pdfauthor=...}`, strip before submission.
- `data_release/v5.0/LICENSE`, `data_release/v1.0/DATA_GOVERNANCE.md`: scanned
  headers clean; full contents to be verified.

---

## 3. Action Items (ordered)

1. **Global replace** of `${CGA_BENCH_ROOT}` in docs and code
   with repo-relative equivalents. Estimated 10–20 minute task.
2. **Install CI guard** `scripts/ci/anonymization_scan.sh`. Estimated 10 minutes.
3. **Strip PDF metadata** from any compiled paper PDF before submission:
   ```bash
   exiftool -all= paper/main_final_v17.pdf
   ```
4. **Git history decision**: confirm commit authors are generic or plan the
   anonymization strategy for upload.
5. **One last `grep` pass** immediately before submission:
   ```bash
   git grep -nE "(anonymous-org|anonymous-user|anonymous-project|/home/[a-z]+/)" || echo "CLEAN"
   ```

---

## 4. Summary Table

| Surface | Finding |
|---|---|
| README.md | ✅ clean |
| LICENSE | ✅ generic |
| paper/*.tex | ✅ anonymous authors |
| croissant.json | ✅ anonymous placeholders |
| CITATION.cff | ✅ anonymous placeholders |
| .zenodo.json | ✅ anonymous placeholders |
| docs/*.md | ❌ `anonymous-user` absolute paths (multiple files) |
| CLAUDE.md | ❌ `anonymous-user` absolute paths |
| tests/test_e2e/test_e2e_comprehensive_pipeline.py | ❌ hardcoded `anonymous-user` path in `sys.path.insert` |
| Git history | ⚠ verify |
| Compiled PDFs | ⚠ strip exif |

Resolving Item 2.1 (§2.1 + §2.2) unblocks the submission from an anonymization
perspective.

---

*End of anonymization scan report.*
