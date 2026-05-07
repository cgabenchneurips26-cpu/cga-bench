"""각 graph에서 시나리오가 생성되는 과정을 단계별로 추적."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from cpg_model.constraint_derivation import ConstraintDerivationEngine
from cpg_model.patient_generator import PatientGenerator, _collect_all_rules

engine = ConstraintDerivationEngine()
generator = PatientGenerator(engine, seed=42)

print("=" * 100)
print("SCENARIO GENERATION MECHANICS — FULL BREAKDOWN")
print("=" * 100)

total_rules = 0
total_trigger = 0
total_normal = 0
total_combo = 0
total_skipped_trigger = 0
total_skipped_normal = 0

graph_details: list[dict] = []

for graph_path in sorted(Path("cpg_model/graphs/").glob("*.yaml")):
    with open(graph_path) as f:
        graph = yaml.safe_load(f)

    graph_id = graph.get("graph_id", graph_path.stem)
    rules = _collect_all_rules(graph)

    trigger_count = 0
    normal_count = 0
    skipped_trigger = 0
    skipped_normal = 0

    rule_details: list[dict] = []
    for rule in rules:
        trigger_range = rule.get("trigger_range", {})
        normal_range = rule.get("normal_range", {})

        # Trigger attempt
        trigger_ok = False
        if trigger_range:
            base = generator._get_base_patient(graph_id)
            for var_path, range_spec in trigger_range.items():
                value = generator._sample_value(range_spec)
                from cpg_model.patient_generator import _set_nested

                _set_nested(base, var_path.replace("patient.", ""), value)
            fires = engine._evaluate_condition(rule.get("condition", ""), base)
            if fires:
                trigger_count += 1
                trigger_ok = True
            else:
                skipped_trigger += 1

        # Normal attempt
        normal_ok = False
        if normal_range:
            base_n = generator._get_base_patient(graph_id)
            for var_path, range_spec in normal_range.items():
                value = generator._sample_value(range_spec)
                _set_nested(base_n, var_path.replace("patient.", ""), value)
            fires_n = engine._evaluate_condition(rule.get("condition", ""), base_n)
            if not fires_n:
                normal_count += 1
                normal_ok = True
            else:
                skipped_normal += 1

        rule_details.append(
            {
                "rule_id": rule["rule_id"],
                "condition": rule.get("condition", "")[:80],
                "severity": rule.get("severity", "?"),
                "trigger_generated": trigger_ok,
                "normal_generated": normal_ok,
                "has_trigger_range": bool(trigger_range),
                "has_normal_range": bool(normal_range),
            }
        )

    # Combinatorial
    combo_scenarios = generator._generate_combinatorial(rules, graph)
    combo_count = len(combo_scenarios)

    total_from_graph = trigger_count + normal_count + combo_count

    graph_details.append(
        {
            "graph_id": graph_id,
            "conditional_rules": len(rules),
            "trigger_scenarios": trigger_count,
            "normal_scenarios": normal_count,
            "combo_scenarios": combo_count,
            "skipped_trigger": skipped_trigger,
            "skipped_normal": skipped_normal,
            "total": total_from_graph,
        }
    )

    total_rules += len(rules)
    total_trigger += trigger_count
    total_normal += normal_count
    total_combo += combo_count
    total_skipped_trigger += skipped_trigger
    total_skipped_normal += skipped_normal

    print(f"\n{'─' * 80}")
    print(f"GRAPH: {graph_id}")
    print(f"  Conditional rules: {len(rules)}")
    print(f"  → Trigger scenarios (trap): {trigger_count}")
    print(f"  → Normal scenarios (baseline): {normal_count}")
    print(f"  → Combinatorial scenarios: {combo_count}")
    print(f"  → Skipped: trigger={skipped_trigger}, normal={skipped_normal}")
    print(f"  = TOTAL from this graph: {total_from_graph}")
    print("  Rules detail:")
    for rd in rule_details:
        t = "T" if rd["trigger_generated"] else ("x" if rd["has_trigger_range"] else "-")
        n = "N" if rd["normal_generated"] else ("x" if rd["has_normal_range"] else "-")
        print(f"    {rd['rule_id'][:50]:50s} [{rd['severity']:8s}] trigger={t} normal={n}")

print(f"\n{'=' * 100}")
print("GRAND TOTAL")
print(f"{'=' * 100}")
print(f"  Graphs: {len(graph_details)}")
print(f"  Conditional rules: {total_rules}")
print(f"  Trigger (trap) scenarios: {total_trigger}")
print(f"  Normal (baseline) scenarios: {total_normal}")
print(f"  Combinatorial scenarios: {total_combo}")
print(f"  Skipped: trigger={total_skipped_trigger}, normal={total_skipped_normal}")
print(f"  AUTO-GENERATED TOTAL: {total_trigger + total_normal + total_combo}")

# Generation formula
print(f"\n{'=' * 100}")
print("GENERATION FORMULA")
print(f"{'=' * 100}")
print("  Per conditional rule: max 2 (1 trigger + 1 normal)")
print(f"  Theoretical max (rules x 2): {total_rules * 2}")
print(f"  Actual single-rule: {total_trigger + total_normal}")
print(f"  Single-rule efficiency: {(total_trigger + total_normal) / max(total_rules * 2, 1) * 100:.0f}%")
print(f"  + Combinatorial: {total_combo}")
print(f"  TOTAL: {total_trigger + total_normal + total_combo}")

# Summary table
print(f"\n{'=' * 100}")
hdr = f"{'Graph':<35s} {'Rules':>6s} {'Trigger':>8s} {'Normal':>7s} {'Combo':>6s} {'Skip':>5s} {'Total':>6s}"
print(hdr)
print(f"{'─' * 35} {'─' * 6} {'─' * 8} {'─' * 7} {'─' * 6} {'─' * 5} {'─' * 6}")
for gd in sorted(graph_details, key=lambda x: -x["total"]):
    skip = gd["skipped_trigger"] + gd["skipped_normal"]
    print(
        f"{gd['graph_id']:<35s} {gd['conditional_rules']:>6d} "
        f"{gd['trigger_scenarios']:>8d} {gd['normal_scenarios']:>7d} "
        f"{gd['combo_scenarios']:>6d} {skip:>5d} {gd['total']:>6d}"
    )
print(f"{'─' * 35} {'─' * 6} {'─' * 8} {'─' * 7} {'─' * 6} {'─' * 5} {'─' * 6}")
total_skip = total_skipped_trigger + total_skipped_normal
print(
    f"{'TOTAL':<35s} {total_rules:>6d} {total_trigger:>8d} "
    f"{total_normal:>7d} {total_combo:>6d} {total_skip:>5d} "
    f"{total_trigger + total_normal + total_combo:>6d}"
)
