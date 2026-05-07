"""Full v6 runner — clinical-axes (auto_v2) inclusive benchmark.

Differences from `full_690_runner.py`:

1. Always sets `CGA_BENCH_INCLUDE_AUTO_V2=1` so `ScenarioLoader` picks up
   `configs/scenarios/auto_v2/*_scenarios.yaml` (4720 clinical-axes scenarios)
   in addition to the 942 manual+pilot scenarios. Total expected = ~5662.
2. Default output dir is `results/full_v6_<timestamp>/` instead of
   `results/full_690_<timestamp>/` to keep v5 / v6 episodes separated.
3. Otherwise reuses `full_690_runner` end-to-end (atomic claim files, sharding,
   model registry, scoring, dedup, validate).

Use this runner for the v6 (post-2026-04-25) clinical-axes benchmark.
The original `full_690_runner.py` is preserved intact for v5 reproduction.

Usage::

    PYTHONPATH=. python scripts/experiments/full_v6_runner.py qwen35b
    PYTHONPATH=. python scripts/experiments/full_v6_runner.py qwen35b \\
        results/full_v6_run_20260425 --shard 1/12 --port 30002
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Force clinical-axes inclusion before any ScenarioLoader import in children.
os.environ["CGA_BENCH_INCLUDE_AUTO_V2"] = "1"


def _patch_default_output_dir() -> None:
    """Inject `results/full_v6_<timestamp>/` as the default if no positional given.

    `full_690_runner.parse_args()` defaults to `results/full_690_<ts>/`. We
    rewrite sys.argv when the user does not supply an explicit output_dir.
    """
    if len(sys.argv) < 2:
        return  # full_690 will print help / fail naturally
    # argv layout: [prog, model_key, (output_dir?), *flags]
    has_positional_output = len(sys.argv) >= 3 and not sys.argv[2].startswith("-")
    if has_positional_output:
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_dir = f"results/full_v6_{timestamp}"
    sys.argv.insert(2, default_dir)


def main() -> None:
    """Entry point — delegate to full_690_runner with env + default-dir tweaks."""
    _patch_default_output_dir()

    from scripts.experiments import full_690_runner

    full_690_runner.main()


if __name__ == "__main__":
    main()
