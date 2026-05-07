"""
Statistical comparison tools for multi-agent evaluation.

Implements paired t-test, Wilcoxon signed-rank, bootstrap CI,
Cohen's d, Cliff's delta, and Bonferroni correction.
"""

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
import json
import logging
import warnings

logger = logging.getLogger(__name__)

try:
    import numpy as np
    from scipy import stats as scipy_stats
except ImportError:
    np = None  # type: ignore
    scipy_stats = None  # type: ignore
    logger.warning("scipy/numpy not installed. Statistical comparison unavailable.")


@dataclass
class StatisticalTestResult:
    """Result of a statistical test."""
    test_name: str
    statistic: float
    p_value: float
    significant: bool
    alpha: float = 0.05

    def __repr__(self) -> str:
        sig = "***" if self.significant else "n.s."
        return f"{self.test_name}: stat={self.statistic:.3f}, p={self.p_value:.4f} {sig}"


@dataclass
class EffectSizeResult:
    """Effect size measure."""
    measure_name: str
    value: float
    interpretation: str  # negligible, small, medium, large

    def __repr__(self) -> str:
        return f"{self.measure_name}: {self.value:.3f} ({self.interpretation})"


@dataclass
class PairwiseComparison:
    """Complete pairwise comparison between two agents."""
    agent1: str
    agent2: str
    scenario: str
    n_samples: int
    mean_diff: float
    ci_lower: float
    ci_upper: float
    tests: List[StatisticalTestResult] = field(default_factory=list)
    effect_sizes: List[EffectSizeResult] = field(default_factory=list)
    winner: Optional[str] = None


