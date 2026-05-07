from __future__ import annotations

import pytest

from cga_bench.assessor_core.dual_track_evaluator import ScoringPolicy


class TestScoringPolicyDefaults:
    def test_default_policy_id(self):
        p = ScoringPolicy()
        assert p.policy_id == "CGA-v2.0-safety-dominant"
        assert p.safety_gate_enabled is True
        assert p.high_severity_threshold == 1


class TestModularSafety:
    def test_zero_high_count_returns_one(self):
        assert ScoringPolicy.compute_modular_safety(0) == 1.0

    def test_one_high_count_default_k_returns_zero(self):
        assert ScoringPolicy.compute_modular_safety(1) == 0.0

    def test_high_count_exceeds_k(self):
        assert ScoringPolicy.compute_modular_safety(5, K=3) == 0.0

    def test_fractional_safety(self):
        assert ScoringPolicy.compute_modular_safety(1, K=4) == pytest.approx(0.75)

    def test_k_zero_with_violations(self):
        assert ScoringPolicy.compute_modular_safety(1, K=0) == 0.0

    def test_k_zero_without_violations(self):
        assert ScoringPolicy.compute_modular_safety(0, K=0) == 1.0


class TestClassifyDivergence:
    def test_aligned_when_equal(self):
        assert ScoringPolicy.classify_divergence(0.5, 0.5) == "ALIGNED"

    def test_aligned_within_threshold(self):
        assert ScoringPolicy.classify_divergence(0.50, 0.55) == "ALIGNED"

    def test_cpg_overspecific(self):
        assert ScoringPolicy.classify_divergence(0.3, 0.8) == "CPG_OVERSPECIFIC"

    def test_benchmark_gap(self):
        assert ScoringPolicy.classify_divergence(0.9, 0.3) == "BENCHMARK_GAP"

    def test_boundary_exactly_at_threshold(self):
        result = ScoringPolicy.classify_divergence(0.5, 0.6)
        assert result == "ALIGNED"


class TestSensitivityAnalysis:
    def test_both_zero(self):
        result = ScoringPolicy.sensitivity_analysis(0.0, 0.0)
        assert result["f1_harmonic"] == 0.0
        assert result["f2_harmonic"] == 0.0
        assert result["arithmetic_mean"] == 0.0
        assert result["multiplicative"] == 0.0

    def test_both_one(self):
        result = ScoringPolicy.sensitivity_analysis(1.0, 1.0)
        assert result["f1_harmonic"] == pytest.approx(1.0)
        assert result["multiplicative"] == pytest.approx(1.0)
        assert result["arithmetic_mean"] == pytest.approx(1.0)

    def test_asymmetric_scores(self):
        result = ScoringPolicy.sensitivity_analysis(0.8, 0.4)
        assert result["multiplicative"] == pytest.approx(0.32)
        assert result["arithmetic_mean"] == pytest.approx(0.6)
        assert result["f1_harmonic"] > 0


class TestComputeFinalScore:
    def test_perfect_scores(self):
        p = ScoringPolicy()
        result = p.compute_final_score(1.0, 1.0)
        assert result["final_score"] == pytest.approx(1.0)
        assert result["safety_gate_triggered"] is False

    def test_multiplicative_combination(self):
        p = ScoringPolicy()
        result = p.compute_final_score(0.8, 0.5)
        assert result["final_score"] == pytest.approx(0.4)

    def test_safety_gate_triggers_on_severe(self):
        p = ScoringPolicy()
        result = p.compute_final_score(0.9, 0.9, violation_severities=["severe"])
        assert result["final_score"] == 0.0
        assert result["safety_gate_triggered"] is True
        assert result["high_severity_count"] == 1

    def test_safety_gate_triggers_on_catastrophic(self):
        p = ScoringPolicy()
        result = p.compute_final_score(0.9, 0.9, violation_severities=["catastrophic"])
        assert result["final_score"] == 0.0
        assert result["safety_gate_triggered"] is True

    def test_safety_gate_disabled(self):
        p = ScoringPolicy(safety_gate_enabled=False)
        result = p.compute_final_score(0.9, 0.9, violation_severities=["severe"])
        assert result["final_score"] == pytest.approx(0.81)
        assert result["safety_gate_triggered"] is False

    def test_moderate_severity_no_gate(self):
        p = ScoringPolicy()
        result = p.compute_final_score(0.8, 0.7, violation_severities=["moderate", "minor"])
        assert result["final_score"] == pytest.approx(0.56)
        assert result["safety_gate_triggered"] is False
        assert result["high_severity_count"] == 0

    def test_cpg_overspecific_guard_raises_floor(self):
        p = ScoringPolicy()
        result = p.compute_final_score(
            track_a_score=0.3,
            track_b_compliance=0.9,
            modular_compliance=0.95,
        )
        assert result["divergence_type"] == "CPG_OVERSPECIFIC"
        assert result["cpg_compliance"] == pytest.approx(0.95)
        assert result["cpg_compliance_raw"] == pytest.approx(0.9)
        assert result["final_score"] == pytest.approx(0.3 * 0.95)

    def test_cpg_overspecific_guard_no_effect_when_track_b_higher(self):
        p = ScoringPolicy()
        result = p.compute_final_score(
            track_a_score=0.3,
            track_b_compliance=0.8,
            modular_compliance=0.5,
        )
        assert result["cpg_compliance"] == pytest.approx(0.8)

    def test_result_contains_all_required_fields(self):
        p = ScoringPolicy()
        result = p.compute_final_score(0.5, 0.5)
        required = [
            "original_benchmark_score", "cpg_compliance", "cpg_compliance_raw",
            "modular_safety", "final_score", "safety_gate_triggered",
            "high_severity_count", "divergence", "divergence_type",
            "policy_id", "policy_version", "formula", "sensitivity",
        ]
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_sensitivity_included_in_result(self):
        p = ScoringPolicy()
        result = p.compute_final_score(0.7, 0.6)
        sens = result["sensitivity"]
        assert "f1_harmonic" in sens
        assert "f2_harmonic" in sens
        assert "arithmetic_mean" in sens
        assert "multiplicative" in sens


class TestMonotonicityDualTrack:
    def test_higher_track_b_produces_higher_final(self):
        p = ScoringPolicy()
        prev_final = -1.0
        for b in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
            result = p.compute_final_score(0.8, b)
            assert result["final_score"] >= prev_final
            prev_final = result["final_score"]

    def test_higher_track_a_produces_higher_final(self):
        p = ScoringPolicy()
        prev_final = -1.0
        for a in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
            result = p.compute_final_score(a, 0.7)
            assert result["final_score"] >= prev_final
            prev_final = result["final_score"]

    def test_safety_gate_dominates(self):
        p = ScoringPolicy()
        result_safe = p.compute_final_score(1.0, 1.0)
        result_gated = p.compute_final_score(1.0, 1.0, violation_severities=["severe"])
        assert result_safe["final_score"] == 1.0
        assert result_gated["final_score"] == 0.0
