"""Tests for C6: audit-guided evaluator selection experiment.

Validates:
1. binary_tau correctness on known inputs
2. pi_class_distance ordinal properties
3. Separation: same-class pairs agree MORE than cross-class pairs
4. Degenerate evaluator detection (DxEM → tau=0 with everything)
5. Structural properties of the result dict
"""

from __future__ import annotations

from audit.metrics.selection import (
    PI_CLASS_ORDER,
    audit_guided_selection,
    binary_tau,
    pi_class_distance,
)
from audit.shims import SHIM_REGISTRY
import pytest
from scripts.audit.evaluator_audit import step1_pi_class


class TestBinaryTau:
    """Unit tests for binary tau (phi coefficient)."""

    def test_perfect_agreement(self) -> None:
        va = [True, False, True, False, True]
        tau = binary_tau(va, va)
        assert abs(tau - 1.0) < 1e-10

    def test_perfect_disagreement(self) -> None:
        va = [True, False, True, False, True]
        vb = [False, True, False, True, False]
        tau = binary_tau(va, vb)
        assert abs(tau - (-1.0)) < 1e-10

    def test_no_correlation(self) -> None:
        """Balanced 2x2 table → tau = 0."""
        va = [True, True, False, False]
        vb = [True, False, True, False]
        tau = binary_tau(va, vb)
        assert abs(tau) < 1e-10

    def test_constant_vector_returns_zero(self) -> None:
        va = [True, True, True, True]
        vb = [True, False, True, False]
        tau = binary_tau(va, vb)
        assert tau == 0.0

    def test_both_constant_returns_zero(self) -> None:
        va = [True, True, True]
        vb = [False, False, False]
        tau = binary_tau(va, vb)
        assert tau == 0.0

    def test_range(self) -> None:
        """Tau always in [-1, 1]."""
        import random

        rng = random.Random(42)
        for _ in range(100):
            n = 50
            va = [rng.choice([True, False]) for _ in range(n)]
            vb = [rng.choice([True, False]) for _ in range(n)]
            tau = binary_tau(va, vb)
            assert -1.0 <= tau <= 1.0


class TestPiClassDistance:
    """Unit tests for pi-class distance."""

    def test_same_class_zero(self) -> None:
        for pi in PI_CLASS_ORDER:
            assert pi_class_distance(pi, pi) == 0

    def test_max_distance(self) -> None:
        assert pi_class_distance("term", "nctx") == 3

    def test_symmetric(self) -> None:
        assert pi_class_distance("aset", "nctx") == pi_class_distance("nctx", "aset")

    def test_adjacent(self) -> None:
        assert pi_class_distance("term", "aset") == 1
        assert pi_class_distance("aset", "nord") == 1
        assert pi_class_distance("nord", "nctx") == 1

    def test_intermediate(self) -> None:
        assert pi_class_distance("term", "nord") == 2
        assert pi_class_distance("aset", "nctx") == 2


class TestAuditGuidedSelection:
    """Integration tests with real W8-filtered data."""

    @pytest.fixture(scope="class")
    def experiment_result(self) -> dict:
        """Run the full experiment once for all tests."""
        shim_names = ["dxem", "ac_proxy", "mab_proxy", "c2_shim", "acov_shim", "v4_hard"]
        evaluators = {name: SHIM_REGISTRY[name]() for name in shim_names}
        pi_classes = {}
        for name, ev in evaluators.items():
            s1 = step1_pi_class(ev)
            pi_classes[name] = s1["pi_class"]
        return audit_guided_selection(evaluators, pi_classes)

    def test_result_structure(self, experiment_result: dict) -> None:
        """Result has all expected top-level keys."""
        expected = {
            "n_evaluators",
            "n_pairs",
            "pi_classes",
            "pairs",
            "audit_guided_pair",
            "same_class_stats",
            "cross_class_stats",
            "null_distribution",
            "degenerate_pairs",
            "separation_confirmed",
        }
        assert set(experiment_result.keys()) == expected

    def test_pair_count(self, experiment_result: dict) -> None:
        """C(6,2) = 15 pairs from 6 evaluators."""
        assert experiment_result["n_evaluators"] == 6
        assert experiment_result["n_pairs"] == 15
        assert len(experiment_result["pairs"]) == 15

    def test_all_tau_in_range(self, experiment_result: dict) -> None:
        """All pairwise tau values in [-1, 1]."""
        for pair in experiment_result["pairs"]:
            assert -1.0 <= pair["tau"] <= 1.0, f"{pair['evaluator_a']}-{pair['evaluator_b']}: tau={pair['tau']}"

    def test_audit_guided_has_max_distance(self, experiment_result: dict) -> None:
        """Audit-guided pair must have maximum pi-class distance."""
        ag_dist = experiment_result["audit_guided_pair"]["pi_distance"]
        max_dist = max(p["pi_distance"] for p in experiment_result["pairs"])
        assert ag_dist == max_dist

    def test_separation_confirmed(self, experiment_result: dict) -> None:
        """Same-class evaluators agree MORE than cross-class (non-degenerate)."""
        assert experiment_result["separation_confirmed"], (
            f"Separation failed: same_nondegen={experiment_result['same_class_stats']['mean_tau_nondegen']:.4f} "
            f"vs cross_nondegen={experiment_result['cross_class_stats']['mean_tau_nondegen']:.4f}"
        )

    def test_dxem_degenerate(self, experiment_result: dict) -> None:
        """DxEM (constant evaluator) produces tau=0 with all partners."""
        dxem_pairs = [p for p in experiment_result["pairs"] if "dxem" in (p["evaluator_a"], p["evaluator_b"])]
        for p in dxem_pairs:
            assert abs(p["tau"]) < 0.001, f"DxEM pair {p['evaluator_a']}-{p['evaluator_b']}: tau={p['tau']}"

    def test_v4_hard_self_class(self, experiment_result: dict) -> None:
        """V4Hard is classified as nctx (finest projection)."""
        assert experiment_result["pi_classes"]["v4_hard"] == "nctx"

    def test_same_class_pairs_exist(self, experiment_result: dict) -> None:
        """At least one same-class pair exists."""
        assert experiment_result["same_class_stats"]["n_pairs"] > 0

    def test_cross_class_pairs_exist(self, experiment_result: dict) -> None:
        """At least one cross-class pair exists."""
        assert experiment_result["cross_class_stats"]["n_pairs"] > 0
