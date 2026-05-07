#!/usr/bin/env python3
"""Extract constraint counts from CPG graph YAML files and update auto_numbers.tex.

Usage:
    python scripts/extract_constraint_counts.py \
        --graphs-dir cpg_model/graphs \
        --scenarios-dir configs/scenarios \
        --auto-generated configs/scenarios/auto_generated_scenarios.yaml \
        --output paper/auto_numbers.tex

Fills these macros:
    numForbidden, numMust, numShould, numBefore, numWithin, numShouldWithin,
    numHardConstraints, numSoftConstraints, numTotalConstraints,
    avgManualConstraints, avgEngineConstraints, expansionRatio,
    numExtraForbidden, numExtraRequired, numExtraBefore, numExtraWithin,
    numExtraAll, precForbidden, precRequired, precBefore, precWithin, precAll
"""

import argparse
from collections import Counter
import glob
import json
import os
import re

import yaml


def load_yaml(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def count_graph_constraints(graph_path: str) -> dict:
    """Count constraint types from a single CPG graph YAML."""
    g = load_yaml(graph_path)
    counts = Counter()

    # Count from nodes
    nodes = g.get("nodes", [])
    if isinstance(nodes, dict):
        nodes = list(nodes.values())

    for node in nodes:
        if not isinstance(node, dict):
            continue

        # Forbidden actions (from node-level forbidden_actions)
        forbidden = node.get("forbidden_actions", [])
        if isinstance(forbidden, list):
            counts["forbidden"] += len(forbidden)

        # Required actions (mandatory = hard MUST, optional = soft SHOULD)
        mandatory = node.get("mandatory_actions", [])
        if isinstance(mandatory, list):
            counts["must"] += len(mandatory)

        optional = node.get("optional_actions", [])
        if isinstance(optional, list):
            counts["should"] += len(optional)

        # Deadlines (WITHIN constraints)
        deadlines = node.get("deadlines", {})
        if isinstance(deadlines, dict):
            for action, dl in deadlines.items():
                if isinstance(dl, dict):
                    strength = dl.get("evidence_strength", "").upper()
                    if strength in ("HIGH", "STRONG", "I", "IA", "IB"):
                        counts["within_hard"] += 1
                    else:
                        counts["within_soft"] += 1
                else:
                    counts["within_hard"] += 1  # default to hard

        # Node-level sequence_rules (BEFORE constraints)
        node_seq = node.get("sequence_rules", [])
        if isinstance(node_seq, list):
            counts["before"] += len(node_seq)

        # Node-level required_prior_actions (BEFORE constraints)
        req_prior = node.get("required_prior_actions", {})
        if isinstance(req_prior, dict):
            for action, priors in req_prior.items():
                if isinstance(priors, list):
                    counts["before"] += len(priors)

        # Node-level conditional_rules
        node_cond = node.get("conditional_rules", [])
        if isinstance(node_cond, list):
            for rule in node_cond:
                if not isinstance(rule, dict):
                    continue
                ct = rule.get("constraint_type", "").upper()
                if ct == "FORBIDDEN":
                    counts["forbidden"] += 1
                elif ct == "REQUIRED":
                    strength = rule.get("evidence_strength", "").upper()
                    if strength in ("HIGH", "STRONG", "I", "IA", "IB", "MUST"):
                        counts["must"] += 1
                    else:
                        counts["should"] += 1
                elif ct == "BEFORE":
                    counts["before"] += 1
                elif ct == "WITHIN":
                    counts["within_hard"] += 1

    # Top-level sequence rules (BEFORE constraints) — if any exist at graph root
    seq_rules = g.get("sequence_rules", [])
    if isinstance(seq_rules, list):
        counts["before"] += len(seq_rules)

    # Top-level conditional_rules
    cond_rules = g.get("conditional_rules", [])
    if isinstance(cond_rules, list):
        for rule in cond_rules:
            if not isinstance(rule, dict):
                continue
            constraint_type = rule.get("constraint_type", "").upper()
            if constraint_type == "FORBIDDEN":
                counts["forbidden"] += 1
            elif constraint_type == "REQUIRED":
                strength = rule.get("evidence_strength", "").upper()
                if strength in ("HIGH", "STRONG", "I", "IA", "IB", "MUST"):
                    counts["must"] += 1
                else:
                    counts["should"] += 1
            elif constraint_type == "BEFORE":
                counts["before"] += 1
            elif constraint_type == "WITHIN":
                counts["within_hard"] += 1

    # Count from global forbidden
    global_forbidden = g.get("global_forbidden_actions", [])
    if isinstance(global_forbidden, list):
        counts["forbidden"] += len(global_forbidden)

    return counts


def count_scenario_constraints(scenario: dict) -> dict:
    """Count constraints specified in a single scenario YAML entry."""
    counts = Counter()

    forbidden = scenario.get("forbidden_actions", [])
    if isinstance(forbidden, list):
        counts["forbidden"] += len(forbidden)

    expected = scenario.get("expected_actions", [])
    if isinstance(expected, list):
        counts["must"] += len(expected)

    before = scenario.get("before_constraints", [])
    if isinstance(before, list):
        counts["before"] += len(before)

    within = scenario.get("within_constraints", [])
    if isinstance(within, list):
        counts["within"] += len(within)

    return counts


def _count_graph_level_constraints(graph_path: str) -> int:
    """Count total constraints (forbidden + mandatory + deadlines) in a graph."""
    g = load_yaml(graph_path)
    total = 0
    nodes = g.get("nodes", [])
    if isinstance(nodes, dict):
        nodes = list(nodes.values())
    for node in nodes:
        if not isinstance(node, dict):
            continue
        total += len(node.get("forbidden_actions", []))
        total += len(node.get("mandatory_actions", []))
        total += len(node.get("deadlines", {}))
    return total


def analyze_engine_vs_manual(manual_scenarios_dir: str, auto_scenarios_file: str, graphs_dir: str) -> dict:
    """Compare author-specified constraints vs engine-derived graph constraints.

    Manual authors specify expected_actions (avg ~6-7 per scenario).
    The linked CPG graph contains the full constraint set (forbidden +
    mandatory + deadlines), which is what the engine derives. The expansion
    ratio measures how many more constraints the engine produces vs what
    the human author explicitly listed.
    """
    manual_author = []  # author-specified expected_actions count
    manual_engine = []  # graph-level constraint count for same scenario

    for f in sorted(glob.glob(os.path.join(manual_scenarios_dir, "*.yaml"))):
        if "auto_generated" in f:
            continue
        data = load_yaml(f)
        scenarios = data.get("scenarios", {})
        if not isinstance(scenarios, dict):
            continue
        for sid, s in scenarios.items():
            if not isinstance(s, dict):
                continue
            ea = s.get("expected_actions", [])
            graph_name = s.get("guideline_graph", "")
            if not ea or not graph_name:
                continue
            graph_path = os.path.join(graphs_dir, f"{graph_name}.yaml")
            if not os.path.exists(graph_path):
                continue
            n_author = len(ea)
            n_engine = _count_graph_level_constraints(graph_path)
            manual_author.append(n_author)
            manual_engine.append(n_engine)

    n = len(manual_author)
    avg_author = sum(manual_author) / max(n, 1)
    avg_engine = sum(manual_engine) / max(n, 1)
    ratio = avg_engine / max(avg_author, 0.001)

    return {
        "avg_manual": round(avg_author, 1),
        "avg_auto": round(avg_engine, 1),
        "ratio": round(ratio, 1),
        "n_manual": n,
        "n_auto": n,
    }


def compute_extra_constraints(
    manual_scenarios_dir: str, auto_scenarios_file: str, graphs_dir: str = "cpg_model/graphs"
) -> dict:
    """Compute engine-only constraints by type (for Table constraint_type_precision).

    Manual authors specify only expected_actions (MUST type).
    All FORBIDDEN, BEFORE, WITHIN constraints are engine-only.
    Extra REQUIRED = graph-level MUST - author-specified expected_actions.
    Precision values require exp_b_constraint_type_precision.py (left as ??).
    """
    from collections import defaultdict

    graph_author_must = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(manual_scenarios_dir, "*.yaml"))):
        if "auto_generated" in f:
            continue
        data = load_yaml(f)
        scenarios = data.get("scenarios", {})
        if not isinstance(scenarios, dict):
            continue
        for sid, s in scenarios.items():
            if not isinstance(s, dict):
                continue
            graph_name = s.get("guideline_graph", "")
            ea = s.get("expected_actions", [])
            if graph_name and ea:
                graph_author_must[graph_name].append(len(ea))

    extra = {"forbidden": 0, "required": 0, "before": 0, "within": 0}
    for graph_name, author_counts in graph_author_must.items():
        gpath = os.path.join(graphs_dir, f"{graph_name}.yaml")
        if not os.path.exists(gpath):
            continue
        g = load_yaml(gpath)
        nodes = g.get("nodes", [])
        if isinstance(nodes, dict):
            nodes = list(nodes.values())
        g_forbidden, g_must, g_within = 0, 0, 0
        for node in nodes:
            if not isinstance(node, dict):
                continue
            g_forbidden += len(node.get("forbidden_actions", []))
            g_must += len(node.get("mandatory_actions", []))
            g_within += len(node.get("deadlines", {}))
        g_before = len(g.get("sequence_rules", []))
        for n_author in author_counts:
            extra["forbidden"] += g_forbidden
            extra["required"] += max(g_must - n_author, 0)
            extra["before"] += g_before
            extra["within"] += g_within

    total = sum(extra.values())
    return {
        "extra_forbidden": extra["forbidden"],
        "extra_required": extra["required"],
        "extra_before": extra["before"],
        "extra_within": extra["within"],
        "extra_all": total,
        "prec_forbidden": "??",
        "prec_required": "??",
        "prec_before": "??",
        "prec_within": "??",
        "prec_all": "??",
    }


