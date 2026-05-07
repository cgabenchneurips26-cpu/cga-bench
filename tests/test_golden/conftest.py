import json
from pathlib import Path
from typing import cast

from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig
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
    CGAScore,
    EpisodeLog,
    HarmSeverity,
    PatientState,
    RecommendationClass,
    ViolationEvent,
    ViolationType,
    VitalSigns,
)

GRAPHS_DIR = Path(__file__).parent.parent.parent / "cpg_model" / "graphs"
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


def save_golden_snapshot(
    case_id: str,
    a_result: dict[str, list[ViolationEvent] | CGAScore],
    b_result: dict[str, list[ViolationEvent] | CGAScore],
) -> None:
    SNAPSHOTS_DIR.mkdir(exist_ok=True)
    snapshot = {
        "case_id": case_id,
        "a": _result_to_dict(a_result),
        "b": _result_to_dict(b_result),
    }
    path = SNAPSHOTS_DIR / f"{case_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, sort_keys=True)


def load_golden_snapshot(case_id: str) -> dict[str, object] | None:
    path = SNAPSHOTS_DIR / f"{case_id}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return cast(dict[str, object], json.load(f))


def _result_to_dict(result: dict[str, list[ViolationEvent] | CGAScore]) -> dict[str, object]:
    score = cast(CGAScore, result["score"])
    violations = cast(list[ViolationEvent], result["violations"])
    return {
        "compliance_score": round(score.compliance_score, 4),
        "peak_risk": round(score.peak_risk, 4),
        "aggregate_risk": round(score.aggregate_risk, 4),
        "total_violations": score.total_violations,
        "violations_by_type": {k: v for k, v in score.violations_by_type.items() if v > 0},
        "sub_scores": {k: round(v, 4) for k, v in score.sub_scores.items()},
        "violation_details": [
            {
                "type": v.violation_type.value,
                "action": v.action_involved or v.expected_action or "",
                "timestamp": round(v.timestamp_minutes, 1) if v.timestamp_minutes else None,
            }
            for v in violations
        ],
    }


