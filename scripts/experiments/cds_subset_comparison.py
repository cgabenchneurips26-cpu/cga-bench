"""TG-V1 — CDS=True / CDS=False subset comparison harness.

Quantifies the evaluation-leakage magnitude of exposing ``mandatory_actions``
to the agent.  Phase F's claim that ``cds_assistance: bool = False`` should be
the default benchmark posture rests on the empirical score-delta between the
two arms; without that delta, a reviewer can legitimately ask "why is False
the right default?"

Design (Day 5-6 compute window):

    * 14 CPGs (one representative each from the trust-gate corpus)
    * 50 scenarios per CPG (~10% of the canonical sweep)
    * 9 models (the standard SGSC sweep models)
    * 3 runs per (model, scenario, mode)
    * 2 modes: cds_assistance=True (v6 implicit) vs False (v7 default)

Total episodes: ~14 * 50 * 9 * 3 * 2 = 37,800 (= 18,900 per arm).
This is roughly 2x the canonical Phase A rerun budget; do NOT bump the
subset above 50 scenarios per CPG without a fresh budget review.

Output (per arm):
    results/cds_subset/<arm>/episode_logs.jsonl
    results/cds_subset/<arm>/aggregate.json

Comparison report:
    results/cds_subset/comparison.json   — score-delta per CPG, per model
    results/cds_subset/comparison.md     — human-readable summary

The harness is a *driver*: it does not itself spawn the runner pool.  It
emits per-(arm, scenario, model) job descriptors to STDOUT in JSONL form,
which are consumed by ``scripts/experiments/full_690_runner.py`` (or a
shell wrapper that submits them to vLLM).  This separation keeps the
selection logic deterministic and the compute layer pluggable.

Usage::

    python scripts/experiments/cds_subset_comparison.py \\
        --scenarios-dir cpg_model/graphs \\
        --models qwen35b oss120b ... \\
        --per-cpg 50 --runs 3 \\
        --output-dir results/cds_subset \\
        > job_descriptors.jsonl

    # Submit jobs (existing infrastructure)
    cat job_descriptors.jsonl | xargs -L 1 python scripts/experiments/full_690_runner.py ...

    # After all jobs complete, aggregate:
    python scripts/experiments/cds_subset_comparison.py \\
        --aggregate results/cds_subset/

The aggregate phase reads each arm's episode logs, computes per-CPG mean
compliance scores, and writes the comparison delta table.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Dataclasses
# ------------------------------------------------------------------


@dataclass(frozen=True)
class JobDescriptor:
    """One unit of compute work: (cpg, scenario, model, run_idx, arm)."""

    cpg_id: str
    scenario_id: str
    model: str
    run_idx: int
    arm: str  # "cds_true" | "cds_false"
    output_path: str


@dataclass(frozen=True)
class ArmAggregate:
    """Per-(arm, cpg, model) aggregated score."""

    arm: str
    cpg_id: str
    model: str
    n_episodes: int
    mean_compliance: float
    mean_peak_risk: float
    mean_aggregate_risk: float


@dataclass(frozen=True)
class ComparisonRow:
    """One row of the cross-arm comparison table."""

    cpg_id: str
    model: str
    n_episodes_per_arm: int
    compliance_cds_true: float
    compliance_cds_false: float
    delta_compliance: float  # true - false (positive = leakage helps the agent)


# ------------------------------------------------------------------
# Subset selection
# ------------------------------------------------------------------


def select_scenarios_per_cpg(
    available_scenarios: dict[str, list[str]],
    per_cpg: int,
    seed: int,
) -> dict[str, list[str]]:
    """Deterministically pick ``per_cpg`` scenarios from each CPG.

    Args:
        available_scenarios: Map of cpg_id -> list of scenario_ids in that CPG.
        per_cpg: Number of scenarios to pick from each CPG.  Capped at
            ``len(available)`` for CPGs with fewer scenarios.
        seed: Random seed for reproducible selection.

    Returns:
        Map of cpg_id -> selected scenario_ids (sorted for determinism).
    """
    rng = random.Random(seed)
    selected: dict[str, list[str]] = {}
    for cpg_id, scenarios in sorted(available_scenarios.items()):
        cap = min(per_cpg, len(scenarios))
        chosen = sorted(rng.sample(scenarios, cap))
        selected[cpg_id] = chosen
    return selected


# ------------------------------------------------------------------
# Job emission
# ------------------------------------------------------------------


def emit_jobs(
    selected: dict[str, list[str]],
    models: list[str],
    n_runs: int,
    output_root: Path,
) -> list[JobDescriptor]:
    """Build the cartesian product of (cpg, scenario, model, run, arm)."""
    jobs: list[JobDescriptor] = []
    for cpg_id, scenarios in selected.items():
        for scenario_id in scenarios:
            for model in models:
                for run_idx in range(n_runs):
                    for arm in ("cds_true", "cds_false"):
                        jobs.append(
                            JobDescriptor(
                                cpg_id=cpg_id,
                                scenario_id=scenario_id,
                                model=model,
                                run_idx=run_idx,
                                arm=arm,
                                output_path=str(
                                    output_root
                                    / arm
                                    / cpg_id
                                    / f"{scenario_id}_{model}_run{run_idx}.json"
                                ),
                            )
                        )
    return jobs


# ------------------------------------------------------------------
# Aggregation
# ------------------------------------------------------------------


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate_arm_episodes(arm_dir: Path) -> list[ArmAggregate]:
    """Walk ``arm_dir/<cpg>/<scenario>_<model>_runN.json`` and aggregate scores.

    Each episode JSON is expected to contain at minimum:
        compliance_score: float in [0, 1]
        peak_risk: float
        aggregate_risk: float
    """
    arm = arm_dir.name
    by_cpg_model: dict[tuple[str, str], list[dict[str, float]]] = {}

    for cpg_dir in sorted(arm_dir.iterdir()):
        if not cpg_dir.is_dir():
            continue
        cpg_id = cpg_dir.name
        for episode_path in sorted(cpg_dir.glob("*.json")):
            try:
                data = json.loads(episode_path.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping unreadable episode %s: %s", episode_path, exc)
                continue
            model = episode_path.stem.split("_")[-2] if "_" in episode_path.stem else "unknown"
            by_cpg_model.setdefault((cpg_id, model), []).append(
                {
                    "compliance_score": float(data.get("compliance_score", 0.0)),
                    "peak_risk": float(data.get("peak_risk", 0.0)),
                    "aggregate_risk": float(data.get("aggregate_risk", 0.0)),
                }
            )

    aggregates: list[ArmAggregate] = []
    for (cpg_id, model), episodes in sorted(by_cpg_model.items()):
        aggregates.append(
            ArmAggregate(
                arm=arm,
                cpg_id=cpg_id,
                model=model,
                n_episodes=len(episodes),
                mean_compliance=_mean([e["compliance_score"] for e in episodes]),
                mean_peak_risk=_mean([e["peak_risk"] for e in episodes]),
                mean_aggregate_risk=_mean([e["aggregate_risk"] for e in episodes]),
            )
        )
    return aggregates


def build_comparison_rows(
    cds_true: list[ArmAggregate],
    cds_false: list[ArmAggregate],
) -> list[ComparisonRow]:
    """Inner-join the two arms on (cpg_id, model) and compute deltas."""
    by_key_true = {(a.cpg_id, a.model): a for a in cds_true}
    by_key_false = {(a.cpg_id, a.model): a for a in cds_false}
    keys = sorted(set(by_key_true) & set(by_key_false))

    rows: list[ComparisonRow] = []
    for key in keys:
        t = by_key_true[key]
        f = by_key_false[key]
        # Episode counts should match per-arm; pick the min for the report.
        n = min(t.n_episodes, f.n_episodes)
        rows.append(
            ComparisonRow(
                cpg_id=key[0],
                model=key[1],
                n_episodes_per_arm=n,
                compliance_cds_true=t.mean_compliance,
                compliance_cds_false=f.mean_compliance,
                delta_compliance=t.mean_compliance - f.mean_compliance,
            )
        )
    return rows


def render_comparison_md(rows: list[ComparisonRow]) -> str:
    """Render the comparison table as Markdown for paper inclusion."""
    if not rows:
        return "# CDS True/False Comparison\n\n_No matched episodes to compare._\n"

    overall_delta = _mean([r.delta_compliance for r in rows])

    lines = [
        "# CDS True/False Subset Comparison (TG-V1 evidence)",
        "",
        f"**Overall mean compliance delta (CDS_true - CDS_false): {overall_delta:+.4f}**",
        "",
        "Positive delta = exposing `mandatory_actions` to the agent boosts compliance,",
        "i.e. the leakage hint inflates the score relative to the unassisted baseline.",
        "",
        "| CPG | Model | n/arm | CDS_true | CDS_false | Delta |",
        "|-----|-------|-------|---------:|----------:|------:|",
    ]
    for r in rows:
        lines.append(
            f"| {r.cpg_id} | {r.model} | {r.n_episodes_per_arm} | "
            f"{r.compliance_cds_true:.4f} | {r.compliance_cds_false:.4f} | "
            f"{r.delta_compliance:+.4f} |"
        )
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TG-V1 CDS=True/False subset comparison driver.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    plan = sub.add_parser("plan", help="Emit per-job descriptors as JSONL.")
    plan.add_argument("--scenarios-manifest", type=Path, required=True,
                      help="JSON file mapping cpg_id -> [scenario_id, ...].")
    plan.add_argument("--models", nargs="+", required=True,
                      help="Model identifiers, e.g. qwen35b oss120b.")
    plan.add_argument("--per-cpg", type=int, default=50,
                      help="Scenarios sampled per CPG (capped at availability).")
    plan.add_argument("--runs", type=int, default=3,
                      help="Runs per (scenario, model, arm).")
    plan.add_argument("--output-dir", type=Path, required=True,
                      help="Root directory for episode JSON outputs.")
    plan.add_argument("--seed", type=int, default=42)

    agg = sub.add_parser("aggregate", help="Aggregate completed episodes into a report.")
    agg.add_argument("--arms-dir", type=Path, required=True,
                     help="Directory containing 'cds_true/' and 'cds_false/' subdirs.")
    return parser


def cmd_plan(args: argparse.Namespace) -> int:
    available = json.loads(args.scenarios_manifest.read_text())
    if not isinstance(available, dict):
        print("ERROR: scenarios manifest must be a JSON object", file=sys.stderr)
        return 1
    selected = select_scenarios_per_cpg(available, per_cpg=args.per_cpg, seed=args.seed)
    jobs = emit_jobs(selected, args.models, args.runs, args.output_dir)
    for job in jobs:
        print(json.dumps(asdict(job)))
    print(
        f"# emitted {len(jobs)} job descriptors "
        f"({len(selected)} CPGs * {args.per_cpg} scenarios * {len(args.models)} models * "
        f"{args.runs} runs * 2 arms)",
        file=sys.stderr,
    )
    return 0


def cmd_aggregate(args: argparse.Namespace) -> int:
    cds_true_dir = args.arms_dir / "cds_true"
    cds_false_dir = args.arms_dir / "cds_false"
    if not cds_true_dir.exists() or not cds_false_dir.exists():
        print("ERROR: arms_dir must contain cds_true/ and cds_false/", file=sys.stderr)
        return 1

    cds_true = aggregate_arm_episodes(cds_true_dir)
    cds_false = aggregate_arm_episodes(cds_false_dir)
    rows = build_comparison_rows(cds_true, cds_false)

    out_json = args.arms_dir / "comparison.json"
    out_md = args.arms_dir / "comparison.md"
    out_json.write_text(
        json.dumps(
            {"rows": [asdict(r) for r in rows], "n_rows": len(rows)},
            indent=2,
        )
    )
    out_md.write_text(render_comparison_md(rows))
    print(f"Wrote {out_json} and {out_md}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "plan":
        return cmd_plan(args)
    if args.cmd == "aggregate":
        return cmd_aggregate(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
