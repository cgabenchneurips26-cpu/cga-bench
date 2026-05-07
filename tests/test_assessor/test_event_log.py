import pytest

from cga_bench.assessor_core.event_log import (
    ActionEvent,
    CompletedActions,
    EventLog,
    normalize_timestamp,
)

try:
    from dataclasses import FrozenInstanceError
except ImportError:
    FrozenInstanceError = AttributeError


class TestActionEventFrozen:
    def test_cannot_modify_timestamp(self):
        event = ActionEvent(
            step=0,
            raw_action="order_lab_lactate",
            canonical_key="order_lab_lactate",
            timestamp=10.0,
            source_benchmark="test",
        )
        with pytest.raises((AttributeError, FrozenInstanceError)):
            event.timestamp = 20.0

    def test_cannot_modify_action(self):
        event = ActionEvent(
            step=0,
            raw_action="order_lab_lactate",
            canonical_key="order_lab_lactate",
            timestamp=10.0,
            source_benchmark="test",
        )
        with pytest.raises((AttributeError, FrozenInstanceError)):
            event.canonical_key = "different"


class TestEventLogSortStability:
    def test_stable_sort_same_timestamp(self):
        log = EventLog()
        events = [
            ActionEvent(
                step=0,
                raw_action="a",
                canonical_key="action_a",
                timestamp=5.0,
                source_benchmark="test",
            ),
            ActionEvent(
                step=1,
                raw_action="b",
                canonical_key="action_b",
                timestamp=5.0,
                source_benchmark="test",
            ),
            ActionEvent(
                step=2,
                raw_action="c",
                canonical_key="action_c",
                timestamp=5.0,
                source_benchmark="test",
            ),
        ]
        for event in events:
            log.append(event)

        sorted_events = log.sorted_events
        assert [event.canonical_key for event in sorted_events] == [
            "action_a",
            "action_b",
            "action_c",
        ]

    def test_sort_by_timestamp(self):
        log = EventLog()
        log.append(
            ActionEvent(
                step=0,
                raw_action="late",
                canonical_key="late",
                timestamp=30.0,
                source_benchmark="test",
            )
        )
        log.append(
            ActionEvent(
                step=1,
                raw_action="early",
                canonical_key="early",
                timestamp=10.0,
                source_benchmark="test",
            )
        )
        log.append(
            ActionEvent(
                step=2,
                raw_action="mid",
                canonical_key="mid",
                timestamp=20.0,
                source_benchmark="test",
            )
        )

        sorted_events = log.sorted_events
        assert [event.canonical_key for event in sorted_events] == ["early", "mid", "late"]


class TestNormalizeTimestamp:
    def test_seconds_passthrough(self):
        assert normalize_timestamp(60.0, "seconds") == 60.0

    def test_minutes_to_seconds(self):
        assert normalize_timestamp(5.0, "minutes") == 300.0

    def test_zero(self):
        assert normalize_timestamp(0.0, "minutes") == 0.0

    def test_default_unit_is_seconds(self):
        assert normalize_timestamp(42.0) == 42.0


class TestEventLogFreeze:
    def test_append_after_freeze_raises(self):
        log = EventLog()
        log.freeze()
        event = ActionEvent(
            step=0,
            raw_action="x",
            canonical_key="x",
            timestamp=0.0,
            source_benchmark="test",
        )
        with pytest.raises(RuntimeError):
            log.append(event)

    def test_events_are_tuple(self):
        log = EventLog()
        assert isinstance(log.events, tuple)


class TestCompletedActions:
    def test_completed_actions_instantiation(self):
        completed = CompletedActions()
        assert completed.all_keys == set()
