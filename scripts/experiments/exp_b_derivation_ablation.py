#!/usr/bin/env python3
"""EXP-B: Constraint Derivation Engine Ablation Study.

Quantifies each Derivation Engine component's contribution and compares
against alternative approaches (unconditional, no-type, random-patient,
baseline-manual).

Outputs:
  evidence_pack/exp_b_derivation_ablation.json
  evidence_pack/exp_b_derivation_ablation.md
  evidence_pack/figures/exp_b_ablation_bars.png
  evidence_pack/figures/exp_b_scalability.png
  evidence_pack/tables/derivation_ablation.tex

Usage:
    PYTHONPATH=. python scripts/experiments/exp_b_derivation_ablation.py
"""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cpg_model.constraint_derivation import (
    ConstraintDerivationEngine,
    DerivedConstraint,
    DerivedConstraintSet,
    load_graph,
)
import matplotlib
from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    TABLES_DIR,
    fmt_p,
    load_all_graphs,
    load_all_scenarios,
    resolve_graph_path,
    save_figure,
    save_json,
    save_latex_table,
    save_markdown,
    setup_matplotlib,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ============================================================
# Ablation variants (subclasses, never modify original)
# ============================================================


class AblationUnconditional(ConstraintDerivationEngine):
    """Ablation A: Activate ALL conditional rules regardless of patient."""

    def _evaluate_condition(self, condition: str, patient: dict[str, Any]) -> bool:
        """Always returns True — unconditionally activates every rule."""
        return True


class AblationNoTypeDistinction(ConstraintDerivationEngine):
    """Ablation B: Map all constraints to REQUIRED (no type distinction)."""

    def _process_conditional_rules(
        self,
        node_id: str,
        node: dict[str, Any],
        graph_id: str,
        patient: dict[str, Any],
        result: DerivedConstraintSet,
    ) -> None:
        """Override to force all conditional constraints to REQUIRED."""
        for rule in node.get("conditional_rules", []):
            result.total_rules_evaluated += 1
            condition = rule.get("condition", "")

            if self._evaluate_condition(condition, patient):
                result.total_rules_triggered += 1
                effect = rule.get("effect", {})
                condition_met_str = self._format_condition_met(condition, patient)

                result.add(
                    DerivedConstraint(
                        constraint_type="REQUIRED",
                        actions=effect.get("actions", []),
                        provenance=(
                            f"graph:{graph_id}:node:{node_id}"
                            f":rule:{rule.get('rule_id', 'unknown')}"
                        ),
                        evidence=rule.get("evidence", ""),
                        severity=rule.get("severity", "HIGH"),
                        description=rule.get("description", ""),
                        condition_met=condition_met_str,
                        is_conditional=True,
                    )
                )


class AblationRandomPatient(ConstraintDerivationEngine):
    """Ablation C: Use random patient context for derivation."""

    pass  # We'll generate random patients externally and pass them in


# ============================================================
# Graph complexity metrics
# ============================================================


def compute_graph_complexity(graph: dict[str, Any]) -> dict[str, Any]:
    """Compute complexity metrics for a CPG graph.

    Returns:
        Dict with node_count, edge_count, conditional_rules_count, max_depth.
    """
    nodes = graph.get("nodes", {})
    node_count = len(nodes)

    edge_count = 0
    conditional_rules_count = 0
    for node in nodes.values():
        transitions = node.get("transitions", [])
        if isinstance(transitions, (list, dict)):
            edge_count += len(transitions)
        conditional_rules_count += len(node.get("conditional_rules", []))

    # BFS max depth from entry node
    entry = graph.get("entry_node", "")
    max_depth = _bfs_max_depth(nodes, entry)

    return {
        "node_count": node_count,
        "edge_count": edge_count,
        "conditional_rules_count": conditional_rules_count,
        "max_depth": max_depth,
    }


