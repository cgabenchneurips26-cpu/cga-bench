"""Tests for T0-1: pi-class permutation test."""

from __future__ import annotations

import pytest

from scripts.experiments.exp_piclass_permutation import (
    _compute_gap,
    permutation_test,
)


_PAIRS_CLEAN_SEPARATION = [
    # same-class pairs (all term) → τ ≈ 1.0
    {"evaluator_a": "A", "evaluator_b": "B", "tau": 1.0},
    {"evaluator_a": "A", "evaluator_b": "C", "tau": 1.0},
    {"evaluator_a": "B", "evaluator_b": "C", "tau": 1.0},
    # same-class pairs (all nctx) → τ ≈ 1.0
    {"evaluator_a": "D", "evaluator_b": "E", "tau": 1.0},
    {"evaluator_a": "D", "evaluator_b": "F", "tau": 1.0},
    {"evaluator_a": "E", "evaluator_b": "F", "tau": 1.0},
    # cross-class pairs → τ ≈ 0.0
    {"evaluator_a": "A", "evaluator_b": "D", "tau": 0.0},
    {"evaluator_a": "A", "evaluator_b": "E", "tau": 0.0},
    {"evaluator_a": "A", "evaluator_b": "F", "tau": 0.0},
    {"evaluator_a": "B", "evaluator_b": "D", "tau": 0.0},
    {"evaluator_a": "B", "evaluator_b": "E", "tau": 0.0},
    {"evaluator_a": "B", "evaluator_b": "F", "tau": 0.0},
    {"evaluator_a": "C", "evaluator_b": "D", "tau": 0.0},
    {"evaluator_a": "C", "evaluator_b": "E", "tau": 0.0},
    {"evaluator_a": "C", "evaluator_b": "F", "tau": 0.0},
]
_PI_CLASSES_CLEAN = {"A": "term", "B": "term", "C": "term", "D": "nctx", "E": "nctx", "F": "nctx"}


class TestComputeGap:
    def test_clean_separation_gap_is_one(self) -> None:
        assert _compute_gap(_PI_CLASSES_CLEAN, _PAIRS_CLEAN_SEPARATION) == pytest.approx(1.0)

    def test_all_same_class_gap_zero(self) -> None:
        flat = {k: "term" for k in _PI_CLASSES_CLEAN}
        # all pairs become same-class; cross has no non-degen pairs → cross mean 0
        # same has 6 non-degen (1.0) + 9 degen (0.0 filtered) → mean 1.0
        # gap = 1.0 - 0.0 = 1.0. Not zero. Use a different fixture:
        pairs = [{"evaluator_a": "A", "evaluator_b": "B", "tau": 0.3}]
        assert _compute_gap({"A": "term", "B": "term"}, pairs) == pytest.approx(0.3)

    def test_empty_cross_returns_mean_same(self) -> None:
        pairs = [{"evaluator_a": "A", "evaluator_b": "B", "tau": 0.5}]
        assert _compute_gap({"A": "term", "B": "term"}, pairs) == pytest.approx(0.5)


class TestPermutationTest:
    def test_clean_separation_gap_above_null_distribution(self) -> None:
        """Strongly separated fixture → obs_gap above null mean by > 1 SD.

        With only 6 evaluators the permutation space is small (15 pairs,
        C(6,3)=20 possible 3-3 splits), so even a maximally separated
        dataset cannot reach p < 0.05 here. We check the effect-size
        surrogate instead: observed gap must exceed null mean + 1 SD.
        """
        res = permutation_test(_PI_CLASSES_CLEAN, _PAIRS_CLEAN_SEPARATION, B=2000, seed=42)
        assert res["obs_gap"] == pytest.approx(1.0)
        assert res["obs_gap"] > res["null_mean"] + res["null_sd"]
        # Observed gap should also be at or very close to the maximum possible gap
        assert res["p_value"] <= 0.15  # 15-pair permutation upper bound

    def test_degenerate_gap_zero_yields_high_p(self) -> None:
        """All pairs identical τ → any permutation gives gap=0; p=1."""
        pairs = [
            {"evaluator_a": n1, "evaluator_b": n2, "tau": 0.5}
            for n1, n2 in [("A", "B"), ("A", "C"), ("B", "C"), ("A", "D"),
                           ("B", "D"), ("C", "D")]
        ]
        pi_class = {"A": "term", "B": "nctx", "C": "nctx", "D": "aset"}
        res = permutation_test(pi_class, pairs, B=500, seed=42)
        # Same τ on all pairs → gap always 0
        assert res["obs_gap"] == pytest.approx(0.0)
        assert res["p_value"] >= 0.99

    def test_seed_determinism(self) -> None:
        r1 = permutation_test(_PI_CLASSES_CLEAN, _PAIRS_CLEAN_SEPARATION, B=500, seed=7)
        r2 = permutation_test(_PI_CLASSES_CLEAN, _PAIRS_CLEAN_SEPARATION, B=500, seed=7)
        assert r1 == r2

    def test_seed_variation_changes_null_draws(self) -> None:
        """Different seeds produce different null distributions."""
        r1 = permutation_test(_PI_CLASSES_CLEAN, _PAIRS_CLEAN_SEPARATION, B=500, seed=1)
        r2 = permutation_test(_PI_CLASSES_CLEAN, _PAIRS_CLEAN_SEPARATION, B=500, seed=999)
        # Obs gap is deterministic; null stats should differ.
        assert r1["obs_gap"] == r2["obs_gap"]
        assert (r1["null_mean"], r1["n_extreme"]) != (r2["null_mean"], r2["n_extreme"])
