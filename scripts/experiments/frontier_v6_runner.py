#!/usr/bin/env python3
"""Frontier API Model Runner for V6 Corpus — 706 scenarios × 4 models × 3 runs.

Reuses frontier_parallel_runner infrastructure but targets the V6 706-scenario
corpus instead of V7.3 SGSC.  This enables AT.3 cross-corpus ρ computation
between frontier models on V6 vs V7.3.

Key differences from frontier_parallel_runner.py:
  - Uses default ScenarioLoader (non-SGSC V6 scenarios)
  - Scenario list filtered to the 706 IDs present in existing V6 open-weight results
  - Output: results/full_v6a_706/{model_key}/
  - 4 models only: claude_opus47, claude_sonnet46, gpt54, gpt54mini (no gemini)

Usage::

    # All 4 frontier models in parallel
    PYTHONPATH=. python scripts/experiments/frontier_v6_runner.py

    # Single model
    PYTHONPATH=. python scripts/experiments/frontier_v6_runner.py --models gpt54

    # Dry run (1 scenario × 1 run per model)
    PYTHONPATH=. python scripts/experiments/frontier_v6_runner.py --dry-run

    # Override workers
    PYTHONPATH=. python scripts/experiments/frontier_v6_runner.py --max-workers 4
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
from datetime import datetime
from pathlib import Path
import sys
import time

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT.parent))
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            f"/tmp/frontier_v6_runner_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        ),
    ],
)
logger = logging.getLogger(__name__)

# Reuse frontier runner infrastructure
from scripts.experiments.frontier_parallel_runner import (  # noqa: E402
    FRONTIER_MODELS,
    _install_signal_handlers,
    run_all_models,
)

# ---------------------------------------------------------------------------
# V6-specific configuration
# ---------------------------------------------------------------------------
DEFAULT_MODELS = ["claude_opus47", "claude_sonnet46", "gpt54", "gpt54mini"]
V6_OUTPUT = _ROOT / "results" / "full_v6a_706"
V6_REF_MODEL = "oss120b"  # Reference model for extracting V6 scenario IDs
RUNS_PER_SCENARIO = 3


def extract_v6_scenario_ids() -> list[str]:
    """Extract scenario IDs from existing V6 open-weight results."""
    ref_dir = V6_OUTPUT / V6_REF_MODEL
    if not ref_dir.exists():
        logger.error(f"Reference model dir not found: {ref_dir}")
        sys.exit(1)

    sids: set[str] = set()
    for jp in glob.glob(str(ref_dir / "*.json")):
        try:
            with open(jp) as f:
                ep = json.load(f)
            sid = ep.get("scenario_id")
            if sid:
                sids.add(sid)
        except Exception:
            continue

    result = sorted(sids)
    logger.info(f"Extracted {len(result)} V6 scenario IDs from {ref_dir}")
    return result


def load_v6_scenario_ids() -> list[str]:
    """Load V6 scenarios using default ScenarioLoader, filtered to 706 IDs."""
    v6_ref_ids = set(extract_v6_scenario_ids())

    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    loader = ScenarioLoader()  # Default: configs/scenarios/ (non-SGSC)
    all_sc = loader.load_all_scenarios()
    all_ids = set(all_sc.keys()) if isinstance(all_sc, dict) else set()

    # Intersect: only scenarios that exist both in loader AND V6 results
    valid = sorted(v6_ref_ids & all_ids)
    missing = v6_ref_ids - all_ids
    if missing:
        logger.warning(
            f"{len(missing)} V6 scenario IDs not found in ScenarioLoader "
            f"(first 3: {sorted(missing)[:3]})"
        )

    logger.info(
        f"V6 scenario set: {len(valid)} (ref={len(v6_ref_ids)}, loader={len(all_ids)})"
    )
    return valid


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Frontier V6 runner — 706 scenarios × 4 models × 3 runs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help=f"Comma-separated model keys (default: {','.join(DEFAULT_MODELS)})",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        metavar="N",
        help="Override per-model worker count",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run 1 scenario × 1 run per model only",
    )
    parser.add_argument(
        "--num-runs",
        type=int,
        default=RUNS_PER_SCENARIO,
        help=f"Runs per scenario (default: {RUNS_PER_SCENARIO})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Pilot mode: limit to first N scenarios",
    )
    parser.add_argument(
        "--no-load-env",
        action="store_true",
        help="Skip loading secrets/frontier_api_keys.env",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()

    # Load frontier API keys
    if not args.no_load_env:
        from cga_bench.agent_runner.frontier_env_loader import load_frontier_env

        try:
            loaded = load_frontier_env()
            logger.info(f"Loaded {len(loaded)} key(s) from frontier_api_keys.env")
        except (FileNotFoundError, PermissionError) as exc:
            logger.error(str(exc))
            sys.exit(1)

    _install_signal_handlers()

    # Parse model list
    model_keys = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [m for m in model_keys if m not in FRONTIER_MODELS]
    if unknown:
        logger.error(
            f"Unknown model(s): {unknown}. Available: {list(FRONTIER_MODELS.keys())}"
        )
        sys.exit(1)

    # Load V6 scenarios
    scenarios = load_v6_scenario_ids()
    if not scenarios:
        logger.error("No V6 scenarios found.")
        sys.exit(1)

    if args.limit is not None and args.limit > 0:
        scenarios = scenarios[: args.limit]
        logger.info(f"PILOT MODE: limited to {len(scenarios)} scenarios")

    # Output to V6 results directory
    output_dir = V6_OUTPUT
    output_dir.mkdir(parents=True, exist_ok=True)

    # V6 scenarios use default ScenarioLoader (NOT SGSC dir)
    # Pass sgsc_dir=None → frontier_parallel_runner will use SGSC_DIR,
    # but we override by passing the scenarios list directly.
    # The ScenarioLoader in run_single_episode_frontier needs to find
    # V6 scenarios, so we pass the parent configs/scenarios/ dir.
    scenarios_dir = _ROOT / "configs" / "scenarios"

    logger.info("=" * 60)
    logger.info("Frontier V6 Runner")
    logger.info(f"Models: {model_keys}")
    logger.info(f"Scenarios: {len(scenarios)}")
    logger.info(f"Runs per scenario: {args.num_runs}")
    logger.info(f"Total episodes per model: {len(scenarios) * args.num_runs}")
    logger.info(f"Output: {output_dir}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 60)

    start_time = time.monotonic()

    summaries = run_all_models(
        model_keys=model_keys,
        output_dir=output_dir,
        scenarios=scenarios,
        num_runs=args.num_runs,
        dry_run=args.dry_run,
        max_workers_override=args.max_workers,
        sgsc_dir=scenarios_dir,
    )

    elapsed = time.monotonic() - start_time

    combined = {
        "run_timestamp": datetime.now().isoformat(),
        "models": model_keys,
        "corpus": "v6_706",
        "n_scenarios": len(scenarios),
        "num_runs": args.num_runs,
        "dry_run": args.dry_run,
        "elapsed_seconds": round(elapsed, 1),
        "per_model": summaries,
    }
    summary_path = (
        output_dir
        / f"frontier_v6_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(summary_path, "w") as fout:
        json.dump(combined, fout, indent=2, default=str)

    logger.info(f"\n{'=' * 60}")
    logger.info(f"All models complete in {elapsed:.0f}s")
    logger.info(f"Summary: {summary_path}")
    logger.info(f"{'=' * 60}")

    print(json.dumps(combined, indent=2, default=str))


if __name__ == "__main__":
    main()
