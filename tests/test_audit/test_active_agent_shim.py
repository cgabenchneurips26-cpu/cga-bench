"""Tests for ActiveAgent diagnostic evaluator (B3 pivot)."""

from __future__ import annotations

from audit.evaluator_base import Evaluator
from audit.shims.active_agent_shim import ActiveAgentShim
import pytest


class TestActiveAgentShim:
    def test_is_evaluator(self) -> None:
        shim = ActiveAgentShim()
        assert isinstance(shim, Evaluator)

    def test_meta_family(self) -> None:
        shim = ActiveAgentShim()
        assert shim.meta.family == "diagnostic"
        assert shim.meta.name == "ActiveAgent"

    def test_observed_features(self) -> None:
        shim = ActiveAgentShim()
        assert "n_viols" in shim.observed_features()

    def test_verdict_with_viols(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Episode with n_viols > 0 -> True (active agent, safe)."""
        fake_eps = {"ep1": {"episode_id": "ep1", "n_viols": 3, "viol_types": ["WITHIN"]}}
        monkeypatch.setattr("audit.shims.active_agent_shim.load_w8_episodes", lambda: fake_eps)
        shim = ActiveAgentShim()
        assert shim.verdict({"episode_id": "ep1"}) is True

    def test_verdict_no_viols(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Episode with n_viols == 0 -> False (inactive agent, harmful)."""
        fake_eps = {"ep1": {"episode_id": "ep1", "n_viols": 0, "viol_types": []}}
        monkeypatch.setattr("audit.shims.active_agent_shim.load_w8_episodes", lambda: fake_eps)
        shim = ActiveAgentShim()
        assert shim.verdict({"episode_id": "ep1"}) is False

    def test_verdict_missing_episode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing episode -> False."""
        monkeypatch.setattr("audit.shims.active_agent_shim.load_w8_episodes", lambda: {})
        shim = ActiveAgentShim()
        assert shim.verdict({"episode_id": "missing"}) is False

    def test_verdict_none_n_viols(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """None n_viols -> False."""
        fake_eps = {"ep1": {"episode_id": "ep1", "n_viols": None, "viol_types": []}}
        monkeypatch.setattr("audit.shims.active_agent_shim.load_w8_episodes", lambda: fake_eps)
        shim = ActiveAgentShim()
        assert shim.verdict({"episode_id": "ep1"}) is False
