from __future__ import annotations

import pytest

from cga_bench.semantic_layer.evidence.schema import EvidenceRecord
from cga_bench.semantic_layer.evidence.scoring_policy import (
    EvidenceScoringPolicy,
    ScoringAdjustment,
    apply_evidence_scoring,
    compute_evidence_adjusted_score,
)
from cga_bench.semantic_layer.evidence.uncertainty import (
    CalibrationConfig,
    CalibrationReport,
    UncertaintyOutput,
    apply_temperature_scaling,
    compute_brier_score,
    compute_calibration_report,
    compute_ece,
    compute_overconfidence_rate,
    validate_uncertainty_output,
)


def _record(action_id: str, clause_id: str, quote_hash: str = "hash") -> EvidenceRecord:
    return {
        "action_id": action_id,
        "guideline_id": "ssc_sepsis_2021",
        "clause_id": clause_id,
        "quote_span": {"start": 0, "end": 4, "text": "text", "hash": quote_hash},
        "quote_hash": quote_hash,
        "confidence": 0.9,
    }


class TestEvidenceScoringPolicyFactories:
    def test_default_factory_values(self):
        policy = EvidenceScoringPolicy.default()
        assert policy.verified_bonus == 0.0
        assert policy.unverified_penalty == 0.1
        assert policy.no_evidence_penalty == 0.15
        assert policy.abstain_protection == 0.05

    def test_strict_factory_values(self):
        policy = EvidenceScoringPolicy.strict()
        assert policy.verified_bonus == 0.02
        assert policy.unverified_penalty == 0.2
        assert policy.no_evidence_penalty == 0.25
        assert policy.abstain_protection == 0.1


class TestApplyEvidenceScoring:
    def test_mandatory_verified_gets_bonus(self):
        policy = EvidenceScoringPolicy(verified_bonus=0.03)
        action_scores = [{"action_id": "order_lab_lactate", "score": 0.8, "is_mandatory": True}]
        records = [_record("order_lab_lactate", "CLAUSE_1", quote_hash="valid")]

        result = apply_evidence_scoring(action_scores, records, policy)
        assert len(result) == 1
        assert abs(result[0]["adjustment"] - 0.03) < 1e-9
        assert result[0]["reason"] == "verified_evidence_bonus"

    def test_mandatory_unverified_penalty(self):
        policy = EvidenceScoringPolicy(unverified_penalty=0.12)
        action_scores = [{"action_id": "give_antibiotics", "score": 0.9, "is_mandatory": True}]
        records = [_record("give_antibiotics", "CLAUSE_X", quote_hash="")]

        result = apply_evidence_scoring(action_scores, records, policy)
        assert abs(result[0]["adjustment"] + 0.12) < 1e-9
        assert result[0]["reason"] == "unverified_evidence_penalty"

    def test_mandatory_without_evidence_gets_no_evidence_penalty(self):
        policy = EvidenceScoringPolicy(no_evidence_penalty=0.2)
        action_scores = [{"action_id": "order_blood_culture", "score": 0.7, "is_mandatory": True}]

        result = apply_evidence_scoring(action_scores, [], policy)
        assert abs(result[0]["adjustment"] + 0.2) < 1e-9
        assert result[0]["reason"] == "no_evidence_penalty"

    def test_abstain_protection_reduces_unverified_penalty(self):
        policy = EvidenceScoringPolicy(unverified_penalty=0.2, abstain_protection=0.05)
        action_scores = [
            {
                "action_id": "start_vasopressor_norepinephrine",
                "score": 0.75,
                "is_mandatory": True,
                "abstain_recommendation": True,
            }
        ]
        records = [_record("start_vasopressor_norepinephrine", "CLAUSE_2", quote_hash="")]

        result = apply_evidence_scoring(action_scores, records, policy)
        assert abs(result[0]["adjustment"] + 0.15) < 1e-9
        assert result[0]["reason"] == "unverified_evidence_penalty_with_abstain_protection"

    def test_abstain_protection_reduces_no_evidence_penalty(self):
        policy = EvidenceScoringPolicy(no_evidence_penalty=0.2, abstain_protection=0.1)
        action_scores = [
            {
                "action_id": "give_crystalloid_30ml_kg",
                "score": 0.75,
                "is_mandatory": True,
                "request_more_info": True,
            }
        ]

        result = apply_evidence_scoring(action_scores, [], policy)
        assert abs(result[0]["adjustment"] + 0.1) < 1e-9
        assert result[0]["reason"] == "no_evidence_penalty_with_abstain_protection"

    def test_non_mandatory_action_unaffected(self):
        policy = EvidenceScoringPolicy.strict()
        action_scores = [{"action_id": "order_lab_cbc", "score": 0.6, "is_mandatory": False}]

        result = apply_evidence_scoring(action_scores, [], policy)
        assert result[0]["adjustment"] == 0.0
        assert abs(result[0]["adjusted_score"] - 0.6) < 1e-9
        assert result[0]["reason"] == "non_mandatory_no_adjustment"

    def test_high_risk_actions_filter(self):
        policy = EvidenceScoringPolicy(high_risk_actions=["high_risk_a"])
        action_scores = [
            {"action_id": "high_risk_a", "score": 0.8, "is_mandatory": True},
            {"action_id": "mandatory_but_not_high_risk", "score": 0.8, "is_mandatory": True},
        ]

        result = apply_evidence_scoring(action_scores, [], policy)
        assert result[0]["adjustment"] < 0.0
        assert result[1]["adjustment"] == 0.0
        assert result[1]["reason"] == "mandatory_not_high_risk_no_adjustment"

    def test_verified_clause_ids_override_quote_hash_check(self):
        policy = EvidenceScoringPolicy(verified_bonus=0.05)
        action_scores = [{"action_id": "a", "score": 0.5, "is_mandatory": True}]
        records = [_record("a", "CLAUSE_OK", quote_hash="")]

        result = apply_evidence_scoring(
            action_scores,
            records,
            policy,
            verified_clause_ids={"CLAUSE_OK"},
        )
        assert abs(result[0]["adjustment"] - 0.05) < 1e-9


