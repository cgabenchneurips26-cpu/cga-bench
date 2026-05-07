"""Tests for enhanced ScoringPolicy: modular_safety, sensitivity, divergence, reporting."""

import pytest

from cga_bench.assessor_core.dual_track_evaluator import ScoringPolicy


class TestPolicyVersion:
    """E10: Policy version and ID present in output."""

    def test_policy_version_present(self):
        policy = ScoringPolicy()
        result = policy.compute_final_score(0.8, 0.9)
        assert "policy_version" in result
        assert result["policy_version"] == "2.0.0"

    def test_policy_id_present(self):
        policy = ScoringPolicy()
        result = policy.compute_final_score(0.8, 0.9)
        assert result["policy_id"] == "CGA-v2.0-safety-dominant"

    def test_custom_policy_id(self):
        policy = ScoringPolicy(policy_id="custom-policy", policy_version="3.0.0")
        result = policy.compute_final_score(0.5, 0.5)
        assert result["policy_id"] == "custom-policy"
        assert result["policy_version"] == "3.0.0"


class TestModularSafety:
    """Modular safety computation: 1.0 - min(1.0, high_count / K)."""

    def test_zero_violations(self):
        assert ScoringPolicy.compute_modular_safety(0, K=1) == 1.0

    def test_one_violation_K1(self):
        assert ScoringPolicy.compute_modular_safety(1, K=1) == 0.0

    def test_two_violations_K2(self):
        assert ScoringPolicy.compute_modular_safety(2, K=2) == 0.0

    def test_one_violation_K2(self):
        assert ScoringPolicy.compute_modular_safety(1, K=2) == 0.5

    def test_one_violation_K4(self):
        assert ScoringPolicy.compute_modular_safety(1, K=4) == 0.75

    def test_exceeds_K(self):
        """More violations than K still clamps to 0."""
        assert ScoringPolicy.compute_modular_safety(5, K=2) == 0.0

    def test_K_zero_no_violations(self):
        assert ScoringPolicy.compute_modular_safety(0, K=0) == 1.0

    def test_K_zero_with_violations(self):
        assert ScoringPolicy.compute_modular_safety(3, K=0) == 0.0


class TestSensitivityAnalysis:
    """F1, F2 harmonic, arithmetic, multiplicative."""

    def test_sensitivity_keys(self):
        result = ScoringPolicy.sensitivity_analysis(0.8, 0.6)
        assert "f1_harmonic" in result
        assert "f2_harmonic" in result
        assert "arithmetic_mean" in result
        assert "multiplicative" in result

    def test_multiplicative(self):
        result = ScoringPolicy.sensitivity_analysis(0.8, 0.5)
        assert abs(result["multiplicative"] - 0.4) < 1e-9

    def test_arithmetic(self):
        result = ScoringPolicy.sensitivity_analysis(0.8, 0.4)
        assert abs(result["arithmetic_mean"] - 0.6) < 1e-9

    def test_f1_harmonic(self):
        """F1 = 2*a*b/(a+b)"""
        result = ScoringPolicy.sensitivity_analysis(1.0, 1.0)
        assert abs(result["f1_harmonic"] - 1.0) < 1e-9

    def test_f1_zero_case(self):
        result = ScoringPolicy.sensitivity_analysis(0.0, 0.0)
        assert result["f1_harmonic"] == 0.0

    def test_f2_safety_weighted(self):
        """F2 = 5*a*b / (a + 4*b). With b=0 → 0."""
        result = ScoringPolicy.sensitivity_analysis(1.0, 0.0)
        assert result["f2_harmonic"] == 0.0

    def test_f2_equal_scores(self):
        """F2 with equal scores = 5*x^2 / 5x = x."""
        result = ScoringPolicy.sensitivity_analysis(0.8, 0.8)
        assert abs(result["f2_harmonic"] - 0.8) < 1e-9

    def test_sensitivity_bounds(self):
        """All sensitivity variants are bounded between 0 and 1 for valid inputs."""
        for a, b in [(0.9, 0.3), (0.5, 0.8), (1.0, 0.0), (0.0, 0.0)]:
            result = ScoringPolicy.sensitivity_analysis(a, b)
            for key, val in result.items():
                assert 0.0 <= val <= 1.0, f"{key}={val} out of bounds for a={a},b={b}"


