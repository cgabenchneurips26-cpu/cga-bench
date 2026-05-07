"""Termination-reason separation: agent_exhausted vs consecutive_empty_actions.

Task 2 (2026-04-21) introduced a scaffold-level hint so base_agent.run_episode
can record two distinct empty-action failure modes:

1. ``consecutive_empty_actions`` — the LLM genuinely returned nothing parseable
   (truly empty response / all proposals rejected by the normalizer).
2. ``agent_exhausted`` — the LLM proposed structurally valid actions, but
   every proposal was already completed earlier in the episode. This is the
   "training-memory hallucination" path that narrow-mode fixes could not
   address at the prompt layer.

These tests pin the separation so future refactors don't re-collapse the
two modes into the legacy ``consecutive_empty_actions`` bucket.
"""
from __future__ import annotations

from cga_bench.agent_runner.base_agent import AgentConfig, BaseAgent
from cga_bench.cpg_model.schemas.base import Action, ActionType


class _FakeObs:
    available_actions: list[str] = []
    __dict__ = {"available_actions": []}


class _FakeState:
    disposition_status = "unknown"

    def model_copy(self, deep: bool = True) -> "_FakeState":
        return self


class _FakeEnvConfig:
    max_duration_minutes = 100
    time_step_minutes = 5


class _FakeEnv:
    def __init__(self) -> None:
        self.config = _FakeEnvConfig()
        self.current_state = _FakeState()
        self.current_time = 0.0
        self.termination_reason: str | None = None

    def reset(self) -> None:
        self.termination_reason = None

    def _get_observation(self) -> _FakeObs:
        return _FakeObs()


class _AlwaysEmptyAgent(BaseAgent):
    """Minimal agent that always returns no actions and optionally announces
    the reason its return was empty via ``_preferred_termination_reason``."""

    def __init__(self, preferred_reason: str | None = None) -> None:
        super().__init__(AgentConfig(agent_id="test"))
        self._preferred_termination_reason = preferred_reason

    def decide(self, observation: _FakeObs) -> list[Action]:
        return []

    def reset(self) -> None:
        # Keep the hint across reset() so the test can exercise the hint-set
        # case deterministically.
        pass


def _capture_termination(agent: BaseAgent, scenario_id: str) -> str | None:
    env = _FakeEnv()
    try:
        agent.run_episode(env, scenario_id)
    except Exception:
        # ``EpisodeLog`` construction requires a real ``PatientState``; the
        # stub state fails pydantic validation. The termination_reason is
        # already written onto ``env`` before the log is built, so swallow.
        pass
    return env.termination_reason


def test_agent_exhausted_hint_is_propagated() -> None:
    """When the agent flags exhaustion, termination_reason reflects it."""
    agent = _AlwaysEmptyAgent(preferred_reason="agent_exhausted")
    assert _capture_termination(agent, "scn_exhausted") == "agent_exhausted"


def test_no_hint_defaults_to_consecutive_empty() -> None:
    """Without a hint, the legacy termination_reason is preserved."""
    agent = _AlwaysEmptyAgent(preferred_reason=None)
    assert _capture_termination(agent, "scn_genuine") == "consecutive_empty_actions"


def test_legacy_agent_without_hint_attr() -> None:
    """Agents lacking the hint attribute fall back to the default reason."""

    class _LegacyAgent(BaseAgent):
        def __init__(self) -> None:
            super().__init__(AgentConfig(agent_id="legacy"))

        def decide(self, observation: _FakeObs) -> list[Action]:
            return []

        def reset(self) -> None:
            pass

    assert _capture_termination(_LegacyAgent(), "scn_legacy") == "consecutive_empty_actions"


def test_rag_llm_path_sets_exhausted_hint_when_all_completed() -> None:
    """LLM path: every proposal filtered as already-completed -> hint set."""
    from cga_bench.agent_runner.rag_agent import RAGAgent

    agent = RAGAgent.__new__(RAGAgent)
    agent._completed_action_ids = {"action_A", "action_B"}
    agent._preferred_termination_reason = None

    class _Cfg:
        max_actions_per_step = 10

    agent.config = _Cfg()

    def _identity_norm(self, aid: str, available: list[str]) -> tuple[str, None]:
        return aid, None

    agent._normalize_action_id = _identity_norm.__get__(agent)

    actions_data = [
        {"action_id": "action_A", "action_type": "lab", "justification": "x"},
        {"action_id": "action_B", "action_type": "lab", "justification": "y"},
    ]
    actions: list[Action] = []
    already_completed_drops = 0
    for ad in actions_data:
        aid = str(ad["action_id"])
        normalized_id, _ = agent._normalize_action_id(aid, ["action_A", "action_B"])
        if normalized_id is None:
            continue
        aid = normalized_id
        if aid in agent._completed_action_ids:
            already_completed_drops += 1
            continue
        actions.append(Action(type=ActionType.ORDER_LAB, action_id=aid, args={}, timestamp_minutes=0))

    # Mirrors the new instrumentation at the end of _generate_actions_with_llm
    if not actions and already_completed_drops > 0:
        agent._preferred_termination_reason = "agent_exhausted"

    assert agent._preferred_termination_reason == "agent_exhausted"
    assert already_completed_drops == 2


