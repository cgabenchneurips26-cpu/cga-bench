"""
Tests for LLM-as-Judge Error Severity Assessment.

Uses mock LLM responses to verify structured CoT reasoning,
severity judgment, and causal relationship detection.
"""
from __future__ import annotations

from typing import List, Optional

import pytest

from cga_bench.cpg_model.schemas.base import (
    HarmSeverity, RecommendationClass, ViolationEvent, ViolationType,
)
from cga_bench.semantic_layer.conformance.llm_severity_judge import (
    CausalRelationship, JudgedViolation, JudgmentResult,
    LLMJudgeConfig, LLMSeverityJudge,
)


# --- Fixtures ---

def _make_violation(
    violation_id: str = "v1",
    violation_type: ViolationType = ViolationType.OMISSION,
    timestamp: float = 5.0,
    action_involved: Optional[str] = None,
    expected_action: Optional[str] = None,
    severity: HarmSeverity = HarmSeverity.MAJOR,
    description: str = "Test violation",
    guideline_ref: str = "Test Guideline",
    node: str = "node1",
) -> ViolationEvent:
    return ViolationEvent(
        violation_id=violation_id,
        violation_type=violation_type,
        timestamp_minutes=timestamp,
        action_involved=action_involved,
        expected_action=expected_action,
        state_at_violation="state1",
        node_at_violation=node,
        harm_severity=severity,
        guideline_class=RecommendationClass.CLASS_I,
        preventability=1.0,
        description=description,
        guideline_reference=guideline_ref,
    )


def _mock_assessment_response(
    violation_id: str,
    severity: str = "major",
    reasoning: str = "Clinical reasoning...",
    confidence: float = 0.85,
) -> dict:
    return {
        "assessments": [{
            "violation_id": violation_id,
            "severity": severity,
            "reasoning": reasoning,
            "causal_factors": ["factor1"],
            "clinical_significance": "Significant clinical impact",
            "confidence": confidence,
        }],
        "overall_assessment": "Test overall assessment",
    }


def _mock_multi_assessment_response(violations: list) -> dict:
    return {
        "assessments": [
            {
                "violation_id": v["id"],
                "severity": v.get("severity", "major"),
                "reasoning": v.get("reasoning", "Clinical reasoning"),
                "causal_factors": v.get("factors", []),
                "clinical_significance": "Impact noted",
                "confidence": v.get("confidence", 0.8),
            }
            for v in violations
        ],
        "overall_assessment": "Multiple violations assessed",
    }


def _mock_causal_response(relationships: list) -> dict:
    return {
        "relationships": [
            {
                "cause_id": r["cause"],
                "effect_id": r["effect"],
                "type": r.get("type", "contributing_factor"),
                "explanation": r.get("explanation", "Causal explanation"),
                "confidence": r.get("confidence", 0.75),
            }
            for r in relationships
        ]
    }


# =====================================================
# TEST CATEGORY 1: Basic Functionality
# =====================================================

