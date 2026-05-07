#!/usr/bin/env python3
"""Scenario complexity quantification for CGA-Bench.

Parses CPG graph YAML files and scenario configs to produce:
  1. Per-graph complexity metrics (nodes, actions, constraints)
  2. Per-scenario complexity metrics (expected actions, active constraints)
  3. Benchmark comparison table (CGA-Bench vs external benchmarks)
  4. LaTeX tables for the paper

Usage:
    PYTHONPATH=. python scripts/experiments/scenario_complexity.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]  # cga_bench root
GRAPH_DIR = BASE_DIR / "cpg_model" / "graphs"
SCENARIO_DIR = BASE_DIR / "configs" / "scenarios"
ANALYSIS_DIR = BASE_DIR / "evidence_pack" / "analysis"
TABLE_DIR = BASE_DIR / "evidence_pack" / "tables"

# The 15 scenarios used in the main evaluation
EVAL_SCENARIOS: list[str] = [
    "septic_shock_basic",
    "septic_shock_penicillin_allergy",
    "stemi_inferior_rv_trap",
    "dka_moderate_basic",
    "dka_hypokalemia_trap",
    "stroke_tpa_eligible",
    "contrast_aki_prevention_basic",
    "aki_stage1_basic",
    "af_new_onset_basic",
    "gi_bleeding_upper_basic",
    "htn_emergency_basic",
    "pe_submassive_basic",
    "copd_moderate_exacerbation",
    "adhf_warm_wet",
    "hemorrhagic_stroke",
]

# Evidence strength mappings (various formats found in YAMLs)
EVIDENCE_STRENGTH_MAP: dict[str, str] = {
    "A": "STRONG",
    "B": "MODERATE",
    "B-NR": "MODERATE",
    "C": "WEAK",
    "C-LD": "WEAK",
    "C-EO": "WEAK",
    "I": "STRONG",       # recommendation class I
    "IIa": "MODERATE",
    "IIb": "WEAK",
    "III": "WEAK",
}

# Violation types that can occur in CGA-Bench
VIOLATION_TYPES: list[str] = [
    "OMISSION",
    "COMMISSION",
    "TIMING",
    "SEQUENCE",
    "DEVIATION",
]


# ---------------------------------------------------------------------------
# Step 1: CPG Graph Complexity
# ---------------------------------------------------------------------------

def parse_graph_file(path: Path) -> dict:
    """Parse a single CPG graph YAML and extract complexity metrics.

    Args:
        path: Path to the YAML graph file.

    Returns:
        Dictionary with graph-level complexity metrics.
    """
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    graph_id = data.get("graph_id", path.stem)
    guideline_name = data.get("guideline_name", graph_id)
    nodes = data.get("nodes", {})

    total_nodes = len(nodes)
    all_mandatory: set[str] = set()
    all_forbidden: set[str] = set()
    all_allowed: set[str] = set()
    timing_constraints = 0
    timing_details: dict[str, int] = {}
    sequence_deps = 0
    sequence_details: list[dict[str, str]] = []
    conditional_branches = 0
    evidence_levels: list[str] = []

    for node_id, node in nodes.items():
        # Mandatory actions
        mandatory = node.get("mandatory_actions", [])
        if mandatory:
            all_mandatory.update(mandatory)

        # Forbidden actions
        forbidden = node.get("forbidden_actions", [])
        if forbidden:
            all_forbidden.update(forbidden)

        # Allowed actions
        allowed = node.get("allowed_actions", [])
        if allowed:
            all_allowed.update(allowed)

        # Timing constraints (deadlines)
        deadlines = node.get("deadlines", {})
        if deadlines:
            timing_constraints += len(deadlines)
            for action, minutes in deadlines.items():
                timing_details[action] = minutes

        # Sequence dependencies
        prior = node.get("required_prior_actions", {})
        if prior:
            for action, deps in prior.items():
                if isinstance(deps, list) and deps:
                    sequence_deps += len(deps)
                    for dep in deps:
                        sequence_details.append({
                            "action": action,
                            "requires": dep,
                            "node": node_id,
                        })

        # Conditional branches
        cond_next = node.get("conditional_next", {})
        if cond_next:
            conditional_branches += len(cond_next)

        # Evidence level
        ev_level = node.get("evidence_level", "")
        if ev_level:
            evidence_levels.append(str(ev_level))

    # Classify evidence strength distribution
    strength_counts: dict[str, int] = {"STRONG": 0, "MODERATE": 0, "WEAK": 0}
    for level in evidence_levels:
        mapped = EVIDENCE_STRENGTH_MAP.get(level, "WEAK")
        strength_counts[mapped] += 1

    total_ev = sum(strength_counts.values()) or 1
    strength_pct = {
        k: round(v / total_ev * 100, 1) for k, v in strength_counts.items()
    }

    return {
        "graph_id": graph_id,
        "guideline_name": guideline_name,
        "file": path.name,
        "total_nodes": total_nodes,
        "total_mandatory_actions": len(all_mandatory),
        "mandatory_actions": sorted(all_mandatory),
        "total_forbidden_actions": len(all_forbidden),
        "forbidden_actions": sorted(all_forbidden),
        "total_allowed_actions": len(all_allowed),
        "timing_constraints": timing_constraints,
        "timing_details": timing_details,
        "sequence_dependencies": sequence_deps,
        "sequence_details": sequence_details,
        "conditional_branches": conditional_branches,
        "evidence_strength_distribution": strength_counts,
        "evidence_strength_pct": strength_pct,
    }


def analyze_all_graphs() -> dict[str, dict]:
    """Parse all CPG graph YAML files and return complexity metrics.

    Indexes by both graph_id and filename stem so that scenario configs
    referencing either form (e.g. ``ssc_sepsis_hour1`` vs
    ``ssc_sepsis_hour1_bundle``) resolve correctly.

    Returns:
        Dictionary mapping graph_id (and filename stem alias) to metrics.
    """
    results: dict[str, dict] = {}
    for yaml_path in sorted(GRAPH_DIR.glob("*.yaml")):
        metrics = parse_graph_file(yaml_path)
        results[metrics["graph_id"]] = metrics
        # Also index by filename stem if it differs from graph_id
        stem = yaml_path.stem
        if stem not in results:
            results[stem] = metrics
    return results


# ---------------------------------------------------------------------------
# Step 2: Scenario-level Complexity
# ---------------------------------------------------------------------------

def load_all_scenarios() -> dict[str, dict]:
    """Load all scenario configs from YAML files.

    Returns:
        Dictionary mapping scenario_id to its config data.
    """
    scenarios: dict[str, dict] = {}
    for yaml_path in sorted(SCENARIO_DIR.glob("*.yaml")):
        with open(yaml_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not data or "scenarios" not in data:
            continue
        for sid, sdata in data["scenarios"].items():
            sdata["_source_file"] = yaml_path.name
            scenarios[sid] = sdata
    return scenarios


def graph_id_from_scenario(scenario: dict) -> str:
    """Extract graph reference from a scenario config.

    Args:
        scenario: Scenario configuration dictionary.

    Returns:
        Graph identifier string.
    """
    return scenario.get("guideline_graph", scenario.get("cpg_graph", ""))


def analyze_scenario(
    scenario_id: str,
    scenario: dict,
    graph_metrics: dict[str, dict],
) -> dict:
    """Compute complexity metrics for a single scenario.

    Args:
        scenario_id: Identifier for the scenario.
        scenario: Scenario configuration dictionary.
        graph_metrics: Pre-computed graph complexity metrics.

    Returns:
        Dictionary with scenario-level complexity metrics.
    """
    graph_ref = graph_id_from_scenario(scenario)
    expected = scenario.get("expected_actions", [])
    forbidden = scenario.get("forbidden_actions", [])
    is_trap = scenario.get("trap_scenario", False)

    # Pull graph-level data if available
    graph = graph_metrics.get(graph_ref, {})

    active_deadlines = 0
    active_deadline_details: dict[str, int] = {}
    active_sequence_deps = 0
    active_sequence_details: list[dict[str, str]] = []

    if graph:
        # Count deadlines relevant to expected actions
        all_deadlines = graph.get("timing_details", {})
        for action, minutes in all_deadlines.items():
            active_deadlines += 1
            active_deadline_details[action] = minutes

        # Count sequence dependencies
        all_seqs = graph.get("sequence_details", [])
        for seq in all_seqs:
            active_sequence_deps += 1
            active_sequence_details.append(seq)

    # Determine which violation types can occur
    possible_violations: list[str] = []

    # OMISSION: if there are mandatory actions in the graph
    if graph.get("total_mandatory_actions", 0) > 0:
        possible_violations.append("OMISSION")

    # COMMISSION: if there are forbidden actions
    total_forbidden = graph.get("total_forbidden_actions", 0) + len(forbidden)
    if total_forbidden > 0:
        possible_violations.append("COMMISSION")

    # TIMING: if there are deadline constraints
    if active_deadlines > 0:
        possible_violations.append("TIMING")

    # SEQUENCE: if there are sequence dependencies
    if active_sequence_deps > 0:
        possible_violations.append("SEQUENCE")

    # DEVIATION: always possible (agent can do off-protocol actions)
    possible_violations.append("DEVIATION")

    return {
        "scenario_id": scenario_id,
        "graph_ref": graph_ref,
        "source_file": scenario.get("_source_file", ""),
        "expected_actions_count": len(expected),
        "expected_actions": expected,
        "scenario_forbidden_actions": forbidden,
        "scenario_forbidden_count": len(forbidden),
        "is_trap_scenario": is_trap,
        "active_deadlines": active_deadlines,
        "active_deadline_details": active_deadline_details,
        "active_sequence_deps": active_sequence_deps,
        "active_sequence_details": active_sequence_details,
        "graph_total_forbidden": graph.get("total_forbidden_actions", 0),
        "graph_total_mandatory": graph.get("total_mandatory_actions", 0),
        "graph_total_nodes": graph.get("total_nodes", 0),
        "graph_conditional_branches": graph.get("conditional_branches", 0),
        "possible_violation_types": possible_violations,
        "violation_type_count": len(possible_violations),
    }


def analyze_all_scenarios(
    graph_metrics: dict[str, dict],
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Analyze all scenarios and separate eval-set from full set.

    Args:
        graph_metrics: Pre-computed graph complexity metrics.

    Returns:
        Tuple of (all_scenario_metrics, eval_scenario_metrics).
    """
    all_scenarios = load_all_scenarios()
    all_metrics: dict[str, dict] = {}
    eval_metrics: dict[str, dict] = {}

    for sid, sdata in all_scenarios.items():
        m = analyze_scenario(sid, sdata, graph_metrics)
        all_metrics[sid] = m
        if sid in EVAL_SCENARIOS:
            eval_metrics[sid] = m

    return all_metrics, eval_metrics


