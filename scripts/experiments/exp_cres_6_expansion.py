#!/usr/bin/env python3
"""CRES-6 Expansion: Scenario-Level BEFORE Perturbation.

Extends the graph-level BEFORE perturbation (n=17) to scenario-level
by iterating over all 706 scenarios.  For each scenario, finds BEFORE
pairs where both actions appear in the scenario's expected_actions,
builds a synthetic conformant trace, perturbs, and scores.

Target: n >= 180  →  Wilson upper ≤ 2% at zero detections.

Algorithm:
  1. Load all 706 scenarios with their expected_actions.
  2. Load all 25 CPG graphs and extract BEFORE pairs.
  3. For each scenario:
     a. Resolve its graph.
     b. Filter BEFORE pairs to those where BOTH actions are in the
        scenario's expected_actions set.
     c. Build a synthetic conformant trace from expected_actions,
        respecting BEFORE ordering and WITHIN deadlines.
     d. Verify d_G = 0 via ConformanceDistanceSolver.
     e. Swap the BEFORE pair's timestamps.
     f. Verify orthogonality (BEFORE-only violation).
     g. Score both traces.
  4. Compute Wilson CIs on detection rates.

Outputs:
  evidence_pack/cres_6_expansion/cres_6_expansion_results.json
  evidence_pack/cres_6_expansion/cres_6_expansion_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_cres_6_expansion.py
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
from typing import Any

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[3]))  # AnonProject/
sys.path.insert(0, str(_HERE.parents[2]))  # cga_bench/

from cpg_model.conformance_distance import (  # noqa: E402
    ConformanceDistanceSolver,
    CostConfig,
)
from cpg_model.schemas.base import Action, ActionType  # noqa: E402
from scripts.experiments._common import (  # noqa: E402
    EVIDENCE_DIR,
    load_all_scenarios,
    save_json,
)
from scripts.experiments.exp_before_only_perturbation import (  # noqa: E402
    _assign_timestamps,
    _build_constraints,
    _check_orthogonal_before,
    _compute_verdicts,
    _topological_order,
)
from scripts.experiments.gap_experiments import (  # noqa: E402
    _load_cpg_graph_constraints,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OUTPUT_DIR = EVIDENCE_DIR / "cres_6_expansion"
_Z_95 = 1.9599639845400545
AC_THRESHOLD = 0.5
MAB_THRESHOLD = 0.5
C2_THRESHOLD = 0.7


# ---------------------------------------------------------------------------
# Wilson CI (same as cres_6_before_analysis.py)
# ---------------------------------------------------------------------------


def wilson_ci(
    n_success: int,
    n_total: int,
    z: float = _Z_95,
) -> tuple[float, float, float]:
    """Return (point_estimate, lower, upper) Wilson CI."""
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
    """Given 0 detections, required n for Wilson-upper <= target."""
    if target_upper <= 0 or target_upper >= 1:
        raise ValueError("target_upper must be in (0, 1)")
    return int(math.ceil(z * z * (1 / target_upper - 1)))


# ---------------------------------------------------------------------------
# Graph → scenario mapping
# ---------------------------------------------------------------------------

# Graph YAML stem → canonical graph_id aliases
_STEM_TO_GRAPH_ID: dict[str, str] = {
    "ssc_sepsis_hour1": "ssc_sepsis_hour1_bundle",
    "aha_chest_pain": "aha_chest_pain_evaluation",
    "aha_heart_failure": "aha_heart_failure_2022",
    "aha_stroke": "aha_stroke_2019",
}

_GRAPH_ID_TO_STEM: dict[str, str] = {v: k for k, v in _STEM_TO_GRAPH_ID.items()}


def _resolve_graph_name(guideline_graph: str, graph_names: set[str]) -> str | None:
    """Resolve a scenario's guideline_graph to a graph constraint key."""
    if guideline_graph in graph_names:
        return guideline_graph
    # Try alias
    alias = _STEM_TO_GRAPH_ID.get(guideline_graph)
    if alias and alias in graph_names:
        return alias
    reverse = _GRAPH_ID_TO_STEM.get(guideline_graph)
    if reverse and reverse in graph_names:
        return reverse
    return None


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------