class TestDivergenceClassification:
    """ALIGNED / CPG_OVERSPECIFIC / BENCHMARK_GAP."""

    def test_aligned_equal(self):
        assert ScoringPolicy.classify_divergence(0.8, 0.8) == "ALIGNED"

    def test_aligned_small_diff(self):
        assert ScoringPolicy.classify_divergence(0.8, 0.85) == "ALIGNED"

    def test_cpg_overspecific(self):
        """B >> A: CPG demands more than benchmark."""
        assert ScoringPolicy.classify_divergence(0.5, 0.8) == "CPG_OVERSPECIFIC"

    def test_benchmark_gap(self):
        """A >> B: benchmark easy but CPG violations."""
        assert ScoringPolicy.classify_divergence(0.9, 0.5) == "BENCHMARK_GAP"

    def test_boundary_aligned(self):
        """Exactly at threshold boundary (0.09 < 0.1)."""
        assert ScoringPolicy.classify_divergence(0.5, 0.59) == "ALIGNED"

    def test_boundary_cpg_overspecific(self):
        """Just beyond threshold."""
        assert ScoringPolicy.classify_divergence(0.5, 0.61) == "CPG_OVERSPECIFIC"

    def test_boundary_benchmark_gap(self):
        assert ScoringPolicy.classify_divergence(0.7, 0.59) == "BENCHMARK_GAP"


class TestReportingCompleteness:
    """E10: All required fields present in compute_final_score output."""

    REQUIRED_FIELDS = [
        "original_benchmark_score",
        "cpg_compliance",
        "modular_safety",
        "final_score",
        "safety_gate_triggered",
        "high_severity_count",
        "divergence",
        "divergence_type",
        "policy_id",
        "policy_version",
        "formula",
        "sensitivity",
    ]

    def test_all_fields_present(self):
        policy = ScoringPolicy()
        result = policy.compute_final_score(0.7, 0.8)
        for field_name in self.REQUIRED_FIELDS:
            assert field_name in result, f"Missing field: {field_name}"

    def test_all_fields_present_with_violations(self):
        policy = ScoringPolicy()
        result = policy.compute_final_score(
            0.7, 0.8, violation_severities=["severe", "minor"]
        )
        for field_name in self.REQUIRED_FIELDS:
            assert field_name in result, f"Missing field: {field_name}"

    def test_sensitivity_has_four_variants(self):
        policy = ScoringPolicy()
        result = policy.compute_final_score(0.7, 0.8)
        sensitivity = result["sensitivity"]
        assert "f1_harmonic" in sensitivity
        assert "f2_harmonic" in sensitivity
        assert "arithmetic_mean" in sensitivity
        assert "multiplicative" in sensitivity


class TestSafetyGate:
    """Safety gate triggers on high-severity violations."""

    def test_no_violations_no_gate(self):
        policy = ScoringPolicy()
        result = policy.compute_final_score(0.8, 0.9)
        assert result["safety_gate_triggered"] is False
        assert result["final_score"] == pytest.approx(0.8 * 0.9)

    def test_severe_triggers_gate(self):
        policy = ScoringPolicy()
        result = policy.compute_final_score(
            0.8, 0.9, violation_severities=["severe"]
        )
        assert result["safety_gate_triggered"] is True
        assert result["final_score"] == 0.0

    def test_catastrophic_triggers_gate(self):
        policy = ScoringPolicy()
        result = policy.compute_final_score(
            0.8, 0.9, violation_severities=["catastrophic"]
        )
        assert result["safety_gate_triggered"] is True
        assert result["final_score"] == 0.0

    def test_minor_does_not_trigger_gate(self):
        policy = ScoringPolicy()
        result = policy.compute_final_score(
            0.8, 0.9, violation_severities=["minor", "moderate"]
        )
        assert result["safety_gate_triggered"] is False
        assert result["final_score"] > 0

    def test_gate_disabled(self):
        policy = ScoringPolicy(safety_gate_enabled=False)
        result = policy.compute_final_score(
            0.8, 0.9, violation_severities=["severe"]
        )
        assert result["safety_gate_triggered"] is False
        assert result["final_score"] == pytest.approx(0.8 * 0.9)

    def test_modular_safety_zero_on_gate(self):
        """When safety gate triggers, modular_safety should also be 0."""
        policy = ScoringPolicy()
        result = policy.compute_final_score(
            0.8, 0.9, violation_severities=["catastrophic"]
        )
        assert result["modular_safety"] == 0.0

    def test_formula_field(self):
        policy = ScoringPolicy()
        result = policy.compute_final_score(0.5, 0.5)
        assert "formula" in result
        assert isinstance(result["formula"], str)
