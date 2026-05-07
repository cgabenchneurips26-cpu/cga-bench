"""Tests for EvaluationLoop (closed-loop CPG evaluation pipeline)."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from cga_bench.assessor_core.evaluation_loop import (
    EvaluationLoopResult,
    TimelineEntry,
    run_cpg_evaluation_loop,
    _states_equal,
)
from cga_bench.assessor_core.event_log import ActionEvent, EventLog
from cga_bench.cpg_engine.stepper import StepResult
from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    PatientState,
    VitalSigns,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_state(sid: str = "s0") -> PatientState:
    return PatientState(
        state_id=sid,
        age=50,
        sex="M",
        chief_complaint="test complaint",
        vitals=VitalSigns(
            heart_rate=80,
            blood_pressure_systolic=120,
            blood_pressure_diastolic=80,
        ),
    )


def _make_action(aid: str, t: float = 0.0) -> Action:
    return Action(
        type=ActionType.ORDER_LAB,
        action_id=aid,
        args={},
        timestamp_minutes=t,
    )


def _mock_cpg_engine():
    engine = MagicMock()
    engine.current_node_id = "root"
    # evaluate returns an object with mandatory_actions
    output = MagicMock()
    output.mandatory_actions = ["measure_lactate"]
    output.forbidden_actions = []
    output.allowed_actions = ["measure_lactate"]
    engine.evaluate.return_value = output
    return engine


def _mock_stepper_step_result(advanced: bool = False, node: str = "root"):
    return StepResult(
        advanced=advanced,
        new_node=node,
        new_obligations=[],
        completed_obligations=[],
        violations=[],
    )


# ============================================================================
# Basic Pipeline Execution
# ============================================================================

class TestBasicPipeline:
    def test_empty_actions_returns_empty_timeline(self):
        engine = _mock_cpg_engine()
        state = _make_state()
        result = run_cpg_evaluation_loop([], engine, state)
        assert isinstance(result, EvaluationLoopResult)
        assert len(result.timeline) == 0
        assert result.event_log.frozen is True

    def test_single_action_timeline(self):
        engine = _mock_cpg_engine()
        state = _make_state()
        actions = [_make_action("order_lab_lactate", t=5)]

        with patch("cga_bench.assessor_core.evaluation_loop.CPGStepper") as MockStepper:
            stepper_inst = MockStepper.return_value
            stepper_inst.current_node = "root"
            stepper_inst.step.return_value = _mock_stepper_step_result()
            result = run_cpg_evaluation_loop(actions, engine, state)

        assert len(result.timeline) == 1
        assert result.timeline[0].action_id == "order_lab_lactate"
        assert result.timeline[0].step == 0
        assert result.timeline[0].timestamp == 5.0

    def test_multiple_actions_timeline_order(self):
        engine = _mock_cpg_engine()
        state = _make_state()
        actions = [
            _make_action("measure_lactate", t=5),
            _make_action("blood_culture", t=10),
            _make_action("give_antibiotics", t=15),
        ]

        with patch("cga_bench.assessor_core.evaluation_loop.CPGStepper") as MockStepper:
            stepper_inst = MockStepper.return_value
            stepper_inst.current_node = "root"
            stepper_inst.step.return_value = _mock_stepper_step_result()
            result = run_cpg_evaluation_loop(actions, engine, state)

        assert len(result.timeline) == 3
        assert [e.action_id for e in result.timeline] == [
            "measure_lactate", "blood_culture", "give_antibiotics",
        ]


# ============================================================================
# Event Log
# ============================================================================

class TestEventLogIntegration:
    def test_event_log_frozen_after_run(self):
        engine = _mock_cpg_engine()
        state = _make_state()
        actions = [_make_action("action_1", t=0)]

        with patch("cga_bench.assessor_core.evaluation_loop.CPGStepper") as MockStepper:
            stepper_inst = MockStepper.return_value
            stepper_inst.current_node = "root"
            stepper_inst.step.return_value = _mock_stepper_step_result()
            result = run_cpg_evaluation_loop(actions, engine, state)

        assert result.event_log.frozen is True

    def test_event_log_contains_all_actions(self):
        engine = _mock_cpg_engine()
        state = _make_state()
        actions = [_make_action("a1", t=0), _make_action("a2", t=5)]

        with patch("cga_bench.assessor_core.evaluation_loop.CPGStepper") as MockStepper:
            stepper_inst = MockStepper.return_value
            stepper_inst.current_node = "root"
            stepper_inst.step.return_value = _mock_stepper_step_result()
            result = run_cpg_evaluation_loop(actions, engine, state)

        assert len(result.event_log) == 2
        keys = [e.canonical_key for e in result.event_log.events]
        assert keys == ["a1", "a2"]


# ============================================================================
# Normalizer Integration
# ============================================================================

class TestNormalizerIntegration:
    def test_normalizer_applied_to_action_id(self):
        engine = _mock_cpg_engine()
        state = _make_state()
        actions = [_make_action("raw_action", t=0)]

        normalizer = MagicMock()
        normalizer.normalize.return_value = "canonical_action"

        with patch("cga_bench.assessor_core.evaluation_loop.CPGStepper") as MockStepper:
            stepper_inst = MockStepper.return_value
            stepper_inst.current_node = "root"
            stepper_inst.step.return_value = _mock_stepper_step_result()
            result = run_cpg_evaluation_loop(
                actions, engine, state, normalizer=normalizer
            )

        normalizer.normalize.assert_called_once_with("raw_action")
        assert result.timeline[0].action_id == "canonical_action"

    def test_no_normalizer_uses_raw_id(self):
        engine = _mock_cpg_engine()
        state = _make_state()
        actions = [_make_action("original_id", t=0)]

        with patch("cga_bench.assessor_core.evaluation_loop.CPGStepper") as MockStepper:
            stepper_inst = MockStepper.return_value
            stepper_inst.current_node = "root"
            stepper_inst.step.return_value = _mock_stepper_step_result()
            result = run_cpg_evaluation_loop(actions, engine, state)

        assert result.timeline[0].action_id == "original_id"


# ============================================================================
# Replay Determinism
# ============================================================================

class TestReplayDeterminism:
    def test_replay_deterministic_flag_set(self):
        engine = _mock_cpg_engine()
        state = _make_state()
        actions = [_make_action("a1", t=0)]

        with patch("cga_bench.assessor_core.evaluation_loop.CPGStepper") as MockStepper:
            stepper_inst = MockStepper.return_value
            stepper_inst.current_node = "root"
            stepper_inst.step.return_value = _mock_stepper_step_result()
            result = run_cpg_evaluation_loop(actions, engine, state)

        assert isinstance(result.replay_deterministic, bool)


# ============================================================================
# _states_equal
# ============================================================================

class TestStatesEqual:
    def test_identical_states(self):
        s1 = _make_state()
        s2 = _make_state()
        assert _states_equal(s1, s2) is True

    def test_different_procedures(self):
        s1 = _make_state()
        s2 = _make_state()
        s1.procedures_done = ["cath_lab"]
        s2.procedures_done = []
        assert _states_equal(s1, s2) is False

    def test_different_medications(self):
        s1 = _make_state()
        s2 = _make_state()
        s1.medications_given = [{"medication_code": "aspirin"}]
        s2.medications_given = []
        assert _states_equal(s1, s2) is False


# ============================================================================
# Source Benchmark
# ============================================================================

class TestSourceBenchmark:
    def test_source_benchmark_passed_to_events(self):
        engine = _mock_cpg_engine()
        state = _make_state()
        actions = [_make_action("a1", t=0)]

        with patch("cga_bench.assessor_core.evaluation_loop.CPGStepper") as MockStepper:
            stepper_inst = MockStepper.return_value
            stepper_inst.current_node = "root"
            stepper_inst.step.return_value = _mock_stepper_step_result()
            result = run_cpg_evaluation_loop(
                actions, engine, state, source_benchmark="agentclinic"
            )

        assert result.event_log.events[0].source_benchmark == "agentclinic"
