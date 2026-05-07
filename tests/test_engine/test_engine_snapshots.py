import json
from pathlib import Path

import pytest

from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns

ROOT_DIR = Path(__file__).resolve().parents[2]
GRAPHS_DIR = ROOT_DIR / "cpg_model" / "graphs"
SNAPSHOTS_DIR = Path(__file__).resolve().parents[1] / "snapshots"


GRAPH_CASES = [
    ("ssc_sepsis_hour1_bundle.yaml", "ssc_sepsis_hour1_bundle", "sepsis"),
    ("aha_chest_pain_evaluation.yaml", "aha_chest_pain_evaluation", "chest_pain"),
    ("aha_stroke_2019.yaml", "aha_stroke_2019", "stroke"),
    ("aha_heart_failure_2022.yaml", "aha_heart_failure_2022", "heart_failure"),
    ("kdigo_aki_full.yaml", "kdigo_aki_full", "aki"),
    ("kdigo_contrast_aki.yaml", "kdigo_contrast_aki", "contrast_aki"),
    ("ada_dka_management.yaml", "ada_dka_management", "dka"),
    ("universal_clinical_safety.yaml", "universal_clinical_safety", "universal"),
    # Phase 7 expansion graphs
    ("atrial_fibrillation.yaml", "atrial_fibrillation", "atrial_fibrillation"),
    ("cap_pneumonia.yaml", "cap_pneumonia", "cap_pneumonia"),
    ("copd_exacerbation.yaml", "copd_exacerbation", "copd_exacerbation"),
    ("gi_bleeding.yaml", "gi_bleeding", "gi_bleeding"),
    ("hypertensive_emergency.yaml", "hypertensive_emergency", "hypertensive_emergency"),
    ("pulmonary_embolism.yaml", "pulmonary_embolism", "pulmonary_embolism"),
]


def save_snapshot(graph_id: str, data: dict) -> None:
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOTS_DIR / f"{graph_id}.json"
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)


def load_snapshot(graph_id: str) -> dict:
    path = SNAPSHOTS_DIR / f"{graph_id}.json"
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def generate_or_compare_snapshot(graph_id: str, result: dict) -> None:
    path = SNAPSHOTS_DIR / f"{graph_id}.json"
    if not path.exists():
        save_snapshot(graph_id, result)
    expected = load_snapshot(graph_id)
    assert result == expected, f"Snapshot mismatch for {graph_id}"


def _base_patient_state(state_id: str, chief_complaint: str, working_diagnosis: str | None) -> PatientState:
    return PatientState(
        state_id=state_id,
        time_since_arrival_minutes=0,
        age=60,
        sex="M",
        weight_kg=70,
        vitals=VitalSigns(
            heart_rate=100,
            blood_pressure_systolic=100,
            blood_pressure_diastolic=60,
            respiratory_rate=20,
            temperature=37.5,
            oxygen_saturation=95,
            map_mmhg=60,
        ),
        chief_complaint=chief_complaint,
        working_diagnosis=working_diagnosis,
        contraindications=[],
        allergies=[],
        comorbidities=[],
    )


def _patient_for_domain(domain: str) -> PatientState:
    if domain == "sepsis":
        return _base_patient_state(
            "snapshot_sepsis",
            "fever and hypotension",
            "septic_shock",
        )

    if domain == "chest_pain":
        return _base_patient_state(
            "snapshot_chest_pain",
            "severe chest pain radiating to left arm",
            "stemi",
        )

    if domain == "stroke":
        return _base_patient_state(
            "snapshot_stroke",
            "sudden weakness and speech difficulty",
            "ischemic_stroke",
        )

    if domain == "heart_failure":
        patient = _base_patient_state(
            "snapshot_hf",
            "dyspnea and edema",
            "hfref",
        )
        patient.__dict__["bnp"] = 500
        patient.__dict__["ntprobnp"] = 2000
        return patient

    if domain == "aki":
        patient = _base_patient_state(
            "snapshot_aki",
            "decreased urine output",
            "aki",
        )
        patient.__dict__["creatinine"] = 2.0
        patient.__dict__["baseline"] = 1.0
        patient.__dict__["creatinine_increase"] = 1.0
        return patient

    if domain == "contrast_aki":
        patient = _base_patient_state(
            "snapshot_contrast_aki",
            "planned contrast study",
            "aki",
        )
        patient.__dict__["egfr"] = 25
        return patient

    if domain == "dka":
        patient = _base_patient_state(
            "snapshot_dka",
            "polyuria, polydipsia, abdominal pain",
            "dka",
        )
        patient.__dict__["serum_k"] = 4.0
        return patient

    if domain == "universal":
        return _base_patient_state(
            "snapshot_universal",
            "general malaise",
            "general",
        )

    if domain == "atrial_fibrillation":
        patient = _base_patient_state(
            "snapshot_af",
            "palpitations and irregular pulse",
            "atrial_fibrillation",
        )
        patient.vitals.heart_rate = 140
        return patient

    if domain == "cap_pneumonia":
        patient = _base_patient_state(
            "snapshot_cap",
            "cough, fever, dyspnea",
            "community_acquired_pneumonia",
        )
        patient.vitals.temperature = 39.2
        patient.vitals.respiratory_rate = 28
        patient.vitals.oxygen_saturation = 90
        return patient

    if domain == "copd_exacerbation":
        patient = _base_patient_state(
            "snapshot_copd",
            "worsening dyspnea and increased sputum",
            "copd_exacerbation",
        )
        patient.vitals.respiratory_rate = 30
        patient.vitals.oxygen_saturation = 88
        patient.comorbidities = ["copd"]
        return patient

    if domain == "gi_bleeding":
        patient = _base_patient_state(
            "snapshot_gib",
            "hematemesis and melena",
            "upper_gi_bleeding",
        )
        patient.vitals.heart_rate = 120
        patient.vitals.blood_pressure_systolic = 85
        patient.vitals.map_mmhg = 55
        return patient

    if domain == "hypertensive_emergency":
        patient = _base_patient_state(
            "snapshot_htn",
            "severe headache, blurred vision",
            "hypertensive_emergency",
        )
        patient.vitals.blood_pressure_systolic = 220
        patient.vitals.blood_pressure_diastolic = 130
        patient.vitals.map_mmhg = 160
        return patient

    if domain == "pulmonary_embolism":
        patient = _base_patient_state(
            "snapshot_pe",
            "acute dyspnea and pleuritic chest pain",
            "pulmonary_embolism",
        )
        patient.vitals.heart_rate = 115
        patient.vitals.oxygen_saturation = 89
        patient.vitals.blood_pressure_systolic = 90
        patient.vitals.map_mmhg = 58
        return patient

    raise ValueError(f"Unknown domain: {domain}")


@pytest.mark.parametrize("filename,graph_id,domain", GRAPH_CASES)
def test_graph_constraint_output_snapshot(filename: str, graph_id: str, domain: str) -> None:
    graph_path = GRAPHS_DIR / filename
    engine = CPGEngineFactory.load_from_file(str(graph_path))
    patient = _patient_for_domain(domain)

    output = engine.evaluate(patient)
    constraint_output = output.to_constraint_output()
    contract_output = engine.evaluate_constraints(patient)

    result = {
        "graph_id": graph_id,
        "entry_node": engine.graph.entry_node,
        "evaluated_node_id": output.current_node_id,
        "constraint_output": constraint_output.model_dump(),
    }

    assert contract_output.model_dump() == constraint_output.model_dump()
    generate_or_compare_snapshot(graph_id, result)
