from typing import Any, Dict, List

from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns
from .models import EpisodeEvidence, NormalizedEpisode


def normalize_action_id(action_id: str) -> str:
    return action_id.lower().replace(" ", "_").replace("-", "_").strip()


def extract_actions_from_osce(case: Dict[str, Any]) -> List[str]:
    actions: List[str] = []

    raw_osce = case.get("raw_osce", {})
    test_results = raw_osce.get("Test_Results", case.get("test_results", {}))

    if test_results:
        for category, results in test_results.items():
            category_lower = normalize_action_id(category)

            if "blood" in category_lower or category_lower in ["cbc", "cmp", "bmp"]:
                actions.append(f"order_lab_{category_lower}")
                if isinstance(results, dict):
                    for test_name in results.keys():
                        actions.append(f"order_lab_{normalize_action_id(test_name)}")
            elif any(
                img in category_lower
                for img in ["imaging", "xray", "x_ray", "ct", "mri", "ultrasound", "ecg", "ekg", "echo"]
            ):
                actions.append(f"order_imaging_{category_lower}")
                if isinstance(results, dict):
                    for img_name in results.keys():
                        actions.append(f"order_imaging_{normalize_action_id(img_name)}")
            elif any(proc in category_lower for proc in ["emg", "electromyography", "eeg", "nerve_conduction", "biopsy"]):
                actions.append(f"order_procedure_{category_lower}")
            else:
                actions.append(f"order_test_{category_lower}")

    physical_exam = raw_osce.get("Physical_Examination_Findings", {})
    if physical_exam:
        for exam_type in physical_exam.keys():
            exam_lower = normalize_action_id(exam_type)
            if exam_lower != "vital_signs":
                actions.append(f"physical_exam_{exam_lower}")

    vitals = case.get("vitals", {})
    if vitals and any(v is not None for v in vitals.values()):
        actions.append("assess_vitals")
        actions.append("check_vital_signs")

    actions.append("take_history")
    actions.append("assess_chief_complaint")

    return sorted(set(normalize_action_id(action) for action in actions))


def create_patient_state(case: Dict[str, Any]) -> PatientState:
    patient = case.get("patient", {})
    vitals_data = case.get("vitals", {})

    vitals = VitalSigns(
        heart_rate=vitals_data.get("heart_rate"),
        blood_pressure_systolic=vitals_data.get("blood_pressure_systolic"),
        blood_pressure_diastolic=vitals_data.get("blood_pressure_diastolic"),
        respiratory_rate=vitals_data.get("respiratory_rate"),
        temperature_celsius=vitals_data.get("temperature"),
        oxygen_saturation=vitals_data.get("spo2"),
    )

    medical_history = case.get("medical_history", {})

    return PatientState(
        state_id=patient.get("id", "unknown"),
        age=patient.get("age", 50),
        sex=patient.get("sex", "U"),
        vitals=vitals,
        chief_complaint=case.get("chief_complaint", ""),
        allergies=medical_history.get("allergies", []),
        comorbidities=medical_history.get("conditions", []),
        contraindications=[],
        time_since_arrival_minutes=0.0,
    )


def build_episode_evidence(case: Dict[str, Any], actions: List[str]) -> EpisodeEvidence:
    raw_osce = case.get("raw_osce", {})
    test_results = raw_osce.get("Test_Results", case.get("test_results", {}))

    has_test_results = bool(test_results)
    has_imaging_results = False
    if isinstance(test_results, dict):
        for category in test_results.keys():
            category_lower = normalize_action_id(category)
            if any(img in category_lower for img in ["imaging", "xray", "x_ray", "ct", "mri", "ultrasound", "ecg", "ekg"]):
                has_imaging_results = True
                break

    physical_exam = raw_osce.get("Physical_Examination_Findings", {})
    has_physical_exam = bool(physical_exam)

    vitals = case.get("vitals", {})
    has_vitals = bool(vitals) and any(v is not None for v in vitals.values())

    medicals = case.get("medications") or raw_osce.get("Medications") or []
    has_medications = bool(medicals)

    has_history = bool(case.get("chief_complaint")) or bool(case.get("medical_history")) or bool(raw_osce.get("History"))

    ground_truth = case.get("ground_truth", {})
    has_diagnosis = isinstance(ground_truth, dict) and bool(ground_truth.get("diagnosis"))

    has_timestamps = any(
        key in case
        for key in ["timestamps", "timeline", "timepoints", "event_time", "event_times"]
    )

    return EpisodeEvidence(
        has_vitals=has_vitals,
        has_test_results=has_test_results,
        has_imaging_results=has_imaging_results,
        has_medications=has_medications,
        has_physical_exam=has_physical_exam,
        has_history=has_history,
        has_diagnosis=has_diagnosis,
        has_timestamps=has_timestamps,
        action_catalog=set(actions),
    )


def normalize_agentclinic_case(case: Dict[str, Any]) -> NormalizedEpisode:
    case_id = case.get("case_id", "unknown")
    source_benchmark = case.get("source_benchmark", "AgentClinic")

    actions = extract_actions_from_osce(case)
    patient_state = create_patient_state(case)
    evidence = build_episode_evidence(case, actions)

    warnings = []
    if not evidence.has_test_results:
        warnings.append("missing_test_results")
    if not evidence.has_vitals:
        warnings.append("missing_vitals")

    return NormalizedEpisode(
        case_id=case_id,
        source_benchmark=source_benchmark,
        patient_state=patient_state,
        actions=actions,
        evidence=evidence,
        warnings=warnings,
    )
