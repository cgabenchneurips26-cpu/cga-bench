#!/usr/bin/env python3
"""Phase 6 pre-flight — final audit before camera-ready submission.

Checks executed (HALT on any failure):
  1. All 8 phase summary JSONs exist and parse.
  2. ``cohort_sepsis3.parquet`` hash recorded in MANIFEST.json matches
     the file on disk.
  3. ``pytest tests/test_mimic_iv_*.py`` exits 0.
  4. ``scripts/ci/leakage_scan.py --dir evidence_pack/mimic_iv/
     --canaries 10`` reports 0 hits.
  5. Git working tree is clean outside ``data/`` (which is gitignored).

This script does not modify anything; it reports a single PASS / FAIL
verdict to stdout with a per-check breakdown.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from scripts.experiments.mimic._common import (  # noqa: E402
    EVIDENCE_ROOT,
    MIMIC_LOCAL_ROOT,
    cohort_hash,
)
from scripts.experiments.mimic.phase6_integrate import PHASE_SUMMARIES  # noqa: E402

MANIFEST = EVIDENCE_ROOT / "MANIFEST.json"
COHORT_PATH = MIMIC_LOCAL_ROOT / "cohort_sepsis3.parquet"
LEAKAGE_SCAN = REPO_ROOT / "scripts" / "ci" / "leakage_scan.py"


def _check_summaries() -> tuple[bool, str]:
    missing = [p for p in PHASE_SUMMARIES if not p.is_file()]
    if missing:
        return False, f"missing: {[str(p.relative_to(REPO_ROOT)) for p in missing]}"
    for p in PHASE_SUMMARIES:
        try:
            json.loads(p.read_text())
        except Exception as exc:
            return False, f"{p.name}: {exc}"
    return True, f"{len(PHASE_SUMMARIES)} summaries OK"


def _check_cohort_hash() -> tuple[bool, str]:
    if not MANIFEST.is_file():
        return False, "MANIFEST.json missing"
    if not COHORT_PATH.is_file():
        return False, "cohort_sepsis3.parquet missing"
    manifest = json.loads(MANIFEST.read_text())
    expected = manifest.get("cohort_sha256")
    if not expected:
        return False, "MANIFEST.cohort_sha256 missing"
    actual = cohort_hash(COHORT_PATH)
    if actual != expected:
        return False, f"hash mismatch: expected {expected[:12]} got {actual[:12]}"
    return True, f"cohort hash OK ({actual[:12]})"


def _check_pytest() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-k", "mimic_iv", "-q"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
        )
        ok = result.returncode == 0
        last = "\n".join(result.stdout.splitlines()[-5:])
        return ok, last
    except Exception as exc:
        return False, str(exc)


def _check_leakage() -> tuple[bool, str]:
    if not LEAKAGE_SCAN.is_file():
        return False, "leakage_scan.py missing"
    try:
        result = subprocess.run(
            [sys.executable, str(LEAKAGE_SCAN), "--dir", str(EVIDENCE_ROOT),
             "--canaries", "10"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        ok = result.returncode == 0
        return ok, result.stdout.strip().splitlines()[-1] if result.stdout else ""
    except Exception as exc:
        return False, str(exc)


def _check_git_clean() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        # filter out gitignored data/
        lines = [
            ln for ln in result.stdout.splitlines()
            if ln.strip() and not ln.endswith(" data/") and "data/mimic_iv_local" not in ln
        ]
        if lines:
            return False, f"{len(lines)} dirty file(s) outside data/"
        return True, "git tree clean (outside data/)"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--skip", default="",
        help="Comma-separated check names to skip: summaries, cohort, "
        "pytest, leakage, git",
    )
    args = ap.parse_args()
    skip = set(args.skip.split(",")) if args.skip else set()

    checks = [
        ("summaries", _check_summaries),
        ("cohort", _check_cohort_hash),
        ("pytest", _check_pytest),
        ("leakage", _check_leakage),
        ("git", _check_git_clean),
    ]
    print(f"[pre-flight] starting {time.strftime('%Y-%m-%d %H:%M:%S')}")
    rows: list[tuple[str, bool, str]] = []
    overall_ok = True
    for name, fn in checks:
        if name in skip:
            print(f"  [{name:10s}] SKIP")
            continue
        ok, detail = fn()
        marker = "PASS" if ok else "FAIL"
        print(f"  [{name:10s}] {marker}  {detail}")
        rows.append((name, ok, detail))
        if not ok:
            overall_ok = False

    print(f"[pre-flight] overall: {'PASS' if overall_ok else 'FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
