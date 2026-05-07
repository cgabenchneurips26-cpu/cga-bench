#!/bin/bash
# Anonymization Scan — fails CI if any identifying string appears in the repo.
# Run as:
#   bash scripts/ci/anonymization_scan.sh
#
# Intended to be wired into CI (GitHub Actions) or a lefthook pre-commit hook.
# For the camera-ready version of the benchmark, the forbidden patterns are
# relaxed once the real author identities are disclosed — this guard is only
# active during the NeurIPS 2026 D&B double-blind review phase.

set -euo pipefail

# Forbidden substrings that would de-anonymize the submission.
FORBIDDEN_PATTERNS=(
    "/home/anonymous-org/"
    "/home/anonymous-user/"
    "anonymous-project"
    "tommy_personal"
    "anonymous-org@"            # ssh username leak
    "anonymous-user@"        # ssh username leak
)

# Excluded paths.
# Rationale:
#   - caches / local settings / archives: never shipped
#   - operational deploy scripts and run logs: NOT part of the anonymous upload,
#     handled at submission time by scripts/prepare_anonymous_repo.py which
#     strips PII on copy. Leaving these in the source tree is fine.
#   - anonymizer rule-definer scripts: by design contain the forbidden patterns
#     as regex literals.
#   - meta-documents about this guard itself: reference the patterns for
#     pedagogy; excluding them keeps the guard self-referentially sane.
EXCLUDES=(
    ":(exclude).hypothesis/"
    ":(exclude).pytest_cache/"
    ":(exclude).ruff_cache/"
    ":(exclude).mypy_cache/"
    ":(exclude).claude/"
    ":(exclude).omc/"
    ":(exclude)_archive/"
    ":(exclude)anonymous_repo/"
    ":(exclude)reports/"
    ":(exclude)*.pyc"
    ":(exclude)requirements.lock"
    # Meta-documents about anonymization (contain the patterns as examples):
    ":(exclude)docs/ANONYMIZATION_SCAN_REPORT.md"
    ":(exclude)docs/NEURIPS_DB_REPRO_CHECKLIST.md"
    ":(exclude)scripts/ci/anonymization_scan.sh"
    ":(exclude)scripts/prepare_anonymous_repo.py"
    ":(exclude)scripts/experiments/p7_build_release.py"
    # Operational deployment scripts — stripped by prepare_anonymous_repo.py
    # at submission time; not part of the scientific artefact:
    ":(exclude)scripts/experiments/*.sh"
    ":(exclude)scripts/experiments/deploy_*.py"
    # Agent run logs (stack-trace paths) — stripped at submission time:
    ":(exclude)evidence_pack/ex1_llm_judge_*/log.txt"
    # Internal session-status memos (pre-P0 defense work notes) — excluded
    # from the scientific artefact scope:
    ":(exclude)docs/attack_gap_exp_exp/260405_*.md"
    ":(exclude)docs/attack_gap_exp_exp/260416_*.md"
    ":(exclude)docs/attack_gap_exp_exp/new_server_deploy.md"
)

EXIT_CODE=0

for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
    matches=$(git grep --untracked -nE -- "$pattern" "${EXCLUDES[@]}" 2>/dev/null || true)
    if [[ -n "$matches" ]]; then
        echo "ANONYMIZATION LEAK: pattern '$pattern' found:"
        echo "$matches"
        echo
        EXIT_CODE=1
    fi
done

if [[ $EXIT_CODE -eq 0 ]]; then
    echo "Anonymization scan passed: no forbidden substrings detected."
else
    echo "--"
    echo "Anonymization scan FAILED. Fix the above occurrences before committing."
    echo "For bulk remediation, run: python scripts/prepare_anonymous_repo.py"
    echo "(This produces an anonymised copy under anonymous_repo/ without"
    echo " mutating the source tree.)"
fi

exit $EXIT_CODE
