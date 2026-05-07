#!/usr/bin/env python3
r"""Python orchestrator for SGSC v7 full expansion (25 CPG guidelines).

Reads configs/sgsc/full_25_registry.json and runs the SGSC pipeline
for each guideline. Extends run_pilot_14.py with:
  - --skip-existing: skip guidelines that already have output
  - 4 no-go criteria checks after the run
  - Standard JSON output contract (check_name, status, commit, hashes, metrics)
  - Manifest + LaTeX macro update after run

Usage:
    PYTHONPATH=. python scripts/sgsc/run_full_25.py \
        --endpoint http://localhost:8013/v1

    PYTHONPATH=. python scripts/sgsc/run_full_25.py \
        --atoms-dir sgsc_output/precomputed/

    PYTHONPATH=. python scripts/sgsc/run_full_25.py --dry-run

    PYTHONPATH=. python scripts/sgsc/run_full_25.py \
        --endpoint http://localhost:8013/v1 --skip-existing
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = REPO_ROOT / "configs" / "sgsc" / "full_25_registry.json"
OUTPUT_BASE = REPO_ROOT / "sgsc_output"
REPORT_PATH = OUTPUT_BASE / "full_25_report.json"
MANIFEST_PATH = OUTPUT_BASE / "sgsc_manifest_v1.json"
LATEX_PATH = REPO_ROOT / "paper" / "auto_numbers_sgsc.tex"

EXPECTED_GUIDELINE_COUNT = 25

# Models x runs constant for expected episode calculation
MODELS_COUNT = 8
RUNS_COUNT = 3

# Ensure cga_bench and sgsc are importable in both main and worker processes
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

logger = logging.getLogger("sgsc_full_25")


# ---------------------------------------------------------------------------
# Data classes (same shape as run_pilot_14.py)
# ---------------------------------------------------------------------------


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
    skipped: bool = False
    scenario_count: int = 0
    atom_count: int = 0
    hallucination_rate: float = 0.0
    leakage_passed: bool = True
    error: str = ""
    duration_seconds: float = 0.0


@dataclass
class AggregateReport:
    """Aggregate report across all 25 guidelines."""

    total_guidelines: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    total_scenarios: int = 0
    total_atoms: int = 0
    avg_hallucination_rate: float = 0.0
    leakage_all_passed: bool = True
    per_guideline: list[RunResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------


def load_registry() -> list[GuidelineEntry]:
    """Load and validate full_25_registry.json."""
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

    if len(entries) != EXPECTED_GUIDELINE_COUNT:
        raise ValueError(f"Expected {EXPECTED_GUIDELINE_COUNT} guidelines, got {len(entries)}")

    return entries


# ---------------------------------------------------------------------------
# Path validation (same logic as run_pilot_14.py)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Skip-existing check
# ---------------------------------------------------------------------------


def is_already_done(guideline_id: str) -> bool:
    """Return True if scenarios output file already exists for this guideline."""
    scenarios_path = OUTPUT_BASE / guideline_id / f"{guideline_id}_scenarios.json"
    return scenarios_path.exists()


# ---------------------------------------------------------------------------
# Single-guideline runner (same logic as run_pilot_14.py)
# ---------------------------------------------------------------------------


def run_single_guideline(
    entry: GuidelineEntry,
    endpoint: str | None,
    model: str,
    atoms_dir: Path | None,
    max_scenarios: int,
    threshold: float,
    enable_multi_pass: bool = False,
    corpus_context_chars: int = 0,
    output_base: Path | None = None,
    top_p: float = 1.0,
    deterministic: bool = False,
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
            llm_config = AtomProposerConfig(
                endpoint=endpoint,
                model=model,
                timeout_seconds=600.0,
                enable_multi_pass=enable_multi_pass,
                corpus_context_chars=corpus_context_chars,
                top_p=top_p,
                deterministic=deterministic,
            )

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
        _base = output_base if output_base else OUTPUT_BASE
        outdir = _base / entry.guideline_id
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


# ---------------------------------------------------------------------------
# Aggregate runner
# ---------------------------------------------------------------------------


def run_all(
    entries: list[GuidelineEntry],
    endpoint: str | None,
    model: str,
    atoms_dir: Path | None,
    max_scenarios: int,
    threshold: float,
    parallel: int,
    skip_existing: bool,
    enable_multi_pass: bool = False,
    corpus_context_chars: int = 0,
    output_base: Path | None = None,
    top_p: float = 1.0,
    deterministic: bool = False,
) -> AggregateReport:
    """Run pipeline for all guidelines with optional parallelism and skip logic."""
    report = AggregateReport(total_guidelines=len(entries))

    # Separate entries into skip vs run
    to_run: list[GuidelineEntry] = []
    for entry in entries:
        if skip_existing and is_already_done(entry.guideline_id):
            logger.info(
                "[%s] skipping, already exists",
                entry.guideline_id,
            )
            skipped = RunResult(
                guideline_id=entry.guideline_id,
                success=True,
                skipped=True,
            )
            # Load existing counts from scenarios file
            try:
                scenarios_path = OUTPUT_BASE / entry.guideline_id / f"{entry.guideline_id}_scenarios.json"
                existing = json.loads(scenarios_path.read_text())
                skipped.scenario_count = len(existing)
            except Exception:
                pass
            report.per_guideline.append(skipped)
            report.succeeded += 1
            report.skipped += 1
        else:
            to_run.append(entry)

    if parallel <= 1:
        for entry in to_run:
            logger.info("Running: %s", entry.guideline_id)
            result = run_single_guideline(
                entry, endpoint, model, atoms_dir, max_scenarios, threshold,
                enable_multi_pass, corpus_context_chars, output_base,
                top_p, deterministic,
            )
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
                    enable_multi_pass,
                    corpus_context_chars,
                    output_base,
                    top_p,
                    deterministic,
                ): entry.guideline_id
                for entry in to_run
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
    succeeded_with_atoms = [r for r in report.per_guideline if r.success and not r.skipped]
    if succeeded_with_atoms:
        report.avg_hallucination_rate = sum(r.hallucination_rate for r in succeeded_with_atoms) / len(
            succeeded_with_atoms
        )
    report.leakage_all_passed = all(r.leakage_passed for r in report.per_guideline if r.success)

    return report


# ---------------------------------------------------------------------------
# No-go criteria checks
# ---------------------------------------------------------------------------


def _load_guideline_output(guideline_id: str) -> dict:
    """Load the pipeline output summary for a guideline if it exists."""
    outdir = OUTPUT_BASE / guideline_id
    # Try the main scenarios file and any summary/report file
    for candidate in [
        outdir / f"{guideline_id}_report.json",
        outdir / f"{guideline_id}_summary.json",
        outdir / "pipeline_report.json",
    ]:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text())
            except (json.JSONDecodeError, OSError):
                pass
    return {}


def check_no_go_criteria(
    report: AggregateReport,
) -> tuple[bool, list[str]]:
    """Run 4 no-go checks. Returns (all_passed, list_of_failure_messages).

    No-go criteria:
    1. Any guideline has uncovered hard constraint targets
       (WITHIN/FORBID/BEFORE with uncovered > 0).
    2. Public/private scenario count mismatch for any guideline.
    3. Field entailment not checked for any accepted atom
       (atoms exist but no entailment report).
    4. Runtime leakage canary hit > 0.
    """
    failures: list[str] = []

    for result in report.per_guideline:
        gid = result.guideline_id
        outdir = OUTPUT_BASE / gid
        output = _load_guideline_output(gid)

        # No-go 1: uncovered hard constraint targets
        coverage = output.get("coverage", {})
        for ctype in ("WITHIN", "FORBID", "BEFORE"):
            uncovered = coverage.get(f"{ctype}_uncovered", 0)
            if uncovered > 0:
                failures.append(f"NO-GO-1: [{gid}] {ctype} has {uncovered} uncovered hard constraint target(s)")

        # No-go 2: public/private count mismatch
        pub_file = outdir / f"{gid}_scenarios_public.json"
        priv_file = outdir / f"{gid}_scenarios_private.json"
        if pub_file.exists() and priv_file.exists():
            try:
                pub_data = json.loads(pub_file.read_text())
                priv_data = json.loads(priv_file.read_text())
                pub_count = len(pub_data) if isinstance(pub_data, (list, dict)) else 0
                priv_count = len(priv_data) if isinstance(priv_data, (list, dict)) else 0
                if pub_count != priv_count:
                    failures.append(
                        f"NO-GO-2: [{gid}] public scenario count ({pub_count}) != private scenario count ({priv_count})"
                    )
            except (json.JSONDecodeError, OSError) as e:
                failures.append(f"NO-GO-2: [{gid}] could not read scenario files: {e}")

        # No-go 3: entailment not checked for accepted atoms
        atoms_file = outdir / "atoms_smoke.json"
        entailment_file = outdir / f"{gid}_entailment_report.json"
        if atoms_file.exists() and not entailment_file.exists():
            try:
                atoms_data = json.loads(atoms_file.read_text())
                if isinstance(atoms_data, list) and len(atoms_data) > 0:
                    failures.append(f"NO-GO-3: [{gid}] {len(atoms_data)} atom(s) exist but no entailment report found")
            except (json.JSONDecodeError, OSError):
                pass

        # No-go 4: runtime leakage canary hit
        leakage_hits = output.get("leakage_canary_hits", 0)
        if leakage_hits > 0:
            failures.append(f"NO-GO-4: [{gid}] runtime leakage canary hit {leakage_hits} time(s)")
        # Also check the RunResult leakage flag
        if result.success and not result.leakage_passed:
            failures.append(f"NO-GO-4: [{gid}] leakage_passed=False reported by pipeline")

    return (len(failures) == 0, failures)


# ---------------------------------------------------------------------------
# Git + hash helpers
# ---------------------------------------------------------------------------


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Standard JSON output contract
# ---------------------------------------------------------------------------


def build_output_contract(
    report: AggregateReport,
    no_go_passed: bool,
    no_go_failures: list[str],
) -> dict:
    """Build the standard JSON output contract."""
    registry_hash = _sha256_file(REGISTRY_PATH) if REGISTRY_PATH.exists() else "missing"

    per_guideline_list = [
        {
            "guideline_id": r.guideline_id,
            "success": r.success,
            "skipped": r.skipped,
            "scenario_count": r.scenario_count,
            "atom_count": r.atom_count,
            "hallucination_rate": round(r.hallucination_rate, 4),
            "leakage_passed": r.leakage_passed,
            "error": r.error if r.error else None,
            "duration_seconds": round(r.duration_seconds, 1),
        }
        for r in sorted(report.per_guideline, key=lambda x: x.guideline_id)
    ]

    total_scenarios = report.total_scenarios
    expected_episodes = total_scenarios * MODELS_COUNT * RUNS_COUNT

    # Determine overall status
    if report.failed > 0 or not no_go_passed:
        status = "fail"
    elif report.skipped > 0 or not report.leakage_all_passed:
        status = "warn"
    else:
        status = "pass"

    failures: list[dict] = []
    for result in report.per_guideline:
        if not result.success:
            failures.append({"guideline_id": result.guideline_id, "error": result.error})
    for msg in no_go_failures:
        failures.append({"no_go": msg})

    contract: dict = {
        "check_name": "full_25_expansion",
        "status": status,
        "commit": _git_commit(),
        "input_hash": registry_hash,
        "output_hash": "",  # filled below
        "metrics": {
            "total_guidelines": report.total_guidelines,
            "succeeded": report.succeeded,
            "failed": report.failed,
            "skipped": report.skipped,
            "total_scenarios": total_scenarios,
            "total_atoms": report.total_atoms,
            "expected_episodes": expected_episodes,
            "avg_hallucination_rate": round(report.avg_hallucination_rate, 4),
            "leakage_all_passed": report.leakage_all_passed,
            "no_go_passed": no_go_passed,
        },
        "failures": failures,
        "per_guideline": per_guideline_list,
    }

    # Compute output_hash over a stable subset (exclude output_hash itself)
    stable = {k: v for k, v in contract.items() if k != "output_hash"}
    contract["output_hash"] = _sha256_str(json.dumps(stable, sort_keys=True, ensure_ascii=False))

    return contract


# ---------------------------------------------------------------------------
# Manifest + LaTeX update
# ---------------------------------------------------------------------------


def update_manifest_and_latex(report: AggregateReport) -> None:
    """Invoke build_manifest_tables logic inline to update manifest and LaTeX."""
    try:
        from scripts.sgsc.build_manifest_tables import run_build
    except ImportError:
        # Fall back to subprocess
        try:
            subprocess.check_call(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "sgsc" / "build_manifest_tables.py"),
                    "--models",
                    str(MODELS_COUNT),
                    "--runs",
                    str(RUNS_COUNT),
                    "--manifest-output",
                    str(MANIFEST_PATH),
                    "--latex-output",
                    str(LATEX_PATH),
                ],
                cwd=str(REPO_ROOT),
            )
            logger.info("Manifest and LaTeX updated via build_manifest_tables.py")
        except subprocess.CalledProcessError as e:
            logger.warning("build_manifest_tables.py returned non-zero: %s", e)
        except FileNotFoundError as e:
            logger.warning("Could not run build_manifest_tables.py: %s", e)
        return

    sgsc_dir = OUTPUT_BASE
    manifest_dict, _build_report, latex = run_build(sgsc_dir, MODELS_COUNT, RUNS_COUNT, None)

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest_dict, indent=2, ensure_ascii=False))
    logger.info("Manifest written to %s", MANIFEST_PATH)

    LATEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEX_PATH.write_text(latex)
    logger.info("LaTeX macros written to %s", LATEX_PATH)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="SGSC v7 Full Expansion Runner — 25 CPG guidelines",
    )
    parser.add_argument("--endpoint", default=None, help="vLLM endpoint URL")
    parser.add_argument("--model", default="default", help="Model name")
    parser.add_argument("--atoms-dir", default=None, help="Dir with precomputed atoms (skip LLM)")
    parser.add_argument(
        "--max-scenarios",
        type=int,
        default=55,
        help="Max scenarios per guideline",
    )
    parser.add_argument("--threshold", type=float, default=0.5, help="Grounding threshold")
    parser.add_argument("--parallel", type=int, default=1, help="Parallel workers")
    parser.add_argument("--dry-run", action="store_true", help="Validate paths only")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip guidelines whose output already exists in sgsc_output/{id}/",
    )
    parser.add_argument("--multi-pass", action="store_true", help="Enable E3-b 3-pass extraction")
    parser.add_argument("--corpus-chars", type=int, default=0, help="E3-c corpus context chars (0=disabled)")
    parser.add_argument("--output-dir", default=None, help="Override output base directory")
    parser.add_argument("--guidelines", default=None, help="Comma-separated guideline IDs to run (default: all)")
    parser.add_argument("--deterministic", action="store_true", help="Enable vLLM seed for bit-exact reproducibility")
    parser.add_argument("--top-p", type=float, default=1.0, help="Sampling top_p (default 1.0)")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Load registry
    entries = load_registry()
    logger.info("Loaded %d guidelines from registry: %s", len(entries), REGISTRY_PATH)

    # Validate paths
    atoms_dir = Path(args.atoms_dir) if args.atoms_dir else None
    errors = validate_paths(entries, atoms_dir)
    if errors:
        for err in errors:
            logger.error(err)
        return 1

    logger.info("All paths validated")

    if args.dry_run:
        already_done = [e for e in entries if is_already_done(e.guideline_id)]
        print(f"\nDRY RUN: {len(entries)} guidelines ready.")
        print(f"Target scenarios: {len(entries)} x {args.max_scenarios} = ~{len(entries) * args.max_scenarios}")
        if args.skip_existing and already_done:
            print(f"Would skip {len(already_done)} already-complete guidelines.")
        print()
        for e in entries:
            conflict = f" [{e.conflict_pattern}]" if e.conflict_pattern else ""
            held = " (held-out)" if e.held_out else ""
            done = " [DONE]" if is_already_done(e.guideline_id) else ""
            print(f"  {e.guideline_id:40s} {e.category:18s}{conflict}{held}{done}")
        return 0

    # Validate endpoint
    if not args.endpoint and not atoms_dir:
        logger.error("--endpoint required (or use --atoms-dir or --dry-run)")
        return 1

    # Filter guidelines if requested
    if args.guidelines:
        allowed = {g.strip() for g in args.guidelines.split(",")}
        entries = [e for e in entries if e.guideline_id in allowed]
        if not entries:
            logger.error("No matching guidelines for: %s", args.guidelines)
            return 1
        logger.info("Filtered to %d guidelines: %s", len(entries), [e.guideline_id for e in entries])

    # Output base override
    output_base = Path(args.output_dir) if args.output_dir else None
    if output_base:
        output_base.mkdir(parents=True, exist_ok=True)

    # Run all guidelines
    report = run_all(
        entries,
        args.endpoint,
        args.model,
        atoms_dir,
        args.max_scenarios,
        args.threshold,
        args.parallel,
        args.skip_existing,
        args.multi_pass,
        args.corpus_chars,
        output_base,
        args.top_p,
        args.deterministic,
    )

    # No-go criteria checks
    no_go_passed, no_go_failures = check_no_go_criteria(report)
    if no_go_passed:
        logger.info("All 4 no-go criteria passed")
    else:
        for msg in no_go_failures:
            logger.error("NO-GO FAIL: %s", msg)

    # Build and write standard JSON output contract
    contract = build_output_contract(report, no_go_passed, no_go_failures)
    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(contract, indent=2, ensure_ascii=False))
    logger.info("Report written to %s", REPORT_PATH)

    # Update manifest + LaTeX macros
    update_manifest_and_latex(report)

    # Print summary
    m = contract["metrics"]
    print("\n=== SGSC v7 Full Expansion Summary ===")
    print(f"Status:           {contract['status'].upper()}")
    print(f"Guidelines:       {m['succeeded']}/{m['total_guidelines']} succeeded")
    if m["skipped"] > 0:
        print(f"Skipped:          {m['skipped']} (--skip-existing)")
    print(f"Total scenarios:  {m['total_scenarios']}")
    print(f"Total atoms:      {m['total_atoms']}")
    print(f"Avg hallucination:{m['avg_hallucination_rate']:.3f}")
    print(f"Leakage passed:   {m['leakage_all_passed']}")
    print(f"No-go passed:     {m['no_go_passed']}")
    print(f"Expected episodes:{m['expected_episodes']}  ({MODELS_COUNT}m x {m['total_scenarios']}s x {RUNS_COUNT}r)")
    print(f"Commit:           {contract['commit'][:12]}")
    print()

    for r in sorted(report.per_guideline, key=lambda x: x.guideline_id):
        if r.skipped:
            tag = "SKIP"
        elif r.success:
            tag = "OK"
        else:
            tag = "FAIL"
        print(
            f"  [{tag:4s}] {r.guideline_id:40s} "
            f"{r.scenario_count:4d} scenarios, "
            f"{r.atom_count:3d} atoms, "
            f"{r.duration_seconds:.1f}s"
        )
        if r.error:
            print(f"         ERROR: {r.error}")

    if no_go_failures:
        print("\nNo-go failures:")
        for msg in no_go_failures:
            print(f"  {msg}")

    return 1 if (report.failed > 0 or not no_go_passed) else 0


if __name__ == "__main__":
    sys.exit(main())
