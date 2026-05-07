#!/usr/bin/env python3
"""BEFORE-only Perturbation Experiment.

Constructs synthetic conformant traces from CPG mandatory action sets and
perturbs them by swapping BEFORE-pair timestamps.  Measures which evaluators
detect the resulting BEFORE-only violation.

Problem addressed: E1's orthogonal perturbation produced 0 BEFORE-only pairs
because real conformant traces never contain both actions of a BEFORE pair.
This script works around that by building synthetic conformant traces.

Algorithm:
  1. Extract all BEFORE(prior, dependent) pairs from all 25 CPG graphs.
  2. Keep only pairs where BOTH actions are in the mandatory set.
  3. Build a synthetic conformant trace covering ALL mandatory actions with
     timestamps assigned via topological ordering (respecting every BEFORE
     constraint in the graph) and within-deadline requirements.
  4. Verify d_G = 0 via ConformanceDistanceSolver.
  5. Swap the BEFORE pair's timestamps → exactly 1 BEFORE violation.
  6. Verify orthogonality (no FORBIDDEN or WITHIN violations introduced).
  7. Score both base and perturbed traces with all evaluators.

Outputs:
  evidence_pack/exp_before_only_perturbation.json
  evidence_pack/exp_before_only_perturbation.md

Usage:
    PYTHONPATH=. python scripts/experiments/exp_before_only_perturbation.py
"""

from __future__ import annotations

from pathlib import Path
import sys

_HERE = Path(__file__).resolve()
# parents[2] = cga_bench/ (for cpg_model.* direct imports)
# parents[3] = AnonProject/ (for cga_bench.* imports inside conformance_distance.py)
sys.path.insert(0, str(_HERE.parents[3]))
sys.path.insert(0, str(_HERE.parents[2]))

