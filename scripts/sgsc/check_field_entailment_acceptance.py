#!/usr/bin/env python3
"""P0-2: Field-level entailment acceptance report for Pilot-14 atoms.

Runs rule-based entailment checking over all accepted atoms from the SGSC
Pilot-14 batch and produces a sensitivity report at multiple thresholds.

Usage:
    PYTHONPATH=. python scripts/sgsc/check_field_entailment_acceptance.py
    PYTHONPATH=. python scripts/sgsc/check_field_entailment_acceptance.py --thresholds 0.4,0.5,0.6,0.7
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = REPO_ROOT / "configs" / "sgsc" / "pilot_14_registry.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

from sgsc.schemas.atom import RecommendationAtom  # noqa: E402
from sgsc.verification.entailment_checker import (  # noqa: E402
    ENTAILMENT_FIELDS,
    check_atoms_entailment,
    compare_entailment_thresholds,
)

logger = logging.getLogger("check_field_entailment")


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
    except Exception:
        return "unknown"


def _hash_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def load_pilot_atoms(sgsc_dir: Path) -> tuple[list[RecommendationAtom], list[Path]]:
    """Load all atoms from Pilot-14 output directories.

    Looks for atoms_smoke.json or {id}_atoms.json in each guideline dir.
    """
    atoms: list[RecommendationAtom] = []
    files: list[Path] = []

    for guideline_dir in sorted(sgsc_dir.iterdir()):
        if not guideline_dir.is_dir():
            continue
        gid = guideline_dir.name

        # Try multiple atom file patterns
        candidates = [
            guideline_dir / "atoms_smoke.json",
            guideline_dir / f"{gid}_atoms.json",
            guideline_dir / "atoms.json",
        ]

        for atom_file in candidates:
            if atom_file.exists():
                try:
                    data = json.loads(atom_file.read_text())
                    if isinstance(data, list):
                        for item in data:
                            try:
                                atom = RecommendationAtom.model_validate(item)
                                atoms.append(atom)
                            except Exception:
                                logger.debug("Skipping invalid atom in %s", atom_file)
                    files.append(atom_file)
                    logger.info(
                        "[%s] Loaded %d atoms from %s", gid, len(data) if isinstance(data, list) else 0, atom_file.name
                    )
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Failed to load %s: %s", atom_file, e)
                break  # Use first found file

    return atoms, files


def compute_field_pass_rates(
    atoms: list[RecommendationAtom],
    threshold: float = 0.5,
) -> dict[str, float]:
    """Compute per-field pass rates at a given threshold."""
    if not atoms:
        return dict.fromkeys(ENTAILMENT_FIELDS, 1.0)

    reports = check_atoms_entailment(atoms, action_threshold=threshold, guard_threshold=threshold)

    field_counts: dict[str, dict[str, int]] = {f: {"passed": 0, "total": 0} for f in ENTAILMENT_FIELDS}

    for report in reports:
        for fr in report.field_results:
            if fr.verdict == "NOT_APPLICABLE":
                continue
            field_counts[fr.field]["total"] += 1
            if fr.verdict in ("ENTAILED", "PARTIAL"):
                field_counts[fr.field]["passed"] += 1

    return {
        f: (counts["passed"] / counts["total"] if counts["total"] > 0 else 1.0) for f, counts in field_counts.items()
    }


def find_contradiction_candidates(
    atoms: list[RecommendationAtom],
    threshold: float = 0.5,
) -> list[dict[str, str]]:
    """Find atoms with NOT_ENTAILED on critical fields (action, timing)."""
    reports = check_atoms_entailment(atoms, action_threshold=threshold, guard_threshold=threshold)
    candidates: list[dict[str, str]] = []

    critical_fields = {"action", "timing"}
    for report in reports:
        failed_critical = [
            fr.field for fr in report.field_results if fr.field in critical_fields and fr.verdict == "NOT_ENTAILED"
        ]
        if failed_critical:
            candidates.append(
                {
                    "atom_id": report.atom_id,
                    "failed_fields": ", ".join(failed_critical),
                }
            )

    return candidates


def run_check(
    sgsc_dir: Path,
    thresholds: list[float],
) -> dict:
    """Run the full field entailment acceptance check."""
    atoms, input_files = load_pilot_atoms(sgsc_dir)
    logger.info("Loaded %d total atoms from %d files", len(atoms), len(input_files))

    if not atoms:
        return {
            "check_name": "field_entailment_acceptance",
            "status": "warn",
            "commit": _git_commit(),
            "input_hash": _hash_files(input_files),
            "output_hash": "",
            "metrics": {
                "total_atoms": 0,
                "field_pass_rates": {},
                "threshold_sensitivity": {},
                "fuzzy_only_count": 0,
                "contradiction_candidates": 0,
            },
            "failures": [{"detail": "No atoms found in sgsc_output"}],
        }

    # Field pass rates at default threshold
    default_threshold = 0.5
    field_rates = compute_field_pass_rates(atoms, default_threshold)

    # Multi-threshold sensitivity
    threshold_comparison = compare_entailment_thresholds(atoms, thresholds)
    threshold_sensitivity = {}
    for t, counts in threshold_comparison.items():
        threshold_sensitivity[str(t)] = {
            "strict": counts["n_strict_passing"],
            "lenient": counts["n_lenient_passing"],
            "rejected": counts["n_rejected"],
            "partial_only": counts["n_partial_only"],
        }

    # Fuzzy-only atoms (pass lenient but not strict at default threshold)
    default_counts = threshold_comparison.get(default_threshold, {})
    fuzzy_only = default_counts.get("n_partial_only", 0)

    # Contradiction candidates
    contradictions = find_contradiction_candidates(atoms, default_threshold)

    # Determine status
    if contradictions:
        status = "warn"
    else:
        status = "pass"

    # Check if any field has <80% pass rate
    low_fields = [f for f, r in field_rates.items() if r < 0.8]
    if low_fields:
        status = "warn"

    failures: list[dict] = []
    for c in contradictions:
        failures.append(
            {
                "atom_id": c["atom_id"],
                "detail": f"NOT_ENTAILED on critical fields: {c['failed_fields']}",
            }
        )

    report = {
        "check_name": "field_entailment_acceptance",
        "status": status,
        "commit": _git_commit(),
        "input_hash": _hash_files(input_files),
        "metrics": {
            "total_atoms": len(atoms),
            "field_pass_rates": {f: round(r, 4) for f, r in field_rates.items()},
            "threshold_sensitivity": threshold_sensitivity,
            "fuzzy_only_count": fuzzy_only,
            "contradiction_candidates": len(contradictions),
        },
        "failures": failures,
    }

    report_bytes = json.dumps(report, sort_keys=True).encode()
    report["output_hash"] = hashlib.sha256(report_bytes).hexdigest()

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P0-2: Field entailment acceptance report")
    parser.add_argument("--sgsc-dir", default=str(REPO_ROOT / "sgsc_output"))
    parser.add_argument("--thresholds", default="0.4,0.5,0.6,0.7")
    parser.add_argument(
        "--output", default=str(REPO_ROOT / "evidence_pack" / "analysis" / "field_entailment_report.json")
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    sgsc_dir = Path(args.sgsc_dir)
    thresholds = [float(t) for t in args.thresholds.split(",")]

    if not sgsc_dir.is_dir():
        logger.error("SGSC output dir not found: %s", sgsc_dir)
        return 1

    report = run_check(sgsc_dir, thresholds)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("Report written to %s", output_path)

    m = report["metrics"]
    print("\n=== Field Entailment Acceptance ===")
    print(f"Status: {report['status'].upper()}")
    print(f"Total atoms: {m['total_atoms']}")
    print(f"Fuzzy-only: {m['fuzzy_only_count']}")
    print(f"Contradiction candidates: {m['contradiction_candidates']}")
    print("\nPer-field pass rates (threshold=0.5):")
    for field, rate in m["field_pass_rates"].items():
        print(f"  {field:12s}: {rate:.1%}")
    print("\nThreshold sensitivity:")
    for t, counts in m["threshold_sensitivity"].items():
        print(f"  {t}: strict={counts['strict']}, lenient={counts['lenient']}, rejected={counts['rejected']}")

    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
