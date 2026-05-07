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
    ViolationType,
    VitalSigns,
)


def get_sepsis_graph_path() -> str:
    return str(Path(__file__).parent.parent.parent / "cpg_model" / "graphs" / "ssc_sepsis_hour1_bundle.yaml")


@pytest.fixture
def violation_extractor_config() -> ViolationExtractorConfig:
    return ViolationExtractorConfig(
        harm_severity_mappings=[
            HarmSeverityMapping(action_pattern="lactate", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="blood_culture", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="antibiotics", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="crystalloid", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="vasopressor", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="discharge", severity=HarmSeverity.CATASTROPHIC),
            HarmSeverityMapping(action_pattern="delay", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="withhold", severity=HarmSeverity.SEVERE),
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


def _make_state(time_since_arrival_minutes: float, state_id: str) -> PatientState:
    return PatientState(
        state_id=state_id,
        time_since_arrival_minutes=time_since_arrival_minutes,
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
        chief_complaint="fever, altered mental status",
        working_diagnosis="septic_shock",
    )


def _action(action_id: str, timestamp_minutes: float, action_type: ActionType = ActionType.PROCEDURE) -> Action:
    return Action(
        type=action_type,
        action_id=action_id,
        args={},
        timestamp_minutes=timestamp_minutes,
    )


def _build_episode(episode_id: str, actions: list[Action], final_time: float) -> EpisodeLog:
    states = [_make_state(0, f"{episode_id}_s0")]
    for i, action in enumerate(actions, start=1):
        states.append(_make_state(action.timestamp_minutes, f"{episode_id}_s{i}"))
    states.append(_make_state(final_time, f"{episode_id}_sf"))

    return EpisodeLog(
        episode_id=episode_id,
        scenario_id="septic_shock",
        agent_id="test",
        states=states,
        actions=actions,
        observations=[{}],
        total_duration_minutes=final_time,
        total_llm_calls=0,
        total_tokens=0,
        total_tool_calls=0,
        termination_reason="timeout",
    )


def _extract(episode: EpisodeLog, config: ViolationExtractorConfig):
    engine = CPGEngineFactory.load_from_file(get_sepsis_graph_path())
    engine.current_node_id = "septic_shock_bundle"
    extractor = ViolationExtractor(engine, config)
    return extractor.extract_violations(episode)


def test_omission_missing_lactate_only(violation_extractor_config: ViolationExtractorConfig):
    actions = [
        _action("order_lab_blood_culture", 10),
        _action("give_broad_spectrum_antibiotics", 20),
        _action("give_crystalloid_30ml_kg", 30),
        _action("start_vasopressor_norepinephrine", 40),
    ]
    episode = _build_episode("omission_case", actions, final_time=120)

    violations = _extract(episode, violation_extractor_config)

    omission_violations = [v for v in violations if v.violation_type == ViolationType.OMISSION]
    assert len(omission_violations) == 1
    assert omission_violations[0].expected_action == "order_lab_lactate"


def test_commission_discharge_home_forbidden(violation_extractor_config: ViolationExtractorConfig):
    episode = _build_episode(
        "commission_case",
        [_action("discharge_home", 30, action_type=ActionType.DISPOSITION)],
        final_time=30,
    )

    violations = _extract(episode, violation_extractor_config)

    commission_violations = [v for v in violations if v.violation_type == ViolationType.COMMISSION]
    assert len(commission_violations) == 1
    assert commission_violations[0].action_involved == "discharge_home"


@pytest.mark.parametrize(
    "antibiotic_time,expect_timing",
    [
        (75, True),
        (59, False),
        (61, True),
    ],
)
def test_timing_antibiotics_deadline_boundaries(
    violation_extractor_config: ViolationExtractorConfig,
    antibiotic_time: float,
    expect_timing: bool,
):
    actions = [
        _action("order_lab_blood_culture", 10),
        _action("order_lab_lactate", 15),
        _action("give_crystalloid_30ml_kg", 20),
        _action("start_vasopressor_norepinephrine", 30),
        _action("give_broad_spectrum_antibiotics", antibiotic_time),
    ]
    episode = _build_episode(
        f"timing_case_{int(antibiotic_time)}",
        actions,
        final_time=antibiotic_time,
    )

    violations = _extract(episode, violation_extractor_config)

    timing_violations = [
        v
        for v in violations
        if v.violation_type == ViolationType.TIMING and v.action_involved == "give_broad_spectrum_antibiotics"
    ]
    if expect_timing:
        assert len(timing_violations) == 1
    else:
        assert len(timing_violations) == 0


def test_sequence_antibiotics_before_blood_culture_is_violation(
    violation_extractor_config: ViolationExtractorConfig,
):
    violating_episode = _build_episode(
        "sequence_bad_case",
        [_action("give_broad_spectrum_antibiotics", 30)],
        final_time=30,
    )

    violating_violations = _extract(violating_episode, violation_extractor_config)
    sequence_violations = [v for v in violating_violations if v.violation_type == ViolationType.SEQUENCE]
    assert len(sequence_violations) == 1
    assert sequence_violations[0].action_involved == "give_broad_spectrum_antibiotics"

    control_episode = _build_episode(
        "sequence_control_case",
        [
            _action("order_lab_blood_culture", 10),
            _action("give_broad_spectrum_antibiotics", 30),
        ],
        final_time=30,
    )
    control_violations = _extract(control_episode, violation_extractor_config)
    control_sequence_violations = [v for v in control_violations if v.violation_type == ViolationType.SEQUENCE]
    assert len(control_sequence_violations) == 0


def test_deviation_action_outside_allowed_and_forbidden(violation_extractor_config: ViolationExtractorConfig):
    episode = _build_episode(
        "deviation_case",
        [_action("perform_random_unsupported_action", 15)],
        final_time=15,
    )

    violations = _extract(episode, violation_extractor_config)

    deviation_violations = [v for v in violations if v.violation_type == ViolationType.DEVIATION]
    assert len(deviation_violations) == 1
    assert deviation_violations[0].action_involved == "perform_random_unsupported_action"


def test_mece_priority_sequence_beats_deviation(violation_extractor_config: ViolationExtractorConfig):
    """MECE Violation Priority (Design Review §5-c):
    When an action would trigger both DEVIATION and SEQUENCE for the same action,
    only the higher-priority SEQUENCE violation is retained.

    This is achieved by monkeypatching _check_deviation and _check_sequence to both
    return violations for the same action, then verifying that only SEQUENCE survives.
    """
    from unittest.mock import patch
    import uuid

    from cga_bench.cpg_model.schemas.base import HarmSeverity, ViolationEvent, ViolationType

    engine = CPGEngineFactory.load_from_file(get_sepsis_graph_path())
    engine.current_node_id = "septic_shock_bundle"
    extractor = ViolationExtractor(engine, violation_extractor_config)

    action_key = "some_action_outside_allowed_with_missing_prior"
    episode = _build_episode(
        "mece_priority_case",
        [_action(action_key, 15)],
        final_time=15,
    )

    def fake_deviation(action, state, constraints):
        return ViolationEvent(
            violation_id=str(uuid.uuid4()),
            violation_type=ViolationType.DEVIATION,
            timestamp_minutes=action.timestamp_minutes,
            action_involved=action_key,
            state_at_violation=state.state_id,
            node_at_violation=constraints.current_node_id,
            harm_severity=HarmSeverity.MINOR,
            preventability=0.5,
            description=f"Deviation: {action_key}",
            guideline_reference="test",
        )

    def fake_sequence(action, state, constraints, performed_actions):
        return ViolationEvent(
            violation_id=str(uuid.uuid4()),
            violation_type=ViolationType.SEQUENCE,
            timestamp_minutes=action.timestamp_minutes,
            action_involved=action_key,
            expected_action="some_prior_action",
            state_at_violation=state.state_id,
            node_at_violation=constraints.current_node_id,
            harm_severity=HarmSeverity.MAJOR,
            preventability=1.0,
            description=f"Sequence: {action_key} without prior",
            guideline_reference="test",
        )

    with (
        patch.object(extractor, "_check_deviation", side_effect=fake_deviation),
        patch.object(extractor, "_check_sequence", side_effect=fake_sequence),
        patch.object(extractor, "_check_commission", return_value=None),
        patch.object(extractor, "_check_timing", return_value=None),
    ):
        violations = extractor.extract_violations(episode)

    action_violations = [v for v in violations if v.action_involved == action_key]
    # MECE: only ONE violation per action
    assert len(action_violations) == 1, (
        f"Expected 1 violation (SEQUENCE wins over DEVIATION), got {len(action_violations)}"
    )
    assert action_violations[0].violation_type == ViolationType.SEQUENCE, (
        f"Expected SEQUENCE (higher priority), got {action_violations[0].violation_type}"
    )


def test_b3_forbidden_normalized_via_alias(violation_extractor_config: ViolationExtractorConfig):
    """B3 cross-fix integration: scenario YAML forbidden uses one alias form
    (assess_urine_output) while the agent performs the other alias (monitor_urine_output).
    After α-1 (canonical=monitor_urine_output) + α-3 (engine normalizes scenario forbidden
    on load), both sides resolve to the same canonical key and COMMISSION must fire.

    Pre-fix behavior: action_key='monitor_urine_output' compared against raw
    scenario_forbidden={'assess_urine_output'} - asymmetric, no commission detected.
    """
    engine = CPGEngineFactory.load_from_file(get_sepsis_graph_path())
    engine.current_node_id = "septic_shock_bundle"
    # Inject scenario forbidden in the *raw* alias form a clinical author would write.
    engine.set_scenario_forbidden_actions(["assess_urine_output"])

    extractor = ViolationExtractor(engine, violation_extractor_config)
    episode = _build_episode(
        "b3_alias_case",
        [_action("monitor_urine_output", 30, action_type=ActionType.REASSESS)],
        final_time=30,
    )

    violations = extractor.extract_violations(episode)

    commission_violations = [v for v in violations if v.violation_type == ViolationType.COMMISSION]
    assert len(commission_violations) == 1, (
        f"B3 fix expected 1 COMMISSION via alias-normalized forbidden match; "
        f"got {len(commission_violations)} ({[v.action_involved for v in commission_violations]})"
    )
    # Both sides normalized to canonical form (monitor_urine_output per α-1)
    assert commission_violations[0].action_involved == "monitor_urine_output"