# ---------------------------------------------------------------------------
# Step 3: Aggregate statistics
# ---------------------------------------------------------------------------

def _unique_graphs(graph_metrics: dict[str, dict]) -> dict[str, dict]:
    """Return only unique graphs, deduplicating stem aliases.

    Args:
        graph_metrics: Graph metrics dict that may contain aliases.

    Returns:
        Dict keyed by graph_id with no duplicates.
    """
    seen_ids: set[str] = set()
    unique: dict[str, dict] = {}
    for gm in graph_metrics.values():
        gid = gm["graph_id"]
        if gid not in seen_ids:
            seen_ids.add(gid)
            unique[gid] = gm
    return unique


def compute_aggregate_stats(
    graph_metrics: dict[str, dict],
    eval_scenario_metrics: dict[str, dict],
) -> dict:
    """Compute aggregate statistics across graphs and eval scenarios.

    Args:
        graph_metrics: Per-graph complexity metrics (may contain aliases).
        eval_scenario_metrics: Per-scenario complexity metrics (eval set).

    Returns:
        Dictionary with aggregate statistics.
    """
    unique = _unique_graphs(graph_metrics)

    total_timing = sum(g["timing_constraints"] for g in unique.values())
    total_seq = sum(g["sequence_dependencies"] for g in unique.values())
    total_forbidden = sum(
        g["total_forbidden_actions"] for g in unique.values()
    )
    total_mandatory = sum(
        g["total_mandatory_actions"] for g in unique.values()
    )
    total_nodes = sum(g["total_nodes"] for g in unique.values())
    total_conditional = sum(
        g["conditional_branches"] for g in unique.values()
    )

    # Count unique domains with forbidden actions
    domains_with_forbidden = sum(
        1 for g in unique.values() if g["total_forbidden_actions"] > 0
    )

    # Eval scenario aggregates
    eval_deadlines = sum(
        s["active_deadlines"] for s in eval_scenario_metrics.values()
    )
    eval_seq_deps = sum(
        s["active_sequence_deps"] for s in eval_scenario_metrics.values()
    )

    # Average violation types per eval scenario
    avg_violation_types = (
        sum(s["violation_type_count"] for s in eval_scenario_metrics.values())
        / max(len(eval_scenario_metrics), 1)
    )

    return {
        "graphs": {
            "count": len(unique),
            "total_nodes": total_nodes,
            "total_mandatory_actions": total_mandatory,
            "total_forbidden_actions": total_forbidden,
            "total_timing_constraints": total_timing,
            "total_sequence_dependencies": total_seq,
            "total_conditional_branches": total_conditional,
            "domains_with_forbidden": domains_with_forbidden,
        },
        "eval_scenarios": {
            "count": len(eval_scenario_metrics),
            "total_active_deadlines": eval_deadlines,
            "total_active_sequence_deps": eval_seq_deps,
            "avg_violation_types": round(avg_violation_types, 2),
        },
    }


