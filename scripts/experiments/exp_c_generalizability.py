#!/usr/bin/env python3
"""EXP-C: Held-out Domain Generalizability Analysis.

Proves the Derivation Engine generalises to held-out domains with zero code
changes by comparing derivation success, scenario quality, and coverage
between 20 main graphs and 5 held-out graphs.

Outputs:
  evidence_pack/exp_c_generalizability.json
  evidence_pack/exp_c_generalizability.md
  evidence_pack/figures/exp_c_indomain_vs_holdout.png
  evidence_pack/figures/exp_c_coverage_heatmap.png
  evidence_pack/tables/generalizability.tex

Usage:
    PYTHONPATH=. python scripts/experiments/exp_c_generalizability.py
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
from typing import Any

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cpg_model.constraint_derivation import (
    ConstraintDerivationEngine,
)
from cpg_model.patient_generator import PatientGenerator, _collect_all_rules
import matplotlib
from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    HELD_OUT_GRAPH_IDS,
    TABLES_DIR,
    bootstrap_ci,
    fmt_p,
    load_all_graphs,
    load_all_scenarios,
    save_figure,
    save_json,
    save_latex_table,
    save_markdown,
    setup_matplotlib,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ============================================================
# Analysis 1: Derivation success rate
# ============================================================


def analyze_derivation_success(
    graphs: dict[str, dict[str, Any]],
    graph_ids: list[str],
    engine: ConstraintDerivationEngine,
    generator: PatientGenerator,
    label: str,
) -> list[dict[str, Any]]:
    """Per-graph derivation success metrics.

    Args:
        graphs: All loaded graphs keyed by graph_id.
        graph_ids: Subset of graph IDs to analyse.
        engine: Derivation engine instance.
        generator: Patient generator instance.
        label: "main" or "holdout".

    Returns:
        List of per-graph stat dicts.
    """
    results: list[dict[str, Any]] = []

    for gid in sorted(graph_ids):
        graph = graphs.get(gid)
        if graph is None:
            continue

        rules = _collect_all_rules(graph)
        n_rules = len(rules)

        # Generate scenarios from this graph
        scenarios = generator.generate_from_graph(graph)
        n_scenarios = len(scenarios)
        n_trap = sum(1 for s in scenarios if s.trap_scenario)
        n_normal = n_scenarios - n_trap

        # Derive constraints for each generated scenario
        constraint_counts: list[int] = []
        type_counter: Counter[str] = Counter()
        n_failures = 0

        for sc in scenarios:
            try:
                derived = engine.derive(graph, sc.patient, sc.scenario_id)
                n_c = len(derived.all_constraints())
                constraint_counts.append(n_c)
                for c in derived.all_constraints():
                    type_counter[c.constraint_type] += 1
            except Exception:
                n_failures += 1

        avg_constraints = float(np.mean(constraint_counts)) if constraint_counts else 0.0
        failure_rate = n_failures / max(n_scenarios, 1)

        results.append({
            "graph_id": gid,
            "label": label,
            "n_rules": n_rules,
            "n_scenarios_generated": n_scenarios,
            "n_trap": n_trap,
            "n_normal": n_normal,
            "avg_constraints": round(avg_constraints, 2),
            "constraint_types": dict(type_counter),
            "n_failures": n_failures,
            "failure_rate": round(failure_rate, 4),
        })

    return results


# ============================================================
# Analysis 2: Auto scenario quality comparison
# ============================================================


def analyze_scenario_quality(
    scenarios: list[dict[str, Any]],
    graph_ids: set[str],
    label: str,
) -> dict[str, Any]:
    """Compute quality metrics for scenarios from specified graphs.

    Args:
        scenarios: All loaded scenarios.
        graph_ids: Set of graph IDs to filter.
        label: "main" or "holdout".

    Returns:
        Quality metrics dict.
    """
    filtered = [
        s for s in scenarios
        if s.get("_canonical_graph_id", "") in graph_ids
        and s.get("source_type") == "auto"
    ]

    if not filtered:
        return {"label": label, "n_scenarios": 0}

    complexities = []
    constraint_densities = []
    expected_counts = []
    trap_count = 0

    for sc in filtered:
        n_comorb = len(sc.get("patient", {}).get("comorbidities", []))
        n_allergy = len(sc.get("patient", {}).get("allergies", []))
        complexities.append(n_comorb + n_allergy)

        n_expected = len(sc.get("expected_actions", []))
        n_forbidden = len(sc.get("forbidden_actions", []))
        constraint_densities.append(n_expected + n_forbidden)
        expected_counts.append(n_expected)

        if sc.get("trap_scenario", False):
            trap_count += 1

    n = len(filtered)
    return {
        "label": label,
        "n_scenarios": n,
        "complexity_mean": round(float(np.mean(complexities)), 2),
        "complexity_std": round(float(np.std(complexities)), 2),
        "constraint_density_mean": round(float(np.mean(constraint_densities)), 2),
        "constraint_density_std": round(float(np.std(constraint_densities)), 2),
        "expected_count_mean": round(float(np.mean(expected_counts)), 2),
        "expected_count_std": round(float(np.std(expected_counts)), 2),
        "trap_ratio": round(trap_count / n, 3),
        "trap_count": trap_count,
    }


# ============================================================
# Analysis 3: Structural coverage
# ============================================================


def compute_coverage(
    graph: dict[str, Any],
    generated_scenarios: list[Any],
    engine: ConstraintDerivationEngine,
) -> dict[str, Any]:
    """Compute rule and node coverage for a graph.

    Args:
        graph: Loaded graph dict.
        generated_scenarios: Scenarios from PatientGenerator.
        engine: Derivation engine.

    Returns:
        Coverage metrics dict.
    """
    rules = _collect_all_rules(graph)
    all_rule_ids = {r.get("rule_id", "") for r in rules if r.get("rule_id")}

    nodes = graph.get("nodes", {})

    # Collect all mandatory actions from all nodes
    all_node_actions: set[str] = set()
    for node in nodes.values():
        for a in node.get("mandatory_actions", []):
            all_node_actions.add(a)

    triggered_rules: set[str] = set()
    covered_actions: set[str] = set()

    for sc in generated_scenarios:
        for rule_id in sc.triggered_rules:
            triggered_rules.add(rule_id)

        # Derive to get expected actions
        try:
            derived = engine.derive(graph, sc.patient, sc.scenario_id)
            for c in derived.expected:
                for a in c.actions:
                    covered_actions.add(a)
        except Exception:  # noqa: S110
            pass  # Derivation may fail for held-out graphs with unsupported conditions

    rule_coverage = len(triggered_rules & all_rule_ids) / max(len(all_rule_ids), 1)
    action_coverage = len(covered_actions & all_node_actions) / max(len(all_node_actions), 1)

    return {
        "total_rules": len(all_rule_ids),
        "triggered_rules": len(triggered_rules & all_rule_ids),
        "rule_coverage": round(rule_coverage, 3),
        "total_node_actions": len(all_node_actions),
        "covered_actions": len(covered_actions & all_node_actions),
        "action_coverage": round(action_coverage, 3),
    }


# ============================================================
# Analysis 4: Edge case catalogue
# ============================================================


def catalog_edge_cases(
    graphs: dict[str, dict[str, Any]],
    holdout_ids: list[str],
    main_ids: list[str],
    engine: ConstraintDerivationEngine,
) -> dict[str, Any]:
    """Identify structural patterns unique to held-out graphs.

    Args:
        graphs: All loaded graphs.
        holdout_ids: Held-out graph IDs.
        main_ids: Main graph IDs.
        engine: Derivation engine.

    Returns:
        Edge case catalogue dict.
    """
    # Collect condition patterns from all graphs
    main_patterns: set[str] = set()
    holdout_patterns: set[str] = set()
    holdout_unique: list[dict[str, Any]] = []

    for gid in main_ids:
        graph = graphs.get(gid, {})
        for node in graph.get("nodes", {}).values():
            for rule in node.get("conditional_rules", []):
                cond = rule.get("condition", "")
                pattern = _extract_condition_pattern(cond)
                main_patterns.add(pattern)

    for gid in holdout_ids:
        graph = graphs.get(gid, {})
        for node_id, node in graph.get("nodes", {}).items():
            for rule in node.get("conditional_rules", []):
                cond = rule.get("condition", "")
                pattern = _extract_condition_pattern(cond)
                holdout_patterns.add(pattern)

                if pattern not in main_patterns:
                    holdout_unique.append({
                        "graph_id": gid,
                        "node_id": node_id,
                        "rule_id": rule.get("rule_id", ""),
                        "condition": cond,
                        "pattern": pattern,
                    })

    # Test which patterns fail derivation
    failures: list[dict[str, Any]] = []
    for gid in holdout_ids:
        graph = graphs.get(gid, {})
        rules = _collect_all_rules(graph)
        dummy_patient = {"age": 55, "sex": "M", "labs": {}, "vitals": {},
                         "comorbidities": [], "allergies": []}
        for rule in rules:
            cond = rule.get("condition", "")
            try:
                engine._evaluate_condition(cond, dummy_patient)
            except Exception as e:
                failures.append({
                    "graph_id": gid,
                    "rule_id": rule.get("rule_id", ""),
                    "condition": cond,
                    "error": str(e),
                })

    return {
        "main_pattern_count": len(main_patterns),
        "holdout_pattern_count": len(holdout_patterns),
        "unique_holdout_patterns": len(holdout_unique),
        "unique_patterns": holdout_unique[:20],  # cap for JSON size
        "parsing_failures": failures,
        "n_parsing_failures": len(failures),
    }


def _extract_condition_pattern(condition: str) -> str:
    """Extract structural pattern from condition string.

    Normalises variable names and values to capture the pattern type.
    E.g., "patient.labs.potassium < 3.3" -> "patient.VAR < NUM"
    """
    import re

    s = condition.strip()
    # Replace numeric values
    s = re.sub(r"\b\d+\.?\d*\b", "NUM", s)
    # Replace quoted strings
    s = re.sub(r"'[^']*'", "STR", s)
    s = re.sub(r'"[^"]*"', "STR", s)
    # Replace patient.xxx.yyy.zzz with patient.VAR
    s = re.sub(r"patient(?:\.\w+)+", "patient.VAR", s)
    return s


# ============================================================
# Figures
# ============================================================


def plot_indomain_vs_holdout(
    main_stats: list[dict[str, Any]],
    holdout_stats: list[dict[str, Any]],
) -> plt.Figure:
    """Grouped bar chart comparing main vs held-out metrics."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))

    metrics = [
        ("n_rules", "Conditional Rules per Graph"),
        ("n_scenarios_generated", "Scenarios Generated per Graph"),
        ("avg_constraints", "Avg Constraints per Scenario"),
        ("failure_rate", "Derivation Failure Rate"),
    ]

    for ax, (key, title) in zip(axes.flat, metrics, strict=False):
        main_vals = [s[key] for s in main_stats]
        holdout_vals = [s[key] for s in holdout_stats]

        x = np.arange(2)
        width = 0.5
        bars = ax.bar(
            x,
            [float(np.mean(main_vals)) if main_vals else 0,
             float(np.mean(holdout_vals)) if holdout_vals else 0],
            width,
            color=["steelblue", "coral"],
            edgecolor="black",
            linewidth=0.5,
        )

        # Error bars
        if main_vals:
            ax.errorbar(0, np.mean(main_vals), yerr=np.std(main_vals),
                        fmt="none", ecolor="black", capsize=5)
        if holdout_vals:
            ax.errorbar(1, np.mean(holdout_vals), yerr=np.std(holdout_vals),
                        fmt="none", ecolor="black", capsize=5)

        ax.set_xticks(x)
        ax.set_xticklabels(["Main (n=20)", "Held-out (n=5)"])
        ax.set_title(title)

        # Annotate values
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h + 0.01,
                    f"{h:.2f}", ha="center", va="bottom", fontsize=9)

    fig.suptitle("In-Domain vs Held-out Graph Metrics", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    return fig


def plot_coverage_heatmap(
    coverage_data: dict[str, dict[str, Any]],
) -> plt.Figure:
    """Heatmap: graph x (rule_coverage, action_coverage)."""
    graph_ids = sorted(coverage_data.keys())
    n = len(graph_ids)

    if n == 0:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "No coverage data", ha="center", va="center")
        return fig

    matrix = np.zeros((n, 2))
    for i, gid in enumerate(graph_ids):
        cov = coverage_data[gid]
        matrix[i, 0] = cov.get("rule_coverage", 0)
        matrix[i, 1] = cov.get("action_coverage", 0)

    fig, ax = plt.subplots(figsize=(6, max(4, n * 0.4)))
    im = ax.imshow(matrix, cmap="YlGn", aspect="auto", vmin=0, vmax=1)

    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Rule Coverage", "Action Coverage"])
    ax.set_yticks(range(n))

    # Shorten labels
    short_labels = [gid[:20] for gid in graph_ids]
    ax.set_yticklabels(short_labels, fontsize=8)

    # Annotate cells
    for i in range(n):
        for j in range(2):
            val = matrix[i, j]
            color = "white" if val > 0.7 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=8, color=color)

    fig.colorbar(im, ax=ax, label="Coverage", shrink=0.8)
    ax.set_title("Structural Coverage per Graph")
    fig.tight_layout()
    return fig


