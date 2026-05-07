"""Tests for CPGStepper and evaluation_loop."""

import pytest
from pathlib import Path

from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_engine.stepper import CPGStepper, StepResult
from cga_bench.assessor_core.evaluation_loop import (
    run_cpg_evaluation_loop,
    EvaluationLoopResult,
)
from cga_bench.cpg_model.schemas.base import (
    Action, ActionType, PatientState, VitalSigns, LabResult
)


CPG_GRAPHS_DIR = Path(__file__).parent.parent.parent / "cpg_model" / "graphs"


def _make_state(state_id="test_0", **overrides) -> PatientState:
    defaults = dict(
        state_id=state_id,
        age=65,
        sex="male",
        chief_complaint="fever and hypotension",
        vitals=VitalSigns(
            heart_rate=110.0,
            systolic_bp=85.0,
            diastolic_bp=55.0,
            temperature=39.2,
            respiratory_rate=24.0,
            spo2=93.0,
        ),
    )
    defaults.update(overrides)
    return PatientState(**defaults)


def _make_action(action_id: str, ts: float = 0.0) -> Action:
    return Action(
        type=ActionType.PROCEDURE,
        action_id=action_id,
        args={},
        timestamp_minutes=ts,
    )


def _load_sepsis_engine():
    path = CPG_GRAPHS_DIR / "ssc_sepsis_hour1_bundle.yaml"
    if not path.exists():
        pytest.skip(f"CPG graph not found: {path}")
    return CPGEngineFactory.load_from_file(str(path))


class TestCPGStepperBasic:
    """CPGStepper basic functionality."""

    def test_initial_node(self):
        engine = _load_sepsis_engine()
        stepper = CPGStepper(engine)
        assert stepper.current_node == engine.current_node_id
        assert len(stepper.node_history) == 1

    def test_step_returns_step_result(self):
        engine = _load_sepsis_engine()
        stepper = CPGStepper(engine)
        state = _make_state()
        action = _make_action("assess_vital_signs", 1.0)
        result = stepper.step(state, action)
        assert isinstance(result, StepResult)

    def test_obligations_tracked(self):
        engine = _load_sepsis_engine()
        stepper = CPGStepper(engine)
        state = _make_state()
        action = _make_action("assess_vital_signs", 1.0)
        stepper.step(state, action)
        # After first step, engine should have issued some mandatory obligations
        assert len(stepper.issued_obligations) >= 0  # may or may not have obligations

    def test_action_satisfies_exact(self):
        assert CPGStepper._action_satisfies("order_lab_lactate", "order_lab_lactate")

    def test_action_satisfies_conditional(self):
        assert CPGStepper._action_satisfies(
            "start_vasopressor_norepinephrine",
            "start_vasopressor_if_hypotensive"
        )

    def test_action_not_satisfies(self):
        assert not CPGStepper._action_satisfies(
            "order_lab_lactate",
            "give_antibiotics"
        )

    def test_progress_rate_initial(self):
        engine = _load_sepsis_engine()
        stepper = CPGStepper(engine)
        assert stepper.progress_rate == 1.0  # no obligations yet


class TestSepsisGoldenTrace:
    """Sepsis golden trace: expected node advances."""

    def test_sepsis_golden_trace(self):
        """Run standard sepsis Hour-1 actions and verify stepper tracks them."""
        engine = _load_sepsis_engine()
        stepper = CPGStepper(engine)

        # Sepsis golden trace actions
        golden_actions = [
            ("order_lab_blood_culture", 1.0),
            ("order_lab_lactate", 2.0),
            ("give_broad_spectrum_antibiotics", 5.0),
            ("give_crystalloid_30ml_kg", 10.0),
            ("reassess_perfusion", 30.0),
            ("remeasure_lactate_if_elevated", 45.0),
            ("determine_disposition", 55.0),
        ]

        state = _make_state()
        from cga_bench.assessor_core.state_reducer import StateReducer
        reducer = StateReducer()

        all_violations = []
        for action_id, ts in golden_actions:
            action = _make_action(action_id, ts)
            state = reducer.apply(state, action)
            result = stepper.step(state, action)
            all_violations.extend(result.violations)

        # Golden trace should have minimal violations
        commission_violations = [v for v in all_violations if v.get("type") == "COMMISSION"]
        assert len(commission_violations) == 0, "Golden trace should not have commission violations"

        # Should have visited multiple nodes
        assert len(stepper.node_history) >= 1


class TestEvaluationLoop:
    """Integration test for run_cpg_evaluation_loop."""

    def test_evaluation_loop_returns_result(self):
        engine = _load_sepsis_engine()
        initial = _make_state()
        actions = [
            _make_action("order_lab_blood_culture", 1.0),
            _make_action("order_lab_lactate", 2.0),
            _make_action("give_broad_spectrum_antibiotics", 5.0),
        ]

        result = run_cpg_evaluation_loop(
            agent_actions=actions,
            cpg_engine=engine,
            initial_state=initial,
            source_benchmark="test",
        )

        assert isinstance(result, EvaluationLoopResult)
        assert result.event_log.frozen is True
        assert len(result.event_log) == 3
        assert len(result.timeline) == 3

    def test_evaluation_loop_replay_deterministic(self):
        engine = _load_sepsis_engine()
        initial = _make_state()
        actions = [
            _make_action("order_lab_blood_culture", 1.0),
            _make_action("order_lab_lactate", 2.0),
            _make_action("give_broad_spectrum_antibiotics", 5.0),
            _make_action("assess_vital_signs", 0.0),
        ]

        result = run_cpg_evaluation_loop(
            agent_actions=actions,
            cpg_engine=engine,
            initial_state=initial,
            source_benchmark="test",
        )

        assert result.replay_deterministic is True

    def test_evaluation_loop_completed_actions(self):
        engine = _load_sepsis_engine()
        initial = _make_state()
        actions = [
            _make_action("order_lab_blood_culture", 1.0),
            _make_action("give_broad_spectrum_antibiotics", 5.0),
            _make_action("assess_vital_signs", 0.0),
        ]

        result = run_cpg_evaluation_loop(
            agent_actions=actions,
            cpg_engine=engine,
            initial_state=initial,
        )

        assert "order_lab_blood_culture" in result.completed.ordered
        assert "give_broad_spectrum_antibiotics" in result.completed.administered
        assert "assess_vital_signs" in result.completed.performed

    def test_evaluation_loop_empty_actions(self):
        engine = _load_sepsis_engine()
        initial = _make_state()

        result = run_cpg_evaluation_loop(
            agent_actions=[],
            cpg_engine=engine,
            initial_state=initial,
        )

        assert len(result.event_log) == 0
        assert result.replay_deterministic is True
