"""Validate all conditional_rules in CPG graph YAML files.

Checks:
1. Required fields present (rule_id, condition, effect, evidence, severity)
2. Effect type is valid (FORBIDDEN, REQUIRED, BEFORE, WITHIN)
3. Severity is valid (CRITICAL, HIGH, MODERATE, LOW)
4. Condition is syntactically valid Python
5. condition_variables, trigger_range, normal_range present
6. rule_id uniqueness across all graphs
"""

from __future__ import annotations

from pathlib import Path
import sys

import yaml

VALID_EFFECT_TYPES = {"FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN"}
VALID_SEVERITIES = {"CRITICAL", "HIGH", "MODERATE", "LOW"}


def validate() -> int:
    """Validate all conditional rules. Returns error count."""
    graphs_dir = Path(__file__).parent.parent / "cpg_model" / "graphs"
    errors: list[str] = []
    all_rule_ids: dict[str, str] = {}  # rule_id -> graph_path
    total_rules = 0

    for graph_path in sorted(graphs_dir.glob("*.yaml")):
        with open(graph_path) as f:
            graph = yaml.safe_load(f)

        if not graph or "nodes" not in graph:
            continue

        graph_id = graph.get("graph_id", graph_path.stem)

        for node_id, node in graph.get("nodes", {}).items():
            for rule in node.get("conditional_rules", []):
                total_rules += 1
                prefix = f"{graph_path.name}:{node_id}"

                # rule_id
                rule_id = rule.get("rule_id")
                if not rule_id:
                    errors.append(f"{prefix}: missing rule_id")
                    continue

                # uniqueness
                if rule_id in all_rule_ids:
                    errors.append(f"{prefix}: duplicate rule_id '{rule_id}' (also in {all_rule_ids[rule_id]})")
                all_rule_ids[rule_id] = f"{graph_path.name}:{node_id}"

                # condition
                condition = rule.get("condition")
                if not condition:
                    errors.append(f"{prefix}/{rule_id}: missing condition")
                else:
                    try:
                        compile(condition, "<rule>", "eval")
                    except SyntaxError as e:
                        errors.append(f"{prefix}/{rule_id}: invalid condition syntax: {e}")

                # effect
                effect = rule.get("effect", {})
                etype = effect.get("type")
                if etype not in VALID_EFFECT_TYPES:
                    errors.append(f"{prefix}/{rule_id}: invalid effect type '{etype}'")
                if not effect.get("actions"):
                    errors.append(f"{prefix}/{rule_id}: empty effect.actions")

                # evidence
                if not rule.get("evidence"):
                    errors.append(f"{prefix}/{rule_id}: missing evidence")

                # severity
                severity = rule.get("severity")
                if severity not in VALID_SEVERITIES:
                    errors.append(f"{prefix}/{rule_id}: invalid severity '{severity}'")

                # condition_variables (not required for unconditional rules with condition="True")
                is_unconditional = condition and condition.strip() == "True"
                if not rule.get("condition_variables") and not is_unconditional:
                    errors.append(f"{prefix}/{rule_id}: missing condition_variables")

                # trigger_range / normal_range (not required for unconditional rules)
                if not rule.get("trigger_range") and not is_unconditional:
                    errors.append(f"{prefix}/{rule_id}: missing trigger_range")
                if not rule.get("normal_range") and not is_unconditional:
                    errors.append(f"{prefix}/{rule_id}: missing normal_range")

    # Report
    print(f"Total conditional rules found: {total_rules}")
    print(f"Unique rule IDs: {len(all_rule_ids)}")

    if errors:
        print(f"\n{len(errors)} errors found:")
        for err in errors:
            print(f"  ERROR: {err}")
        return len(errors)

    print("All conditional rules valid")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
