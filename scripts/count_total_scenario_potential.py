"""모든 variation 축을 합산하여 이론적 최대 시나리오 수 계산."""

from __future__ import annotations

from math import comb
from pathlib import Path
import re
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))


def extract_pathway_group(condition: str) -> str:
    """condition에서 pathway 그룹 식별."""
    vars_found = re.findall(r"patient\.(\w+)", condition)
    return vars_found[0] if vars_found else "default"


print("=" * 90)
print("TOTAL SCENARIO GENERATION POTENTIAL")
print("=" * 90)

grand_total: dict[str, int] = {
    "single_trigger": 0,
    "pathway_normal": 0,
    "value_variation": 0,
    "combo_2": 0,
    "combo_3": 0,
}

for graph_path in sorted(Path("cpg_model/graphs/").glob("*.yaml")):
    with open(graph_path) as f:
        graph = yaml.safe_load(f)

    graph_id = graph.get("graph_id", graph_path.stem)

    rules: list[dict] = []
    for node in graph.get("nodes", {}).values():
        for rule in node.get("conditional_rules", []):
            rules.append(rule)
    n_rules = len(rules)

    # Pathway variations
    nodes = graph.get("nodes", {})
    conditional_nodes = [
        n
        for n in nodes.values()
        if str(n.get("patient_activation_condition", "True")).strip() not in ("True", "False", "")
    ]
    n_pathways = max(
        len(set(extract_pathway_group(str(n.get("patient_activation_condition", ""))) for n in conditional_nodes)),
        1,
    )

    numeric_rules = [r for r in rules if any(op in r.get("condition", "") for op in ["<", ">", "<=", ">="])]

    single_trigger = n_rules
    pathway_normal = n_pathways
    value_var = len(numeric_rules) * 2
    c2 = comb(n_rules, 2) if n_rules >= 2 else 0
    c3 = comb(n_rules, 3) if n_rules >= 3 else 0

    total_graph = single_trigger + pathway_normal + value_var + c2

    grand_total["single_trigger"] += single_trigger
    grand_total["pathway_normal"] += pathway_normal
    grand_total["value_variation"] += value_var
    grand_total["combo_2"] += c2
    grand_total["combo_3"] += c3

    print(f"\n{graph_id}:")
    print(f"  Rules: {n_rules}")
    print(f"  Pathways: {n_pathways}")
    print(f"  Single trigger: {single_trigger}")
    print(f"  Pathway normals: {pathway_normal}")
    print(f"  Value variations: {value_var}")
    print(f"  2-rule combos: {c2}")
    print(f"  3-rule combos: {c3}")
    print(f"  Practical total (excl. 3-rule): {total_graph}")

# Read current counts
auto_count = 313
manual_count = 105
current_total = auto_count + manual_count

practical = (
    grand_total["single_trigger"]
    + grand_total["pathway_normal"]
    + grand_total["value_variation"]
    + grand_total["combo_2"]
)
theoretical = practical + grand_total["combo_3"]

print(f"\n{'=' * 90}")
print("GRAND TOTAL ACROSS ALL GRAPHS")
print(f"{'=' * 90}")

print(f"""
  Axis 1 - Single-rule trigger:     {grand_total["single_trigger"]:>6d}  (1 trap per rule)
  Axis 2 - Pathway normal:          {grand_total["pathway_normal"]:>6d}  (1 baseline per pathway combo)
  Axis 3 - Value variation:         {grand_total["value_variation"]:>6d}  (numeric rule x 2 extra values)
  Axis 4 - 2-rule combinatorial:    {grand_total["combo_2"]:>6d}  (2 rules trigger simultaneously)
  ─────────────────────────────────────────
  Practical max (axes 1-4):         {practical:>6d}

  Axis 5 - 3-rule combinatorial:    {grand_total["combo_3"]:>6d}  (3 rules trigger simultaneously)
  ─────────────────────────────────────────
  Theoretical max (axes 1-5):       {theoretical:>6d}

  Current generated:                {auto_count:>6d}  (auto)
  + Manual:                         {manual_count:>6d}
  = Current total:                  {current_total:>6d}

  Utilization (current/practical):  {current_total / max(practical, 1) * 100:>5.1f}%
""")

print(f"""
  +---------------------+----------+-------------+--------------+
  |       Scale         | Scenarios|  Episodes   | Runtime      |
  |                     |          | (x5mod x3run)| (4 GPU par.) |
  +---------------------+----------+-------------+--------------+
  | Current             | ~{current_total:<8d}| {current_total * 15:>11,d} | ~{current_total * 15 * 5 / 60 / 24 / 4:.1f} days    |
  | + Pathway normals   | ~{current_total + grand_total["pathway_normal"]:<8d}| {(current_total + grand_total["pathway_normal"]) * 15:>11,d} | ~{(current_total + grand_total["pathway_normal"]) * 15 * 5 / 60 / 24 / 4:.1f} days    |
  | + Value variation   | ~{current_total + grand_total["pathway_normal"] + grand_total["value_variation"]:<8d}| {(current_total + grand_total["pathway_normal"] + grand_total["value_variation"]) * 15:>11,d} | ~{(current_total + grand_total["pathway_normal"] + grand_total["value_variation"]) * 15 * 5 / 60 / 24 / 4:.1f} days   |
  | Full practical max  | ~{practical:<8d}| {practical * 15:>11,d} | ~{practical * 15 * 5 / 60 / 24 / 4:.1f} days  |
  +---------------------+----------+-------------+--------------+
""")