class TestBasicJudgment:
    """Basic LLM-as-Judge functionality tests"""

    def test_empty_violations_returns_empty_result(self):
        """No violations produces empty judgment result"""
        config = LLMJudgeConfig(backend="mock", mock_responses=[])
        judge = LLMSeverityJudge(config)
        result = judge.judge_violations([])

        assert result.judged_violations == []
        assert result.causal_relationships == []
        assert result.total_llm_tokens_used == 0

    def test_single_violation_judged(self):
        """Single violation is assessed with CoT reasoning"""
        mock_resp = _mock_assessment_response("v1", "severe", "The omission of antibiotics...")
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[mock_resp],
            enable_causal_analysis=False,
        )
        judge = LLMSeverityJudge(config)
        violations = [_make_violation("v1", severity=HarmSeverity.MAJOR)]

        result = judge.judge_violations(violations)

        assert len(result.judged_violations) == 1
        judged = result.judged_violations[0]
        assert judged.violation_id == "v1"
        assert judged.original_severity == HarmSeverity.MAJOR
        assert judged.judged_severity == HarmSeverity.SEVERE
        assert judged.severity_changed is True
        assert judged.confidence == 0.85
        assert "antibiotics" in judged.cot_reasoning

    def test_severity_unchanged_when_same(self):
        """When LLM agrees with original severity, severity_changed=False"""
        mock_resp = _mock_assessment_response("v1", "major", "Confirms major severity")
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[mock_resp],
            enable_causal_analysis=False,
        )
        judge = LLMSeverityJudge(config)
        violations = [_make_violation("v1", severity=HarmSeverity.MAJOR)]

        result = judge.judge_violations(violations)
        assert result.judged_violations[0].severity_changed is False

    def test_multiple_violations_judged(self):
        """Multiple violations are all assessed"""
        mock_resp = _mock_multi_assessment_response([
            {"id": "v1", "severity": "severe", "reasoning": "First violation"},
            {"id": "v2", "severity": "moderate", "reasoning": "Second violation"},
            {"id": "v3", "severity": "catastrophic", "reasoning": "Third violation"},
        ])
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[mock_resp],
            enable_causal_analysis=False,
        )
        judge = LLMSeverityJudge(config)
        violations = [
            _make_violation("v1"),
            _make_violation("v2"),
            _make_violation("v3"),
        ]

        result = judge.judge_violations(violations)
        assert len(result.judged_violations) == 3
        severities = {j.violation_id: j.judged_severity for j in result.judged_violations}
        assert severities["v1"] == HarmSeverity.SEVERE
        assert severities["v2"] == HarmSeverity.MODERATE
        assert severities["v3"] == HarmSeverity.CATASTROPHIC

    def test_patient_context_passed_to_prompt(self):
        """Patient context is included in the assessment"""
        mock_resp = _mock_assessment_response("v1", "severe", "Given the patient's condition...")
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[mock_resp],
            enable_causal_analysis=False,
        )
        judge = LLMSeverityJudge(config)
        violations = [_make_violation("v1")]

        result = judge.judge_violations(
            violations,
            patient_context="65yo male with acute MI and RV involvement",
        )
        assert len(result.judged_violations) == 1


# =====================================================
# TEST CATEGORY 2: Causal Analysis
# =====================================================

class TestCausalAnalysis:
    """Causal relationship detection tests"""

    def test_causal_relationships_detected(self):
        """LLM identifies causal relationships between violations"""
        assessment_resp = _mock_multi_assessment_response([
            {"id": "v1", "severity": "major"},
            {"id": "v2", "severity": "severe"},
        ])
        causal_resp = _mock_causal_response([
            {
                "cause": "v1",
                "effect": "v2",
                "type": "direct_cause",
                "explanation": "Omitting blood culture led to wrong antibiotic choice",
                "confidence": 0.9,
            }
        ])
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[assessment_resp, causal_resp],
            enable_causal_analysis=True,
        )
        judge = LLMSeverityJudge(config)
        violations = [_make_violation("v1"), _make_violation("v2")]

        result = judge.judge_violations(violations)
        assert len(result.causal_relationships) == 1
        rel = result.causal_relationships[0]
        assert rel.cause_violation_id == "v1"
        assert rel.effect_violation_id == "v2"
        assert rel.relationship_type == "direct_cause"
        assert rel.confidence == 0.9

    def test_causal_analysis_disabled(self):
        """When disabled, no causal analysis is performed"""
        mock_resp = _mock_multi_assessment_response([
            {"id": "v1", "severity": "major"},
            {"id": "v2", "severity": "major"},
        ])
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[mock_resp],
            enable_causal_analysis=False,
        )
        judge = LLMSeverityJudge(config)
        violations = [_make_violation("v1"), _make_violation("v2")]

        result = judge.judge_violations(violations)
        assert result.causal_relationships == []

    def test_causal_self_reference_filtered(self):
        """Self-referencing causal relationships are filtered out"""
        assessment_resp = _mock_multi_assessment_response([
            {"id": "v1", "severity": "major"},
        ])
        causal_resp = _mock_causal_response([
            {"cause": "v1", "effect": "v1", "type": "direct_cause"},
        ])
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[assessment_resp, causal_resp],
            enable_causal_analysis=True,
        )
        judge = LLMSeverityJudge(config)
        violations = [_make_violation("v1")]

        result = judge.judge_violations(violations)
        # Single violation + self-reference filtered = no relationships
        assert result.causal_relationships == []

    def test_causal_invalid_ids_filtered(self):
        """References to non-existent violations are filtered out"""
        assessment_resp = _mock_multi_assessment_response([
            {"id": "v1", "severity": "major"},
            {"id": "v2", "severity": "major"},
        ])
        causal_resp = _mock_causal_response([
            {"cause": "v1", "effect": "v_nonexistent", "type": "cascade"},
        ])
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[assessment_resp, causal_resp],
            enable_causal_analysis=True,
        )
        judge = LLMSeverityJudge(config)
        violations = [_make_violation("v1"), _make_violation("v2")]

        result = judge.judge_violations(violations)
        assert result.causal_relationships == []


