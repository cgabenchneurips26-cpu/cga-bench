"""Tests for CGA_DEBUG_RAW_RESPONSE capture paths in RAGAgent.

Covers two distinct empty-actions paths:
  - path="llm_rejected":   LLM returns nothing, normalizer rejects → line ~796
  - path="rule_fallback":  rule-based fallback returns only already-completed
                           actions → line ~833
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cga_bench.agent_runner.llm_provider import LLMBackend
from cga_bench.agent_runner.rag_agent import RAGAgent, RAGConfig
from cga_bench.cpg_model.schemas.base import Action, ActionType
from cga_bench.scenario_engine.environment import Observation

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _make_observation(available_actions: list[str] | None = None) -> Observation:
    return Observation(
        timestamp_minutes=0.0,
        visible_state={
            "vitals": {
                "heart_rate": 100,
                "blood_pressure_systolic": 90,
                "blood_pressure_diastolic": 60,
                "map_mmhg": 70,
                "respiratory_rate": 18,
                "temperature": 37.0,
                "oxygen_saturation": 98,
            },
            "chief_complaint": "sepsis test",
        },
        new_results=[],
        alerts=[],
        available_actions=available_actions or ["order_lab_blood_culture"],
        mandatory_actions=[],
    )


def _make_action(action_id: str) -> Action:
    return Action(
        type=ActionType.ORDER_LAB,
        action_id=action_id,
        args={},
        timestamp_minutes=0.0,
        justification="test",
    )


@pytest.fixture()
def rag_agent_no_llm(tmp_path: Path) -> RAGAgent:
    """RAGAgent with use_llm=False (pure rule-based path)."""
    config = RAGConfig(
        agent_id="test_rag",
        use_llm=False,
        cpg_sources_path=None,
        llm_backend=LLMBackend.MOCK,
        llm_model="mock",
    )
    agent = RAGAgent(config)
    return agent


@pytest.fixture()
def rag_agent_mock_llm() -> RAGAgent:
    """RAGAgent with a mock LLM provider injected."""
    config = RAGConfig(
        agent_id="test_rag_llm",
        use_llm=True,
        cpg_sources_path=None,
        llm_backend=LLMBackend.MOCK,
        llm_model="mock",
    )
    mock_provider = MagicMock()
    mock_provider.get_total_tokens_from_last_call.return_value = 0
    mock_provider._last_raw_content = "raw LLM content for testing"
    agent = RAGAgent(config, llm_provider=mock_provider)
    return agent


# ---------------------------------------------------------------------------
# Path 1: llm_rejected
# ---------------------------------------------------------------------------


class TestLLMRejectedCapture:
    """Path 1: LLM returns empty list → captured with path='llm_rejected'."""

    def test_no_capture_without_env_var(self, rag_agent_mock_llm: RAGAgent) -> None:
        """Without CGA_DEBUG_RAW_RESPONSE, no samples are captured."""
        agent = rag_agent_mock_llm
        # LLM always returns empty
        agent.llm_provider.generate_actions = MagicMock(return_value=[])  # type: ignore[union-attr]

        with patch.object(agent, "_generate_actions_with_llm", return_value=[]):
            with patch.object(agent, "_generate_actions_rule_based", return_value=[]):
                obs = _make_observation()
                env_without = {k: v for k, v in os.environ.items() if k != "CGA_DEBUG_RAW_RESPONSE"}
                with patch.dict(os.environ, env_without, clear=True):
                    agent.decide(obs)

        assert agent._empty_raw_samples == []

    def test_capture_with_env_var(self, rag_agent_mock_llm: RAGAgent) -> None:
        """With CGA_DEBUG_RAW_RESPONSE=1, llm-rejected path populates samples."""
        agent = rag_agent_mock_llm
        agent.llm_provider._last_raw_content = "the model said nothing useful"  # type: ignore[union-attr]

        with patch.object(agent, "_generate_actions_with_llm", return_value=[]):
            with patch.object(agent, "_generate_actions_rule_based", return_value=[]):
                obs = _make_observation()
                with patch.dict(os.environ, {"CGA_DEBUG_RAW_RESPONSE": "1"}):
                    agent.decide(obs)

        assert len(agent._empty_raw_samples) >= 1
        sample = agent._empty_raw_samples[0]
        assert sample["path"] == "llm_rejected"
        assert "llm_call_index" in sample
        assert "attempt" in sample
        assert "raw_preview" in sample
        assert "raw_len" in sample

    def test_capture_path_tag_is_llm_rejected(self, rag_agent_mock_llm: RAGAgent) -> None:
        """Captured sample must have path='llm_rejected', not 'rule_fallback'."""
        agent = rag_agent_mock_llm

        with patch.object(agent, "_generate_actions_with_llm", return_value=[]):
            with patch.object(agent, "_generate_actions_rule_based", return_value=[]):
                obs = _make_observation()
                with patch.dict(os.environ, {"CGA_DEBUG_RAW_RESPONSE": "1"}):
                    agent.decide(obs)

        paths = {s["path"] for s in agent._empty_raw_samples}
        assert "llm_rejected" in paths
        assert "rule_fallback" not in paths


# ---------------------------------------------------------------------------
# Path 2: rule_fallback
# ---------------------------------------------------------------------------


class TestRuleFallbackCapture:
    """Path 2: rule-based returns only already-completed actions → 'rule_fallback'."""

    def test_no_capture_without_env_var(self, rag_agent_no_llm: RAGAgent) -> None:
        """Without CGA_DEBUG_RAW_RESPONSE, rule_fallback path produces no samples."""
        agent = rag_agent_no_llm
        already_done = _make_action("order_lab_blood_culture")
        agent._completed_action_ids.add("order_lab_blood_culture")

        with patch.object(agent, "_generate_actions_rule_based", return_value=[already_done]):
            obs = _make_observation()
            env_without = {k: v for k, v in os.environ.items() if k != "CGA_DEBUG_RAW_RESPONSE"}
            with patch.dict(os.environ, env_without, clear=True):
                agent.decide(obs)

        assert agent._empty_raw_samples == []

    def test_capture_with_env_var(self, rag_agent_no_llm: RAGAgent) -> None:
        """With CGA_DEBUG_RAW_RESPONSE=1, rule_fallback path is captured."""
        agent = rag_agent_no_llm
        already_done = _make_action("order_lab_blood_culture")
        agent._completed_action_ids.add("order_lab_blood_culture")

        with patch.object(agent, "_generate_actions_rule_based", return_value=[already_done]):
            obs = _make_observation()
            with patch.dict(os.environ, {"CGA_DEBUG_RAW_RESPONSE": "1"}):
                agent.decide(obs)

        assert len(agent._empty_raw_samples) >= 1
        sample = agent._empty_raw_samples[0]
        assert sample["path"] == "rule_fallback"
        assert sample["source"] == "rule_fallback_already_completed"
        assert "order_lab_blood_culture" in sample["fallback_input"]
        assert "llm_attempted" in sample
        assert "last_llm_raw" in sample

    def test_capture_path_tag_is_rule_fallback(self, rag_agent_no_llm: RAGAgent) -> None:
        """Captured sample must have path='rule_fallback', not 'llm_rejected'."""
        agent = rag_agent_no_llm
        already_done = _make_action("order_lab_blood_culture")
        agent._completed_action_ids.add("order_lab_blood_culture")

        with patch.object(agent, "_generate_actions_rule_based", return_value=[already_done]):
            obs = _make_observation()
            with patch.dict(os.environ, {"CGA_DEBUG_RAW_RESPONSE": "1"}):
                agent.decide(obs)

        paths = {s["path"] for s in agent._empty_raw_samples}
        assert "rule_fallback" in paths
        assert "llm_rejected" not in paths

    def test_fallback_input_contains_completed_ids(self, rag_agent_no_llm: RAGAgent) -> None:
        """fallback_input field lists the action IDs the rule returned."""
        agent = rag_agent_no_llm
        actions = [_make_action("act_a"), _make_action("act_b")]
        agent._completed_action_ids.update({"act_a", "act_b"})

        with patch.object(agent, "_generate_actions_rule_based", return_value=actions):
            obs = _make_observation()
            with patch.dict(os.environ, {"CGA_DEBUG_RAW_RESPONSE": "1"}):
                agent.decide(obs)

        sample = agent._empty_raw_samples[0]
        assert set(sample["fallback_input"]) == {"act_a", "act_b"}


# ---------------------------------------------------------------------------
# Reset clears samples between episodes
# ---------------------------------------------------------------------------


class TestResetClearsSamples:
    def test_reset_clears_both_paths(self, rag_agent_no_llm: RAGAgent) -> None:
        """reset() must wipe _empty_raw_samples between episodes."""
        agent = rag_agent_no_llm
        already_done = _make_action("order_lab_blood_culture")
        agent._completed_action_ids.add("order_lab_blood_culture")

        with patch.object(agent, "_generate_actions_rule_based", return_value=[already_done]):
            obs = _make_observation()
            with patch.dict(os.environ, {"CGA_DEBUG_RAW_RESPONSE": "1"}):
                agent.decide(obs)

        assert len(agent._empty_raw_samples) >= 1
        agent.reset()
        assert agent._empty_raw_samples == []