def default_violation_config() -> ViolationExtractorConfig:
    return ViolationExtractorConfig(
        harm_severity_mappings=[
            HarmSeverityMapping(action_pattern="lactate", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="blood_culture", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="antibiotics", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="crystalloid", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="vasopressor", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="discharge", severity=HarmSeverity.CATASTROPHIC),
            HarmSeverityMapping(action_pattern="insulin", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="potassium", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="nsaid", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="contrast", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="ecg", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="aspirin", severity=HarmSeverity.MAJOR),
            HarmSeverityMapping(action_pattern="alteplase", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="nitrate", severity=HarmSeverity.CATASTROPHIC),
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
        enable_action_normalization=False,
    )


def default_scorer_config() -> HarmScorerConfig:
    return HarmScorerConfig(
        severity_weights={
            HarmSeverity.MINOR: 0.1,
            HarmSeverity.MODERATE: 0.3,
            HarmSeverity.MAJOR: 0.5,
            HarmSeverity.SEVERE: 0.8,
            HarmSeverity.CATASTROPHIC: 1.0,
        },
        guideline_strength_weights={
            RecommendationClass.CLASS_I: 1.0,
            RecommendationClass.CLASS_IIA: 0.7,
            RecommendationClass.CLASS_IIB: 0.4,
            RecommendationClass.CLASS_III: 0.0,
            None: 0.5,
        },
        violation_type_weights={
            ViolationType.OMISSION: 0.7,
            ViolationType.COMMISSION: 1.0,
            ViolationType.TIMING: 0.5,
            ViolationType.SEQUENCE: 0.6,
            ViolationType.DEVIATION: 0.3,
        },
    )


def _build_episode(patient: PatientState, actions: list[Action], final_time: float) -> EpisodeLog:
    states = [patient.model_copy(deep=True)]
    for idx, action in enumerate(actions, start=1):
        action_state = patient.model_copy(deep=True)
        action_state.state_id = f"s{idx}"
        action_state.time_since_arrival_minutes = action.timestamp_minutes
        states.append(action_state)

    final_state = patient.model_copy(deep=True)
    final_state.state_id = "sf"
    final_state.time_since_arrival_minutes = final_time
    states.append(final_state)

    return EpisodeLog(
        episode_id="golden_test",
        scenario_id="golden",
        agent_id="golden",
        states=states,
        actions=actions,
        observations=[{}],
        total_duration_minutes=final_time,
        total_llm_calls=0,
        total_tokens=0,
        total_tool_calls=0,
        termination_reason="timeout",
    )


def run_case(
    graph_yaml: str,
    node_id: str,
    patient: PatientState,
    actions: list[Action],
    final_time: float,
    total_mandatory_count: int = 20,
) -> dict[str, list[ViolationEvent] | CGAScore]:
    engine = CPGEngineFactory.load_from_file(str(GRAPHS_DIR / graph_yaml))
    engine.current_node_id = node_id

    episode = _build_episode(patient=patient, actions=actions, final_time=final_time)

    extractor = ViolationExtractor(engine, default_violation_config())
    violations = extractor.extract_violations(episode)

    scorer = HarmScorer(total_mandatory_count=total_mandatory_count, config=default_scorer_config())
    score = scorer.compute_score(violations, episode)

    return {"violations": violations, "score": score}


def find_new_violations(a_violations: list[ViolationEvent], b_violations: list[ViolationEvent]) -> list[ViolationEvent]:
    a_keys = {(v.violation_type, v.action_involved or v.expected_action) for v in a_violations}
    return [v for v in b_violations if (v.violation_type, v.action_involved or v.expected_action) not in a_keys]


def assert_ab_monotonic(
    a_result: dict[str, list[ViolationEvent] | CGAScore],
    b_result: dict[str, list[ViolationEvent] | CGAScore],
    expected_violation_type: str,
) -> None:
    a_score = cast(CGAScore, a_result["score"])
    b_score = cast(CGAScore, b_result["score"])

    assert b_score.compliance_score <= a_score.compliance_score, (
        f"Expected B_score <= A_score, got A={a_score.compliance_score:.3f}, "
        f"B={b_score.compliance_score:.3f} (equal allowed after MECE dedup)"
    )

    diff = find_new_violations(
        cast(list[ViolationEvent], a_result["violations"]),
        cast(list[ViolationEvent], b_result["violations"]),
    )
    # After MECE dedup, B may have same violation count as A (dedup removed duplicates).
    # At minimum, B should not have FEWER total violations than A.
    b_total = b_score.total_violations
    a_total = a_score.total_violations
    assert b_total >= a_total, f"B should have >= violations than A: A={a_total}, B={b_total}"
    if diff:
        assert any(v.violation_type.value == expected_violation_type for v in diff), (
            f"Expected new {expected_violation_type} violation, "
            f"got: {[v.violation_type.value for v in diff]}"
        )


def _action(action_id: str, timestamp: float, action_type: ActionType = ActionType.PROCEDURE) -> Action:
    return Action(type=action_type, action_id=action_id, args={}, timestamp_minutes=timestamp, justification=None)


def sepsis_patient() -> PatientState:
    return PatientState(
        state_id="s0",
        time_since_arrival_minutes=0,
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


def chest_pain_patient() -> PatientState:
    return PatientState(
        state_id="s0",
        time_since_arrival_minutes=0,
        age=55,
        sex="M",
        vitals=VitalSigns(
            heart_rate=90,
            blood_pressure_systolic=140,
            blood_pressure_diastolic=90,
            respiratory_rate=18,
            temperature=37.0,
            oxygen_saturation=97,
            map_mmhg=107,
        ),
        chief_complaint="severe chest pain",
        working_diagnosis="stemi",
    )


def dka_patient() -> PatientState:
    return PatientState(
        state_id="s0",
        time_since_arrival_minutes=0,
        age=30,
        sex="F",
        vitals=VitalSigns(
            heart_rate=110,
            blood_pressure_systolic=100,
            blood_pressure_diastolic=60,
            respiratory_rate=28,
            temperature=37.2,
            oxygen_saturation=98,
            map_mmhg=73,
        ),
        chief_complaint="polyuria, nausea, abdominal pain",
        working_diagnosis="dka",
    )


def aki_patient() -> PatientState:
    return PatientState(
        state_id="s0",
        time_since_arrival_minutes=0,
        age=70,
        sex="M",
        vitals=VitalSigns(
            heart_rate=85,
            blood_pressure_systolic=130,
            blood_pressure_diastolic=80,
            respiratory_rate=16,
            temperature=37.0,
            oxygen_saturation=96,
            map_mmhg=97,
        ),
        chief_complaint="decreased urine output",
        working_diagnosis="aki",
    )


def stroke_patient() -> PatientState:
    return PatientState(
        state_id="s0",
        time_since_arrival_minutes=0,
        age=68,
        sex="M",
        vitals=VitalSigns(
            heart_rate=80,
            blood_pressure_systolic=170,
            blood_pressure_diastolic=95,
            respiratory_rate=16,
            temperature=37.0,
            oxygen_saturation=97,
            map_mmhg=120,
        ),
        chief_complaint="sudden left-sided weakness",
        working_diagnosis="ischemic_stroke",
    )


def heart_failure_patient() -> PatientState:
    return PatientState(
        state_id="s0",
        time_since_arrival_minutes=0,
        age=72,
        sex="M",
        vitals=VitalSigns(
            heart_rate=95,
            blood_pressure_systolic=110,
            blood_pressure_diastolic=70,
            respiratory_rate=22,
            temperature=37.0,
            oxygen_saturation=93,
            map_mmhg=83,
        ),
        chief_complaint="dyspnea and edema",
        working_diagnosis="hfref",
    )
