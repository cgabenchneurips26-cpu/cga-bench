from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

_LOINC_ACTION_MAP: Dict[str, Tuple[str, str]] = {
    "2823-3": ("check_potassium_level", "labs"),
    "6298-4": ("check_potassium_level", "labs"),
    "2160-0": ("assess_renal_function", "labs"),
    "38483-4": ("assess_renal_function", "labs"),
    "48642-3": ("assess_renal_function", "labs"),
    "62238-1": ("assess_renal_function", "labs"),
    "3094-0": ("assess_renal_function", "labs"),
    "6299-2": ("assess_renal_function", "labs"),
    "4548-4": ("retrieve_hba1c", "labs"),
    "15577-2": ("retrieve_hba1c", "labs"),
    "2345-7": ("retrieve_glucose_value", "labs"),
    "14749-6": ("retrieve_glucose_value", "labs"),
    "11524-6": ("order_ecg", "imaging"),
    "34534-8": ("order_ecg", "imaging"),
    "718-7": ("check_hemoglobin", "labs"),
    "26464-8": ("check_wbc", "labs"),
    "777-3": ("check_platelet_count", "labs"),
    "1742-6": ("check_alt", "labs"),
    "1920-8": ("check_ast", "labs"),
    "1975-2": ("check_bilirubin", "labs"),
    "2093-3": ("check_cholesterol", "labs"),
    "33914-3": ("assess_renal_function", "labs"),
    "14959-1": ("check_microalbumin", "labs"),
    "2085-9": ("check_hdl", "labs"),
    "13457-7": ("check_ldl", "labs"),
    "2571-8": ("check_triglycerides", "labs"),
    "55284-4": ("measure_blood_pressure", "vitals"),
    "8310-5": ("measure_body_temperature", "vitals"),
    "8867-4": ("measure_heart_rate", "vitals"),
    "9279-1": ("measure_respiratory_rate", "vitals"),
    "2708-6": ("measure_oxygen_saturation", "vitals"),
    "29463-7": ("measure_body_weight", "vitals"),
    "8302-2": ("measure_body_height", "vitals"),
    "39156-5": ("calculate_bmi", "vitals"),
}

_RESOURCE_TYPE_DISPLAY_MAP: Dict[str, str] = {
    "MG": "check_magnesium_level",
    "GLU": "retrieve_glucose_value",
    "ECG": "order_ecg",
    "EKG": "order_ecg",
    "CBC": "order_cbc",
    "CMP": "order_cmp",
    "BMP": "order_bmp",
    "TSH": "check_thyroid",
    "HBA1C": "retrieve_hba1c",
}


