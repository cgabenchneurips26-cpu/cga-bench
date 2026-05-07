"""Benchmark Comparison Table Generator (Defense against Attack 2.1)

Generates a comparison table of CGA-Bench against existing medical AI
benchmarks in both LaTeX and Markdown format.

Usage:
    PYTHONPATH=. python scripts/generate_benchmark_comparison.py
"""

from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
TEX_OUTPUT = BASE_DIR / "evidence_pack" / "tables" / "benchmark_comparison.tex"
MD_OUTPUT = BASE_DIR / "evidence_pack" / "tables" / "benchmark_comparison.md"

BENCHMARKS = [
    {
        "name": "CGA-Bench (ours)",
        "year": 2026,
        "task_type": "Interactive agent",
        "evaluation": "Multi-evaluator, CPG-grounded",
        "n_scenarios": "366",
        "n_domains": "20",
        "constraint_types": "FORBIDDEN, BEFORE, WITHIN, conditional",
        "cpg_grounded": True,
        "auto_generation": True,
        "provenance": True,
        "closed_loop": True,
        "reference": "",
    },
    {
        "name": "MedQA",
        "year": 2021,
        "task_type": "Multiple-choice QA",
        "evaluation": "Accuracy",
        "n_scenarios": "12,723",
        "n_domains": "General",
        "constraint_types": "---",
        "cpg_grounded": False,
        "auto_generation": False,
        "provenance": False,
        "closed_loop": False,
        "reference": "Jin et al., 2021",
    },
    {
        "name": "HealthBench",
        "year": 2025,
        "task_type": "Open-ended dialogue",
        "evaluation": "LLM-as-judge (criteria)",
        "n_scenarios": "5,000",
        "n_domains": "General health",
        "constraint_types": "---",
        "cpg_grounded": False,
        "auto_generation": False,
        "provenance": False,
        "closed_loop": False,
        "reference": "OpenAI, 2025",
    },
    {
        "name": "AgentClinic",
        "year": 2024,
        "task_type": "Simulated patient dialogue",
        "evaluation": "Diagnostic accuracy",
        "n_scenarios": "321",
        "n_domains": "General clinical",
        "constraint_types": "---",
        "cpg_grounded": False,
        "auto_generation": False,
        "provenance": False,
        "closed_loop": True,
        "reference": "Schmidgall et al., 2024",
    },
    {
        "name": "MedAgentBench",
        "year": 2025,
        "task_type": "EHR agent tasks",
        "evaluation": "Task completion",
        "n_scenarios": "300",
        "n_domains": "EHR operations",
        "constraint_types": "---",
        "cpg_grounded": False,
        "auto_generation": False,
        "provenance": False,
        "closed_loop": True,
        "reference": "Shi et al., 2025",
    },
    {
        "name": "MedChain",
        "year": 2025,
        "task_type": "Multi-hop reasoning",
        "evaluation": "Accuracy / F1",
        "n_scenarios": "12,163",
        "n_domains": "General medical",
        "constraint_types": "---",
        "cpg_grounded": False,
        "auto_generation": True,
        "provenance": False,
        "closed_loop": False,
        "reference": "Wang et al., 2025",
    },
    {
        "name": "ClinicalBench",
        "year": 2024,
        "task_type": "Clinical NLP tasks",
        "evaluation": "F1 / Accuracy",
        "n_scenarios": "~2,000",
        "n_domains": "Clinical notes",
        "constraint_types": "---",
        "cpg_grounded": False,
        "auto_generation": False,
        "provenance": False,
        "closed_loop": False,
        "reference": "Yan et al., 2024",
    },
    {
        "name": "CLUE",
        "year": 2024,
        "task_type": "Clinical reasoning",
        "evaluation": "Rubric scoring",
        "n_scenarios": "~300",
        "n_domains": "General clinical",
        "constraint_types": "---",
        "cpg_grounded": False,
        "auto_generation": False,
        "provenance": False,
        "closed_loop": False,
        "reference": "Chiang et al., 2024",
    },
]


def _bool_to_str(val: bool) -> str:
    return "Yes" if val else "No"


def _bool_to_tex(val: bool) -> str:
    return r"\cmark" if val else r"\xmark"