class TestComputeEvidenceAdjustedScore:
    def test_base_plus_adjustments(self):
        adjustments: list[ScoringAdjustment] = [
            {
                "action_id": "a",
                "base_score": 0.8,
                "adjustment": -0.1,
                "adjusted_score": 0.7,
                "reason": "x",
            },
            {
                "action_id": "b",
                "base_score": 0.8,
                "adjustment": 0.05,
                "adjusted_score": 0.85,
                "reason": "y",
            },
        ]
        final_score = compute_evidence_adjusted_score(0.9, adjustments)
        assert abs(final_score - 0.85) < 1e-9

    def test_clamps_to_zero(self):
        adjustments: list[ScoringAdjustment] = [
            {
                "action_id": "a",
                "base_score": 0.1,
                "adjustment": -0.8,
                "adjusted_score": 0.0,
                "reason": "penalty",
            }
        ]
        assert compute_evidence_adjusted_score(0.1, adjustments) == 0.0

    def test_clamps_to_one(self):
        adjustments: list[ScoringAdjustment] = [
            {
                "action_id": "a",
                "base_score": 0.95,
                "adjustment": 0.2,
                "adjusted_score": 1.0,
                "reason": "bonus",
            }
        ]
        assert compute_evidence_adjusted_score(0.95, adjustments) == 1.0


class TestUncertaintyValidation:
    def test_valid_uncertainty_output(self):
        output: UncertaintyOutput = {
            "diagnoses": [
                {"name": "sepsis", "probability": 0.7},
                {"name": "viral_syndrome", "probability": 0.3},
            ],
            "action_confidence": 0.8,
            "abstain_recommendation": False,
            "abstain_reason": "",
        }
        assert validate_uncertainty_output(output) == []

    def test_missing_fields_detected(self):
        output: dict[str, object] = {"diagnoses": []}
        errors = validate_uncertainty_output(output)
        assert any("missing_fields" in e for e in errors)

    def test_invalid_diagnosis_candidate_structure(self):
        output: UncertaintyOutput = {
            "diagnoses": [{"name": "", "probability": 1.2}],
            "action_confidence": 0.5,
            "abstain_recommendation": False,
            "abstain_reason": "",
        }
        errors = validate_uncertainty_output(output)
        assert any("diagnoses[0].name" in e for e in errors)
        assert any("diagnoses[0].probability:out_of_range" in e for e in errors)

    def test_abstain_requires_reason(self):
        output: UncertaintyOutput = {
            "diagnoses": [{"name": "dka", "probability": 1.0}],
            "action_confidence": 0.2,
            "abstain_recommendation": True,
            "abstain_reason": "   ",
        }
        errors = validate_uncertainty_output(output)
        assert "abstain_reason:required_when_abstaining" in errors


