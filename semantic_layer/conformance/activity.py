"""
EpisodeNorm -> Activity abstraction for conformance checking.

Enhanced with:
- Case-insensitive FHIR resource type normalization
- Extended HTTP method support (PUT/PATCH/DELETE)
- CodeVocabulary fallback for broad LOINC code family matching
- Optional neural grounding fallback for unknown codes
- Activity confidence scoring
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qs, unquote, urlparse

logger = logging.getLogger(__name__)


@dataclass
class ActivityExtractionConfig:
    """Configuration for enhanced activity extraction. All optional for backward compat."""
    enable_neural_fallback: bool = False
    neural_confidence_threshold: float = 0.75
    enable_extended_vocabulary: bool = True
    enable_confidence_scoring: bool = False
    # Ontology integration (subsumption-based normalization)
    enable_ontology: bool = False
    ontology_domain: Optional[str] = None  # e.g., "sepsis", "chest_pain", or None for unified


@dataclass
class ActivityEvent:
    name: str
    timestamp_min: float
    raw_event: Dict[str, Any]
    confidence: float = 1.0
    match_source: str = "exact"


FHIR_ACTIVITY_MAP = {
    ("POST", "ServiceRequest"): "ORDER_TEST",
    ("POST", "MedicationRequest"): "PRESCRIBE",
    ("POST", "Observation"): "OBSERVE_RESULT",
    ("POST", "Condition"): "DIAGNOSE",
    ("POST", "Procedure"): "PERFORM_PROCEDURE",
    ("GET", "Observation"): "QUERY_OBSERVATION",
    ("GET", "Patient"): "QUERY_PATIENT",
    ("GET", "MedicationRequest"): "QUERY_MEDICATION",
    ("GET", "Condition"): "QUERY_CONDITION",
    ("GET", "ServiceRequest"): "QUERY_SERVICEREQUEST",
    # Extended: Update/Modify operations
    ("PUT", "MedicationRequest"): "UPDATE_MEDICATION",
    ("PATCH", "MedicationRequest"): "UPDATE_MEDICATION",
    ("PUT", "ServiceRequest"): "UPDATE_ORDER",
    ("PATCH", "ServiceRequest"): "UPDATE_ORDER",
    ("PUT", "Condition"): "UPDATE_DIAGNOSIS",
    ("PATCH", "Condition"): "UPDATE_DIAGNOSIS",
    # Extended: Cancel/Delete operations
    ("DELETE", "MedicationRequest"): "CANCEL_MEDICATION",
    ("DELETE", "ServiceRequest"): "CANCEL_ORDER",
    # Extended: Diagnostic report
    ("GET", "DiagnosticReport"): "QUERY_DIAGNOSTIC_REPORT",
    ("POST", "DiagnosticReport"): "OBSERVE_REPORT",
}

# Case-insensitive resource type normalization
_RESOURCE_TYPE_CANONICAL = {
    "patient": "Patient",
    "observation": "Observation",
    "servicerequest": "ServiceRequest",
    "medicationrequest": "MedicationRequest",
    "condition": "Condition",
    "procedure": "Procedure",
    "diagnosticreport": "DiagnosticReport",
    "imagingstudy": "ImagingStudy",
    "allergyintolerance": "AllergyIntolerance",
    "encounter": "Encounter",
    "medication": "Medication",
    "medicationadministration": "MedicationAdministration",
    "careplan": "CarePlan",
    "careteam": "CareTeam",
    "device": "Device",
    "immunization": "Immunization",
    "documentreference": "DocumentReference",
    "bundle": "Bundle",
}


def _normalize_resource_type(raw: Optional[str]) -> Optional[str]:
    """Normalize resource type to canonical PascalCase."""
    if not raw:
        return None
    return _RESOURCE_TYPE_CANONICAL.get(raw.lower().strip(), raw)

ECG_CODES = {"11524-6", "34534-8", "ECG", "EKG"}
TROPONIN_CODES = {"TROPONIN", "TROPONIN-I", "TROPONIN-T"}
GLUCOSE_CODES = {"GLU", "GLUCOSE"}
HBA1C_CODES = {"4548-4", "15577-2", "LOINC:15577-2", "HBA1C", "A1C"}
POTASSIUM_CODES = {"2823-3", "POTASSIUM", "K"}
MAGNESIUM_CODES = {"MG", "24321-2", "MAGNESIUM"}
LACTATE_CODES = {"2524-7", "LACTATE"}


def extract_activity_events(
    events: Iterable[Dict[str, Any]],
    activity_aliases: Optional[Dict[str, str]] = None,
    config: Optional[ActivityExtractionConfig] = None,
) -> Tuple[List[ActivityEvent], List[Dict[str, Any]]]:
    activity_aliases = activity_aliases or {}
    cfg = config or ActivityExtractionConfig()
    raw_events = list(events)
    activity_events: List[ActivityEvent] = []
    timestamps = [event.get("timestamp_ms") for event in raw_events if event.get("timestamp_ms") is not None]
    base_ms = min(timestamps) if timestamps else None

    # Lazy-init vocabulary, neural backend, and ontology matcher
    vocabulary = _get_vocabulary() if cfg.enable_extended_vocabulary else None
    neural_backend = None
    ontology_matcher = _get_ontology_matcher(cfg) if cfg.enable_ontology else None

    for idx, event in enumerate(raw_events):
        explicit_activity = event.get("activity")
        if explicit_activity:
            timestamp_min = _resolve_timestamp_min(event, idx, base_ms)
            canonical = activity_aliases.get(explicit_activity, explicit_activity)
            confidence = 1.0
            match_source = "exact"
            # Ontology normalization for explicit activities
            if ontology_matcher:
                ont_result = ontology_matcher.match(canonical)
                if ont_result.matched:
                    canonical = ont_result.concept_id
                    confidence = ont_result.confidence
                    match_source = f"ontology_{ont_result.strategy}"
            activity_events.append(
                ActivityEvent(
                    name=canonical, timestamp_min=timestamp_min,
                    raw_event=event, confidence=confidence,
                    match_source=match_source,
                )
            )
            continue
        tool_call = event.get("tool_call") or {}
        method = (tool_call.get("method") or "").upper()
        url = tool_call.get("url") or ""
        payload = tool_call.get("payload") or {}

        resource_type, codes = parse_fhir_call(url, payload)
        activity, confidence, match_source = _map_activity_enhanced(
            method, resource_type, codes, vocabulary, neural_backend, cfg
        )
        if not activity:
            continue

        timestamp_min = _resolve_timestamp_min(event, idx, base_ms)
        canonical = activity_aliases.get(activity, activity)
        activity_events.append(ActivityEvent(
            name=canonical,
            timestamp_min=timestamp_min,
            raw_event=event,
            confidence=confidence,
            match_source=match_source,
        ))

    activity_events.sort(key=lambda e: e.timestamp_min)
    return activity_events, raw_events


def _resolve_timestamp_min(event: Dict[str, Any], idx: int, base_ms: Optional[int]) -> float:
    if event.get("timestamp_ms") is not None and base_ms is not None:
        return (event["timestamp_ms"] - base_ms) / 60000.0
    if event.get("event_index") is not None:
        return float(event["event_index"])
    return float(idx)


def parse_fhir_call(url: str, payload: Dict[str, Any]) -> Tuple[Optional[str], List[str]]:
    resource_type = payload.get("resourceType")
    codes: List[str] = []
    if url:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/") if path else []
        # Strip known prefixes: "fhir", "api/v1/fhir", etc.
        while parts and parts[0].lower() in ("fhir", "api", "v1", "v2", "r4"):
            parts = parts[1:]
        if parts:
            # Strategy 1: First segment that looks like a FHIR resource type
            url_resource = _extract_resource_from_path(parts)
            resource_type = resource_type or url_resource
        query = parse_qs(parsed.query, keep_blank_values=True)
        codes.extend(_extract_token_codes(query.get("code", [])))
    if isinstance(payload.get("code"), dict):
        codings = payload["code"].get("coding", []) or []
        if codings:
            code_value = codings[0].get("code") or codings[0].get("display")
            if code_value:
                codes.append(str(code_value))
    # Normalize resource type (case-insensitive)
    resource_type = _normalize_resource_type(resource_type)
    return resource_type, codes


# Backward-compat alias
_parse_fhir_call = parse_fhir_call


def _extract_resource_from_path(parts: List[str]) -> Optional[str]:
    """Extract FHIR resource type from URL path segments."""
    for part in parts:
        if not part:
            continue
        # Check if it's a known resource type (case-insensitive)
        normalized = _normalize_resource_type(part)
        if normalized and normalized != part.lower():
            return normalized
        # Check if it looks like a PascalCase resource type (not a numeric ID)
        if part[0].isupper() and not part.isdigit():
            return part
    return None


def _map_activity(method: str, resource_type: Optional[str], codes: List[str]) -> Optional[str]:
    """Original activity mapping (kept for backward compat)."""
    if not method or not resource_type:
        return None
    code_upper = {code.upper() for code in codes}
    if resource_type in {"ServiceRequest", "Observation"} and code_upper.intersection(ECG_CODES):
        return "ORDER_ECG" if method == "POST" else "QUERY_ECG"
    if resource_type == "Observation" and method == "GET":
        if code_upper.intersection(HBA1C_CODES):
            return "QUERY_HBA1C"
        if code_upper.intersection(GLUCOSE_CODES):
            return "QUERY_GLUCOSE"
        if code_upper.intersection(POTASSIUM_CODES):
            return "QUERY_POTASSIUM"
        if code_upper.intersection(MAGNESIUM_CODES):
            return "QUERY_MAGNESIUM"
        if code_upper.intersection(LACTATE_CODES):
            return "QUERY_LACTATE"
        if code_upper.intersection(TROPONIN_CODES):
            return "QUERY_TROPONIN"
    return FHIR_ACTIVITY_MAP.get((method, resource_type))


def _map_activity_enhanced(
    method: str,
    resource_type: Optional[str],
    codes: List[str],
    vocabulary: Optional[Any] = None,
    neural_backend: Optional[Any] = None,
    config: Optional[ActivityExtractionConfig] = None,
) -> Tuple[Optional[str], float, str]:
    """Enhanced activity mapping with vocabulary and neural fallback.

    Returns (activity_name, confidence, match_source).
    """
    # Step 1: Try exact match (original logic)
    exact = _map_activity(method, resource_type, codes)
    if exact:
        return exact, 1.0, "exact"

    # Step 2: Try extended vocabulary (code families)
    if vocabulary and codes:
        code_set = set(codes)
        match = vocabulary.match(code_set, method, resource_type)
        if match:
            activity, confidence, family_id = match
            logger.debug(f"CodeVocabulary match: {codes} -> {activity} (family={family_id})")
            return activity, confidence, "code_family"

    # Step 3: Neural fallback (opt-in, lazy)
    # Reserved for future integration with NeuralGroundingBackend

    return None, 0.0, "none"


_vocabulary_instance: Optional[Any] = None
_ontology_matcher_cache: Dict[str, Any] = {}


def _get_vocabulary():
    """Get or create singleton CodeVocabulary instance."""
    global _vocabulary_instance
    if _vocabulary_instance is None:
        from .activity_codes import CodeVocabulary
        _vocabulary_instance = CodeVocabulary()
    return _vocabulary_instance


def _get_ontology_matcher(config: ActivityExtractionConfig):
    """Get or create cached OntologyMatcher for the specified domain."""
    domain_key = config.ontology_domain or "__unified__"
    if domain_key not in _ontology_matcher_cache:
        try:
            from ..ontology.domain_hierarchies import (
                get_ontology_matcher,
                get_unified_matcher,
            )
            if config.ontology_domain:
                _ontology_matcher_cache[domain_key] = get_ontology_matcher(config.ontology_domain)
            else:
                _ontology_matcher_cache[domain_key] = get_unified_matcher()
        except Exception as e:
            logger.warning(f"Failed to initialize ontology matcher: {e}")
            return None
    return _ontology_matcher_cache.get(domain_key)


def derive_flags(
    events: Iterable[Dict[str, Any]],
    derived_specs: Iterable[Dict[str, Any]],
) -> Dict[str, bool]:
    derived = {spec["flag_id"]: False for spec in derived_specs}
    if not derived_specs:
        return derived

    for event in events:
        tool_call = event.get("tool_call") or {}
        method = (tool_call.get("method") or "").upper()
        url = tool_call.get("url") or ""
        payload = tool_call.get("payload") or {}
        resource_type, codes = parse_fhir_call(url, payload)
        response_payload = _parse_response_payload(event.get("response_text"))
        response_bundle = _extract_bundle_meta(response_payload)
        response_error = _detect_response_error(event.get("response_text"), response_payload)

        for spec in derived_specs:
            flag_id = spec["flag_id"]
            if derived.get(flag_id):
                continue
            if spec.get("source") == "request":
                if _match_request_flag(spec, method, resource_type, codes):
                    derived[flag_id] = True
                continue
            if spec.get("source") == "missing":
                if _match_missing_flag(spec, response_bundle, resource_type, codes):
                    derived[flag_id] = True
                continue
            if spec.get("source") == "error":
                if response_error and _match_request_flag(spec, "GET", resource_type, codes):
                    derived[flag_id] = True
                continue

            for result in event.get("new_results") or []:
                resource = result.get("resourceType")
                code = result.get("code")
                value = result.get("value")
                if resource != spec["resource_type"]:
                    continue
                if spec.get("code") and not _match_code(spec.get("code"), code):
                    continue
                if _compare_value(value, spec.get("op"), spec.get("value")):
                    derived[flag_id] = True
                    break
    return derived


def _compare_value(value: Any, op: Optional[str], target: Optional[float]) -> bool:
    if op is None:
        return False
    if op == "exists":
        return value is not None
    if target is None:
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    if op == ">":
        return numeric > target
    if op == ">=":
        return numeric >= target
    if op == "<":
        return numeric < target
    if op == "<=":
        return numeric <= target
    if op == "==":
        return numeric == target
    return False


def _extract_token_codes(values: Iterable[str]) -> List[str]:
    codes: List[str] = []
    for raw in values:
        if raw is None:
            continue
        for chunk in str(raw).split(","):
            chunk = unquote(chunk.strip())
            if not chunk:
                continue
            if "|" in chunk:
                _, code = chunk.split("|", 1)
                if code:
                    codes.append(code)
            else:
                codes.append(chunk)
    return codes


def _match_code(spec_code: Optional[str], actual_code: Optional[str]) -> bool:
    if not spec_code or not actual_code:
        return False
    if "|" in spec_code:
        _, code = spec_code.split("|", 1)
        return code.strip().upper() == str(actual_code).strip().upper()
    return spec_code.strip().upper() == str(actual_code).strip().upper()


def _match_request_flag(spec: Dict[str, Any], method: str, resource_type: Optional[str], codes: List[str]) -> bool:
    if spec.get("resource_type") != resource_type:
        return False
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return False
    if not spec.get("code"):
        return True
    spec_code = str(spec.get("code")).strip().upper()
    code_set = {code.strip().upper() for code in codes}
    if "|" in spec_code:
        spec_code = spec_code.split("|", 1)[1]
    return spec_code in code_set


def _parse_response_payload(response_text: Optional[str]) -> Optional[Dict[str, Any]]:
    if not response_text:
        return None
    prefix = "Here is the response from the GET request:\n"
    text = response_text
    if text.startswith(prefix):
        text = text[len(prefix):]
    if "Please call FINISH" in text:
        text = text.split("Please call FINISH")[0]
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_bundle_meta(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"type": None, "total": None, "entry_count": None}
    bundle_type = payload.get("type")
    total = payload.get("total")
    entry = payload.get("entry")
    entry_count = len(entry) if isinstance(entry, list) else None
    return {"type": bundle_type, "total": total, "entry_count": entry_count}


def _match_missing_flag(
    spec: Dict[str, Any],
    bundle_meta: Dict[str, Any],
    resource_type: Optional[str],
    codes: List[str],
) -> bool:
    if not bundle_meta:
        return False
    if spec.get("resource_type") != resource_type:
        return False
    if spec.get("code") and not _match_request_flag(spec, "GET", resource_type, codes):
        return False
    total = bundle_meta.get("total")
    entry_count = bundle_meta.get("entry_count")
    if bundle_meta.get("type") != "searchset":
        return False
    if total == 0:
        return True
    if total is None and entry_count == 0:
        return True
    return False


def _detect_response_error(response_text: Optional[str], payload: Optional[Dict[str, Any]]) -> bool:
    if isinstance(payload, dict) and payload.get("resourceType") == "OperationOutcome":
        return True
    if response_text:
        text = response_text.strip()
        if text.startswith("Error in sending the GET request"):
            return True
        if "Client Error" in text or "Server Error" in text:
            return True
    return False


def classify_response_error(
    response_text: Optional[str],
    payload: Optional[Dict[str, Any]],
) -> Optional["ClassifiedError"]:  # noqa: F821
    """Classify a response error using the error taxonomy.

    Returns a ClassifiedError if an error is detected, None otherwise.
    Lazy-imports error_taxonomy to avoid circular dependencies.
    """
    from .error_taxonomy import classify_error
    return classify_error(response_text, payload)
