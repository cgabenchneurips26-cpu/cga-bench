from __future__ import annotations

from typing import cast

from cga_bench.semantic_layer.evidence.extended_schema import (
    ExtendedEvidenceRecord,
    StatisticalTestResult,
    cohens_kappa,
    compute_overconfidence_rate,
    paired_proportion_test,
    validate_extended_record,
)
from cga_bench.semantic_layer.evidence.hitl_feedback import (
    ClinicalFeedback,
    FeedbackAction,
    FeedbackImpactMetrics,
    FeedbackSession,
    HITLFeedbackConfig,
    compute_feedback_impact,
    validate_feedback,
)


def _valid_feedback() -> ClinicalFeedback:
    return {
        "episode_id": "ep-1",
        "action_id": "give_aspirin_loading",
        "feedback_action": FeedbackAction.REJECT.value,
        "rationale": "contraindicated in this patient state",
        "suggested_alternative": "order_ecg_12_lead",
        "reviewer_id": "clinician-01",
        "timestamp_minutes": 12.0,
    }


def _valid_extended_record() -> ExtendedEvidenceRecord:
    return {
        "action_id": "order_lab_lactate",
        "guideline_id": "ssc_2021",
        "clause_id": "LACTATE_ORDER",
        "quote_span": {"start": 10, "end": 24, "text": "measure lactate", "hash": "abc123"},
        "quote_hash": "abc123",
        "confidence": 0.92,
        "retrieval": {
            "method": "hybrid",
            "top_k": 5,
            "passage_ids": ["p1", "p2"],
            "retrieval_score": 0.88,
            "latency_ms": 15.3,
        },
        "uncertainty": {"entropy": 0.12, "calibrated": True},
    }


class TestClinicalFeedbackValidation:
    def test_valid_feedback_passes(self):
        errors = validate_feedback(_valid_feedback(), HITLFeedbackConfig.default())
        assert errors == []

    def test_missing_required_field_fails(self):
        feedback = dict(_valid_feedback())
        _ = feedback.pop("action_id")
        errors = validate_feedback(
            cast(ClinicalFeedback, cast(object, feedback)),
            HITLFeedbackConfig.default(),
        )
        assert any(err.startswith("missing_fields:") for err in errors)

    def test_rationale_required(self):
        feedback = _valid_feedback()
        feedback["rationale"] = ""
        errors = validate_feedback(feedback, HITLFeedbackConfig(require_rationale=True))
        assert "rationale:required" in errors

    def test_modify_not_allowed(self):
        feedback = _valid_feedback()
        feedback["feedback_action"] = FeedbackAction.MODIFY.value
        errors = validate_feedback(feedback, HITLFeedbackConfig(allow_modify=False))
        assert "feedback_action:modify_not_allowed" in errors


class TestFeedbackSession:
    def test_add_and_track_accept_reject_modify(self):
        session = FeedbackSession(episode_id="ep-1")

        reject_feedback = _valid_feedback()
        assert session.add_feedback(reject_feedback) == []

        accept_feedback = _valid_feedback()
        accept_feedback["action_id"] = "order_blood_culture"
        accept_feedback["feedback_action"] = FeedbackAction.ACCEPT.value
        assert session.add_feedback(accept_feedback) == []

        modify_feedback = _valid_feedback()
        modify_feedback["action_id"] = "give_nitroglycerin"
        modify_feedback["feedback_action"] = FeedbackAction.MODIFY.value
        modify_feedback["suggested_alternative"] = "give_fentanyl"
        assert session.add_feedback(modify_feedback) == []

        assert session.get_rejected_actions() == ["give_aspirin_loading"]
        assert session.get_accepted_actions() == ["order_blood_culture"]
        assert session.get_modified_actions() == [("give_nitroglycerin", "give_fentanyl")]

    def test_episode_mismatch_rejected(self):
        session = FeedbackSession(episode_id="ep-1")
        feedback = _valid_feedback()
        feedback["episode_id"] = "ep-2"
        errors = session.add_feedback(feedback)
        assert "episode_id:mismatch" in errors
        assert len(session.feedbacks) == 0

    def test_max_feedback_per_episode(self):
        session = FeedbackSession(
            episode_id="ep-1",
            config=HITLFeedbackConfig(max_feedback_per_episode=1),
        )
        assert session.add_feedback(_valid_feedback()) == []
        errors = session.add_feedback(_valid_feedback())
        assert "feedback_limit:exceeded" in errors

    def test_acceptance_and_rejection_rate(self):
        session = FeedbackSession(episode_id="ep-1")

        accept_feedback = _valid_feedback()
        accept_feedback["feedback_action"] = FeedbackAction.ACCEPT.value
        accept_feedback["action_id"] = "a1"
        _ = session.add_feedback(accept_feedback)

        reject_feedback = _valid_feedback()
        reject_feedback["feedback_action"] = FeedbackAction.REJECT.value
        reject_feedback["action_id"] = "a2"
        _ = session.add_feedback(reject_feedback)

        assert session.acceptance_rate() == 0.5
        assert session.rejection_rate() == 0.5

    def test_empty_rates(self):
        session = FeedbackSession(episode_id="ep-1")
        assert session.acceptance_rate() == 0.0
        assert session.rejection_rate() == 0.0