from cpg_model.conformance_distance import (
    ConformanceDistanceSolver,
    ConstraintType,
    CostConfig,
    HardConstraint,
)
from cpg_model.schemas.base import Action, ActionType
from scripts.experiments._common import EVIDENCE_DIR, save_json, save_markdown
from scripts.experiments.gap_experiments import (
    _load_cpg_graph_constraints,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SEED: int = 42
AC_THRESHOLD: float = 0.5
MAB_THRESHOLD: float = 0.5
C2_THRESHOLD: float = 0.7
TIMESTAMP_START: float = 5.0
TIMESTAMP_STEP: float = 5.0


# ---------------------------------------------------------------------------
# Constraint builder
# ---------------------------------------------------------------------------


def _build_constraints(gdata: dict) -> list[HardConstraint]:
    """Build HardConstraint list from graph constraint data.

    Args:
        gdata: Graph constraint dict from _load_cpg_graph_constraints().

    Returns:
        List of HardConstraint objects covering FORBID, MUST, BEFORE, WITHIN.
    """
    constraints: list[HardConstraint] = []

    # FORBID constraints
    for node_id, forbidden_list in gdata.get("forbidden", {}).items():
        for action in forbidden_list:
            constraints.append(
                HardConstraint(
                    type=ConstraintType.FORBID,
                    actions=[action],
                    severity="CRITICAL",
                    provenance=f"{node_id}:forbidden:{action}",
                )
            )

    # MUST constraints (mandatory actions)
    for node_id, mandatory_list in gdata.get("mandatory", {}).items():
        for action in mandatory_list:
            constraints.append(
                HardConstraint(
                    type=ConstraintType.MUST,
                    actions=[action],
                    severity="HIGH",
                    provenance=f"{node_id}:must:{action}",
                )
            )

    # BEFORE constraints from prior_actions
    for node_id, prior_map in gdata.get("prior_actions", {}).items():
        for dependent, priors in prior_map.items():
            if isinstance(priors, str):
                priors = [priors]
            for prior in priors:
                constraints.append(
                    HardConstraint(
                        type=ConstraintType.BEFORE,
                        actions=[prior, dependent],
                        severity="HIGH",
                        provenance=f"{node_id}:before:{prior}->{dependent}",
                    )
                )

    # WITHIN constraints from deadlines
    for node_id, dl_map in gdata.get("deadlines", {}).items():
        for action, deadline in dl_map.items():
            constraints.append(
                HardConstraint(
                    type=ConstraintType.WITHIN,
                    actions=[action],
                    deadline=float(deadline),
                    severity="CRITICAL",
                    provenance=f"{node_id}:within:{action}:{deadline}m",
                )
            )

    return constraints


# ---------------------------------------------------------------------------
# Topological ordering helpers
# ---------------------------------------------------------------------------


def _topological_order(
    mandatory: set[str],
    prior_map: dict[str, dict],
) -> list[str]:
    """Return mandatory actions in topological order respecting BEFORE constraints.

    Uses Kahn's algorithm.  Actions not involved in any BEFORE constraint are
    ordered lexicographically for determinism.

    Args:
        mandatory: Set of mandatory action IDs.
        prior_map: {node_id: {dependent: priors_list_or_str}}.

    Returns:
        Ordered list of action IDs (all elements of `mandatory`).
    """
    # Build adjacency: prior -> set of dependents
    edges: dict[str, set[str]] = {a: set() for a in mandatory}
    in_degree: dict[str, int] = dict.fromkeys(mandatory, 0)

    for prior_node_map in prior_map.values():
        for dependent, priors in prior_node_map.items():
            if dependent not in mandatory:
                continue
            if isinstance(priors, str):
                priors = [priors]
            for prior in priors:
                if prior not in mandatory:
                    continue
                if prior not in edges:
                    edges[prior] = set()
                if dependent not in edges[prior]:
                    edges[prior].add(dependent)
                    in_degree[dependent] = in_degree.get(dependent, 0) + 1

    # Kahn's BFS (stable: use sorted queue for determinism)
    queue: list[str] = sorted(a for a in mandatory if in_degree.get(a, 0) == 0)
    order: list[str] = []

    while queue:
        node = queue.pop(0)
        order.append(node)
        for successor in sorted(edges.get(node, set())):
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                queue.append(successor)

    # If cycle detected (some nodes not placed), append remaining in sorted order
    placed = set(order)
    for a in sorted(mandatory):
        if a not in placed:
            order.append(a)

    return order


def _assign_timestamps(
    ordered_actions: list[str],
    deadline_map: dict[str, dict],
) -> dict[str, float]:
    """Assign monotonically increasing timestamps respecting WITHIN deadlines.

    Uses a scheduling approach: compute each action's latest-start time (LST)
    from its deadline, then assign timestamps from t=1 with a step of 1 minute.
    If action i has a deadline d, it must be placed at most at d-0.5 minutes.
    We topologically ordered the actions so BEFORE constraints are satisfied by
    construction; this function only ensures WITHIN compliance.

    If the tightest deadline is too tight for the topological position of its
    action (i.e., there are too many predecessors to fit before the deadline),
    the caller will detect non-conformance via ConformanceDistanceSolver and
    skip the pair.

    Args:
        ordered_actions: Actions in topological order.
        deadline_map: {node_id: {action: deadline_minutes}}.

    Returns:
        {action_id: timestamp_minutes}, monotonically increasing.
    """
    if not ordered_actions:
        return {}

    # Flatten: action -> tightest deadline across all nodes
    action_deadline: dict[str, float] = {}
    for dl_node_map in deadline_map.values():
        for action, deadline in dl_node_map.items():
            dl_f = float(deadline)
            if action not in action_deadline or dl_f < action_deadline[action]:
                action_deadline[action] = dl_f

    # Use step = 1 minute so many actions fit within tight deadlines
    step = 1.0
    timestamps: dict[str, float] = {}
    current_ts = 1.0

    for action in ordered_actions:
        deadline = action_deadline.get(action)
        ts = current_ts
        if deadline is not None and ts >= deadline:
            # Place it just before the deadline (may break monotonicity if
            # current_ts is already >= deadline — caller handles via solver check)
            ts = max(0.5, deadline - 0.5)
        timestamps[action] = ts
        # Next action gets at least step after this one (always monotone)
        current_ts = max(current_ts + step, ts + step)

    return timestamps


# ---------------------------------------------------------------------------
# Evaluator helpers
# ---------------------------------------------------------------------------


def _action_coverage(agent: set[str], expected: set[str]) -> float:
    """Coverage = |agent & expected| / |expected|."""
    if not expected:
        return 1.0
    return len(agent & expected) / len(expected)


def _mab_f1(agent: set[str], expected: set[str]) -> float:
    """Token-level F1 between action sets."""
    if not expected:
        return 0.0
    prec = len(agent & expected) / len(agent) if agent else 0.0
    rec = len(agent & expected) / len(expected)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def _compute_verdicts(
    trace: list[Action],
    expected_actions: set[str],
    constraints: list[HardConstraint],
    solver: ConformanceDistanceSolver,
) -> dict:
    """Compute all evaluator verdicts on a trace.

    Args:
        trace: List of Action objects.
        expected_actions: Mandatory action IDs (ground truth).
        constraints: Hard constraints for CGA-Bench scoring.
        solver: Conformance distance solver instance.

    Returns:
        Dict with verdict booleans and raw scores.
    """
    agent_actions = {a.action_id for a in trace}

    ac_cov = _action_coverage(agent_actions, expected_actions)
    f1 = _mab_f1(agent_actions, expected_actions)
    omissions = len(expected_actions - agent_actions)
    c2 = max(0.0, 1.0 - omissions / max(len(expected_actions), 1))

    result = solver.compute(trace, constraints)

    return {
        "DxEM": True,  # terminal output unchanged in both base and perturbed
        "AC-Proxy": ac_cov >= AC_THRESHOLD,
        "MAB-Proxy": f1 >= MAB_THRESHOLD,
        "C2>=0.7": c2 >= C2_THRESHOLD,
        "CGA-Bench": result.is_conformant,
        "ac_coverage": round(ac_cov, 4),
        "mab_f1": round(f1, 4),
        "c2_score": round(c2, 4),
        "d_g": round(result.distance, 4),
        "n_violations": len(result.violations),
        "violation_types": sorted({v.get("type", "") for v in result.violations}),
    }


# ---------------------------------------------------------------------------
# Orthogonality check
# ---------------------------------------------------------------------------


def _check_orthogonal_before(
    perturbed_trace: list[Action],
    base_trace: list[Action],
    constraints: list[HardConstraint],
    solver: ConformanceDistanceSolver,
) -> bool:
    """Verify the perturbation introduces ONLY BEFORE violations.

    Checks that the perturbed trace has no FORBID or WITHIN violations,
    and that the action multiset is identical to the base trace (so AC-Proxy,
    MAB, C2 see no change).

    Args:
        perturbed_trace: Trace after timestamp swap.
        base_trace: Original conformant trace.
        constraints: Graph constraints.
        solver: Conformance distance solver.

    Returns:
        True if violation is BEFORE-only and action multisets match.
    """
    # Multiset check: same action IDs
    base_ids = sorted(a.action_id for a in base_trace)
    pert_ids = sorted(a.action_id for a in perturbed_trace)
    if base_ids != pert_ids:
        return False

    # Violation type check via solver
    result = solver.compute(perturbed_trace, constraints)
    if result.is_conformant:
        return False  # No violation at all

    viol_types = {v.get("type", "") for v in result.violations}
    unexpected = viol_types - {"BEFORE"}
    return len(unexpected) == 0


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------


def run_experiment() -> dict:
    """Run the BEFORE-only perturbation experiment.

    Returns:
        Results dict for JSON serialization.
    """
    print("=" * 70)
    print("BEFORE-ONLY PERTURBATION — Synthetic Conformant Traces")
    print("=" * 70)

    all_graphs = _load_cpg_graph_constraints()
    solver = ConformanceDistanceSolver(CostConfig())

    # -----------------------------------------------------------------------
    # Step 1: Extract BEFORE pairs from all graphs
    # -----------------------------------------------------------------------
    print("\nStep 1: Extracting BEFORE pairs from all CPG graphs...")

    all_pairs: list[tuple[str, str, str]] = []  # (prior, dependent, graph_name)
    graphs_with_before: set[str] = set()

    for graph_name, gdata in sorted(all_graphs.items()):
        for node_id, prior_node_map in gdata.get("prior_actions", {}).items():
            for dependent, priors in prior_node_map.items():
                if isinstance(priors, str):
                    priors = [priors]
                for prior in priors:
                    all_pairs.append((prior, dependent, graph_name))
                    graphs_with_before.add(graph_name)

    print(f"  Found {len(all_pairs)} BEFORE pairs across {len(graphs_with_before)} graphs")

    # -----------------------------------------------------------------------
    # Step 2: Filter to pairs where both actions are mandatory
    # -----------------------------------------------------------------------
    print("\nStep 2: Filtering to pairs with both actions in mandatory set...")

    eligible_pairs: list[tuple[str, str, str]] = []
    for prior, dependent, graph_name in all_pairs:
        gdata = all_graphs[graph_name]
        mandatory = gdata.get("all_mandatory_set", set())
        if prior in mandatory and dependent in mandatory:
            eligible_pairs.append((prior, dependent, graph_name))

    # Deduplicate (same prior/dependent/graph may appear from multiple nodes)
    seen_pairs: set[tuple[str, str, str]] = set()
    unique_eligible: list[tuple[str, str, str]] = []
    for pair in eligible_pairs:
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            unique_eligible.append(pair)

    print(f"  Eligible (both mandatory) pairs: {len(unique_eligible)}")

    # -----------------------------------------------------------------------
    # Step 3-6: Build synthetic trace, verify d_G=0, perturb, check orthogonal
    # -----------------------------------------------------------------------
    print("\nSteps 3-6: Building traces, perturbing, checking orthogonality...")

    pair_results: list[dict] = []
    n_skipped_conformance = 0
    n_skipped_orthogonal = 0

    for prior, dependent, graph_name in unique_eligible:
        gdata = all_graphs[graph_name]
        mandatory = gdata.get("all_mandatory_set", set())
        forbidden = gdata.get("all_forbidden_set", set())
        constraints = _build_constraints(gdata)

        # Build topological ordering of mandatory actions
        ordered = _topological_order(mandatory, gdata.get("prior_actions", {}))

        # Exclude any mandatory actions that are also forbidden (edge case)
        ordered = [a for a in ordered if a not in forbidden]
        if not ordered:
            continue

        # Assign timestamps
        timestamps = _assign_timestamps(ordered, gdata.get("deadlines", {}))

        # Build base trace as Action objects
        base_trace: list[Action] = [
            Action(
                type=ActionType.PROCEDURE,
                action_id=action_id,
                args={},
                timestamp_minutes=timestamps[action_id],
            )
            for action_id in ordered
        ]

        # Step 4: Verify d_G = 0
        base_result = solver.compute(base_trace, constraints)
        if not base_result.is_conformant:
            n_skipped_conformance += 1
            continue

        # Check that both prior and dependent are in the trace
        trace_ids = {a.action_id for a in base_trace}
        if prior not in trace_ids or dependent not in trace_ids:
            continue

        # Check that prior actually comes before dependent in base trace
        prior_ts = next(a.timestamp_minutes for a in base_trace if a.action_id == prior)
        dep_ts = next(a.timestamp_minutes for a in base_trace if a.action_id == dependent)
        if prior_ts >= dep_ts:
            # BEFORE already violated in base trace — skip
            n_skipped_conformance += 1
            continue

        # Step 5: Perturb — swap timestamps of the BEFORE pair
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

        # Re-sort by timestamp (as in _perturb_before from exp_orthogonal_perturbation)
        perturbed_trace.sort(key=lambda a: a.timestamp_minutes)

        # Step 6: Verify orthogonality
        orthogonal = _check_orthogonal_before(perturbed_trace, base_trace, constraints, solver)
        if not orthogonal:
            n_skipped_orthogonal += 1

        # Step 7: Score both traces
        expected_actions = set(ordered)  # all mandatory = expected
        verdicts_base = _compute_verdicts(base_trace, expected_actions, constraints, solver)
        verdicts_perturbed = _compute_verdicts(perturbed_trace, expected_actions, constraints, solver)

        pert_result = solver.compute(perturbed_trace, constraints)

        pair_results.append(
            {
                "graph": graph_name,
                "prior": prior,
                "dependent": dependent,
                "prior_ts_base": prior_ts,
                "dep_ts_base": dep_ts,
                "d_g_base": verdicts_base["d_g"],
                "d_g_perturbed": verdicts_perturbed["d_g"],
                "orthogonal": orthogonal,
                "verdicts_base": {
                    k: verdicts_base[k] for k in ["DxEM", "AC-Proxy", "MAB-Proxy", "C2>=0.7", "CGA-Bench"]
                },
                "verdicts_perturbed": {
                    k: verdicts_perturbed[k] for k in ["DxEM", "AC-Proxy", "MAB-Proxy", "C2>=0.7", "CGA-Bench"]
                },
                "n_mandatory_actions": len(ordered),
                "n_violations_perturbed": len(pert_result.violations),
                "violation_types_perturbed": sorted({v.get("type", "") for v in pert_result.violations}),
            }
        )

    print(f"  Total pair results: {len(pair_results)}")
    print(f"  Skipped (non-conformant base): {n_skipped_conformance}")
    print(f"  Non-orthogonal (kept but flagged): {n_skipped_orthogonal}")

    # -----------------------------------------------------------------------
    # Compute detection rates (orthogonal pairs only)
    # -----------------------------------------------------------------------
    orthogonal_pairs = [p for p in pair_results if p["orthogonal"]]
    n_orthogonal = len(orthogonal_pairs)
    print(f"\n  Orthogonal pairs: {n_orthogonal}")

    evaluator_names = ["DxEM", "AC-Proxy", "MAB-Proxy", "C2>=0.7", "CGA-Bench"]
    detection_rates: dict[str, float] = {}

    if n_orthogonal > 0:
        for ev in evaluator_names:
            # Detection = base passes AND perturbed fails
            detected = sum(
                1
                for p in orthogonal_pairs
                if p["verdicts_base"].get(ev, False) and not p["verdicts_perturbed"].get(ev, False)
            )
            detection_rates[ev] = round(detected / n_orthogonal, 4)
    else:
        detection_rates = dict.fromkeys(evaluator_names, 0.0)

    print("\n  Detection rates (orthogonal pairs):")
    for ev, rate in detection_rates.items():
        print(f"    {ev}: {rate:.4f}")

    # -----------------------------------------------------------------------
    # Build output
    # -----------------------------------------------------------------------
    output = {
        "n_graphs_with_before": len(graphs_with_before),
        "n_eligible_pairs": len(unique_eligible),
        "n_pairs_generated": len(pair_results),
        "n_orthogonal": n_orthogonal,
        "n_skipped_conformance": n_skipped_conformance,
        "n_skipped_orthogonal": n_skipped_orthogonal,
        "detection_rates": detection_rates,
        "pairs": pair_results,
    }

    return output


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _build_markdown(output: dict) -> str:
    """Build markdown summary report.

    Args:
        output: Experiment results dict.

    Returns:
        Formatted markdown string.
    """
    lines: list[str] = [
        "# BEFORE-Only Perturbation Experiment",
        "",
        "## Summary",
        "",
        f"- Graphs with BEFORE constraints: **{output['n_graphs_with_before']}**",
        f"- Eligible pairs (both actions mandatory): **{output['n_eligible_pairs']}**",
        f"- Pairs generated: **{output['n_pairs_generated']}**",
        f"- Orthogonal pairs (BEFORE-only violation): **{output['n_orthogonal']}**",
        "",
        "## Detection Rates (orthogonal pairs only)",
        "",
        "| Evaluator | Detection Rate |",
        "|-----------|---------------|",
    ]

    for ev, rate in output["detection_rates"].items():
        lines.append(f"| {ev} | {rate:.4f} |")

    lines += [
        "",
        "## Interpretation",
        "",
        "Expected result: AC-Proxy, MAB-Proxy, and C2 should show **0.0** detection",
        "(action multiset unchanged by timestamp swap).  CGA-Bench should show **1.0**",
        "(BEFORE violation detected via conformance distance).",
        "",
        "## Sample Pairs",
        "",
        "| Graph | Prior | Dependent | d_G base | d_G perturbed | Orthogonal |",
        "|-------|-------|-----------|----------|---------------|------------|",
    ]

    for pair in output["pairs"][:20]:
        lines.append(
            f"| {pair['graph']} | {pair['prior']} | {pair['dependent']} "
            f"| {pair['d_g_base']:.1f} | {pair['d_g_perturbed']:.1f} "
            f"| {'Yes' if pair['orthogonal'] else 'No'} |"
        )

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Running BEFORE-only perturbation experiment...")

    output = run_experiment()

    out_json = EVIDENCE_DIR / "exp_before_only_perturbation.json"
    out_md = EVIDENCE_DIR / "exp_before_only_perturbation.md"

    save_json(output, out_json)
    save_markdown(_build_markdown(output), out_md)

    print("\nDone.")
    print(f"  JSON: {out_json}")
    print(f"  MD:   {out_md}")
