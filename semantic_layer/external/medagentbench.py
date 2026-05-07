import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns
from ..action_normalizer import SemanticActionNormalizer
from .agentclinic import normalize_action_id
from .fhir_parser import try_parse_fhir_payload
from .models import EpisodeEvidence, NormalizedEpisode, EvaluableComplianceReport
from cga_bench.cpg_engine.engine import CPGEngineFactory
from .medagentbench_mappings import MEDAGENTBENCH_TASK_MAPPINGS

logger = logging.getLogger(__name__)


def extract_task_type(task_id: str) -> str:
    if task_id.startswith("task") and "_" in task_id:
        return task_id.split("_", 1)[0]
    return task_id


def build_placeholder_state(task: Dict[str, Any]) -> PatientState:
    instruction = task.get("instruction", "") or ""
    context = task.get("context", "") or ""
    text = f"{instruction} {context}".lower()

    age = 0
    age_match = re.search(r"(\d{1,3})\s*[-–]?\s*year\s*[-–]?\s*old", text)
    if age_match:
        parsed_age = int(age_match.group(1))
        if 0 < parsed_age < 120:
            age = parsed_age

    sex = "U"
    if "female" in text or "woman" in text:
        sex = "F"
    elif "male" in text or " man " in text:
        sex = "M"

    chief_complaint = instruction[:200] if instruction else ""

    known_comorbidities = [
        "diabetes", "hypertension", "copd", "asthma", "heart failure",
        "ckd", "chronic kidney disease", "atrial fibrillation",
    ]
    comorbidities = [c for c in known_comorbidities if c in text]

    allergy_list: List[str] = []
    allergy_match = re.search(r"allerg(?:y|ies)\s*(?:to|:)\s*([^.;]+)", text)
    if allergy_match:
        allergy_list = [a.strip() for a in allergy_match.group(1).split(",") if a.strip()]

    return PatientState(
        state_id=task.get("id", "unknown"),
        age=age,
        sex=sex,
        vitals=VitalSigns(),
        chief_complaint=chief_complaint,
        contraindications=[],
        allergies=allergy_list,
        comorbidities=comorbidities,
    )


def build_task_evidence(task: Dict[str, Any]) -> EpisodeEvidence:
    instruction = (task.get("instruction") or "").lower()
    context = (task.get("context") or "").lower()
    text = f"{instruction} {context}"

    has_history = any(token in text for token in ["name", "dob", "mrn", "patient", "history"])
    has_vitals = any(token in text for token in ["vital", "blood pressure", "heart rate", "bp", "hr"])
    has_test_results = any(token in text for token in ["lab", "cbc", "cmp", "bmp", "hba1c", "glucose", "electrolyte"])
    has_imaging_results = any(token in text for token in ["imaging", "x-ray", "xray", "ct", "mri", "ultrasound", "ecg", "ekg"])
    has_medications = any(token in text for token in ["medication", "drug", "dose", "antibiotic", "insulin", "potassium", "magnesium"])
    has_diagnosis = "diagnosis" in text or "diagnose" in text
    has_physical_exam = any(token in text for token in ["exam", "examination", "assess", "assessment"])
    has_timestamps = any(token in text for token in ["date", "time", "timestamp", "202", "2023", "2024"])

    return EpisodeEvidence(
        has_vitals=False,
        has_test_results=False,
        has_imaging_results=False,
        has_medications=False,
        has_physical_exam=False,
        has_history=False,
        has_diagnosis=False,
        has_timestamps=False,
        action_catalog=set(),
        notes=[
            "instruction_only_context",
            f"required_history:{has_history}",
            f"required_vitals:{has_vitals}",
            f"required_labs:{has_test_results}",
            f"required_imaging:{has_imaging_results}",
            f"required_medications:{has_medications}",
            f"required_exam:{has_physical_exam}",
            f"required_diagnosis:{has_diagnosis}",
            f"required_timestamps:{has_timestamps}",
        ],
    )


def normalize_medagentbench_task(task: Dict[str, Any]) -> NormalizedEpisode:
    task_id = task.get("id", "unknown")
    task_type = extract_task_type(task_id)
    mapping = MEDAGENTBENCH_TASK_MAPPINGS.get(task_type, {})
    required_actions = mapping.get("task_requires", [])
    required_actions = [normalize_action_id(action) for action in required_actions]

    evidence = build_task_evidence(task)
    evidence.action_catalog = set(required_actions)

    warnings = []
    if not mapping:
        warnings.append("missing_task_mapping")

    return NormalizedEpisode(
        case_id=task_id,
        source_benchmark="MedAgentBench",
        patient_state=build_placeholder_state(task),
        actions=[],
        evidence=evidence,
        guideline_id=mapping.get("guideline"),
        required_actions=required_actions,
        warnings=warnings,
    )


