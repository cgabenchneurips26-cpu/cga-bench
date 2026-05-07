#!/usr/bin/env python3
"""CRES-6: BEFORE-only Perturbation Analysis — Wilson CI + Expansion Plan.

Consumes the existing ``evidence_pack/exp_before_only_perturbation.json``
output (produced by ``exp_before_only_perturbation.py``, n=17 pairs),
adds Wilson 95% confidence intervals on detection rates, and records the
gap between current n=17 and the pre-registered target n>=180.

Why this script exists
----------------------
``exp_before_only_perturbation.py`` runs BEFORE-only perturbations on
synthetic conformant traces built from each CPG graph's mandatory
action set. The strict "both actions must be mandatory" eligibility
yields 17 pairs (Wilson 95% CI on 0/17 detections = [0, 18.4%]).

CRES-6 expansion to n>=180 requires relaxing eligibility to include
pairs where at least one action is in the ``all_allowed_set`` (not only
``all_mandatory_set``). That relaxation also requires extending the
synthetic-trace builder to include non-mandatory actions while
maintaining conformance — which is a non-trivial change to the original
script. That work is deferred to a dedicated PR.

This analysis script:
  1. Loads the existing n=17 result.
  2. Computes Wilson 95% CI per evaluator.
  3. Reports the implied upper bound on detection rate at current
     sample size.
  4. Prints the sample size that would be required to reach a
     pre-registered Wilson-upper bound of 2%, 3%, and 5%.
  5. Writes enriched evidence pack + LaTeX macros.

Outputs:
  evidence_pack/cres_6/cres_6_analysis.json
  evidence_pack/cres_6/cres_6_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_cres_6_before_analysis.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from scripts.experiments._common import EVIDENCE_DIR, save_json

INPUT_PATH = EVIDENCE_DIR / "exp_before_only_perturbation.json"
OUTPUT_DIR = EVIDENCE_DIR / "cres_6"

# Wilson CI z-scores
_Z_95 = 1.9599639845400545


def wilson_ci(
    n_success: int,
    n_total: int,
    z: float = _Z_95,
) -> tuple[float, float, float]:
    """Return (point_estimate, lower, upper) Wilson CI.

    Follows the Wilson score interval formula:
        center = (x + z^2/2) / (n + z^2)
        half   = (z / (n + z^2)) * sqrt( x*(n-x)/n + z^2/4 )

    Degenerate cases: n=0 returns (0.0, 0.0, 1.0).
    """
    if n_total <= 0:
        return (0.0, 0.0, 1.0)
    p_hat = n_success / n_total
    denom = 1 + z * z / n_total
    center = (p_hat + z * z / (2 * n_total)) / denom
    half = z / denom * math.sqrt(p_hat * (1 - p_hat) / n_total + z * z / (4 * n_total * n_total))
    lo = max(0.0, center - half)
    hi = min(1.0, center + half)
    return (p_hat, lo, hi)


def required_n_for_upper_bound(
    target_upper: float,
    z: float = _Z_95,
) -> int:
    """Given an observed 0 detections, how large must n be for Wilson-upper <= target?

    Closed form (for x=0): upper = z^2 / (n + z^2).
    Solve: n >= z^2 * (1/target - 1).
    """
    if target_upper <= 0 or target_upper >= 1:
        raise ValueError("target_upper must be in (0, 1)")
    return int(math.ceil(z * z * (1 / target_upper - 1)))


def main() -> int:
    print("=" * 70)
    print("CRES-6: BEFORE-only Detection — Wilson CI Analysis")
    print("=" * 70)

    if not INPUT_PATH.exists():
        print(
            f"ERROR: {INPUT_PATH} not found. Run exp_before_only_perturbation.py first.",
            file=sys.stderr,
        )
        return 1

    with open(INPUT_PATH) as f:
        raw = json.load(f)

    n_pairs = int(raw.get("n_pairs_generated", 0))
    n_orthogonal = int(raw.get("n_orthogonal", n_pairs))
    detection_rates = raw.get("detection_rates", {})
    pairs = raw.get("pairs", [])

    print(f"\nLoaded n={n_pairs} pair results, {n_orthogonal} orthogonal.")

    # Per-evaluator Wilson CI using orthogonal subset
    evaluator_cis: dict[str, dict] = {}
    for ev_name, rate in detection_rates.items():
        n_detected = int(round(rate * n_orthogonal)) if n_orthogonal else 0
        p, lo, hi = wilson_ci(n_detected, n_orthogonal)
        evaluator_cis[ev_name] = {
            "n_detected": n_detected,
            "n_total": n_orthogonal,
            "point_estimate": round(p, 6),
            "wilson_95_lower": round(lo, 6),
            "wilson_95_upper": round(hi, 6),
        }

    # Required n for pre-registered Wilson-upper thresholds (zero-detections case)
    target_upper_bounds = [0.05, 0.03, 0.02, 0.01]
    n_required = {f"upper_{ub:.2f}": required_n_for_upper_bound(ub) for ub in target_upper_bounds}

    # Check which pairs would-be expansion candidates (heuristic)
    # A pair is "expansion-eligible" if the base graph has it but it was
    # skipped because one of the actions wasn't in all_mandatory_set.
    # The existing n=17 run only kept both-mandatory pairs; the expansion
    # would recover ~(46 - 17) = 29 additional pairs at graph level, but
    # the defense doc expects ~180 at scenario level. The existing
    # experiment operates at graph level, so the graph-level ceiling is
    # about 46 unique BEFORE pairs, not 180.
    graph_level_pool = int(raw.get("n_eligible_pairs", 0))

    print("\nWilson 95% CIs per evaluator:")
    print("  evaluator     detected / n       point    [lower, upper]")
    for ev, ci in evaluator_cis.items():
        print(
            f"  {ev:<13} {ci['n_detected']:>3} / {ci['n_total']:<4} "
            f"{ci['point_estimate']:>7.4f}   [{ci['wilson_95_lower']:.4f}, {ci['wilson_95_upper']:.4f}]"
        )

    print("\nRequired n for Wilson upper bound at 0 detections:")
    for target, n_req in n_required.items():
        print(f"  {target}: n >= {n_req}")

    print(
        "\nGraph-level BEFORE pool: "
        f"{graph_level_pool} unique pairs; "
        f"expansion to scenario-level instantiation (target n>=180) "
        "is scaffolded as future work."
    )

    output = {
        "experiment": "CRES-6",
        "description": (
            "Wilson 95% CI analysis of BEFORE-only perturbation detection rates. "
            "Source: evidence_pack/exp_before_only_perturbation.json."
        ),
        "n_pairs": n_pairs,
        "n_orthogonal": n_orthogonal,
        "graph_level_pair_pool": graph_level_pool,
        "evaluators": evaluator_cis,
        "n_required_for_upper_bound_at_zero_detections": n_required,
        "expansion_status": {
            "current_n": n_orthogonal,
            "pre_registered_target_n": 180,
            "gap": max(0, 180 - n_orthogonal),
            "expansion_path": (
                "Scenario-level instantiation: iterate the 706 scenarios, "
                "for each find applicable BEFORE pairs using the scenario's "
                "parameterized graph. Requires extending the synthetic-trace "
                "builder in exp_before_only_perturbation.py to include "
                "non-mandatory actions while preserving conformance."
            ),
            "blockers": [
                "Existing script operates at graph level, not scenario level",
                "Trace builder only schedules actions from all_mandatory_set",
                "Conformance solver must accept additional allowed actions",
            ],
        },
        "source_pairs_n": len(pairs),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUTPUT_DIR / "cres_6_analysis.json"
    save_json(output, out_json)

    # Macros
    macros = [
        "% CRES-6: BEFORE-only Perturbation — Wilson CI",
        f"\\newcommand{{\\cresSixN}}{{{n_orthogonal}}}",
        "\\newcommand{\\cresSixTargetN}{180}",
    ]
    # AC-Proxy upper bound is the headline number
    ac = evaluator_cis.get("AC-Proxy")
    if ac:
        macros.append(f"\\newcommand{{\\cresSixACProxyUpperPct}}{{{ac['wilson_95_upper'] * 100:.1f}}}")
    cga = evaluator_cis.get("CGA-Bench")
    if cga:
        macros.append(f"\\newcommand{{\\cresSixCGABenchLowerPct}}{{{cga['wilson_95_lower'] * 100:.1f}}}")
    macros.append(f"\\newcommand{{\\cresSixReqNTwoPctUpper}}{{{n_required['upper_0.02']}}}")
    macros.append(f"\\newcommand{{\\cresSixReqNThreePctUpper}}{{{n_required['upper_0.03']}}}")

    out_tex = OUTPUT_DIR / "cres_6_macros.tex"
    out_tex.write_text("\n".join(macros) + "\n")

    print(f"\nSaved analysis to {out_json}")
    print(f"Saved macros to {out_tex}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
