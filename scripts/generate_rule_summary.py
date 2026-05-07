"""Rule Summary Table Generator (Defense against Attack A.1)

Generates reviewer-friendly summary of all conditional rules:
severity distribution, type classification, graph density,
and representative examples.

Usage:
    PYTHONPATH=. python scripts/generate_rule_summary.py
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).parent.parent
GRAPHS_DIR = BASE_DIR / "cpg_model" / "graphs"
TEX_OUTPUT = BASE_DIR / "evidence_pack" / "tables" / "rule_summary.tex"
JSON_OUTPUT = BASE_DIR / "evidence_pack" / "analysis" / "rule_summary.json"
MD_OUTPUT = BASE_DIR / "evidence_pack" / "analysis" / "rule_summary.md"


def collect_all_conditional_rules() -> list[dict]:
    """Collect all conditional_rules from every CPG graph YAML."""
    rules: list[dict] = []

    for graph_path in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(graph_path) as f:
            graph = yaml.safe_load(f)

        if not graph or "nodes" not in graph:
            continue

        graph_id = graph.get("graph_id", graph_path.stem)

        for node_id, node in graph.get("nodes", {}).items():
            for rule in node.get("conditional_rules", []):
                rule_copy = dict(rule)
                rule_copy["_graph_id"] = graph_id
                rule_copy["_node_id"] = node_id
                rules.append(rule_copy)

    return rules


def classify_rule_type(rule: dict) -> str:
    """Classify a rule into a clinical category.

    Args:
        rule: Conditional rule dict.

    Returns:
        Category string.
    """
    condition = rule.get("condition", "").lower()

    if any(x in condition for x in ["allergies", "allergy"]):
        return "Drug allergy / cross-reactivity"
    if any(
        x in condition
        for x in [
            "labs.",
            "potassium",
            "glucose",
            "egfr",
            "ph ",
            "inr",
            "bicarbonate",
            "lactate",
            "creatinine",
            "hemoglobin",
            "platelets",
            "troponin",
            "anion_gap",
        ]
    ):
        return "Lab-value gated"
    if any(
        x in condition
        for x in [
            "comorbidities",
            "pregnancy",
            "ckd",
            "liver",
            "cirrhosis",
            "renal",
            "heart_failure",
            "diabetes",
            "copd",
            "asthma",
        ]
    ):
        return "Comorbidity-conditional"
    if any(x in condition for x in ["age", "patient.age"]):
        return "Age-based"
    if any(
        x in condition
        for x in [
            "medications",
            "warfarin",
            "metformin",
            "sglt2",
            "anticoagulant",
            "beta_blocker",
            "ace_inhibitor",
        ]
    ):
        return "Medication interaction"
    if any(
        x in condition
        for x in [
            "vitals",
            "sbp",
            "hr",
            "spo2",
            "map_mmhg",
            "blood_pressure",
            "heart_rate",
        ]
    ):
        return "Vitals-based"
    return "Other"


def select_representative_rules(
    rules: list[dict],
    n: int = 5,
) -> list[dict]:
    """Select representative rules covering different types.

    Args:
        rules: All conditional rules.
        n: Number to select.

    Returns:
        List of representative rules.
    """
    by_type: dict[str, list[dict]] = {}
    for r in rules:
        rtype = classify_rule_type(r)
        by_type.setdefault(rtype, []).append(r)

    # One from each type, preferring CRITICAL severity
    selected: list[dict] = []
    for rtype in sorted(by_type.keys()):
        candidates = by_type[rtype]
        critical = [r for r in candidates if r.get("severity") == "CRITICAL"]
        pick = critical[0] if critical else candidates[0]
        selected.append(pick)
        if len(selected) >= n:
            break

    return selected


def generate_latex_tables(
    severity_dist: Counter,
    type_dist: Counter,
    graph_density: Counter,
    representative: list[dict],
) -> str:
    """Generate LaTeX tables for paper appendix."""
    lines: list[str] = []

    # Table 1: Severity distribution
    lines.extend(
        [
            r"\begin{table}[h]",
            r"\centering",
            r"\caption{Conditional rule severity distribution.}",
            r"\label{tab:rule_severity}",
            r"\begin{tabular}{lcc}",
            r"\toprule",
            r"\textbf{Severity} & \textbf{Count} & \textbf{\%} \\",
            r"\midrule",
        ]
    )
    total = sum(severity_dist.values())
    for sev in ["CRITICAL", "HIGH", "MODERATE", "LOW"]:
        count = severity_dist.get(sev, 0)
        pct = (count / total * 100) if total > 0 else 0
        lines.append(f"{sev} & {count} & {pct:.1f}\\% \\\\")
    lines.extend(
        [
            r"\midrule",
            f"Total & {total} & 100.0\\% \\\\",
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
            "",
        ]
    )

    # Table 2: Type classification
    lines.extend(
        [
            r"\begin{table}[h]",
            r"\centering",
            r"\caption{Conditional rule type classification.}",
            r"\label{tab:rule_types}",
            r"\begin{tabular}{lc}",
            r"\toprule",
            r"\textbf{Type} & \textbf{Count} \\",
            r"\midrule",
        ]
    )
    for rtype, count in type_dist.most_common():
        lines.append(f"{rtype} & {count} \\\\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
            "",
        ]
    )

    # Table 3: Graph density (top 10)
    lines.extend(
        [
            r"\begin{table}[h]",
            r"\centering",
            r"\caption{Conditional rules per CPG graph (top 10).}",
            r"\label{tab:graph_density}",
            r"\begin{tabular}{lc}",
            r"\toprule",
            r"\textbf{Graph} & \textbf{Rules} \\",
            r"\midrule",
        ]
    )
    for graph_id, count in graph_density.most_common(10):
        display = graph_id.replace("_", r"\_")
        lines.append(f"{display} & {count} \\\\")
    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
            "",
        ]
    )

    # Table 4: Representative rules
    lines.extend(
        [
            r"\begin{table*}[t]",
            r"\centering",
            r"\caption{Representative conditional rules (one per type).}",
            r"\label{tab:representative_rules}",
            r"\resizebox{\textwidth}{!}{%",
            r"\begin{tabular}{lllll}",
            r"\toprule",
            (
                r"\textbf{Rule ID} & \textbf{Type} & \textbf{Severity} & "
                r"\textbf{Condition} & \textbf{Effect} \\"
            ),
            r"\midrule",
        ]
    )
    for r in representative:
        rid = r.get("rule_id", "").replace("_", r"\_")
        rtype = classify_rule_type(r).replace("/", r"/")
        severity = r.get("severity", "")
        condition = r.get("condition", "")[:60].replace("_", r"\_")
        effect = r.get("effect", {})
        effect_str = f"{effect.get('type', '')}: {', '.join(effect.get('actions', [])[:2])}"
        effect_str = effect_str[:50].replace("_", r"\_")
        lines.append(f"{rid} & {rtype} & {severity} & {condition} & {effect_str} \\\\")

    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"}",
            r"\end{table*}",
        ]
    )

    return "\n".join(lines)


def generate_markdown_summary(
    severity_dist: Counter,
    type_dist: Counter,
    graph_density: Counter,
    representative: list[dict],
    total: int,
) -> str:
    """Generate markdown summary."""
    lines = [
        "# Conditional Rule Summary\n",
        f"**Total rules**: {total}\n",
        "## Severity Distribution\n",
        "| Severity | Count | % |",
        "|----------|-------|---|",
    ]

    for sev in ["CRITICAL", "HIGH", "MODERATE", "LOW"]:
        count = severity_dist.get(sev, 0)
        pct = (count / total * 100) if total > 0 else 0
        lines.append(f"| {sev} | {count} | {pct:.1f}% |")

    lines.extend(
        [
            "\n## Type Classification\n",
            "| Type | Count |",
            "|------|-------|",
        ]
    )
    for rtype, count in type_dist.most_common():
        lines.append(f"| {rtype} | {count} |")

    lines.extend(
        [
            "\n## Rules per Graph (Top 10)\n",
            "| Graph | Rules |",
            "|-------|-------|",
        ]
    )
    for graph_id, count in graph_density.most_common(10):
        lines.append(f"| {graph_id} | {count} |")

    lines.extend(
        [
            "\n## Representative Rules\n",
            "| Rule ID | Type | Severity | Description |",
            "|---------|------|----------|-------------|",
        ]
    )
    for r in representative:
        rid = r.get("rule_id", "")
        rtype = classify_rule_type(r)
        sev = r.get("severity", "")
        desc = r.get("description", "")[:80]
        lines.append(f"| {rid} | {rtype} | {sev} | {desc} |")

    return "\n".join(lines)


def main() -> None:
    """Generate rule summary statistics and tables."""
    rules = collect_all_conditional_rules()
    total = len(rules)

    # Severity distribution
    severity_dist = Counter(r.get("severity", "UNKNOWN") for r in rules)

    # Type classification
    type_dist = Counter(classify_rule_type(r) for r in rules)

    # Graph density
    graph_density = Counter(r["_graph_id"] for r in rules)

    # Representative rules
    representative = select_representative_rules(rules, n=5)

    print(f"""
