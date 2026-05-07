"""
EvaluationLoop: Closed-loop CPG evaluation pipeline.

Orchestrates:
  1. ActionEvent creation → EventLog
  2. StateReducer → PatientState update
  3. CPGStepper → node advance + obligation tracking
  4. EventLog.freeze() → immutability
  5. Replay determinism verification
  6. Temporal constraint checking

Returns: EvaluationLoopResult
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from cga_bench.assessor_core.event_log import ActionEvent, CompletedActions, EventLog
from cga_bench.assessor_core.state_reducer import StateReducer
from cga_bench.cpg_engine.engine import CPGEngine
from cga_bench.cpg_engine.stepper import CPGStepper, StepResult
from cga_bench.cpg_engine.temporal_constraints import (
    ConstraintResult,
    TemporalConstraint,
    TemporalConstraintChecker,
)
from cga_bench.cpg_model.schemas.base import Action, ActionType, PatientState

logger = logging.getLogger(__name__)


@dataclass
class TimelineEntry:
    """Single entry in the evaluation timeline."""

    step: int
    action_id: str
    node_before: str
    node_after: str
    advanced: bool
    new_obligations: List[str]
    completed_obligations: List[str]
    violations: List[Dict]
    timestamp: float


@dataclass
class EvaluationLoopResult:
    """Result of a complete evaluation loop."""

    event_log: EventLog
    final_state: PatientState
    stepper: CPGStepper
    timeline: List[TimelineEntry]
    replay_deterministic: bool
    completed: CompletedActions
    temporal_results: List[ConstraintResult] = field(default_factory=list)


def run_cpg_evaluation_loop(
    agent_actions: List[Action],
    cpg_engine: CPGEngine,
    initial_state: PatientState,
    source_benchmark: str = "unknown",
    normalizer: Any = None,
    temporal_constraints: Optional[List[TemporalConstraint]] = None,
) -> EvaluationLoopResult:
    """Run the closed-loop CPG evaluation pipeline.

    Args:
        agent_actions: List of Action objects from the agent.
        cpg_engine: Initialized CPGEngine.
        initial_state: Starting PatientState.
        source_benchmark: Name of the benchmark source.
        normalizer: Optional ActionNormalizer.
        temporal_constraints: Optional list of TemporalConstraint to check.

    Returns:
        EvaluationLoopResult with event_log, final_state, stepper, timeline,
        replay_deterministic flag, and temporal constraint results.
    """
    event_log = EventLog()
    reducer = StateReducer()
    stepper = CPGStepper(cpg_engine)
    state = initial_state.model_copy(deep=True)
    timeline: List[TimelineEntry] = []

    for step_idx, action in enumerate(agent_actions):
        # Normalize action_id
        canonical = action.action_id
        if normalizer:
            canonical = normalizer.normalize(canonical)

        # Create event
        event = ActionEvent(
            step=step_idx,
            raw_action=action.action_id,
            canonical_key=canonical,
            timestamp=action.timestamp_minutes,
            source_benchmark=source_benchmark,
        )
        event_log.append(event)

        # Apply to state
        normalized_action = Action(
            type=action.type,
            action_id=canonical,
            args=action.args or {},
            timestamp_minutes=action.timestamp_minutes,
        )
        state = reducer.apply(state, normalized_action)

        # Step CPG
        node_before = stepper.current_node
        step_result = stepper.step(state, normalized_action)

        timeline.append(
            TimelineEntry(
                step=step_idx,
                action_id=canonical,
                node_before=node_before,
                node_after=step_result.new_node or node_before,
                advanced=step_result.advanced,
                new_obligations=step_result.new_obligations,
                completed_obligations=step_result.completed_obligations,
                violations=step_result.violations,
                timestamp=action.timestamp_minutes,
            )
        )

    # Freeze event log
    event_log.freeze()

    # Replay determinism check
    replay_state = event_log.replay(reducer, initial_state)
    replay_deterministic = _states_equal(state, replay_state)

    if not replay_deterministic:
        logger.warning("EvaluationLoop: REPLAY DETERMINISM FAILURE")

    # Temporal constraint checking
    temporal_results = []
    if temporal_constraints:
        trace = [
            (e.canonical_key, e.timestamp) for e in event_log.events
        ]
        checker = TemporalConstraintChecker()
        temporal_results = checker.check_all(temporal_constraints, trace)
        failed = [r for r in temporal_results if not r.satisfied]
        if failed:
            logger.warning(
                f"EvaluationLoop: {len(failed)}/{len(temporal_results)} "
                f"temporal constraints violated"
            )

    return EvaluationLoopResult(
        event_log=event_log,
        final_state=state,
        stepper=stepper,
        timeline=timeline,
        replay_deterministic=replay_deterministic,
        completed=event_log.completed,
        temporal_results=temporal_results,
    )


def _states_equal(s1: PatientState, s2: PatientState) -> bool:
    """Compare two PatientStates for equality (relevant fields)."""
    if set(getattr(lr, "test_code", "") for lr in s1.lab_results) != set(
        getattr(lr, "test_code", "") for lr in s2.lab_results
    ):
        return False

    if set(m.get("medication_code", "") for m in s1.medications_given) != set(
        m.get("medication_code", "") for m in s2.medications_given
    ):
        return False

    if set(s1.procedures_done) != set(s2.procedures_done):
        return False

    return True
