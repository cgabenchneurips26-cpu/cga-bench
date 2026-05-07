from typing import Any, Dict, List, Optional

from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns
from .models import EpisodeEvidence, NormalizedEpisode
from cga_bench.env.adapters.medchain_adapter import MedChainAdapter, MedChainStage


def normalize_medchain_case(case_id: str, case_data: Dict[str, Any]) -> NormalizedEpisode:
    adapter = MedChainAdapter()
    episode = adapter.parse_case(case_id, case_data)
    action_ids: List[str] = []
    for stage in episode.stages:
        if stage.stage == MedChainStage.REFERRAL:
            action_ids.append("consult")
        elif stage.stage == MedChainStage.HISTORY_TAKING:
            action_ids.append("take_history")
        elif stage.stage == MedChainStage.EXAMINATION:
            action_ids.append("order_exam")
        elif stage.stage == MedChainStage.DIAGNOSIS:
            action_ids.append("diagnose")
        elif stage.stage == MedChainStage.TREATMENT:
            action_ids.append("treat")

    vitals = VitalSigns()
    chief_complaint = ""
    if episode.stages:
        for stage in episode.stages:
            if stage.stage == MedChainStage.HISTORY_TAKING and stage.chief_complaint:
                chief_complaint = stage.chief_complaint
                break
    patient_state = PatientState(
        state_id=case_id,
        age=0,
        sex="U",
        vitals=vitals,
        chief_complaint=chief_complaint,
    )

    has_history = any(stage.stage == MedChainStage.HISTORY_TAKING for stage in episode.stages)
    has_physical_exam = any(stage.stage == MedChainStage.EXAMINATION and stage.physical_exam for stage in episode.stages)
    has_test_results = any(stage.stage == MedChainStage.EXAMINATION and stage.auxiliary_exam for stage in episode.stages)
    has_diagnosis = any(stage.stage == MedChainStage.DIAGNOSIS and stage.diagnosis for stage in episode.stages)
    has_medications = any(stage.stage == MedChainStage.TREATMENT and stage.treatment_plan for stage in episode.stages)

    has_imaging_results = False
    for stage in episode.stages:
        if stage.stage == MedChainStage.EXAMINATION:
            for key in stage.auxiliary_exam.keys():
                if any(token in key for token in ["X-ray", "CT", "MRI", "超声", "X线片"]):
                    has_imaging_results = True
                    break

    evidence = EpisodeEvidence(
        has_vitals=bool(vitals.heart_rate or vitals.temperature),
        has_test_results=has_test_results,
        has_imaging_results=has_imaging_results,
        has_medications=has_medications,
        has_physical_exam=has_physical_exam,
        has_history=has_history,
        has_diagnosis=has_diagnosis,
        has_timestamps=True,
        action_catalog=set(action_ids),
        notes=["medchain_stage_based"],
    )

    tags = case_data.get("tags", {})
    departments = tags.get("科室", []) if isinstance(tags, dict) else []
    primary_department = departments[0] if departments else None
    guideline_id = (
        adapter.DEPARTMENT_GUIDELINE_MAPPING.get(primary_department)
        if primary_department
        else None
    )
    warnings: List[str] = []
    if not guideline_id:
        warnings.append("missing_guideline_mapping")

    return NormalizedEpisode(
        case_id=case_id,
        source_benchmark="MedChain",
        patient_state=patient_state,
        actions=action_ids,
        evidence=evidence,
        guideline_id=guideline_id,
        warnings=warnings,
    )
