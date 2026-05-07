"""Tests for B1: Ensemble BSR experiment."""

from __future__ import annotations

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.metrics.ensemble import _bsr_from_verdicts, ensemble_bsr_experiment
import pytest

# ---- Fixtures: Synthetic evaluators ----


class AlwaysTrueEval(Evaluator):
    meta = EvaluatorMeta(name="AlwaysTrue", family="test")

    def verdict(self, ep: dict) -> bool:
        return True


class AlwaysFalseEval(Evaluator):
    meta = EvaluatorMeta(name="AlwaysFalse", family="test")

    def verdict(self, ep: dict) -> bool:
        return False


class EvenTrueEval(Evaluator):
    """True for even-numbered episodes, False for odd."""

    meta = EvaluatorMeta(name="EvenTrue", family="test")

    def verdict(self, ep: dict) -> bool:
        idx = int(ep["episode_id"].split("_")[-1])
        return idx % 2 == 0


class ThirdTrueEval(Evaluator):
    """True for episodes divisible by 3, False otherwise."""

    meta = EvaluatorMeta(name="ThirdTrue", family="test")

    def verdict(self, ep: dict) -> bool:
        idx = int(ep["episode_id"].split("_")[-1])
        return idx % 3 == 0


# ---- Unit tests: _bsr_from_verdicts ----


class TestBSRFromVerdicts:
    def test_perfect_agreement(self) -> None:
        ref = [True, False, True, False]
        result = _bsr_from_verdicts(ref, ref)
        assert result["bsr"] == 0.0
        assert result["n_disagree"] == 0

    def test_complete_disagreement(self) -> None:
        consensus = [True, True, True, True]
        reference = [False, False, False, False]
        result = _bsr_from_verdicts(consensus, reference)
        assert result["bsr"] == 1.0
        assert result["false_accept"] == 4
        assert result["false_reject"] == 0

    def test_mixed(self) -> None:
        consensus = [True, False, True, False]
        reference = [True, True, False, False]
        result = _bsr_from_verdicts(consensus, reference)
        assert result["bsr"] == 0.5
        assert result["false_accept"] == 1
        assert result["false_reject"] == 1

    def test_empty(self) -> None:
        result = _bsr_from_verdicts([], [])
        assert result["bsr"] == 0.0
        assert result["n_total"] == 0


# ---- Unit tests: AND/OR consensus properties ----


class TestConsensusProperties:
    """Test mathematical properties of AND/OR consensus."""

    def test_and_consensus_is_conservative(self) -> None:
        """AND-consensus: True only if BOTH say True -> fewer false accepts."""
        va = [True, True, False, True]
        vb = [True, False, True, True]
        and_c = [a and b for a, b in zip(va, vb)]
        assert and_c == [True, False, False, True]
        # AND produces fewer Trues than either individual
        assert sum(and_c) <= sum(va)
        assert sum(and_c) <= sum(vb)

    def test_or_consensus_is_permissive(self) -> None:
        """OR-consensus: True if EITHER says True -> fewer false rejects."""
        va = [True, True, False, False]
        vb = [True, False, True, False]
        or_c = [a or b for a, b in zip(va, vb)]
        assert or_c == [True, True, True, False]
        assert sum(or_c) >= sum(va)
        assert sum(or_c) >= sum(vb)


# ---- Integration test with synthetic episodes ----


