"""Regression tests for Issue #2: ViolationExtractor final state omission check.

Verifies that the final omission check correctly uses the engine's advanced
node state, and that debug logging is present for troubleshooting.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from unittest.mock import MagicMock, patch

import pytest

from cga_bench.cpg_model.schemas.base import (
    Action, ActionType, PatientState, VitalSigns, EpisodeLog,
    GuidelineEngineOutput, HarmSeverity,
)
from cga_bench.assessor_core.violations import HarmSeverityMapping


# --- Fixtures ---

def _make_vitals() -> VitalSigns:
    return VitalSigns(
        heart_rate=80, blood_pressure_systolic=120,
        blood_pressure_diastolic=80, respiratory_rate=16,
        temperature=37.0, oxygen_saturation=98,
    )


def _make_patient(time: float = 0.0) -> PatientState:
    return PatientState(
        state_id="test", age=50, sex="M",
        vitals=_make_vitals(),
        chief_complaint="test",
        time_since_arrival_minutes=time,
    )


def _make_action(action_id: str, timestamp: float = 0.0) -> Action:
    return Action(
        type=ActionType.PROCEDURE,
        action_id=action_id,
        args={},
        timestamp_minutes=timestamp,
    )


def _make_episode(
    actions: List[Action],
    num_states: Optional[int] = None,
) -> EpisodeLog:
    """Create episode with proper state/action alignment."""
    if num_states is None:
        num_states = len(actions) + 1
    states = [_make_patient(time=i * 5.0) for i in range(num_states)]
    return EpisodeLog(
        episode_id="test_episode",
        scenario_id="test_scenario",
        agent_id="test_agent",
        states=states,
        actions=actions,
        observations=[{}] * num_states,
        total_duration_minutes=num_states * 5.0,
        total_llm_calls=0,
        total_tokens=0,
        total_tool_calls=len(actions),
        termination_reason="success",
    )


# --- Tests ---

class TestFinalStateOmissionLogging:
    """Tests that final omission check includes engine state debug logging."""

    def test_debug_log_emitted(self, caplog):
        """P6: Debug log shows engine node state at final omission check."""
        from cga_bench.assessor_core.violations import ViolationExtractor, ViolationExtractorConfig

        mock_engine = MagicMock()
        mock_engine.current_node_id = "sepsis_bundle"
        mock_engine.evaluate.return_value = GuidelineEngineOutput(
            current_node_id="sepsis_bundle",
            allowed_actions={"order_lab_lactate"},
            mandatory_actions=set(),
            forbidden_actions=set(),
        )
        mock_engine.advance_node.return_value = None

        config = ViolationExtractorConfig(
            harm_severity_mappings=[],
            timing_severity_thresholds=[],
            default_deviation_severity=HarmSeverity.MODERATE,
            default_deviation_preventability=0.5,
        )
        extractor = ViolationExtractor(mock_engine, config)

        episode = _make_episode(
            actions=[_make_action("order_lab_lactate", 5.0)],
        )

        with caplog.at_level(logging.DEBUG):
            extractor.extract_violations(episode)

        assert any(
            "Final omission check" in record.message
            for record in caplog.records
        ), "Debug log for final omission check should be present"

    def test_engine_node_state_in_log(self, caplog):
        """Log message includes engine's current node ID."""
        from cga_bench.assessor_core.violations import ViolationExtractor, ViolationExtractorConfig

        mock_engine = MagicMock()
        mock_engine.current_node_id = "resuscitation_node"
        mock_engine.evaluate.return_value = GuidelineEngineOutput(
            current_node_id="resuscitation_node",
            allowed_actions=set(),
            mandatory_actions=set(),
            forbidden_actions=set(),
        )
        mock_engine.advance_node.return_value = None

        config = ViolationExtractorConfig(
            harm_severity_mappings=[],
            timing_severity_thresholds=[],
            default_deviation_severity=HarmSeverity.MODERATE,
            default_deviation_preventability=0.5,
        )
        extractor = ViolationExtractor(mock_engine, config)

        episode = _make_episode(actions=[_make_action("give_fluids", 5.0)])

        with caplog.at_level(logging.DEBUG):
            extractor.extract_violations(episode)

        log_messages = " ".join(r.message for r in caplog.records)
        assert "resuscitation_node" in log_messages