# ============================================================
# Report generation
# ============================================================


def generate_markdown(results: dict[str, Any]) -> str:
    """Generate markdown report."""
    r = results
    lines = [
        "# EXP-C: Held-out Domain Generalizability Analysis",
        "",
        f"**Main graphs**: {r['summary']['n_main']}",
        f"**Held-out graphs**: {r['summary']['n_holdout']}",
        "",
        "## Analysis 1: Derivation Success",
        "",
        "| Graph | Label | Rules | Scenarios | Avg Constraints | Failures |",
        "|-------|-------|-------|-----------|-----------------|----------|",
    ]

    for s in r["derivation_main"] + r["derivation_holdout"]:
        lines.append(
            f"| {s['graph_id'][:22]} | {s['label']} | {s['n_rules']} | "
            f"{s['n_scenarios_generated']} | {s['avg_constraints']} | "
            f"{s['n_failures']} |"
        )

    # Statistical comparison
    comp = r.get("derivation_comparison", {})
    lines += [
        "",
        "### Statistical Comparison (Main vs Held-out)",
        "",
        f"- Rules: U={comp.get('rules_U', 'N/A')}, p={comp.get('rules_p', 'N/A')}",
        f"- Scenarios: U={comp.get('scenarios_U', 'N/A')}, p={comp.get('scenarios_p', 'N/A')}",
        f"- Constraints: U={comp.get('constraints_U', 'N/A')}, p={comp.get('constraints_p', 'N/A')}",
        "",
    ]

    # Quality comparison
    lines += [
        "## Analysis 2: Auto Scenario Quality",
        "",
        "| Metric | Main | Held-out |",
        "|--------|------|----------|",
    ]
    qm = r.get("quality_main", {})
    qh = r.get("quality_holdout", {})
    for metric in ["n_scenarios", "complexity_mean", "constraint_density_mean",
                    "expected_count_mean", "trap_ratio"]:
        lines.append(
            f"| {metric} | {qm.get(metric, 'N/A')} | {qh.get(metric, 'N/A')} |"
        )

    # Coverage
    lines += [
        "",
        "## Analysis 3: Structural Coverage",
        "",
        "| Graph | Rule Coverage | Action Coverage |",
        "|-------|-------------|-----------------|",
    ]
    for gid, cov in sorted(r.get("coverage", {}).items()):
        lines.append(
            f"| {gid[:22]} | {cov['rule_coverage']:.3f} | {cov['action_coverage']:.3f} |"
        )

    # Edge cases
    ec = r.get("edge_cases", {})
    lines += [
        "",
        "## Analysis 4: Edge Cases",
        "",
        f"- Main condition patterns: {ec.get('main_pattern_count', 0)}",
        f"- Held-out condition patterns: {ec.get('holdout_pattern_count', 0)}",
        f"- Unique held-out patterns: {ec.get('unique_holdout_patterns', 0)}",
        f"- Parsing failures: {ec.get('n_parsing_failures', 0)}",
    ]

    if ec.get("unique_patterns"):
        lines += ["", "### Unique Held-out Patterns", ""]
        for p in ec["unique_patterns"][:10]:
            lines.append(f"- `{p['graph_id']}:{p['rule_id']}` — `{p['pattern']}`")

    return "\n".join(lines) + "\n"