def _extract_codes_from_codeable_concept(concept: Dict[str, Any]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    codings = concept.get("coding", [])
    if not isinstance(codings, list):
        return pairs
    for coding in codings:
        if not isinstance(coding, dict):
            continue
        code = str(coding.get("code", ""))
        display = str(coding.get("display", ""))
        if code:
            pairs.append((code, display))
    return pairs


def _resolve_action_from_codes(
    code_pairs: List[Tuple[str, str]],
) -> Tuple[str | None, str | None]:
    for code, display in code_pairs:
        if code in _LOINC_ACTION_MAP:
            return _LOINC_ACTION_MAP[code]
        display_upper = display.upper()
        if display_upper in _RESOURCE_TYPE_DISPLAY_MAP:
            return (_RESOURCE_TYPE_DISPLAY_MAP[display_upper], "labs")

    for code, display in code_pairs:
        loinc_prefix = code.split(":")[1] if ":" in code else code
        if loinc_prefix in _LOINC_ACTION_MAP:
            return _LOINC_ACTION_MAP[loinc_prefix]

    return None, None


def parse_fhir_patient(resource: Dict[str, Any]) -> Tuple[List[str], Dict[str, bool]]:
    actions: List[str] = []
    evidence: Dict[str, bool] = {}

    name = resource.get("name", [])
    birth_date = resource.get("birthDate")
    identifier = resource.get("identifier", [])

    if name and birth_date:
        actions.append("search_by_name_dob")
    elif identifier:
        actions.append("get_patient_birthdate")
    else:
        actions.append("search_by_name_dob")

    evidence["history"] = True
    return actions, evidence


def parse_fhir_observation(
    resource: Dict[str, Any], method: str = "GET",
) -> Tuple[List[str], Dict[str, bool]]:
    actions: List[str] = []
    evidence: Dict[str, bool] = {}

    if method == "POST":
        actions.append("post_vital_sign")
        evidence["vitals"] = True
        return actions, evidence

    code_concept = resource.get("code", {})
    if not isinstance(code_concept, dict):
        code_concept = {}
    code_pairs = _extract_codes_from_codeable_concept(code_concept)

    action, evidence_key = _resolve_action_from_codes(code_pairs)
    if action:
        actions.append(action)
        if evidence_key:
            evidence[evidence_key] = True
        return actions, evidence

    categories = resource.get("category", [])
    if isinstance(categories, list):
        for cat in categories:
            if not isinstance(cat, dict):
                continue
            cat_codings = cat.get("coding", [])
            if isinstance(cat_codings, list):
                for cc in cat_codings:
                    if isinstance(cc, dict) and str(cc.get("code", "")).lower() == "vital-signs":
                        actions.append("query_vital_signs")
                        evidence["vitals"] = True
                        return actions, evidence

    actions.append("query_lab_results")
    evidence["labs"] = True
    return actions, evidence


def parse_fhir_service_request(
    resource: Dict[str, Any],
) -> Tuple[List[str], Dict[str, bool]]:
    actions: List[str] = ["create_referral_with_given_text"]
    evidence: Dict[str, bool] = {}

    code_concept = resource.get("code", {})
    if isinstance(code_concept, dict):
        code_pairs = _extract_codes_from_codeable_concept(code_concept)
        for code, display in code_pairs:
            upper = (code + display).upper()
            if "ECG" in upper or "EKG" in upper:
                actions.append("order_ecg")
                evidence["imaging"] = True
                break

    return actions, evidence


def parse_fhir_medication_request(
    resource: Dict[str, Any],
) -> Tuple[List[str], Dict[str, bool]]:
    actions: List[str] = []
    evidence: Dict[str, bool] = {"medications": True}

    med_concept = resource.get("medicationCodeableConcept", {})
    if isinstance(med_concept, dict):
        code_pairs = _extract_codes_from_codeable_concept(med_concept)
        if code_pairs:
            _, display = code_pairs[0]
            safe_name = re.sub(r"[^a-z0-9_]", "_", display.lower()).strip("_")
            actions.append(f"prescribe_{safe_name}" if safe_name else "prescribe_medication")
        else:
            actions.append("prescribe_medication")
    else:
        actions.append("prescribe_medication")

    return actions, evidence


def parse_fhir_condition(
    resource: Dict[str, Any],
) -> Tuple[List[str], Dict[str, bool]]:
    actions: List[str] = ["document_diagnosis"]
    evidence: Dict[str, bool] = {"diagnosis": True}
    return actions, evidence


def parse_fhir_diagnostic_report(
    resource: Dict[str, Any],
) -> Tuple[List[str], Dict[str, bool]]:
    actions: List[str] = ["review_diagnostic_report"]
    evidence: Dict[str, bool] = {}

    code_concept = resource.get("code", {})
    if isinstance(code_concept, dict):
        code_pairs = _extract_codes_from_codeable_concept(code_concept)
        action, evidence_key = _resolve_action_from_codes(code_pairs)
        if action:
            actions.append(action)
        if evidence_key:
            evidence[evidence_key] = True
    else:
        evidence["labs"] = True

    return actions, evidence


_RESOURCE_PARSERS = {
    "Patient": parse_fhir_patient,
    "Observation": parse_fhir_observation,
    "ServiceRequest": parse_fhir_service_request,
    "MedicationRequest": parse_fhir_medication_request,
    "Condition": parse_fhir_condition,
    "DiagnosticReport": parse_fhir_diagnostic_report,
}


def parse_fhir_resource(
    resource: Dict[str, Any], method: str = "GET",
) -> Tuple[List[str], Dict[str, bool]]:
    resource_type = resource.get("resourceType", "")
    parser = _RESOURCE_PARSERS.get(resource_type)
    if parser is None:
        return [], {}

    if resource_type == "Observation":
        return parse_fhir_observation(resource, method)
    return parser(resource)


def parse_fhir_bundle(bundle: Dict[str, Any]) -> Tuple[List[str], Dict[str, bool]]:
    all_actions: List[str] = []
    all_evidence: Dict[str, bool] = {}

    entries = bundle.get("entry", [])
    if not isinstance(entries, list):
        return all_actions, all_evidence

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        resource = entry.get("resource", {})
        if not isinstance(resource, dict):
            continue
        request = entry.get("request", {})
        method = str(request.get("method", "GET")).upper() if isinstance(request, dict) else "GET"

        actions, evidence = parse_fhir_resource(resource, method)
        all_actions.extend(actions)
        for key, val in evidence.items():
            if val:
                all_evidence[key] = True

    return all_actions, all_evidence


def try_parse_fhir_payload(payload: Any) -> Tuple[List[str], Dict[str, bool]] | None:
    if not isinstance(payload, dict):
        return None

    if payload.get("resourceType") == "Bundle":
        return parse_fhir_bundle(payload)

    if "resourceType" in payload:
        return parse_fhir_resource(payload)

    return None
