"""
Comparative Conformance Analysis.

Analyzes multiple ConformanceReports across agents and domains to produce:
- Pairwise comparisons between agents
- Domain bias detection
- Agent profiles (strengths/weaknesses)
- Fairness metrics (variance-based parity)
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Dict, List, Optional, Set, Tuple


# --- Configuration ---

@dataclass
class ComparativeConfig:
    """Configuration for comparative analysis."""
    enable_fairness_analysis: bool = True
    enable_domain_bias: bool = True
    enable_agent_profiles: bool = True
    significance_threshold: float = 0.1
    bias_threshold: float = 0.15
    profile_dimensions: List[str] = field(default_factory=lambda: [
        "completeness", "ordering", "timeliness", "safety",
    ])


# --- Data Structures ---

@dataclass
class ScenarioResult:
    """Single scenario evaluation result for an agent."""
    scenario_id: str
    agent_id: str
    domain: str
    report: Any
    rubric_report: Optional[Any] = None


@dataclass
class PairwiseComparison:
    """Comparison between two agents within a domain."""
    agent_a: str
    agent_b: str
    domain: str
    score_diff: float
    dimension_diffs: Dict[str, float]
    significant: bool
    advantage: Optional[str]


@dataclass
class DomainBiasResult:
    """Domain bias for a single agent in a single domain."""
    agent_id: str
    domain: str
    mean_score: float
    overall_mean: float
    bias: float
    is_biased: bool
    direction: str


@dataclass
class AgentProfile:
    """Profile summarizing an agent's performance characteristics."""
    agent_id: str
    scenario_count: int
    mean_scores: Dict[str, float]
    std_scores: Dict[str, float]
    strengths: List[str]
    weaknesses: List[str]
    risk_aversion_score: float
    domain_specialization: Optional[str]


@dataclass
class FairnessMetrics:
    """Fairness analysis across agents."""
    overall_variance: float
    max_score_gap: float
    domain_parity: Dict[str, float]
    is_fair: bool
    unfair_domains: List[str]


@dataclass
class ComparativeAnalysis:
    """Full comparative analysis result."""
    scenario_results: List[ScenarioResult]
    pairwise_comparisons: List[PairwiseComparison]
    domain_biases: List[DomainBiasResult]
    agent_profiles: List[AgentProfile]
    fairness: FairnessMetrics
    summary: Dict[str, Any]


# --- ComparativeAnalyzer ---

