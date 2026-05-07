"""Tests for SyntheticPatientGenerator."""

import pytest

from cga_bench.scenario_engine.synthetic_patient import (
    SyntheticPatientGenerator,
    SyntheticVitals,
    SyntheticLabResult,
    LAB_NORMAL_RANGES,
)


@pytest.fixture
def generator():
    return SyntheticPatientGenerator(random_seed=42)


class TestInferVitals:
    def test_default_normal_vitals(self, generator):
        vitals = generator.infer_vitals_from_description("routine checkup", {})
        assert 60 <= vitals.heart_rate <= 100
        assert 100 <= vitals.blood_pressure_systolic <= 140
        assert 36.5 <= vitals.temperature <= 37.5

    def test_hypotension_detected(self, generator):
        vitals = generator.infer_vitals_from_description(
            "patient with hypotension and shock", {}
        )
        assert vitals.blood_pressure_systolic < 90
        assert vitals.heart_rate > 100

    def test_fever_detected(self, generator):
        vitals = generator.infer_vitals_from_description(
            "patient presenting with high fever", {}
        )
        assert vitals.temperature > 38.0

    def test_explicit_vitals_override(self, generator):
        patient_state = {
            "vitals": {
                "heart_rate": 55,
                "temperature": 36.0,
            }
        }
        vitals = generator.infer_vitals_from_description(
            "patient with fever", patient_state
        )
        # Explicit values should override inferred ones
        assert vitals.heart_rate == 55
        assert vitals.temperature == 36.0

    def test_map_recalculated(self, generator):
        vitals = generator.infer_vitals_from_description("normal patient", {})
        expected_map = (
            vitals.blood_pressure_diastolic
            + (vitals.blood_pressure_systolic - vitals.blood_pressure_diastolic) / 3
        )
        assert abs(vitals.map_mmhg - expected_map) < 0.2


class TestVitalsTrajectory:
    def test_stable_trajectory_length(self, generator):
        initial = SyntheticVitals()
        trajectory = generator.generate_vitals_trajectory(initial, num_steps=10, trend="stable")
        assert len(trajectory) == 10

    def test_stable_trajectory_minimal_change(self, generator):
        initial = SyntheticVitals(heart_rate=75)
        trajectory = generator.generate_vitals_trajectory(initial, num_steps=5, trend="stable")
        # Stable trend: HR should stay close to initial
        for v in trajectory:
            assert 60 <= v.heart_rate <= 90

    def test_deteriorating_trajectory(self, generator):
        initial = SyntheticVitals(blood_pressure_systolic=120)
        trajectory = generator.generate_vitals_trajectory(
            initial, num_steps=20, trend="deteriorating"
        )
        # BP should generally trend downward
        assert trajectory[-1].blood_pressure_systolic <= initial.blood_pressure_systolic

    def test_vitals_clamped_to_physiological(self, generator):
        initial = SyntheticVitals(heart_rate=40)  # At lower boundary
        trajectory = generator.generate_vitals_trajectory(initial, num_steps=50, trend="stable")
        for v in trajectory:
            assert v.heart_rate >= 40  # Should never go below range

    def test_single_step(self, generator):
        initial = SyntheticVitals()
        trajectory = generator.generate_vitals_trajectory(initial, num_steps=1, trend="stable")
        assert len(trajectory) == 1
        assert trajectory[0] is initial

    def test_to_dict(self, generator):
        initial = SyntheticVitals()
        d = initial.to_dict()
        assert "heart_rate" in d
        assert "blood_pressure_systolic" in d
        assert "oxygen_saturation" in d


class TestLabResults:
    def test_generates_results_for_valid_codes(self, generator):
        results = generator.generate_lab_results(
            ["lactate", "wbc", "creatinine"],
            "patient with fever",
        )
        assert len(results) == 3
        for r in results:
            assert isinstance(r, SyntheticLabResult)
            assert r.test_code in LAB_NORMAL_RANGES

    def test_skips_unknown_codes(self, generator):
        results = generator.generate_lab_results(
            ["lactate", "unknown_test_xyz"],
            "patient",
        )
        assert len(results) == 1
        assert results[0].test_code == "lactate"

    def test_sepsis_context_elevates_lactate(self, generator):
        results = generator.generate_lab_results(["lactate"], "sepsis patient")
        assert len(results) == 1
        assert results[0].value > 2.0
        assert results[0].is_abnormal

    def test_mi_context_elevates_troponin(self, generator):
        results = generator.generate_lab_results(["troponin"], "patient with stemi MI")
        assert len(results) == 1
        assert results[0].value > 0.04
        assert results[0].is_abnormal

    def test_dka_context_elevates_glucose(self, generator):
        results = generator.generate_lab_results(
            ["glucose"], "diabetic ketoacidosis DKA"
        )
        assert len(results) == 1
        assert results[0].value > 200
        assert results[0].is_abnormal

    def test_normal_context_normal_values(self, generator):
        results = generator.generate_lab_results(["creatinine"], "routine checkup")
        assert len(results) == 1
        lo, hi, _ = LAB_NORMAL_RANGES["creatinine"]
        assert lo <= results[0].value <= hi
        assert not results[0].is_abnormal

    def test_result_timing(self, generator):
        results = generator.generate_lab_results(
            ["lactate"],
            "sepsis",
            ordered_step=2,
            time_step_minutes=5.0,
            result_delay_minutes=30.0,
        )
        assert results[0].ordered_time_minutes == 10.0
        assert results[0].result_time_minutes == 40.0


class TestSynthesizeTrajectory:
    def test_returns_complete_trajectory(self, generator):
        result = generator.synthesize_patient_trajectory(
            description="patient with sepsis",
            patient_state={"vitals": {}},
            num_steps=10,
        )
        assert "vitals_trajectory" in result
        assert "lab_results" in result
        assert "time_step_minutes" in result
        assert len(result["vitals_trajectory"]) == 10

    def test_deteriorating_trend_for_shock(self, generator):
        result = generator.synthesize_patient_trajectory(
            description="patient in shock and deteriorating rapidly",
            patient_state={"vitals": {}},
            num_steps=10,
        )
        # Should detect "deteriorating" trend
        assert len(result["vitals_trajectory"]) == 10

    def test_deterministic_with_seed(self):
        gen1 = SyntheticPatientGenerator(random_seed=99)
        gen2 = SyntheticPatientGenerator(random_seed=99)

        r1 = gen1.synthesize_patient_trajectory("sepsis shock", {"vitals": {}}, 5)
        r2 = gen2.synthesize_patient_trajectory("sepsis shock", {"vitals": {}}, 5)

        v1 = [v.to_dict() for v in r1["vitals_trajectory"]]
        v2 = [v.to_dict() for v in r2["vitals_trajectory"]]
        assert v1 == v2

    def test_lab_results_generated(self, generator):
        result = generator.synthesize_patient_trajectory(
            description="sepsis with elevated lactate",
            patient_state={"vitals": {}},
            num_steps=10,
        )
        assert len(result["lab_results"]) > 0
