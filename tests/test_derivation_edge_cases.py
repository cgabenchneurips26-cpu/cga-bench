"""Test 1.1: Condition evaluation edge cases for ConstraintDerivationEngine."""

from __future__ import annotations

from cpg_model.constraint_derivation import ConstraintDerivationEngine

engine = ConstraintDerivationEngine()


# --- numeric comparison ---


def test_numeric_less_than() -> None:
    patient = {"labs": {"potassium": 2.9}}
    assert engine._evaluate_condition("patient.labs.potassium < 3.3", patient) is True


def test_numeric_boundary_exact() -> None:
    patient = {"labs": {"potassium": 3.3}}
    assert engine._evaluate_condition("patient.labs.potassium < 3.3", patient) is False


def test_numeric_greater_than() -> None:
    patient = {"labs": {"potassium": 6.2}}
    assert engine._evaluate_condition("patient.labs.potassium > 5.5", patient) is True


# --- list membership ---


def test_list_contains() -> None:
    patient = {"comorbidities": ["cocaine_use", "hypertension"]}
    assert engine._evaluate_condition("'cocaine_use' in patient.comorbidities", patient) is True


def test_list_not_contains() -> None:
    patient = {"comorbidities": ["hypertension"]}
    assert engine._evaluate_condition("'cocaine_use' in patient.comorbidities", patient) is False


# --- compound conditions ---


def test_and_condition() -> None:
    patient = {"medications": ["sglt2_inhibitor"], "labs": {"glucose": 180}}
    assert (
        engine._evaluate_condition(
            "'sglt2_inhibitor' in patient.medications and patient.labs.glucose < 250",
            patient,
        )
        is True
    )


def test_or_condition() -> None:
    patient = {"vitals": {"sbp": 190, "dbp": 100}}
    assert engine._evaluate_condition("patient.vitals.sbp > 185 or patient.vitals.dbp > 110", patient) is True


def test_or_condition_second_true() -> None:
    patient = {"vitals": {"sbp": 170, "dbp": 115}}
    assert engine._evaluate_condition("patient.vitals.sbp > 185 or patient.vitals.dbp > 110", patient) is True


def test_or_condition_neither() -> None:
    patient = {"vitals": {"sbp": 170, "dbp": 100}}
    assert engine._evaluate_condition("patient.vitals.sbp > 185 or patient.vitals.dbp > 110", patient) is False


# --- missing fields (graceful failure) ---


def test_missing_lab_field() -> None:
    patient: dict = {"labs": {}}
    assert engine._evaluate_condition("patient.labs.potassium < 3.3", patient) is False


def test_missing_labs_entirely() -> None:
    patient: dict = {}
    assert engine._evaluate_condition("patient.labs.potassium < 3.3", patient) is False


def test_missing_comorbidities() -> None:
    patient: dict = {}
    assert engine._evaluate_condition("'cocaine_use' in patient.comorbidities", patient) is False


# --- always-true ---


def test_true_condition() -> None:
    patient: dict = {}
    assert engine._evaluate_condition("True", patient) is True


# --- nested access ---


def test_deeply_nested() -> None:
    patient = {"presentation": {"symptom_onset_hours": 18}}
    assert engine._evaluate_condition("patient.presentation.symptom_onset_hours > 12", patient) is True


# --- str() in condition ---


def test_str_in_condition() -> None:
    """Some rules use 'str(patient.comorbidities)' pattern."""
    patient = {"comorbidities": ["pregnancy_28weeks"]}
    assert engine._evaluate_condition("'pregnancy' in str(patient.comorbidities)", patient) is True


def test_str_in_condition_no_match() -> None:
    patient = {"comorbidities": ["hypertension"]}
    assert engine._evaluate_condition("'pregnancy' in str(patient.comorbidities)", patient) is False