def generate_latex(results: dict[str, Any]) -> None:
    """Generate LaTeX comparison table."""
    dm = results["derivation_main"]
    dh = results["derivation_holdout"]

    def _agg(data: list[dict[str, Any]], key: str) -> tuple[float, float]:
        vals = [d[key] for d in data]
        return (float(np.mean(vals)), float(np.std(vals))) if vals else (0, 0)

    metrics = ["n_rules", "n_scenarios_generated", "avg_constraints", "failure_rate"]
    metric_labels = ["Conditional rules", "Scenarios generated", "Avg constraints", "Failure rate"]

    rows = []
    comp = results.get("derivation_comparison", {})
    for metric, label in zip(metrics, metric_labels, strict=True):
        m_mean, m_std = _agg(dm, metric)
        h_mean, h_std = _agg(dh, metric)
        p_key = f"{metric.split('_')[0]}_p" if metric != "avg_constraints" else "constraints_p"
        p_val = comp.get(p_key, "")
        p_str = fmt_p(p_val) if isinstance(p_val, float) else str(p_val)

        rows.append([
            label,
            f"{m_mean:.2f} $\\pm$ {m_std:.2f}",
            f"{h_mean:.2f} $\\pm$ {h_std:.2f}",
            p_str,
        ])

    save_latex_table(
        rows,
        ["Metric", "Main (n=20)", "Held-out (n=5)", "p-value"],
        TABLES_DIR / "generalizability.tex",
        caption="In-domain vs held-out generalizability comparison.",
        label="tab:generalizability",
    )


