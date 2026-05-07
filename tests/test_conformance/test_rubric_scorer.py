"""Tests for rubric_scorer.py - Domain-Specific Evidence-Weighted Rubric Scoring."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest

from cga_bench.semantic_layer.conformance.rubric_scorer import (
    DomainRubricScore,
    EvidenceTier,
    RubricDimension,
    RubricReport,
    RubricScorer,
    RubricScoringConfig,
    ViolationByTier,
    _DEFAULT_DOMAIN_WEIGHTS,
)


# --- Test Fixtures ---

@dataclass
class MockSubScores:
    completeness: float = 1.0
    ordering: float = 1.0
    timeliness: float = 1.0
    safety: float = 1.0


@dataclass
class MockViolation:
    constraint_id: str = ""
    template: str = ""
    channel: str = "req"
    detail: str = ""
    weight: float = 1.0


@dataclass
class MockConformanceReport:
    cpg_id: str = "test_cpg"
    activity_count: int = 10
    phases_present: List[str] = field(default_factory=list)
    missing_phases: List[str] = field(default_factory=list)
    phase_order_violations: List[str] = field(default_factory=list)
    constraint_violations: List[MockViolation] = field(default_factory=list)
    compliance_cost: float = 0.0
    compliance_score: float = 1.0
    compliance_cost_breakdown: Dict[str, float] = field(default_factory=dict)
    compliance_score_breakdown: Dict[str, float] = field(default_factory=dict)
    derived_flags: Dict[str, bool] = field(default_factory=dict)
    sub_scores: Optional[MockSubScores] = None


@dataclass
class MockConstraint:
    constraint_id: str = "c1"
    weight: float = 1.0
    evidence_level: Optional[str] = None
    recommendation_class: Optional[str] = None


# --- TestEvidenceTierClassification ---

class TestEvidenceTierClassification:
    """Tests for classify_evidence_tier."""

    def setup_method(self):
        self.scorer = RubricScorer()

    def test_critical_class_I_evidence_A(self):
        assert self.scorer.classify_evidence_tier("A", "I") == EvidenceTier.CRITICAL

    def test_critical_class_I_evidence_1A(self):
        assert self.scorer.classify_evidence_tier("1A", "I") == EvidenceTier.CRITICAL

    def test_critical_case_insensitive(self):
        assert self.scorer.classify_evidence_tier("1a", "I") == EvidenceTier.CRITICAL

    def test_strong_class_I_evidence_B(self):
        assert self.scorer.classify_evidence_tier("B", "I") == EvidenceTier.STRONG

    def test_strong_class_I_evidence_1B(self):
        assert self.scorer.classify_evidence_tier("1B", "I") == EvidenceTier.STRONG

    def test_strong_class_IIa_evidence_A(self):
        assert self.scorer.classify_evidence_tier("A", "IIa") == EvidenceTier.STRONG

    def test_strong_class_IIa_evidence_1A(self):
        assert self.scorer.classify_evidence_tier("1A", "IIa") == EvidenceTier.STRONG

    def test_moderate_class_IIa_evidence_B(self):
        assert self.scorer.classify_evidence_tier("B", "IIa") == EvidenceTier.MODERATE

    def test_moderate_class_IIa_evidence_2A(self):
        assert self.scorer.classify_evidence_tier("2A", "IIa") == EvidenceTier.MODERATE

    def test_moderate_class_IIb_any_evidence(self):
        assert self.scorer.classify_evidence_tier("1A", "IIb") == EvidenceTier.MODERATE
        assert self.scorer.classify_evidence_tier("B", "IIb") == EvidenceTier.MODERATE
        assert self.scorer.classify_evidence_tier(None, "IIb") == EvidenceTier.MODERATE

    def test_discretionary_class_III(self):
        assert self.scorer.classify_evidence_tier("1A", "III") == EvidenceTier.DISCRETIONARY
        assert self.scorer.classify_evidence_tier("B", "III") == EvidenceTier.DISCRETIONARY

    def test_discretionary_evidence_2C(self):
        assert self.scorer.classify_evidence_tier("2C", "I") == EvidenceTier.DISCRETIONARY

    def test_discretionary_evidence_3(self):
        assert self.scorer.classify_evidence_tier("3", "IIa") == EvidenceTier.DISCRETIONARY

    def test_discretionary_both_none(self):
        assert self.scorer.classify_evidence_tier(None, None) == EvidenceTier.DISCRETIONARY

    def test_class_I_unknown_evidence_strong(self):
        """Class I with non-standard evidence → Strong (benefit of doubt)."""
        assert self.scorer.classify_evidence_tier("2A", "I") == EvidenceTier.STRONG

    def test_evidence_only_A_no_class(self):
        """Evidence A but no class → Strong."""
        assert self.scorer.classify_evidence_tier("A", None) == EvidenceTier.STRONG

    def test_evidence_only_B_no_class(self):
        """Evidence B but no class → Moderate."""
        assert self.scorer.classify_evidence_tier("B", None) == EvidenceTier.MODERATE

    def test_evidence_only_2B_no_class(self):
        """Evidence 2B with no class → Discretionary."""
        assert self.scorer.classify_evidence_tier("2B", None) == EvidenceTier.DISCRETIONARY

    def test_rec_class_normalization_lowercase(self):
        assert self.scorer.classify_evidence_tier("A", "i") == EvidenceTier.CRITICAL


# --- TestDomainWeights ---

class TestDomainWeights:
    """Tests for domain weight selection."""

    def setup_method(self):
        self.scorer = RubricScorer()

    def test_known_domain_sepsis(self):
        weights = self.scorer._get_domain_weights("sepsis")
        assert weights["timeliness"] == 0.30
        assert abs(sum(weights.values()) - 1.0) < 1e-9

    def test_known_domain_dka(self):
        weights = self.scorer._get_domain_weights("dka")
        assert weights["safety"] == 0.25

    def test_unknown_domain_falls_back_to_general(self):
        weights = self.scorer._get_domain_weights("unknown_domain")
        assert weights == _DEFAULT_DOMAIN_WEIGHTS["general"]

    def test_config_override_domain_weights(self):
        custom = {"custom": {"completeness": 0.5, "safety": 0.5}}
        config = RubricScoringConfig(domain_weights=custom)
        scorer = RubricScorer(config)
        weights = scorer._get_domain_weights("custom")
        assert weights["completeness"] == 0.5

    def test_all_default_domains_sum_to_one(self):
        for domain, weights in _DEFAULT_DOMAIN_WEIGHTS.items():
            assert abs(sum(weights.values()) - 1.0) < 1e-9, f"{domain} weights don't sum to 1"


# --- TestDimensionScores ---

class TestDimensionScores:
    """Tests for compute_dimension_scores."""

    def setup_method(self):
        self.scorer = RubricScorer()

    def test_from_subscores(self):
        report = MockConformanceReport(
            sub_scores=MockSubScores(
                completeness=0.9,
                ordering=0.8,
                timeliness=0.7,
                safety=1.0,
            )
        )
        scores = self.scorer.compute_dimension_scores(report, [])
        assert scores["completeness"] == 0.9
        assert scores["ordering"] == 0.8
        assert scores["timeliness"] == 0.7
        assert scores["safety"] == 1.0

    def test_fallback_to_compliance_score(self):
        report = MockConformanceReport(compliance_score=0.75)
        scores = self.scorer.compute_dimension_scores(report, [])
        assert scores["completeness"] == 0.75
        assert scores["ordering"] == 0.75

    def test_evidence_adherence_dimension(self):
        constraints = [
            MockConstraint("c1", weight=2.0, evidence_level="1A", recommendation_class="I"),
            MockConstraint("c2", weight=1.0, evidence_level="2C", recommendation_class="III"),
        ]
        report = MockConformanceReport(
            constraint_violations=[MockViolation(constraint_id="c1")]
        )
        scores = self.scorer.compute_dimension_scores(report, constraints)
        # c1 (critical, weight=1.0) violated; c2 (discretionary, weight=0.3) satisfied
        # adherence = 0.3 / (1.0 + 0.3) = 0.2308
        assert scores["evidence_adherence"] < 0.5

    def test_all_six_dimensions_present(self):
        report = MockConformanceReport(sub_scores=MockSubScores())
        scores = self.scorer.compute_dimension_scores(report, [])
        assert len(scores) == 6
        for dim in RubricDimension:
            assert dim.value in scores


# --- TestPriorityAdherence ---

class TestPriorityAdherence:
    """Tests for compute_priority_adherence."""

    def setup_method(self):
        self.scorer = RubricScorer()

    def test_all_satisfied(self):
        constraints = [MockConstraint(f"c{i}", weight=float(i)) for i in range(1, 5)]
        report = MockConformanceReport()
        assert self.scorer.compute_priority_adherence(report, constraints) == 1.0

    def test_high_priority_violated(self):
        constraints = [MockConstraint(f"c{i}", weight=float(i)) for i in range(1, 5)]
        # c4 is highest weight → top 25% (1 constraint)
        report = MockConformanceReport(
            constraint_violations=[MockViolation(constraint_id="c4")]
        )
        assert self.scorer.compute_priority_adherence(report, constraints) == 0.0

    def test_low_priority_violated(self):
        constraints = [MockConstraint(f"c{i}", weight=float(i)) for i in range(1, 5)]
        # c1 is lowest weight → not in top 25%
        report = MockConformanceReport(
            constraint_violations=[MockViolation(constraint_id="c1")]
        )
        assert self.scorer.compute_priority_adherence(report, constraints) == 1.0

    def test_empty_constraints(self):
        report = MockConformanceReport()
        assert self.scorer.compute_priority_adherence(report, []) == 1.0

    def test_single_constraint_violated(self):
        constraints = [MockConstraint("c1", weight=5.0)]
        report = MockConformanceReport(
            constraint_violations=[MockViolation(constraint_id="c1")]
        )
        assert self.scorer.compute_priority_adherence(report, constraints) == 0.0

    def test_custom_top_fraction(self):
        config = RubricScoringConfig(priority_top_fraction=0.5)
        scorer = RubricScorer(config)
        constraints = [MockConstraint(f"c{i}", weight=float(i)) for i in range(1, 5)]
        # Top 50% = c3, c4. Violate c3.
        report = MockConformanceReport(
            constraint_violations=[MockViolation(constraint_id="c3")]
        )
        assert scorer.compute_priority_adherence(report, constraints) == 0.5


# --- TestTierAnalysis ---

class TestTierAnalysis:
    """Tests for tier analysis (per-tier scores, violations, breakdown)."""

    def setup_method(self):
        self.scorer = RubricScorer()

    def test_no_violations_all_tiers_perfect(self):
        constraints = [
            MockConstraint("c1", evidence_level="1A", recommendation_class="I"),
            MockConstraint("c2", evidence_level="2C", recommendation_class="III"),
        ]
        report = MockConformanceReport()
        tier_scores, violations, breakdown = self.scorer._compute_tier_analysis(report, constraints)
        assert tier_scores["critical"] == 1.0
        assert tier_scores["discretionary"] == 1.0
        assert len(violations) == 0

    def test_critical_tier_violated(self):
        constraints = [
            MockConstraint("c1", evidence_level="1A", recommendation_class="I"),
            MockConstraint("c2", evidence_level="1A", recommendation_class="I"),
        ]
        report = MockConformanceReport(
            constraint_violations=[MockViolation(constraint_id="c1")]
        )
        tier_scores, violations, breakdown = self.scorer._compute_tier_analysis(report, constraints)
        assert tier_scores["critical"] == 0.5
        assert breakdown["critical"] == 2
        assert any(v.tier == EvidenceTier.CRITICAL for v in violations)

    def test_tier_breakdown_counts(self):
        constraints = [
            MockConstraint("c1", evidence_level="A", recommendation_class="I"),  # critical
            MockConstraint("c2", evidence_level="B", recommendation_class="I"),  # strong
            MockConstraint("c3", evidence_level="B", recommendation_class="IIa"),  # moderate
            MockConstraint("c4", evidence_level="2C", recommendation_class="III"),  # discretionary
        ]
        report = MockConformanceReport()
        _, _, breakdown = self.scorer._compute_tier_analysis(report, constraints)
        assert breakdown["critical"] == 1
        assert breakdown["strong"] == 1
        assert breakdown["moderate"] == 1
        assert breakdown["discretionary"] == 1

    def test_empty_tier_score_is_one(self):
        constraints = [
            MockConstraint("c1", evidence_level="1A", recommendation_class="I"),  # critical
        ]
        report = MockConformanceReport()
        tier_scores, _, _ = self.scorer._compute_tier_analysis(report, constraints)
        # Strong tier has no constraints → 1.0
        assert tier_scores["strong"] == 1.0

    def test_violation_weight_tracking(self):
        constraints = [
            MockConstraint("c1", weight=3.0, evidence_level="1A", recommendation_class="I"),
        ]
        report = MockConformanceReport(
            constraint_violations=[MockViolation(constraint_id="c1", weight=3.0)]
        )
        _, violations, _ = self.scorer._compute_tier_analysis(report, constraints)
        assert violations[0].total_weight == 3.0


# --- TestWeightedComposite ---

class TestWeightedComposite:
    """Tests for weighted composite score computation."""

    def setup_method(self):
        self.scorer = RubricScorer()

    def test_perfect_scores_composite_one(self):
        dim_scores = {d.value: 1.0 for d in RubricDimension}
        tier_scores = {t.value: 1.0 for t in EvidenceTier}
        weights = _DEFAULT_DOMAIN_WEIGHTS["general"]
        composite = self.scorer._compute_weighted_composite(dim_scores, tier_scores, weights)
        assert abs(composite - 1.0) < 1e-9

    def test_zero_scores_composite_zero(self):
        dim_scores = {d.value: 0.0 for d in RubricDimension}
        tier_scores = {t.value: 1.0 for t in EvidenceTier}
        weights = _DEFAULT_DOMAIN_WEIGHTS["general"]
        composite = self.scorer._compute_weighted_composite(dim_scores, tier_scores, weights)
        assert composite == 0.0

    def test_tier_penalty_reduces_composite(self):
        dim_scores = {d.value: 1.0 for d in RubricDimension}
        tier_scores_perfect = {t.value: 1.0 for t in EvidenceTier}
        tier_scores_poor = {t.value: 0.0 for t in EvidenceTier}
        weights = _DEFAULT_DOMAIN_WEIGHTS["general"]
        perfect = self.scorer._compute_weighted_composite(dim_scores, tier_scores_perfect, weights)
        poor = self.scorer._compute_weighted_composite(dim_scores, tier_scores_poor, weights)
        assert poor < perfect

    def test_disabled_evidence_tiers_no_penalty(self):
        config = RubricScoringConfig(enable_evidence_tiers=False)
        scorer = RubricScorer(config)
        dim_scores = {d.value: 0.8 for d in RubricDimension}
        tier_scores = {t.value: 0.0 for t in EvidenceTier}  # Would penalize if enabled
        weights = _DEFAULT_DOMAIN_WEIGHTS["general"]
        composite = scorer._compute_weighted_composite(dim_scores, tier_scores, weights)
        assert abs(composite - 0.8) < 1e-9


# --- TestRubricReport ---

class TestRubricReport:
    """Tests for full score() → RubricReport generation."""

    def setup_method(self):
        self.scorer = RubricScorer()

    def test_basic_report_generation(self):
        report = MockConformanceReport(
            sub_scores=MockSubScores(completeness=0.9, ordering=0.8, timeliness=0.7, safety=1.0)
        )
        constraints = [
            MockConstraint("c1", weight=2.0, evidence_level="1A", recommendation_class="I"),
        ]
        result = self.scorer.score(report, constraints, domain="sepsis")
        assert isinstance(result, RubricReport)
        assert result.domain == "sepsis"
        assert result.base_report is report
        assert result.rubric_score.domain == "sepsis"

    def test_evidence_coverage(self):
        constraints = [
            MockConstraint("c1", evidence_level="1A"),
            MockConstraint("c2", evidence_level=None),
            MockConstraint("c3", evidence_level="B"),
        ]
        report = MockConformanceReport()
        result = self.scorer.score(report, constraints)
        assert abs(result.evidence_coverage - 2.0 / 3.0) < 1e-9

    def test_recommendation_coverage(self):
        constraints = [
            MockConstraint("c1", recommendation_class="I"),
            MockConstraint("c2"),
        ]
        report = MockConformanceReport()
        result = self.scorer.score(report, constraints)
        assert abs(result.recommendation_coverage - 0.5) < 1e-9

    def test_dimension_weights_match_domain(self):
        report = MockConformanceReport(sub_scores=MockSubScores())
        result = self.scorer.score(report, [], domain="stroke")
        assert result.dimension_weights_used == _DEFAULT_DOMAIN_WEIGHTS["stroke"]

    def test_composite_score_bounded(self):
        report = MockConformanceReport(sub_scores=MockSubScores())
        constraints = [
            MockConstraint("c1", weight=1.0, evidence_level="1A", recommendation_class="I"),
        ]
        result = self.scorer.score(report, constraints)
        assert 0.0 <= result.rubric_score.weighted_composite <= 1.0

    def test_no_constraints_perfect_score(self):
        report = MockConformanceReport(sub_scores=MockSubScores())
        result = self.scorer.score(report, [])
        assert result.rubric_score.weighted_composite == 1.0

    def test_all_violated_low_composite(self):
        constraints = [
            MockConstraint("c1", weight=2.0, evidence_level="1A", recommendation_class="I"),
            MockConstraint("c2", weight=2.0, evidence_level="A", recommendation_class="I"),
        ]
        report = MockConformanceReport(
            sub_scores=MockSubScores(completeness=0.3, ordering=0.3, timeliness=0.3, safety=0.3),
            constraint_violations=[
                MockViolation(constraint_id="c1"),
                MockViolation(constraint_id="c2"),
            ],
        )
        result = self.scorer.score(report, constraints)
        assert result.rubric_score.weighted_composite < 0.3


# --- TestEvidenceAdherence ---

class TestEvidenceAdherence:
    """Tests for _compute_evidence_adherence."""

    def setup_method(self):
        self.scorer = RubricScorer()

    def test_all_satisfied(self):
        constraints = [
            MockConstraint("c1", evidence_level="1A", recommendation_class="I"),
            MockConstraint("c2", evidence_level="2C", recommendation_class="III"),
        ]
        report = MockConformanceReport()
        score = self.scorer._compute_evidence_adherence(report, constraints)
        assert score == 1.0

    def test_critical_violated_more_impact(self):
        constraints = [
            MockConstraint("c1", evidence_level="1A", recommendation_class="I"),  # critical
            MockConstraint("c2", evidence_level="2C", recommendation_class="III"),  # discretionary
        ]
        report_crit = MockConformanceReport(
            constraint_violations=[MockViolation(constraint_id="c1")]
        )
        report_disc = MockConformanceReport(
            constraint_violations=[MockViolation(constraint_id="c2")]
        )
        score_crit = self.scorer._compute_evidence_adherence(report_crit, constraints)
        score_disc = self.scorer._compute_evidence_adherence(report_disc, constraints)
        # Violating critical hurts more than violating discretionary
        assert score_crit < score_disc

    def test_empty_constraints(self):
        report = MockConformanceReport()
        assert self.scorer._compute_evidence_adherence(report, []) == 1.0
