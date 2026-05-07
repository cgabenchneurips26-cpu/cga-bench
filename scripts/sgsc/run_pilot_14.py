#!/usr/bin/env python3
"""Python orchestrator for SGSC v7 pilot (14 CPG guidelines).

Reads configs/sgsc/pilot_14_registry.json and runs the SGSC pipeline
for each guideline. Supports precomputed atoms, parallel execution,
and aggregate reporting.

Usage:
    PYTHONPATH=. python scripts/sgsc/run_pilot_14.py \
        --endpoint http://localhost:8013/v1

    PYTHONPATH=. python scripts/sgsc/run_pilot_14.py \
        --atoms-dir sgsc_output/precomputed/

    PYTHONPATH=. python scripts/sgsc/run_pilot_14.py --dry-run
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = REPO_ROOT / "configs" / "sgsc" / "pilot_14_registry.json"
OUTPUT_BASE = REPO_ROOT / "sgsc_output"

# Ensure cga_bench and sgsc are importable in both main and worker processes
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

logger = logging.getLogger("sgsc_pilot")


@dataclass
class GuidelineEntry:
    """Single guideline from the registry."""

    guideline_id: str
    guideline_name: str
    corpus_file: str
    graph_file: str
    category: str
    conflict_pattern: str | None
    tier: str | None
    held_out: bool
    domain: str


@dataclass
class RunResult:
    """Result of a single guideline pipeline run."""

    guideline_id: str
    success: bool
    scenario_count: int = 0
    atom_count: int = 0
    hallucination_rate: float = 0.0
    leakage_passed: bool = True
    error: str = ""
    duration_seconds: float = 0.0


@dataclass
class AggregateReport:
    """Aggregate report across all 14 guidelines."""

    total_guidelines: int = 0
    succeeded: int = 0
    failed: int = 0
    total_scenarios: int = 0
    total_atoms: int = 0
    avg_hallucination_rate: float = 0.0
    leakage_all_passed: bool = True
    per_guideline: list[RunResult] = field(default_factory=list)


def load_registry() -> list[GuidelineEntry]:
    """Load and validate the pilot_14_registry.json."""
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Registry not found: {REGISTRY_PATH}")

    data = json.loads(REGISTRY_PATH.read_text())
    entries = []
    for g in data["guidelines"]:
        entries.append(
            GuidelineEntry(
                guideline_id=g["guideline_id"],
                guideline_name=g["guideline_name"],
                corpus_file=g["corpus_file"],
                graph_file=g["graph_file"],
                category=g["category"],
                conflict_pattern=g.get("conflict_pattern"),
                tier=g.get("tier"),
                held_out=g.get("held_out", False),
                domain=g.get("domain", "unknown"),
            )
        )

    if len(entries) != 14:
        raise ValueError(f"Expected 14 guidelines, got {len(entries)}")

    return entries


def validate_paths(
    entries: list[GuidelineEntry],
    atoms_dir: Path | None = None,
) -> list[str]:
    """Validate all corpus/graph/output paths exist. Returns list of errors."""
    errors = []
    for e in entries:
        corpus_path = REPO_ROOT / e.corpus_file
        if not corpus_path.exists():
            errors.append(f"CORPUS MISSING: {e.corpus_file}")

        graph_path = REPO_ROOT / e.graph_file
        if not graph_path.exists():
            errors.append(f"GRAPH MISSING: {e.graph_file}")

        outdir = OUTPUT_BASE / e.guideline_id
        if not outdir.is_dir():
            outdir.mkdir(parents=True, exist_ok=True)
            logger.info("Created output dir: %s", outdir)

        if atoms_dir:
            atoms_path = atoms_dir / f"{e.guideline_id}_atoms.json"
            if not atoms_path.exists():
                logger.warning(
                    "No precomputed atoms for %s at %s",
                    e.guideline_id,
                    atoms_path,
                )

    return errors


def run_single_guideline(
    entry: GuidelineEntry,
    endpoint: str | None,
    model: str,
    atoms_dir: Path | None,
    max_scenarios: int,
    threshold: float,
) -> RunResult:
    """Run the SGSC pipeline for a single guideline."""
    start = time.monotonic()
    try:
        # Lazy import to avoid loading pipeline at module level
        from sgsc.extraction.atom_proposer import AtomProposerConfig
        from sgsc.pipeline import PipelineConfig, run_pipeline
        from sgsc.schemas.atom import RecommendationAtom

        # Load corpus
        corpus_path = REPO_ROOT / entry.corpus_file
        data = json.loads(corpus_path.read_text())

        if isinstance(data, dict):
            recommendations = data.get("recommendations", [])
            full_text = data.get("full_text", "")
            if not full_text and recommendations:
                full_text = " ".join(str(r.get("text", "")) for r in recommendations)
        elif isinstance(data, list):
            recommendations = data
            full_text = " ".join(str(r.get("text", "")) for r in data)
        else:
            recommendations = []
            full_text = str(data)

        # LLM config
        llm_config = None
        if endpoint:
            llm_config = AtomProposerConfig(endpoint=endpoint, model=model, timeout_seconds=600.0)

        # Precomputed atoms
        precomputed = None
        if atoms_dir:
            atoms_path = atoms_dir / f"{entry.guideline_id}_atoms.json"
            if atoms_path.exists():
                atoms_data = json.loads(atoms_path.read_text())
                precomputed = [RecommendationAtom.model_validate(a) for a in atoms_data]
                logger.info(
                    "[%s] Loaded %d precomputed atoms",
                    entry.guideline_id,
                    len(precomputed),
                )

        # Pipeline config
        outdir = OUTPUT_BASE / entry.guideline_id
        config = PipelineConfig(
            guideline_id=entry.guideline_id,
            guideline_name=entry.guideline_name,
            output_dir=str(outdir),
            llm_config=llm_config,
            grounding_threshold=threshold,
            max_scenarios=max_scenarios,
        )

        # Run
        result = run_pipeline(config, full_text, recommendations, precomputed)

        elapsed = time.monotonic() - start
        return RunResult(
            guideline_id=entry.guideline_id,
            success=True,
            scenario_count=len(result.scenarios),
            atom_count=len(result.atoms),
            hallucination_rate=result.hallucination_rate,
            leakage_passed=result.leakage_passed,
            duration_seconds=elapsed,
        )

    except Exception as e:
        elapsed = time.monotonic() - start
        logger.error("[%s] Pipeline failed: %s", entry.guideline_id, e)
        return RunResult(
            guideline_id=entry.guideline_id,
            success=False,
            error=str(e),
            duration_seconds=elapsed,
        )


def run_all(
    entries: list[GuidelineEntry],
    endpoint: str | None,
    model: str,
    atoms_dir: Path | None,
    max_scenarios: int,
    threshold: float,
    parallel: int,
) -> AggregateReport:
    """Run pipeline for all guidelines with optional parallelism."""
    report = AggregateReport(total_guidelines=len(entries))

    if parallel <= 1:
        # Sequential execution
        for entry in entries:
            logger.info("Running: %s", entry.guideline_id)
            result = run_single_guideline(entry, endpoint, model, atoms_dir, max_scenarios, threshold)
            report.per_guideline.append(result)
            if result.success:
                report.succeeded += 1
                logger.info(
                    "  OK: %d scenarios, %d atoms, %.1fs",
                    result.scenario_count,
                    result.atom_count,
                    result.duration_seconds,
                )
            else:
                report.failed += 1
                logger.error("  FAILED: %s", result.error)
    else:
        # Parallel execution
        with ProcessPoolExecutor(max_workers=parallel) as pool:
            futures = {
                pool.submit(
                    run_single_guideline,
                    entry,
                    endpoint,
                    model,
                    atoms_dir,
                    max_scenarios,
                    threshold,
                ): entry.guideline_id
                for entry in entries
            }

            for future in as_completed(futures):
                gid = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = RunResult(guideline_id=gid, success=False, error=str(e))

                report.per_guideline.append(result)
                if result.success:
                    report.succeeded += 1
                    logger.info(
                        "[%s] OK: %d scenarios, %d atoms, %.1fs",
                        gid,
                        result.scenario_count,
                        result.atom_count,
                        result.duration_seconds,
                    )
                else:
                    report.failed += 1
                    logger.error("[%s] FAILED: %s", gid, result.error)

    # Aggregate
    report.total_scenarios = sum(r.scenario_count for r in report.per_guideline)
    report.total_atoms = sum(r.atom_count for r in report.per_guideline)
    succeeded_results = [r for r in report.per_guideline if r.success]
    if succeeded_results:
        report.avg_hallucination_rate = sum(r.hallucination_rate for r in succeeded_results) / len(succeeded_results)
    report.leakage_all_passed = all(r.leakage_passed for r in report.per_guideline if r.success)

    return report


def write_report(report: AggregateReport, output_path: Path) -> None:
    """Write aggregate report as JSON."""
    data = {
        "total_guidelines": report.total_guidelines,
        "succeeded": report.succeeded,
        "failed": report.failed,
        "total_scenarios": report.total_scenarios,
        "total_atoms": report.total_atoms,
        "avg_hallucination_rate": round(report.avg_hallucination_rate, 4),
        "leakage_all_passed": report.leakage_all_passed,
        "expected_episodes_8m3r": report.total_scenarios * 8 * 3,
        "per_guideline": [
            {
                "guideline_id": r.guideline_id,
                "success": r.success,
                "scenario_count": r.scenario_count,
                "atom_count": r.atom_count,
                "hallucination_rate": round(r.hallucination_rate, 4),
                "leakage_passed": r.leakage_passed,
                "error": r.error if r.error else None,
                "duration_seconds": round(r.duration_seconds, 1),
            }
            for r in sorted(report.per_guideline, key=lambda x: x.guideline_id)
        ],
    }
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    logger.info("Report written to %s", output_path)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="SGSC v7 Pilot Runner — 14 CPG guidelines",
    )
    parser.add_argument("--endpoint", default=None, help="vLLM endpoint URL")
    parser.add_argument("--model", default="default", help="Model name")
    parser.add_argument("--atoms-dir", default=None, help="Dir with precomputed atoms (skip LLM)")
    parser.add_argument("--max-scenarios", type=int, default=55, help="Max scenarios/guideline")
    parser.add_argument("--threshold", type=float, default=0.5, help="Grounding threshold")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel workers")
    parser.add_argument("--dry-run", action="store_true", help="Validate paths only")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Load registry
    entries = load_registry()
    logger.info("Loaded %d guidelines from registry", len(entries))

    # Validate paths
    atoms_dir = Path(args.atoms_dir) if args.atoms_dir else None
    errors = validate_paths(entries, atoms_dir)
    if errors:
        for err in errors:
            logger.error(err)
        return 1

    logger.info("All paths validated")

    if args.dry_run:
        print(f"\nDRY RUN: {len(entries)} guidelines ready.")
        print(f"Target scenarios: {len(entries)} x {args.max_scenarios} = ~{len(entries) * args.max_scenarios}")
        for e in entries:
            conflict = f" [{e.conflict_pattern}]" if e.conflict_pattern else ""
            held = " (held-out)" if e.held_out else ""
            print(f"  {e.guideline_id:35s} {e.category:18s}{conflict}{held}")
        return 0

    # Validate endpoint
    if not args.endpoint and not atoms_dir:
        logger.error("--endpoint required (or use --atoms-dir or --dry-run)")
        return 1

    # Run
    report = run_all(
        entries,
        args.endpoint,
        args.model,
        atoms_dir,
        args.max_scenarios,
        args.threshold,
        args.parallel,
    )

    # Print summary
    print("\n=== SGSC v7 Pilot Summary ===")
    print(f"Guidelines: {report.succeeded}/{report.total_guidelines} succeeded")
    print(f"Total scenarios: {report.total_scenarios} (target: ~700)")
    print(f"Total atoms: {report.total_atoms}")
    print(f"Avg hallucination rate: {report.avg_hallucination_rate:.3f}")
    print(f"Leakage all passed: {report.leakage_all_passed}")
    print(f"Expected episodes (8m x 3r): {report.total_scenarios * 8 * 3}")
    print()

    for r in sorted(report.per_guideline, key=lambda x: x.guideline_id):
        status = "OK" if r.success else "FAIL"
        print(
            f"  [{status}] {r.guideline_id:35s} {r.scenario_count:4d} scenarios, "
            f"{r.atom_count:3d} atoms, {r.duration_seconds:.1f}s"
        )
        if r.error:
            print(f"         ERROR: {r.error}")

    # Write report
    report_path = OUTPUT_BASE / "pilot_14_report.json"
    write_report(report, report_path)

    return 1 if report.failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
