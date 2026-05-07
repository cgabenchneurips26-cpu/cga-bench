"""Tests for enhanced domain detection and dynamic observation in run_external_benchmark."""

import pytest
import sys
from pathlib import Path

# Ensure run_external_benchmark can be imported
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run_external_benchmark import (
    detect_domain,
    create_observation,
    ExternalScenario,
)


def _make_scenario(
    description: str = "",
    diagnosis: str = "",
    chief_complaint: str = "",
    vitals: dict = None,
    test_results: dict = None,
    symptoms: dict = None,
) -> ExternalScenario:
    """Helper to create test scenarios."""
    return ExternalScenario(
        scenario_id="test_001",
        source_benchmark="test",
        description=description,
        patient_state={
            "chief_complaint": chief_complaint,
            "working_diagnosis": "",
            "vitals": vitals or {},
            "history": "",
            "symptoms": symptoms or {},
            "test_results": test_results or {},
            "allergies": [],
            "comorbidities": [],
            "contraindications": [],
        },
        expected_diagnosis=diagnosis,
        expected_actions=["assess_patient"],
        metadata={},
    )


class TestEnhancedDomainDetection:
    """Test multi-feature domain scoring."""

    def test_sepsis_from_keywords(self):
        scenario = _make_scenario(diagnosis="Sepsis")
        assert detect_domain(scenario) == "sepsis"

    def test_sepsis_from_infection_plus_vitals(self):
        scenario = _make_scenario(
            description="Patient presenting with infection",
            vitals={"temperature": 39.0, "heart_rate": 110},
        )
        # infection (1.5) + temp>38 (1.0) + HR>90 (0.5) = 3.0
        # Threshold is >3.0, so with temp + HR this should cross
        # Actually need >3.0 not >=3.0. infection=1.5 + temp=1.0 + hr=0.5 = 3.0 exactly
        # Won't match because >3.0 required. Let's add blood culture to push over.
        scenario = _make_scenario(
            description="Patient presenting with infection, blood culture ordered",
            vitals={"temperature": 39.0, "heart_rate": 110},
        )
        assert detect_domain(scenario) == "sepsis"

    def test_chest_pain_from_stemi(self):
        scenario = _make_scenario(diagnosis="STEMI")
        assert detect_domain(scenario) == "chest_pain"

    def test_chest_pain_from_troponin_and_ecg(self):
        scenario = _make_scenario(
            chief_complaint="chest pain with troponin elevation",
            description="patient needs ECG",
        )
        # chest pain (1.5) + troponin (1.5) + ecg (0.5) = 3.5
        assert detect_domain(scenario) == "chest_pain"

    def test_stroke_from_keywords(self):
        scenario = _make_scenario(diagnosis="ischemic stroke with hemiparesis")
        assert detect_domain(scenario) == "stroke"

    def test_stroke_from_nihss(self):
        scenario = _make_scenario(
            description="neurological emergency",
            chief_complaint="sudden onset weakness, NIHSS score 12, needs tPA",
        )
        assert detect_domain(scenario) == "stroke"

    def test_heart_failure(self):
        scenario = _make_scenario(
            diagnosis="Acute decompensated heart failure",
            description="patient with pulmonary edema and elevated BNP",
        )
        assert detect_domain(scenario) == "heart_failure"

    def test_aki_detection(self):
        scenario = _make_scenario(
            diagnosis="Acute kidney injury",
            description="patient with elevated creatinine and oliguria",
        )
        assert detect_domain(scenario) == "aki"

    def test_dka_detection(self):
        scenario = _make_scenario(
            diagnosis="Diabetic ketoacidosis DKA",
            description="hyperglycemia with ketones",
        )
        assert detect_domain(scenario) == "dka"

    def test_general_for_unmatched(self):
        scenario = _make_scenario(
            description="routine physical examination",
            diagnosis="healthy adult",
        )
        assert detect_domain(scenario) == "general"

    def test_highest_scoring_domain_wins(self):
        # Both sepsis and chest_pain keywords, but ACS should dominate
        scenario = _make_scenario(
            diagnosis="STEMI with troponin elevation and ST elevation",
            description="patient also febrile",
        )
        # chest_pain: stemi(3) + troponin(1.5) + st elevation(2) = 6.5
        # sepsis: febrile is not in the keyword list
        assert detect_domain(scenario) == "chest_pain"


