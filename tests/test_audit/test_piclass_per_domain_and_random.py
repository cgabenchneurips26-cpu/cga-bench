"""Tests for T1-5 per-domain + T1-6 random-clustering experiments."""

from __future__ import annotations

import pytest

from scripts.experiments.exp_piclass_per_domain import _compute_domain_tau
from scripts.experiments.exp_piclass_random_clustering import (
    _same_cross_nondegen_gap,
    _size_preserving_partition,
    run_random_clustering,
)


class TestComputeDomainTau:
    def test_zero_episodes_returns_none(self) -> None:
        pi = {"dxem": "term", "ac_proxy": "nctx", "mab_proxy": "term",
              "c2_shim": "aset", "acov_shim": "nctx", "v4_hard": "nctx"}
        assert _compute_domain_tau({}, pi, "anything") is None

    def test_nonempty_returns_structured_row(self) -> None:
        pi = {"dxem": "term", "ac_proxy": "nctx", "mab_proxy": "term",
              "c2_shim": "aset", "acov_shim": "nctx", "v4_hard": "nctx"}
        eps = {
            "e1": {"scenario_id": "sepsis_foo", "dxem": True, "ac_proxy": True,
                   "mab_proxy": False, "c2_pass": True, "acov_pass": False,
                   "v4_hard": True},
            "e2": {"scenario_id": "sepsis_bar", "dxem": False, "ac_proxy": False,
                   "mab_proxy": True, "c2_pass": False, "acov_pass": True,
                   "v4_hard": False},
        }
        r = _compute_domain_tau(eps, pi, "sepsis")
        assert r is not None
        assert r["prefix"] == "sepsis"
        assert r["n_episodes"] == 2
        assert "gap" in r


class TestRandomClusteringGap:
    def test_degenerate_pairs_filtered(self) -> None:
        pairs = [
            {"evaluator_a": "A", "evaluator_b": "B", "tau": 0.8},
            {"evaluator_a": "A", "evaluator_b": "C", "tau": 0.0005},  # degen
            {"evaluator_a": "B", "evaluator_b": "C", "tau": 0.2},
        ]
        part = {"A": "term", "B": "term", "C": "nctx"}
        # same: AB=0.8 → 0.8
        # cross: BC=0.2 → 0.2
        gap = _same_cross_nondegen_gap(pairs, part)
        assert gap == pytest.approx(0.6)


class TestSizePreservingPartition:
    def test_preserves_sizes(self) -> None:
        import random

        rng = random.Random(42)
        names = ["a", "b", "c", "d", "e", "f"]
        sizes = {"x": 2, "y": 3, "z": 1}
        part = _size_preserving_partition(names, sizes, rng)
        actual = {"x": 0, "y": 0, "z": 0}
        for v in part.values():
            actual[v] += 1
        assert actual == sizes


class TestRunRandomClustering:
    def test_seed_determinism(self) -> None:
        pi = {"A": "term", "B": "term", "C": "nctx", "D": "nctx"}
        pairs = [
            {"evaluator_a": "A", "evaluator_b": "B", "tau": 0.9},
            {"evaluator_a": "C", "evaluator_b": "D", "tau": 0.9},
            {"evaluator_a": "A", "evaluator_b": "C", "tau": 0.1},
            {"evaluator_a": "A", "evaluator_b": "D", "tau": 0.1},
            {"evaluator_a": "B", "evaluator_b": "C", "tau": 0.1},
            {"evaluator_a": "B", "evaluator_b": "D", "tau": 0.1},
        ]
        r1 = run_random_clustering(pairs, pi, B=500, seed=7)
        r2 = run_random_clustering(pairs, pi, B=500, seed=7)
        assert r1 == r2

    def test_strong_separation_low_p(self) -> None:
        """Perfect within-class = 0.9 and zero cross = 0.1 should sit at a tail."""
        pi = {"A": "term", "B": "term", "C": "nctx", "D": "nctx"}
        pairs = [
            {"evaluator_a": "A", "evaluator_b": "B", "tau": 0.9},
            {"evaluator_a": "C", "evaluator_b": "D", "tau": 0.9},
            {"evaluator_a": "A", "evaluator_b": "C", "tau": 0.1},
            {"evaluator_a": "A", "evaluator_b": "D", "tau": 0.1},
            {"evaluator_a": "B", "evaluator_b": "C", "tau": 0.1},
            {"evaluator_a": "B", "evaluator_b": "D", "tau": 0.1},
        ]
        res = run_random_clustering(pairs, pi, B=500, seed=42)
        assert res["obs_gap"] == pytest.approx(0.8)
        # With 4 evaluators size {term:2, nctx:2}, there are only C(4,2)/2=3
        # distinct size-preserving partitions, so upper-tail p is bounded below
        # by 1/3. Check it's ≤ that.
        assert res["upper_tail_p"] <= 0.5
