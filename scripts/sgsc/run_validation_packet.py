#!/usr/bin/env python3
r"""Standalone CLI runner for Gate-7 clinician validation packet generation.

Reads a registry JSON (default: configs/sgsc/pilot_14_registry.json), locates
SGSC output artefacts for each guideline, and calls build_validation_packet +
serialize_packet to produce the review packet.

Outputs:
    {output_dir}/{guideline_id}/packet.json
    {output_dir}/{guideline_id}/clinician_review_form.csv
    evidence_pack/analysis/validation_packet_summary.json  -- standard contract

Usage:
    PYTHONPATH=. python scripts/sgsc/run_validation_packet.py --all
    PYTHONPATH=. python scripts/sgsc/run_validation_packet.py --guideline ssc_sepsis_hour1
    PYTHONPATH=. python scripts/sgsc/run_validation_packet.py --all --dry-run
    PYTHONPATH=. python scripts/sgsc/run_validation_packet.py \
        --all --sgsc-dir sgsc_output/ --output-dir sgsc_output/validation_packet/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]

# Must appear before local imports; noqa comment silences ruff E402
sys.path.insert(0, str(REPO_ROOT))

from sgsc.e2e_harness import E2EHarnessReport  # noqa: E402
from sgsc.validation_packet import (  # noqa: E402
    build_validation_packet,
    serialize_packet,
)

logger = logging.getLogger("run_validation_packet")

_DEFAULT_REGISTRY = REPO_ROOT / "configs" / "sgsc" / "pilot_14_registry.json"
_DEFAULT_SGSC_DIR = REPO_ROOT / "sgsc_output"
_DEFAULT_OUTPUT_DIR = REPO_ROOT / "sgsc_output" / "validation_packet"
_SUMMARY_PATH = REPO_ROOT / "evidence_pack" / "analysis" / "validation_packet_summary.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git_commit() -> str:
    """Return current HEAD SHA or 'unknown'."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=str(REPO_ROOT),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_registry(registry_path: Path) -> list[dict[str, str]]:
    """Load guideline entries from registry JSON.

    Returns a list of dicts each containing at least ``guideline_id``.
    """
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "guidelines" in data:
        return data["guidelines"]
    raise ValueError(f"Unrecognised registry format in {registry_path}")


# ---------------------------------------------------------------------------
# SGSC output path resolution
# ---------------------------------------------------------------------------


def _resolve_harness_report(
    guideline_id: str,
    sgsc_dir: Path,
) -> tuple[E2EHarnessReport | None, list[str]]:
    """Build an E2EHarnessReport from SGSC output files.

    Returns ``(report, missing_paths)``.  When any required file is absent
    ``report`` is ``None`` and ``missing_paths`` lists the absent paths.
    """
    base = sgsc_dir / guideline_id
    required: list[tuple[str, Path]] = [
        ("accepted_atoms_path", base / "atoms_accepted.json"),
        ("constraints_path", base / f"{guideline_id}_constraints.json"),
        ("scenarios_public_path", base / f"{guideline_id}_scenarios_public.json"),
        ("scenarios_private_path", base / f"{guideline_id}_scenarios_private.json"),
    ]

    missing: list[str] = [str(p) for _field, p in required if not p.exists()]
    if missing:
        return None, missing

    # Optional paths — use empty string placeholder when absent
    def _opt(p: Path) -> str:
        return str(p) if p.exists() else ""

    report = E2EHarnessReport(
        proposed_atoms_path=_opt(base / "atoms_proposed.json"),
        accepted_atoms_path=str(required[0][1]),
        rejected_atoms_path=_opt(base / "atoms_rejected.json"),
        review_required_atoms_path=_opt(base / "atoms_review_required.json"),
        constraints_path=str(required[1][1]),
        seeds_path=_opt(base / "seeds_summary.json"),
        scenarios_public_path=str(required[2][1]),
        scenarios_private_path=str(required[3][1]),
        coverage_report_path=_opt(base / "coverage_report.json"),
        leakage_report_path=_opt(base / "leakage_report.json"),
    )
    return report, []


# ---------------------------------------------------------------------------
# Per-guideline logic
# ---------------------------------------------------------------------------


