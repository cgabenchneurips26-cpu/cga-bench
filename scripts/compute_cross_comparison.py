#!/usr/bin/env python3
"""
Compute cross-benchmark discordance analysis at scale.

Usage:
    PYTHONPATH=. python scripts/compute_cross_comparison.py \
        --results results/agentclinic_full.json results/medagentbench_full.json \
        --output evidence_pack/analysis/cross_comparison_scaled.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Discordance thresholds per benchmark
NATIVE_THRESHOLDS: Dict[str, float] = {
    "AgentClinic": 0.5,
    "MedAgentBench": 0.5,
    "MedChain": 0.5,
    "HealthBench": 0.5,
}


def _get_native_score(episode: Dict[str, Any]) -> Optional[float]:
    """Extract the native benchmark score from an episode result."""
    # Try HealthBench native_normalized first
    if "native_normalized" in episode:
        return episode["native_normalized"]
    # Standard action_coverage
    if "action_coverage" in episode:
        return episode["action_coverage"]
    return None


def _has_cga_violation(episode: Dict[str, Any]) -> bool:
    """Check if CGA found any violations in this episode."""
    cpg = episode.get("cpg_score")
    if cpg is None:
        return False
    if isinstance(cpg, dict):
        return cpg.get("total_violations", 0) > 0
    return False


def _get_violation_types(episode: Dict[str, Any]) -> List[str]:
    """Get list of violation types from an episode."""
    cpg = episode.get("cpg_score")
    if cpg is None or not isinstance(cpg, dict):
        return []
    vbt = cpg.get("violations_by_type", {})
    return [vt for vt, count in vbt.items() if count > 0]


def _wilson_ci(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo = (centre - spread) / denom
    hi = (centre + spread) / denom
    return (max(0.0, lo), min(1.0, hi))


def compute_discordance(
    results: List[Dict[str, Any]],
    benchmark: str,
) -> Dict[str, Any]:
    """Compute discordance statistics for a set of episodes."""
    threshold = NATIVE_THRESHOLDS.get(benchmark, 0.5)

    total = len(results)
    native_available = 0
    native_ok = 0
    discordant = 0
    discordant_types: Dict[str, int] = {}
    native_scores: List[float] = []
    compliance_scores: List[float] = []
    discordant_ids: List[str] = []

    for ep in results:
        native = _get_native_score(ep)
        if native is None:
            continue
        native_available += 1
        native_scores.append(native)

        cpg = ep.get("cpg_score")
        if cpg and isinstance(cpg, dict):
            compliance_scores.append(cpg.get("compliance_score", 1.0))

        if native >= threshold:
            native_ok += 1
            if _has_cga_violation(ep):
                discordant += 1
                discordant_ids.append(ep.get("scenario_id", "?"))
                for vt in _get_violation_types(ep):
                    discordant_types[vt] = discordant_types.get(vt, 0) + 1

    rate = discordant / native_ok if native_ok > 0 else 0.0
    ci_lo, ci_hi = _wilson_ci(rate, native_ok)

    return {
        "benchmark": benchmark,
        "total_episodes": total,
        "native_metric_available": native_available,
        "native_pass_count": native_ok,
        "native_pass_threshold": threshold,
        "discordant_count": discordant,
        "discordant_rate": round(rate, 4),
        "ci_95_lower": round(ci_lo, 4),
        "ci_95_upper": round(ci_hi, 4),
        "ci_95_width": round(ci_hi - ci_lo, 4),
        "native_mean": round(sum(native_scores) / len(native_scores), 4) if native_scores else None,
        "compliance_mean": round(sum(compliance_scores) / len(compliance_scores), 4) if compliance_scores else None,
        "violation_type_breakdown": discordant_types,
        "discordant_scenario_ids": discordant_ids[:50],
    }


def load_results_file(path: Path) -> tuple[str, List[Dict[str, Any]]]:
    """Load results and detect benchmark name."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Handle both list and dict formats
    if isinstance(data, list):
        results = data
    elif isinstance(data, dict):
        results = data.get("results", [])
    else:
        results = []

    # Detect benchmark from first result
    benchmark = "Unknown"
    if results:
        src = results[0].get("source_benchmark", "")
        if src:
            benchmark = src
        else:
            # Try to infer from scenario_id
            sid = results[0].get("scenario_id", "")
            if "agentclinic" in sid:
                benchmark = "AgentClinic"
            elif "medagentbench" in sid:
                benchmark = "MedAgentBench"
            elif "medchain" in sid:
                benchmark = "MedChain"
            elif "healthbench" in sid or "prompt_id" in results[0]:
                benchmark = "HealthBench"

    return benchmark, results


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-benchmark discordance analysis")
    parser.add_argument("--results", nargs="+", required=True, help="Result JSON files")
    parser.add_argument("--output", default="evidence_pack/analysis/cross_comparison_scaled.json")
    args = parser.parse_args()

    all_benchmarks: Dict[str, Dict[str, Any]] = {}
    total_episodes = 0
    total_discordant = 0
    total_native_ok = 0

    for result_path in args.results:
        path = Path(result_path)
        if not path.exists():
            print(f"WARNING: {path} not found, skipping", file=sys.stderr)
            continue

        benchmark, results = load_results_file(path)
        analysis = compute_discordance(results, benchmark)

        # Merge if same benchmark from multiple files
        if benchmark in all_benchmarks:
            prev = all_benchmarks[benchmark]
            # Simple: just take the larger one
            if analysis["total_episodes"] > prev["total_episodes"]:
                all_benchmarks[benchmark] = analysis
        else:
            all_benchmarks[benchmark] = analysis

        total_episodes += analysis["total_episodes"]
        total_discordant += analysis["discordant_count"]
        total_native_ok += analysis["native_pass_count"]

    # Overall
    overall_rate = total_discordant / total_native_ok if total_native_ok > 0 else 0.0
    ci_lo, ci_hi = _wilson_ci(overall_rate, total_native_ok)

    output = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "total_episodes": total_episodes,
        "total_native_pass": total_native_ok,
        "total_discordant": total_discordant,
        "overall_discordant_rate": round(overall_rate, 4),
        "overall_ci_95": [round(ci_lo, 4), round(ci_hi, 4)],
        "overall_ci_width": round(ci_hi - ci_lo, 4),
        "per_benchmark": all_benchmarks,
    }

    # Print summary table
    print("=" * 80)
    print("Cross-Benchmark Discordance Analysis")
    print("=" * 80)
    print(f"{'Benchmark':<16} {'N':>6} {'Pass':>6} {'Discord':>8} {'Rate':>7} {'95% CI':>16}")
    print("-" * 80)
    for bm, info in sorted(all_benchmarks.items()):
        ci = f"[{info['ci_95_lower']:.1%},{info['ci_95_upper']:.1%}]"
        print(f"{bm:<16} {info['total_episodes']:>6} {info['native_pass_count']:>6} "
              f"{info['discordant_count']:>8} {info['discordant_rate']:>6.1%} {ci:>16}")
    print("-" * 80)
    ci_overall = f"[{ci_lo:.1%},{ci_hi:.1%}]"
    print(f"{'TOTAL':<16} {total_episodes:>6} {total_native_ok:>6} "
          f"{total_discordant:>8} {overall_rate:>6.1%} {ci_overall:>16}")
    print("=" * 80)

    # Save
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    main()