class TestDynamicCreateObservation:
    """Test create_observation with trajectory parameter."""

    def test_static_observation_without_trajectory(self):
        scenario = _make_scenario(
            chief_complaint="test patient",
            vitals={"heart_rate": 80},
        )
        obs = create_observation(scenario, step=0)
        assert obs.timestamp_minutes == 0
        assert obs.new_results == []
        assert obs.alerts == []
        assert obs.visible_state["vitals"]["heart_rate"] == 80

    def test_static_observation_same_each_step(self):
        scenario = _make_scenario(vitals={"heart_rate": 80})
        obs1 = create_observation(scenario, step=0)
        obs2 = create_observation(scenario, step=5)
        assert obs1.visible_state["vitals"] == obs2.visible_state["vitals"]
        assert obs2.timestamp_minutes == 25

    def test_dynamic_observation_with_trajectory(self):
        scenario = _make_scenario(vitals={"heart_rate": 80})
        trajectory = {
            "vitals": [
                {"heart_rate": 80, "blood_pressure_systolic": 120},
                {"heart_rate": 85, "blood_pressure_systolic": 118},
                {"heart_rate": 90, "blood_pressure_systolic": 115},
            ],
            "lab_results": [],
        }
        obs0 = create_observation(scenario, step=0, trajectory=trajectory)
        obs1 = create_observation(scenario, step=1, trajectory=trajectory)
        obs2 = create_observation(scenario, step=2, trajectory=trajectory)

        assert obs0.visible_state["vitals"]["heart_rate"] == 80
        assert obs1.visible_state["vitals"]["heart_rate"] == 85
        assert obs2.visible_state["vitals"]["heart_rate"] == 90

    def test_dynamic_lab_result_delivery(self):
        scenario = _make_scenario()
        trajectory = {
            "vitals": [{"heart_rate": 80}] * 10,
            "lab_results": [
                {
                    "test_code": "lactate",
                    "value": 4.5,
                    "unit": "mmol/L",
                    "ordered_time_minutes": 0,
                    "result_time_minutes": 15,  # Arrives at step 3 (15 min)
                    "is_abnormal": True,
                },
            ],
        }
        # Step 0-2: result not ready
        obs0 = create_observation(scenario, step=0, trajectory=trajectory)
        assert len(obs0.new_results) == 0

        obs2 = create_observation(scenario, step=2, trajectory=trajectory)
        assert len(obs2.new_results) == 0

        # Step 3: result arrives (result_time_minutes=15, step=3 → 15 min)
        obs3 = create_observation(scenario, step=3, trajectory=trajectory)
        assert len(obs3.new_results) == 1
        assert obs3.new_results[0]["test_code"] == "lactate"
        assert obs3.new_results[0]["is_abnormal"] is True

    def test_dynamic_alerts_from_abnormal_labs(self):
        scenario = _make_scenario()
        trajectory = {
            "vitals": [{"heart_rate": 80}] * 5,
            "lab_results": [
                {
                    "test_code": "troponin",
                    "value": 2.5,
                    "unit": "ng/mL",
                    "ordered_time_minutes": 0,
                    "result_time_minutes": 10,
                    "is_abnormal": True,
                },
            ],
        }
        obs = create_observation(scenario, step=2, trajectory=trajectory)
        assert any("ALERT" in a for a in obs.alerts)

    def test_dynamic_alerts_from_hypotension(self):
        scenario = _make_scenario()
        trajectory = {
            "vitals": [
                {"heart_rate": 80, "blood_pressure_systolic": 85, "oxygen_saturation": 97},
            ],
            "lab_results": [],
        }
        obs = create_observation(scenario, step=0, trajectory=trajectory)
        assert any("Hypotension" in a for a in obs.alerts)

    def test_trajectory_fallback_to_last_vitals(self):
        scenario = _make_scenario()
        trajectory = {
            "vitals": [
                {"heart_rate": 80},
                {"heart_rate": 85},
            ],
            "lab_results": [],
        }
        # Step 5 is beyond the trajectory length → should use last vitals
        obs = create_observation(scenario, step=5, trajectory=trajectory)
        assert obs.visible_state["vitals"]["heart_rate"] == 85
