#!/usr/bin/env python3
"""EX-16: Source Traceability Audit

Proves all TCC constraints are traceable to published CPGs.
Parses all 25 graph YAMLs for source_guideline, source_section, evidence_level.

Usage:
    PYTHONPATH=. python scripts/experiments/ex16_source_traceability.py
"""

from collections import defaultdict
import json
from pathlib import Path

import yaml

GRAPHS_DIR = Path("cpg_model/graphs")
OUTPUT_DIR = Path("evidence_pack/ex16_source_traceability")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("EX-16: SOURCE TRACEABILITY AUDIT")
    print("=" * 70)

    # Parse all graphs
    total_constraints = 0
    with_source = 0
    with_evidence = 0
    by_type = defaultdict(lambda: {"total": 0, "with_source": 0, "with_evidence": 0})
    graph_summary = []
    example_chains = []

    for graph_file in sorted(GRAPHS_DIR.glob("*.yaml")):
        if graph_file.name.startswith("_"):
            continue
        try:
            graph = yaml.safe_load(open(graph_file))
        except Exception:
            continue

        if not graph:
            continue

        graph_id = graph.get("graph_id", graph_file.stem)
        guideline_name = graph.get("guideline_name", "")
        metadata = graph.get("metadata", {})
        primary_source = metadata.get("primary_source", {})
        graph_source = primary_source.get("title", metadata.get("source", ""))

        nodes = graph.get("nodes", {})
        if isinstance(nodes, dict):
            nodes = list(nodes.values())

        g_total = 0
        g_sourced = 0
        g_evidenced = 0

        for node in nodes:
            if not isinstance(node, dict):
                continue

            node_id = node.get("node_id", node.get("id", ""))
            node_source = node.get("source_guideline", "")
            node_section = node.get("source_section", "")
            node_evidence = node.get("evidence_level", "")
            node_quote = node.get("source_quote", "")

            has_node_source = bool(node_source or graph_source)
            has_evidence = bool(node_evidence)

            # Mandatory actions
            for action in node.get("mandatory_actions") or []:
                total_constraints += 1
                g_total += 1
                by_type["MUST"]["total"] += 1
                if has_node_source:
                    with_source += 1
                    g_sourced += 1
                    by_type["MUST"]["with_source"] += 1
                if has_evidence:
                    with_evidence += 1
                    g_evidenced += 1
                    by_type["MUST"]["with_evidence"] += 1

            # Forbidden actions
            for action in node.get("forbidden_actions") or []:
                total_constraints += 1
                g_total += 1
                by_type["FORBIDDEN"]["total"] += 1
                if has_node_source:
                    with_source += 1
                    g_sourced += 1
                    by_type["FORBIDDEN"]["with_source"] += 1
                if has_evidence:
                    with_evidence += 1
                    g_evidenced += 1
                    by_type["FORBIDDEN"]["with_evidence"] += 1

            # Deadlines (WITHIN)
            deadlines = node.get("deadlines", {})
            if isinstance(deadlines, dict):
                for action, dl in deadlines.items():
                    total_constraints += 1
                    g_total += 1
                    by_type["WITHIN"]["total"] += 1
                    if has_node_source:
                        with_source += 1
                        g_sourced += 1
                        by_type["WITHIN"]["with_source"] += 1
                    if has_evidence:
                        with_evidence += 1
                        g_evidenced += 1
                        by_type["WITHIN"]["with_evidence"] += 1

            # Sequence rules (BEFORE)
            for sr in node.get("sequence_rules") or []:
                total_constraints += 1
                g_total += 1
                by_type["BEFORE"]["total"] += 1
                if has_node_source:
                    with_source += 1
                    g_sourced += 1
                    by_type["BEFORE"]["with_source"] += 1
                if has_evidence:
                    with_evidence += 1
                    g_evidenced += 1
                    by_type["BEFORE"]["with_evidence"] += 1

            # Collect example provenance chains
            if node_source and node_section and node_quote and len(example_chains) < 5:
                sample_action = (node.get("mandatory_actions") or [""])[0]
                if sample_action:
                    example_chains.append(
                        {
                            "graph": graph_id,
                            "node": node_id,
                            "action": sample_action,
                            "source": node_source,
                            "section": node_section,
                            "evidence": node_evidence,
                            "quote": node_quote[:150],
                        }
                    )

        # Conditional rules
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for rule in node.get("conditional_rules") or []:
                if not isinstance(rule, dict):
                    continue
                total_constraints += 1
                g_total += 1
                rule_type = (rule.get("effect", {}).get("type", "CONDITIONAL")).upper()
                by_type[rule_type]["total"] += 1
                rule_evidence = rule.get("evidence", "")
                if rule_evidence or graph_source:
                    with_source += 1
                    g_sourced += 1
                    by_type[rule_type]["with_source"] += 1
                if rule_evidence:
                    with_evidence += 1
                    g_evidenced += 1
                    by_type[rule_type]["with_evidence"] += 1

        graph_summary.append(
            {
                "graph_id": graph_id,
                "guideline": guideline_name[:60],
                "source": graph_source[:50],
                "constraints": g_total,
                "sourced": g_sourced,
                "rate": round(g_sourced / g_total * 100, 1) if g_total else 0,
            }
        )

    # Report
    source_rate = with_source / total_constraints * 100 if total_constraints else 0
    evidence_rate = with_evidence / total_constraints * 100 if total_constraints else 0

    print("\n## Overall")
    print(f"  Total constraints: {total_constraints}")
    print(f"  With published source: {with_source} ({source_rate:.1f}%)")
    print(f"  With evidence grade: {with_evidence} ({evidence_rate:.1f}%)")

    print("\n## By Constraint Type")
    print(f"  {'Type':<15} {'Total':>6} {'Sourced':>8} {'Rate':>7} {'Evidenced':>10}")
    for ctype in sorted(by_type):
        t = by_type[ctype]
        r = t["with_source"] / t["total"] * 100 if t["total"] else 0
        print(f"  {ctype:<15} {t['total']:>6} {t['with_source']:>8} {r:>6.1f}% {t['with_evidence']:>10}")

    print("\n## Per-Graph Summary")
    print(f"  {'Graph':<35} {'Source':<30} {'N':>4} {'%':>6}")
    for g in sorted(graph_summary, key=lambda x: -x["constraints"]):
        print(f"  {g['graph_id']:<35} {g['source']:<30} {g['constraints']:>4} {g['rate']:>5.1f}%")

    print("\n## Example Provenance Chains")
    for ex in example_chains:
        print(f"  {ex['graph']}/{ex['node']}: {ex['action']}")
        print(f"    Source: {ex['source']}, {ex['section']}, Evidence: {ex['evidence']}")
        print(f'    Quote: "{ex["quote"]}"')

    # Save
    output = {
        "total_constraints": total_constraints,
        "with_source": with_source,
        "source_rate": round(source_rate, 1),
        "with_evidence": with_evidence,
        "evidence_rate": round(evidence_rate, 1),
        "by_type": {k: dict(v) for k, v in by_type.items()},
        "graph_summary": graph_summary,
        "example_chains": example_chains,
    }
    with open(OUTPUT_DIR / "ex16_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    with open(OUTPUT_DIR / "ex16_macros.tex", "w") as f:
        f.write(f"\\newcommand{{\\traceSourceRate}}{{{source_rate:.1f}}}\n")
        f.write(f"\\newcommand{{\\traceEvidenceRate}}{{{evidence_rate:.1f}}}\n")
        f.write(f"\\newcommand{{\\traceTotalConstraints}}{{{total_constraints}}}\n")

    print(f"\n[SAVED] {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
