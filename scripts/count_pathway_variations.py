"""각 graph의 node들을 patient_activation_condition 기준으로 분석.
상호 배타적 pathway를 식별하고, pathway 조합 수를 계산.
"""

from __future__ import annotations

from collections import defaultdict
from functools import reduce
from operator import mul
from pathlib import Path
import re
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))


def extract_main_variable(condition: str) -> str:
    """Condition string에서 주요 분기 변수 추출."""
    # patient.labs.ph, patient.vitals.sbp 등
    vars_found = re.findall(r"patient\.[\w.]+", condition)
    if vars_found:
        return vars_found[0]

    in_match = re.search(r"in patient\.(\w+)", condition)
    if in_match:
        return f"patient.{in_match.group(1)}"

    return "unknown"


print("=" * 90)
print("PATHWAY VARIATION ANALYSIS")
print("=" * 90)

total_pathways = 0
total_pathway_scenarios = 0

for graph_path in sorted(Path("cpg_model/graphs/").glob("*.yaml")):
    with open(graph_path) as f:
        graph = yaml.safe_load(f)

    graph_id = graph.get("graph_id", graph_path.stem)
    nodes = graph.get("nodes", {})

    always_active: list[dict] = []
    never_active: list[dict] = []
    conditional_nodes: list[dict] = []

    for node_id, node in nodes.items():
        pac = str(node.get("patient_activation_condition", "")).strip()
        ma = node.get("mandatory_actions", [])

        if not pac or pac == "True":
            always_active.append({"node_id": node_id, "mandatory": len(ma), "condition": pac})
        elif pac == "False":
            never_active.append({"node_id": node_id, "mandatory": len(ma)})
        else:
            conditional_nodes.append({"node_id": node_id, "mandatory": len(ma), "condition": pac})

    # Group conditional nodes by main variable
    condition_groups: dict[str, list[dict]] = defaultdict(list)
    for cn in conditional_nodes:
        main_var = extract_main_variable(cn["condition"])
        condition_groups[main_var].append(cn)

    # Each group: one choice among members (+ "none" option)
    group_sizes = [len(g) + 1 for g in condition_groups.values()]
    pathway_combinations = reduce(mul, group_sizes, 1) if group_sizes else 1

    always_mandatory = sum(n["mandatory"] for n in always_active)

    total_pathways += len(conditional_nodes)
    total_pathway_scenarios += pathway_combinations

    print(f"\n{graph_id}:")
    print(f"  Always-active nodes: {len(always_active)} ({always_mandatory} mandatory actions)")
    print(f"  Conditional nodes: {len(conditional_nodes)}")
    print(f"  Never-active nodes: {len(never_active)}")
    print(f"  Condition groups: {len(condition_groups)}")
    for var, group in condition_groups.items():
        node_ids = [n["node_id"] for n in group]
        print(f"    {var}: {len(group)} options -> {node_ids}")
    print(f"  Pathway combinations: {pathway_combinations}")

print(f"\n{'=' * 90}")
print(f"Total conditional pathway nodes: {total_pathways}")
print(f"Total pathway-based normal scenario variations: {total_pathway_scenarios}")