def _process_guideline(
    guideline_id: str,
    sgsc_dir: Path,
    output_dir: Path,
    n_atoms: int,
    n_constraints: int,
    n_scenarios: int,
    n_traces: int,
    dry_run: bool,
) -> dict[str, object]:
    """Process one guideline.  Returns a per-guideline result dict."""
    harness_report, missing = _resolve_harness_report(guideline_id, sgsc_dir)

    if missing:
        logger.warning("[%s] missing files: %s", guideline_id, missing)
        return {
            "guideline_id": guideline_id,
            "status": "skipped",
            "items": 0,
            "reason": f"missing: {', '.join(missing)}",
        }

    if dry_run:
        logger.info("[%s] dry-run: all required paths present", guideline_id)
        return {
            "guideline_id": guideline_id,
            "status": "ok",
            "items": 0,
            "reason": "dry-run",
        }

    try:
        packet = build_validation_packet(
            harness_report,
            n_atoms=n_atoms,
            n_constraints=n_constraints,
            n_scenarios=n_scenarios,
            n_traces=n_traces,
        )
        out = output_dir / guideline_id
        serialize_packet(packet, out)
        n_items = len(packet.items)
        logger.info("[%s] packet written: %d items -> %s", guideline_id, n_items, out)
        return {
            "guideline_id": guideline_id,
            "status": "ok",
            "items": n_items,
            "reason": None,
        }
    except Exception as exc:
        logger.error("[%s] failed: %s", guideline_id, exc)
        return {
            "guideline_id": guideline_id,
            "status": "skipped",
            "items": 0,
            "reason": str(exc),
        }


# ---------------------------------------------------------------------------
# Aggregate stats
# ---------------------------------------------------------------------------


def _per_bucket_counts(
    guideline_id: str,
    output_dir: Path,
) -> dict[str, int]:
    """Read packet.json for a guideline and tally items by type."""
    packet_path = output_dir / guideline_id / "packet.json"
    if not packet_path.exists():
        return {"atom": 0, "constraint": 0, "scenario": 0, "trace": 0}
    try:
        data = json.loads(packet_path.read_text(encoding="utf-8"))
        counts: dict[str, int] = {"atom": 0, "constraint": 0, "scenario": 0, "trace": 0}
        for item in data.get("items", []):
            t = item.get("item_type", "")
            if t in counts:
                counts[t] += 1
        return counts
    except Exception:
        return {"atom": 0, "constraint": 0, "scenario": 0, "trace": 0}


# ---------------------------------------------------------------------------
# Standard JSON contract
# ---------------------------------------------------------------------------


