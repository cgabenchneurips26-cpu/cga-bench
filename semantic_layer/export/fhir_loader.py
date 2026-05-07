from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..conformance.activity import ActivityEvent


_RESOURCE_TYPE_MAP = {
    "Encounter": "encounter",
    "MedicationRequest": "give_medication",
    "MedicationAdministration": "give_medication",
    "Procedure": "procedure",
    "Observation": "order_lab",
    "DiagnosticReport": "order_imaging",
    "Condition": "assess",
    "Immunization": "give_immunization",
    "CarePlan": "plan",
    "ServiceRequest": "order",
    "AllergyIntolerance": "assess_allergy",
}


def load_fhir_bundle(path: str | Path) -> List[ActivityEvent]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_fhir_bundle(data)


def parse_fhir_bundle(bundle: Dict[str, Any]) -> List[ActivityEvent]:
    if bundle.get("resourceType") != "Bundle":
        raise ValueError(f"Expected FHIR Bundle, got {bundle.get('resourceType')}")

    events: List[ActivityEvent] = []
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        event = _resource_to_event(resource)
        if event:
            events.append(event)

    return sorted(events, key=lambda e: e.timestamp_min)


def _resource_to_event(resource: Dict[str, Any]) -> Optional[ActivityEvent]:
    resource_type = resource.get("resourceType", "")
    prefix = _RESOURCE_TYPE_MAP.get(resource_type)
    if not prefix:
        return None

    name = _extract_display_name(resource, prefix)
    timestamp_min = _extract_timestamp_minutes(resource)

    return ActivityEvent(
        name=name,
        timestamp_min=timestamp_min,
        raw_event={
            "fhir_resource_type": resource_type,
            "fhir_id": resource.get("id", ""),
            "fhir_status": resource.get("status", ""),
        },
    )


def _extract_display_name(resource: Dict[str, Any], prefix: str) -> str:
    code = resource.get("code", resource.get("medicationCodeableConcept", {}))
    if isinstance(code, dict):
        for coding in code.get("coding", []):
            if isinstance(coding, dict) and coding.get("display"):
                slug = coding["display"].lower().replace(" ", "_").replace("-", "_")[:60]
                return f"{prefix}_{slug}"

    type_list = resource.get("type", [])
    if isinstance(type_list, list) and type_list:
        for type_item in type_list:
            if isinstance(type_item, dict):
                for coding in type_item.get("coding", []):
                    if isinstance(coding, dict) and coding.get("display"):
                        slug = coding["display"].lower().replace(" ", "_")[:60]
                        return f"{prefix}_{slug}"

    return f"{prefix}_{resource.get('id', 'unknown')[:30]}"


def _extract_timestamp_minutes(resource: Dict[str, Any]) -> float:
    for field in [
        "effectiveDateTime",
        "authoredOn",
        "occurrenceDateTime",
        "recordedDate",
        "onsetDateTime",
        "performedDateTime",
        "issued",
        "date",
    ]:
        val = resource.get(field)
        if isinstance(val, str) and val:
            return _datetime_to_minutes(val)

    period = resource.get("period", resource.get("performedPeriod", {}))
    if isinstance(period, dict) and period.get("start"):
        return _datetime_to_minutes(period["start"])

    return 0.0


def _datetime_to_minutes(dt_str: str) -> float:
    try:
        normalized = dt_str.replace("Z", "+00:00")
        if "T" in normalized:
            dt = datetime.fromisoformat(normalized.split("+")[0])
            return dt.hour * 60 + dt.minute + dt.second / 60.0
        return 0.0
    except (ValueError, AttributeError):
        return 0.0
