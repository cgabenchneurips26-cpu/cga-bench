"""Tests for T1-4: Held-out 5-CPG generalisation."""

from __future__ import annotations

import pytest

from scripts.experiments.exp_piclass_heldout import (
    HELDOUT_PREFIXES,
    _filter_episodes,
    _heldout_vs_core,
    _pair_results,
    _same_cross_nondegen,
)


@pytest.fixture
def pi_classes() -> dict[str, str]:
    return {"A": "term", "B": "term", "C": "nctx", "D": "nctx"}


class TestFilterEpisodes:
    def test_prefix_filter_hits(self) -> None:
        eps = {
            "e1": {"scenario_id": "aba_burn_1"},
            "e2": {"scenario_id": "septic_shock"},
            "e3": {"scenario_id": "toxicology_m_acet"},
        }
        held = _filter_episodes(eps, HELDOUT_PREFIXES)
        assert set(held) == {"e1", "e3"}

    def test_empty_input(self) -> None:
        assert _filter_episodes({}, HELDOUT_PREFIXES) == {}


class TestSameCrossNondegen:
    def test_filters_degenerate_pairs(self, pi_classes: dict[str, str]) -> None:
        pairs = [
            {"evaluator_a": "A", "evaluator_b": "B", "tau": 0.5},
            {"evaluator_a": "A", "evaluator_b": "C", "tau": 0.0005},  # degen
            {"evaluator_a": "C", "evaluator_b": "D", "tau": 0.7},
            {"evaluator_a": "A", "evaluator_b": "D", "tau": 0.1},
        ]
        s, c, ns, nc = _same_cross_nondegen(pairs, pi_classes)
        assert s == pytest.approx(0.6)   # (0.5 + 0.7) / 2
        assert c == pytest.approx(0.1)
        assert ns == 2
        assert nc == 1

    def test_empty_pairs_returns_zero(self, pi_classes: dict[str, str]) -> None:
        s, c, ns, nc = _same_cross_nondegen([], pi_classes)
        assert (s, c, ns, nc) == (0.0, 0.0, 0, 0)


class TestPairResults:
    def test_tau_range(self, pi_classes: dict[str, str]) -> None:
        verdicts = {
            "A": [True, True, False, False],
            "B": [True, True, False, False],  # perfect agreement
            "C": [False, False, True, True],  # anti-correlated
            "D": [True, False, True, False],  # uncorrelated
        }
        pairs = _pair_results(verdicts, pi_classes)
        assert len(pairs) == 6
        # AB same-class perfect
        ab = next(p for p in pairs if set((p["evaluator_a"], p["evaluator_b"])) == {"A", "B"})
        assert ab["tau"] == pytest.approx(1.0)
        ac = next(p for p in pairs if set((p["evaluator_a"], p["evaluator_b"])) == {"A", "C"})
        assert ac["tau"] == pytest.approx(-1.0)


class TestHeldoutVsCore:
    def test_split_sanity(self, pi_classes: dict[str, str]) -> None:
        # Need canonical-6 evaluator columns; use minimal fake ep structure
        def _fake(verdicts: tuple[bool, ...], scenario: str) -> dict:
            return {
                "scenario_id": scenario,
                "dxem": verdicts[0],
                "ac_proxy": verdicts[1],
                "mab_proxy": verdicts[2],
                "c2_pass": verdicts[3],
                "acov_pass": verdicts[4],
                "v4_hard": verdicts[5],
            }

        pi_c6 = {
            "dxem": "term",
            "ac_proxy": "nctx",
            "mab_proxy": "term",
            "c2_shim": "aset",
            "acov_shim": "nctx",
            "v4_hard": "nctx",
        }
        eps = {
            f"ep_held_{i}": _fake((True,) * 6, "aba_burn_scenario")
            for i in range(4)
        }
        eps.update(
            {
                f"ep_core_{i}": _fake((False,) * 6, "sepsis_basic")
                for i in range(8)
            }
        )

        res = _heldout_vs_core(eps, pi_c6)
        assert res["held_out"]["n_episodes"] == 4
        assert res["core"]["n_episodes"] == 8
        # All-True / all-False yields zero variance → degen → means 0
        # but counts should be non-negative integers
        assert res["held_out"]["n_same_nondegen"] >= 0
        assert res["held_out"]["n_cross_nondegen"] >= 0