class TestTemperatureScaling:
    def test_temperature_one_no_change(self):
        confidences = [0.2, 0.5, 0.9]
        scaled = apply_temperature_scaling(confidences, 1.0)
        assert all(abs(s - c) < 1e-9 for s, c in zip(scaled, confidences, strict=True))

    def test_temperature_gt_one_flattens_extremes(self):
        confidences = [0.1, 0.9]
        scaled = apply_temperature_scaling(confidences, 2.0)
        assert 0.1 < scaled[0] < 0.5
        assert 0.5 < scaled[1] < 0.9

    def test_invalid_temperature_raises(self):
        with pytest.raises(ValueError):
            _ = apply_temperature_scaling([0.5], 0.0)


class TestCalibrationMetrics:
    def test_ece_perfect_calibration_zero(self):
        confidences = [1.0, 1.0, 0.0, 0.0]
        correctness = [True, True, False, False]
        assert abs(compute_ece(confidences, correctness, n_bins=2) - 0.0) < 1e-9

    def test_ece_worst_case_high(self):
        confidences = [1.0, 1.0, 1.0, 1.0]
        correctness = [False, False, False, False]
        ece = compute_ece(confidences, correctness, n_bins=4)
        assert abs(ece - 1.0) < 1e-9

    def test_brier_all_correct_zero(self):
        confidences = [1.0, 1.0, 1.0]
        correctness = [True, True, True]
        assert abs(compute_brier_score(confidences, correctness) - 0.0) < 1e-9

    def test_brier_all_wrong_one(self):
        confidences = [1.0, 1.0]
        correctness = [False, False]
        assert abs(compute_brier_score(confidences, correctness) - 1.0) < 1e-9

    def test_overconfidence_rate_detects_high_conf_wrong(self):
        confidences = [0.9, 0.95, 0.4]
        correctness = [False, True, False]
        rate = compute_overconfidence_rate(confidences, correctness, threshold=0.8)
        assert abs(rate - (1 / 3)) < 1e-9

    def test_empty_inputs_return_zero(self):
        assert compute_ece([], [], n_bins=5) == 0.0
        assert compute_brier_score([], []) == 0.0
        assert compute_overconfidence_rate([], []) == 0.0

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            _ = compute_ece([0.5], [True, False])
        with pytest.raises(ValueError):
            _ = compute_brier_score([0.5], [True, False])
        with pytest.raises(ValueError):
            _ = compute_overconfidence_rate([0.5], [True, False])


class TestCalibrationReport:
    def test_summary_contains_expected_fields(self):
        report = CalibrationReport(
            ece=0.12,
            brier_score=0.08,
            overconfidence_rate=0.2,
            n_samples=10,
            temperature=1.5,
        )
        summary = report.summary()
        assert set(summary.keys()) == {
            "ece",
            "brier_score",
            "overconfidence_rate",
            "n_samples",
            "temperature",
        }

    def test_compute_calibration_report_convenience(self):
        confidences = [0.9, 0.8, 0.2, 0.1]
        correctness = [True, True, False, False]
        config = CalibrationConfig(temperature=1.0, n_bins=4)

        report = compute_calibration_report(confidences, correctness, config)
        assert report.n_samples == 4
        assert report.temperature == 1.0
        assert report.ece >= 0.0
        assert report.brier_score >= 0.0
        assert report.overconfidence_rate >= 0.0

    def test_compute_calibration_report_empty_inputs(self):
        report = compute_calibration_report([], [], CalibrationConfig.default())
        assert report.n_samples == 0
        assert report.ece == 0.0
        assert report.brier_score == 0.0
        assert report.overconfidence_rate == 0.0

    def test_calibration_config_default(self):
        cfg = CalibrationConfig.default()
        assert cfg.temperature == 1.0
        assert cfg.n_bins == 10
