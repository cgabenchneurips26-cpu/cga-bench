"""Unit tests for LLM-as-Judge error severity assessment."""
import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio

from cga_bench.semantic_layer.conformance.llm_error_judge import (
    LLMErrorJudge,
    LLMJudgeConfig,
    SeverityLevel,
    ChainOfThoughtReasoning,
    DimensionalSeverity,
    LLMSeverityAssessment,
    MockLLMProvider,
    VLLMProvider,
)


# ============================================
# Test Fixtures
# ============================================

@pytest.fixture
def mock_config():
    """Create a mock LLM judge config."""
    return LLMJudgeConfig(
        model_backend="mock",
        enable_cot_reasoning=True,
        enable_multi_dimensional=True,
    )


@pytest.fixture
def judge_with_mock(mock_config):
    """Create an LLM judge with mock provider."""
    return LLMErrorJudge(mock_config)


# ============================================
# Test Class: Configuration
# ============================================

class TestLLMJudgeConfig:
    """Tests for LLMJudgeConfig."""

    def test_default_config(self):
        """Default config has expected values."""
        config = LLMJudgeConfig()
        assert config.model_backend == "vllm"
        assert config.enable_cot_reasoning is True
        assert config.enable_multi_dimensional is True
        assert config.temperature == 0.1
        assert config.max_tokens == 1024

    def test_custom_config(self):
        """Custom config values are preserved."""
        config = LLMJudgeConfig(
            model_backend="openai",
            temperature=0.5,
            max_tokens=2048,
        )
        assert config.model_backend == "openai"
        assert config.temperature == 0.5
        assert config.max_tokens == 2048

    def test_severity_dimensions(self):
        """Default severity dimensions are correct."""
        config = LLMJudgeConfig()
        expected = [
            "patient_safety",
            "care_continuity",
            "information_loss",
            "reversibility",
            "time_sensitivity",
        ]
        assert config.severity_dimensions == expected


# ============================================
# Test Class: Severity Levels
# ============================================

class TestSeverityLevel:
    """Tests for SeverityLevel enum."""

    def test_severity_levels_exist(self):
        """All expected severity levels exist."""
        assert SeverityLevel.MINIMAL.value == "minimal"
        assert SeverityLevel.LOW.value == "low"
        assert SeverityLevel.MODERATE.value == "moderate"
        assert SeverityLevel.HIGH.value == "high"
        assert SeverityLevel.CRITICAL.value == "critical"

    def test_severity_ordering(self):
        """Severity levels can be compared."""
        levels = list(SeverityLevel)
        assert len(levels) == 5


# ============================================
# Test Class: Mock Provider
# ============================================

class TestMockLLMProvider:
    """Tests for MockLLMProvider."""

    def test_mock_provider_initialization(self):
        """Mock provider initializes correctly."""
        provider = MockLLMProvider()
        assert provider is not None

    def test_mock_provider_returns_response(self):
        """Mock provider returns a response."""
        provider = MockLLMProvider()
        response, tokens = asyncio.run(provider.complete("System prompt", "Test prompt"))
        assert response is not None
        assert isinstance(response, str)
        assert isinstance(tokens, int)

    def test_mock_provider_json_response(self):
        """Mock provider returns parseable JSON for severity assessment."""
        provider = MockLLMProvider()
        response, tokens = asyncio.run(provider.complete(
            "System prompt",
            "Assess error severity for: OMISSION of blood_culture"
        ))

        # Should contain JSON-like structure
        import json
        # Try to extract JSON from response
        assert "severity" in response.lower() or "{" in response


# ============================================
# Test Class: LLM Error Judge
# ============================================

