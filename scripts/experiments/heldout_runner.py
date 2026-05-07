#!/usr/bin/env python3
"""Experiment H: Held-out 5 CPG Full Sweep Runner.

Runs held-out guideline scenarios across all models to test benchmark
generalization beyond the core guidelines used for model selection.

Held-out 5 (pre-registered at commit 8e60cd3e,
docs/cpg_expansion_v7/09_tier_s_preregistration.md §3.2):
  - pals_pediatric_emergency (17, alpha, retained from core-25 heldout)
  - toxicology_management    (17, alpha, retained)
  - apa_agitation_management (15, alpha, retained)
  - aha_acc_aortic_dissection_2022 (19, beta, replaces aba_burn_resuscitation=14)
  - aha_asa_ich_2022               (19, beta, replaces acog_obstetric_hemorrhage=14)

The 2 beta CPGs require: (a) rag_corpus parsed.json, (b) scenarios in
configs/scenarios/auto/, (c) cpg_source_properties.json entry with
annotation_tier=beta. Phase 1c-1d of the Tier S workstream gates these.
Running this script against the new held-out 5 before those artifacts
exist will fail loudly (no scenarios for graph X).

Legacy 5 (pre-2026-04-23): aabb_transfusion, aba_burn_resuscitation,
  acog_obstetric_hemorrhage, apa_agitation_management, pals_pediatric_emergency
  — kept in git history (ef230e81 parent) for reproducibility of the
  v5 heldout run in results/heldout_v1/.

Usage:
  PYTHONPATH=${CGA_BENCH_ROOT} \
    python scripts/experiments/heldout_runner.py oss120b results/heldout_v1 \
    --runs 3

  # Specific guidelines only
  PYTHONPATH=${CGA_BENCH_ROOT} \
    python scripts/experiments/heldout_runner.py qwen35b results/heldout_v1 \
    --guidelines aba,acog --runs 3

  # Shard 1 of 4
  PYTHONPATH=${CGA_BENCH_ROOT} \
    python scripts/experiments/heldout_runner.py oss120b results/heldout_v1 \
    --shard 1/4

  # Dry run
  PYTHONPATH=${CGA_BENCH_ROOT} \
    python scripts/experiments/heldout_runner.py oss120b --dry-run
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Path setup — reuse full_690_runner infrastructure
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT.parent))
sys.path.insert(0, str(_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"/tmp/heldout_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
    ],
)
logger = logging.getLogger(__name__)

# Import infrastructure from full_690_runner
from scripts.experiments.full_690_runner import (
    MODELS,
    apply_shard,
    checkpoint_filename,
    cleanup_stale_claims,
    load_checkpoint,
    release_claim,
    run_single_episode,
    save_checkpoint,
    try_claim,
)

# ---------------------------------------------------------------------------
# Held-out configuration
# ---------------------------------------------------------------------------

# Pre-registered at commit 8e60cd3e per
# docs/cpg_expansion_v7/09_tier_s_preregistration.md §3.2.
# Short keys (2-4 chars) are purely for CLI --guidelines filtering.
HELDOUT_GUIDELINES: dict[str, str] = {
    "pals": "pals_pediatric_emergency",  # 17, alpha (retained)
    "tox": "toxicology_management",  # 17, alpha (retained)
    "apa": "apa_agitation_management",  # 15, alpha (retained)
    "aad": "aha_acc_aortic_dissection_2022",  # 19, beta (replaces aba_burn=14)
    "ich": "aha_asa_ich_2022",  # 19, beta (replaces acog_obstetric=14)
}

# Retained for results/heldout_v1/ reproducibility. Do not use for new runs.
_LEGACY_HELDOUT_GUIDELINES: dict[str, str] = {
    "aba": "aba_burn_resuscitation",
    "acog": "acog_obstetric_hemorrhage",
    "apa": "apa_agitation_management",
    "pals": "pals_pediatric_emergency",
    "tox": "toxicology_management",
}

ALL_HELDOUT_GRAPHS = set(HELDOUT_GUIDELINES.values())

# 8 models from experiment design
HELDOUT_MODELS = [
    "oss120b",
    "qwen35b",
    "qwen27b",
    "qwen4b",
    "qwen397b",
    "gemma31b",
    "nemotron30b",
    "deepseek_r1_7b",
]

RUNS_PER_SCENARIO = int(os.environ.get("HELDOUT_RUNS", "3"))


# ---------------------------------------------------------------------------
# Scenario loading (filtered to held-out guidelines only)
# ---------------------------------------------------------------------------


def load_heldout_scenario_ids(
    guideline_filter: set[str] | None = None,
) -> list[str]:
    """Load scenario IDs whose guideline_graph matches held-out set.

    Args:
        guideline_filter: If set, only include these guideline_graph values.
            Defaults to ALL_HELDOUT_GRAPHS.

    Returns:
        Sorted list of matching scenario IDs.
    """
    target_graphs = guideline_filter or ALL_HELDOUT_GRAPHS

    scenario_dir = _ROOT / "configs" / "scenarios"
    matching: list[str] = []

    for f in sorted(scenario_dir.glob("*.yaml")):
        with open(f) as fh:
            data = yaml.safe_load(fh)
        for sid, s in (data.get("scenarios") or {}).items():
            g = s.get("guideline_graph", "")
            if g in target_graphs:
                matching.append(sid)

    matching.sort()
    logger.info(f"Loaded {len(matching)} held-out scenarios (guidelines: {sorted(target_graphs)})")
    return matching


# ---------------------------------------------------------------------------
# Health check (reuse from full_690_runner if available, else inline)
# ---------------------------------------------------------------------------


def health_check(host: str, port: int, api_key: str = "sk-no-key-required") -> bool:
    """Quick model health check via /v1/models."""
    import urllib.request

    url = f"http://{host}:{port}/v1/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return bool(data.get("data"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Model runner (adapted from full_690_runner.run_model)
# ---------------------------------------------------------------------------


def run_model(
    model_key: str,
    output_dir: Path,
    scenarios: list[str],
    dry_run: bool = False,
    shard_spec: str | None = None,
    host_override: str | None = None,
    port_override: int | None = None,
) -> dict[str, Any]:
    """Run all held-out scenarios for a single model."""
    model_info = MODELS[model_key]
    host = host_override or model_info.get("host", "localhost")
    port = port_override or model_info["port"]

    agent_config_path = Path(model_info["config"])
    agent_yaml = yaml.safe_load(agent_config_path.read_text())["agent"]
    api_key = agent_yaml.get("api_key", "sk-no-key-required")

    scenarios = apply_shard(scenarios, shard_spec)

    shard_label = f" [shard {shard_spec}]" if shard_spec else ""
    logger.info(f"\n{'=' * 60}")
    logger.info(f"HELD-OUT: {model_info['label']} ({model_key}){shard_label}")
    logger.info(f"Endpoint: {host}:{port}")
    logger.info(f"Scenarios: {len(scenarios)}")
    logger.info(f"Runs: {RUNS_PER_SCENARIO}")
    logger.info(f"Total episodes: {len(scenarios) * RUNS_PER_SCENARIO}")
    logger.info(f"{'=' * 60}")

    if not health_check(host, port, api_key=api_key):
        logger.error(f"Model {model_key} not responding on {host}:{port}")
        return {"model": model_key, "status": "offline", "episodes": 0}

    model_dir = output_dir / model_key
    model_dir.mkdir(parents=True, exist_ok=True)

    stale = cleanup_stale_claims(model_dir)
    if stale:
        logger.info(f"Cleaned up {stale} stale claim files")

    cp_name = checkpoint_filename(shard_spec)
    checkpoint_path = model_dir / cp_name
    completed = load_checkpoint(checkpoint_path)
    logger.info(f"Checkpoint ({cp_name}): {len(completed)} episodes already completed")

    if dry_run:
        scenarios = scenarios[:1]
        runs = 1
        logger.info("DRY RUN: 1 scenario x 1 run")
    else:
        runs = RUNS_PER_SCENARIO

    results: list[dict] = []
    failures = 0
    skipped_by_file = 0
    skipped_by_claim = 0
    total = len(scenarios) * runs

    for scenario_id in scenarios:
        for run_idx in range(runs):
            episode_key = f"{scenario_id}_{model_key}_r{run_idx}"

            if episode_key in completed:
                continue

            existing = list(model_dir.glob(f"{scenario_id}_{model_key}_r{run_idx}_*.json"))
            if existing:
                completed.add(episode_key)
                skipped_by_file += 1
                continue

            if not try_claim(model_dir, scenario_id, run_idx):
                completed.add(episode_key)
                skipped_by_claim += 1
                continue

            progress = f"[{len(completed) + len(results) + 1}/{total}]"
            logger.info(f"{progress} {scenario_id} r{run_idx}")

            result = run_single_episode(
                model_key,
                scenario_id,
                run_idx,
                output_dir,
                host_override=host_override,
                port_override=port_override,
            )
            if result is None:
                failures += 1
                import time

                time.sleep(2)
                result = run_single_episode(
                    model_key,
                    scenario_id,
                    run_idx,
                    output_dir,
                    host_override=host_override,
                    port_override=port_override,
                )
                if result is None:
                    failures += 1

            release_claim(model_dir, scenario_id, run_idx)

            if result:
                results.append(result)
                completed.add(episode_key)

            if len(results) % 10 == 0:
                save_checkpoint(checkpoint_path, completed)

    save_checkpoint(checkpoint_path, completed)

    if skipped_by_file or skipped_by_claim:
        logger.info(f"Dedup: skipped {skipped_by_file} (file exists) + {skipped_by_claim} (claimed)")

    summary: dict[str, Any] = {
        "experiment": "heldout_v1",
        "model": model_key,
        "label": model_info["label"],
        "shard": shard_spec,
        "total_episodes": len(results),
        "expected_episodes": total,
        "failures": failures,
        "skipped_file_exists": skipped_by_file,
        "skipped_claimed": skipped_by_claim,
        "status": "ok" if failures / max(total, 1) < 0.1 else "high_failure_rate",
        "timestamp": datetime.now().isoformat(),
    }

    if results:
        scores = [r["compliance_score"] for r in results]
        summary["cga_mean"] = round(sum(scores) / len(scores), 4)

    with open(model_dir / "model_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"\n{model_key}{shard_label} complete: {len(results)} episodes, {failures} failures")
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Experiment H: Held-out 5 CPG Full Sweep")
    parser.add_argument(
        "model_key",
        choices=list(MODELS.keys()),
        help="Model to run",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="results/heldout_v1",
        help="Output directory (default: results/heldout_v1)",
    )
    parser.add_argument(
        "--guidelines",
        default=",".join(HELDOUT_GUIDELINES.keys()),
        help=(f"Comma-separated guideline short names (choices: {','.join(HELDOUT_GUIDELINES.keys())})"),
    )
    parser.add_argument("--runs", type=int, default=3, help="Runs per scenario")
    parser.add_argument("--shard", help="Shard spec (e.g. 1/4)")
    parser.add_argument("--host", help="Override endpoint host")
    parser.add_argument("--port", type=int, help="Override endpoint port")
    parser.add_argument("--dry-run", action="store_true", help="Run 1 scenario x 1 run only")
    return parser.parse_args()


def main() -> None:
    """Entry point for held-out runner."""
    args = parse_args()

    # Override global runs
    global RUNS_PER_SCENARIO
    RUNS_PER_SCENARIO = args.runs

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parse guideline filter
    guideline_keys = [g.strip() for g in args.guidelines.split(",")]
    guideline_graphs: set[str] = set()
    for key in guideline_keys:
        if key in HELDOUT_GUIDELINES:
            guideline_graphs.add(HELDOUT_GUIDELINES[key])
        else:
            logger.warning(f"Unknown guideline key: {key}")

    if not guideline_graphs:
        logger.error("No valid guidelines selected")
        sys.exit(1)

    # Load held-out scenarios
    scenarios = load_heldout_scenario_ids(guideline_graphs)

    if not scenarios:
        logger.error("No scenarios found for selected guidelines")
        sys.exit(1)

    logger.info(f"Held-out Runner: {args.model_key}")
    logger.info(f"Guidelines: {sorted(guideline_graphs)}")
    logger.info(f"Scenarios: {len(scenarios)}")
    logger.info(f"Runs: {RUNS_PER_SCENARIO}")
    logger.info(f"Output: {output_dir}")

    summary = run_model(
        args.model_key,
        output_dir,
        scenarios,
        dry_run=args.dry_run,
        shard_spec=args.shard,
        host_override=args.host,
        port_override=args.port,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