# =====================================================
# TEST CATEGORY 3: Error Handling & Robustness
# =====================================================

class TestRobustness:
    """Error handling and edge cases"""

    def test_llm_returns_invalid_json(self):
        """Invalid JSON from LLM is handled gracefully"""
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=["not valid json at all {{{"],
            enable_causal_analysis=False,
        )
        judge = LLMSeverityJudge(config)
        violations = [_make_violation("v1")]

        result = judge.judge_violations(violations)
        # Should fall back to original severity
        assert len(result.judged_violations) == 1
        assert result.judged_violations[0].judged_severity == HarmSeverity.MAJOR
        assert result.judged_violations[0].confidence == 0.0

    def test_missing_violation_in_response(self):
        """Violations not in LLM response get default judgment"""
        mock_resp = _mock_assessment_response("v1", "severe", "Only v1 assessed")
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[mock_resp],
            enable_causal_analysis=False,
        )
        judge = LLMSeverityJudge(config)
        violations = [
            _make_violation("v1", severity=HarmSeverity.MAJOR),
            _make_violation("v2", severity=HarmSeverity.MODERATE),
        ]

        result = judge.judge_violations(violations)
        assert len(result.judged_violations) == 2
        v2_judged = next(j for j in result.judged_violations if j.violation_id == "v2")
        assert v2_judged.judged_severity == HarmSeverity.MODERATE  # original
        assert v2_judged.confidence == 0.0

    def test_no_provider_graceful_fallback(self):
        """When LLM provider fails to init, falls back gracefully"""
        config = LLMJudgeConfig(
            backend="nonexistent_backend",
            enable_causal_analysis=False,
        )
        judge = LLMSeverityJudge(config)
        violations = [_make_violation("v1")]

        result = judge.judge_violations(violations)
        assert len(result.judged_violations) == 1
        assert result.judged_violations[0].confidence == 0.0

    def test_empty_assessment_response(self):
        """Empty assessments list in response is handled"""
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[{"assessments": [], "overall_assessment": ""}],
            enable_causal_analysis=False,
        )
        judge = LLMSeverityJudge(config)
        violations = [_make_violation("v1")]

        result = judge.judge_violations(violations)
        assert len(result.judged_violations) == 1
        assert result.judged_violations[0].confidence == 0.0


# =====================================================
# TEST CATEGORY 4: Clinical Scenarios
# =====================================================

class TestClinicalScenarios:
    """Clinically meaningful LLM judgment scenarios"""

    def test_rv_trap_severity_upgrade(self):
        """RV infarct + nitrates: LLM upgrades to catastrophic"""
        mock_resp = {
            "assessments": [{
                "violation_id": "v_nitrate",
                "severity": "catastrophic",
                "reasoning": (
                    "Step 1: Patient has inferior MI with RV involvement. "
                    "Step 2: Nitroglycerin reduces preload. "
                    "Step 3: RV-dependent circulation cannot compensate. "
                    "Step 4: Risk of cardiogenic shock and death."
                ),
                "causal_factors": [
                    "RV dependence on preload",
                    "Nitrate-induced vasodilation",
                    "Hemodynamic collapse risk",
                ],
                "clinical_significance": "Potentially fatal hemodynamic compromise",
                "confidence": 0.95,
            }],
            "overall_assessment": "Critical safety violation in RV infarct management",
        }
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[mock_resp],
            enable_causal_analysis=False,
        )
        judge = LLMSeverityJudge(config)
        violations = [
            _make_violation(
                "v_nitrate",
                violation_type=ViolationType.COMMISSION,
                action_involved="give_nitroglycerin",
                severity=HarmSeverity.SEVERE,
                description="Administered nitroglycerin to RV infarct patient",
            ),
        ]

        result = judge.judge_violations(
            violations,
            patient_context="65yo male with inferior STEMI, V4R ST elevation indicating RV involvement",
        )
        judged = result.judged_violations[0]
        assert judged.judged_severity == HarmSeverity.CATASTROPHIC
        assert judged.severity_changed is True
        assert judged.confidence == 0.95
        assert "RV" in judged.cot_reasoning or "preload" in judged.cot_reasoning

    def test_sepsis_bundle_cascade(self):
        """Sepsis hour-1 bundle: LLM identifies cascade pattern"""
        assessment_resp = _mock_multi_assessment_response([
            {"id": "v_culture", "severity": "major", "reasoning": "Delayed blood culture"},
            {"id": "v_abx", "severity": "severe", "reasoning": "Late antibiotics"},
            {"id": "v_fluid", "severity": "major", "reasoning": "Inadequate resuscitation"},
        ])
        causal_resp = _mock_causal_response([
            {"cause": "v_culture", "effect": "v_abx", "type": "direct_cause",
             "explanation": "Culture delay led to antibiotic delay", "confidence": 0.85},
            {"cause": "v_abx", "effect": "v_fluid", "type": "cascade",
             "explanation": "Without antibiotics, patient deteriorated requiring more fluid",
             "confidence": 0.7},
        ])
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[assessment_resp, causal_resp],
            enable_causal_analysis=True,
        )
        judge = LLMSeverityJudge(config)
        violations = [
            _make_violation("v_culture", expected_action="order_blood_culture"),
            _make_violation("v_abx", expected_action="give_broad_spectrum_antibiotics"),
            _make_violation("v_fluid", expected_action="give_crystalloid_30ml_kg"),
        ]

        result = judge.judge_violations(violations)
        assert len(result.causal_relationships) == 2
        # Chain: culture -> abx -> fluid
        causes = {r.cause_violation_id for r in result.causal_relationships}
        assert "v_culture" in causes
        assert "v_abx" in causes


