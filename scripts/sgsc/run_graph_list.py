#!/usr/bin/env python3
"""SGSC v7.2 expansion runner — accepts arbitrary graph list.

Adapted from ``run_full_25.py``. Reads a JSON file produced by
Track-C C-1 (``data/tier_s_expansion_list.json``) which lists
expansion graphs together with their corpus_file and graph_file
paths.

Usage:
    PYTHONPATH=. python scripts/sgsc/run_graph_list.py \\
        --graph-list data/tier_s_expansion_list.json \\
        --endpoint http://localhost:8013/v1 \\
        --threshold 0.6 \\
        --deterministic --base-seed 42 --top-p 1.0 \\
        --parallel 4 \\
        --output-dir sgsc_output/v7_2_atoms_expansion/

    PYTHONPATH=. python scripts/sgsc/run_graph_list.py \\
        --graph-list data/tier_s_expansion_list.json --dry-run
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

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

logger = logging.getLogger("sgsc_graph_list")


@dataclass
class GraphEntry:
    graph_id: str
    graph_file: str
    corpus_file: str
    tier: str
    total: int
    corpus_kind: str  # "real" or "synthetic"


@dataclass
class RunResult:
    graph_id: str
    success: bool
    scenario_count: int = 0
    atom_count: int = 0
    hallucination_rate: float = 0.0
    leakage_passed: bool = True
    error: str = ""
    duration_seconds: float = 0.0


def load_graph_list(path: Path) -> list[GraphEntry]:
    """Load expansion list from C-1 output JSON."""
    if not path.exists():
        raise FileNotFoundError(f"Graph list not found: {path}")
    data = json.loads(path.read_text())
    entries: list[GraphEntry] = []
    for g in data.get("expansion_25", []):
        entries.append(
            GraphEntry(
                graph_id=g["graph_id"],
                graph_file=g["graph_file"],
                corpus_file=g["corpus_file"],
                tier=g.get("tier", ""),
                total=g.get("total", 0),
                corpus_kind=g.get("corpus_kind", "real"),
            )
        )
    if not entries:
        raise ValueError(f"No expansion graphs found in {path}")
    return entries


def validate_paths(entries: list[GraphEntry]) -> list[str]:
    errors: list[str] = []
    for e in entries:
        cp = REPO_ROOT / e.corpus_file
        gp = REPO_ROOT / e.graph_file
        if not cp.exists():
            errors.append(f"CORPUS MISSING: [{e.graph_id}] {e.corpus_file}")
        if not gp.exists():
            errors.append(f"GRAPH MISSING:  [{e.graph_id}] {e.graph_file}")
    return errors


def is_already_done(graph_id: str, output_base: Path) -> bool:
    return (output_base / graph_id / f"{graph_id}_scenarios.json").exists()


def run_single_graph(
    entry: GraphEntry,
    endpoint: str | None,
    model: str,
    max_scenarios: int,
    threshold: float,
    output_base: Path,
    top_p: float,
    deterministic: bool,
    base_seed: int,
) -> RunResult:
    start = time.monotonic()
    try:
        from sgsc.extraction.atom_proposer import AtomProposerConfig
        from sgsc.pipeline import PipelineConfig, run_pipeline

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

        llm_config = None
        if endpoint:
            llm_config = AtomProposerConfig(
                endpoint=endpoint,
                model=model,
                timeout_seconds=600.0,
                top_p=top_p,
                deterministic=deterministic,
                base_seed=base_seed,
            )

        outdir = output_base / entry.graph_id
        config = PipelineConfig(
            guideline_id=entry.graph_id,
            guideline_name=entry.graph_id,
            output_dir=str(outdir),
            llm_config=llm_config,
            grounding_threshold=threshold,
            max_scenarios=max_scenarios,
        )

        result = run_pipeline(config, full_text, recommendations, None)

        return RunResult(
            graph_id=entry.graph_id,
            success=True,
            scenario_count=len(result.scenarios),
            atom_count=len(result.atoms),
            hallucination_rate=result.hallucination_rate,
            leakage_passed=result.leakage_passed,
            duration_seconds=time.monotonic() - start,
        )
    except Exception as e:
        return RunResult(
            graph_id=entry.graph_id,
            success=False,
            error=f"{type(e).__name__}: {e}",
            duration_seconds=time.monotonic() - start,
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SGSC v7.2 expansion runner")
    p.add_argument("--graph-list", type=Path, required=True,
                   help="JSON list with expansion_25 entries (from Track-C C-1)")
    p.add_argument("--endpoint", default=None)
    # NOTE: vLLM rejects model="default" with HTTP 404. The default below
    # matches the active endpoint per .claude/rules/vllm-launch.md. Override
    # with --model when the loaded model changes.
    p.add_argument("--model", default="Qwen/Qwen3.5-397B-A17B-FP8")
    p.add_argument("--threshold", type=float, default=0.6)
    p.add_argument("--max-scenarios", type=int, default=55)
    p.add_argument("--parallel", type=int, default=1)
    p.add_argument("--output-dir", type=Path,
                   default=REPO_ROOT / "sgsc_output" / "v7_2_atoms_expansion")
    p.add_argument("--deterministic", action="store_true")
    p.add_argument("--base-seed", type=int, default=42)
    p.add_argument("--top-p", type=float, default=1.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--skip-existing", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    entries = load_graph_list(args.graph_list)
    logger.info("Loaded %d graphs from %s", len(entries), args.graph_list)

    errors = validate_paths(entries)
    if errors:
        for err in errors:
            logger.error(err)
        return 1
    logger.info("All paths validated")

    if args.dry_run:
        print(f"\nDRY RUN: {len(entries)} graphs ready.")
        for e in entries:
            done = " [DONE]" if is_already_done(e.graph_id, args.output_dir) else ""
            print(f"  {e.graph_id:50s} tier={e.tier} total={e.total:2d} corpus={e.corpus_kind}{done}")
        return 0

    if not args.endpoint:
        logger.error("--endpoint required (or --dry-run)")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    to_run = [e for e in entries
              if not (args.skip_existing and is_already_done(e.graph_id, args.output_dir))]
    skipped = len(entries) - len(to_run)
    logger.info("Running %d / skipping %d", len(to_run), skipped)

    results: list[RunResult] = []
    if args.parallel <= 1:
        for entry in to_run:
            logger.info("Running: %s", entry.graph_id)
            r = run_single_graph(
                entry, args.endpoint, args.model, args.max_scenarios,
                args.threshold, args.output_dir, args.top_p,
                args.deterministic, args.base_seed,
            )
            results.append(r)
            if r.success:
                logger.info("[%s] OK: %d scenarios, %d atoms, %.1fs",
                            r.graph_id, r.scenario_count, r.atom_count, r.duration_seconds)
            else:
                logger.error("[%s] FAILED: %s", r.graph_id, r.error)
    else:
        with ProcessPoolExecutor(max_workers=args.parallel) as pool:
            futures = {
                pool.submit(
                    run_single_graph,
                    entry, args.endpoint, args.model, args.max_scenarios,
                    args.threshold, args.output_dir, args.top_p,
                    args.deterministic, args.base_seed,
                ): entry.graph_id
                for entry in to_run
            }
            for fut in as_completed(futures):
                gid = futures[fut]
                try:
                    r = fut.result()
                except Exception as e:
                    r = RunResult(graph_id=gid, success=False, error=str(e))
                results.append(r)
                if r.success:
                    logger.info("[%s] OK: %d scenarios, %d atoms, %.1fs",
                                gid, r.scenario_count, r.atom_count, r.duration_seconds)
                else:
                    logger.error("[%s] FAILED: %s", gid, r.error)

    succeeded = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    total_atoms = sum(r.atom_count for r in succeeded)
    total_scenarios = sum(r.scenario_count for r in succeeded)
    avg_halluc = (sum(r.hallucination_rate for r in succeeded) / len(succeeded)) if succeeded else 0.0

    print("\n=== SGSC v7.2 Graph-List Expansion Summary ===")
    print(f"Graphs:           {len(succeeded)}/{len(to_run)} succeeded")
    print(f"Total scenarios:  {total_scenarios}")
    print(f"Total atoms:      {total_atoms}")
    print(f"Avg hallucination:{avg_halluc:.4f}")
    print(f"Output base:      {args.output_dir}")

    for r in sorted(results, key=lambda x: x.graph_id):
        tag = "OK" if r.success else "FAIL"
        print(f"  [{tag:4s}] {r.graph_id:50s} {r.scenario_count:3d} sc, {r.atom_count:3d} atoms, {r.duration_seconds:5.1f}s")
        if r.error:
            print(f"           ERROR: {r.error}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
