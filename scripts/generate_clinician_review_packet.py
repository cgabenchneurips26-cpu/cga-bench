"""Clinician Review Packet Generator (Defense against Attack 3.1)

Collects all conditional rules from CPG graphs and converts them
to natural-language clinical questions for clinician validation.

Usage:
    PYTHONPATH=. python scripts/generate_clinician_review_packet.py
"""

from __future__ import annotations

import csv
from pathlib import Path
import re

import yaml

BASE_DIR = Path(__file__).parent.parent
GRAPHS_DIR = BASE_DIR / "cpg_model" / "graphs"
OUTPUT_DIR = BASE_DIR / "evidence_pack" / "clinician_review"


def collect_all_conditional_rules() -> list[dict]:
    """Collect all conditional_rules from every CPG graph YAML file.

    Returns:
        List of rule dicts augmented with _graph_id, _node_id, _graph_file.
    """
    rules: list[dict] = []

    for graph_path in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(graph_path) as f:
            graph = yaml.safe_load(f)

        if not graph or "nodes" not in graph:
            continue

        graph_id = graph.get("graph_id", graph_path.stem)
        guideline_name = graph.get("guideline_name", graph_id)

        for node_id, node in graph.get("nodes", {}).items():
            for rule in node.get("conditional_rules", []):
                rule_copy = dict(rule)
                rule_copy["_graph_id"] = graph_id
                rule_copy["_graph_file"] = graph_path.name
                rule_copy["_node_id"] = node_id
                rule_copy["_guideline_name"] = guideline_name
                rules.append(rule_copy)

    return rules