class TestEnsembleBSRExperiment:
    @pytest.fixture()
    def synthetic_episodes(self) -> dict[str, dict]:
        """12 episodes: v4_hard alternates True/False."""
        eps = {}
        for i in range(12):
            eid = f"syn_{i}"
            eps[eid] = {
                "episode_id": eid,
                "v4_hard": i % 2 == 0,  # even=True, odd=False
            }
        return eps

    def test_basic_run(self, synthetic_episodes: dict) -> None:
        """Experiment runs and produces expected structure."""
        evaluators = {
            "ev_even": EvenTrueEval(),
            "ev_third": ThirdTrueEval(),
            "ev_all": AlwaysTrueEval(),
        }
        pi_classes = {
            "ev_even": "nctx",
            "ev_third": "aset",
            "ev_all": "term",
        }

        # Monkeypatch get_verdict to use synthetic data
        import audit.metrics.ensemble as mod

        original = mod.get_verdict

        def fake_get_verdict(eid: str, col: str) -> bool:
            return synthetic_episodes[eid]["v4_hard"]

        mod.get_verdict = fake_get_verdict

        try:
            result = ensemble_bsr_experiment(evaluators, pi_classes, episodes=synthetic_episodes)
        finally:
            mod.get_verdict = original

        assert result["n_evaluators"] == 3
        assert result["n_pairs"] == 3
        assert result["n_episodes"] == 12
        assert len(result["pairs"]) == 3
        assert "same_class_stats" in result
        assert "cross_class_stats" in result
        assert "hypothesis_confirmed" in result

    def test_and_fa_leq_or_fa(self, synthetic_episodes: dict) -> None:
        """AND-consensus false-accept set is a subset of OR-consensus's.

        If AND(a,b) = True then both a and b are True, which implies OR(a,b) = True.
        Therefore {ep : AND=True, ref=False} subset of {ep : OR=True, ref=False},
        so and_fa <= or_fa for every pair. This is the core "AND is conservative"
        invariant the ensemble result relies on.
        """
        evaluators = {
            "ev_even": EvenTrueEval(),
            "ev_third": ThirdTrueEval(),
        }
        pi_classes = {"ev_even": "nctx", "ev_third": "aset"}

        import audit.metrics.ensemble as mod

        original = mod.get_verdict

        def fake_get_verdict(eid: str, col: str) -> bool:
            return synthetic_episodes[eid]["v4_hard"]

        mod.get_verdict = fake_get_verdict

        try:
            result = ensemble_bsr_experiment(evaluators, pi_classes, episodes=synthetic_episodes)
        finally:
            mod.get_verdict = original

        for p in result["pairs"]:
            assert p["and_fa"] <= p["or_fa"], (
                f"{p['evaluator_a']}x{p['evaluator_b']}: "
                f"and_fa={p['and_fa']} > or_fa={p['or_fa']} — "
                "AND cannot produce more false-accepts than OR"
            )

    def test_pair_count_formula(self, synthetic_episodes: dict) -> None:
        """C(n,2) pairs produced."""
        evaluators = {
            "a": AlwaysTrueEval(),
            "b": AlwaysFalseEval(),
            "c": EvenTrueEval(),
            "d": ThirdTrueEval(),
        }
        pi_classes = {"a": "term", "b": "nctx", "c": "aset", "d": "nord"}

        import audit.metrics.ensemble as mod

        original = mod.get_verdict

        def fake_get_verdict(eid: str, col: str) -> bool:
            return synthetic_episodes[eid]["v4_hard"]

        mod.get_verdict = fake_get_verdict

        try:
            result = ensemble_bsr_experiment(evaluators, pi_classes, episodes=synthetic_episodes)
        finally:
            mod.get_verdict = original

        # C(4,2) = 6 pairs
        assert result["n_pairs"] == 6

    def test_same_vs_cross_grouping(self, synthetic_episodes: dict) -> None:
        """Same-class and cross-class grouping is correct."""
        evaluators = {
            "a": AlwaysTrueEval(),
            "b": EvenTrueEval(),
            "c": ThirdTrueEval(),
        }
        # a and b are same class (nctx), c is different (aset)
        pi_classes = {"a": "nctx", "b": "nctx", "c": "aset"}

        import audit.metrics.ensemble as mod

        original = mod.get_verdict

        def fake_get_verdict(eid: str, col: str) -> bool:
            return synthetic_episodes[eid]["v4_hard"]

        mod.get_verdict = fake_get_verdict

        try:
            result = ensemble_bsr_experiment(evaluators, pi_classes, episodes=synthetic_episodes)
        finally:
            mod.get_verdict = original

        assert result["same_class_stats"]["n_pairs"] == 1  # a,b
        assert result["cross_class_stats"]["n_pairs"] == 2  # a,c and b,c