class TestOmissionWithAdvancedEngine:
    """Tests that omission check uses engine state after all advances."""

    def test_no_false_positive_when_all_mandatory_done(self):
        """P6 영향도: mandatory actions 완료 시 omission violation 없음.

        After Issue #1 fix, engine advances correctly → no false positive omissions.
        """
        from cga_bench.assessor_core.violations import ViolationExtractor, ViolationExtractorConfig

        mock_engine = MagicMock()
        mock_engine.current_node_id = "final_node"
        mock_engine.evaluate.return_value = GuidelineEngineOutput(
            current_node_id="final_node",
            allowed_actions={"action_a"},
            mandatory_actions=set(),  # No mandatory at final node
            forbidden_actions=set(),
        )
        mock_engine.advance_node.return_value = None

        config = ViolationExtractorConfig(
            harm_severity_mappings=[],
            timing_severity_thresholds=[],
            default_deviation_severity=HarmSeverity.MODERATE,
            default_deviation_preventability=0.5,
        )
        extractor = ViolationExtractor(mock_engine, config)

        episode = _make_episode(actions=[_make_action("action_a", 5.0)])
        violations = extractor.extract_violations(episode)

        omissions = [v for v in violations if v.violation_type.value == "omission"]
        assert len(omissions) == 0

    def test_empty_episode_no_crash(self):
        """Empty action list should not crash the extractor.

        When episode ends past the deadline with no actions performed,
        omission should be detected.
        """
        from cga_bench.assessor_core.violations import ViolationExtractor, ViolationExtractorConfig

        mock_engine = MagicMock()
        mock_engine.current_node_id = "entry"
        mock_engine.evaluate.return_value = GuidelineEngineOutput(
            current_node_id="entry",
            allowed_actions=set(),
            mandatory_actions={"required_action"},
            forbidden_actions=set(),
            deadlines={"required_action": 60.0},
        )

        config = ViolationExtractorConfig(
            harm_severity_mappings=[
                HarmSeverityMapping(action_pattern="", severity=HarmSeverity.MAJOR),
            ],
            timing_severity_thresholds=[],
            default_deviation_severity=HarmSeverity.MODERATE,
            default_deviation_preventability=0.5,
        )
        extractor = ViolationExtractor(mock_engine, config)

        # Patient time (120 min) exceeds deadline (60 min) → omission detected
        states = [_make_patient(time=120.0)]
        episode = EpisodeLog(
            episode_id="test_episode",
            scenario_id="test_scenario",
            agent_id="test_agent",
            states=states,
            actions=[],
            observations=[{}],
            total_duration_minutes=120.0,
            total_llm_calls=0,
            total_tokens=0,
            total_tool_calls=0,
            termination_reason="timeout",
        )
        violations = extractor.extract_violations(episode)

        # Should detect omission for required_action (time 120 > deadline 60)
        omissions = [v for v in violations if v.violation_type.value == "omission"]
        assert len(omissions) >= 1

    def test_actions_count_in_log(self, caplog):
        """Log includes number of actions processed."""
        from cga_bench.assessor_core.violations import ViolationExtractor, ViolationExtractorConfig

        mock_engine = MagicMock()
        mock_engine.current_node_id = "node1"
        mock_engine.evaluate.return_value = GuidelineEngineOutput(
            current_node_id="node1",
            allowed_actions={"a", "b", "c"},
            mandatory_actions=set(),
            forbidden_actions=set(),
        )
        mock_engine.advance_node.return_value = None

        config = ViolationExtractorConfig(
            harm_severity_mappings=[],
            timing_severity_thresholds=[],
            default_deviation_severity=HarmSeverity.MODERATE,
            default_deviation_preventability=0.5,
        )
        extractor = ViolationExtractor(mock_engine, config)

        episode = _make_episode(actions=[
            _make_action("a", 5.0),
            _make_action("b", 10.0),
            _make_action("c", 15.0),
        ])

        with caplog.at_level(logging.DEBUG):
            extractor.extract_violations(episode)

        log_messages = " ".join(r.message for r in caplog.records)
        assert "3 actions" in log_messages