class TestFeedbackImpactMetrics:
    def test_application_rate_property(self):
        metrics = FeedbackImpactMetrics(total_feedbacks=4, feedbacks_applied=3)
        assert metrics.application_rate == 0.75

    def test_error_reduction_rate_property(self):
        metrics = FeedbackImpactMetrics(safety_violations_pre=5, safety_violations_post=2)
        assert metrics.error_reduction_rate == 0.6

    def test_error_reduction_zero_pre(self):
        metrics = FeedbackImpactMetrics(safety_violations_pre=0, safety_violations_post=0)
        assert metrics.error_reduction_rate == 0.0

    def test_summary_contains_rates(self):
        metrics = FeedbackImpactMetrics(
            total_feedbacks=2,
            feedbacks_applied=1,
            safety_violations_pre=4,
            safety_violations_post=2,
        )
        summary = metrics.summary()
        assert summary["application_rate"] == 0.5
        assert summary["error_reduction_rate"] == 0.5


class TestComputeFeedbackImpact:
    def test_pre_post_comparison(self):
        feedbacks = cast(
            list[ClinicalFeedback],
            [
            {
                **_valid_feedback(),
                "action_id": "give_nitroglycerin",
                "feedback_action": FeedbackAction.REJECT.value,
            },
            {
                **_valid_feedback(),
                "action_id": "order_lactate",
                "feedback_action": FeedbackAction.ACCEPT.value,
            },
            {
                **_valid_feedback(),
                "action_id": "give_ns",
                "feedback_action": FeedbackAction.MODIFY.value,
                "suggested_alternative": "give_lr",
            },
            ],
        )
        metrics = compute_feedback_impact(
            feedbacks=feedbacks,
            pre_actions=["give_nitroglycerin", "order_lactate", "give_ns"],
            post_actions=["order_lactate", "give_lr"],
            pre_violations=3,
            post_violations=1,
        )
        assert metrics.total_feedbacks == 3
        assert metrics.feedbacks_applied == 3
        assert metrics.same_error_repeated == 0
        assert metrics.error_reduction_rate == (1.0 - (1 / 3))

    def test_empty_feedbacks(self):
        metrics = compute_feedback_impact([], [], [], 0, 0)
        assert metrics.total_feedbacks == 0
        assert metrics.application_rate == 0.0

    def test_same_error_repeated_detected(self):
        feedbacks = cast(
            list[ClinicalFeedback],
            [{**_valid_feedback(), "action_id": "give_nitroglycerin"}],
        )
        metrics = compute_feedback_impact(
            feedbacks=feedbacks,
            pre_actions=["give_nitroglycerin"],
            post_actions=["give_nitroglycerin"],
            pre_violations=1,
            post_violations=1,
        )
        assert metrics.same_error_repeated == 1


class TestExtendedRecordValidation:
    def test_valid_extended_record(self):
        errors = validate_extended_record(_valid_extended_record())
        assert errors == []

    def test_invalid_retrieval_structure(self):
        record = _valid_extended_record()
        retrieval = record["retrieval"]
        retrieval_data = cast(dict[str, object], cast(object, retrieval))
        retrieval_data["method"] = "unknown"
        retrieval_data["top_k"] = 0
        retrieval_data["passage_ids"] = ["p1", 2]
        errors = validate_extended_record(record)
        assert "retrieval.method:invalid" in errors
        assert "retrieval.top_k:invalid" in errors
        assert "retrieval.passage_ids:invalid" in errors

    def test_uncertainty_required_dict(self):
        record = _valid_extended_record()
        record_data = cast(dict[str, object], cast(object, record))
        record_data["uncertainty"] = "not-a-dict"
        errors = validate_extended_record(record)
        assert "uncertainty:not_dict" in errors


class TestOverconfidenceMetric:
    def test_high_confidence_wrong_detected(self):
        value = compute_overconfidence_rate(
            confidences=[0.95, 0.91, 0.50, 0.99],
            correctness=[True, False, True, False],
            threshold=0.8,
        )
        assert value == 0.5

    def test_no_wrong_returns_zero(self):
        value = compute_overconfidence_rate(
            confidences=[0.95, 0.9],
            correctness=[True, True],
            threshold=0.8,
        )
        assert value == 0.0

    def test_length_mismatch_returns_zero(self):
        value = compute_overconfidence_rate(
            confidences=[0.9],
            correctness=[True, False],
        )
        assert value == 0.0


class TestStatsHelpers:
    def test_cohens_kappa_perfect_agreement(self):
        assert cohens_kappa([0, 1, 1, 0], [0, 1, 1, 0]) == 1.0

    def test_cohens_kappa_randomish(self):
        kappa = cohens_kappa([0, 0, 1, 1], [0, 1, 0, 1])
        assert abs(kappa) < 1e-9

    def test_paired_proportion_significant(self):
        result = paired_proportion_test(20, 100, 80, 100)
        assert isinstance(result, StatisticalTestResult)
        assert result.significant is True
        assert result.p_value < 0.05

    def test_paired_proportion_not_significant(self):
        result = paired_proportion_test(50, 100, 52, 100)
        assert result.significant is False
        assert result.p_value >= 0.05

    def test_paired_proportion_empty_totals(self):
        result = paired_proportion_test(0, 0, 0, 0)
        assert result.p_value == 1.0
        assert result.n_samples == 0
