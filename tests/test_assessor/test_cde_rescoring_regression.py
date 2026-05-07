"""CDE-rescoring backward-compat regression guard (B-cde-rescoring v1.1).

When `derived_constraints=None` is passed (or omitted) to extract_violations,
the output MUST be byte-identical to the legacy behaviour. This is the
foundation for the per-episode additivity assertion in the re-scoring driver.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cga_bench.assessor_core.violations import (
    HarmSeverityMapping,
    TimingSeverityThreshold,
    ViolationExtractor,
    ViolationExtractorConfig,
)
from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    EpisodeLog,
    HarmSeverity,
    PatientState,
    VitalSigns,
)


def _sepsis_graph() -> str:
    return str(
        Path(__file__).parent.parent.parent
        / "cpg_model"
        / "graphs"
        / "ssc_sepsis_hour1_bundle.yaml"
    )


@pytest.fixture
def config() -> ViolationExtractorConfig:
    return ViolationExtractorConfig(
        harm_severity_mappings=[
            HarmSeverityMapping(action_pattern="lactate", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="blood_culture", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="antibiotics", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="crystalloid", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="vasopressor", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="", severity=HarmSeverity.MODERATE),
        ],
        timing_severity_thresholds=[
            TimingSeverityThreshold(max_delay_minutes=15, severity=HarmSeverity.MODERATE),
            TimingSeverityThreshold(max_delay_minutes=30, severity=HarmSeverity.MAJOR),
            TimingSeverityThreshold(max_delay_minutes=60, severity=HarmSeverity.SEVERE),
        ],
        default_deviation_severity=HarmSeverity.MINOR,
        default_deviation_preventability=0.5,
    )


def _make_state(t: float, sid: str) -> PatientState:
    return PatientState(
        state_id=sid,
        time_since_arrival_minutes=t,
        age=65,
        sex="M",
        weight_kg=70,
        vitals=VitalSigns(
            heart_rate=120,
            blood_pressure_systolic=85,
            blood_pressure_diastolic=50,
            respiratory_rate=24,
            temperature=38.9,
            oxygen_saturation=92,
            map_mmhg=62,
        ),
        chief_complaint="fever",
        working_diagnosis="septic_shock",
    )


def _action(aid: str, t: float) -> Action:
    return Action(type=ActionType.PROCEDURE, action_id=aid, args={}, timestamp_minutes=t)


def _episode() -> EpisodeLog:
    actions = [
        _action("order_lab_lactate", 5),
        _action("order_lab_blood_culture", 10),
        _action("give_broad_spectrum_antibiotics", 15),
        _action("give_crystalloid_30ml_kg", 25),
    ]
    states = [_make_state(0, "s0")]
    for i, a in enumerate(actions, 1):
        states.append(_make_state(a.timestamp_minutes, f"s{i}"))
    return EpisodeLog(
        episode_id="reg",
        scenario_id="septic_shock",
        agent_id="test",
        states=states,
        actions=actions,
        observations=[{}],
        total_duration_minutes=60,
        total_llm_calls=0,
        total_tokens=0,
        total_tool_calls=0,
        termination_reason="timeout",
    )


def _violation_signature(v) -> tuple:
    return (
        v.violation_type,
        v.action_involved,
        v.expected_action,
        v.timestamp_minutes,
        v.harm_severity,
    )


def test_extract_violations_byte_identical_when_derived_none(config) -> None:
    """`derived_constraints=None` (default) must produce same violations as
    legacy 2-arg call signature."""
    episode = _episode()

    engine = CPGEngineFactory.load_from_file(_sepsis_graph())
    engine.current_node_id = "septic_shock_bundle"
    legacy = ViolationExtractor(engine, config).extract_violations(episode)

    engine2 = CPGEngineFactory.load_from_file(_sepsis_graph())
    engine2.current_node_id = "septic_shock_bundle"
    new = ViolationExtractor(engine2, config).extract_violations(
        episode, derived_constraints=None
    )

    assert len(legacy) == len(new)
    legacy_sigs = sorted(_violation_signature(v) for v in legacy)
    new_sigs = sorted(_violation_signature(v) for v in new)
    assert legacy_sigs == new_sigs


def test_extract_violations_default_omits_source_field(config) -> None:
    """Legacy code path should leave `source` as None (only CDE path tags 'cde')."""
    episode = _episode()
    engine = CPGEngineFactory.load_from_file(_sepsis_graph())
    engine.current_node_id = "septic_shock_bundle"
    violations = ViolationExtractor(engine, config).extract_violations(episode)

    for v in violations:
        assert v.source is None
        assert v.conflict_provenance is None