def _parse_observed_event_actions(events: List[Dict[str, Any]]) -> Tuple[List[str], Dict[str, bool]]:
    performed_actions: List[str] = []
    evidence_flags = {
        "vitals": False,
        "labs": False,
        "imaging": False,
        "medications": False,
        "exam": False,
        "history": False,
        "diagnosis": False,
        "timestamps": False,
        "state_delta": False,
    }
    code_action_map = {
        "MG": ("check_magnesium_level", "labs"),
        "2823-3": ("check_potassium_level", "labs"),
        "GLU": ("retrieve_glucose_value", "labs"),
        "4548-4": ("retrieve_hba1c", "labs"),
        "LOINC:15577-2": ("retrieve_hba1c", "labs"),
        "15577-2": ("retrieve_hba1c", "labs"),
        "2160-0": ("assess_renal_function", "labs"),
        "38483-4": ("assess_renal_function", "labs"),
        "48642-3": ("assess_renal_function", "labs"),
        "62238-1": ("assess_renal_function", "labs"),
        "3094-0": ("assess_renal_function", "labs"),
        "6299-2": ("assess_renal_function", "labs"),
        "11524-6": ("order_ecg", "imaging"),
        "34534-8": ("order_ecg", "imaging"),
        "ECG": ("order_ecg", "imaging"),
        "EKG": ("order_ecg", "imaging"),
    }

    for event in events:
        tool_call = event.get("tool_call") or {}
        method = (tool_call.get("method") or "").upper()
        payload = tool_call.get("payload")

        fhir_result = try_parse_fhir_payload(payload) if payload else None
        if fhir_result is not None:
            fhir_actions, fhir_evidence = fhir_result
            performed_actions.extend(fhir_actions)
            for key, val in fhir_evidence.items():
                if val and key in evidence_flags:
                    evidence_flags[key] = True
            if event.get("timestamp_ms") is not None:
                evidence_flags["timestamps"] = True
            if event.get("state_delta"):
                evidence_flags["state_delta"] = True
            continue

        url = tool_call.get("url") or ""
        if not url:
            if event.get("timestamp_ms") is not None:
                evidence_flags["timestamps"] = True
            if event.get("state_delta"):
                evidence_flags["state_delta"] = True
            continue

        parsed = urlparse(url)
        path = parsed.path.lower()
        query = parse_qs(parsed.query)
        code = query.get("code", [None])[0]
        if code:
            code = unquote(code)
        category = (query.get("category", [None])[0] or "").lower()

        if path.endswith("/patient"):
            if "family" in query and "given" in query and "birthdate" in query:
                performed_actions.append("search_by_name_dob")
            elif "identifier" in query:
                performed_actions.append("get_patient_birthdate")
            else:
                performed_actions.append("search_by_name_dob")
            evidence_flags["history"] = True

        if path.endswith("/observation"):
            if method == "POST":
                performed_actions.append("post_vital_sign")
                evidence_flags["vitals"] = True
            else:
                code_upper = (code or "").upper()
                if code_upper in code_action_map:
                    action, evidence_key = code_action_map[code_upper]
                    performed_actions.append(action)
                    evidence_flags[evidence_key] = True
                elif "ECG" in code_upper or "EKG" in code_upper:
                    performed_actions.append("order_ecg")
                    evidence_flags["imaging"] = True
                elif "vital-signs" in category:
                    performed_actions.append("query_vital_signs")
                    evidence_flags["vitals"] = True
                else:
                    performed_actions.append("query_lab_results")
                    evidence_flags["labs"] = True

        if path.endswith("/servicerequest") and method == "POST":
            performed_actions.append("create_referral_with_given_text")
            sr_payload = tool_call.get("payload") or {}
            code_block = sr_payload.get("code", {})
            codings = code_block.get("coding", []) if isinstance(code_block, dict) else []
            for coding in codings:
                code_value = str(coding.get("code") or coding.get("display") or "").upper()
                if "ECG" in code_value or "EKG" in code_value:
                    performed_actions.append("order_ecg")
                    evidence_flags["imaging"] = True

        if event.get("timestamp_ms") is not None:
            evidence_flags["timestamps"] = True
        if event.get("state_delta"):
            evidence_flags["state_delta"] = True

    return performed_actions, evidence_flags


def load_medagentbench_observed(path: Path) -> Dict[int, Dict[str, Any]]:
    observed: Dict[int, Dict[str, Any]] = {}
    if not path.exists():
        return observed

    with path.open("r") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            task_id = record.get("task_id")
            if task_id is None:
                continue
            try:
                task_index = int(task_id)
            except (TypeError, ValueError):
                continue
            events = record.get("events") or []
            actions, evidence_flags = _parse_observed_event_actions(events)
            state_delta_count = sum(1 for event in events if event.get("state_delta"))
            observed[task_index] = {
                "actions": actions,
                "evidence": evidence_flags,
                "event_count": len(events),
                "state_delta_count": state_delta_count,
                "observed_source": record.get("observed_source"),
            }

    return observed