def condition_to_natural_language(condition: str) -> str:
    """Convert a Python condition string to natural language.

    Args:
        condition: e.g., "patient.labs.potassium < 3.3"

    Returns:
        Natural language description.
    """
    text = condition

    # Replace patient field references
    replacements = [
        (r"patient\.labs\.potassium", "serum potassium"),
        (r"patient\.labs\.glucose", "blood glucose"),
        (r"patient\.labs\.ph", "arterial pH"),
        (r"patient\.labs\.egfr", "eGFR"),
        (r"patient\.labs\.inr", "INR"),
        (r"patient\.labs\.bicarbonate", "serum bicarbonate"),
        (r"patient\.labs\.lactate", "serum lactate"),
        (r"patient\.labs\.creatinine", "serum creatinine"),
        (r"patient\.labs\.hemoglobin", "hemoglobin"),
        (r"patient\.labs\.platelets", "platelet count"),
        (r"patient\.labs\.troponin", "troponin"),
        (r"patient\.labs\.anion_gap", "anion gap"),
        (r"patient\.vitals\.sbp", "systolic BP"),
        (r"patient\.vitals\.hr", "heart rate"),
        (r"patient\.vitals\.spo2", "SpO2"),
        (r"patient\.vitals\.map_mmhg", "MAP"),
        (r"patient\.age", "patient age"),
        (r"patient\.sex", "patient sex"),
        (r"patient\.weight_kg", "patient weight"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)

    # Replace 'in patient.comorbidities' patterns
    text = re.sub(
        r"'(\w+)' in patient\.comorbidities",
        r"patient has \1",
        text,
    )
    text = re.sub(
        r"'(\w+)' in patient\.medications",
        r"patient is on \1",
        text,
    )
    text = re.sub(
        r"'(\w+)' in patient\.allergies",
        r"patient is allergic to \1",
        text,
    )

    # Clean up underscores
    text = text.replace("_", " ")

    # Replace operators
    text = text.replace(" and ", " AND ")
    text = text.replace(" or ", " OR ")

    return text


def action_to_natural_language(action_id: str) -> str:
    """Convert action_id to natural language.

    Args:
        action_id: e.g., "start_insulin_infusion"

    Returns:
        Natural language action description.
    """
    action_map = {
        "start_insulin_infusion": "start an insulin infusion",
        "give_insulin_bolus": "give an insulin bolus",
        "give_potassium_iv": "give IV potassium",
        "give_potassium_replacement": "give potassium replacement",
        "give_rapid_fluid_bolus": "give a rapid fluid bolus",
        "give_bicarbonate": "administer sodium bicarbonate",
        "give_nitroglycerin": "administer nitroglycerin",
        "give_nitrates": "administer nitrates",
        "give_aspirin_loading": "give aspirin loading dose",
        "give_alteplase_0.9mg_kg": "give alteplase (tPA)",
        "give_broad_spectrum_antibiotics": "give broad-spectrum antibiotics",
        "start_vasopressor_norepinephrine": "start norepinephrine",
        "discharge_based_on_normal_glucose": "discharge based on normal glucose",
        "stop_sglt2_inhibitor": "stop SGLT2 inhibitor",
        "add_dextrose_to_iv": "add dextrose to IV fluids",
    }
    if action_id in action_map:
        return action_map[action_id]
    return action_id.replace("_", " ")


def format_clinical_question(rule: dict) -> str:
    """Convert a rule to a natural-language clinical question.

    Args:
        rule: Conditional rule dict from YAML.

    Returns:
        Formatted clinical question with response options.
    """
    condition = rule.get("condition", "")
    effect = rule.get("effect", {})
    description = rule.get("description", "")
    condition_nl = condition_to_natural_language(condition)

    effect_type = effect.get("type", "FORBIDDEN")
    actions = effect.get("actions", [])
    actions_nl = ", ".join(action_to_natural_language(a) for a in actions)

    if effect_type == "FORBIDDEN":
        question = (
            f"Clinical scenario: {condition_nl}\n"
            f"Context: {description}\n"
            f"Question: Is it safe to {actions_nl}?\n"
            f"[ ] Yes, safe  [ ] No, contraindicated  [ ] Depends (explain)"
        )
    elif effect_type == "REQUIRED":
        question = (
            f"Clinical scenario: {condition_nl}\n"
            f"Context: {description}\n"
            f"Question: Should the clinician {actions_nl}?\n"
            f"[ ] Yes, required  [ ] No, not needed  [ ] Depends (explain)"
        )
    elif effect_type in ("BEFORE", "WITHIN"):
        question = (
            f"Clinical scenario: {condition_nl}\n"
            f"Context: {description}\n"
            f"Question: Is the ordering/timing constraint ({actions_nl}) "
            f"clinically appropriate?\n"
            f"[ ] Yes, correct  [ ] No, incorrect  [ ] Depends (explain)"
        )
    else:
        question = f"Context: {description}\nQuestion: Is this rule clinically valid?"

    return question


def save_csv(rules: list[dict], output_path: Path) -> None:
    """Save rules as CSV for clinician review.

    Args:
        rules: List of rule dicts to save.
        output_path: Output CSV file path.
    """
    fieldnames = [
        "rule_id",
        "graph",
        "guideline",
        "node",
        "severity",
        "effect_type",
        "condition",
        "actions",
        "clinical_question",
        "expected_answer",
        "evidence_cited",
        "clinician_agrees",
        "clinician_notes",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for rule in rules:
            effect = rule.get("effect", {})
            effect_type = effect.get("type", "FORBIDDEN")

            if effect_type == "FORBIDDEN":
                expected = "No, contraindicated"
            elif effect_type == "REQUIRED":
                expected = "Yes, required"
            else:
                expected = "Yes, correct"

            writer.writerow(
                {
                    "rule_id": rule.get("rule_id", ""),
                    "graph": rule.get("_graph_id", ""),
                    "guideline": rule.get("_guideline_name", ""),
                    "node": rule.get("_node_id", ""),
                    "severity": rule.get("severity", ""),
                    "effect_type": effect_type,
                    "condition": rule.get("condition", ""),
                    "actions": ", ".join(effect.get("actions", [])),
                    "clinical_question": format_clinical_question(rule),
                    "expected_answer": expected,
                    "evidence_cited": rule.get("evidence", ""),
                    "clinician_agrees": "",  # Clinician fills this
                    "clinician_notes": "",  # Clinician fills this
                }
            )


def main() -> None:
    """Generate clinician review packets."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_rules = collect_all_conditional_rules()
    print(f"Total conditional rules collected: {len(all_rules)}")

    # Separate by severity
    critical = [r for r in all_rules if r.get("severity") == "CRITICAL"]
    high = [r for r in all_rules if r.get("severity") == "HIGH"]
    moderate = [r for r in all_rules if r.get("severity") == "MODERATE"]
    low = [r for r in all_rules if r.get("severity") == "LOW"]

    print(f"  CRITICAL: {len(critical)}")
    print(f"  HIGH: {len(high)}")
    print(f"  MODERATE: {len(moderate)}")
    print(f"  LOW: {len(low)}")

    # Save CSVs
    save_csv(critical, OUTPUT_DIR / "critical_rules.csv")
    save_csv(high, OUTPUT_DIR / "high_rules.csv")
    save_csv(moderate, OUTPUT_DIR / "moderate_rules.csv")
    save_csv(all_rules, OUTPUT_DIR / "all_rules.csv")

    print(f"\nGenerated {len(critical)} CRITICAL + {len(high)} HIGH questions")
    print(f"Files saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
