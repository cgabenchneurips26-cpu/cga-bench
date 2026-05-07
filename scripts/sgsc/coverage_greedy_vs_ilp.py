#!/usr/bin/env python3
"""Compare greedy set-cover vs ILP (optimal) solver per guideline.

Loads coverage data from sgsc_output/{guideline_id}/ directories, runs both
solvers on the reconstructed universe + vectors, and produces a per-guideline
comparison table.

Usage:
    PYTHONPATH=. python scripts/sgsc/coverage_greedy_vs_ilp.py
    PYTHONPATH=. python scripts/sgsc/coverage_greedy_vs_ilp.py \
        --registry configs/sgsc/pilot_14_registry.json \
        --output-dir evidence_pack/analysis/
    PYTHONPATH=. python scripts/sgsc/coverage_greedy_vs_ilp.py -v
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

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

from sgsc.optimizer.set_cover_solver import (  # noqa: E402
    SetCoverConfig,
    solve_set_cover,
    solve_set_cover_ilp,
)
from sgsc.schemas.coverage import CoverageVector  # noqa: E402

DEFAULT_REGISTRY = REPO_ROOT / "configs" / "sgsc" / "pilot_14_registry.json"
DEFAULT_SGSC_DIR = REPO_ROOT / "sgsc_output"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "evidence_pack" / "analysis"
OUTPUT_FILENAME = "greedy_vs_ilp_comparison.json"

RATIO_WARN_THRESHOLD = 1.5
RATIO_FAIL_THRESHOLD = 2.0

logger = logging.getLogger("coverage_greedy_vs_ilp")


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _git_commit() -> str:
    """Return current HEAD commit hash, or 'unknown' on failure."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _hash_bytes(data: bytes) -> str:
    """Return SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _hash_files(paths: list[Path]) -> str:
    """Return SHA-256 over concatenated bytes of all existing files."""
    h = hashlib.sha256()
    for p in sorted(paths):
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------


def load_registry(registry_path: Path) -> list[str]:
    """Return list of guideline_ids from registry JSON.

    Args:
        registry_path: Path to registry JSON file with a ``guidelines`` list.

    Returns:
        Ordered list of guideline_id strings.

    Raises:
        FileNotFoundError: If the registry file does not exist.
        KeyError: If the registry JSON lacks the expected structure.
    """
    if not registry_path.exists():
        raise FileNotFoundError(f"Registry not found: {registry_path}")
    data = json.loads(registry_path.read_text())
    return [g["guideline_id"] for g in data["guidelines"]]


# ---------------------------------------------------------------------------
# Coverage data loading
# ---------------------------------------------------------------------------


def _load_coverage_vectors(
    guideline_id: str,
    sgsc_dir: Path,
) -> tuple[frozenset[str], list[CoverageVector]] | None:
    """Load universe and vectors from {guideline_id}_coverage.json.

    Returns None if the file is missing or contains no vector data.

    The coverage JSON may contain:
    - ``coverage_items``: list of item dicts with ``item_id``
    - ``vectors``: list of dicts with ``scenario_id`` and ``covered_items``

    When ``coverage_items`` and ``vectors`` are both non-empty they are used
    to reconstruct the universe and CoverageVector objects.  When they are
    absent (legacy format with only summary counts), None is returned.

    Args:
        guideline_id: Guideline identifier string.
        sgsc_dir: Base directory containing per-guideline subdirectories.

    Returns:
        ``(universe, vectors)`` tuple or ``None`` if no vector data available.
    """
    cov_path = sgsc_dir / guideline_id / f"{guideline_id}_coverage.json"
    if not cov_path.exists():
        logger.debug("[%s] Coverage file not found: %s", guideline_id, cov_path)
        return None

    data = json.loads(cov_path.read_text())

    coverage_items_raw: list[dict] = data.get("coverage_items", [])
    vectors_raw: list[dict] = data.get("vectors", [])

    if not coverage_items_raw or not vectors_raw:
        logger.debug(
            "[%s] Coverage file has no vector data (coverage_items=%d, vectors=%d)",
            guideline_id,
            len(coverage_items_raw),
            len(vectors_raw),
        )
        return None

    universe: frozenset[str] = frozenset(item["item_id"] for item in coverage_items_raw if "item_id" in item)
    if not universe:
        logger.debug("[%s] Universe is empty after parsing coverage_items", guideline_id)
        return None

    vectors: list[CoverageVector] = []
    for v in vectors_raw:
        scenario_id = v.get("scenario_id", "")
        covered_raw = v.get("covered_items", [])
        if not scenario_id:
            continue
        vectors.append(
            CoverageVector(
                scenario_id=scenario_id,
                covered_items=frozenset(covered_raw),
            )
        )

    if not vectors:
        logger.debug("[%s] No valid vectors parsed from coverage file", guideline_id)
        return None

    return universe, vectors


def _atoms_exist(guideline_id: str, sgsc_dir: Path) -> bool:
    """Return True if atoms_smoke.json exists for this guideline."""
    return (sgsc_dir / guideline_id / "atoms_smoke.json").exists()


# ---------------------------------------------------------------------------
# Per-guideline comparison
# ---------------------------------------------------------------------------


def _compare_guideline(
    guideline_id: str,
    sgsc_dir: Path,
    config: SetCoverConfig,
) -> dict:
    """Run greedy and ILP solvers for one guideline.

    Args:
        guideline_id: Guideline identifier.
        sgsc_dir: Base directory for sgsc_output.
        config: Shared SetCoverConfig for both solvers.

    Returns:
        Dict with keys: guideline_id, status, targets, greedy_scenarios,
        ilp_scenarios, ratio, greedy_uncovered, ilp_uncovered.
        ``status`` is one of "ok", "no_data", "no_atoms", "error".
    """
    result: dict = {
        "guideline_id": guideline_id,
        "status": "ok",
        "targets": 0,
        "greedy_scenarios": 0,
        "ilp_scenarios": 0,
        "ratio": 1.0,
        "greedy_uncovered": 0,
        "ilp_uncovered": 0,
    }

    # Require atoms_smoke.json as presence gate (per spec)
    if not _atoms_exist(guideline_id, sgsc_dir):
        logger.info("[%s] Skipping — no atoms_smoke.json", guideline_id)
        result["status"] = "no_atoms"
        return result

    loaded = _load_coverage_vectors(guideline_id, sgsc_dir)
    if loaded is None:
        logger.info("[%s] Skipping — no vector data in coverage file", guideline_id)
        result["status"] = "no_data"
        return result

    universe, vectors = loaded
    result["targets"] = len(universe)

    try:
        greedy = solve_set_cover(vectors, universe, config)
        ilp = solve_set_cover_ilp(vectors, universe, config)
    except Exception as exc:
        logger.warning("[%s] Solver error: %s", guideline_id, exc)
        result["status"] = "error"
        return result

    greedy_count = len(greedy.selected_ids)
    ilp_count = len(ilp.selected_ids)

    ratio = (greedy_count / ilp_count) if ilp_count > 0 else 1.0

    result["greedy_scenarios"] = greedy_count
    result["ilp_scenarios"] = ilp_count
    result["ratio"] = round(ratio, 4)
    result["greedy_uncovered"] = len(greedy.uncovered_items)
    result["ilp_uncovered"] = len(ilp.uncovered_items)

    logger.info(
        "[%s] greedy=%d  ilp=%d  ratio=%.3f  uncovered(g=%d, i=%d)",
        guideline_id,
        greedy_count,
        ilp_count,
        ratio,
        len(greedy.uncovered_items),
        len(ilp.uncovered_items),
    )

    return result


# ---------------------------------------------------------------------------
# Main comparison logic
# ---------------------------------------------------------------------------


def run_comparison(
    registry_path: Path,
    sgsc_dir: Path,
    output_dir: Path,
) -> dict:
    """Run greedy-vs-ILP comparison for all guidelines in the registry.

    Args:
        registry_path: Path to pilot_14_registry.json (or equivalent).
        sgsc_dir: Base directory for sgsc_output per-guideline subdirs.
        output_dir: Directory where the output JSON will be written.

    Returns:
        Standard JSON contract dict (written to output_dir as a side-effect).
    """
    guideline_ids = load_registry(registry_path)
    logger.info("Loaded %d guidelines from registry", len(guideline_ids))

    config = SetCoverConfig()

    # Collect input files for hash
    input_files: list[Path] = [registry_path]
    for gid in guideline_ids:
        cov = sgsc_dir / gid / f"{gid}_coverage.json"
        atoms = sgsc_dir / gid / "atoms_smoke.json"
        input_files.extend([cov, atoms])

    per_guideline: list[dict] = []
    failures: list[dict] = []

    for gid in sorted(guideline_ids):
        entry = _compare_guideline(gid, sgsc_dir, config)
        per_guideline.append(entry)
        if entry["status"] == "error":
            failures.append({"guideline_id": gid, "reason": "solver_error"})

    # Compute aggregate metrics over guidelines that ran successfully
    runnable = [e for e in per_guideline if e["status"] == "ok"]
    guidelines_compared = len(runnable)

    if runnable:
        mean_ratio = sum(e["ratio"] for e in runnable) / len(runnable)
        max_ratio = max(e["ratio"] for e in runnable)
        all_covered_greedy = all(e["greedy_uncovered"] == 0 for e in runnable)
        all_covered_ilp = all(e["ilp_uncovered"] == 0 for e in runnable)
    else:
        mean_ratio = 1.0
        max_ratio = 1.0
        all_covered_greedy = True
        all_covered_ilp = True

    # Status logic
    if not all_covered_ilp:
        status = "fail"
    elif any(e["ratio"] >= RATIO_WARN_THRESHOLD for e in runnable) or not all_covered_greedy:
        status = "warn"
    elif any(e["ratio"] >= RATIO_FAIL_THRESHOLD for e in runnable):
        status = "fail"
    else:
        status = "pass"

    # Build report (output_hash computed after serialising without it)
    report: dict = {
        "check_name": "greedy_vs_ilp_comparison",
        "status": status,
        "commit": _git_commit(),
        "input_hash": _hash_files(input_files),
        "output_hash": "",  # filled below
        "metrics": {
            "guidelines_compared": guidelines_compared,
            "mean_ratio": round(mean_ratio, 4),
            "max_ratio": round(max_ratio, 4),
            "all_covered_greedy": all_covered_greedy,
            "all_covered_ilp": all_covered_ilp,
        },
        "per_guideline": per_guideline,
        "failures": failures,
    }

    # Compute output hash over the body (without the hash field itself)
    body_bytes = json.dumps(report, sort_keys=True).encode()
    report["output_hash"] = _hash_bytes(body_bytes)

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / OUTPUT_FILENAME
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("Report written to %s", output_path)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Compare greedy vs ILP set-cover solvers per guideline",
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY),
        help="Path to guideline registry JSON (default: configs/sgsc/pilot_14_registry.json)",
    )
    parser.add_argument(
        "--sgsc-dir",
        default=str(DEFAULT_SGSC_DIR),
        help="Base directory for sgsc_output per-guideline subdirs",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for output JSON (default: evidence_pack/analysis/)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    registry_path = Path(args.registry)
    sgsc_dir = Path(args.sgsc_dir)
    output_dir = Path(args.output_dir)

    if not registry_path.exists():
        logger.error("Registry not found: %s", registry_path)
        return 1

    if not sgsc_dir.is_dir():
        logger.error("SGSC output directory not found: %s", sgsc_dir)
        return 1

    report = run_comparison(registry_path, sgsc_dir, output_dir)

    m = report["metrics"]
    per_g = report["per_guideline"]

    runnable = [e for e in per_g if e["status"] == "ok"]
    skipped = [e for e in per_g if e["status"] in ("no_data", "no_atoms")]
    errored = [e for e in per_g if e["status"] == "error"]

    print("\n=== Greedy vs ILP Set-Cover Comparison ===")
    print(f"Status:              {report['status'].upper()}")
    print(f"Guidelines compared: {m['guidelines_compared']}")
    print(f"Skipped (no data):   {len(skipped)}")
    print(f"Errors:              {len(errored)}")
    print(f"Mean ratio:          {m['mean_ratio']:.4f}")
    print(f"Max ratio:           {m['max_ratio']:.4f}")
    print(f"All covered (greedy):{m['all_covered_greedy']}")
    print(f"All covered (ILP):   {m['all_covered_ilp']}")
    print()

    if runnable:
        header = f"  {'Guideline':<40} {'Targets':>7} {'Greedy':>7} {'ILP':>5} {'Ratio':>6} {'UncovG':>7} {'UncovI':>7}"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for e in sorted(runnable, key=lambda x: x["guideline_id"]):
            print(
                f"  {e['guideline_id']:<40} {e['targets']:>7} "
                f"{e['greedy_scenarios']:>7} {e['ilp_scenarios']:>5} "
                f"{e['ratio']:>6.3f} {e['greedy_uncovered']:>7} {e['ilp_uncovered']:>7}"
            )

    if skipped:
        print(f"\nSkipped ({len(skipped)}):")
        for e in skipped:
            print(f"  {e['guideline_id']} [{e['status']}]")

    if errored:
        print(f"\nErrors ({len(errored)}):")
        for e in errored:
            print(f"  {e['guideline_id']}")

    output_path = output_dir / OUTPUT_FILENAME
    print(f"\nOutput: {output_path}")

    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
