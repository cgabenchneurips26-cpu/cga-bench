from __future__ import annotations

import pytest

from cga_bench.assessor_core.state_reducer import StateReducer, _NORMAL_LAB_DEFAULTS
from cga_bench.cpg_model.schemas.base import Action, ActionType, PatientState, VitalSigns


def _state(time: float = 0.0) -> PatientState:
    return PatientState(
        state_id="s1",
        time_since_arrival_minutes=time,
        age=55,
        sex="M",
        chief_complaint="test complaint",
        vitals=VitalSigns(
            heart_rate=80, systolic_bp=120, diastolic_bp=80,
            mean_arterial_pressure=93, respiratory_rate=16,
            oxygen_saturation=98, temperature=37.0,
        ),
        vital_signs=VitalSigns(
            heart_rate=80, systolic_bp=120, diastolic_bp=80,
            mean_arterial_pressure=93, respiratory_rate=16,
            oxygen_saturation=98, temperature=37.0,
        ),
        lab_results=[],
        medications_given=[],
        procedures_done=[],
        active_problems=[],
        allergies=[],
    )


def _action(action_id: str, ts: float = 5.0, args: dict | None = None) -> Action:
    return Action(
        type=ActionType.ORDER_LAB,
        action_id=action_id,
        args=args or {},
        timestamp_minutes=ts,
    )


class TestLabOrders:
    def test_order_lab_adds_lab_result(self):
        reducer = StateReducer()
        state = _state()
        new = reducer.apply(state, _action("order_lab_lactate"))
        assert len(new.lab_results) == 1
        assert new.lab_results[0].test_code == "lactate"

    def test_lab_result_uses_normal_defaults(self):
        reducer = StateReducer()
        new = reducer.apply(_state(), _action("order_lab_troponin"))
        lab = new.lab_results[0]
        assert lab.value == pytest.approx(0.01)
        assert lab.unit == "ng/mL"

    def test_unknown_lab_defaults_to_zero(self):
        reducer = StateReducer()
        new = reducer.apply(_state(), _action("order_lab_exotic_test"))
        assert new.lab_results[0].value == 0.0

    def test_duplicate_lab_not_added(self):
        reducer = StateReducer()
        s1 = reducer.apply(_state(), _action("order_lab_lactate", ts=1.0))
        s2 = reducer.apply(s1, _action("order_lab_lactate", ts=2.0))
        assert len(s2.lab_results) == 1

    def test_empty_test_code_ignored(self):
        reducer = StateReducer()
        new = reducer.apply(_state(), _action("order_lab_"))
        assert len(new.lab_results) == 0


class TestMedications:
    def test_give_adds_medication(self):
        reducer = StateReducer()
        new = reducer.apply(_state(), _action("give_broad_spectrum_antibiotics"))
        assert len(new.medications_given) == 1
        assert new.medications_given[0]["medication_code"] == "broad_spectrum_antibiotics"

    def test_duplicate_medication_not_added(self):
        reducer = StateReducer()
        s1 = reducer.apply(_state(), _action("give_aspirin"))
        s2 = reducer.apply(s1, _action("give_aspirin"))
        assert len(s2.medications_given) == 1

    def test_empty_med_code_ignored(self):
        reducer = StateReducer()
        new = reducer.apply(_state(), _action("give_"))
        assert len(new.medications_given) == 0


class TestProcedures:
    def test_procedure_added(self):
        reducer = StateReducer()
        new = reducer.apply(_state(), _action("assess_vital_signs"))
        assert "assess_vital_signs" in new.procedures_done

    def test_duplicate_procedure_not_added(self):
        reducer = StateReducer()
        s1 = reducer.apply(_state(), _action("start_vasopressor"))
        s2 = reducer.apply(s1, _action("start_vasopressor"))
        assert s2.procedures_done.count("start_vasopressor") == 1


class TestImmutability:
    def test_original_state_unchanged(self):
        reducer = StateReducer()
        original = _state()
        original_labs = len(original.lab_results)
        _ = reducer.apply(original, _action("order_lab_lactate"))
        assert len(original.lab_results) == original_labs

    def test_timestamp_updated(self):
        reducer = StateReducer()
        new = reducer.apply(_state(0.0), _action("assess_vital_signs", ts=15.0))
        assert new.time_since_arrival_minutes == 15.0


class TestNormalLabDefaults:
    def test_all_defaults_have_float_values(self):
        for code, (value, unit) in _NORMAL_LAB_DEFAULTS.items():
            assert isinstance(value, float), f"{code} value not float"
            assert isinstance(unit, str), f"{code} unit not str"

    def test_at_least_30_defaults(self):
        assert len(_NORMAL_LAB_DEFAULTS) >= 30
