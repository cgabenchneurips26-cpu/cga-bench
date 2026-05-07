"""Tests for ApplicabilityFilter: clinical applicability beyond structural reachability."""

import pytest

from cga_bench.cpg_engine.applicability import ApplicabilityFilter, MandatoryObligation
from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns


def _make_state(**overrides) -> PatientState:
    defaults = dict(
        state_id="test",
        age=65,
        sex="male",
        chief_complaint="fever",
        vitals=VitalSigns(
            heart_rate=110.0,
            blood_pressure_systolic=85.0,
            blood_pressure_diastolic=55.0,
            temperature=39.0,
            respiratory_rate=22.0,
            oxygen_saturation=94.0,
        ),
    )
    defaults.update(overrides)
    return PatientState(**defaults)


class TestApplicabilityFilter:
    """Clinical applicability checks."""

    def test_no_criteria_is_applicable(self):
        """Node with no entry_criteria is always applicable."""
        node_data = {"mandatory_actions": ["assess_vital_signs"]}
        state = _make_state()
        assert ApplicabilityFilter.is_clinically_applicable(node_data, state) is True

    def test_empty_criteria_is_applicable(self):
        node_data = {"entry_criteria": {}}
        state = _make_state()
        assert ApplicabilityFilter.is_clinically_applicable(node_data, state) is True

    def test_none_state_is_applicable(self):
        """Conservative: None state → applicable."""
        node_data = {"entry_criteria": {"sbp_below": 90}}
        assert ApplicabilityFilter.is_clinically_applicable(node_data, None) is True

    def test_sbp_below_criterion_met(self):
        node_data = {"entry_criteria": {"sbp_below": 90}}
        state = _make_state()  # sbp=85
        assert ApplicabilityFilter.is_clinically_applicable(node_data, state) is True

    def test_sbp_below_criterion_not_met(self):
        node_data = {"entry_criteria": {"sbp_below": 80}}
        state = _make_state()  # sbp=85
        assert ApplicabilityFilter.is_clinically_applicable(node_data, state) is False

    def test_temperature_criterion(self):
        node_data = {"entry_criteria": {"temperature_above": 38.0}}
        state = _make_state()  # temp=39.0
        assert ApplicabilityFilter.is_clinically_applicable(node_data, state) is True

    def test_age_criterion(self):
        node_data = {"entry_criteria": {"age_above": 18}}
        state = _make_state()  # age=65
        assert ApplicabilityFilter.is_clinically_applicable(node_data, state) is True

    def test_age_criterion_not_met(self):
        node_data = {"entry_criteria": {"age_above": 70}}
        state = _make_state()  # age=65
        assert ApplicabilityFilter.is_clinically_applicable(node_data, state) is False

    def test_unknown_criterion_conservative(self):
        """Unknown criteria default to True (conservative)."""
        node_data = {"entry_criteria": {"unknown_field": "some_value"}}
        state = _make_state()
        assert ApplicabilityFilter.is_clinically_applicable(node_data, state) is True


class TestMandatoryObligation:
    """MandatoryObligation dataclass."""

    def test_creation(self):
        ob = MandatoryObligation(
            action="order_lab_lactate",
            node="initial_assessment",
            depth=0,
            reachability_type="AF",
            severity="moderate",
        )
        assert ob.action == "order_lab_lactate"
        assert ob.reachability_type == "AF"