def generate_latex() -> str:
    """Generate LaTeX table for paper."""
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Comparison of CGA-Bench with existing medical AI benchmarks.}",
        r"\label{tab:benchmark_comparison}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{lccccccccc}",
        r"\toprule",
        (
            r"\textbf{Benchmark} & \textbf{Year} & \textbf{Task Type} & "
            r"\textbf{Evaluation} & \textbf{Scenarios} & \textbf{Domains} & "
            r"\textbf{CPG} & \textbf{Auto-Gen} & \textbf{Provenance} & "
            r"\textbf{Closed-Loop} \\"
        ),
        r"\midrule",
    ]

    for b in BENCHMARKS:
        is_ours = "ours" in b["name"]
        name = r"\textbf{" + b["name"] + "}" if is_ours else b["name"]
        row = (
            f"{name} & {b['year']} & {b['task_type']} & "
            f"{b['evaluation']} & {b['n_scenarios']} & {b['n_domains']} & "
            f"{_bool_to_tex(b['cpg_grounded'])} & "
            f"{_bool_to_tex(b['auto_generation'])} & "
            f"{_bool_to_tex(b['provenance'])} & "
            f"{_bool_to_tex(b['closed_loop'])} \\\\"
        )
        lines.append(row)

    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"}",
            r"\end{table*}",
        ]
    )

    return "\n".join(lines)


def generate_markdown() -> str:
    """Generate Markdown comparison table."""
    header = (
        "| Benchmark | Year | Task Type | Evaluation | Scenarios | Domains "
        "| CPG-Grounded | Auto-Gen | Provenance | Closed-Loop |"
    )
    separator = (
        "|-----------|------|-----------|------------|-----------|------"
        "---|--------------|----------|------------|-------------|"
    )

    rows = [header, separator]
    for b in BENCHMARKS:
        row = f"| **{b['name']}** " if "ours" in b["name"] else f"| {b['name']} "
        row += (
            f"| {b['year']} | {b['task_type']} | {b['evaluation']} "
            f"| {b['n_scenarios']} | {b['n_domains']} "
            f"| {_bool_to_str(b['cpg_grounded'])} "
            f"| {_bool_to_str(b['auto_generation'])} "
            f"| {_bool_to_str(b['provenance'])} "
            f"| {_bool_to_str(b['closed_loop'])} |"
        )
        rows.append(row)

    return "\n".join(rows)


def generate_dimension_comparison_tex() -> str:
    """Generate constraint-type dimension comparison (sub-table)."""
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Constraint types supported by CGA-Bench vs.\ prior work.}",
        r"\label{tab:constraint_dimensions}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        (
            r"\textbf{Benchmark} & \textbf{FORBIDDEN} & \textbf{BEFORE} & "
            r"\textbf{WITHIN} & \textbf{Conditional} \\"
        ),
        r"\midrule",
    ]

    dimension_data = [
        ("CGA-Bench (ours)", True, True, True, True),
        ("MedQA", False, False, False, False),
        ("HealthBench", False, False, False, False),
        ("AgentClinic", False, False, False, False),
        ("MedAgentBench", False, False, False, False),
        ("MedChain", False, False, False, False),
        ("ClinicalBench", False, False, False, False),
        ("CLUE", False, False, False, False),
    ]

    for name, forbidden, before, within, conditional in dimension_data:
        is_ours = "ours" in name
        display_name = r"\textbf{" + name + "}" if is_ours else name
        row = (
            f"{display_name} & {_bool_to_tex(forbidden)} & "
            f"{_bool_to_tex(before)} & {_bool_to_tex(within)} & "
            f"{_bool_to_tex(conditional)} \\\\"
        )
        lines.append(row)

    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    """Generate benchmark comparison tables."""
    TEX_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # Main comparison table
    tex_content = generate_latex()
    tex_content += "\n\n" + generate_dimension_comparison_tex()
    with open(TEX_OUTPUT, "w") as f:
        f.write(tex_content)
    print(f"LaTeX table saved to {TEX_OUTPUT}")

    # Markdown version
    md_content = "# Benchmark Comparison\n\n"
    md_content += generate_markdown()
    md_content += "\n\n## Constraint Type Dimensions\n\n"
    md_content += (
        "Only CGA-Bench supports structured constraint types (FORBIDDEN, BEFORE, WITHIN) with conditional rules.\n"
    )
    with open(MD_OUTPUT, "w") as f:
        f.write(md_content)
    print(f"Markdown table saved to {MD_OUTPUT}")


if __name__ == "__main__":
    main()
