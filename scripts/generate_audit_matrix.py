"""Generate Rule Coverage Audit Matrix.

Produces evidence_pack/rule_coverage_audit.yaml and .md with:
- Per-graph conditional rule inventory
- Rule ID -> evidence mapping
- Coverage statistics
"""

from __future__ import annotations

from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"
EVIDENCE_DIR = Path(__file__).parent.parent / "evidence_pack"


def collect_rules(graph: dict) -> list[dict]:
    """Collect all conditional_rules from a graph."""
    rules: list[dict] = []
    for node_id, node in graph.get("nodes", {}).items():
        for rule in node.get("conditional_rules", []):
            rules.append(
                {
                    "rule_id": rule.get("rule_id", ""),
                    "node_id": node_id,
                    "condition": rule.get("condition", ""),
                    "effect_type": rule.get("effect", {}).get("type", ""),
                    "actions": rule.get("effect", {}).get("actions", []),
                    "evidence": rule.get("evidence", ""),
                    "severity": rule.get("severity", ""),
                    "has_trigger_range": bool(rule.get("trigger_range")),
                    "has_normal_range": bool(rule.get("normal_range")),
                    "condition_variables": rule.get("condition_variables", []),
                }
            )
    return rules


def count_unconditional_forbidden(graph: dict) -> int:
    """Count total unconditional forbidden actions across all nodes."""
    total = 0
    for node in graph.get("nodes", {}).values():
        total += len(node.get("forbidden_actions", []))
    return total


def count_sequence_rules(graph: dict) -> int:
    """Count total BEFORE-type constraints (sequence_rules + required_prior_actions)."""
    total = 0
    for node in graph.get("nodes", {}).values():
        total += len(node.get("sequence_rules", []))
        rpa = node.get("required_prior_actions", {})
        if isinstance(rpa, dict):
            for priors in rpa.values():
                if isinstance(priors, list):
                    total += len(priors)
    return total


def generate_audit() -> None:
    """Generate the audit matrix."""
    audit: dict[str, dict] = {}

    for graph_path in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(graph_path) as f:
            graph = yaml.safe_load(f)

        if not graph or "nodes" not in graph:
            continue

        graph_id = graph.get("graph_id", graph_path.stem)
        rules = collect_rules(graph)

        audit[graph_id] = {
            "guideline_name": graph.get("guideline_name", ""),
            "total_nodes": len(graph.get("nodes", {})),
            "total_unconditional_forbidden": count_unconditional_forbidden(graph),
            "total_sequence_rules": count_sequence_rules(graph),
            "total_conditional_rules": len(rules),
            "rules_by_severity": {
                "CRITICAL": sum(1 for r in rules if r["severity"] == "CRITICAL"),
                "HIGH": sum(1 for r in rules if r["severity"] == "HIGH"),
                "MODERATE": sum(1 for r in rules if r["severity"] == "MODERATE"),
                "LOW": sum(1 for r in rules if r["severity"] == "LOW"),
            },
            "rules_by_type": {
                "FORBIDDEN": sum(1 for r in rules if r["effect_type"] == "FORBIDDEN"),
                "REQUIRED": sum(1 for r in rules if r["effect_type"] == "REQUIRED"),
                "BEFORE": sum(1 for r in rules if r["effect_type"] == "BEFORE"),
                "WITHIN": sum(1 for r in rules if r["effect_type"] == "WITHIN"),
            },
            "rules": rules,
        }

    # Save YAML
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    yaml_path = EVIDENCE_DIR / "rule_coverage_audit.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(audit, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)

    # Save Markdown
    md_path = EVIDENCE_DIR / "rule_coverage_audit.md"
    with open(md_path, "w") as f:
        f.write("# Rule Coverage Audit Matrix\n\n")
        f.write("Auto-generated from CPG graph conditional_rules.\n\n")

        # Summary table
        total_rules = sum(a["total_conditional_rules"] for a in audit.values())
        total_uncond = sum(a["total_unconditional_forbidden"] for a in audit.values())
        total_seq = sum(a["total_sequence_rules"] for a in audit.values())

        f.write("## Summary\n\n")
        f.write(f"- **Total graphs**: {len(audit)}\n")
        f.write(f"- **Total unconditional forbidden**: {total_uncond}\n")
        f.write(f"- **Total sequence rules**: {total_seq}\n")
        f.write(f"- **Total conditional rules**: {total_rules}\n")
        f.write(f"- **Total constraints**: {total_uncond + total_seq + total_rules}\n\n")

        # Per-graph table
        f.write("## Per-Graph Breakdown\n\n")
        f.write("| Graph | Nodes | Uncond. Forbidden | Sequence | Conditional | CRITICAL | HIGH |\n")
        f.write("|-------|-------|-------------------|----------|-------------|----------|------|\n")
        for gid, data in audit.items():
            f.write(
                f"| {gid} | {data['total_nodes']} "
                f"| {data['total_unconditional_forbidden']} "
                f"| {data['total_sequence_rules']} "
                f"| {data['total_conditional_rules']} "
                f"| {data['rules_by_severity']['CRITICAL']} "
                f"| {data['rules_by_severity']['HIGH']} |\n"
            )

        # Detailed rules
        f.write("\n## Detailed Rule Inventory\n\n")
        for gid, data in audit.items():
            f.write(f"### {gid} ({data['guideline_name']})\n\n")
            if data["rules"]:
                f.write("| Rule ID | Type | Severity | Evidence |\n")
                f.write("|---------|------|----------|----------|\n")
                for r in data["rules"]:
                    evidence_short = r["evidence"][:60] + "..." if len(r["evidence"]) > 60 else r["evidence"]
                    f.write(f"| {r['rule_id']} | {r['effect_type']} | {r['severity']} | {evidence_short} |\n")
                f.write("\n")
            else:
                f.write("_No conditional rules defined._\n\n")

    # Print summary
    print(f"Total graphs: {len(audit)}")
    print(f"Total unconditional forbidden: {total_uncond}")
    print(f"Total sequence rules: {total_seq}")
    print(f"Total conditional rules: {total_rules}")
    print(f"Total constraints: {total_uncond + total_seq + total_rules}")
    print(f"\nOutput: {yaml_path}")
    print(f"Output: {md_path}")


if __name__ == "__main__":
    generate_audit()