class ComparativeAnalyzer:
    """Computes comparative conformance metrics across agents and domains."""

    def __init__(self, config: Optional[ComparativeConfig] = None):
        self.config = config or ComparativeConfig()

    def analyze(self, results: List[ScenarioResult]) -> ComparativeAnalysis:
        """Run full comparative analysis on a set of scenario results.

        Args:
            results: List of ScenarioResult from multiple agents/domains.

        Returns:
            ComparativeAnalysis with pairwise, bias, profiles, and fairness.
        """
        pairwise = self.compute_pairwise(results)
        domain_biases = (
            self.detect_domain_bias(results) if self.config.enable_domain_bias else []
        )
        agent_profiles = (
            self.build_agent_profiles(results) if self.config.enable_agent_profiles else []
        )
        fairness = (
            self.compute_fairness(results) if self.config.enable_fairness_analysis
            else FairnessMetrics(
                overall_variance=0.0,
                max_score_gap=0.0,
                domain_parity={},
                is_fair=True,
                unfair_domains=[],
            )
        )

        summary = self._build_summary(results, pairwise, domain_biases, agent_profiles, fairness)

        return ComparativeAnalysis(
            scenario_results=results,
            pairwise_comparisons=pairwise,
            domain_biases=domain_biases,
            agent_profiles=agent_profiles,
            fairness=fairness,
            summary=summary,
        )

    def compute_pairwise(self, results: List[ScenarioResult]) -> List[PairwiseComparison]:
        """Compute pairwise comparisons between agents per domain.

        For each unique (agent_a, agent_b, domain) triple, computes mean score
        differences and determines statistical significance.
        """
        by_domain = self._group_by_domain(results)
        comparisons: List[PairwiseComparison] = []

        for domain, domain_results in by_domain.items():
            by_agent = self._group_by_agent(domain_results)
            agents = sorted(by_agent.keys())

            for a, b in combinations(agents, 2):
                scores_a = [self._extract_score(r) for r in by_agent[a]]
                scores_b = [self._extract_score(r) for r in by_agent[b]]

                mean_a = sum(scores_a) / len(scores_a) if scores_a else 0.0
                mean_b = sum(scores_b) / len(scores_b) if scores_b else 0.0
                score_diff = mean_a - mean_b

                dim_diffs = self._compute_dimension_diffs(by_agent[a], by_agent[b])
                significant = abs(score_diff) > self.config.significance_threshold

                advantage: Optional[str] = None
                if significant:
                    advantage = a if score_diff > 0 else b

                comparisons.append(PairwiseComparison(
                    agent_a=a,
                    agent_b=b,
                    domain=domain,
                    score_diff=score_diff,
                    dimension_diffs=dim_diffs,
                    significant=significant,
                    advantage=advantage,
                ))

        return comparisons

    def detect_domain_bias(self, results: List[ScenarioResult]) -> List[DomainBiasResult]:
        """Detect domain bias for each agent.

        Bias = domain_mean - overall_mean for each agent.
        """
        by_agent = self._group_by_agent(results)
        biases: List[DomainBiasResult] = []

        for agent_id, agent_results in by_agent.items():
            all_scores = [self._extract_score(r) for r in agent_results]
            overall_mean = sum(all_scores) / len(all_scores) if all_scores else 0.0

            domain_groups = self._group_by_domain(agent_results)
            for domain, dr in domain_groups.items():
                domain_scores = [self._extract_score(r) for r in dr]
                domain_mean = (
                    sum(domain_scores) / len(domain_scores) if domain_scores else 0.0
                )
                bias = domain_mean - overall_mean
                is_biased = abs(bias) > self.config.bias_threshold
                direction = "advantage" if bias > 0 else "disadvantage"

                biases.append(DomainBiasResult(
                    agent_id=agent_id,
                    domain=domain,
                    mean_score=domain_mean,
                    overall_mean=overall_mean,
                    bias=bias,
                    is_biased=is_biased,
                    direction=direction,
                ))

        return biases

    def build_agent_profiles(self, results: List[ScenarioResult]) -> List[AgentProfile]:
        """Build performance profiles for each agent.

        Identifies strengths (top 2 dimensions), weaknesses (bottom 2),
        risk_aversion_score, and domain_specialization.
        """
        by_agent = self._group_by_agent(results)
        profiles: List[AgentProfile] = []

        for agent_id, agent_results in sorted(by_agent.items()):
            dim_values: Dict[str, List[float]] = defaultdict(list)

            for r in agent_results:
                dim_scores = self._extract_dimension_scores(r)
                for dim in self.config.profile_dimensions:
                    if dim in dim_scores:
                        dim_values[dim].append(dim_scores[dim])

            mean_scores: Dict[str, float] = {}
            std_scores: Dict[str, float] = {}
            for dim, values in dim_values.items():
                mean_scores[dim] = sum(values) / len(values) if values else 0.0
                std_scores[dim] = _std(values) if len(values) > 1 else 0.0

            # Strengths and weaknesses
            sorted_dims = sorted(mean_scores.items(), key=lambda x: x[1], reverse=True)
            strengths = [d[0] for d in sorted_dims[:2]] if len(sorted_dims) >= 2 else [d[0] for d in sorted_dims]
            weaknesses = [d[0] for d in sorted_dims[-2:]] if len(sorted_dims) >= 2 else []

            # Risk aversion = safety score
            risk_aversion = mean_scores.get("safety", 0.0)

            # Domain specialization
            domain_groups = self._group_by_domain(agent_results)
            domain_means: Dict[str, float] = {}
            for domain, dr in domain_groups.items():
                scores = [self._extract_score(r) for r in dr]
                domain_means[domain] = sum(scores) / len(scores) if scores else 0.0

            domain_specialization: Optional[str] = None
            if domain_means:
                domain_specialization = max(domain_means, key=lambda d: domain_means[d])

            profiles.append(AgentProfile(
                agent_id=agent_id,
                scenario_count=len(agent_results),
                mean_scores=mean_scores,
                std_scores=std_scores,
                strengths=strengths,
                weaknesses=weaknesses,
                risk_aversion_score=risk_aversion,
                domain_specialization=domain_specialization,
            ))

        return profiles

    def compute_fairness(self, results: List[ScenarioResult]) -> FairnessMetrics:
        """Compute fairness metrics across agents.

        - overall_variance: variance of agent mean scores
        - max_score_gap: max - min agent score
        - domain_parity: per-domain variance across agents
        - is_fair: all domain_parity < significance_threshold
        """
        by_agent = self._group_by_agent(results)
        agent_means: List[float] = []

        for agent_id, agent_results in by_agent.items():
            scores = [self._extract_score(r) for r in agent_results]
            agent_means.append(sum(scores) / len(scores) if scores else 0.0)

        overall_variance = _variance(agent_means) if len(agent_means) > 1 else 0.0
        max_score_gap = (max(agent_means) - min(agent_means)) if agent_means else 0.0

        # Domain parity
        by_domain = self._group_by_domain(results)
        domain_parity: Dict[str, float] = {}
        unfair_domains: List[str] = []

        for domain, domain_results in by_domain.items():
            agent_domain_groups = self._group_by_agent(domain_results)
            agent_domain_means = []
            for agent_results_in_domain in agent_domain_groups.values():
                scores = [self._extract_score(r) for r in agent_results_in_domain]
                agent_domain_means.append(
                    sum(scores) / len(scores) if scores else 0.0
                )
            var = _variance(agent_domain_means) if len(agent_domain_means) > 1 else 0.0
            domain_parity[domain] = var
            if var >= self.config.significance_threshold:
                unfair_domains.append(domain)

        is_fair = len(unfair_domains) == 0

        return FairnessMetrics(
            overall_variance=overall_variance,
            max_score_gap=max_score_gap,
            domain_parity=domain_parity,
            is_fair=is_fair,
            unfair_domains=unfair_domains,
        )

    # --- Private Helpers ---

    def _group_by_agent(self, results: List[ScenarioResult]) -> Dict[str, List[ScenarioResult]]:
        groups: Dict[str, List[ScenarioResult]] = defaultdict(list)
        for r in results:
            groups[r.agent_id].append(r)
        return dict(groups)

    def _group_by_domain(self, results: List[ScenarioResult]) -> Dict[str, List[ScenarioResult]]:
        groups: Dict[str, List[ScenarioResult]] = defaultdict(list)
        for r in results:
            groups[r.domain].append(r)
        return dict(groups)

    def _extract_score(self, result: ScenarioResult) -> float:
        """Extract compliance_score from a ScenarioResult."""
        report = result.report
        if report is None:
            return 0.0
        # Try rubric_report weighted_composite first
        if result.rubric_report is not None:
            rubric_score = getattr(result.rubric_report, "rubric_score", None)
            if rubric_score is not None:
                return getattr(rubric_score, "weighted_composite", 0.0)
        return getattr(report, "compliance_score", 0.0)

    def _extract_dimension_scores(self, result: ScenarioResult) -> Dict[str, float]:
        """Extract per-dimension scores from a ScenarioResult."""
        # Try rubric_report dimension_scores first
        if result.rubric_report is not None:
            rubric_score = getattr(result.rubric_report, "rubric_score", None)
            if rubric_score is not None:
                return getattr(rubric_score, "dimension_scores", {})

        # Fallback to SubScores from report
        report = result.report
        if report is None:
            return {}
        sub = getattr(report, "sub_scores", None)
        if sub is None:
            return {}
        return {
            "completeness": getattr(sub, "completeness", 0.0),
            "ordering": getattr(sub, "ordering", 0.0),
            "timeliness": getattr(sub, "timeliness", 0.0),
            "safety": getattr(sub, "safety", 0.0),
        }

    def _compute_dimension_diffs(
        self,
        results_a: List[ScenarioResult],
        results_b: List[ScenarioResult],
    ) -> Dict[str, float]:
        """Compute mean dimension score differences between two agent result sets."""
        dims_a: Dict[str, List[float]] = defaultdict(list)
        dims_b: Dict[str, List[float]] = defaultdict(list)

        for r in results_a:
            for dim, score in self._extract_dimension_scores(r).items():
                dims_a[dim].append(score)
        for r in results_b:
            for dim, score in self._extract_dimension_scores(r).items():
                dims_b[dim].append(score)

        all_dims = set(dims_a.keys()) | set(dims_b.keys())
        diffs: Dict[str, float] = {}
        for dim in all_dims:
            mean_a = sum(dims_a[dim]) / len(dims_a[dim]) if dims_a[dim] else 0.0
            mean_b = sum(dims_b[dim]) / len(dims_b[dim]) if dims_b[dim] else 0.0
            diffs[dim] = mean_a - mean_b

        return diffs

    def _build_summary(
        self,
        results: List[ScenarioResult],
        pairwise: List[PairwiseComparison],
        biases: List[DomainBiasResult],
        profiles: List[AgentProfile],
        fairness: FairnessMetrics,
    ) -> Dict[str, Any]:
        """Build aggregate summary statistics."""
        agents = set(r.agent_id for r in results)
        domains = set(r.domain for r in results)

        return {
            "total_scenarios": len(results),
            "num_agents": len(agents),
            "num_domains": len(domains),
            "agents": sorted(agents),
            "domains": sorted(domains),
            "significant_comparisons": sum(1 for p in pairwise if p.significant),
            "biased_agent_domains": sum(1 for b in biases if b.is_biased),
            "is_fair": fairness.is_fair,
            "max_score_gap": fairness.max_score_gap,
        }


# --- Utility Functions ---

def _variance(values: List[float]) -> float:
    """Compute population variance."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def _std(values: List[float]) -> float:
    """Compute population standard deviation."""
    return _variance(values) ** 0.5
