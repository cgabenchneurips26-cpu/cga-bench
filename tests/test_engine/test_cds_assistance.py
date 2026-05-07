"""
Gate 4 — CDS Assistance leakage closure tests.

Verifies that Observation.mandatory_actions is empty by default (cds_assistance=False)
and non-empty when cds_assistance=True.
"""

import pytest

from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns, Action, ActionType
from cga_bench.scenario_engine.environment import ClinicalEnvironment, EnvironmentConfig


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_septic_shock_state() -> PatientState:
    return PatientState(
        state_id="cds_test_septic_shock",
        time_since_arrival_minutes=0,
        age=60,
        sex="M",
        weight_kg=75,
        vitals=VitalSigns(
            heart_rate=115,
            blood_pressure_systolic=82,
            blood_pressure_diastolic=48,
            respiratory_rate=22,
            temperature=38.8,
            oxygen_saturation=93,
            map_mmhg=59,
        ),
        chief_complaint="fever, hypotension",
        working_diagnosis="septic_shock",
        contraindications=[],
        allergies=[],
        comorbidities=[],
    )


def _make_base_config(**overrides) -> EnvironmentConfig:
    defaults = dict(
        max_duration_minutes=60,
        time_step_minutes=5,
        lab_result_delay_minutes=30,
        imaging_result_delay_minutes=45,
        enable_state_deterioration=False,
    )
    defaults.update(overrides)
    return EnvironmentConfig(**defaults)


def _make_env(state: PatientState, config: EnvironmentConfig) -> ClinicalEnvironment:
    ground_truth = {
        "lab_lactate": 4.2,
        "lab_blood_culture": "pending",
    }
    return ClinicalEnvironment(
        initial_state=state,
        config=config,
        ground_truth=ground_truth,
    )


def _dummy_lab_action() -> Action:
    return Action(
        type=ActionType.ORDER_LAB,
        action_id="order_lab_lactate",
        args={"test_code": "lactate"},
        timestamp_minutes=0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_default_observation_hides_mandatory_actions() -> None:
    """Default config (cds_assistance=False) must yield empty mandatory_actions."""
    state = _make_septic_shock_state()
    config = _make_base_config()  # cds_assistance defaults to False

    assert config.cds_assistance is False, "Precondition: default must be False"

    env = _make_env(state, config)
    obs = env.reset()
    assert obs.mandatory_actions == [], (
        f"Expected empty mandatory_actions on reset, got {obs.mandatory_actions}"
    )

    # Also verify after a step
    obs2, _, _, _ = env.step(_dummy_lab_action())
    assert obs2.mandatory_actions == [], (
        f"Expected empty mandatory_actions after step, got {obs2.mandatory_actions}"
    )


def test_cds_assistance_exposes_mandatory_actions() -> None:
    """cds_assistance=True must yield non-empty mandatory_actions for a septic shock patient."""
    state = _make_septic_shock_state()
    config = _make_base_config(cds_assistance=True)

    env = _make_env(state, config)
    obs = env.reset()

    assert isinstance(obs.mandatory_actions, list)
    assert len(obs.mandatory_actions) > 0, (
        "Expected non-empty mandatory_actions when cds_assistance=True for septic_shock"
    )

    # Spot-check that at least one SSC Hour-1 action is present
    ssc_expected = {
        "order_lab_lactate",
        "order_lab_blood_culture",
        "give_broad_spectrum_antibiotics",
    }
    assert ssc_expected & set(obs.mandatory_actions), (
        f"No SSC Hour-1 mandatory action found. Got: {obs.mandatory_actions}"
    )