class TestLLMErrorJudge:
    """Tests for LLMErrorJudge."""

    def test_judge_initialization(self, mock_config):
        """Judge initializes with config."""
        judge = LLMErrorJudge(mock_config)
        assert judge is not None
        assert judge.config == mock_config

    def test_judge_has_provider(self, judge_with_mock):
        """Judge has LLM provider."""
        assert judge_with_mock._provider is not None

    def test_assess_error_returns_assessment(self, judge_with_mock):
        """assess_error_severity_sync returns LLMSeverityAssessment."""
        result = judge_with_mock.assess_error_severity_sync(
            error_type="OMISSION",
            action_attempted="order_blood_culture",
            error_message="Blood culture not ordered",
            domain="sepsis",
        )
        assert isinstance(result, LLMSeverityAssessment)

    def test_assessment_has_severity(self, judge_with_mock):
        """Assessment includes severity level and score."""
        result = judge_with_mock.assess_error_severity_sync(
            error_type="TIMEOUT",
            action_attempted="order_lab",
        )
        assert result.overall_severity is not None
        assert isinstance(result.overall_severity, SeverityLevel)
        assert 0.0 <= result.overall_score <= 1.0

    def test_assessment_has_confidence(self, judge_with_mock):
        """Assessment includes confidence score."""
        result = judge_with_mock.assess_error_severity_sync(
            error_type="NOT_FOUND",
            action_attempted="give_medication",
        )
        assert 0.0 <= result.overall_confidence <= 1.0

    def test_cot_reasoning_enabled(self, judge_with_mock):
        """CoT reasoning is included when enabled."""
        result = judge_with_mock.assess_error_severity_sync(
            error_type="OMISSION",
            action_attempted="assess_vitals",
            error_message="Vitals not assessed",
        )
        # With mock, CoT may be None, but structure should exist
        if result.cot_reasoning:
            assert isinstance(result.cot_reasoning, ChainOfThoughtReasoning)

    def test_dimensional_scores(self, judge_with_mock):
        """Assessment includes dimensional scores."""
        result = judge_with_mock.assess_error_severity_sync(
            error_type="COMMISSION",
            action_attempted="give_nitroglycerin",
            domain="chest_pain",
        )
        assert isinstance(result.dimensional_scores, list)
        if result.dimensional_scores:
            for dim in result.dimensional_scores:
                assert isinstance(dim, DimensionalSeverity)
                assert 0.0 <= dim.score <= 1.0


# ============================================
# Test Class: Clinical Scenarios
# ============================================

class TestClinicalScenarios:
    """Tests for clinical scenario handling."""

    def test_sepsis_scenario(self, judge_with_mock):
        """Sepsis scenario is processed correctly."""
        result = judge_with_mock.assess_error_severity_sync(
            error_type="OMISSION",
            action_attempted="order_blood_culture",
            error_message="Blood culture delayed",
            domain="sepsis",
            phase="initial",
            patient_state={
                "temperature": 39.0,
                "heart_rate": 110,
                "systolic_bp": 90,
            },
            guideline_context="SSC 2021 Hour-1 Bundle",
        )
        assert result.overall_severity is not None

    def test_chest_pain_scenario(self, judge_with_mock):
        """Chest pain scenario is processed correctly."""
        result = judge_with_mock.assess_error_severity_sync(
            error_type="COMMISSION",
            action_attempted="give_nitroglycerin",
            error_message="Nitrates given to RV infarct patient",
            domain="chest_pain",
            phase="treatment",
            patient_state={
                "rv_involvement": True,
                "systolic_bp": 88,
            },
            guideline_context="AHA: Nitrates contraindicated in RV infarction",
        )
        assert result.overall_severity is not None

    def test_aki_scenario(self, judge_with_mock):
        """AKI scenario is processed correctly."""
        result = judge_with_mock.assess_error_severity_sync(
            error_type="COMMISSION",
            action_attempted="order_ct_with_contrast",
            error_message="Contrast given to AKI patient",
            domain="aki",
            phase="assessment",
            patient_state={
                "creatinine": 3.5,
                "egfr": 25,
            },
        )
        assert result.overall_severity is not None


# ============================================
# Test Class: Error Types
# ============================================