# ============================================================
# Main
# ============================================================


def main() -> None:
    """Run EXP-C generalizability analysis."""
    setup_matplotlib()

    print("EXP-C: Held-out Domain Generalizability Analysis")
    print("=" * 60)

    graphs = load_all_graphs()
    all_graph_ids = set(graphs.keys())

    holdout_ids = sorted(HELD_OUT_GRAPH_IDS & all_graph_ids)
    main_ids = sorted(all_graph_ids - HELD_OUT_GRAPH_IDS)

    print(f"Main graphs: {len(main_ids)}")
    print(f"Held-out graphs: {len(holdout_ids)}")

    engine = ConstraintDerivationEngine()
    generator = PatientGenerator(engine, seed=42)

    # Analysis 1: Derivation success
    print("\n--- Analysis 1: Derivation Success ---")
    main_stats = analyze_derivation_success(graphs, main_ids, engine, generator, "main")
    holdout_stats = analyze_derivation_success(graphs, holdout_ids, engine, generator, "holdout")

    # Statistical comparison
    comparison: dict[str, Any] = {}
    for key, prefix in [
        ("n_rules", "rules"),
        ("n_scenarios_generated", "scenarios"),
        ("avg_constraints", "constraints"),
    ]:
        m_vals = [s[key] for s in main_stats]
        h_vals = [s[key] for s in holdout_stats]
        if m_vals and h_vals:
            u_stat, p_val = stats.mannwhitneyu(
                m_vals, h_vals, alternative="two-sided"
            )
            comparison[f"{prefix}_U"] = round(float(u_stat), 2)
            comparison[f"{prefix}_p"] = round(float(p_val), 4)
        else:
            comparison[f"{prefix}_U"] = "N/A"
            comparison[f"{prefix}_p"] = "N/A"

    # Bootstrap CIs for key metrics
    for key in ["n_rules", "avg_constraints"]:
        m_arr = np.array([s[key] for s in main_stats], dtype=float)
        h_arr = np.array([s[key] for s in holdout_stats], dtype=float)
        if len(m_arr) > 0:
            comparison[f"main_{key}_ci"] = list(
                bootstrap_ci(m_arr, np.mean)
            )
        if len(h_arr) > 0:
            comparison[f"holdout_{key}_ci"] = list(
                bootstrap_ci(h_arr, np.mean)
            )

    # Analysis 2: Scenario quality
    print("\n--- Analysis 2: Scenario Quality ---")
    scenarios = load_all_scenarios(tag_source=True)
    quality_main = analyze_scenario_quality(scenarios, set(main_ids), "main")
    quality_holdout = analyze_scenario_quality(scenarios, set(holdout_ids), "holdout")

    # Analysis 3: Coverage
    print("\n--- Analysis 3: Coverage ---")
    coverage: dict[str, dict[str, Any]] = {}
    for gid in holdout_ids + main_ids[:5]:  # All held-out + 5 main for comparison
        graph = graphs.get(gid)
        if graph is None:
            continue
        gen_scenarios = generator.generate_from_graph(graph)
        coverage[gid] = compute_coverage(graph, gen_scenarios, engine)
        coverage[gid]["label"] = "holdout" if gid in holdout_ids else "main"
        print(f"  {gid}: rule={coverage[gid]['rule_coverage']:.3f}, "
              f"action={coverage[gid]['action_coverage']:.3f}")

    # Analysis 4: Edge cases
    print("\n--- Analysis 4: Edge Cases ---")
    edge_cases = catalog_edge_cases(graphs, holdout_ids, main_ids, engine)
    print(f"  Unique held-out patterns: {edge_cases['unique_holdout_patterns']}")
    print(f"  Parsing failures: {edge_cases['n_parsing_failures']}")

    # Assemble results
    results: dict[str, Any] = {
        "summary": {
            "n_main": len(main_ids),
            "n_holdout": len(holdout_ids),
            "main_ids": main_ids,
            "holdout_ids": holdout_ids,
        },
        "derivation_main": main_stats,
        "derivation_holdout": holdout_stats,
        "derivation_comparison": comparison,
        "quality_main": quality_main,
        "quality_holdout": quality_holdout,
        "coverage": coverage,
        "edge_cases": edge_cases,
    }

    # Save outputs
    save_json(results, EVIDENCE_DIR / "exp_c_generalizability.json")
    save_markdown(generate_markdown(results), EVIDENCE_DIR / "exp_c_generalizability.md")
    generate_latex(results)

    # Figures
    fig1 = plot_indomain_vs_holdout(main_stats, holdout_stats)
    save_figure(fig1, FIGURES_DIR / "exp_c_indomain_vs_holdout.png")

    fig2 = plot_coverage_heatmap(coverage)
    save_figure(fig2, FIGURES_DIR / "exp_c_coverage_heatmap.png")

    print("\nEXP-C complete.")


if __name__ == "__main__":
    main()