def run_expansion() -> dict[str, Any]:
    """Run scenario-level BEFORE perturbation expansion."""
    print("=" * 70)
    print("CRES-6 Expansion: Scenario-Level BEFORE Perturbation")
    print("=" * 70)

    # Step 1: Load scenarios
    print("\nStep 1: Loading scenarios...")
    scenarios = load_all_scenarios(tag_source=True)
    print(f"  Loaded {len(scenarios)} scenarios")

    # Step 2: Load graph constraints
    print("\nStep 2: Loading CPG graph constraints...")
    all_graphs = _load_cpg_graph_constraints()
    graph_names = set(all_graphs.keys())
    print(f"  Loaded {len(all_graphs)} graphs")

    # Extract all BEFORE pairs per graph
    graph_before_pairs: dict[str, list[tuple[str, str]]] = {}
    for gname, gdata in all_graphs.items():
        pairs: list[tuple[str, str]] = []
        for _node_id, prior_node_map in gdata.get("prior_actions", {}).items():
            for dependent, priors in prior_node_map.items():
                if isinstance(priors, str):
                    priors = [priors]
                for prior in priors:
                    pairs.append((prior, dependent))
        # Deduplicate
        graph_before_pairs[gname] = list(set(pairs))

    total_graph_pairs = sum(len(p) for p in graph_before_pairs.values())
    graphs_with_before = sum(1 for p in graph_before_pairs.values() if len(p) > 0)
    print(f"  {total_graph_pairs} unique BEFORE pairs across {graphs_with_before} graphs")

    # Step 3: Iterate scenarios
    print("\nStep 3: Building scenario-level perturbations...")
    solver = ConformanceDistanceSolver(CostConfig())

    pair_results: list[dict[str, Any]] = []
    n_no_graph = 0
    n_no_before = 0
    n_no_eligible = 0
    n_skipped_conformance = 0
    n_skipped_order = 0
    n_skipped_orthogonal = 0

    for sc_idx, sc in enumerate(scenarios):
        sid = sc.get("scenario_id", "")
        gg = sc.get("guideline_graph", "")
        expected_actions = set(sc.get("expected_actions", []))
        forbidden_actions = set(sc.get("forbidden_actions", []))

        if not expected_actions:
            continue

        # Resolve graph
        gname = _resolve_graph_name(gg, graph_names)
        if gname is None:
            n_no_graph += 1
            continue

        gdata = all_graphs[gname]

        # Get BEFORE pairs for this graph
        before_pairs = graph_before_pairs.get(gname, [])
        if not before_pairs:
            n_no_before += 1
            continue

        # Filter to pairs where BOTH actions are in expected_actions
        eligible = [
            (prior, dep) for prior, dep in before_pairs if prior in expected_actions and dep in expected_actions
        ]
        if not eligible:
            n_no_eligible += 1
            continue

        # Build constraints for this graph
        constraints = _build_constraints(gdata)

        # Build topological ordering of expected_actions
        ordered = _topological_order(expected_actions, gdata.get("prior_actions", {}))
        # Remove any forbidden actions
        ordered = [a for a in ordered if a not in forbidden_actions]
        if not ordered:
            continue

        # Assign timestamps
        timestamps = _assign_timestamps(ordered, gdata.get("deadlines", {}))

        # Build base trace
        base_trace: list[Action] = [
            Action(
                type=ActionType.PROCEDURE,
                action_id=action_id,
                args={},
                timestamp_minutes=timestamps[action_id],
            )
            for action_id in ordered
            if action_id in timestamps
        ]

        # Verify base trace conformance
        base_result = solver.compute(base_trace, constraints)
        if not base_result.is_conformant:
            n_skipped_conformance += 1
            continue

        trace_ids = {a.action_id for a in base_trace}

        # Test each eligible BEFORE pair
        for prior, dependent in eligible:
            if prior not in trace_ids or dependent not in trace_ids:
                continue

            # Verify order in base trace
            prior_ts = next(a.timestamp_minutes for a in base_trace if a.action_id == prior)
            dep_ts = next(a.timestamp_minutes for a in base_trace if a.action_id == dependent)
            if prior_ts >= dep_ts:
                n_skipped_order += 1
                continue

            # Perturb: swap timestamps
            perturbed_trace: list[Action] = []
            for action in base_trace:
                if action.action_id == prior:
                    perturbed_trace.append(
                        Action(
                            type=action.type,
                            action_id=action.action_id,
                            args=action.args,
                            timestamp_minutes=dep_ts,
                        )
                    )
                elif action.action_id == dependent:
                    perturbed_trace.append(
                        Action(
                            type=action.type,
                            action_id=action.action_id,
                            args=action.args,
                            timestamp_minutes=prior_ts,
                        )
                    )
                else:
                    perturbed_trace.append(action)

            perturbed_trace.sort(key=lambda a: a.timestamp_minutes)

            # Orthogonality check
            orthogonal = _check_orthogonal_before(perturbed_trace, base_trace, constraints, solver)
            if not orthogonal:
                n_skipped_orthogonal += 1

            # Score both traces
            expected_set = set(ordered)
            verdicts_base = _compute_verdicts(base_trace, expected_set, constraints, solver)
            verdicts_perturbed = _compute_verdicts(perturbed_trace, expected_set, constraints, solver)

            pert_result = solver.compute(perturbed_trace, constraints)

            pair_results.append(
                {
                    "scenario_id": sid,
                    "graph": gname,
                    "prior": prior,
                    "dependent": dependent,
                    "prior_ts_base": prior_ts,
                    "dep_ts_base": dep_ts,
                    "d_g_base": verdicts_base["d_g"],
                    "d_g_perturbed": verdicts_perturbed["d_g"],
                    "orthogonal": orthogonal,
                    "verdicts_base": {
                        k: verdicts_base[k]
                        for k in [
                            "DxEM",
                            "AC-Proxy",
                            "MAB-Proxy",
                            "C2>=0.7",
                            "CGA-Bench",
                        ]
                    },
                    "verdicts_perturbed": {
                        k: verdicts_perturbed[k]
                        for k in [
                            "DxEM",
                            "AC-Proxy",
                            "MAB-Proxy",
                            "C2>=0.7",
                            "CGA-Bench",
                        ]
                    },
                    "n_expected_actions": len(expected_actions),
                    "n_violations_perturbed": len(pert_result.violations),
                    "violation_types_perturbed": sorted({v.get("type", "") for v in pert_result.violations}),
                }
            )

        if (sc_idx + 1) % 100 == 0:
            print(f"  [{sc_idx + 1}/{len(scenarios)}] pairs so far: {len(pair_results)}")

    print(f"\n  Total scenario-pair results: {len(pair_results)}")
    print(f"  No graph match: {n_no_graph}")
    print(f"  No BEFORE pairs: {n_no_before}")
    print(f"  No eligible (both in expected): {n_no_eligible}")
    print(f"  Skipped (non-conformant base): {n_skipped_conformance}")
    print(f"  Skipped (wrong order in base): {n_skipped_order}")
    print(f"  Non-orthogonal: {n_skipped_orthogonal}")

    # Step 4: Detection rates on orthogonal pairs
    orthogonal_pairs = [p for p in pair_results if p["orthogonal"]]
    n_orthogonal = len(orthogonal_pairs)
    print(f"\n  Orthogonal pairs: {n_orthogonal}")

    evaluator_names = ["DxEM", "AC-Proxy", "MAB-Proxy", "C2>=0.7", "CGA-Bench"]
    detection_rates: dict[str, float] = {}
    detection_counts: dict[str, int] = {}

    if n_orthogonal > 0:
        for ev in evaluator_names:
            detected = sum(
                1
                for p in orthogonal_pairs
                if p["verdicts_base"].get(ev, False) and not p["verdicts_perturbed"].get(ev, False)
            )
            detection_counts[ev] = detected
            detection_rates[ev] = round(detected / n_orthogonal, 6)
    else:
        detection_rates = dict.fromkeys(evaluator_names, 0.0)
        detection_counts = dict.fromkeys(evaluator_names, 0)

    print("\n  Detection rates (orthogonal pairs):")
    for ev, rate in detection_rates.items():
        cnt = detection_counts.get(ev, 0)
        print(f"    {ev}: {rate:.4f} ({cnt}/{n_orthogonal})")

    # Step 5: Wilson CIs
    evaluator_cis: dict[str, dict[str, Any]] = {}
    for ev in evaluator_names:
        cnt = detection_counts.get(ev, 0)
        p, lo, hi = wilson_ci(cnt, n_orthogonal)
        evaluator_cis[ev] = {
            "n_detected": cnt,
            "n_total": n_orthogonal,
            "point_estimate": round(p, 6),
            "wilson_95_lower": round(lo, 6),
            "wilson_95_upper": round(hi, 6),
        }

    print("\n  Wilson 95% CIs per evaluator:")
    for ev, ci in evaluator_cis.items():
        print(
            f"    {ev}: {ci['n_detected']}/{ci['n_total']} [{ci['wilson_95_lower']:.4f}, {ci['wilson_95_upper']:.4f}]"
        )

    # Required n for target upper bounds
    target_bounds = [0.05, 0.03, 0.02, 0.01]
    n_required = {f"upper_{ub:.2f}": required_n_for_upper_bound(ub) for ub in target_bounds}

    # Scenario coverage
    scenarios_with_pairs = len(set(p["scenario_id"] for p in pair_results))
    graphs_with_pairs = len(set(p["graph"] for p in pair_results))

    output: dict[str, Any] = {
        "experiment": "CRES-6-expansion",
        "description": (
            "Scenario-level BEFORE perturbation expansion. "
            f"Extends graph-level n=17 to scenario-level n={n_orthogonal}."
        ),
        "n_scenarios_total": len(scenarios),
        "n_scenarios_with_pairs": scenarios_with_pairs,
        "n_graphs_with_pairs": graphs_with_pairs,
        "n_pair_results_total": len(pair_results),
        "n_orthogonal": n_orthogonal,
        "n_no_graph": n_no_graph,
        "n_no_before": n_no_before,
        "n_no_eligible": n_no_eligible,
        "n_skipped_conformance": n_skipped_conformance,
        "n_skipped_order": n_skipped_order,
        "n_skipped_orthogonal": n_skipped_orthogonal,
        "detection_rates": detection_rates,
        "detection_counts": detection_counts,
        "evaluator_wilson_cis": evaluator_cis,
        "n_required_for_upper_bound": n_required,
        "target_met": n_orthogonal >= 180,
        "graph_level_comparison": {
            "previous_n": 17,
            "previous_wilson_upper": 0.184,
            "expansion_n": n_orthogonal,
        },
        "pairs_sample": pair_results[:50],
    }

    return output


