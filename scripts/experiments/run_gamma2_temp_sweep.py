#!/usr/bin/env python3
"""γ-2 Temperature Sensitivity Sweep on Held-out Episodes.

Wraps heldout_runner.run_model with monkeypatched MODELS so the 8
temp-variant agent configs (qwen397b/gemma31b × {0.0, 0.3, 0.7, 1.0})
can be invoked without editing full_690_runner's MODELS dict.

Endpoint distribution (multi-endpoint parallelism):
  - Qwen397B variants -> 144:30001 (single endpoint, sequential T)
  - Gemma31B variants -> 145:30210 + 145:30211 (two endpoints, even-T split)

Output: results/gamma2_temp_sweep/{model_key}/

Usage:
    PYTHONPATH=${REPO}:${REPO}/cga_bench .venv311/bin/python \
      scripts/experiments/run_gamma2_temp_sweep.py \
        --family gemma31b              # only Gemma sweep (parallel-safe with γ-1)
        --temps 0.0,0.3,0.7,1.0
        --runs 3

    # After γ-1 completes:
    .venv311/bin/python scripts/experiments/run_gamma2_temp_sweep.py \
        --family qwen397b --temps 0.0,0.3,0.7,1.0 --runs 3
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO.parent))
sys.path.insert(0, str(REPO))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("gamma2")

OUTPUT_BASE = REPO / "results" / "gamma2_temp_sweep"

# Endpoint pool per family. Format: list of (host, port).
# Gemma31B: 6 endpoints on 145 after Llama-4-Scout kill (γ-2 boost)
ENDPOINTS = {
    "qwen397b": [("127.0.0.1 30001)],
    "gemma31b": [
        ("127.0.0.1 30210),
        ("127.0.0.1 30211),
        ("127.0.0.1 30212),
        ("127.0.0.1 30213),
        ("127.0.0.1 30214),
        ("127.0.0.1 30215),
    ],
}


def _temp_tag(t: float) -> str:
    return f"temp{int(round(t * 10)):02d}"


def register_temp_models(family: str, temps: list[float]) -> list[str]:
    """Inject temp-variant entries into full_690_runner.MODELS at runtime.

    Returns list of model_keys that were registered.
    """
    from scripts.experiments import full_690_runner as r

    label_prefix = {"qwen397b": "Qwen3.5-397B", "gemma31b": "Gemma4-31B-IT"}[family]
    endpoints = ENDPOINTS[family]
    keys: list[str] = []
    for i, t in enumerate(temps):
        tag = _temp_tag(t)
        key = f"{family}_{tag}"
        config_path = REPO / "configs" / "agents" / f"clean_slate_{key}.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"agent config missing: {config_path}")
        host, port = endpoints[i % len(endpoints)]
        r.MODELS[key] = {
            "config": str(config_path.relative_to(REPO)),
            "port": port,
            "host": host,
            "label": f"{label_prefix} T={t}",
        }
        keys.append(key)
        logger.info("Registered MODELS[%s] -> %s:%d (label=%s T=%.1f)", key, host, port, label_prefix, t)
    return keys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", required=True, choices=["qwen397b", "gemma31b"])
    parser.add_argument(
        "--temps",
        default="0.0,0.3,0.7,1.0",
        help="Comma-separated T values to sweep",
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--guidelines", default="aabb,aba,acog,apa,pals", help="Legacy heldout 5 short codes")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=1,
        help="Run T values in parallel (1=sequential). Each T uses one endpoint slot.",
    )
    args = parser.parse_args()

    temps = [float(x) for x in args.temps.split(",")]
    keys = register_temp_models(args.family, temps)

    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    os.environ["HELDOUT_RUNS"] = str(args.runs)

    from scripts.experiments import heldout_runner as hr

    # Override LEGACY heldout 5 to match results/heldout_v1 reproducibility
    hr.HELDOUT_GUIDELINES = hr._LEGACY_HELDOUT_GUIDELINES
    hr.ALL_HELDOUT_GRAPHS = set(hr._LEGACY_HELDOUT_GUIDELINES.values())

    guideline_filter: set[str] | None = None
    if args.guidelines:
        codes = [c.strip() for c in args.guidelines.split(",")]
        guideline_filter = {hr.HELDOUT_GUIDELINES[c] for c in codes if c in hr.HELDOUT_GUIDELINES}

    scenarios = hr.load_heldout_scenario_ids(guideline_filter)
    logger.info("Loaded %d heldout scenarios across %d guidelines", len(scenarios), len(guideline_filter or set()))

    if args.dry_run:
        for k in keys:
            logger.info("DRY RUN would run %s on %d scenarios x %d runs", k, len(scenarios), args.runs)
        return 0

    # Sequential or parallel across T values
    if args.max_parallel <= 1:
        for k in keys:
            logger.info("=== Running %s ===", k)
            from scripts.experiments.full_690_runner import MODELS

            host = MODELS[k]["host"]
            port = MODELS[k]["port"]
            summary = hr.run_model(
                k,
                OUTPUT_BASE,
                scenarios,
                dry_run=False,
                shard_spec=None,
                host_override=host,
                port_override=port,
            )
            logger.info("[%s] DONE: %s", k, json.dumps(summary, default=str))
    else:
        # Parallel: spawn each T as separate subprocess so they don't share GIL
        procs = []
        for k in keys:
            log_path = OUTPUT_BASE / f"_log_{k}.txt"
            cmd = [
                sys.executable,
                __file__,
                "--family",
                args.family,
                "--temps",
                str(temps[keys.index(k)]),
                "--runs",
                str(args.runs),
                "--guidelines",
                args.guidelines,
                "--max-parallel",
                "1",
            ]
            logger.info("Spawning %s -> %s", k, log_path)
            p = subprocess.Popen(
                cmd,
                stdout=open(log_path, "w"),
                stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONPATH": f"{REPO.parent}:{REPO}"},
                cwd=str(REPO),
            )
            procs.append((k, p))
            time.sleep(2)  # stagger to avoid registry race

        for k, p in procs:
            rc = p.wait()
            logger.info("[%s] subprocess exit=%d", k, rc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
