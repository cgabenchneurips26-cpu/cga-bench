#!/usr/bin/env python3
r"""Verify β-1+β-3 stemming + threshold change on Pilot-14 atoms.

Loads the existing 9-atom smoke test and runs entailment at both old (0.5)
and new (0.6) defaults, reporting before/after.

Usage:
    PYTHONPATH=. python scripts/sgsc/verify_threshold_change.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from sgsc.schemas.atom import RecommendationAtom  # noqa: E402
from sgsc.verification.entailment_checker import check_atoms_entailment  # noqa: E402

ATOMS_PATH = REPO_ROOT / "sgsc_output" / "ssc_sepsis_hour1_bundle" / "atoms_smoke.json"


def _load_atoms(path: Path) -> list[RecommendationAtom]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [RecommendationAtom.model_validate(a) for a in raw]


def _run_at_threshold(atoms: list[RecommendationAtom], threshold: float) -> dict[str, int]:
    reports = check_atoms_entailment(atoms, action_threshold=threshold, guard_threshold=threshold)
    n_strict = sum(1 for r in reports if r.strict_passed)
    n_lenient = sum(1 for r in reports if r.all_passed)
    n_rejected = sum(1 for r in reports if not r.all_passed)
    n_contradictions = 0
    for r in reports:
        action_result = next((f for f in r.field_results if f.field == "action"), None)
        if action_result and action_result.verdict == "NOT_ENTAILED":
            n_contradictions += 1
    return {
        "threshold": threshold,
        "strict": n_strict,
        "lenient": n_lenient,
        "rejected": n_rejected,
        "contradictions": n_contradictions,
    }


def main() -> int:
    if not ATOMS_PATH.exists():
        print(f"ERROR: atoms file not found: {ATOMS_PATH}")
        return 1

    atoms = _load_atoms(ATOMS_PATH)
    print(f"Loaded {len(atoms)} atoms from {ATOMS_PATH.name}\n")

    print(f"{'Threshold':<12} {'Strict':<8} {'Lenient':<9} {'Rejected':<10} {'Contradictions'}")
    print("-" * 55)

    for t in [0.5, 0.6, 0.7]:
        r = _run_at_threshold(atoms, t)
        print(f"{r['threshold']:<12.1f} {r['strict']:<8} {r['lenient']:<9} {r['rejected']:<10} {r['contradictions']}")

    print("\nPer-atom detail at threshold=0.6:")
    reports = check_atoms_entailment(atoms, action_threshold=0.6, guard_threshold=0.6)
    for report in reports:
        tag = "PASS" if report.all_passed else "FAIL"
        fields = [(f.field, f.verdict, f"{f.confidence:.2f}" if f.confidence else "-") for f in report.field_results]
        print(f"  [{tag}] {report.atom_id}")
        for field, verdict, conf in fields:
            print(f"         {field:12s} {verdict:16s} conf={conf}")

    # Verify critical criterion: 0 contradictions at 0.6
    r06 = _run_at_threshold(atoms, 0.6)
    if r06["contradictions"] > 0:
        print(f"\nFAIL: {r06['contradictions']} contradiction(s) remain at 0.6 — stemming incomplete")
        return 1
    print("\nPASS: 0 contradictions at threshold=0.6 (use_balanced_crystalloids resolved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