# =====================================================
# TEST CATEGORY 5: Data Model Validation
# =====================================================

class TestDataModels:
    """Verify data model correctness"""

    def test_judged_violation_fields(self):
        """JudgedViolation has all expected fields"""
        jv = JudgedViolation(
            violation_id="v1",
            original_severity=HarmSeverity.MAJOR,
            judged_severity=HarmSeverity.SEVERE,
            cot_reasoning="Step 1... Step 2...",
            causal_factors=["factor1", "factor2"],
            clinical_significance="High impact",
            confidence=0.9,
            severity_changed=True,
        )
        assert jv.violation_id == "v1"
        assert jv.severity_changed is True
        assert len(jv.causal_factors) == 2

    def test_causal_relationship_fields(self):
        """CausalRelationship has all expected fields"""
        cr = CausalRelationship(
            cause_violation_id="v1",
            effect_violation_id="v2",
            relationship_type="direct_cause",
            explanation="V1 caused V2",
            confidence=0.85,
        )
        assert cr.cause_violation_id == "v1"
        assert cr.relationship_type == "direct_cause"

    def test_judgment_result_fields(self):
        """JudgmentResult has all expected fields"""
        jr = JudgmentResult(
            judged_violations=[],
            causal_relationships=[],
            overall_assessment="All clear",
            total_llm_tokens_used=100,
        )
        assert jr.total_llm_tokens_used == 100

    def test_config_defaults(self):
        """LLMJudgeConfig has sensible defaults"""
        config = LLMJudgeConfig()
        assert config.enable_cot_reasoning is True
        assert config.enable_causal_analysis is True
        assert config.max_violations_per_batch == 10
        assert config.temperature == 0.1


# =====================================================
# TEST CATEGORY 6: Batching
# =====================================================

class TestBatching:
    """Violation batching for large episode handling"""

    def test_violations_batched_correctly(self):
        """Violations are split into batches of max size"""
        # Create 15 violations with batch size 10 = 2 batches
        batch1_resp = _mock_multi_assessment_response(
            [{"id": f"v{i}", "severity": "major"} for i in range(10)]
        )
        batch2_resp = _mock_multi_assessment_response(
            [{"id": f"v{i}", "severity": "moderate"} for i in range(10, 15)]
        )
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[batch1_resp, batch2_resp],
            enable_causal_analysis=False,
            max_violations_per_batch=10,
        )
        judge = LLMSeverityJudge(config)
        violations = [_make_violation(f"v{i}") for i in range(15)]

        result = judge.judge_violations(violations)
        assert len(result.judged_violations) == 15

    def test_single_batch_no_split(self):
        """Violations under batch size are processed in one call"""
        mock_resp = _mock_multi_assessment_response(
            [{"id": "v0", "severity": "major"}, {"id": "v1", "severity": "major"}]
        )
        config = LLMJudgeConfig(
            backend="mock",
            mock_responses=[mock_resp],
            enable_causal_analysis=False,
            max_violations_per_batch=10,
        )
        judge = LLMSeverityJudge(config)
        violations = [_make_violation("v0"), _make_violation("v1")]

        result = judge.judge_violations(violations)
        assert len(result.judged_violations) == 2