class ModelComparisonAnalyzer:
    """Statistical comparison of multiple agents across scenarios."""

    def __init__(self, alpha: float = 0.05, bootstrap_iterations: int = 10000):
        if np is None or scipy_stats is None:
            raise ImportError(
                "scipy and numpy are required for ModelComparisonAnalyzer. "
                "Install with: pip install scipy numpy"
            )
        self.alpha = alpha
        self.bootstrap_iterations = bootstrap_iterations

    def load_experiment_results(self, summary_path: Path) -> Dict[str, Any]:
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def extract_scores_by_agent_scenario(
        self, results: List[Dict],
    ) -> Dict[Tuple[str, str], List[float]]:
        """Extract scores organized by (agent_id, scenario_id).

        Supports both 'agent_id' and 'baseline_id' field names for
        compatibility with different experiment runner formats.
        """
        scores: Dict[Tuple[str, str], List[float]] = {}
        for r in results:
            agent = r.get("agent_id") or r.get("baseline_id", "unknown")
            scenario = r.get("scenario_id", "unknown")
            key = (agent, scenario)
            scores.setdefault(key, []).append(r["compliance_score"])
        return scores

    # ------------------------------------------------------------------
    # Statistical tests
    # ------------------------------------------------------------------

    def paired_t_test(
        self, scores1: List[float], scores2: List[float],
    ) -> StatisticalTestResult:
        """Paired t-test for matched samples."""
        if len(scores1) != len(scores2):
            raise ValueError("Score lists must be the same length for paired test")
        if len(scores1) < 2:
            return StatisticalTestResult("Paired t-test", 0.0, 1.0, False, self.alpha)

        stat, p = scipy_stats.ttest_rel(scores1, scores2)
        return StatisticalTestResult("Paired t-test", float(stat), float(p),
                                     p < self.alpha, self.alpha)

    def wilcoxon_signed_rank(
        self, scores1: List[float], scores2: List[float],
    ) -> StatisticalTestResult:
        """Wilcoxon signed-rank test (non-parametric)."""
        if len(scores1) != len(scores2):
            raise ValueError("Score lists must be the same length for paired test")
        if len(scores1) < 2:
            return StatisticalTestResult("Wilcoxon signed-rank", 0.0, 1.0, False, self.alpha)

        diffs = [a - b for a, b in zip(scores1, scores2)]
        if all(d == 0 for d in diffs):
            return StatisticalTestResult("Wilcoxon signed-rank", 0.0, 1.0, False, self.alpha)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stat, p = scipy_stats.wilcoxon(scores1, scores2)
        return StatisticalTestResult("Wilcoxon signed-rank", float(stat), float(p),
                                     p < self.alpha, self.alpha)

    def bootstrap_ci(
        self,
        scores1: List[float],
        scores2: List[float],
        confidence_level: float = 0.95,
    ) -> Tuple[float, float, float]:
        """Bootstrap confidence interval for mean difference.

        Returns (mean_diff, ci_lower, ci_upper).
        """
        a1 = np.array(scores1)
        a2 = np.array(scores2)
        observed_diff = float(np.mean(a1) - np.mean(a2))

        n = len(a1)
        rng = np.random.default_rng()
        diffs = np.empty(self.bootstrap_iterations)
        for i in range(self.bootstrap_iterations):
            idx = rng.choice(n, size=n, replace=True)
            diffs[i] = np.mean(a1[idx]) - np.mean(a2[idx])

        alpha_half = (1 - confidence_level) / 2
        ci_lower = float(np.percentile(diffs, alpha_half * 100))
        ci_upper = float(np.percentile(diffs, (1 - alpha_half) * 100))
        return observed_diff, ci_lower, ci_upper

    # ------------------------------------------------------------------
    # Effect sizes
    # ------------------------------------------------------------------

    def cohens_d(self, scores1: List[float], scores2: List[float]) -> EffectSizeResult:
        """Cohen's d effect size with pooled standard deviation."""
        a1, a2 = np.array(scores1), np.array(scores2)
        n1, n2 = len(a1), len(a2)
        pooled_std = np.sqrt(
            ((n1 - 1) * np.var(a1, ddof=1) + (n2 - 1) * np.var(a2, ddof=1))
            / (n1 + n2 - 2)
        )
        d = float((np.mean(a1) - np.mean(a2)) / pooled_std) if pooled_std > 0 else 0.0
        return EffectSizeResult("Cohen's d", d, self._interpret_cohens_d(abs(d)))

    @staticmethod
    def _interpret_cohens_d(abs_d: float) -> str:
        if abs_d < 0.2:
            return "negligible"
        if abs_d < 0.5:
            return "small"
        if abs_d < 0.8:
            return "medium"
        return "large"

    def cliff_delta(self, scores1: List[float], scores2: List[float]) -> EffectSizeResult:
        """Cliff's delta (non-parametric effect size)."""
        n1, n2 = len(scores1), len(scores2)
        dom = sum(
            (1 if s1 > s2 else (-1 if s1 < s2 else 0))
            for s1 in scores1
            for s2 in scores2
        )
        delta = dom / (n1 * n2) if n1 * n2 > 0 else 0.0
        return EffectSizeResult("Cliff's delta", delta,
                                self._interpret_cliff_delta(abs(delta)))

    @staticmethod
    def _interpret_cliff_delta(abs_d: float) -> str:
        if abs_d < 0.147:
            return "negligible"
        if abs_d < 0.33:
            return "small"
        if abs_d < 0.474:
            return "medium"
        return "large"

    # ------------------------------------------------------------------
    # Multiple comparison correction
    # ------------------------------------------------------------------

    def bonferroni_correction(self, p_values: List[float]) -> List[bool]:
        """Apply Bonferroni correction for multiple comparisons."""
        if not p_values:
            return []
        corrected_alpha = self.alpha / len(p_values)
        return [p < corrected_alpha for p in p_values]

    # ------------------------------------------------------------------
    # Full comparison
    # ------------------------------------------------------------------

    def compare_pair(
        self,
        scores1: List[float],
        scores2: List[float],
        agent1_name: str,
        agent2_name: str,
        scenario_id: str,
    ) -> PairwiseComparison:
        """Perform complete pairwise comparison."""
        min_len = min(len(scores1), len(scores2))
        s1, s2 = scores1[:min_len], scores2[:min_len]

        t_test = self.paired_t_test(s1, s2)
        wilcoxon = self.wilcoxon_signed_rank(s1, s2)
        mean_diff, ci_lo, ci_hi = self.bootstrap_ci(s1, s2)
        cd = self.cohens_d(s1, s2)
        cliff = self.cliff_delta(s1, s2)

        winner = None
        if t_test.significant:
            winner = agent1_name if mean_diff > 0 else agent2_name

        return PairwiseComparison(
            agent1=agent1_name,
            agent2=agent2_name,
            scenario=scenario_id,
            n_samples=min_len,
            mean_diff=mean_diff,
            ci_lower=ci_lo,
            ci_upper=ci_hi,
            tests=[t_test, wilcoxon],
            effect_sizes=[cd, cliff],
            winner=winner,
        )

    def compare_all_agents(
        self,
        summary_path: Path,
        per_scenario: bool = True,
    ) -> List[PairwiseComparison]:
        """Compare all agent pairs, optionally per-scenario."""
        data = self.load_experiment_results(summary_path)
        results = data.get("results", [])
        scores_dict = self.extract_scores_by_agent_scenario(results)

        agents = sorted({a for a, _ in scores_dict})
        scenarios = sorted({s for _, s in scores_dict})
        comparisons: List[PairwiseComparison] = []

        if per_scenario:
            for scenario in scenarios:
                for i, a1 in enumerate(agents):
                    for a2 in agents[i + 1:]:
                        k1, k2 = (a1, scenario), (a2, scenario)
                        if k1 in scores_dict and k2 in scores_dict:
                            comparisons.append(self.compare_pair(
                                scores_dict[k1], scores_dict[k2], a1, a2, scenario,
                            ))
        else:
            for i, a1 in enumerate(agents):
                for a2 in agents[i + 1:]:
                    s1 = [s for sc in scenarios for s in scores_dict.get((a1, sc), [])]
                    s2 = [s for sc in scenarios for s in scores_dict.get((a2, sc), [])]
                    if s1 and s2:
                        comparisons.append(self.compare_pair(s1, s2, a1, a2, "overall"))

        # Apply Bonferroni correction across all p-values
        all_p: List[float] = []
        for comp in comparisons:
            all_p.extend(t.p_value for t in comp.tests)
        corrected = self.bonferroni_correction(all_p)
        idx = 0
        for comp in comparisons:
            for t in comp.tests:
                t.significant = corrected[idx]
                idx += 1
            # Re-evaluate winner after correction
            primary = comp.tests[0] if comp.tests else None
            if primary and primary.significant:
                comp.winner = comp.agent1 if comp.mean_diff > 0 else comp.agent2
            else:
                comp.winner = None

        return comparisons