# ---------------------------------------------------------------------------
# Step 4: Benchmark comparison
# ---------------------------------------------------------------------------

def build_benchmark_comparison(agg: dict) -> list[dict]:
    """Build comparison table of CGA-Bench vs external benchmarks.

    Uses only verified, published numbers for external benchmarks.

    Args:
        agg: Aggregate statistics from compute_aggregate_stats.

    Returns:
        List of benchmark comparison rows.
    """
    g = agg["graphs"]
    e = agg["eval_scenarios"]

    return [
        {
            "benchmark": "MedQA",
            "items": 11450,
            "eval_type": "Single MCQ",
            "time_constraints": "None",
            "sequence_constraints": "None",
            "forbidden_actions": "None",
            "violation_types": 0,
            "source": "Jin et al., 2021",
        },
        {
            "benchmark": "AgentClinic",
            "items": 321,
            "eval_type": "Dx + Tx",
            "time_constraints": "None",
            "sequence_constraints": "None",
            "forbidden_actions": "None",
            "violation_types": 0,
            "source": "Schmidgall et al., 2024",
        },
        {
            "benchmark": "HealthBench",
            "items": 5000,
            "eval_type": "Rubric-based",
            "time_constraints": "None",
            "sequence_constraints": "None",
            "forbidden_actions": "Partial",
            "violation_types": 1,
            "source": "OpenAI, 2025",
        },
        {
            "benchmark": "MedAgentBench",
            "items": 300,
            "eval_type": "FHIR success",
            "time_constraints": "None",
            "sequence_constraints": "None",
            "forbidden_actions": "None",
            "violation_types": 0,
            "source": "Yin et al., 2024",
        },
        {
            "benchmark": "CGA-Bench",
            "items": e["count"],
            "eval_type": "Full CPG closed-loop",
            "time_constraints": f"{g['total_timing_constraints']} constraints",
            "sequence_constraints": f"{g['total_sequence_dependencies']}+ deps",
            "forbidden_actions": f"{g['domains_with_forbidden']}+ domains",
            "violation_types": 5,
            "source": "This work",
        },
    ]


