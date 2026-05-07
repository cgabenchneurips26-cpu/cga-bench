"""
Experiment D: Evaluator Actionability

Proves CGA is a diagnostic evaluator that provides actionable feedback,
not just a stricter scoring function. Targeted prompt patches improve
specific CGA dimensions without affecting others.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PromptPatchType(str, Enum):
    """Targeted prompt patches for actionability experiment."""
    BASELINE = "baseline"
    TIMING = "patch_T"
    SEQUENCE = "patch_S"
    OVERACTION = "patch_O"


# Prompt patch text appended to agent system prompt
PROMPT_PATCHES: Dict[PromptPatchType, str] = {
    PromptPatchType.BASELINE: "",
    PromptPatchType.TIMING: (
        "\n\nCRITICAL TIMING REQUIREMENT:\n"
        "All mandatory actions must be completed within the guideline-specified "
        "time window. For sepsis, this means completing the Hour-1 Bundle "
        "(blood cultures, antibiotics, lactate, fluid resuscitation) within "
        "60 minutes of presentation. For DKA, IV fluids must start within "
        "15 minutes. For STEMI, cath lab activation within 10 minutes of "
        "ECG diagnosis. Delays in time-critical interventions are associated "
        "with increased mortality. Prioritize mandatory actions by deadline urgency."
    ),
    PromptPatchType.SEQUENCE: (
        "\n\nCRITICAL SEQUENCE REQUIREMENT:\n"
        "Actions must be performed in the correct clinical order. "
        "Always obtain blood cultures BEFORE administering antibiotics. "
        "In DKA, always check and correct potassium BEFORE starting insulin. "
        "In stroke, always obtain CT head BEFORE administering tPA. "
        "In chest pain, always obtain 12-lead ECG BEFORE giving aspirin. "
        "Violating these sequences can cause direct patient harm or mask "
        "important diagnostic information."
    ),
    PromptPatchType.OVERACTION: (
        "\n\nACTION SCOPE REQUIREMENT:\n"
        "Only perform actions that are explicitly recommended in the "
        "clinical guideline for this specific condition. Do not order "
        "additional tests or treatments that are not part of the "
        "standard protocol, even if they seem clinically reasonable. "
        "Off-protocol actions waste resources, delay critical "
        "interventions, and may cause unnecessary harm. Stick strictly "
        "to the guideline-recommended action set."
    ),
}

# Expected dimension impact mapping
EXPECTED_IMPACT: Dict[PromptPatchType, str] = {
    PromptPatchType.TIMING: "C4_timing_compliance",
    PromptPatchType.SEQUENCE: "C5_sequence_integrity",
    PromptPatchType.OVERACTION: "C1_path_selection",
}


@dataclass
class ActionabilityResult:
    """Result from a single actionability run."""
    scenario_id: str
    patch_type: PromptPatchType
    compliance_score: float
    sub_scores: Dict[str, float]
    violations_by_type: Dict[str, int]
    total_violations: int


@dataclass
class ActionabilityAnalysis:
    """Computed actionability metrics."""
    patch_type: PromptPatchType
    target_dimension: str
    targeted_improvement_rate: float  # Episodes where target dim improved
    specificity: float                # Episodes where ONLY target dim improved
    mean_target_delta: float          # Average Δ in target dimension
    mean_other_delta: float           # Average Δ in non-target dimensions
    per_scenario: Dict[str, Dict[str, float]]


class ActionabilityExperiment:
    """Runs Experiment D: Evaluator Actionability.

    Tests whether CGA's 5 sub-dimensions are independently
    actionable by applying targeted prompt patches and measuring
    whether the targeted dimension improves selectively.
    """

    SCENARIOS = [
        "septic_shock_basic",
        "septic_shock_penicillin_allergy",
        "stemi_inferior_rv_trap",
        "dka_moderate_basic",
        "dka_hypokalemia_trap",
        "stroke_tpa_eligible",
        "contrast_aki_prevention_basic",
        "aki_stage1_basic",
    ]

    def __init__(
        self,
        output_dir: str = "evidence_pack/experiments",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.results: List[ActionabilityResult] = []

    def load_results_from_files(
        self,
        baseline_dir: str,
        patch_dirs: Dict[PromptPatchType, str],
    ) -> int:
        """Load pre-computed results from experiment run directories.

        Args:
            baseline_dir: Directory with baseline (no patch) results.
            patch_dirs: Map from patch type to results directory.

        Returns:
            Number of results loaded.
        """
        count = 0

        # Load baseline
        count += self._load_dir(baseline_dir, PromptPatchType.BASELINE)

        # Load patch results
        for patch_type, dir_path in patch_dirs.items():
            count += self._load_dir(dir_path, patch_type)

        return count

    def load_results_directly(self, results: List[ActionabilityResult]) -> None:
        """Load results directly (for programmatic use)."""
        self.results.extend(results)

    def add_result(
        self,
        scenario_id: str,
        patch_type: PromptPatchType,
        compliance_score: float,
        sub_scores: Dict[str, float],
        violations_by_type: Optional[Dict[str, int]] = None,
        total_violations: int = 0,
    ) -> None:
        """Add a single result."""
        self.results.append(
            ActionabilityResult(
                scenario_id=scenario_id,
                patch_type=patch_type,
                compliance_score=compliance_score,
                sub_scores=sub_scores,
                violations_by_type=violations_by_type or {},
                total_violations=total_violations,
            )
        )

    def analyze(self) -> List[ActionabilityAnalysis]:
        """Compute actionability metrics for each patch type."""
        analyses: List[ActionabilityAnalysis] = []

        # Group baseline results by scenario
        baseline_by_scenario: Dict[str, ActionabilityResult] = {}
        for r in self.results:
            if r.patch_type == PromptPatchType.BASELINE:
                baseline_by_scenario[r.scenario_id] = r

        for patch_type in [PromptPatchType.TIMING, PromptPatchType.SEQUENCE, PromptPatchType.OVERACTION]:
            target_dim = EXPECTED_IMPACT[patch_type]
            other_dims = [
                d for d in [
                    "C1_path_selection",
                    "C2_mandatory_completion",
                    "C3_forbidden_avoidance",
                    "C4_timing_compliance",
                    "C5_sequence_integrity",
                ] if d != target_dim
            ]

            patched = [r for r in self.results if r.patch_type == patch_type]
            if not patched:
                continue

            target_improved_count = 0
            only_target_improved_count = 0
            target_deltas: List[float] = []
            other_deltas: List[float] = []
            per_scenario: Dict[str, Dict[str, float]] = {}

            for pr in patched:
                baseline = baseline_by_scenario.get(pr.scenario_id)
                if baseline is None:
                    continue

                # Delta in target dimension
                bl_target = baseline.sub_scores.get(target_dim, 0.0)
                pr_target = pr.sub_scores.get(target_dim, 0.0)
                target_delta = pr_target - bl_target
                target_deltas.append(target_delta)

                target_improved = target_delta > 0.01

                # Delta in other dimensions
                other_changed = False
                scenario_deltas: Dict[str, float] = {target_dim: round(target_delta, 4)}
                for dim in other_dims:
                    bl_val = baseline.sub_scores.get(dim, 0.0)
                    pr_val = pr.sub_scores.get(dim, 0.0)
                    delta = pr_val - bl_val
                    other_deltas.append(delta)
                    scenario_deltas[dim] = round(delta, 4)
                    if abs(delta) > 0.01:
                        other_changed = True

                if target_improved:
                    target_improved_count += 1
                    if not other_changed:
                        only_target_improved_count += 1

                per_scenario[pr.scenario_id] = scenario_deltas

            total = len(patched)
            analyses.append(
                ActionabilityAnalysis(
                    patch_type=patch_type,
                    target_dimension=target_dim,
                    targeted_improvement_rate=round(
                        target_improved_count / max(total, 1), 4
                    ),
                    specificity=round(
                        only_target_improved_count / max(target_improved_count, 1), 4
                    ),
                    mean_target_delta=round(
                        sum(target_deltas) / max(len(target_deltas), 1), 4
                    ),
                    mean_other_delta=round(
                        sum(abs(d) for d in other_deltas) / max(len(other_deltas), 1), 4
                    ),
                    per_scenario=per_scenario,
                )
            )

        return analyses

    def save_results(self) -> None:
        """Save actionability experiment results."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        analyses = self.analyze()

        # JSON
        json_path = self.output_dir / "actionability_results.json"
        json_data = {
            "experiment": "D_actionability",
            "description": "Evaluator Actionability Experiment",
            "prompt_patches": {
                pt.value: text for pt, text in PROMPT_PATCHES.items()
            },
            "results": [
                {
                    "scenario_id": r.scenario_id,
                    "patch_type": r.patch_type.value,
                    "compliance_score": r.compliance_score,
                    "sub_scores": r.sub_scores,
                    "violations_by_type": r.violations_by_type,
                    "total_violations": r.total_violations,
                }
                for r in self.results
            ],
            "analyses": [
                {
                    "patch_type": a.patch_type.value,
                    "target_dimension": a.target_dimension,
                    "targeted_improvement_rate": a.targeted_improvement_rate,
                    "specificity": a.specificity,
                    "mean_target_delta": a.mean_target_delta,
                    "mean_other_delta": a.mean_other_delta,
                    "per_scenario": a.per_scenario,
                }
                for a in analyses
            ],
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        # Markdown
        md_path = self.output_dir / "actionability_summary.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self._generate_markdown(analyses))

        # LaTeX
        tables_dir = self.output_dir.parent / "tables"
        tables_dir.mkdir(parents=True, exist_ok=True)
        tex_path = tables_dir / "table_actionability.tex"
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(self._generate_latex(analyses))

        logger.info(f"Actionability results saved: {json_path}, {md_path}, {tex_path}")

    def _load_dir(self, dir_path: str, patch_type: PromptPatchType) -> int:
        """Load results from a directory."""
        rdir = Path(dir_path)
        if not rdir.exists():
            logger.warning(f"Directory not found: {rdir}")
            return 0

        count = 0
        for json_file in sorted(rdir.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                self.results.append(
                    ActionabilityResult(
                        scenario_id=data["scenario_id"],
                        patch_type=patch_type,
                        compliance_score=data.get("compliance_score", 0.0),
                        sub_scores=data.get("sub_scores", {}),
                        violations_by_type=data.get("violations_by_type", {}),
                        total_violations=data.get("total_violations", 0),
                    )
                )
                count += 1
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning(f"Failed to load {json_file}: {exc}")

        return count

    @staticmethod
    def _generate_markdown(analyses: List[ActionabilityAnalysis]) -> str:
        """Generate markdown summary."""
        lines = [
            "# Experiment D: Evaluator Actionability Results\n",
            "## Actionability Matrix\n",
            "| Patch | Target Dim | Improvement Rate | Specificity | Mean Δ Target | Mean Δ Other |",
            "|-------|-----------|-----------------|------------|---------------|-------------|",
        ]

        for a in analyses:
            lines.append(
                f"| {a.patch_type.value} | {a.target_dimension} | "
                f"{a.targeted_improvement_rate:.1%} | {a.specificity:.1%} | "
                f"{a.mean_target_delta:+.4f} | {a.mean_other_delta:.4f} |"
            )

        lines.extend([
            "",
            "## Interpretation\n",
            "- **High Improvement Rate + High Specificity** = CGA dimension is actionable and orthogonal",
            "- **High Improvement Rate + Low Specificity** = Dimension coupling detected (also interesting)",
            "- **Low Improvement Rate** = Prompt patch insufficient or dimension already saturated",
            "",
            "## CGA Sub-Score Impact Table\n",
            "| | Baseline | Patch T | Patch S | Patch O |",
            "|--------|----------|---------|---------|---------|",
        ])

        # Build dimension × patch matrix from analyses
        dims = [
            "C1_path_selection",
            "C2_mandatory_completion",
            "C3_forbidden_avoidance",
            "C4_timing_compliance",
            "C5_sequence_integrity",
        ]
        for dim in dims:
            row = [f"| {dim} |"]
            row.append(" — |")  # baseline placeholder
            for a in analyses:
                delta = 0.0
                for scenario_data in a.per_scenario.values():
                    delta += scenario_data.get(dim, 0.0)
                if a.per_scenario:
                    delta /= len(a.per_scenario)
                arrow = "↑" if delta > 0.01 else ("↓" if delta < -0.01 else "—")
                row.append(f" {arrow} ({delta:+.3f}) |")
            lines.append("".join(row))

        return "\n".join(lines)

    @staticmethod
    def _generate_latex(analyses: List[ActionabilityAnalysis]) -> str:
        """Generate LaTeX table."""
        lines = [
            r"\begin{table}[t]",
            r"\centering",
            r"\caption{Evaluator actionability: targeted prompt patches improve specific CGA dimensions.}",
            r"\label{tab:actionability}",
            r"\begin{tabular}{lccc}",
            r"\toprule",
            r"Patch & Target & Improvement Rate & Specificity \\",
            r"\midrule",
        ]

        for a in analyses:
            target_short = a.target_dimension.replace("_", " ")
            lines.append(
                f"{a.patch_type.value} & {target_short} & "
                f"{a.targeted_improvement_rate:.0%} & {a.specificity:.0%} \\\\"
            )

        lines.extend([
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ])

        return "\n".join(lines)