def update_auto_numbers(tex_path: str, updates: dict):
    """Update specific \\newcommand values in auto_numbers.tex."""
    with open(tex_path) as f:
        content = f.read()

    for macro_name, value in updates.items():
        # Match \newcommand{\macroName}{value}
        pattern = rf"(\\newcommand{{\\{macro_name}}})\{{[^}}]*\}}"
        replacement = rf"\1{{{value}}}"
        content, n = re.subn(pattern, replacement, content)
        if n == 0:
            print(f"  WARNING: macro \\{macro_name} not found in {tex_path}")

    with open(tex_path, "w") as f:
        f.write(content)


def main():
    parser = argparse.ArgumentParser(description="Extract constraint counts from CPG graphs")
    parser.add_argument("--graphs-dir", default="cpg_model/graphs")
    parser.add_argument("--scenarios-dir", default="configs/scenarios")
    parser.add_argument("--auto-generated", default="configs/scenarios/auto_generated_scenarios.yaml")
    parser.add_argument("--output", default="paper/auto_numbers.tex")
    parser.add_argument("--dry-run", action="store_true", help="Print values without updating file")
    args = parser.parse_args()

    # Aggregate counts across all graphs
    total = Counter()
    graph_files = sorted(glob.glob(os.path.join(args.graphs_dir, "*.yaml")))
    # Exclude _archive
    graph_files = [f for f in graph_files if "_archive" not in f]

    print(f"Processing {len(graph_files)} graph files...")
    for gf in graph_files:
        counts = count_graph_constraints(gf)
        total += counts
        name = os.path.basename(gf)
        print(
            f"  {name}: F={counts['forbidden']} M={counts['must']} S={counts['should']} "
            f"B={counts['before']} W_h={counts['within_hard']} W_s={counts['within_soft']}"
        )

    hard = total["forbidden"] + total["must"] + total["before"] + total["within_hard"]
    soft = total["should"] + total["within_soft"]
    total_all = hard + soft

    print("\n=== TOTALS ===")
    print(f"FORBIDDEN:     {total['forbidden']}")
    print(f"MUST (hard):   {total['must']}")
    print(f"SHOULD (soft): {total['should']}")
    print(f"BEFORE:        {total['before']}")
    print(f"WITHIN (hard): {total['within_hard']}")
    print(f"WITHIN (soft): {total['within_soft']}")
    print(f"--- Hard: {hard}  Soft: {soft}  Total: {total_all}")

    # Engine vs Manual comparison
    comparison = analyze_engine_vs_manual(args.scenarios_dir, args.auto_generated, args.graphs_dir)
    print("\n=== ENGINE vs MANUAL ===")
    print(f"Avg manual constraints/scenario: {comparison['avg_manual']} (n={comparison['n_manual']})")
    print(f"Avg engine constraints/scenario: {comparison['avg_auto']} (n={comparison['n_auto']})")
    print(f"Expansion ratio: {comparison['ratio']}x")

    # Extra constraints analysis
    extras = compute_extra_constraints(args.scenarios_dir, args.auto_generated, args.graphs_dir)

    # Prepare update dict
    updates = {
        "numForbidden": total["forbidden"],
        "numMust": total["must"],
        "numShould": total["should"],
        "numBefore": total["before"],
        "numWithin": total["within_hard"],
        "numShouldWithin": total["within_soft"],
        "numHardConstraints": hard,
        "numSoftConstraints": soft,
        "numTotalConstraints": total_all,
        "avgManualConstraints": comparison["avg_manual"],
        "avgEngineConstraints": comparison["avg_auto"],
        "expansionRatio": comparison["ratio"],
        "numExtraForbidden": extras["extra_forbidden"],
        "numExtraRequired": extras["extra_required"],
        "numExtraBefore": extras["extra_before"],
        "numExtraWithin": extras["extra_within"],
        "numExtraAll": extras["extra_all"],
        "precForbidden": extras["prec_forbidden"],
        "precRequired": extras["prec_required"],
        "precBefore": extras["prec_before"],
        "precWithin": extras["prec_within"],
        "precAll": extras["prec_all"],
    }

    if args.dry_run:
        print(f"\n=== DRY RUN: Would update {len(updates)} macros ===")
        for k, v in updates.items():
            print(f"  \\{k} = {v}")
    else:
        update_auto_numbers(args.output, updates)
        print(f"\n✅ Updated {len(updates)} macros in {args.output}")

    # Also output as JSON for downstream scripts
    result = {
        "constraint_counts": dict(total),
        "hard": hard,
        "soft": soft,
        "total": total_all,
        "comparison": comparison,
        "extras": extras,
    }
    json_path = os.path.splitext(args.output)[0] + "_constraints.json"
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"📄 JSON saved to {json_path}")


if __name__ == "__main__":
    main()
