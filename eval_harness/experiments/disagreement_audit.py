"""
Experiment C: Disagreement Audit (4-Quadrant)

Systematically classifies when and why existing metrics and CGA
reach different conclusions, producing a structured blind-spot taxonomy.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class Quadrant(str, Enum):
    """4-quadrant classification of metric agreement."""
    Q1_BOTH_PASS = "Q1"   # Task PASS, CGA PASS — consensus
    Q2_CGA_DETECTS = "Q2"  # Task PASS, CGA FAIL — CGA catches hidden defect
    Q3_CGA_LENIENT = "Q3"  # Task FAIL, CGA PASS — CGA recognizes process quality
    Q4_BOTH_FAIL = "Q4"   # Task FAIL, CGA FAIL — consensus


class FailureMode(str, Enum):
    """Q2 failure mode classification."""
    TIMING = "timing"          # Task done but deadline violated
    SEQUENCE = "sequence"      # Actions done but wrong order
    OVERACTION = "overaction"  # Extra off-protocol actions
    SAFETY = "safety"          # Contraindicated action performed
    MIXED = "mixed"            # Multiple violation types


@dataclass
class EpisodeClassification:
    """Classification of a single episode."""
    episode_id: str
    scenario_id: str
    agent_id: str
    source: str  # "original" or "perturbed"
    task_completion_pass: bool
    cga_compliance: float
    cga_pass: bool
    quadrant: Quadrant
    failure_mode: Optional[FailureMode]
    sub_scores: Dict[str, float]
    violations_by_type: Dict[str, int]
    perturbation_type: Optional[str] = None


@dataclass
class QuadrantResult:
    """Aggregated result for the 4-quadrant analysis."""
    threshold: float
    total_episodes: int
    q1_count: int
    q2_count: int
    q3_count: int
    q4_count: int
    q2_failure_modes: Dict[str, int]
    q2_natural_count: int   # Q2 without perturbation
    q2_perturbed_count: int  # Q2 from perturbation
    by_scenario: Dict[str, Dict[str, int]]
    by_agent: Dict[str, Dict[str, int]]


CGA_THRESHOLDS = [0.50, 0.60, 0.70, 0.80]
DEFAULT_CGA_THRESHOLD = 0.70


class DisagreementAudit:
    """Runs the 4-Quadrant Disagreement Audit.

    Classifies all episodes (original + perturbed) into 4 quadrants
    based on Task Completion vs CGA Compliance agreement/disagreement.
    """

    def __init__(
        self,
        output_dir: str = "evidence_pack/experiments",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.episodes: List[EpisodeClassification] = []

    def load_original_results(
        self,
        results_dirs: List[str],
    ) -> int:
        """Load original episode results from result JSON files.

        Args:
            results_dirs: List of directories containing result JSON files.

        Returns:
            Number of episodes loaded.
        """
        count = 0
        for results_dir in results_dirs:
            rdir = Path(results_dir)
            if not rdir.exists():
                logger.warning(f"Results directory not found: {rdir}")
                continue

            for json_file in sorted(rdir.glob("*.json")):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    scenario_id = data.get("scenario_id", "")
                    agent_id = data.get("agent_id", "")
                    compliance = data.get("compliance_score", 0.0)
                    sub_scores = data.get("sub_scores", {})
                    violations = data.get("violations_by_type", {})

                    # Task completion: C2 (mandatory completion) == 1.0
                    c2 = sub_scores.get("C2_mandatory_completion", 0.0)
                    task_pass = c2 >= 1.0

                    self.episodes.append(
                        EpisodeClassification(
                            episode_id=json_file.stem,
                            scenario_id=scenario_id,
                            agent_id=agent_id,
                            source="original",
                            task_completion_pass=task_pass,
                            cga_compliance=compliance,
                            cga_pass=False,  # Set during classification
                            quadrant=Quadrant.Q1_BOTH_PASS,  # Set during classification
                            failure_mode=None,
                            sub_scores=sub_scores,
                            violations_by_type=violations,
                        )
                    )
                    count += 1
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning(f"Failed to load {json_file}: {exc}")

        logger.info(f"Loaded {count} original episodes")
        return count

    def load_perturbation_results(
        self,
        perturbation_results: List[dict],
    ) -> int:
        """Load results from Experiment A perturbation.

        Args:
            perturbation_results: List of PerturbationResult-like dicts.

        Returns:
            Number of episodes loaded.
        """
        count = 0
        for r in perturbation_results:
            if r.get("description") == "Baseline (no perturbation)":
                continue

            self.episodes.append(
                EpisodeClassification(
                    episode_id=f"perturbed_{r['scenario_id']}_{r['perturbation_type']}",
                    scenario_id=r["scenario_id"],
                    agent_id="perturbed",
                    source="perturbed",
                    task_completion_pass=r["task_completion_pass"],
                    cga_compliance=r["cga_compliance"],
                    cga_pass=False,
                    quadrant=Quadrant.Q1_BOTH_PASS,
                    failure_mode=None,
                    sub_scores=r.get("cga_sub_scores", {}),
                    violations_by_type=r.get("violations_by_type", {}),
                    perturbation_type=r.get("perturbation_type"),
                )
            )
            count += 1

        logger.info(f"Loaded {count} perturbation episodes")
        return count

    def classify(
        self,
        cga_threshold: float = DEFAULT_CGA_THRESHOLD,
    ) -> QuadrantResult:
        """Classify all loaded episodes into 4 quadrants.

        Args:
            cga_threshold: CGA compliance threshold for PASS/FAIL.
        """
        q_counts = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0}
        q2_modes: Dict[str, int] = {}
        q2_natural = 0
        q2_perturbed = 0
        by_scenario: Dict[str, Dict[str, int]] = {}
        by_agent: Dict[str, Dict[str, int]] = {}

        for ep in self.episodes:
            ep.cga_pass = ep.cga_compliance >= cga_threshold

            # Classify quadrant
            if ep.task_completion_pass and ep.cga_pass:
                ep.quadrant = Quadrant.Q1_BOTH_PASS
            elif ep.task_completion_pass and not ep.cga_pass:
                ep.quadrant = Quadrant.Q2_CGA_DETECTS
            elif not ep.task_completion_pass and ep.cga_pass:
                ep.quadrant = Quadrant.Q3_CGA_LENIENT
            else:
                ep.quadrant = Quadrant.Q4_BOTH_FAIL

            q_counts[ep.quadrant.value] += 1

            # Q2 failure mode analysis
            if ep.quadrant == Quadrant.Q2_CGA_DETECTS:
                ep.failure_mode = self._classify_failure_mode(ep)
                mode_key = ep.failure_mode.value
                q2_modes[mode_key] = q2_modes.get(mode_key, 0) + 1

                if ep.source == "original":
                    q2_natural += 1
                else:
                    q2_perturbed += 1

            # By scenario
            if ep.scenario_id not in by_scenario:
                by_scenario[ep.scenario_id] = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0}
            by_scenario[ep.scenario_id][ep.quadrant.value] += 1

            # By agent
            if ep.agent_id not in by_agent:
                by_agent[ep.agent_id] = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0}
            by_agent[ep.agent_id][ep.quadrant.value] += 1

        return QuadrantResult(
            threshold=cga_threshold,
            total_episodes=len(self.episodes),
            q1_count=q_counts["Q1"],
            q2_count=q_counts["Q2"],
            q3_count=q_counts["Q3"],
            q4_count=q_counts["Q4"],
            q2_failure_modes=q2_modes,
            q2_natural_count=q2_natural,
            q2_perturbed_count=q2_perturbed,
            by_scenario=by_scenario,
            by_agent=by_agent,
        )

    def run_threshold_sensitivity(self) -> Dict[float, QuadrantResult]:
        """Run classification at multiple CGA thresholds."""
        results: Dict[float, QuadrantResult] = {}
        for threshold in CGA_THRESHOLDS:
            results[threshold] = self.classify(threshold)
        return results

    def save_results(self, result: Optional[QuadrantResult] = None) -> None:
        """Save audit results to evidence_pack."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if result is None:
            result = self.classify()

        # Threshold sensitivity
        sensitivity = self.run_threshold_sensitivity()

        # JSON
        json_path = self.output_dir / "disagreement_audit.json"
        json_data = {
            "experiment": "C_disagreement_audit",
            "description": "4-Quadrant Disagreement Audit",
            "default_threshold": DEFAULT_CGA_THRESHOLD,
            "default_result": self._result_to_dict(result),
            "threshold_sensitivity": {
                str(t): self._result_to_dict(r)
                for t, r in sensitivity.items()
            },
            "episode_details": [
                {
                    "episode_id": ep.episode_id,
                    "scenario_id": ep.scenario_id,
                    "agent_id": ep.agent_id,
                    "source": ep.source,
                    "task_completion_pass": ep.task_completion_pass,
                    "cga_compliance": ep.cga_compliance,
                    "cga_pass": ep.cga_pass,
                    "quadrant": ep.quadrant.value,
                    "failure_mode": ep.failure_mode.value if ep.failure_mode else None,
                    "perturbation_type": ep.perturbation_type,
                }
                for ep in self.episodes
            ],
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        # Markdown
        md_path = self.output_dir / "disagreement_audit.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self._generate_markdown(result, sensitivity))

        # LaTeX
        tables_dir = self.output_dir.parent / "tables"
        tables_dir.mkdir(parents=True, exist_ok=True)
        tex_path = tables_dir / "table_quadrant.tex"
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(self._generate_latex(result))

        logger.info(f"Audit results saved: {json_path}, {md_path}, {tex_path}")

    @staticmethod
    def _classify_failure_mode(ep: EpisodeClassification) -> FailureMode:
        """Classify Q2 episode into specific failure mode."""
        violations = ep.violations_by_type
        mode_flags: List[str] = []

        if violations.get("timing", 0) > 0:
            mode_flags.append("timing")
        if violations.get("sequence", 0) > 0:
            mode_flags.append("sequence")
        if violations.get("deviation", 0) > 0:
            mode_flags.append("overaction")
        if violations.get("commission", 0) > 0:
            mode_flags.append("safety")

        if len(mode_flags) > 1:
            return FailureMode.MIXED
        if len(mode_flags) == 1:
            mode = mode_flags[0]
            if mode == "timing":
                return FailureMode.TIMING
            if mode == "sequence":
                return FailureMode.SEQUENCE
            if mode == "overaction":
                return FailureMode.OVERACTION
            if mode == "safety":
                return FailureMode.SAFETY
        return FailureMode.MIXED

    @staticmethod
    def _result_to_dict(result: QuadrantResult) -> Dict:
        """Convert QuadrantResult to serializable dict."""
        return {
            "threshold": result.threshold,
            "total_episodes": result.total_episodes,
            "q1_count": result.q1_count,
            "q2_count": result.q2_count,
            "q3_count": result.q3_count,
            "q4_count": result.q4_count,
            "q2_failure_modes": result.q2_failure_modes,
            "q2_natural_count": result.q2_natural_count,
            "q2_perturbed_count": result.q2_perturbed_count,
            "by_scenario": result.by_scenario,
            "by_agent": result.by_agent,
        }

    @staticmethod
    def _generate_markdown(
        result: QuadrantResult,
        sensitivity: Dict[float, QuadrantResult],
    ) -> str:
        """Generate markdown report."""
        lines = [
            "# Experiment C: Disagreement Audit (4-Quadrant)\n",
            "## 4-Quadrant Matrix\n",
            f"CGA Threshold: {result.threshold:.0%}\n",
            "|                  | CGA PASS | CGA FAIL |",
            "|------------------|----------|----------|",
            f"| **Task PASS**    | Q1: {result.q1_count} | Q2: {result.q2_count} |",
            f"| **Task FAIL**    | Q3: {result.q3_count} | Q4: {result.q4_count} |",
            "",
            f"Total episodes: {result.total_episodes}\n",
            "## Q2 Analysis (Task PASS / CGA FAIL)\n",
            f"- Total Q2: {result.q2_count}",
            f"- Naturally occurring: {result.q2_natural_count}",
            f"- From perturbation: {result.q2_perturbed_count}",
            "",
            "### Failure Mode Breakdown\n",
            "| Mode | Count |",
            "|------|-------|",
        ]

        for mode, count in sorted(result.q2_failure_modes.items()):
            lines.append(f"| {mode} | {count} |")

        lines.extend([
            "",
            "## Q3 Analysis (Task FAIL / CGA PASS)\n",
            f"- Total Q3: {result.q3_count}",
            "- Interpretation: CGA recognizes process quality independent of outcome",
            "",
            "## Threshold Sensitivity\n",
            "| Threshold | Q1 | Q2 | Q3 | Q4 |",
            "|-----------|----|----|----|----|",
        ])

        for threshold in sorted(sensitivity.keys()):
            r = sensitivity[threshold]
            lines.append(
                f"| {threshold:.0%} | {r.q1_count} | {r.q2_count} | "
                f"{r.q3_count} | {r.q4_count} |"
            )

        lines.extend([
            "",
            "## By Scenario\n",
            "| Scenario | Q1 | Q2 | Q3 | Q4 |",
            "|----------|----|----|----|----|",
        ])

        for scenario, counts in sorted(result.by_scenario.items()):
            lines.append(
                f"| {scenario} | {counts['Q1']} | {counts['Q2']} | "
                f"{counts['Q3']} | {counts['Q4']} |"
            )

        return "\n".join(lines)

    @staticmethod
    def _generate_latex(result: QuadrantResult) -> str:
        """Generate LaTeX table for paper."""
        lines = [
            r"\begin{table}[t]",
            r"\centering",
            r"\caption{4-Quadrant disagreement audit between task-completion metric and CGA.}",
            r"\label{tab:quadrant}",
            r"\begin{tabular}{lcc}",
            r"\toprule",
            r" & CGA PASS & CGA FAIL \\",
            r"\midrule",
            f"Task PASS & Q1: {result.q1_count} & \\textbf{{Q2: {result.q2_count}}} \\\\",
            f"Task FAIL & Q3: {result.q3_count} & Q4: {result.q4_count} \\\\",
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ]
        return "\n".join(lines)
