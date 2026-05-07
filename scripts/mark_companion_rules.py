"""Mark companion FORBIDDEN rules with skip_scenario_generation: true.

Companion FORBIDDEN rules (rule_id ending with '-FORBIDDEN') exist solely to
provide differentiation for their parent rule's trap patients. They participate
in constraint derivation but must NOT generate their own scenarios.
"""

from __future__ import annotations

from pathlib import Path

import yaml

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"


def mark_companions(graph_path: Path) -> int:
    """Add skip_scenario_generation: true to companion FORBIDDEN rules.

    Returns number of rules marked.
    """
    with open(graph_path, encoding="utf-8") as f:
        raw = f.read()

    data = yaml.safe_load(raw)
    if not data or "nodes" not in data:
        return 0

    marked = 0
    for _node_id, node in data.get("nodes", {}).items():
        for rule in node.get("conditional_rules", []):
            rid = rule.get("rule_id", "")
            if not rid.endswith("-FORBIDDEN"):
                continue
            if rule.get("skip_scenario_generation"):
                continue  # already marked
            rule["skip_scenario_generation"] = True
            marked += 1

    if marked > 0:
        with open(graph_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )

    return marked


def main() -> None:
    total = 0
    for graph_path in sorted(GRAPHS_DIR.glob("*.yaml")):
        count = mark_companions(graph_path)
        if count > 0:
            print(f"  {graph_path.name}: {count} rules marked")
            total += count

    print(f"\nTotal: {total} companion rules marked with skip_scenario_generation: true")


if __name__ == "__main__":
    main()
