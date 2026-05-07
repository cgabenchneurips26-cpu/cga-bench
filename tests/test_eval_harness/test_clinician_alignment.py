from __future__ import annotations

import pytest

from cga_bench.eval_harness.clinician_alignment import (
    AlignmentMetrics,
    ClinicalExpertise,
    ClinicianAlignmentExperiment,
    ClinicianRating,
    EpisodeAnnotation,
    SafetyCategory,
    interpret_correlation,
    interpret_kappa,
)
from cga_bench.assessor_core.episode_risk_scorer import (
    EpisodeRiskConfig,
    EpisodeRiskResult,
    EpisodeRiskScorer,
)


def _scorer() -> EpisodeRiskScorer:
    return EpisodeRiskScorer(EpisodeRiskConfig())


def _experiment(**kwargs) -> ClinicianAlignmentExperiment:
    return ClinicianAlignmentExperiment(scorer=_scorer(), config=kwargs or None)


def _rating(
    clinician_id: str = "c1",
    episode_id: str = "ep1",
    category: SafetyCategory = SafetyCategory.SAFE,
    expertise: ClinicalExpertise = ClinicalExpertise.ATTENDING,
    confidence: float = 0.9,
    risk: float = 0.1,
) -> ClinicianRating:
    return ClinicianRating(
        clinician_id=clinician_id,
        expertise=expertise,
        episode_id=episode_id,
        safety_category=category,
        confidence=confidence,
        perceived_risk=risk,
    )


def _risk_result(episode_id: str = "ep1", r_norm: float = 0.1) -> EpisodeRiskResult:
    return EpisodeRiskResult(
        episode_id=episode_id,
        r_raw=r_norm * 5,
        r_omission=0.0,
        r_total=r_norm * 5,
        r_norm=r_norm,
        task_success=r_norm < 0.5,
        sas=1.0 - r_norm,
        total_actions=10,
        total_violations=int(r_norm * 10),
        violations_by_type={},
        action_violations=[],
        missing_critical_actions=[],
        peak_risk=r_norm,
        aggregate_risk=r_norm * 5,
        episode_duration_minutes=60.0,
    )


_EXPERTISE_WEIGHTS = {
    ClinicalExpertise.ATTENDING: 1.0,
    ClinicalExpertise.FELLOW: 0.8,
    ClinicalExpertise.RESIDENT: 0.6,
    ClinicalExpertise.NURSE_PRACTITIONER: 0.7,
    ClinicalExpertise.PHARMACIST: 0.7,
}


class TestEpisodeAnnotation:
    def test_compute_consensus_majority(self):
        ann = EpisodeAnnotation(
            episode_id="ep1",
            ratings=[
                _rating("c1", category=SafetyCategory.SAFE),
                _rating("c2", category=SafetyCategory.SAFE),
                _rating("c3", category=SafetyCategory.UNSAFE),
            ],
        )
        ann.compute_consensus(_EXPERTISE_WEIGHTS)
        assert ann.consensus_category == SafetyCategory.SAFE
        assert ann.agreement_level == pytest.approx(2 / 3)

    def test_compute_consensus_unanimous(self):
        ann = EpisodeAnnotation(
            episode_id="ep1",
            ratings=[
                _rating("c1", category=SafetyCategory.UNSAFE, risk=0.9),
                _rating("c2", category=SafetyCategory.UNSAFE, risk=0.8),
            ],
        )
        ann.compute_consensus(_EXPERTISE_WEIGHTS)
        assert ann.consensus_category == SafetyCategory.UNSAFE
        assert ann.agreement_level == 1.0

    def test_compute_consensus_expertise_weights_matter(self):
        ann = EpisodeAnnotation(
            episode_id="ep1",
            ratings=[
                _rating("c1", category=SafetyCategory.UNSAFE, expertise=ClinicalExpertise.ATTENDING, confidence=1.0),
                _rating("c2", category=SafetyCategory.SAFE, expertise=ClinicalExpertise.RESIDENT, confidence=0.5),
                _rating("c3", category=SafetyCategory.SAFE, expertise=ClinicalExpertise.RESIDENT, confidence=0.5),
            ],
        )
        ann.compute_consensus(_EXPERTISE_WEIGHTS)
        assert ann.consensus_category == SafetyCategory.UNSAFE

    def test_compute_consensus_empty_ratings(self):
        ann = EpisodeAnnotation(episode_id="ep1", ratings=[])
        ann.compute_consensus(_EXPERTISE_WEIGHTS)
        assert ann.consensus_category is None

    def test_compute_consensus_requires_weights(self):
        ann = EpisodeAnnotation(
            episode_id="ep1",
            ratings=[_rating()],
        )
        with pytest.raises(ValueError, match="expertise_weights is required"):
            ann.compute_consensus(None)

    def test_mean_perceived_risk(self):
        ann = EpisodeAnnotation(
            episode_id="ep1",
            ratings=[
                _rating("c1", risk=0.2),
                _rating("c2", risk=0.4),
                _rating("c3", risk=0.6),
            ],
        )
        ann.compute_consensus(_EXPERTISE_WEIGHTS)
        assert ann.mean_perceived_risk == pytest.approx(0.4)


