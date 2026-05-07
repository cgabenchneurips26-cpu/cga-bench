"""Meso integration fixtures: 10 domain-representative scenarios.

Each scenario has a known violation profile (1-2 violations per case).
Tests verify: correct violation count, correct violation types, score in expected range.
"""

from collections.abc import Callable
from typing import NotRequired, TypedDict, cast

import pytest

from cga_bench.cpg_model.schemas.base import Action, ActionType, CGAScore, PatientState, ViolationEvent

from .conftest import (
    aki_patient,
    chest_pain_patient,
    dka_patient,
    heart_failure_patient,
    run_case,
    sepsis_patient,
    stroke_patient,
)


def action(action_id: str, timestamp: float, action_type: ActionType = ActionType.PROCEDURE) -> Action:
    return Action(type=action_type, action_id=action_id, args={}, timestamp_minutes=timestamp, justification=None)


class MesoScenario(TypedDict):
    id: str
    graph: str
    node: str
    patient: Callable[[], PatientState]
    actions: list[Action]
    final_time: float
    expected_violation_types: list[str]
    max_violations: NotRequired[int]
    min_violations: NotRequired[int]


MESO_SCENARIOS: list[MesoScenario] = [
    {
        "id": "meso_sepsis_compliant",
        "graph": "ssc_sepsis_hour1_bundle.yaml",
        "node": "septic_shock_bundle",
        "patient": sepsis_patient,
        "actions": [
            action("order_lab_blood_culture", 5),
            action("order_lab_lactate", 8),
            action("give_broad_spectrum_antibiotics", 20),
            action("give_crystalloid_30ml_kg", 25),
            action("start_vasopressor_norepinephrine", 35),
        ],
        "final_time": 50,
        "expected_violation_types": [],
        "max_violations": 0,
    },
    {
        "id": "meso_sepsis_late_and_missing",
        "graph": "ssc_sepsis_hour1_bundle.yaml",
        "node": "septic_shock_bundle",
        "patient": sepsis_patient,
        "actions": [
            action("order_lab_blood_culture", 10),
            action("give_broad_spectrum_antibiotics", 90),
        ],
        "final_time": 120,
        "expected_violation_types": ["timing"],
        "min_violations": 1,
    },
    {
        "id": "meso_chest_pain_compliant",
        "graph": "aha_chest_pain_evaluation.yaml",
        "node": "initial_assessment",
        "patient": chest_pain_patient,
        "actions": [
            action("obtain_12_lead_ecg", 5),
            action("assess_vital_signs", 3),
            action("obtain_chest_pain_history", 8),
        ],
        "final_time": 15,
        "expected_violation_types": [],
        "max_violations": 0,
    },
    {
        "id": "meso_chest_pain_nitrate_trap",
        "graph": "aha_chest_pain_evaluation.yaml",
        "node": "stemi_pathway",
        "patient": chest_pain_patient,
        "actions": [
            action("give_aspirin_loading", 5),
            action("give_nitrates_if_rv_infarct", 10),
        ],
        "final_time": 20,
        "expected_violation_types": ["commission"],
        "min_violations": 1,
    },
    {
        "id": "meso_stroke_compliant",
        "graph": "aha_stroke_2019.yaml",
        "node": "stroke_initial_assessment",
        "patient": stroke_patient,
        "actions": [
            action("activate_stroke_team", 2),
            action("obtain_last_known_well_time", 3),
            action("perform_nihss", 5),
            action("check_glucose", 6),
            action("establish_iv_access", 7),
            action("order_stat_ct_head", 10),
            action("order_cbc_bmp_coag", 12),
            action("obtain_12_lead_ecg", 15),
        ],
        "final_time": 30,
        "expected_violation_types": [],
        "max_violations": 0,
    },
    {
        "id": "meso_stroke_late_ct",
        "graph": "aha_stroke_2019.yaml",
        "node": "stroke_initial_assessment",
        "patient": stroke_patient,
        "actions": [
            action("activate_stroke_team", 2),
            action("obtain_last_known_well_time", 3),
            action("perform_nihss", 5),
            action("check_glucose", 6),
            action("establish_iv_access", 7),
            action("order_stat_ct_head", 40),
            action("order_cbc_bmp_coag", 42),
            action("obtain_12_lead_ecg", 45),
        ],
        "final_time": 50,
        "expected_violation_types": ["timing"],
        "min_violations": 1,
    },
    {
        "id": "meso_dka_compliant",
        "graph": "ada_dka_management.yaml",
        "node": "initial_assessment",
        "patient": dka_patient,
        "actions": [
            action("assess_vital_signs", 2),
            action("assess_mental_status", 3),
            action("order_lab_glucose", 8),
            action("order_lab_bmp", 9),
            action("order_lab_ketones", 12),
            action("order_lab_abg", 12),
        ],
        "final_time": 30,
        "expected_violation_types": ["omission"],
        "min_violations": 1,
        "max_violations": 2,
    },
    {
        "id": "meso_aki_nsaid",
        "graph": "kdigo_aki_full.yaml",
        "node": "aki_stage_1_management",
        "patient": aki_patient,
        "actions": [
            action("optimize_volume_status", 10),
            action("give_nsaid", 20),
        ],
        "final_time": 40,
        "expected_violation_types": ["commission"],
        "min_violations": 1,
    },
    {
        "id": "meso_hf_compliant",
        "graph": "aha_heart_failure_2022.yaml",
        "node": "hfref_gdmt",
        "patient": heart_failure_patient,
        "actions": [
            action("initiate_ace_or_arb_or_arni", 10),
            action("initiate_beta_blocker", 20),
            action("initiate_mra", 30),
            action("initiate_sglt2i", 40),
        ],
        "final_time": 50,
        "expected_violation_types": [],
        "max_violations": 0,
    },
    {
        "id": "meso_hf_nsaid_and_gap",
        "graph": "aha_heart_failure_2022.yaml",
        "node": "hfref_gdmt",
        "patient": heart_failure_patient,
        "actions": [
            action("initiate_ace_or_arb_or_arni", 10),
            action("give_nsaid", 15),
        ],
        "final_time": 120,
        "expected_violation_types": ["commission"],
        "min_violations": 1,
    },
]


@pytest.mark.parametrize("scenario", MESO_SCENARIOS, ids=[str(s["id"]) for s in MESO_SCENARIOS])
def test_meso_scenario(scenario: MesoScenario) -> None:
    patient = scenario["patient"]()
    result = run_case(
        graph_yaml=scenario["graph"],
        node_id=scenario["node"],
        patient=patient,
        actions=scenario["actions"],
        final_time=scenario["final_time"],
    )

    violations = cast("list[ViolationEvent]", result["violations"])
    score = cast("CGAScore", result["score"])
    violation_types = [v.violation_type.value for v in violations]

    for expected_type in scenario.get("expected_violation_types", []):
        assert expected_type in violation_types, f"Expected {expected_type} in {violation_types}"

    if "max_violations" in scenario:
        assert len(violations) <= scenario["max_violations"], (
            f"Too many violations: {len(violations)} > {scenario['max_violations']}"
        )
    if "min_violations" in scenario:
        assert len(violations) >= scenario["min_violations"], (
            f"Too few violations: {len(violations)} < {scenario['min_violations']}"
        )

    assert 0.0 <= score.compliance_score <= 1.0
    assert score.peak_risk >= 0.0
