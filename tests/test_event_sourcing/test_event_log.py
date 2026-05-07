"""Tests for EventLog: append-only, freeze, replay determinism, CompletedActions."""

import pytest

from cga_bench.assessor_core.event_log import ActionEvent, CompletedActions, EventLog
from cga_bench.assessor_core.state_reducer import StateReducer
from cga_bench.cpg_model.schemas.base import (
    Action, ActionType, PatientState, VitalSigns
)


def _make_event(step: int, key: str, ts: float = 0.0) -> ActionEvent:
    return ActionEvent(
        step=step,
        raw_action=key,
        canonical_key=key,
        timestamp=ts,
        source_benchmark="test",
    )


def _make_initial_state() -> PatientState:
    return PatientState(
        state_id="test_0",
        age=65,
        sex="male",
        chief_complaint="fever",
        vitals=VitalSigns(
            heart_rate=110.0,
            systolic_bp=90.0,
            diastolic_bp=60.0,
            temperature=38.9,
            respiratory_rate=22.0,
            spo2=94.0,
        ),
    )


class TestEventLogAppendFreeze:
    """EventLog append-only and freeze semantics."""

    def test_append_event(self):
        log = EventLog()
        e = _make_event(0, "assess_vital_signs")
        log.append(e)
        assert len(log) == 1
        assert log.events[0] is e

    def test_multiple_append(self):
        log = EventLog()
        log.append(_make_event(0, "a"))
        log.append(_make_event(1, "b"))
        assert len(log) == 2

    def test_freeze_prevents_append(self):
        log = EventLog()
        log.append(_make_event(0, "a"))
        log.freeze()
        assert log.frozen is True
        with pytest.raises(RuntimeError, match="frozen"):
            log.append(_make_event(1, "b"))

    def test_events_returns_tuple(self):
        log = EventLog()
        log.append(_make_event(0, "a"))
        events = log.events
        assert isinstance(events, tuple)

    def test_empty_log(self):
        log = EventLog()
        assert len(log) == 0
        assert log.events == ()
        assert log.frozen is False


class TestCompletedActionsTracking:
    """CompletedActions index tracking."""

    def test_lab_order_classified(self):
        log = EventLog()
        log.append(_make_event(0, "order_lab_lactate"))
        assert "order_lab_lactate" in log.completed.ordered

    def test_medication_classified(self):
        log = EventLog()
        log.append(_make_event(0, "give_broad_spectrum_antibiotics"))
        assert "give_broad_spectrum_antibiotics" in log.completed.administered

    def test_procedure_classified(self):
        log = EventLog()
        log.append(_make_event(0, "assess_vital_signs"))
        assert "assess_vital_signs" in log.completed.performed

    def test_all_keys_union(self):
        log = EventLog()
        log.append(_make_event(0, "order_lab_lactate"))
        log.append(_make_event(1, "give_aspirin_loading"))
        log.append(_make_event(2, "assess_vital_signs"))
        all_keys = log.completed.all_keys
        assert "order_lab_lactate" in all_keys
        assert "give_aspirin_loading" in all_keys
        assert "assess_vital_signs" in all_keys

    def test_completed_actions_default(self):
        ca = CompletedActions()
        assert len(ca.ordered) == 0
        assert len(ca.administered) == 0
        assert len(ca.performed) == 0
        assert len(ca.resulted) == 0


class TestReplayDeterminism:
    """E2: Replay determinism — online == replay."""

    def test_replay_determinism_online_equals_replay(self):
        """Online state changes must match replayed state changes."""
        log = EventLog()
        reducer = StateReducer()
        initial = _make_initial_state()
        state = initial.model_copy(deep=True)

        # Build events online
        actions = [
            ("order_lab_lactate", 1.0),
            ("order_lab_blood_culture", 2.0),
            ("give_broad_spectrum_antibiotics", 5.0),
            ("assess_vital_signs", 0.0),
            ("reassess_perfusion", 10.0),
        ]
        for i, (key, ts) in enumerate(actions):
            event = _make_event(i, key, ts)
            log.append(event)
            action = Action(
                type=ActionType.PROCEDURE,
                action_id=key,
                args={},
                timestamp_minutes=ts,
            )
            state = reducer.apply(state, action)

        log.freeze()

        # Replay
        replay_state = log.replay(reducer, initial)

        # Compare
        online_labs = {getattr(lr, "test_code", "") for lr in state.lab_results}
        replay_labs = {getattr(lr, "test_code", "") for lr in replay_state.lab_results}
        assert online_labs == replay_labs

        online_meds = {m.get("medication_code", "") for m in state.medications_given}
        replay_meds = {m.get("medication_code", "") for m in replay_state.medications_given}
        assert online_meds == replay_meds

        online_procs = set(state.procedures_done)
        replay_procs = set(replay_state.procedures_done)
        assert online_procs == replay_procs

    def test_replay_empty_log(self):
        """Replaying empty log returns identical initial state."""
        log = EventLog()
        log.freeze()
        reducer = StateReducer()
        initial = _make_initial_state()
        result = log.replay(reducer, initial)
        assert set(result.procedures_done) == set(initial.procedures_done)

    def test_replay_preserves_initial(self):
        """Initial state is not modified by replay."""
        log = EventLog()
        log.append(_make_event(0, "order_lab_lactate", 1.0))
        log.freeze()
        reducer = StateReducer()
        initial = _make_initial_state()
        _ = log.replay(reducer, initial)
        # initial should be unchanged
        assert len(initial.lab_results) == 0


class TestActionEventImmutability:
    """ActionEvent frozen dataclass."""

    def test_frozen(self):
        e = _make_event(0, "test")
        with pytest.raises(AttributeError):
            e.step = 5