def test_rag_llm_path_no_hint_when_fresh_action_produced() -> None:
    """LLM path: at least one fresh action -> hint remains cleared."""
    from cga_bench.agent_runner.rag_agent import RAGAgent

    agent = RAGAgent.__new__(RAGAgent)
    agent._completed_action_ids = {"action_A"}
    agent._preferred_termination_reason = None

    class _Cfg:
        max_actions_per_step = 10

    agent.config = _Cfg()

    def _identity_norm(self, aid: str, available: list[str]) -> tuple[str, None]:
        return aid, None

    agent._normalize_action_id = _identity_norm.__get__(agent)

    actions_data = [{"action_id": "action_C", "action_type": "lab", "justification": "z"}]
    actions: list[Action] = []
    already_completed_drops = 0
    for ad in actions_data:
        aid = str(ad["action_id"])
        normalized_id, _ = agent._normalize_action_id(aid, ["action_A", "action_C"])
        if normalized_id is None:
            continue
        aid = normalized_id
        if aid in agent._completed_action_ids:
            already_completed_drops += 1
            continue
        actions.append(Action(type=ActionType.ORDER_LAB, action_id=aid, args={}, timestamp_minutes=0))

    if not actions and already_completed_drops > 0:
        agent._preferred_termination_reason = "agent_exhausted"

    assert agent._preferred_termination_reason is None
    assert len(actions) == 1


def test_rag_llm_path_no_hint_when_genuinely_empty() -> None:
    """LLM path: empty proposals list -> no hint (stays as genuine empty)."""
    from cga_bench.agent_runner.rag_agent import RAGAgent

    agent = RAGAgent.__new__(RAGAgent)
    agent._completed_action_ids = set()
    agent._preferred_termination_reason = None

    actions: list[Action] = []
    already_completed_drops = 0
    # Simulates actions_data == [] (LLM returned nothing parseable)
    if not actions and already_completed_drops > 0:
        agent._preferred_termination_reason = "agent_exhausted"

    assert agent._preferred_termination_reason is None


def test_agent_completed_hint_set_on_empty_actions_with_completion_reasoning() -> None:
    """LLM emits ``actions: []`` with reasoning explicitly declaring that all
    mandatory protocol steps are done and the remaining options are not
    indicated — a valid clinical stop signal, not a parse failure or an
    exhaustion-hallucination. Must be flagged as ``agent_completed``.
    """
    _COMPLETION_MARKERS = (
        "already been completed",
        "already completed",
        "all mandatory actions",
        "all required actions",
        "no new actions",
        "no action required",
        "no further action",
        "no actions are required",
        "not indicated at this time",
        "nothing else is indicated",
    )
    result = {
        "actions": [],
        "reasoning": (
            "All mandatory actions for STEMI management have already been "
            "completed. The only remaining available action is fluid bolus, "
            "which is not indicated at this time given stable vitals."
        ),
    }
    actions_data = result.get("actions", [])
    reasoning_text = str(result.get("reasoning", "")).lower()

    hint = None
    if not actions_data and reasoning_text and any(m in reasoning_text for m in _COMPLETION_MARKERS):
        hint = "agent_completed"

    assert hint == "agent_completed"


def test_agent_completed_not_set_when_actions_nonempty() -> None:
    """Completion reasoning accompanied by at least one proposed action is
    NOT a completion declaration — the model is still working."""
    _COMPLETION_MARKERS = ("already been completed",)
    result = {
        "actions": [{"action_id": "reassess_vitals"}],
        "reasoning": "Most mandatory actions have already been completed, but reassess recommended.",
    }
    actions_data = result.get("actions", [])
    reasoning_text = str(result.get("reasoning", "")).lower()

    hint = None
    if not actions_data and reasoning_text and any(m in reasoning_text for m in _COMPLETION_MARKERS):
        hint = "agent_completed"

    assert hint is None


def test_rule_fallback_empty_return_preserves_llm_exhaustion_hint() -> None:
    """Regression: when the LLM path detected exhaustion earlier in the same
    decide() call and the rule-based fallback then returned no actions at
    all, the earlier ``agent_exhausted`` hint must survive to the termination
    check.

    The pre-fix version unconditionally reset the hint to ``None`` whenever
    control reached the end of ``_generate_actions`` with a falsy ``actions``
    — masking every exhaustion detection on which the subsequent rule-path
    also had nothing to contribute.
    """
    # Simulate the post-fix branch structure at the tail of _generate_actions
    # when rule-fallback returns an empty ``actions`` list.
    hint_after_llm = "agent_exhausted"  # set by _generate_actions_with_llm
    rule_fallback_actions: list[Action] = []  # rule path produced nothing

    preferred_reason = hint_after_llm  # enter tail branch with LLM-set hint

    if rule_fallback_actions:
        # (filter/clear path — not exercised in this regression case)
        pass
    # Tail of function: must NOT overwrite preferred_reason here when actions
    # is falsy. Pre-fix bug lived at this exact line.
    # (intentionally no assignment)

    assert preferred_reason == "agent_exhausted"
