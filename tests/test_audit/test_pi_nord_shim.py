"""Tests for PiNordShim (B3 constructive witness)."""

from __future__ import annotations

from audit.evaluator_base import Evaluator
from audit.shims.pi_nord_shim import PiNordShim
import pytest


class TestPiNordShim:
    def test_is_evaluator(self) -> None:
        assert isinstance(PiNordShim(), Evaluator)

    def test_meta(self) -> None:
        shim = PiNordShim()
        assert shim.meta.name == "PiNordWitness"
        assert shim.meta.family == "pi_nord_constructive"

    def test_observed_features_are_pi_nord_admissible(self) -> None:
        """No TCC-derived field may appear in observed_features."""
        shim = PiNordShim()
        feats = shim.observed_features()
        forbidden = {
            "n_viols",
            "viol_types",
            "violation_events",
            "compliance_score",
            "sub_scores",
        }
        assert feats.isdisjoint(forbidden), (
            f"PiNord witness must not read TCC-derived fields; found: {feats & forbidden}"
        )

    def test_verdict_pass_when_expected_satisfied_and_no_forbidden(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = {
            "actions": [
                {"action_id": "order_cbc"},
                {"action_id": "order_type_and_screen"},
            ],
            "expected_actions": ["order_cbc", "order_type_and_screen"],
            "forbidden_actions": ["delay_blood_products_for_crossmatch"],
        }
        monkeypatch.setattr("audit.shims.pi_nord_shim.load_trajectory", lambda eid: fake)
        assert PiNordShim().verdict({"episode_id": "x"}) is True

    def test_verdict_fail_when_missing_expected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = {
            "actions": [{"action_id": "order_cbc"}],
            "expected_actions": ["order_cbc", "order_type_and_screen"],
            "forbidden_actions": [],
        }
        monkeypatch.setattr("audit.shims.pi_nord_shim.load_trajectory", lambda eid: fake)
        assert PiNordShim().verdict({"episode_id": "x"}) is False

    def test_verdict_fail_on_forbidden_action(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = {
            "actions": [
                {"action_id": "order_cbc"},
                {"action_id": "delay_blood_products_for_crossmatch"},
            ],
            "expected_actions": ["order_cbc"],
            "forbidden_actions": ["delay_blood_products_for_crossmatch"],
        }
        monkeypatch.setattr("audit.shims.pi_nord_shim.load_trajectory", lambda eid: fake)
        assert PiNordShim().verdict({"episode_id": "x"}) is False

    def test_verdict_fail_on_empty_trajectory(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = {"actions": [], "expected_actions": ["a"], "forbidden_actions": []}
        monkeypatch.setattr("audit.shims.pi_nord_shim.load_trajectory", lambda eid: fake)
        assert PiNordShim().verdict({"episode_id": "x"}) is False

    def test_verdict_fail_on_missing_trajectory(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("audit.shims.pi_nord_shim.load_trajectory", lambda eid: None)
        assert PiNordShim().verdict({"episode_id": "x"}) is False
