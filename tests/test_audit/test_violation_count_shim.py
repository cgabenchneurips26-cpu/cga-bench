"""Tests for ViolationCountEvaluator — EVP-1 extensibility proof."""

from __future__ import annotations

from unittest.mock import patch

from audit.evaluator_base import Evaluator
from audit.shims.violation_count_shim import ViolationCountEvaluator
import pytest


class TestViolationCountEvaluator:
    """Unit tests for the weighted violation count evaluator."""

    def setup_method(self) -> None:
        self.evaluator = ViolationCountEvaluator()

    def test_is_evaluator_subclass(self) -> None:
        assert isinstance(self.evaluator, Evaluator)

    def test_meta_fields(self) -> None:
        assert self.evaluator.meta.name == "ViolCount"
        assert self.evaluator.meta.family == "custom-live"
        assert self.evaluator.meta.source == "live-computation:n_viols+viol_types"

    def test_observed_features(self) -> None:
        features = self.evaluator.observed_features()
        assert "n_viols" in features
        assert "viol_types" in features

    @pytest.fixture()
    def mock_episodes(self) -> dict[str, dict]:
        return {
            "ep_clean": {
                "n_viols": 0,
                "viol_types": [],
            },
            "ep_one_soft": {
                "n_viols": 1,
                "viol_types": ["OMISSION"],
            },
            "ep_two_soft": {
                "n_viols": 2,
                "viol_types": ["OMISSION", "DEVIATION"],
            },
            "ep_one_hard": {
                "n_viols": 1,
                "viol_types": ["COMMISSION"],
            },
            "ep_two_hard": {
                "n_viols": 2,
                "viol_types": ["COMMISSION", "TIMING"],
            },
            "ep_mixed_pass": {
                "n_viols": 2,
                "viol_types": ["COMMISSION", "OMISSION"],
            },
            "ep_mixed_fail": {
                "n_viols": 3,
                "viol_types": ["COMMISSION", "TIMING", "OMISSION"],
            },
            "ep_three_soft": {
                "n_viols": 3,
                "viol_types": ["OMISSION", "SEQUENCE", "DEVIATION"],
            },
        }

    def _verdict(self, mock_episodes: dict, ep_id: str) -> bool:
        with patch(
            "audit.shims.violation_count_shim.load_w8_episodes",
            return_value=mock_episodes,
        ):
            return self.evaluator.verdict({"episode_id": ep_id})

    def test_clean_episode_passes(self, mock_episodes: dict) -> None:
        assert self._verdict(mock_episodes, "ep_clean") is True

    def test_one_soft_passes(self, mock_episodes: dict) -> None:
        # 1 soft = weighted 1.0 < 3.0 -> pass
        assert self._verdict(mock_episodes, "ep_one_soft") is True

    def test_two_soft_passes(self, mock_episodes: dict) -> None:
        # 2 soft = weighted 2.0 < 3.0 -> pass
        assert self._verdict(mock_episodes, "ep_two_soft") is True

    def test_one_hard_passes(self, mock_episodes: dict) -> None:
        # 1 hard = weighted 2.0 < 3.0 -> pass
        assert self._verdict(mock_episodes, "ep_one_hard") is True

    def test_two_hard_fails(self, mock_episodes: dict) -> None:
        # 2 hard = weighted 4.0 >= 3.0 -> fail
        assert self._verdict(mock_episodes, "ep_two_hard") is False

    def test_mixed_pass(self, mock_episodes: dict) -> None:
        # 1 hard(2.0) + 1 soft(1.0) = 3.0, NOT < 3.0 -> fail
        assert self._verdict(mock_episodes, "ep_mixed_pass") is False

    def test_mixed_fail(self, mock_episodes: dict) -> None:
        # 2 hard(4.0) + 1 soft(1.0) = 5.0 >= 3.0 -> fail
        assert self._verdict(mock_episodes, "ep_mixed_fail") is False

    def test_three_soft_fails(self, mock_episodes: dict) -> None:
        # 3 soft = weighted 3.0, NOT < 3.0 -> fail
        assert self._verdict(mock_episodes, "ep_three_soft") is False

    def test_unknown_episode_returns_false(self, mock_episodes: dict) -> None:
        assert self._verdict(mock_episodes, "nonexistent") is False

    def test_registry_contains_viol_count(self) -> None:
        from audit.shims import SHIM_REGISTRY

        assert "viol_count" in SHIM_REGISTRY
        assert SHIM_REGISTRY["viol_count"] is ViolationCountEvaluator
