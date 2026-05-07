#!/usr/bin/env python3
"""EX-33: Benchmark Survey Audit — Systematic comparison of clinical AI benchmarks.

Classifies 10+ clinical AI benchmarks along 4 process-safety dimensions:
  - Timing support (WITHIN constraint checking)
  - Ordering check (BEFORE constraint checking)
  - Conditional safety (context-dependent FORBIDDEN)
  - CPG fidelity (formal guideline graph evaluation)

Demonstrates that CGA-Bench is the only benchmark covering all 4 dimensions,
justifying the need for a new benchmark artifact rather than a new scorer alone.

Output: evidence_pack/ex33_benchmark_survey/
Macros: surveyNBenchmarks, surveyNProcessOblivious, surveyNTimingChecked, etc.

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_e33_benchmark_survey.py
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._common import save_json, save_markdown

OUTPUT_DIR = ROOT / "evidence_pack" / "ex33_benchmark_survey"


# ---------------------------------------------------------------------------
# Benchmark classification data (from published papers + codebases)
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkEntry:
    """Classification of a clinical AI benchmark along process-safety axes."""

    name: str
    year: int
    venue: str
    observation_level: str  # "action_set", "free_text", "structured_trace", "action_sequence"
    scoring_paradigm: str  # "checklist", "llm_judge", "f1_match", "constraint_graph", "rubric"

    # 4 process-safety dimensions (True = supported)
    timing_support: bool = False
    ordering_check: bool = False
    conditional_safety: bool = False
    cpg_fidelity: bool = False

    # Additional metadata
    n_scenarios: str = ""  # approximate count or range
    modality: str = ""  # "text", "multimodal", "EHR"
    notes: str = ""
    citation_key: str = ""


BENCHMARKS: list[BenchmarkEntry] = [
    BenchmarkEntry(
        name="AgentClinic",
        year=2024,
        venue="NeurIPS",
        observation_level="free_text",
        scoring_paradigm="llm_judge",
        timing_support=False,
        ordering_check=False,
        conditional_safety=False,
        cpg_fidelity=False,
        n_scenarios="~300",
        modality="text",
        notes="Dialogue-based; LLM judge scores diagnosis + key actions; no temporal structure",
        citation_key="schmidgall2024agentclinic",
    ),
    BenchmarkEntry(
        name="MedAgentBench",
        year=2025,
        venue="NAACL",
        observation_level="action_set",
        scoring_paradigm="f1_match",
        timing_support=False,
        ordering_check=False,
        conditional_safety=False,
        cpg_fidelity=False,
        n_scenarios="100",
        modality="EHR",
        notes="Action multiset F1; safety penalty flag but no constraint typing",
        citation_key="qiao2025medagentbench",
    ),
    BenchmarkEntry(
        name="HealthBench",
        year=2025,
        venue="arXiv",
        observation_level="free_text",
        scoring_paradigm="rubric",
        timing_support=False,
        ordering_check=False,
        conditional_safety=False,
        cpg_fidelity=False,
        n_scenarios="5000",
        modality="text",
        notes="Conversation rubric items; LLM-graded; no structured action representation",
        citation_key="arora2025healthbench",
    ),
    BenchmarkEntry(
        name="AMEGA",
        year=2024,
        venue="arXiv",
        observation_level="action_sequence",
        scoring_paradigm="checklist",
        timing_support=False,
        ordering_check=True,  # partial: checks action ordering
        conditional_safety=False,
        cpg_fidelity=False,
        n_scenarios="120",
        modality="text",
        notes="Action sequence with partial ordering awareness; no timing deadlines",
        citation_key="chen2024amega",
    ),
    BenchmarkEntry(
        name="CliBench",
        year=2024,
        venue="EMNLP",
        observation_level="action_set",
        scoring_paradigm="checklist",
        timing_support=False,
        ordering_check=False,
        conditional_safety=False,
        cpg_fidelity=False,
        n_scenarios="1000+",
        modality="EHR",
        notes="MIMIC-based; action presence checklist; no process constraints",
        citation_key="wang2024clibench",
    ),
    BenchmarkEntry(
        name="MedGUIDE",
        year=2024,
        venue="ML4H",
        observation_level="free_text",
        scoring_paradigm="llm_judge",
        timing_support=False,
        ordering_check=False,
        conditional_safety=False,
        cpg_fidelity=False,
        n_scenarios="300+",
        modality="text",
        notes="Guideline-referenced but free-text evaluation; no constraint formalization",
        citation_key="wang2024medguide",
    ),
    BenchmarkEntry(
        name="CancerGUIDE",
        year=2024,
        venue="arXiv",
        observation_level="free_text",
        scoring_paradigm="rubric",
        timing_support=False,
        ordering_check=False,
        conditional_safety=True,  # partial: treatment-specific contraindications
        cpg_fidelity=False,
        n_scenarios="200+",
        modality="text",
        notes="Cancer treatment planning; some conditional contraindication checks",
        citation_key="chen2024cancerguide",
    ),
    BenchmarkEntry(
        name="MTBBench",
        year=2024,
        venue="arXiv",
        observation_level="action_set",
        scoring_paradigm="checklist",
        timing_support=False,
        ordering_check=False,
        conditional_safety=True,  # biomarker-conditional treatment
        cpg_fidelity=False,
        n_scenarios="50+",
        modality="text",
        notes="Molecular tumor board; biomarker-conditional treatment matching",
        citation_key="lu2024mtbbench",
    ),
    BenchmarkEntry(
        name="EHRStruct",
        year=2024,
        venue="arXiv",
        observation_level="action_set",
        scoring_paradigm="f1_match",
        timing_support=False,
        ordering_check=False,
        conditional_safety=False,
        cpg_fidelity=False,
        n_scenarios="500+",
        modality="EHR",
        notes="Structured EHR-based; action matching; no process safety dimensions",
        citation_key="pang2024ehrstruct",
    ),
    BenchmarkEntry(
        name="LLMEval-Med",
        year=2024,
        venue="arXiv",
        observation_level="free_text",
        scoring_paradigm="llm_judge",
        timing_support=False,
        ordering_check=False,
        conditional_safety=False,
        cpg_fidelity=False,
        n_scenarios="200+",
        modality="text",
        notes="Multi-turn dialogue; LLM-as-judge; no structured constraint checking",
        citation_key="tian2024llmevalmed",
    ),
    BenchmarkEntry(
        name="NICE",
        year=2024,
        venue="arXiv",
        observation_level="free_text",
        scoring_paradigm="rubric",
        timing_support=False,
        ordering_check=False,
        conditional_safety=False,
        cpg_fidelity=False,
        n_scenarios="150+",
        modality="text",
        notes="NICE guideline adherence; rubric-based but no formal constraint model",
        citation_key="wang2024nice",
    ),
    # CGA-Bench (ours) — reference row
    BenchmarkEntry(
        name="CGA-Bench",
        year=2025,
        venue="NeurIPS (submitted)",
        observation_level="structured_trace",
        scoring_paradigm="constraint_graph",
        timing_support=True,
        ordering_check=True,
        conditional_safety=True,
        cpg_fidelity=True,
        n_scenarios="706",
        modality="structured_trace",
        notes="Typed constraint checking over CPG graphs; WITHIN/BEFORE/FORBIDDEN/MUST",
        citation_key="ours",
    ),
]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

SAFETY_DIMS = ["timing_support", "ordering_check", "conditional_safety", "cpg_fidelity"]


def analyze_benchmarks(benchmarks: list[BenchmarkEntry]) -> dict:
    """Compute survey statistics."""
    n = len(benchmarks)
    others = [b for b in benchmarks if b.name != "CGA-Bench"]
    n_others = len(others)

    # Count each dimension
    dim_counts: dict[str, int] = {}
    for dim in SAFETY_DIMS:
        dim_counts[dim] = sum(1 for b in others if getattr(b, dim))

    # Process-oblivious: none of the 4 dimensions
    n_oblivious = sum(1 for b in others if not any(getattr(b, d) for d in SAFETY_DIMS))

    # Partial coverage: some but not all dimensions
    n_partial = sum(
        1 for b in others if any(getattr(b, d) for d in SAFETY_DIMS) and not all(getattr(b, d) for d in SAFETY_DIMS)
    )

    # Full coverage (should be 0 for others)
    n_full = sum(1 for b in others if all(getattr(b, d) for d in SAFETY_DIMS))

    # Observation level distribution
    obs_levels: dict[str, int] = {}
    for b in others:
        obs_levels[b.observation_level] = obs_levels.get(b.observation_level, 0) + 1

    # Scoring paradigm distribution
    score_paradigms: dict[str, int] = {}
    for b in others:
        score_paradigms[b.scoring_paradigm] = score_paradigms.get(b.scoring_paradigm, 0) + 1

    return {
        "n_benchmarks": n,
        "n_others": n_others,
        "n_process_oblivious": n_oblivious,
        "n_partial_coverage": n_partial,
        "n_full_coverage_others": n_full,
        "dimension_support_counts": dim_counts,
        "n_timing_checked": dim_counts["timing_support"],
        "n_ordering_checked": dim_counts["ordering_check"],
        "n_conditional_checked": dim_counts["conditional_safety"],
        "n_cpg_fidelity": dim_counts["cpg_fidelity"],
        "observation_levels": obs_levels,
        "scoring_paradigms": score_paradigms,
        "per_benchmark": [asdict(b) for b in benchmarks],
    }


def generate_latex_table(benchmarks: list[BenchmarkEntry]) -> str:
    """Generate LaTeX table for the benchmark survey."""
    dim_labels = {
        "timing_support": "Timing",
        "ordering_check": "Order",
        "conditional_safety": "Cond.",
        "cpg_fidelity": "CPG",
    }

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\small",
        r"\caption{Process-safety dimension coverage across clinical AI benchmarks. "
        r"\checkmark{} = supported, \textemdash{} = not supported. "
        r"CGA-Bench is the only benchmark covering all four dimensions.}",
        r"\label{tab:benchmark-survey}",
        r"\begin{tabular}{lcccccl}",
        r"\toprule",
        r"Benchmark & Year & Timing & Order & Cond. & CPG & Obs.\ Level \\",
        r"\midrule",
    ]

    for b in benchmarks:
        mark = lambda v: r"\checkmark" if v else r"\textemdash"
        obs_short = {
            "free_text": "text",
            "action_set": "actions",
            "action_sequence": "seq",
            "structured_trace": "trace",
            "EHR": "EHR",
        }.get(b.observation_level, b.observation_level)

        if b.name == "CGA-Bench":
            lines.append(r"\midrule")
            lines.append(
                f"\\textbf{{{b.name}}} & {b.year} & "
                f"{mark(b.timing_support)} & {mark(b.ordering_check)} & "
                f"{mark(b.conditional_safety)} & {mark(b.cpg_fidelity)} & "
                f"{obs_short} \\\\"
            )
        else:
            lines.append(
                f"{b.name} & {b.year} & "
                f"{mark(b.timing_support)} & {mark(b.ordering_check)} & "
                f"{mark(b.conditional_safety)} & {mark(b.cpg_fidelity)} & "
                f"{obs_short} \\\\"
            )

    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )
    return "\n".join(lines)


def generate_markdown(results: dict) -> str:
    """Generate human-readable markdown report."""
    lines = [
        "# EX-33: Benchmark Survey Audit",
        "",
        f"**Benchmarks surveyed:** {results['n_benchmarks']} ({results['n_others']} external + CGA-Bench)",
        "",
        "## Process-Safety Dimension Coverage",
        "",
        f"- **Process-oblivious** (0/4 dimensions): {results['n_process_oblivious']}/{results['n_others']}",
        f"- **Partial coverage** (1-3 dimensions): {results['n_partial_coverage']}/{results['n_others']}",
        f"- **Full coverage** (4/4 dimensions, excl. CGA-Bench): {results['n_full_coverage_others']}/{results['n_others']}",
        "",
        "## Dimension Support (among external benchmarks)",
        "",
        "| Dimension | Supported | Rate |",
        "|-----------|-----------|------|",
    ]

    n_others = results["n_others"]
    for dim, count in results["dimension_support_counts"].items():
        label = dim.replace("_", " ").title()
        pct = count / n_others * 100 if n_others else 0
        lines.append(f"| {label} | {count}/{n_others} | {pct:.0f}% |")

    lines.extend(
        [
            "",
            "## Per-Benchmark Detail",
            "",
            "| Benchmark | Year | Timing | Order | Cond. | CPG | Obs. Level | Scoring |",
            "|-----------|------|--------|-------|-------|-----|------------|---------|",
        ]
    )

    for b in results["per_benchmark"]:
        mark = lambda v: "Y" if v else "-"
        lines.append(
            f"| {b['name']} | {b['year']} | "
            f"{mark(b['timing_support'])} | {mark(b['ordering_check'])} | "
            f"{mark(b['conditional_safety'])} | {mark(b['cpg_fidelity'])} | "
            f"{b['observation_level']} | {b['scoring_paradigm']} |"
        )

    lines.extend(
        [
            "",
            "## Observation Level Distribution",
            "",
        ]
    )
    for level, count in results["observation_levels"].items():
        lines.append(f"- {level}: {count}")

    lines.extend(
        [
            "",
            "## Scoring Paradigm Distribution",
            "",
        ]
    )
    for paradigm, count in results["scoring_paradigms"].items():
        lines.append(f"- {paradigm}: {count}")

    lines.extend(
        [
            "",
            "## Key Finding",
            "",
            f"Of {n_others} external benchmarks, {results['n_process_oblivious']} "
            f"({results['n_process_oblivious'] / n_others * 100:.0f}%) are completely "
            f"process-oblivious (no timing, ordering, conditional, or CPG checks). "
            f"Only {results['n_timing_checked']} check timing constraints and "
            f"{results['n_ordering_checked']} check action ordering. "
            f"None achieve full coverage of all 4 process-safety dimensions.",
        ]
    )

    return "\n".join(lines)


def generate_macros(results: dict) -> str:
    """Generate LaTeX macros for auto_numbers.tex."""
    lines = [
        "",
        "% ---------------------------------------------------------------------------",
        "% EX-33: Benchmark Survey Audit",
        "% ---------------------------------------------------------------------------",
        f"\\newcommand{{\\surveyNBenchmarks}}{{{results['n_benchmarks']}}}",
        f"\\newcommand{{\\surveyNOthers}}{{{results['n_others']}}}",
        f"\\newcommand{{\\surveyNProcessOblivious}}{{{results['n_process_oblivious']}}}",
        f"\\newcommand{{\\surveyNTimingChecked}}{{{results['n_timing_checked']}}}",
        f"\\newcommand{{\\surveyNOrderChecked}}{{{results['n_ordering_checked']}}}",
        f"\\newcommand{{\\surveyNConditionalChecked}}{{{results['n_conditional_checked']}}}",
        f"\\newcommand{{\\surveyNFullCoverageOthers}}{{{results['n_full_coverage_others']}}}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 70)
    print("EX-33: BENCHMARK SURVEY AUDIT")
    print("=" * 70)

    results = analyze_benchmarks(BENCHMARKS)

    # Save outputs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(results, OUTPUT_DIR / "benchmark_survey.json")

    md = generate_markdown(results)
    save_markdown(md, OUTPUT_DIR / "benchmark_survey.md")

    tex_table = generate_latex_table(BENCHMARKS)
    tex_path = OUTPUT_DIR / "benchmark_survey_table.tex"
    tex_path.write_text(tex_table)
    print(f"  Saved: {tex_path}")

    macros = generate_macros(results)
    macros_path = OUTPUT_DIR / "macros.tex"
    macros_path.write_text(macros)
    print(f"  Saved: {macros_path}")

    # Print summary
    print(f"\n  Benchmarks: {results['n_benchmarks']} ({results['n_others']} external)")
    print(f"  Process-oblivious: {results['n_process_oblivious']}/{results['n_others']}")
    print(f"  Timing checked: {results['n_timing_checked']}/{results['n_others']}")
    print(f"  Ordering checked: {results['n_ordering_checked']}/{results['n_others']}")
    print(f"  Conditional checked: {results['n_conditional_checked']}/{results['n_others']}")
    print(f"  Full coverage (others): {results['n_full_coverage_others']}/{results['n_others']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
