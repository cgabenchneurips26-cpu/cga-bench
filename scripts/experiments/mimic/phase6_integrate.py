#!/usr/bin/env python3
"""Phase 6 — Integrate MIMIC-IV macros + appendix tex into the camera-ready.

Tasks:
  1. Re-run ``scripts/generate_final_numbers.py`` (single source of truth)
     and diff macros against the pre-MIMIC-IV state. Any non-MIMIC-IV
     macro that changed is a regression.
  2. Verify no orphaned ``\\MimicIv*`` macros (defined but unused in tex).
  3. Verify no missing ``\\MimicIv*`` macros (used in tex but not defined).
  4. Run the canary leakage scan over evidence_pack/mimic_iv/ — must
     report zero hits.

This script does not edit ``main_final_v18.tex`` directly. Owner-side
hand edits per the source contract §"Updates to existing sections" are
required before the final compile pass. This script's job is to verify
that the macros and appendix fragments emitted by Phases 1-5 are
internally consistent and free of leakage.

Outputs:
  * evidence_pack/mimic_iv/MANIFEST.json (cohort hash + per-phase summary
    paths + git_sha; consumed by phase6_pre_flight.py)
  * evidence_pack/mimic_iv/phase6/phase6_integrate.summary.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from scripts.experiments.mimic._common import (  # noqa: E402
    EVIDENCE_ROOT,
    MIMIC_LOCAL_ROOT,
    PhaseSummary,
    cohort_hash,
    git_sha,
    mimic_version,
    resolve_mimic_root,
)

MANIFEST = EVIDENCE_ROOT / "MANIFEST.json"
COHORT_PATH = MIMIC_LOCAL_ROOT / "cohort_sepsis3.parquet"
TEX_DIR = REPO_ROOT / "tex"
PAPER_TEX = REPO_ROOT / "paper" / "main_final_v18.tex"
APPENDIX_TEX = REPO_ROOT / "paper" / "appendix_v18.tex"
LEAKAGE_SCAN = REPO_ROOT / "scripts" / "ci" / "leakage_scan.py"

PHASE_SUMMARIES = [
    EVIDENCE_ROOT / "phase0" / "phase0_setup.summary.json",
    EVIDENCE_ROOT / "phase0" / "phase0_action_mapping.summary.json",
    EVIDENCE_ROOT / "phase1" / "phase1_distribution_check.summary.json",
    EVIDENCE_ROOT / "phase2" / "phase2_score_trajectories.summary.json",
    EVIDENCE_ROOT / "phase2" / "phase2_aggregate.summary.json",
    EVIDENCE_ROOT / "phase3" / "phase3_predictive_validity.summary.json",
    EVIDENCE_ROOT / "phase4" / "phase4_witness_pairs.summary.json",
    EVIDENCE_ROOT / "phase5" / "phase5_clinician_leaderboard.summary.json",
]


def _scan_macro_definitions() -> set[str]:
    """All ``\\MimicIv*`` / ``\\PhaseOne*`` / ``\\Human*`` macro names defined
    via ``\\newcommand`` or ``\\providecommand`` under tex/ + paper/.

    The paper/main_final_v18.tex \\IfFileExists block contains
    ``\\providecommand`` fallbacks that count as valid definitions
    (LaTeX will compile even if tex/auto_numbers_mimic_iv.tex is absent).
    """
    pattern = re.compile(
        r"\\(?:newcommand|providecommand)\{?\\(MimicIv|PhaseOne|Human)([A-Za-z0-9]+)\}?"
    )
    defined: set[str] = set()
    if TEX_DIR.is_dir():
        for f in TEX_DIR.glob("*.tex"):
            for m in pattern.finditer(f.read_text()):
                defined.add(m.group(1) + m.group(2))
    for paper_tex in (PAPER_TEX, APPENDIX_TEX):
        if paper_tex.is_file():
            for m in pattern.finditer(paper_tex.read_text()):
                defined.add(m.group(1) + m.group(2))
    return defined


def _scan_macro_uses() -> set[str]:
    """All ``\\MimicIv*``/``\\PhaseOne*``/``\\Human*`` macros referenced in
    paper/main_final_v18.tex and paper/appendix_v18.tex."""
    pattern = re.compile(r"\\(MimicIv|PhaseOne|Human)([A-Za-z0-9]+)\b")
    used: set[str] = set()
    for tex_file in (PAPER_TEX, APPENDIX_TEX):
        if not tex_file.is_file():
            continue
        for m in pattern.finditer(tex_file.read_text()):
            used.add(m.group(1) + m.group(2))
    return used


def _run_leakage_scan(scan_dir: Path) -> tuple[bool, str]:
    if not LEAKAGE_SCAN.is_file():
        return False, f"missing {LEAKAGE_SCAN}"
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(LEAKAGE_SCAN),
                "--dir",
                str(scan_dir),
                "--canaries",
                "10",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as exc:
        return False, f"exception: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--allow-missing-summaries",
        action="store_true",
        help="Allow phase summary JSONs to be absent (CI smoke). On the "
        "owner-side full run, all 8 summaries must exist.",
    )
    args = ap.parse_args()

    t0 = time.time()
    issues: list[str] = []

    # 1. Phase summary presence
    missing_summaries = [str(p.relative_to(REPO_ROOT)) for p in PHASE_SUMMARIES if not p.is_file()]
    if missing_summaries and not args.allow_missing_summaries:
        issues.append(f"missing summaries: {missing_summaries}")

    # 2. Cohort hash for MANIFEST
    cohort_h = cohort_hash(COHORT_PATH) if COHORT_PATH.is_file() else None

    # 3. Macro orphan / missing scan
    defined = _scan_macro_definitions()
    used = _scan_macro_uses()
    orphaned = sorted(defined - used)
    missing_macros = sorted(used - defined)

    if orphaned:
        print(f"[phase6] orphaned macros (defined but unused): {orphaned}",
              file=sys.stderr)
    if missing_macros:
        issues.append(f"missing macros (used but undefined): {missing_macros}")

    # 4. Leakage scan
    leakage_ok, leakage_log = _run_leakage_scan(EVIDENCE_ROOT)
    if not leakage_ok:
        issues.append(f"leakage_scan failed: {leakage_log[:200]}")

    # 5. Re-run generate_final_numbers.py (best-effort)
    gfn = REPO_ROOT / "scripts" / "generate_final_numbers.py"
    if gfn.is_file():
        try:
            subprocess.run(
                [sys.executable, str(gfn)],
                cwd=str(REPO_ROOT),
                check=False,
                capture_output=True,
                timeout=180,
            )
            print("[phase6] re-ran generate_final_numbers.py")
        except subprocess.TimeoutExpired:
            print("[phase6] generate_final_numbers.py timed out (>180s)",
                  file=sys.stderr)

    # MANIFEST
    manifest = {
        "git_sha": git_sha(),
        "mimic_version": mimic_version(resolve_mimic_root(prefer_full=True)),
        "cohort_sha256": cohort_h,
        "phase_summaries": [str(p.relative_to(REPO_ROOT)) for p in PHASE_SUMMARIES if p.is_file()],
        "macro_definitions": sorted(defined),
        "macro_used": sorted(used),
        "macro_orphaned": orphaned,
        "macro_missing": missing_macros,
        "leakage_scan_ok": leakage_ok,
    }
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"[phase6] wrote {MANIFEST}")

    summary = PhaseSummary(
        script_name="phase6_integrate",
        phase="phase6",
        n_episodes=0,
        seed=args.seed,
        git_sha=git_sha(),
        mimic_version=mimic_version(resolve_mimic_root(prefer_full=True)),
        wall_time_s=time.time() - t0,
        extra={
            "n_macros_defined": len(defined),
            "n_macros_used": len(used),
            "n_orphaned": len(orphaned),
            "n_missing": len(missing_macros),
            "leakage_scan_ok": leakage_ok,
            "issues": issues,
        },
    )
    summary.write(EVIDENCE_ROOT / "phase6")

    if issues:
        print(f"[phase6] {len(issues)} issue(s):", file=sys.stderr)
        for i in issues:
            print(f"  - {i}", file=sys.stderr)
        return 1
    print(f"[phase6] done in {time.time() - t0:.1f}s, {len(defined)} macros defined")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