def write_macros(output: dict[str, Any]) -> None:
    """Write LaTeX macros for CRES-6 expansion."""
    n_orth = output["n_orthogonal"]
    cis = output["evaluator_wilson_cis"]

    lines = [
        "% CRES-6 Expansion: Scenario-Level BEFORE Perturbation",
        "% DO NOT EDIT — regenerate with exp_cres_6_expansion.py",
        f"\\newcommand{{\\cresSixExpN}}{{{n_orth}}}",
        f"\\newcommand{{\\cresSixExpNScenarios}}{{{output['n_scenarios_with_pairs']}}}",
        f"\\newcommand{{\\cresSixExpTargetMet}}{{{str(output['target_met']).lower()}}}",
    ]

    cga_ci = cis.get("CGA-Bench", {})
    if cga_ci:
        lines.append(f"\\newcommand{{\\cresSixExpCGADetectPct}}{{{cga_ci['point_estimate'] * 100:.1f}}}")
        lines.append(f"\\newcommand{{\\cresSixExpCGAUpperPct}}{{{cga_ci['wilson_95_upper'] * 100:.1f}}}")

    ac_ci = cis.get("AC-Proxy", {})
    if ac_ci:
        lines.append(f"\\newcommand{{\\cresSixExpACUpperPct}}{{{ac_ci['wilson_95_upper'] * 100:.1f}}}")

    prev = output.get("graph_level_comparison", {})
    lines.append(f"\\newcommand{{\\cresSixExpPrevN}}{{{prev.get('previous_n', 17)}}}")
    lines.append(f"\\newcommand{{\\cresSixExpPrevWilsonUpper}}{{{prev.get('previous_wilson_upper', 0.184) * 100:.1f}}}")

    tex_path = OUTPUT_DIR / "cres_6_expansion_macros.tex"
    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text("\n".join(lines) + "\n")
    print(f"  Saved macros to {tex_path}")


def main() -> int:
    """Run CRES-6 expansion experiment."""
    output = run_expansion()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUTPUT_DIR / "cres_6_expansion_results.json"
    save_json(output, out_json)

    write_macros(output)

    # Summary
    n = output["n_orthogonal"]
    target = 180
    print(f"\n{'=' * 70}")
    print("CRES-6 Expansion Complete")
    print(f"  Orthogonal pairs: {n} (target: >= {target})")
    print(f"  Target met: {output['target_met']}")
    if n > 0:
        cga = output["evaluator_wilson_cis"].get("CGA-Bench", {})
        ac = output["evaluator_wilson_cis"].get("AC-Proxy", {})
        print(
            f"  CGA-Bench detection: {cga.get('point_estimate', 0) * 100:.1f}% "
            f"[{cga.get('wilson_95_lower', 0) * 100:.1f}, "
            f"{cga.get('wilson_95_upper', 0) * 100:.1f}]"
        )
        print(
            f"  AC-Proxy detection: {ac.get('point_estimate', 0) * 100:.1f}% "
            f"[{ac.get('wilson_95_lower', 0) * 100:.1f}, "
            f"{ac.get('wilson_95_upper', 0) * 100:.1f}]"
        )
    print(f"{'=' * 70}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