def _infer_task_actions(task_type: str, performed_actions: List[str], task_text: str) -> List[str]:
    inferred = set(performed_actions)
    text = task_text.lower()

    if task_type == "task2" and "get_patient_birthdate" in inferred:
        inferred.add("calculate_age")

    if task_type == "task6":
        if "retrieve_glucose_values" in inferred:
            inferred.add("calculate_average")
        elif "retrieve_glucose_value" in inferred and "average" in text:
            inferred.add("calculate_average")

    return list(inferred)


def evaluate_medagentbench_task(
    task: Dict[str, Any],
    observed: Optional[Dict[str, Any]] = None,
) -> EvaluableComplianceReport:
    normalized = normalize_medagentbench_task(task)
    task_type = extract_task_type(normalized.case_id)
    mapping = MEDAGENTBENCH_TASK_MAPPINGS.get(task_type)

    default_evidence_flags = {
        "vitals": normalized.evidence.has_vitals,
        "labs": normalized.evidence.has_test_results,
        "imaging": normalized.evidence.has_imaging_results,
        "medications": normalized.evidence.has_medications,
        "exam": normalized.evidence.has_physical_exam,
        "history": normalized.evidence.has_history,
        "diagnosis": normalized.evidence.has_diagnosis,
        "timestamps": normalized.evidence.has_timestamps,
        "state_delta": False,
    }

    performed_actions = normalized.actions
    evidence_flags = default_evidence_flags
    observed_notes: List[str] = []
    if observed:
        performed_actions = observed.get("actions") or []
        evidence_flags = observed.get("evidence") or default_evidence_flags
        observed_source = observed.get("observed_source")
        if observed_source:
            observed_notes.append(f"observed_source:{observed_source}")
        observed_notes.append(f"observed_event_count:{observed.get('event_count', 0)}")
        task_text = f"{task.get('instruction', '')} {task.get('context', '')}"
        performed_actions = _infer_task_actions(task_type, performed_actions, task_text)
    required_actions = normalized.required_actions or []

    if not mapping:
        return EvaluableComplianceReport(
            case_id=normalized.case_id,
            guideline_id=None,
            mandatory_actions=[],
            performed_actions=performed_actions,
            evaluable_actions=[],
            not_observable_actions=[],
            satisfied_actions=[],
            violations=[],
            observability_index=0.0,
            compliance_score=0.0,
            evidence_summary={"performed_action_count": len(performed_actions), "evidence": evidence_flags},
            notes=normalized.warnings + observed_notes + ["unknown_task_mapping"],
        )

    mandatory_actions = mapping.get("cpg_mandatory", [])
    normalizer = SemanticActionNormalizer(llm_provider=None, use_llm_fallback=False)
    normalizer.register_vocabulary("medagentbench", mandatory_actions)
    normalized_performed = []
    for action in performed_actions:
        result = normalizer.normalize(action, domain="medagentbench")
        normalized_performed.append(result)
    normalized_required = []
    for action in required_actions:
        result = normalizer.normalize(action, domain="medagentbench")
        normalized_required.append(result)
    performed_norm = {normalize_action_id(action) for action in performed_actions}
    required_norm = {normalize_action_id(action) for action in required_actions}

    forbidden_actions: List[str] = []
    required_prior_actions: Dict[str, List[str]] = {}
    deadlines: Dict[str, float] = {}
    guideline_path = mapping.get("guideline")
    if guideline_path:
        try:
            engine = CPGEngineFactory.load_from_file(str(Path(guideline_path)))
            constraints = engine.evaluate(normalized.patient_state)
            forbidden_actions = list(constraints.forbidden_actions)
            required_prior_actions = constraints.required_prior_actions
            deadlines = constraints.deadlines
        except Exception:
            forbidden_actions = []
            required_prior_actions = {}
            deadlines = {}

    evaluable_actions: List[str] = []
    not_observable_actions: List[str] = []
    satisfied_actions: List[str] = []
    required_satisfied_actions: List[str] = []
    violations: List[Dict[str, Any]] = []

    for mandatory in mandatory_actions:
        action_norm = normalize_action_id(mandatory)
        # Reuse evidence checks from action naming alone.
        if action_norm.startswith("check_") and evidence_flags["labs"]:
            evaluable_actions.append(mandatory)
        elif action_norm.startswith("order_") and (evidence_flags["labs"] or evidence_flags["imaging"]):
            evaluable_actions.append(mandatory)
        elif action_norm.startswith("assess_") and (evidence_flags["history"] or evidence_flags["labs"]):
            evaluable_actions.append(mandatory)
        elif action_norm.startswith("verify_") and evidence_flags["history"]:
            evaluable_actions.append(mandatory)
        elif action_norm in {"document_vitals", "verify_accuracy"} and evidence_flags["vitals"]:
            evaluable_actions.append(mandatory)
        elif action_norm == "view_lab_results" and evidence_flags["labs"]:
            evaluable_actions.append(mandatory)
        else:
            not_observable_actions.append(mandatory)
            continue

        matched = False
        if action_norm in performed_norm:
            matched = True
        else:
            for result in normalized_performed:
                if result.normalized_action == mandatory and result.confidence >= 0.7:
                    matched = True
                    break

        if matched:
            satisfied_actions.append(mandatory)
        else:
            violations.append(
                {
                    "type": "OMISSION",
                    "action": mandatory,
                    "description": f"evaluable_mandatory_missing:{mandatory}",
                }
            )

    for forbidden in forbidden_actions:
        if normalize_action_id(forbidden) in performed_norm:
            violations.append(
                {
                    "type": "COMMISSION",
                    "action": forbidden,
                    "description": f"forbidden_action_performed:{forbidden}",
                }
            )

    for mandatory in mandatory_actions:
        action_norm = normalize_action_id(mandatory)
        required_matched = False
        if action_norm in required_norm:
            required_matched = True
        else:
            for result in normalized_required:
                if result.normalized_action == mandatory and result.confidence >= 0.7:
                    required_matched = True
                    break
        if required_matched:
            required_satisfied_actions.append(mandatory)

    for action, priors in required_prior_actions.items():
        action_norm = normalize_action_id(action)
        if action_norm in performed_norm:
            missing_priors = [
                prior for prior in priors if normalize_action_id(prior) not in performed_norm
            ]
            if missing_priors:
                violations.append(
                    {
                        "type": "SEQUENCE",
                        "action": action,
                        "description": f"missing_required_priors:{','.join(missing_priors)}",
                    }
                )

    observability_index = (
        len(evaluable_actions) / len(mandatory_actions) if mandatory_actions else 1.0
    )
    compliance_score = (
        len(satisfied_actions) / len(evaluable_actions) if evaluable_actions else 0.0
    )
    required_compliance_score = (
        len(required_satisfied_actions) / len(mandatory_actions) if mandatory_actions else 1.0
    )

    notes = normalized.warnings[:] + observed_notes
    gap_reason = mapping.get("gap_reason")
    if gap_reason:
        notes.append(f"gap_reason:{gap_reason}")
    if deadlines and not any("required_timestamps:True" in note for note in normalized.evidence.notes):
        notes.append("timing_not_evaluable")

    return EvaluableComplianceReport(
        case_id=normalized.case_id,
        guideline_id=mapping.get("guideline"),
        mandatory_actions=mandatory_actions,
        performed_actions=performed_actions,
        required_actions=required_actions,
        evaluable_actions=evaluable_actions,
        not_observable_actions=not_observable_actions,
        satisfied_actions=satisfied_actions,
        required_satisfied_actions=required_satisfied_actions,
        violations=violations,
        observability_index=observability_index,
        compliance_score=compliance_score,
        required_compliance_score=required_compliance_score,
        forbidden_actions=forbidden_actions,
        required_prior_actions=required_prior_actions,
        deadlines=deadlines,
        evidence_summary={
            "performed_action_count": len(performed_actions),
            "observed": evidence_flags,
            "required": {
                "vitals": any("required_vitals:True" in note for note in normalized.evidence.notes),
                "labs": any("required_labs:True" in note for note in normalized.evidence.notes),
                "imaging": any("required_imaging:True" in note for note in normalized.evidence.notes),
                "medications": any("required_medications:True" in note for note in normalized.evidence.notes),
                "exam": any("required_exam:True" in note for note in normalized.evidence.notes),
                "history": any("required_history:True" in note for note in normalized.evidence.notes),
                "diagnosis": any("required_diagnosis:True" in note for note in normalized.evidence.notes),
                "timestamps": any("required_timestamps:True" in note for note in normalized.evidence.notes),
            },
        },
        notes=notes,
    )


def evaluate_medagentbench_tasks(
    tasks: List[Dict[str, Any]],
    observed_map: Optional[Dict[int, Dict[str, Any]]] = None,
) -> List[EvaluableComplianceReport]:
    reports: List[EvaluableComplianceReport] = []
    for idx, task in enumerate(tasks):
        observed = observed_map.get(idx) if observed_map else None
        reports.append(evaluate_medagentbench_task(task, observed))
    return reports