Rule Summary:
  Total rules: {total}
  By severity: {dict(severity_dist)}
  By type: {dict(type_dist)}
  Graphs with most rules: {graph_density.most_common(5)}
""")

    # Generate outputs
    TEX_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # LaTeX
    tex = generate_latex_tables(severity_dist, type_dist, graph_density, representative)
    with open(TEX_OUTPUT, "w") as f:
        f.write(tex)
    print(f"LaTeX tables saved to {TEX_OUTPUT}")

    # JSON
    json_data = {
        "total_rules": total,
        "severity_distribution": dict(severity_dist),
        "type_classification": dict(type_dist),
        "graph_density": dict(graph_density.most_common()),
        "representative_rules": [
            {
                "rule_id": r.get("rule_id"),
                "graph": r.get("_graph_id"),
                "type": classify_rule_type(r),
                "severity": r.get("severity"),
                "condition": r.get("condition"),
                "effect": r.get("effect"),
                "evidence": r.get("evidence"),
                "description": r.get("description"),
            }
            for r in representative
        ],
    }
    with open(JSON_OUTPUT, "w") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"JSON data saved to {JSON_OUTPUT}")

    # Markdown
    md = generate_markdown_summary(severity_dist, type_dist, graph_density, representative, total)
    with open(MD_OUTPUT, "w") as f:
        f.write(md)
    print(f"Markdown summary saved to {MD_OUTPUT}")


if __name__ == "__main__":
    main()