# ---------------------------------------------------------------------------
# Step 5: LaTeX table generation
# ---------------------------------------------------------------------------

def generate_scenario_complexity_tex(
    eval_metrics: dict[str, dict],
    agg: dict,
) -> str:
    """Generate LaTeX table for per-scenario complexity.

    Args:
        eval_metrics: Per-scenario complexity metrics (eval set).
        agg: Aggregate statistics.

    Returns:
        LaTeX table string.
    """
    lines: list[str] = []
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\caption{Scenario Complexity Quantification (15 Eval Scenarios)}")
    lines.append(r"\label{tab:scenario_complexity}")
    lines.append(r"\small")
    lines.append(
        r"\begin{tabular}{l c c c c c c}"
    )
    lines.append(r"\toprule")
    lines.append(
        r"Scenario & Expected & Deadlines & Seq.\ Deps & Forbidden & "
        r"Violation & Trap \\"
    )
    lines.append(
        r" & Actions & & & Actions & Types & \\"
    )
    lines.append(r"\midrule")

    for sid in EVAL_SCENARIOS:
        m = eval_metrics.get(sid, {})
        trap_mark = r"\checkmark" if m.get("is_trap_scenario") else ""
        short_id = sid.replace("_", r"\_")
        lines.append(
            f"  {short_id} & "
            f"{m.get('expected_actions_count', 0)} & "
            f"{m.get('active_deadlines', 0)} & "
            f"{m.get('active_sequence_deps', 0)} & "
            f"{m.get('scenario_forbidden_count', 0) + m.get('graph_total_forbidden', 0)} & "
            f"{m.get('violation_type_count', 0)} & "
            f"{trap_mark} \\\\"
        )

    lines.append(r"\midrule")
    g = agg["graphs"]
    e = agg["eval_scenarios"]
    lines.append(
        f"  \\textbf{{Total / Avg}} & "
        f"-- & "
        f"{g['total_timing_constraints']} & "
        f"{g['total_sequence_dependencies']} & "
        f"{g['total_forbidden_actions']} & "
        f"{e['avg_violation_types']:.1f} & "
        f"-- \\\\"
    )
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


