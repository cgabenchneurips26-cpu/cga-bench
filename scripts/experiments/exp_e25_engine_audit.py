#!/usr/bin/env python3
"""EX-25: Engine Structural Audit — structural soundness of CPG graphs.

Audits all 25 CPG graphs across 6 dimensions:
  1. Unreachable nodes (BFS from entry_node)
  2. Dead-end nodes (no outgoing transitions)
  3. Contradictory constraints (action in both mandatory + forbidden)
  4. Duplicate constraints (same graph/action/type triplet)
  5. Provenance completeness (source_guideline + evidence_level)
  6. Constraint density and coverage metrics

Output: evidence_pack/ex25_engine_audit/
Macros: auditTotalRules, auditUnreachableRate, etc.

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_e25_engine_audit.py
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._common import save_json, save_markdown

GRAPHS_DIR = ROOT / "cpg_model" / "graphs"
OUTPUT_DIR = ROOT / "evidence_pack" / "ex25_engine_audit"

# Constraint types extracted from graph nodes
CONSTRAINT_TYPES = ("MUST", "FORBIDDEN", "WITHIN", "BEFORE")


# ---------------------------------------------------------------------------
# Graph parsing
# ---------------------------------------------------------------------------


def load_graph(path: Path) -> dict:
    """Load a single CPG graph YAML."""
    return yaml.safe_load(path.read_text())


def extract_constraints(graph: dict) -> list[dict]:
    """Extract all constraints from a graph's nodes.

    Constraint types:
      MUST:      one per mandatory_action
      FORBIDDEN: one per forbidden_action
      WITHIN:    one per deadline entry (action + minutes)
      BEFORE:    one per required_prior_actions entry
    """
    constraints: list[dict] = []
    graph_id = graph.get("graph_id", "unknown")
    nodes = graph.get("nodes", {})

    for node_id, node in nodes.items():
        # MUST constraints
        for action in node.get("mandatory_actions", []) or []:
            constraints.append(
                {
                    "graph_id": graph_id,
                    "node_id": node_id,
                    "type": "MUST",
                    "action": action,
                    "detail": None,
                }
            )

        # FORBIDDEN constraints
        for action in node.get("forbidden_actions", []) or []:
            constraints.append(
                {
                    "graph_id": graph_id,
                    "node_id": node_id,
                    "type": "FORBIDDEN",
                    "action": action,
                    "detail": None,
                }
            )

        # WITHIN constraints (deadlines)
        for action, minutes in (node.get("deadlines", {}) or {}).items():
            constraints.append(
                {
                    "graph_id": graph_id,
                    "node_id": node_id,
                    "type": "WITHIN",
                    "action": action,
                    "detail": minutes,
                }
            )

        # BEFORE constraints (required_prior_actions)
        for action, prereqs in (node.get("required_prior_actions", {}) or {}).items():
            if not prereqs:
                continue
            for prereq in prereqs:
                constraints.append(
                    {
                        "graph_id": graph_id,
                        "node_id": node_id,
                        "type": "BEFORE",
                        "action": action,
                        "detail": prereq,
                    }
                )

        # BEFORE constraints (sequence_rules: list of [prereq, action] pairs)
        for seq_rule in node.get("sequence_rules", []) or []:
            if isinstance(seq_rule, list) and len(seq_rule) >= 2:
                constraints.append(
                    {
                        "graph_id": graph_id,
                        "node_id": node_id,
                        "type": "BEFORE",
                        "action": seq_rule[1],
                        "detail": seq_rule[0],
                    }
                )

    return constraints


# ---------------------------------------------------------------------------
# Audit dimensions
# ---------------------------------------------------------------------------


def audit_reachability(graph: dict) -> dict:
    """Dimension 1+2: Unreachable and dead-end nodes via BFS."""
    nodes = graph.get("nodes", {})
    entry = graph.get("entry_node", "")
    n_nodes = len(nodes)

    if n_nodes == 0:
        return {"n_nodes": 0, "unreachable": 0, "dead_ends": 0, "unreachable_ids": [], "dead_end_ids": []}

    # BFS from entry_node
    visited: set[str] = set()
    queue = [entry] if entry in nodes else []
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        node = nodes.get(current, {})
        # Follow next_nodes
        for nxt in node.get("next_nodes", []) or []:
            if nxt in nodes and nxt not in visited:
                queue.append(nxt)
        # Follow conditional_next
        for _cond, nxt in (node.get("conditional_next", {}) or {}).items():
            if nxt in nodes and nxt not in visited:
                queue.append(nxt)

    unreachable_ids = sorted(set(nodes.keys()) - visited)

    # Dead-end: no outgoing edges
    dead_end_ids = []
    for node_id, node in nodes.items():
        has_next = bool(node.get("next_nodes", []))
        has_cond = bool(node.get("conditional_next", {}))
        if not has_next and not has_cond:
            dead_end_ids.append(node_id)

    return {
        "n_nodes": n_nodes,
        "unreachable": len(unreachable_ids),
        "dead_ends": len(dead_end_ids),
        "unreachable_ids": unreachable_ids,
        "dead_end_ids": sorted(dead_end_ids),
    }


def audit_contradictions(graph: dict) -> list[dict]:
    """Dimension 3: Actions in both mandatory and forbidden within same node."""
    contradictions: list[dict] = []
    graph_id = graph.get("graph_id", "unknown")
    nodes = graph.get("nodes", {})

    for node_id, node in nodes.items():
        mandatory = set(node.get("mandatory_actions", []) or [])
        forbidden = set(node.get("forbidden_actions", []) or [])
        overlap = mandatory & forbidden
        for action in sorted(overlap):
            contradictions.append(
                {
                    "graph_id": graph_id,
                    "node_id": node_id,
                    "action": action,
                }
            )

    return contradictions


def audit_duplicates(constraints: list[dict]) -> list[dict]:
    """Dimension 4: Duplicate constraints within same graph."""
    seen: dict[tuple, dict] = {}
    duplicates: list[dict] = []

    for c in constraints:
        key = (c["graph_id"], c["type"], c["action"], str(c["detail"]))
        if key in seen:
            duplicates.append(
                {
                    "graph_id": c["graph_id"],
                    "type": c["type"],
                    "action": c["action"],
                    "node_id": c["node_id"],
                    "first_node": seen[key]["node_id"],
                }
            )
        else:
            seen[key] = c

    return duplicates


def audit_provenance(graph: dict) -> dict:
    """Dimension 5: Provenance completeness of nodes."""
    nodes = graph.get("nodes", {})
    n_nodes = len(nodes)
    complete = 0
    missing_fields: list[dict] = []

    provenance_fields = ["source_guideline", "evidence_level"]

    for node_id, node in nodes.items():
        has_all = True
        missing = []
        for field in provenance_fields:
            val = node.get(field)
            if not val or str(val).strip() in ("", "null", "None"):
                has_all = False
                missing.append(field)
        if has_all:
            complete += 1
        elif missing:
            missing_fields.append({"node_id": node_id, "missing": missing})

    return {
        "n_nodes": n_nodes,
        "complete": complete,
        "rate": round(complete / max(n_nodes, 1) * 100, 1),
        "missing_details": missing_fields[:10],
    }


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def run_audit() -> dict:
    """Run all audit dimensions across all graphs."""
    graph_files = sorted(GRAPHS_DIR.glob("*.yaml"))
    print(f"  Found {len(graph_files)} graph files")

    all_constraints: list[dict] = []
    per_graph: dict[str, dict] = {}

    total_nodes = 0
    total_unreachable = 0
    total_dead_ends = 0
    total_contradictions = 0
    total_provenance_complete = 0
    total_provenance_nodes = 0

    for gf in graph_files:
        graph = load_graph(gf)
        graph_id = graph.get("graph_id", gf.stem)

        # Extract constraints
        constraints = extract_constraints(graph)
        all_constraints.extend(constraints)

        # Constraint type counts
        type_counts: Counter[str] = Counter()
        for c in constraints:
            type_counts[c["type"]] += 1

        # Reachability
        reach = audit_reachability(graph)
        total_nodes += reach["n_nodes"]
        total_unreachable += reach["unreachable"]
        total_dead_ends += reach["dead_ends"]

        # Contradictions
        contras = audit_contradictions(graph)
        total_contradictions += len(contras)

        # Provenance
        prov = audit_provenance(graph)
        total_provenance_complete += prov["complete"]
        total_provenance_nodes += prov["n_nodes"]

        per_graph[graph_id] = {
            "n_nodes": reach["n_nodes"],
            "n_constraints": len(constraints),
            "constraint_types": dict(type_counts),
            "unreachable": reach["unreachable"],
            "unreachable_ids": reach["unreachable_ids"],
            "dead_ends": reach["dead_ends"],
            "dead_end_ids": reach["dead_end_ids"],
            "contradictions": len(contras),
            "contradiction_details": contras,
            "provenance_rate": prov["rate"],
        }

    # Global duplicates
    duplicates = audit_duplicates(all_constraints)

    # Constraint type distribution
    global_type_counts: Counter[str] = Counter()
    for c in all_constraints:
        global_type_counts[c["type"]] += 1

    # Unique actions across all graphs
    unique_actions = len({c["action"] for c in all_constraints})

    # Compute rates
    n_graphs = len(graph_files)
    unreachable_rate = round(total_unreachable / max(total_nodes, 1) * 100, 1)
    dead_end_rate = round(total_dead_ends / max(total_nodes, 1) * 100, 1)
    contradiction_rate = round(total_contradictions / max(len(all_constraints), 1) * 100, 2)
    duplicate_rate = round(len(duplicates) / max(len(all_constraints), 1) * 100, 1)
    provenance_rate = round(total_provenance_complete / max(total_provenance_nodes, 1) * 100, 1)

    # Graphs with issues
    graphs_with_unreachable = sum(1 for g in per_graph.values() if g["unreachable"] > 0)
    graphs_with_contradictions = sum(1 for g in per_graph.values() if g["contradictions"] > 0)

    return {
        "n_graphs": n_graphs,
        "n_total_nodes": total_nodes,
        "n_total_constraints": len(all_constraints),
        "n_unique_actions": unique_actions,
        "constraint_type_distribution": dict(global_type_counts),
        "constraints_per_node": round(len(all_constraints) / max(total_nodes, 1), 1),
        "audit_results": {
            "unreachable_nodes": total_unreachable,
            "unreachable_rate": unreachable_rate,
            "graphs_with_unreachable": graphs_with_unreachable,
            "dead_end_nodes": total_dead_ends,
            "dead_end_rate": dead_end_rate,
            "contradictions": total_contradictions,
            "contradiction_rate": contradiction_rate,
            "graphs_with_contradictions": graphs_with_contradictions,
            "duplicates": len(duplicates),
            "duplicate_rate": duplicate_rate,
            "duplicate_details": duplicates[:20],
            "provenance_complete_nodes": total_provenance_complete,
            "provenance_total_nodes": total_provenance_nodes,
            "provenance_rate": provenance_rate,
        },
        "per_graph": per_graph,
    }


def generate_markdown(results: dict) -> str:
    ar = results["audit_results"]
    lines = [
        "# EX-25: Engine Structural Audit",
        "",
        f"**Graphs:** {results['n_graphs']}",
        f"**Nodes:** {results['n_total_nodes']}",
        f"**Constraints:** {results['n_total_constraints']}",
        f"**Unique actions:** {results['n_unique_actions']}",
        f"**Constraints/node:** {results['constraints_per_node']}",
        "",
        "## Constraint Type Distribution",
        "",
        "| Type | Count | % |",
        "|------|-------|---|",
    ]
    total_c = results["n_total_constraints"]
    for ct in CONSTRAINT_TYPES:
        cnt = results["constraint_type_distribution"].get(ct, 0)
        pct = round(cnt / max(total_c, 1) * 100, 1)
        lines.append(f"| {ct} | {cnt} | {pct}% |")

    lines.extend(
        [
            "",
            "## Audit Results",
            "",
            "| Dimension | Count | Rate | Status |",
            "|-----------|-------|------|--------|",
            f"| Unreachable nodes | {ar['unreachable_nodes']} | {ar['unreachable_rate']}% "
            f"| {'CLEAN' if ar['unreachable_nodes'] == 0 else 'WARN'} |",
            f"| Dead-end nodes | {ar['dead_end_nodes']} | {ar['dead_end_rate']}% | INFO (legitimate terminals) |",
            f"| Contradictions | {ar['contradictions']} | {ar['contradiction_rate']}% "
            f"| {'CLEAN' if ar['contradictions'] == 0 else 'FAIL'} |",
            f"| Duplicates | {ar['duplicates']} | {ar['duplicate_rate']}% "
            f"| {'CLEAN' if ar['duplicates'] == 0 else 'WARN'} |",
            f"| Provenance complete | {ar['provenance_complete_nodes']}/{ar['provenance_total_nodes']} "
            f"| {ar['provenance_rate']}% | {'CLEAN' if ar['provenance_rate'] >= 95 else 'WARN'} |",
        ]
    )

    lines.extend(
        [
            "",
            "## Per-Graph Summary (sorted by constraint count)",
            "",
            "| Graph | Nodes | Constraints | Unreach | Dead | Contra | Prov% |",
            "|-------|-------|-------------|---------|------|--------|-------|",
        ]
    )
    sorted_graphs = sorted(results["per_graph"].items(), key=lambda x: x[1]["n_constraints"], reverse=True)
    for gid, pg in sorted_graphs:
        lines.append(
            f"| {gid} | {pg['n_nodes']} | {pg['n_constraints']} | "
            f"{pg['unreachable']} | {pg['dead_ends']} | "
            f"{pg['contradictions']} | {pg['provenance_rate']}% |"
        )

    if ar["duplicates"] > 0:
        lines.extend(
            [
                "",
                "## Duplicate Details (first 20)",
                "",
            ]
        )
        for d in ar["duplicate_details"][:20]:
            lines.append(f"- {d['graph_id']}: {d['type']}({d['action']}) in {d['first_node']} and {d['node_id']}")

    return "\n".join(lines)


def generate_macros(results: dict) -> str:
    ar = results["audit_results"]
    lines = [
        "",
        "% ---------------------------------------------------------------------------",
        "% EX-25: Engine Structural Audit",
        "% ---------------------------------------------------------------------------",
        f"\\newcommand{{\\auditNGraphs}}{{{results['n_graphs']}}}",
        f"\\newcommand{{\\auditTotalNodes}}{{{results['n_total_nodes']}}}",
        f"\\newcommand{{\\auditTotalRules}}{{{results['n_total_constraints']}}}",
        f"\\newcommand{{\\auditUniqueActions}}{{{results['n_unique_actions']}}}",
        f"\\newcommand{{\\auditConstraintsPerNode}}{{{results['constraints_per_node']}}}",
        f"\\newcommand{{\\auditUnreachableRate}}{{{ar['unreachable_rate']}}}",
        f"\\newcommand{{\\auditDeadRate}}{{{ar['dead_end_rate']}}}",
        f"\\newcommand{{\\auditContradictoryRate}}{{{ar['contradiction_rate']}}}",
        f"\\newcommand{{\\auditDuplicateRate}}{{{ar['duplicate_rate']}}}",
        f"\\newcommand{{\\auditProvenanceComplete}}{{{ar['provenance_rate']}}}",
        f"\\newcommand{{\\auditGraphsWithUnreachable}}{{{ar['graphs_with_unreachable']}}}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 70)
    print("EX-25: ENGINE STRUCTURAL AUDIT")
    print("=" * 70)

    results = run_audit()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(results, OUTPUT_DIR / "engine_audit.json")

    md = generate_markdown(results)
    save_markdown(md, OUTPUT_DIR / "engine_audit.md")

    macros = generate_macros(results)
    macros_path = OUTPUT_DIR / "macros.tex"
    macros_path.write_text(macros)
    print(f"  Saved: {macros_path}")

    ar = results["audit_results"]
    print(f"\n  Graphs: {results['n_graphs']}")
    print(f"  Nodes: {results['n_total_nodes']}")
    print(f"  Constraints: {results['n_total_constraints']}")
    print(f"  Unique actions: {results['n_unique_actions']}")
    print(f"  Constraints/node: {results['constraints_per_node']}")
    print()
    print(f"  Unreachable nodes:  {ar['unreachable_nodes']} ({ar['unreachable_rate']}%)")
    print(f"  Dead-end nodes:     {ar['dead_end_nodes']} ({ar['dead_end_rate']}%)")
    print(f"  Contradictions:     {ar['contradictions']} ({ar['contradiction_rate']}%)")
    print(f"  Duplicates:         {ar['duplicates']} ({ar['duplicate_rate']}%)")
    print(f"  Provenance:         {ar['provenance_rate']}%")
    print()

    # Constraint type distribution
    print("  Constraint types:")
    for ct in CONSTRAINT_TYPES:
        cnt = results["constraint_type_distribution"].get(ct, 0)
        print(f"    {ct:12s}: {cnt}")

    print("=" * 70)


if __name__ == "__main__":
    main()