def _build_contract(
    per_guideline: list[dict[str, object]],
    output_dir: Path,
    registry_path: Path,
) -> dict[str, object]:
    """Build the standard JSON output contract."""
    processed = [g for g in per_guideline if g["status"] == "ok"]
    skipped = [g for g in per_guideline if g["status"] == "skipped"]

    total_items = sum(int(g["items"]) for g in per_guideline)

    per_bucket: dict[str, int] = {"atom": 0, "constraint": 0, "scenario": 0, "trace": 0}
    for g in processed:
        gid = str(g["guideline_id"])
        counts = _per_bucket_counts(gid, output_dir)
        for k in per_bucket:
            per_bucket[k] += counts[k]

    status = "pass" if skipped == [] else "warn"

    failures: list[dict[str, object]] = [
        {"guideline_id": g["guideline_id"], "reason": g["reason"]}
        for g in skipped
        if g.get("reason") and g["reason"] != "dry-run"
    ]

    input_hash = _sha256_file(registry_path)

    contract: dict[str, object] = {
        "check_name": "validation_packet_runner",
        "status": status,
        "commit": _git_commit(),
        "input_hash": input_hash,
        "output_hash": "",
        "metrics": {
            "guidelines_processed": len(processed),
            "guidelines_skipped": len(skipped),
            "total_items": total_items,
            "per_bucket": per_bucket,
            "per_guideline": per_guideline,
        },
        "failures": failures,
    }

    stable = {k: v for k, v in contract.items() if k != "output_hash"}
    contract["output_hash"] = _sha256_str(json.dumps(stable, sort_keys=True, ensure_ascii=False))
    return contract


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Build Gate-7 clinician validation packets from SGSC output artefacts.",
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--guideline",
        metavar="GUIDELINE_ID",
        help="Process a single guideline by ID.",
    )
    selection.add_argument(
        "--all",
        action="store_true",
        help="Process all guidelines listed in the registry.",
    )
    parser.add_argument(
        "--registry",
        default=str(_DEFAULT_REGISTRY),
        help="Path to registry JSON (default: configs/sgsc/pilot_14_registry.json).",
    )
    parser.add_argument(
        "--sgsc-dir",
        default=str(_DEFAULT_SGSC_DIR),
        help="Root directory of SGSC output (default: sgsc_output/).",
    )
    parser.add_argument(
        "--n-atoms",
        type=int,
        default=100,
        help="Target atom review items per guideline (default: 100).",
    )
    parser.add_argument(
        "--n-constraints",
        type=int,
        default=100,
        help="Target constraint review items per guideline (default: 100).",
    )
    parser.add_argument(
        "--n-scenarios",
        type=int,
        default=60,
        help="Target scenario review items per guideline (default: 60).",
    )
    parser.add_argument(
        "--n-traces",
        type=int,
        default=60,
        help="Target trace review items per guideline (default: 60).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate paths only; do not build packets.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_DEFAULT_OUTPUT_DIR),
        help="Directory for packet output (default: sgsc_output/validation_packet/).",
    )
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    registry_path = Path(args.registry)
    if not registry_path.exists():
        logger.error("Registry not found: %s", registry_path)
        return 1

    sgsc_dir = Path(args.sgsc_dir)
    output_dir = Path(args.output_dir)

    # Load registry
    try:
        all_entries = _load_registry(registry_path)
    except Exception as exc:
        logger.error("Failed to load registry: %s", exc)
        return 1

    # Select guidelines
    selected_ids = [str(e["guideline_id"]) for e in all_entries] if args.all else [args.guideline]

    logger.info(
        "Processing %d guideline(s) | sgsc_dir=%s | output_dir=%s | dry_run=%s",
        len(selected_ids),
        sgsc_dir,
        output_dir,
        args.dry_run,
    )

    # Process each guideline
    per_guideline: list[dict[str, object]] = []
    for gid in selected_ids:
        result = _process_guideline(
            guideline_id=gid,
            sgsc_dir=sgsc_dir,
            output_dir=output_dir,
            n_atoms=args.n_atoms,
            n_constraints=args.n_constraints,
            n_scenarios=args.n_scenarios,
            n_traces=args.n_traces,
            dry_run=args.dry_run,
        )
        per_guideline.append(result)

    # Build and write standard contract
    contract = _build_contract(per_guideline, output_dir, registry_path)

    _SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SUMMARY_PATH.write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Summary written to %s", _SUMMARY_PATH)

    # Print summary
    m = contract["metrics"]
    processed_count = m["guidelines_processed"]  # type: ignore[index]
    skipped_count = m["guidelines_skipped"]  # type: ignore[index]
    total_items = m["total_items"]  # type: ignore[index]
    per_bucket = m["per_bucket"]  # type: ignore[index]

    print("\n=== Validation Packet Runner ===")
    print(f"Status:    {contract['status'].upper()}")
    print(f"Processed: {processed_count}/{len(selected_ids)}")
    if skipped_count:
        print(f"Skipped:   {skipped_count}")
    print(f"Items:     {total_items} total")
    print(
        f"  atoms={per_bucket['atom']}  constraints={per_bucket['constraint']}"  # type: ignore[index]
        f"  scenarios={per_bucket['scenario']}  traces={per_bucket['trace']}"  # type: ignore[index]
    )

    for g in per_guideline:
        tag = "OK  " if g["status"] == "ok" else "SKIP"
        reason = f"  ({g['reason']})" if g.get("reason") else ""
        print(f"  [{tag}] {g['guideline_id']:40s} {g['items']:4d} items{reason}")

    failures = contract.get("failures", [])
    if failures:
        print("\nFailures:")
        for f in failures:  # type: ignore[union-attr]
            print(f"  {f}")

    return 1 if contract["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
