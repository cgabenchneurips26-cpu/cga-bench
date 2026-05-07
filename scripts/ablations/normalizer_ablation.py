#!/usr/bin/env python3
"""Experiment N: Strict Normalizer Ablation.

Re-scores existing oss120b episodes with 4 normalizer modes to measure
fuzzy matching's impact on CGA compliance scores.

Modes:
  A (current)      : full pipeline (direct + abbrev + synonym + pattern + fuzzy)
  B (strict)       : exact lowercase match only — no mappings at all
  C (pattern_only) : regex pattern rules only
  D (direct_only)  : direct mappings + domain-specific only

No GPU required — pure CPU re-evaluation of saved trajectories.

Usage:
  PYTHONPATH=${CGA_BENCH_ROOT} \
    python scripts/ablations/normalizer_ablation.py \
    --trajectories results/full_706_v5/oss120b/ \
    --output evidence_pack/normalizer_ablation/
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sys
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from cga_bench.assessor_core.action_normalizer import ActionNormalizer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Normalizer config factories (no production code modification needed)
# ---------------------------------------------------------------------------

MODES = ("current", "strict", "pattern_only", "direct_only")


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
        return ActionNormalizer()  # full default

    if mode == "strict":
        return ActionNormalizer(ActionNormalizerConfig())  # empty — exact match

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

SCENARIO_DIR = Path("configs/scenarios")


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

SKIP_FILES = {"checkpoint.json", "model_summary.json"}


def load_episodes(traj_dir: Path) -> list[dict]:
    """Load all episode JSONs from a results directory."""
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
# Re-scoring logic
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
    """Re-score a single episode with the given normalizer.

    Returns dict with coverage/commission/compliance metrics.
    """
    raw_actions = [a.get("action_id", "") for a in ep.get("actions", [])]
    expected = ep.get("expected_actions", []) or []
    forbidden = ep.get("forbidden_actions", []) or []

    # Normalize both sides with same normalizer
    norm_agent = _normalize_set(normalizer, raw_actions, cpg_id)
    norm_expected = _normalize_set(normalizer, expected, cpg_id)
    norm_forbidden = _normalize_set(normalizer, forbidden, cpg_id)

    # Coverage: how many expected actions were matched
    covered = norm_agent & norm_expected
    n_expected = len(norm_expected) if norm_expected else 1
    coverage = len(covered) / n_expected

    # Commission: how many forbidden actions were committed
    committed = norm_agent & norm_forbidden
    n_forbidden = len(norm_forbidden) if norm_forbidden else 1
    commission_rate = len(committed) / n_forbidden

    # Simple compliance (coverage-weighted, penalty for commissions)
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


def compute_mapping_diff(
    episodes: list[dict],
    norm_current: ActionNormalizer,
    norm_strict: ActionNormalizer,
    graph_map: dict[str, str],
) -> list[dict]:
    """Find top-N (raw→normalized) pairs where current differs from strict.

    These are the mappings that the normalizer "absorbs".
    """
    diff_counter: Counter[tuple[str, str]] = Counter()

    for ep in episodes:
        cpg_id = graph_map.get(ep["scenario_id"])
        for a in ep.get("actions", []):
            raw = a.get("action_id", "")
            if not raw:
                continue
            cur = norm_current.normalize(raw, cpg_id)
            strict = norm_strict.normalize(raw, cpg_id)
            if cur != strict:
                diff_counter[(strict, cur)] += 1

    return [{"raw": raw, "normalized": normed, "count": count} for (raw, normed), count in diff_counter.most_common(30)]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run normalizer ablation experiment."""
    parser = argparse.ArgumentParser(description="Experiment N: Normalizer Ablation")
    parser.add_argument(
        "--trajectories",
        default="results/full_706_v5/oss120b",
        help="Directory with episode JSONs",
    )
    parser.add_argument(
        "--output",
        default="evidence_pack/normalizer_ablation",
        help="Output directory for results",
    )
    parser.add_argument(
        "--modes",
        default=",".join(MODES),
        help="Comma-separated normalizer modes to test",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    traj_dir = Path(args.trajectories)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    modes = [m.strip() for m in args.modes.split(",")]

    # Load scenario→graph mapping
    print("Loading scenario→graph mapping...")
    graph_map = load_scenario_graph_map()

    # Load episodes
    print(f"Loading episodes from {traj_dir}...")
    episodes = load_episodes(traj_dir)
    print(f"  Loaded {len(episodes)} unique episodes")

    if not episodes:
        print("ERROR: No episodes found")
        return 1

    # Run ablation for each mode
    mode_results: dict[str, dict] = {}
    mode_per_episode: dict[str, list[dict]] = {}

    for mode in modes:
        print(f"\nScoring mode: {mode}...")
        normalizer = _make_normalizer(mode)

        scores = []
        for ep in episodes:
            cpg_id = graph_map.get(ep["scenario_id"])
            result = score_episode(ep, normalizer, cpg_id)
            scores.append(result)

        # Aggregate
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

        print(
            f"  coverage={mean_coverage:.4f}  "
            f"commission={mean_commission:.4f}  "
            f"compliance={mean_compliance:.4f}  "
            f"(covered={mean_covered:.1f}/{mean_expected:.1f})"
        )

    # Compute deltas relative to 'current'
    deltas: dict[str, dict] = {}
    if "current" in mode_results:
        cur = mode_results["current"]
        for mode in modes:
            if mode == "current":
                continue
            m = mode_results[mode]
            delta_cov = cur["mean_coverage"] - m["mean_coverage"]
            delta_comp = cur["mean_compliance"] - m["mean_compliance"]
            deltas[f"current_vs_{mode}"] = {
                "delta_coverage": round(delta_cov, 4),
                "delta_coverage_pct": round(delta_cov * 100, 2),
                "delta_compliance": round(delta_comp, 4),
                "delta_compliance_pct": round(delta_comp * 100, 2),
            }
            print(
                f"\n  DELTA current-{mode}: "
                f"coverage={delta_cov:+.4f} ({delta_cov * 100:+.2f}pp)  "
                f"compliance={delta_comp:+.4f} ({delta_comp * 100:+.2f}pp)"
            )

    # Mapping diff analysis (current vs strict)
    top_mappings: list[dict] = []
    if "current" in modes and "strict" in modes:
        print("\nComputing top mapping diffs (current vs strict)...")
        norm_cur = _make_normalizer("current")
        norm_strict = _make_normalizer("strict")
        top_mappings = compute_mapping_diff(episodes, norm_cur, norm_strict, graph_map)
        print(f"  Found {len(top_mappings)} distinct mapping diffs")
        for m in top_mappings[:10]:
            print(f"    {m['raw']} -> {m['normalized']} (x{m['count']})")

    # Violation type absorption analysis
    absorption: dict[str, int] = defaultdict(int)
    if "current" in mode_per_episode and "strict" in mode_per_episode:
        cur_eps = {(s["scenario_id"], s["run_index"]): s for s in mode_per_episode["current"]}
        for s_strict in mode_per_episode["strict"]:
            key = (s_strict["scenario_id"], s_strict["run_index"])
            s_cur = cur_eps.get(key)
            if not s_cur:
                continue
            gained = s_cur["n_covered"] - s_strict["n_covered"]
            if gained > 0:
                absorption["episodes_with_gains"] += 1
                absorption["total_gained_matches"] += gained

    # Hypothesis evaluation
    delta_key = "current_vs_strict"
    hypothesis = "UNKNOWN"
    delta_val = 0.0
    if delta_key in deltas:
        delta_val = abs(deltas[delta_key]["delta_compliance"])
        if delta_val < 0.05:
            hypothesis = "H1: normalizer is cosmetic (|delta| < 0.05)"
        elif delta_val < 0.15:
            hypothesis = "H2: moderate effect, report both (0.05 <= |delta| < 0.15)"
        else:
            hypothesis = "H3: red flag, normalizer over-rewrites (|delta| >= 0.15)"

    # Build output
    results = {
        "experiment": "N_normalizer_ablation",
        "description": "Strict Normalizer Ablation — 4 normalization modes",
        "model": "oss120b",
        "trajectory_source": str(traj_dir),
        "modes": modes,
        "mode_results": mode_results,
        "deltas": deltas,
        "hypothesis_result": hypothesis,
        "delta_current_strict_compliance": round(delta_val, 4),
        "top_mapping_diffs": top_mappings,
        "absorption_stats": dict(absorption),
        "timestamp": datetime.now(UTC).isoformat(),
    }

    # Write results JSON
    results_path = out_dir / "normalizer_ablation_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults: {results_path}")

    # Write LaTeX macros
    macros_path = out_dir / "normalizer_ablation_macros.tex"
    with open(macros_path, "w") as f:
        f.write("% Experiment N: Normalizer Ablation Macros\n")
        f.write(f"% Auto-generated {datetime.now(UTC).isoformat()}\n")
        for mode, mr in mode_results.items():
            tag = mode.replace("_", "").title()
            f.write(f"\\providecommand{{\\normAblation{tag}N}}{{{mr['n_episodes']}}}\n")
            f.write(f"\\providecommand{{\\normAblation{tag}Coverage}}{{{mr['mean_coverage']:.3f}}}\n")
            f.write(f"\\providecommand{{\\normAblation{tag}Compliance}}{{{mr['mean_compliance']:.3f}}}\n")
        # Delta macros
        if delta_key in deltas:
            d = deltas[delta_key]
            f.write(f"\\providecommand{{\\normAblationDeltaCovPP}}{{{d['delta_coverage_pct']:+.1f}}}\n")
            f.write(f"\\providecommand{{\\normAblationDeltaCompPP}}{{{d['delta_compliance_pct']:+.1f}}}\n")
        f.write(f"\\providecommand{{\\normAblationHypothesis}}{{{hypothesis[:2]}}}\n")
        if absorption:
            f.write(f"\\providecommand{{\\normAblationGainedEpisodes}}{{{absorption.get('episodes_with_gains', 0)}}}\n")
            f.write(f"\\providecommand{{\\normAblationGainedMatches}}{{{absorption.get('total_gained_matches', 0)}}}\n")
    print(f"Macros: {macros_path}")

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    for mode, mr in mode_results.items():
        print(f"  {mode:15s}: coverage={mr['mean_coverage']:.4f}  compliance={mr['mean_compliance']:.4f}")
    if delta_key in deltas:
        d = deltas[delta_key]
        print(f"\n  Delta (current-strict): {d['delta_compliance_pct']:+.2f} pp")
    print(f"  Hypothesis: {hypothesis}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