def _bfs_max_depth(nodes: dict[str, Any], start: str) -> int:
    """BFS from start node, return max depth."""
    if not start or start not in nodes:
        return 0

    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(start, 0)]
    max_d = 0

    while queue:
        nid, depth = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        max_d = max(max_d, depth)

        node = nodes.get(nid, {})
        transitions = node.get("transitions", [])
        targets: list[str] = []
        if isinstance(transitions, list):
            for t in transitions:
                if isinstance(t, dict):
                    tgt = t.get("target") or t.get("target_node", "")
                    if tgt:
                        targets.append(tgt)
                elif isinstance(t, str):
                    targets.append(t)
        elif isinstance(transitions, dict):
            for val in transitions.values():
                if isinstance(val, str):
                    targets.append(val)
                elif isinstance(val, dict):
                    tgt = val.get("target") or val.get("target_node", "")
                    if tgt:
                        targets.append(tgt)

        for tgt in targets:
            if tgt not in visited:
                queue.append((tgt, depth + 1))

    return max_d


# ============================================================
# Ablation 1: Component removal experiments
# ============================================================


def run_ablation_a(
    graphs: dict[str, dict[str, Any]],
    auto_scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    """Ablation A: Unconditional activation — all rules fire.

    Measures constraint overgeneration vs baseline.
    """
    print("\n--- Ablation A: Unconditional activation ---")
    engine_normal = ConstraintDerivationEngine()
    engine_ablated = AblationUnconditional()

    baseline_total = 0
    ablated_total = 0
    per_graph: list[dict[str, Any]] = []

    graphs_seen: set[str] = set()
    for sc in auto_scenarios:
        gid = sc.get("_canonical_graph_id", "")
        if gid in graphs_seen or gid not in graphs:
            continue
        graphs_seen.add(gid)

        graph = graphs[gid]
        patient = sc.get("patient", {})

        r_normal = engine_normal.derive(graph, patient, sc.get("scenario_id", ""))
        r_ablated = engine_ablated.derive(graph, patient, sc.get("scenario_id", ""))

        n_normal = len(r_normal.all_constraints())
        n_ablated = len(r_ablated.all_constraints())
        baseline_total += n_normal
        ablated_total += n_ablated

        per_graph.append({
            "graph_id": gid,
            "baseline_constraints": n_normal,
            "ablated_constraints": n_ablated,
            "overgeneration": n_ablated - n_normal,
            "overgeneration_pct": (
                (n_ablated - n_normal) / max(n_normal, 1) * 100
            ),
        })

    overgen_rate = (ablated_total - baseline_total) / max(baseline_total, 1) * 100
    print(f"  Baseline total: {baseline_total}")
    print(f"  Ablated total:  {ablated_total}")
    print(f"  Overgeneration: {overgen_rate:.1f}%")

    return {
        "description": "Unconditional rule activation (all rules fire)",
        "baseline_total": baseline_total,
        "ablated_total": ablated_total,
        "overgeneration_rate_pct": round(overgen_rate, 2),
        "per_graph": per_graph,
    }


def run_ablation_b(
    graphs: dict[str, dict[str, Any]],
    auto_scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    """Ablation B: No type distinction — all constraints become REQUIRED.

    Measures scenario differentiation loss.
    """
    print("\n--- Ablation B: No type distinction ---")
    engine_normal = ConstraintDerivationEngine()
    engine_ablated = AblationNoTypeDistinction()

    normal_trap_diff = 0
    ablated_trap_diff = 0
    n_compared = 0

    for sc in auto_scenarios:
        gid = sc.get("_canonical_graph_id", "")
        if gid not in graphs:
            continue
        graph = graphs[gid]
        patient = sc.get("patient", {})

        r_normal = engine_normal.derive(graph, patient, sc.get("scenario_id", ""))
        r_ablated = engine_ablated.derive(graph, patient, sc.get("scenario_id", ""))

        n_types_normal = len({c.constraint_type for c in r_normal.all_constraints()})
        n_types_ablated = len({c.constraint_type for c in r_ablated.all_constraints()})

        normal_trap_diff += n_types_normal
        ablated_trap_diff += n_types_ablated
        n_compared += 1

    avg_types_normal = normal_trap_diff / max(n_compared, 1)
    avg_types_ablated = ablated_trap_diff / max(n_compared, 1)
    loss_pct = (1 - avg_types_ablated / max(avg_types_normal, 1)) * 100

    # Count how many scenarios lose forbidden constraints
    n_lost_forbidden = 0
    for sc in auto_scenarios:
        gid = sc.get("_canonical_graph_id", "")
        if gid not in graphs:
            continue
        graph = graphs[gid]
        patient = sc.get("patient", {})
        r_normal = engine_normal.derive(graph, patient, sc.get("scenario_id", ""))
        if r_normal.forbidden:
            n_lost_forbidden += 1

    print(f"  Avg constraint types (normal): {avg_types_normal:.2f}")
    print(f"  Avg constraint types (ablated): {avg_types_ablated:.2f}")
    print(f"  Differentiation loss: {loss_pct:.1f}%")
    print(f"  Scenarios losing FORBIDDEN: {n_lost_forbidden}")

    return {
        "description": "All constraints mapped to REQUIRED (no type distinction)",
        "avg_types_normal": round(avg_types_normal, 3),
        "avg_types_ablated": round(avg_types_ablated, 3),
        "differentiation_loss_pct": round(loss_pct, 2),
        "scenarios_losing_forbidden": n_lost_forbidden,
        "n_compared": n_compared,
    }


def run_ablation_c(
    graphs: dict[str, dict[str, Any]],
    auto_scenarios: list[dict[str, Any]],
    n_random: int = 50,
) -> dict[str, Any]:
    """Ablation C: Random patient context instead of PatientGenerator.

    Measures constraint activation accuracy (FP/FN rate).
    """
    print("\n--- Ablation C: Random patient context ---")
    rng = np.random.default_rng(42)
    engine = ConstraintDerivationEngine()

    total_fp = 0
    total_fn = 0
    total_constraints_gold = 0
    total_constraints_random = 0
    n_evaluated = 0

    for sc in auto_scenarios[:200]:  # Cap to avoid long runtime
        gid = sc.get("_canonical_graph_id", "")
        if gid not in graphs:
            continue
        graph = graphs[gid]
        patient_gold = sc.get("patient", {})

        # Gold derivation
        r_gold = engine.derive(graph, patient_gold, sc.get("scenario_id", ""))
        gold_set = {
            (c.constraint_type, tuple(c.actions))
            for c in r_gold.all_constraints()
            if c.is_conditional
        }

        # Random patient
        random_patient = _make_random_patient(patient_gold, rng)
        r_random = engine.derive(graph, random_patient, "random")
        random_set = {
            (c.constraint_type, tuple(c.actions))
            for c in r_random.all_constraints()
            if c.is_conditional
        }

        fp = len(random_set - gold_set)
        fn = len(gold_set - random_set)
        total_fp += fp
        total_fn += fn
        total_constraints_gold += len(gold_set)
        total_constraints_random += len(random_set)
        n_evaluated += 1

    fp_rate = total_fp / max(total_constraints_random, 1) * 100
    fn_rate = total_fn / max(total_constraints_gold, 1) * 100

    print(f"  Gold conditional constraints: {total_constraints_gold}")
    print(f"  Random conditional constraints: {total_constraints_random}")
    print(f"  FP rate: {fp_rate:.1f}%")
    print(f"  FN rate: {fn_rate:.1f}%")

    return {
        "description": "Random patient context replaces PatientGenerator",
        "n_evaluated": n_evaluated,
        "total_constraints_gold": total_constraints_gold,
        "total_constraints_random": total_constraints_random,
        "total_fp": total_fp,
        "total_fn": total_fn,
        "fp_rate_pct": round(fp_rate, 2),
        "fn_rate_pct": round(fn_rate, 2),
    }


def _make_random_patient(template: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    """Generate a random patient by perturbing the template."""
    p = copy.deepcopy(template)

    # Randomise age
    p["age"] = int(rng.integers(18, 90))

    # Randomise sex
    p["sex"] = rng.choice(["M", "F"])

    # Randomise labs if present
    if "labs" in p and isinstance(p["labs"], dict):
        for key in p["labs"]:
            if isinstance(p["labs"][key], (int, float)):
                p["labs"][key] = round(float(rng.uniform(0.5, 15.0)), 1)

    # Randomise vitals if present
    if "vitals" in p and isinstance(p["vitals"], dict):
        vitals_ranges = {
            "hr": (50, 130),
            "sbp": (80, 200),
            "dbp": (40, 120),
            "rr": (10, 35),
            "spo2": (85, 100),
            "temp": (35.0, 40.0),
            "map_mmhg": (50, 140),
        }
        for key, (lo, hi) in vitals_ranges.items():
            if key in p["vitals"]:
                p["vitals"][key] = round(float(rng.uniform(lo, hi)), 1)

    # Randomise comorbidities
    all_comorbidities = [
        "hypertension", "diabetes", "ckd", "chf", "copd", "pregnancy",
        "cocaine_use", "atrial_fibrillation", "cardiogenic_shock",
    ]
    n_comorb = int(rng.integers(0, 4))
    p["comorbidities"] = list(rng.choice(all_comorbidities, size=n_comorb, replace=False))

    # Clear allergies randomly
    if rng.random() > 0.3:
        p["allergies"] = []

    return p


# ============================================================
# Baseline-Manual comparison
# ============================================================


def run_baseline_manual(
    graphs: dict[str, dict[str, Any]],
    manual_scenarios: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare engine-derived constraints vs manual expected/forbidden.

    Computes precision/recall of engine output vs manual ground truth.
    """
    print("\n--- Baseline-Manual comparison ---")
    engine = ConstraintDerivationEngine()

    precisions: list[float] = []
    recalls: list[float] = []
    per_scenario: list[dict[str, Any]] = []

    for sc in manual_scenarios:
        graph_path = resolve_graph_path(sc.get("guideline_graph", ""))
        if graph_path is None:
            continue

        graph = load_graph(graph_path)
        patient = sc.get("patient", {})
        if not patient:
            continue

        r = engine.derive(graph, patient, sc.get("scenario_id", ""))

        # Manual ground truth
        manual_expected = set(sc.get("expected_actions", []))
        manual_forbidden = set(sc.get("forbidden_actions", []))
        manual_all = manual_expected | manual_forbidden

        if not manual_all:
            continue

        # Engine output
        engine_expected = {a for c in r.expected for a in c.actions}
        engine_forbidden = {a for c in r.forbidden for a in c.actions}
        engine_all = engine_expected | engine_forbidden

        tp = len(engine_all & manual_all)
        fp = len(engine_all - manual_all)
        fn = len(manual_all - engine_all)

        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)

        precisions.append(prec)
        recalls.append(rec)

        per_scenario.append({
            "scenario_id": sc.get("scenario_id", ""),
            "manual_actions": len(manual_all),
            "engine_actions": len(engine_all),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(prec, 3),
            "recall": round(rec, 3),
        })

    avg_prec = float(np.mean(precisions)) if precisions else 0.0
    avg_rec = float(np.mean(recalls)) if recalls else 0.0

    print(f"  Evaluated {len(precisions)} scenarios with ground truth")
    print(f"  Avg precision: {avg_prec:.3f}")
    print(f"  Avg recall:    {avg_rec:.3f}")

    return {
        "description": "Engine vs manual expected/forbidden actions",
        "n_evaluated": len(precisions),
        "avg_precision": round(avg_prec, 3),
        "avg_recall": round(avg_rec, 3),
        "std_precision": round(float(np.std(precisions)), 3) if precisions else 0.0,
        "std_recall": round(float(np.std(recalls)), 3) if recalls else 0.0,
        "per_scenario": per_scenario,
    }


# ============================================================
# Scalability analysis
# ============================================================


def run_scalability(
    graphs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Per-graph complexity vs constraint count and derivation time."""
    print("\n--- Scalability analysis ---")
    engine = ConstraintDerivationEngine()

    per_graph: list[dict[str, Any]] = []

    for gid, graph in sorted(graphs.items()):
        complexity = compute_graph_complexity(graph)

        # Use a representative default patient
        patient = {"age": 55, "sex": "M", "labs": {}, "vitals": {
            "hr": 80, "sbp": 130, "dbp": 80, "rr": 16, "spo2": 98,
            "temp": 37.0, "map_mmhg": 97,
        }, "comorbidities": [], "allergies": [], "medications": [],
            "history": [], "presentation": {}}

        # Time the derivation (average of 3 runs)
        times: list[float] = []
        constraint_count = 0
        for _ in range(3):
            t0 = time.perf_counter()
            r = engine.derive(graph, patient, f"scalability_{gid}")
            t1 = time.perf_counter()
            times.append(t1 - t0)
            constraint_count = len(r.all_constraints())

        avg_time_ms = float(np.mean(times)) * 1000

        per_graph.append({
            "graph_id": gid,
            **complexity,
            "constraint_count": constraint_count,
            "derivation_time_ms": round(avg_time_ms, 2),
        })

    print(f"  Analyzed {len(per_graph)} graphs")
    return {
        "description": "Graph complexity vs constraint derivation metrics",
        "per_graph": per_graph,
    }


# ============================================================
# Figures
# ============================================================


def plot_ablation_bars(
    ablation_a: dict[str, Any],
    ablation_b: dict[str, Any],
    ablation_c: dict[str, Any],
    baseline_manual: dict[str, Any],
) -> plt.Figure:
    """Bar chart comparing ablation results."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left: overgeneration / loss rates
    labels = ["A: Unconditional\n(overgen %)", "B: No Type\n(diff loss %)",
              "C: Random Patient\n(FP %)", "C: Random Patient\n(FN %)"]
    values = [
        ablation_a["overgeneration_rate_pct"],
        ablation_b["differentiation_loss_pct"],
        ablation_c["fp_rate_pct"],
        ablation_c["fn_rate_pct"],
    ]
    colors = ["#e74c3c", "#f39c12", "#3498db", "#2ecc71"]

    ax = axes[0]
    bars = ax.bar(range(len(labels)), values, color=colors, edgecolor="black", linewidth=0.5)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Rate (%)")
    ax.set_title("Ablation Impact (Higher = More Degradation)")
    for bar, val in zip(bars, values, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=9)

    # Right: baseline-manual precision/recall
    ax2 = axes[1]
    metrics = ["Precision", "Recall"]
    vals = [baseline_manual["avg_precision"], baseline_manual["avg_recall"]]
    stds = [baseline_manual["std_precision"], baseline_manual["std_recall"]]
    bars2 = ax2.bar(metrics, vals, yerr=stds, color=["#9b59b6", "#1abc9c"],
                    edgecolor="black", linewidth=0.5, capsize=5)
    ax2.set_ylim(0, 1.1)
    ax2.set_ylabel("Score")
    ax2.set_title("Engine vs Manual Ground Truth")
    for bar, val in zip(bars2, vals, strict=True):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                 f"{val:.3f}", ha="center", va="bottom", fontsize=10)

    fig.tight_layout()
    return fig


def plot_scalability(scalability: dict[str, Any]) -> plt.Figure:
    """Scatter plots: graph complexity vs constraint count & time."""
    per_graph = scalability["per_graph"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    nodes = [g["node_count"] for g in per_graph]
    rules = [g["conditional_rules_count"] for g in per_graph]
    constraints = [g["constraint_count"] for g in per_graph]
    times = [g["derivation_time_ms"] for g in per_graph]
    labels = [g["graph_id"][:12] for g in per_graph]

    # Left: rules vs constraints
    ax = axes[0]
    ax.scatter(rules, constraints, c=nodes, cmap="viridis", s=60, edgecolors="black",
               linewidth=0.5, zorder=3)
    ax.set_xlabel("Conditional Rules")
    ax.set_ylabel("Derived Constraints")
    ax.set_title("Graph Complexity vs Constraints")

    # Annotate outliers
    for i, lbl in enumerate(labels):
        if constraints[i] > np.mean(constraints) + np.std(constraints):
            ax.annotate(lbl, (rules[i], constraints[i]), fontsize=7,
                        xytext=(5, 5), textcoords="offset points")

    # Correlation
    if len(rules) > 2:
        r, p = stats.pearsonr(rules, constraints)
        ax.text(0.05, 0.95, f"r={r:.3f}, p={fmt_p(p)}", transform=ax.transAxes,
                fontsize=9, va="top")

    # Right: rules vs time
    ax2 = axes[1]
    ax2.scatter(rules, times, c="steelblue", s=60, edgecolors="black",
                linewidth=0.5, zorder=3)
    ax2.set_xlabel("Conditional Rules")
    ax2.set_ylabel("Derivation Time (ms)")
    ax2.set_title("Scalability: Rules vs Time")

    if len(rules) > 2:
        r2, p2 = stats.pearsonr(rules, times)
        ax2.text(0.05, 0.95, f"r={r2:.3f}, p={fmt_p(p2)}", transform=ax2.transAxes,
                 fontsize=9, va="top")

    fig.tight_layout()
    return fig


# ============================================================
# Report generation
# ============================================================


def generate_markdown_report(results: dict[str, Any]) -> str:
    """Generate human-readable markdown report."""
    lines = [
        "# EXP-B: Constraint Derivation Engine Ablation Study",
        "",
        f"**Graphs analyzed**: {results['summary']['n_graphs']}",
        f"**Auto scenarios used**: {results['summary']['n_auto']}",
        f"**Manual scenarios used**: {results['summary']['n_manual']}",
        "",
        "## Ablation Results",
        "",
        "### Ablation A: Unconditional Activation",
        "",
        "All conditional rules activated regardless of patient context.",
        f"- Baseline constraints: {results['ablation_a']['baseline_total']}",
        f"- Ablated constraints: {results['ablation_a']['ablated_total']}",
        f"- **Overgeneration rate: {results['ablation_a']['overgeneration_rate_pct']:.1f}%**",
        "",
        "### Ablation B: No Type Distinction",
        "",
        "All constraints mapped to REQUIRED (losing FORBIDDEN/BEFORE/WITHIN).",
        f"- Avg constraint types (normal): {results['ablation_b']['avg_types_normal']:.2f}",
        f"- Avg constraint types (ablated): {results['ablation_b']['avg_types_ablated']:.2f}",
        f"- **Differentiation loss: {results['ablation_b']['differentiation_loss_pct']:.1f}%**",
        f"- Scenarios losing FORBIDDEN: {results['ablation_b']['scenarios_losing_forbidden']}",
        "",
        "### Ablation C: Random Patient Context",
        "",
        "Random patient instead of PatientGenerator-derived patient.",
        f"- Evaluated: {results['ablation_c']['n_evaluated']} scenarios",
        f"- **FP rate: {results['ablation_c']['fp_rate_pct']:.1f}%**",
        f"- **FN rate: {results['ablation_c']['fn_rate_pct']:.1f}%**",
        "",
        "## Baseline-Manual Comparison",
        "",
        "Engine-derived constraints vs manual expected/forbidden actions.",
        f"- Evaluated: {results['baseline_manual']['n_evaluated']} scenarios",
        f"- **Precision: {results['baseline_manual']['avg_precision']:.3f}"
        f" ± {results['baseline_manual']['std_precision']:.3f}**",
        f"- **Recall: {results['baseline_manual']['avg_recall']:.3f}"
        f" ± {results['baseline_manual']['std_recall']:.3f}**",
        "",
        "## Scalability",
        "",
        "| Graph | Nodes | Rules | Constraints | Time (ms) |",
        "|-------|-------|-------|-------------|-----------|",
    ]

    for g in sorted(
        results["scalability"]["per_graph"],
        key=lambda x: x["conditional_rules_count"],
        reverse=True,
    ):
        lines.append(
            f"| {g['graph_id'][:25]} | {g['node_count']} | "
            f"{g['conditional_rules_count']} | {g['constraint_count']} | "
            f"{g['derivation_time_ms']:.1f} |"
        )

    return "\n".join(lines) + "\n"


def generate_latex(results: dict[str, Any]) -> None:
    """Generate LaTeX ablation table."""
    rows = [
        [
            "A: Unconditional",
            str(results["ablation_a"]["baseline_total"]),
            str(results["ablation_a"]["ablated_total"]),
            f"{results['ablation_a']['overgeneration_rate_pct']:.1f}\\%",
            "---",
        ],
        [
            "B: No Type",
            f"{results['ablation_b']['avg_types_normal']:.2f}",
            f"{results['ablation_b']['avg_types_ablated']:.2f}",
            f"{results['ablation_b']['differentiation_loss_pct']:.1f}\\%",
            str(results["ablation_b"]["scenarios_losing_forbidden"]),
        ],
        [
            "C: Random Patient",
            str(results["ablation_c"]["total_constraints_gold"]),
            str(results["ablation_c"]["total_constraints_random"]),
            f"FP {results['ablation_c']['fp_rate_pct']:.1f}\\%",
            f"FN {results['ablation_c']['fn_rate_pct']:.1f}\\%",
        ],
        [
            "Engine vs Manual",
            f"P={results['baseline_manual']['avg_precision']:.3f}",
            f"R={results['baseline_manual']['avg_recall']:.3f}",
            str(results["baseline_manual"]["n_evaluated"]),
            "---",
        ],
    ]
    headers = ["Ablation", "Baseline", "Ablated", "Impact", "Detail"]
    save_latex_table(
        rows, headers,
        TABLES_DIR / "derivation_ablation.tex",
        caption="Constraint Derivation Engine ablation study results.",
        label="tab:ablation",
    )


# ============================================================
# Main
# ============================================================


def main() -> None:
    """Run EXP-B ablation study."""
    setup_matplotlib()

    print("EXP-B: Constraint Derivation Engine Ablation Study")
    print("=" * 60)

    graphs = load_all_graphs()
    scenarios = load_all_scenarios(tag_source=True)

    auto = [s for s in scenarios if s.get("source_type") == "auto"]
    manual = [s for s in scenarios if s.get("source_type") == "manual"]
    print(f"Loaded {len(graphs)} graphs, {len(auto)} auto, {len(manual)} manual scenarios")

    results: dict[str, Any] = {}

    # Ablation experiments
    results["ablation_a"] = run_ablation_a(graphs, auto)
    results["ablation_b"] = run_ablation_b(graphs, auto)
    results["ablation_c"] = run_ablation_c(graphs, auto)

    # Baseline comparison
    results["baseline_manual"] = run_baseline_manual(graphs, manual)

    # Scalability
    results["scalability"] = run_scalability(graphs)

    results["summary"] = {
        "n_graphs": len(graphs),
        "n_auto": len(auto),
        "n_manual": len(manual),
    }

    # Save outputs
    save_json(results, EVIDENCE_DIR / "exp_b_derivation_ablation.json")

    md = generate_markdown_report(results)
    save_markdown(md, EVIDENCE_DIR / "exp_b_derivation_ablation.md")

    generate_latex(results)

    # Figures
    fig1 = plot_ablation_bars(
        results["ablation_a"], results["ablation_b"],
        results["ablation_c"], results["baseline_manual"],
    )
    save_figure(fig1, FIGURES_DIR / "exp_b_ablation_bars.png")

    fig2 = plot_scalability(results["scalability"])
    save_figure(fig2, FIGURES_DIR / "exp_b_scalability.png")

    print("\nEXP-B complete.")


if __name__ == "__main__":
    main()