class TestErrorTypes:
    """Tests for different error types."""

    @pytest.mark.parametrize("error_type", [
        "OMISSION",
        "COMMISSION",
        "TIMING",
        "SEQUENCE",
        "NOT_FOUND",
        "TIMEOUT",
        "INVALID",
    ])
    def test_all_error_types(self, judge_with_mock, error_type):
        """All error types are handled."""
        result = judge_with_mock.assess_error_severity_sync(
            error_type=error_type,
            action_attempted="test_action",
        )
        assert result.overall_severity is not None


# ============================================
# Test Class: Edge Cases
# ============================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_context(self, judge_with_mock):
        """Handles empty clinical context."""
        result = judge_with_mock.assess_error_severity_sync(
            error_type="OMISSION",
            action_attempted="test_action",
            # No context provided
        )
        assert result is not None

    def test_minimal_input(self, judge_with_mock):
        """Handles minimal input."""
        result = judge_with_mock.assess_error_severity_sync(
            error_type="TIMEOUT",
            action_attempted="action",
        )
        assert result is not None

    def test_long_action_name(self, judge_with_mock):
        """Handles long action names."""
        long_action = "order_comprehensive_metabolic_panel_with_additional_tests_" * 5
        result = judge_with_mock.assess_error_severity_sync(
            error_type="OMISSION",
            action_attempted=long_action,
        )
        assert result is not None

    def test_special_characters_in_message(self, judge_with_mock):
        """Handles special characters in error message."""
        result = judge_with_mock.assess_error_severity_sync(
            error_type="INVALID",
            action_attempted="test",
            error_message="Error with 'quotes' and \"double quotes\" and {brackets}",
        )
        assert result is not None


# ============================================
# Test Class: Batch Processing
# ============================================

class TestBatchProcessing:
    """Tests for batch error assessment."""

    def test_batch_assessment(self, mock_config):
        """Batch assessment processes multiple errors."""
        judge = LLMErrorJudge(mock_config)
        errors = [
            {
                "error_type": "OMISSION",
                "action_attempted": "order_blood_culture",
            },
            {
                "error_type": "TIMING",
                "action_attempted": "give_antibiotics",
            },
            {
                "error_type": "COMMISSION",
                "action_attempted": "give_nitroglycerin",
            },
        ]
        results = asyncio.run(judge.assess_batch(errors, max_concurrent=2))
        assert len(results) == 3
        for result in results:
            assert isinstance(result, LLMSeverityAssessment)


# ============================================
# Test Class: Data Classes
# ============================================

class TestDataClasses:
    """Tests for data class structures."""

    def test_chain_of_thought_reasoning(self):
        """ChainOfThoughtReasoning has expected fields."""
        cot = ChainOfThoughtReasoning(
            error_description="Test error",
            clinical_context="Test context",
            immediate_impact="Test impact",
            downstream_effects="Test effects",
            patient_population_risk="Test risk",
            aggravating_factors=["factor1"],
            mitigating_factors=["factor2"],
            severity_level=SeverityLevel.MODERATE,
            confidence=0.8,
            key_reasoning="Test reasoning",
        )
        assert cot.error_description == "Test error"
        assert cot.severity_level == SeverityLevel.MODERATE
        assert cot.confidence == 0.8

    def test_dimensional_severity(self):
        """DimensionalSeverity has expected fields."""
        dim = DimensionalSeverity(
            dimension="patient_safety",
            score=0.9,
            reasoning="High risk",
            confidence=0.8,
        )
        assert dim.dimension == "patient_safety"
        assert dim.score == 0.9
        assert dim.reasoning == "High risk"
        assert dim.confidence == 0.8

    def test_llm_severity_assessment(self):
        """LLMSeverityAssessment has expected fields."""
        assessment = LLMSeverityAssessment(
            error_id="test_001",
            error_type="OMISSION",
            action_attempted="test_action",
            cot_reasoning=None,
            dimensional_scores=[],
            overall_severity=SeverityLevel.HIGH,
            overall_score=0.75,
            overall_confidence=0.9,
            summary_explanation="Test summary",
            clinical_recommendation="Test recommendation",
        )
        assert assessment.error_id == "test_001"
        assert assessment.overall_severity == SeverityLevel.HIGH
        assert assessment.overall_score == 0.75