class TestClassifyEpisode:
    def test_low_risk_is_safe(self):
        exp = _experiment(safe_threshold=0.2, unsafe_threshold=0.6)
        result = _risk_result(r_norm=0.1)
        assert exp.classify_episode(result) == SafetyCategory.SAFE

    def test_high_risk_is_unsafe(self):
        exp = _experiment(safe_threshold=0.2, unsafe_threshold=0.6)
        result = _risk_result(r_norm=0.8)
        assert exp.classify_episode(result) == SafetyCategory.UNSAFE

    def test_medium_risk_is_marginal(self):
        exp = _experiment(safe_threshold=0.2, unsafe_threshold=0.6)
        result = _risk_result(r_norm=0.4)
        assert exp.classify_episode(result) == SafetyCategory.MARGINAL


class TestCohensKappa:
    def test_perfect_agreement(self):
        exp = _experiment()
        pred = [SafetyCategory.SAFE, SafetyCategory.UNSAFE, SafetyCategory.MARGINAL]
        gold = [SafetyCategory.SAFE, SafetyCategory.UNSAFE, SafetyCategory.MARGINAL]
        kappa = exp._compute_cohens_kappa(pred, gold)
        assert kappa == pytest.approx(1.0)

    def test_no_agreement_beyond_chance(self):
        exp = _experiment()
        pred = [SafetyCategory.SAFE, SafetyCategory.SAFE, SafetyCategory.SAFE]
        gold = [SafetyCategory.UNSAFE, SafetyCategory.UNSAFE, SafetyCategory.UNSAFE]
        kappa = exp._compute_cohens_kappa(pred, gold)
        assert kappa <= 0.0

    def test_empty_lists(self):
        exp = _experiment()
        assert exp._compute_cohens_kappa([], []) == 0.0


class TestFleissKappa:
    def test_perfect_agreement_all_same(self):
        exp = _experiment()
        annotations = [
            EpisodeAnnotation(
                episode_id=f"ep{i}",
                ratings=[
                    _rating(f"c{j}", f"ep{i}", SafetyCategory.SAFE)
                    for j in range(3)
                ],
            )
            for i in range(5)
        ]
        kappa = exp._compute_fleiss_kappa(annotations)
        assert kappa == pytest.approx(1.0) or kappa > 0.9

    def test_empty_annotations(self):
        exp = _experiment()
        assert exp._compute_fleiss_kappa([]) == 0.0


class TestCorrelationMetrics:
    def test_perfect_positive_correlation(self):
        exp = _experiment()
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 20.0, 30.0, 40.0, 50.0]
        assert exp._compute_pearson(x, y) == pytest.approx(1.0)

    def test_perfect_negative_correlation(self):
        exp = _experiment()
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [50.0, 40.0, 30.0, 20.0, 10.0]
        assert exp._compute_pearson(x, y) == pytest.approx(-1.0)

    def test_zero_variance_returns_zero(self):
        exp = _experiment()
        x = [1.0, 1.0, 1.0]
        y = [2.0, 3.0, 4.0]
        assert exp._compute_pearson(x, y) == 0.0

    def test_single_element_returns_zero(self):
        exp = _experiment()
        assert exp._compute_pearson([1.0], [2.0]) == 0.0

    def test_spearman_rank_correlation(self):
        exp = _experiment()
        x = [1.0, 2.0, 3.0, 4.0]
        y = [10.0, 20.0, 30.0, 40.0]
        rho = exp._compute_rank_correlation(x, y)
        assert rho == pytest.approx(1.0)

    def test_kendall_tau_concordant(self):
        exp = _experiment()
        x = [1.0, 2.0, 3.0, 4.0]
        y = [1.0, 2.0, 3.0, 4.0]
        tau = exp._compute_kendall_tau(x, y)
        assert tau == pytest.approx(1.0)

    def test_kendall_tau_discordant(self):
        exp = _experiment()
        x = [1.0, 2.0, 3.0, 4.0]
        y = [4.0, 3.0, 2.0, 1.0]
        tau = exp._compute_kendall_tau(x, y)
        assert tau == pytest.approx(-1.0)


class TestPrecisionRecall:
    def test_perfect_precision_recall(self):
        exp = _experiment()
        pred = [SafetyCategory.SAFE, SafetyCategory.UNSAFE]
        gold = [SafetyCategory.SAFE, SafetyCategory.UNSAFE]
        p, r = exp._compute_precision_recall(pred, gold, SafetyCategory.SAFE)
        assert p == 1.0
        assert r == 1.0

    def test_zero_precision(self):
        exp = _experiment()
        pred = [SafetyCategory.SAFE, SafetyCategory.SAFE]
        gold = [SafetyCategory.UNSAFE, SafetyCategory.UNSAFE]
        p, r = exp._compute_precision_recall(pred, gold, SafetyCategory.SAFE)
        assert p == 0.0


class TestInterpretFunctions:
    def test_interpret_kappa_ranges(self):
        assert "Poor" in interpret_kappa(-0.1)
        assert "Slight" in interpret_kappa(0.1)
        assert "Fair" in interpret_kappa(0.3)
        assert "Moderate" in interpret_kappa(0.5)
        assert "Substantial" in interpret_kappa(0.7)
        assert "perfect" in interpret_kappa(0.9).lower()

    def test_interpret_correlation_ranges(self):
        assert "Negligible" in interpret_correlation(0.05)
        assert "Weak" in interpret_correlation(0.2)
        assert "Moderate" in interpret_correlation(0.4)
        assert "Strong" in interpret_correlation(0.6)
        assert "Very strong" in interpret_correlation(0.8)