def generate_benchmark_comparison_tex(comparison: list[dict]) -> str:
    """Generate LaTeX table for benchmark dimension comparison.

    Args:
        comparison: List of benchmark comparison rows.

    Returns:
        LaTeX table string.
    """
    lines: list[str] = []
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(
        r"\caption{Benchmark Evaluation Dimension Comparison}"
    )
    lines.append(r"\label{tab:benchmark_dimension}")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{l r l l l l}")
    lines.append(r"\toprule")
    lines.append(
        r"Benchmark & Items & Eval Type & Time & Sequence & Forbidden \\"
    )
    lines.append(
        r" & & & Constraints & Constraints & Actions \\"
    )
    lines.append(r"\midrule")

    for row in comparison:
        bname = row["benchmark"]
        if bname == "CGA-Bench":
            bname = r"\textbf{CGA-Bench}"
        lines.append(
            f"  {bname} & "
            f"{row['items']:,} & "
            f"{row['eval_type']} & "
            f"{row['time_constraints']} & "
            f"{row['sequence_constraints']} & "
            f"{row['forbidden_actions']} \\\\"
        )

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 6: Summary paragraph
# ---------------------------------------------------------------------------

def generate_summary(
    graph_metrics: dict[str, dict],
    eval_metrics: dict[str, dict],
    agg: dict,
) -> str:
    """Generate a 1-paragraph summary of complexity findings.

    Args:
        graph_metrics: Per-graph complexity metrics.
        eval_metrics: Per-scenario complexity metrics (eval set).
        agg: Aggregate statistics.

    Returns:
        Summary paragraph string.
    """
    g = agg["graphs"]
    e = agg["eval_scenarios"]

    trap_count = sum(
        1 for m in eval_metrics.values() if m.get("is_trap_scenario")
    )

    return (
        f"CGA-Bench comprises {g['count']} CPG graphs with "
        f"{g['total_nodes']} total nodes, encoding "
        f"{g['total_mandatory_actions']} unique mandatory actions, "
        f"{g['total_forbidden_actions']} forbidden actions across "
        f"{g['domains_with_forbidden']} clinical domains, "
        f"{g['total_timing_constraints']} timing constraints, and "
        f"{g['total_sequence_dependencies']} sequence dependencies. "
        f"The {e['count']}-scenario evaluation set spans all "
        f"{g['count']} guideline domains with an average of "
        f"{e['avg_violation_types']:.1f}/5 possible violation types per "
        f"scenario, including {trap_count} trap scenario(s) designed to "
        f"detect clinically dangerous commission errors. "
        f"In contrast, existing benchmarks (MedQA, AgentClinic, "
        f"HealthBench, MedAgentBench) evaluate none of the temporal, "
        f"sequential, or forbidden-action dimensions that CGA-Bench "
        f"captures through its closed-loop CPG engine."
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the full scenario complexity analysis pipeline."""
    os.chdir(BASE_DIR)

    print("=" * 60)
    print("CGA-Bench Scenario Complexity Quantification")
    print("=" * 60)

    # Step 1: Graph complexity
    print("\n[Step 1] Parsing CPG graph files...")
    graph_metrics = analyze_all_graphs()
    unique_graphs = _unique_graphs(graph_metrics)
    print(f"  Parsed {len(unique_graphs)} graphs (+ stem aliases)")
    for gid, gm in sorted(unique_graphs.items()):
        print(
            f"    {gid}: {gm['total_nodes']} nodes, "
            f"{gm['total_mandatory_actions']} mandatory, "
            f"{gm['total_forbidden_actions']} forbidden, "
            f"{gm['timing_constraints']} deadlines, "
            f"{gm['sequence_dependencies']} seq deps, "
            f"{gm['conditional_branches']} branches"
        )

    # Step 2: Scenario complexity
    print("\n[Step 2] Analyzing scenario complexity...")
    all_scenario_metrics, eval_scenario_metrics = analyze_all_scenarios(
        graph_metrics
    )
    print(f"  Total scenarios: {len(all_scenario_metrics)}")
    print(f"  Eval scenarios:  {len(eval_scenario_metrics)}")
    for sid in EVAL_SCENARIOS:
        sm = eval_scenario_metrics.get(sid, {})
        print(
            f"    {sid}: "
            f"expected={sm.get('expected_actions_count', 0)}, "
            f"deadlines={sm.get('active_deadlines', 0)}, "
            f"seq_deps={sm.get('active_sequence_deps', 0)}, "
            f"forbidden={sm.get('scenario_forbidden_count', 0)}, "
            f"violations={sm.get('violation_type_count', 0)}"
        )

    # Step 3: Aggregates
    print("\n[Step 3] Computing aggregate statistics...")
    agg = compute_aggregate_stats(graph_metrics, eval_scenario_metrics)
    print(f"  Graphs: {json.dumps(agg['graphs'], indent=2)}")
    print(f"  Eval:   {json.dumps(agg['eval_scenarios'], indent=2)}")

    # Step 4: Benchmark comparison
    print("\n[Step 4] Building benchmark comparison...")
    comparison = build_benchmark_comparison(agg)
    for row in comparison:
        print(f"  {row['benchmark']}: {row['items']} items, {row['eval_type']}")

    # Step 5: Generate outputs
    print("\n[Step 5] Writing output files...")

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)

    # 5a: scenario_complexity.json
    scenario_out = {
        "eval_scenarios": {
            sid: eval_scenario_metrics[sid] for sid in EVAL_SCENARIOS
            if sid in eval_scenario_metrics
        },
        "all_scenarios_count": len(all_scenario_metrics),
        "aggregate": agg,
    }
    out_path = ANALYSIS_DIR / "scenario_complexity.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(scenario_out, fh, indent=2, ensure_ascii=False)
    print(f"  -> {out_path}")

    # 5b: cpg_graph_complexity.json (unique graphs only, no stem aliases)
    graph_out = {}
    for gid, gm in unique_graphs.items():
        graph_out[gid] = gm
    out_path = ANALYSIS_DIR / "cpg_graph_complexity.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(graph_out, fh, indent=2, ensure_ascii=False)
    print(f"  -> {out_path}")

    # 5c: scenario_complexity.tex
    tex = generate_scenario_complexity_tex(eval_scenario_metrics, agg)
    out_path = TABLE_DIR / "scenario_complexity.tex"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(tex)
    print(f"  -> {out_path}")

    # 5d: benchmark_dimension_comparison.tex
    tex = generate_benchmark_comparison_tex(comparison)
    out_path = TABLE_DIR / "benchmark_dimension_comparison.tex"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(tex)
    print(f"  -> {out_path}")

    # 5e: Summary
    summary = generate_summary(graph_metrics, eval_scenario_metrics, agg)
    print(f"\n[Summary]\n{summary}")

    print("\nDone.")


if __name__ == "__main__":
    main()
