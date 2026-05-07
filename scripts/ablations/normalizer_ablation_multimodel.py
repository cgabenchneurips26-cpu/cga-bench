#!/usr/bin/env python3
"""Experiment N-Multi: Strict Normalizer Ablation across all 9 complete models.

Re-scores existing episodes with 4 normalizer modes to measure fuzzy
matching's impact on CGA compliance scores, across all 9 complete models.

Models: oss120b, qwen27b, qwen35b, qwen4b, qwen397b, gemma31b, nemotron30b, deepseek_r1_7b, llama4scout

Modes:
  A (current)      : full pipeline (direct + abbrev + synonym + pattern + fuzzy)
  B (strict)       : exact lowercase match only — no mappings at all
  C (pattern_only) : regex pattern rules only
  D (direct_only)  : direct mappings + domain-specific only

No GPU required — pure CPU re-evaluation of saved trajectories.

Usage:
  PYTHONPATH=${CGA_BENCH_ROOT} \\
    python scripts/ablations/normalizer_ablation_multimodel.py \\
    --results-root results/full_706_v5/ \\
    --output evidence_pack/normalizer_ablation/
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import logging
import math
from pathlib import Path
import sys
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from cga_bench.assessor_core.action_normalizer import ActionNormalizer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMPLETE_MODELS = [
    "oss120b",
    "qwen27b",
    "qwen35b",
    "qwen4b",
    "qwen397b",
    "gemma31b",
    "nemotron30b",
    "deepseek_r1_7b",
    "llama4scout",
]

MODES = ("current", "strict", "pattern_only", "direct_only")

SKIP_FILES = {"checkpoint.json", "model_summary.json"}

SCENARIO_DIR = Path("configs/scenarios")


# ---------------------------------------------------------------------------
# Normalizer config factories
# ---------------------------------------------------------------------------


def _make_normalizer(mode: str) -> ActionNormalizer:
    """Create an ActionNormalizer with mode-specific config."""
    from cga_bench.assessor_core.action_normalizer import (
        _DEFAULT_DIRECT_MAPPINGS,
        _DEFAULT_DOMAIN_SPECIFIC_MAPPINGS,
        _DEFAULT_PATTERN_RULES,
        ActionNormalizer,
        ActionNormalizerConfig,
    )

    if mode == "current":
        return ActionNormalizer()

    if mode == "strict":
        return ActionNormalizer(ActionNormalizerConfig())

    if mode == "pattern_only":
        return ActionNormalizer(ActionNormalizerConfig(pattern_rules=list(_DEFAULT_PATTERN_RULES)))

    if mode == "direct_only":
        return ActionNormalizer(
            ActionNormalizerConfig(
                direct_mappings=dict(_DEFAULT_DIRECT_MAPPINGS),
                domain_specific_mappings={k: dict(v) for k, v in _DEFAULT_DOMAIN_SPECIFIC_MAPPINGS.items()},
            )
        )

    raise ValueError(f"Unknown mode: {mode}")


# ---------------------------------------------------------------------------
# Scenario → guideline_graph mapping
# ---------------------------------------------------------------------------


def load_scenario_graph_map() -> dict[str, str]:
    """Return {scenario_id: guideline_graph} from all scenario YAMLs."""
    mapping: dict[str, str] = {}
    for f in sorted(SCENARIO_DIR.glob("*.yaml")):
        with open(f) as fh:
            data = yaml.safe_load(fh)
        for sid, s in (data.get("scenarios") or {}).items():
            g = s.get("guideline_graph", "")
            if g:
                mapping[sid] = g
    return mapping


# ---------------------------------------------------------------------------
# Episode loading
# ---------------------------------------------------------------------------


def load_episodes(traj_dir: Path) -> list[dict]:
    """Load all episode JSONs from a results directory, deduped by (scenario_id, run_index)."""
    episodes: list[dict] = []
    seen: set[str] = set()
    for f in sorted(traj_dir.glob("*.json")):
        if f.name in SKIP_FILES or f.name.startswith("checkpoint"):
            continue
        try:
            with open(f) as fh:
                ep = json.load(fh)
            sid = ep.get("scenario_id", "")
            ridx = ep.get("run_index", 0)
            if not sid:
                continue
            key = f"{sid}_r{ridx}"
            if key in seen:
                continue
            seen.add(key)
            episodes.append(ep)
        except (json.JSONDecodeError, OSError):
            continue
    return episodes


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------


def _normalize_set(
    normalizer: ActionNormalizer,
    action_ids: list[str],
    cpg_id: str | None,
) -> set[str]:
    """Normalize a list of action IDs and return unique set."""
    return {normalizer.normalize(a, cpg_id) for a in action_ids if a}


def score_episode(
    ep: dict,
    normalizer: ActionNormalizer,
    cpg_id: str | None,
) -> dict:
    """Re-score a single episode with the given normalizer."""
    raw_actions = [a.get("action_id", "") for a in ep.get("actions", [])]
    expected = ep.get("expected_actions", []) or []
    forbidden = ep.get("forbidden_actions", []) or []

    norm_agent = _normalize_set(normalizer, raw_actions, cpg_id)
    norm_expected = _normalize_set(normalizer, expected, cpg_id)
    norm_forbidden = _normalize_set(normalizer, forbidden, cpg_id)

    covered = norm_agent & norm_expected
    n_expected = len(norm_expected) if norm_expected else 1
    coverage = len(covered) / n_expected

    committed = norm_agent & norm_forbidden
    n_forbidden = len(norm_forbidden) if norm_forbidden else 1
    commission_rate = len(committed) / n_forbidden

    compliance = coverage * (1.0 - 0.5 * commission_rate)

    return {
        "scenario_id": ep["scenario_id"],
        "run_index": ep.get("run_index", 0),
        "n_agent_actions": len(raw_actions),
        "n_expected": len(norm_expected),
        "n_forbidden": len(norm_forbidden),
        "n_covered": len(covered),
        "n_committed": len(committed),
        "coverage": round(coverage, 4),
        "commission_rate": round(commission_rate, 4),
        "compliance": round(compliance, 4),
    }


def score_model(
    episodes: list[dict],
    graph_map: dict[str, str],
    modes: tuple[str, ...],
) -> dict[str, dict]:
    """Score all episodes for each mode. Returns {mode: aggregate_stats}."""
    mode_results: dict[str, dict] = {}
    mode_per_episode: dict[str, list[dict]] = {}

    for mode in modes:
        normalizer = _make_normalizer(mode)
        scores = []
        for ep in episodes:
            cpg_id = graph_map.get(ep["scenario_id"])
            result = score_episode(ep, normalizer, cpg_id)
            scores.append(result)

        n = len(scores)
        mean_coverage = sum(s["coverage"] for s in scores) / n
        mean_commission = sum(s["commission_rate"] for s in scores) / n
        mean_compliance = sum(s["compliance"] for s in scores) / n
        mean_covered = sum(s["n_covered"] for s in scores) / n
        mean_expected = sum(s["n_expected"] for s in scores) / n

        mode_results[mode] = {
            "n_episodes": n,
            "mean_coverage": round(mean_coverage, 4),
            "mean_commission_rate": round(mean_commission, 4),
            "mean_compliance": round(mean_compliance, 4),
            "mean_covered_actions": round(mean_covered, 2),
            "mean_expected_actions": round(mean_expected, 2),
        }
        mode_per_episode[mode] = scores

    return mode_results, mode_per_episode


def compute_model_deltas(mode_results: dict[str, dict]) -> dict[str, dict]:
    """Compute deltas of each mode vs 'current'."""
    deltas: dict[str, dict] = {}
    if "current" not in mode_results:
        return deltas
    cur = mode_results["current"]
    for mode, mr in mode_results.items():
        if mode == "current":
            continue
        delta_cov = cur["mean_coverage"] - mr["mean_coverage"]
        delta_comp = cur["mean_compliance"] - mr["mean_compliance"]
        deltas[f"current_vs_{mode}"] = {
            "delta_coverage": round(delta_cov, 4),
            "delta_coverage_pct": round(delta_cov * 100, 2),
            "delta_compliance": round(delta_comp, 4),
            "delta_compliance_pct": round(delta_comp * 100, 2),
        }
    return deltas


# ---------------------------------------------------------------------------
# Cross-model ranking: Spearman rho
# ---------------------------------------------------------------------------


def _rank_list(values: list[float]) -> list[float]:
    """Return 1-based ranks for a list of values (ascending, average ties)."""
    n = len(values)
    sorted_with_idx = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        # Find ties
        while j < n - 1 and sorted_with_idx[j + 1][1] == sorted_with_idx[j][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[sorted_with_idx[k][0]] = avg_rank
        i = j + 1
    return ranks


def spearman_rho(x: list[float], y: list[float]) -> float:
    """Compute Spearman rank correlation between two lists."""
    n = len(x)
    if n < 2:
        return float("nan")
    rx = _rank_list(x)
    ry = _rank_list(y)
    d2 = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    rho = 1.0 - (6.0 * d2) / (n * (n * n - 1))
    return round(rho, 4)


# ---------------------------------------------------------------------------
# Aggregate stats across models
# ---------------------------------------------------------------------------


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else float("nan")


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))


def compute_aggregate(per_model: dict[str, dict]) -> dict:
    """Compute aggregate stats across all models for current vs strict delta."""
    delta_cov_vals: list[float] = []
    delta_comp_vals: list[float] = []

    for model_data in per_model.values():
        deltas = model_data.get("deltas", {})
        d = deltas.get("current_vs_strict", {})
        if d:
            delta_cov_vals.append(d["delta_coverage_pct"])
            delta_comp_vals.append(d["delta_compliance_pct"])

    return {
        "n_models": len(per_model),
        "delta_coverage_pp": {
            "mean": round(_mean(delta_cov_vals), 3),
            "std": round(_std(delta_cov_vals), 3),
            "min": round(min(delta_cov_vals), 3) if delta_cov_vals else float("nan"),
            "max": round(max(delta_cov_vals), 3) if delta_cov_vals else float("nan"),
        },
        "delta_compliance_pp": {
            "mean": round(_mean(delta_comp_vals), 3),
            "std": round(_std(delta_comp_vals), 3),
            "min": round(min(delta_comp_vals), 3) if delta_comp_vals else float("nan"),
            "max": round(max(delta_comp_vals), 3) if delta_comp_vals else float("nan"),
        },
    }


def compute_ranking_stability(per_model: dict[str, dict]) -> dict:
    """Spearman rho between model compliance rankings under current vs strict."""
    models = list(per_model.keys())
    current_comp = [per_model[m]["mode_results"].get("current", {}).get("mean_compliance", 0.0) for m in models]
    strict_comp = [per_model[m]["mode_results"].get("strict", {}).get("mean_compliance", 0.0) for m in models]
    rho = spearman_rho(current_comp, strict_comp)
    return {
        "models": models,
        "current_compliance": [round(v, 4) for v in current_comp],
        "strict_compliance": [round(v, 4) for v in strict_comp],
        "spearman_rho": rho,
    }


# ---------------------------------------------------------------------------
# Hypothesis evaluation
# ---------------------------------------------------------------------------


def evaluate_hypothesis(mean_delta_compliance_pp: float) -> str:
    """Evaluate H1/H2/H3 based on mean compliance delta across models."""
    abs_delta = abs(mean_delta_compliance_pp)
    if abs_delta < 5.0:
        return "H1: normalizer is cosmetic across models (|mean delta| < 5pp)"
    elif abs_delta < 15.0:
        return "H2: moderate effect across models, report both (5pp <= |mean delta| < 15pp)"
    else:
        return "H3: red flag, normalizer over-rewrites across models (|mean delta| >= 15pp)"


# ---------------------------------------------------------------------------
# LaTeX macro generation
# ---------------------------------------------------------------------------


def write_macros(
    path: Path,
    aggregate: dict,
    ranking: dict,
    hypothesis: str,
    total_episodes: int,
    n_models: int,
) -> None:
    """Write LaTeX macros file."""
    delta_cov = aggregate["delta_coverage_pp"]
    delta_comp = aggregate["delta_compliance_pp"]
    rho = ranking["spearman_rho"]
    hyp_tag = hypothesis[:2]

    with open(path, "w") as f:
        f.write("% Experiment N-Multi: Multi-Model Normalizer Ablation Macros\n")
        f.write(f"% Auto-generated {datetime.now(UTC).isoformat()}\n")
        f.write(f"\\providecommand{{\\normMultiNModels}}{{{n_models}}}\n")
        f.write(f"\\providecommand{{\\normMultiNEpisodes}}{{{total_episodes}}}\n")
        f.write(f"\\providecommand{{\\normMultiMeanDeltaCovPP}}{{{delta_cov['mean']:+.1f}}}\n")
        f.write(f"\\providecommand{{\\normMultiMeanDeltaCompPP}}{{{delta_comp['mean']:+.1f}}}\n")
        f.write(f"\\providecommand{{\\normMultiMaxDeltaCompPP}}{{{delta_comp['max']:+.1f}}}\n")
        f.write(f"\\providecommand{{\\normMultiMinDeltaCompPP}}{{{delta_comp['min']:+.1f}}}\n")
        f.write(f"\\providecommand{{\\normMultiRankingRho}}{{{rho:.3f}}}\n")
        f.write(f"\\providecommand{{\\normMultiHypothesis}}{{{hyp_tag}}}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run multi-model normalizer ablation experiment."""
    parser = argparse.ArgumentParser(description="Experiment N-Multi: Multi-Model Normalizer Ablation")
    parser.add_argument(
        "--results-root",
        default="results/full_706_v5",
        help="Root directory containing per-model result subdirectories",
    )
    parser.add_argument(
        "--output",
        default="evidence_pack/normalizer_ablation",
        help="Output directory for results",
    )
    parser.add_argument(
        "--models",
        default=",".join(COMPLETE_MODELS),
        help="Comma-separated model names to process",
    )
    parser.add_argument(
        "--modes",
        default=",".join(MODES),
        help="Comma-separated normalizer modes to test",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    results_root = Path(args.results_root)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    models = [m.strip() for m in args.models.split(",")]
    modes = tuple(m.strip() for m in args.modes.split(","))

    print(f"Multi-model normalizer ablation: {len(models)} models x {len(modes)} modes")
    print(f"Models: {', '.join(models)}")

    # Load scenario->graph mapping once
    print("\nLoading scenario->graph mapping...")
    graph_map = load_scenario_graph_map()
    print(f"  {len(graph_map)} scenario->graph mappings loaded")

    # Process each model
    per_model: dict[str, dict] = {}
    total_episodes = 0

    for model in models:
        traj_dir = results_root / model
        if not traj_dir.exists():
            print(f"\n[SKIP] {model}: directory not found at {traj_dir}")
            continue

        print(f"\n{'=' * 60}")
        print(f"Model: {model}")
        print(f"{'=' * 60}")

        episodes = load_episodes(traj_dir)
        n_ep = len(episodes)
        print(f"  Loaded {n_ep} unique episodes")

        if not episodes:
            print("  [SKIP] No episodes found")
            continue

        total_episodes += n_ep

        model_mode_results: dict[str, dict] = {}
        model_per_episode: dict[str, list[dict]] = {}

        for mode in modes:
            print(f"  Scoring mode: {mode}...", end="", flush=True)
            normalizer = _make_normalizer(mode)
            scores = []
            for ep in episodes:
                cpg_id = graph_map.get(ep["scenario_id"])
                result = score_episode(ep, normalizer, cpg_id)
                scores.append(result)

            n = len(scores)
            mean_coverage = sum(s["coverage"] for s in scores) / n
            mean_commission = sum(s["commission_rate"] for s in scores) / n
            mean_compliance = sum(s["compliance"] for s in scores) / n
            mean_covered = sum(s["n_covered"] for s in scores) / n
            mean_expected = sum(s["n_expected"] for s in scores) / n

            model_mode_results[mode] = {
                "n_episodes": n,
                "mean_coverage": round(mean_coverage, 4),
                "mean_commission_rate": round(mean_commission, 4),
                "mean_compliance": round(mean_compliance, 4),
                "mean_covered_actions": round(mean_covered, 2),
                "mean_expected_actions": round(mean_expected, 2),
            }
            model_per_episode[mode] = scores

            print(f" coverage={mean_coverage:.4f}  commission={mean_commission:.4f}  compliance={mean_compliance:.4f}")

        # Per-model deltas
        model_deltas = compute_model_deltas(model_mode_results)
        if "current_vs_strict" in model_deltas:
            d = model_deltas["current_vs_strict"]
            print(
                f"\n  DELTA current-strict: "
                f"coverage={d['delta_coverage_pct']:+.2f}pp  "
                f"compliance={d['delta_compliance_pct']:+.2f}pp"
            )

        per_model[model] = {
            "mode_results": model_mode_results,
            "deltas": model_deltas,
            "n_episodes": n_ep,
        }

    if not per_model:
        print("\nERROR: No models processed successfully")
        return 1

    print(f"\n{'=' * 60}")
    print("AGGREGATE ANALYSIS")
    print(f"{'=' * 60}")

    # Aggregate stats
    aggregate = compute_aggregate(per_model)
    delta_comp = aggregate["delta_compliance_pp"]
    delta_cov = aggregate["delta_coverage_pp"]
    print(f"  Mean delta coverage  (current-strict): {delta_cov['mean']:+.3f} pp  (std={delta_cov['std']:.3f})")
    print(f"  Mean delta compliance (current-strict): {delta_comp['mean']:+.3f} pp  (std={delta_comp['std']:.3f})")
    print(f"  Min/Max compliance delta: {delta_comp['min']:+.3f} / {delta_comp['max']:+.3f} pp")

    # Cross-model ranking stability
    ranking = compute_ranking_stability(per_model)
    print(f"  Spearman rho (model rankings current vs strict): {ranking['spearman_rho']:.4f}")

    # Hypothesis
    hypothesis = evaluate_hypothesis(delta_comp["mean"])
    print(f"  Hypothesis: {hypothesis}")

    # Build full output
    results = {
        "experiment": "N_normalizer_ablation_multimodel",
        "description": "Multi-Model Strict Normalizer Ablation — 9 models x 4 normalization modes",
        "models": list(per_model.keys()),
        "modes": list(modes),
        "total_episodes": total_episodes,
        "per_model": per_model,
        "aggregate": aggregate,
        "cross_model_ranking": ranking,
        "hypothesis_result": hypothesis,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Write results JSON
    results_path = out_dir / "multimodel_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults: {results_path}")

    # Write LaTeX macros
    macros_path = out_dir / "multimodel_macros.tex"
    write_macros(
        macros_path,
        aggregate=aggregate,
        ranking=ranking,
        hypothesis=hypothesis,
        total_episodes=total_episodes,
        n_models=len(per_model),
    )
    print(f"Macros: {macros_path}")

    # Per-model summary table
    print(f"\n{'=' * 60}")
    print("PER-MODEL SUMMARY (current mode compliance)")
    print(f"{'=' * 60}")
    print(f"  {'Model':20s}  {'N':>5}  {'Coverage':>9}  {'Compliance':>10}  {'Delta(comp)':>12}")
    print(f"  {'-' * 20}  {'-' * 5}  {'-' * 9}  {'-' * 10}  {'-' * 12}")
    for model, mdata in per_model.items():
        cur = mdata["mode_results"].get("current", {})
        delta_str = "n/a"
        d = mdata["deltas"].get("current_vs_strict", {})
        if d:
            delta_str = f"{d['delta_compliance_pct']:+.2f}pp"
        print(
            f"  {model:20s}  {mdata['n_episodes']:>5}  "
            f"{cur.get('mean_coverage', 0):.4f}     "
            f"{cur.get('mean_compliance', 0):.4f}      "
            f"{delta_str:>12}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
