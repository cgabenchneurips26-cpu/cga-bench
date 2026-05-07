"""
Enhanced OCEL object typing with FHIR resource mapping, CodeFamily subtypes, and type hierarchy.

Provides multi-layer resolution strategy:
1. FHIR resource type from raw event data
2. CodeFamily-based specific subtypes (cbc_test, cardiac_markers, etc.)
3. Fallback to original string-based inference

All features are opt-in via ObjectTypeConfig.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from ..conformance.activity import (
    ActivityEvent,
    parse_fhir_call,
    _normalize_resource_type,
)


@dataclass
class ObjectTypeConfig:
    """Configuration for enhanced OCEL object typing.

    Attributes:
        enable_fhir_typing: Use FHIR resource types for object classification
        enable_code_subtypes: Use CodeVocabulary for specific test subtypes
        enable_type_hierarchy: Include type hierarchy in output
        custom_type_mappings: User-defined activity name -> object type overrides
    """
    enable_fhir_typing: bool = True
    enable_code_subtypes: bool = True
    enable_type_hierarchy: bool = True
    custom_type_mappings: Dict[str, str] = field(default_factory=dict)


@dataclass
class ObjectTypeHierarchy:
    """Represents a type with optional parent for hierarchy."""
    type_id: str
    parent_type: Optional[str] = None
    fhir_resource: Optional[str] = None
    clinical_domain: Optional[str] = None


@dataclass
class EnrichedOCELObject:
    """An OCEL object with enriched type information."""
    object_id: str
    object_type: str
    parent_type: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    fhir_resource_type: Optional[str] = None
    clinical_domain: Optional[str] = None
    codes: List[str] = field(default_factory=list)


# FHIR Resource Type -> OCEL Object Type
FHIR_TO_OBJECT_TYPE: Dict[str, str] = {
    "Patient": "patient",
    "ServiceRequest": "lab_order",
    "MedicationRequest": "medication_order",
    "MedicationAdministration": "medication_administration",
    "Observation": "observation",
    "DiagnosticReport": "diagnostic_report",
    "Procedure": "procedure",
    "Condition": "diagnosis",
    "ImagingStudy": "imaging_study",
    "Encounter": "encounter",
    "AllergyIntolerance": "allergy",
    "CarePlan": "care_plan",
    "Device": "device",
    "Immunization": "immunization",
    "DocumentReference": "document",
    "Bundle": "bundle",
}

# CodeFamily.family_id -> specific object subtype
CODE_FAMILY_TO_SUBTYPE: Dict[str, str] = {
    "cbc": "cbc_test",
    "bmp": "bmp_test",
    "cmp": "cmp_test",
    "cardiac": "cardiac_markers",
    "coagulation": "coagulation_test",
    "sepsis": "sepsis_markers",
    "abg": "abg_test",
    "thyroid": "thyroid_test",
    "renal": "renal_test",
    "liver": "liver_test",
    "urinalysis": "urinalysis_test",
    "lipid": "lipid_panel",
    "electrolytes": "electrolyte_panel",
    "imaging": "imaging_test",
    "ecg": "ecg_test",
    "drug_levels": "drug_level_test",
    "inflammatory": "inflammatory_markers",
    "toxicology": "toxicology_screen",
}

# Type hierarchy: child -> parent
TYPE_HIERARCHY: Dict[str, str] = {
    # Lab test subtypes
    "cbc_test": "lab_test",
    "bmp_test": "lab_test",
    "cmp_test": "lab_test",
    "cardiac_markers": "lab_test",
    "coagulation_test": "lab_test",
    "sepsis_markers": "lab_test",
    "abg_test": "lab_test",
    "thyroid_test": "lab_test",
    "renal_test": "lab_test",
    "liver_test": "lab_test",
    "urinalysis_test": "lab_test",
    "lipid_panel": "lab_test",
    "electrolyte_panel": "lab_test",
    "drug_level_test": "lab_test",
    "inflammatory_markers": "lab_test",
    "toxicology_screen": "lab_test",
    # Imaging subtypes
    "ecg_test": "imaging_test",
    "ct_scan": "imaging_test",
    "mri_scan": "imaging_test",
    "xray": "imaging_test",
    "echocardiogram": "imaging_test",
    "ultrasound": "imaging_test",
    "angiography": "imaging_test",
    # Order-level grouping
    "lab_test": "order",
    "imaging_test": "order",
    "lab_order": "order",
    "medication_order": "order",
    "medication_administration": "medication",
    # FHIR-derived types
    "observation": "order",
    "diagnostic_report": "order",
    "diagnosis": "clinical",
    "encounter": "clinical",
    "allergy": "clinical",
    "care_plan": "clinical",
}

# CodeFamily.family_id -> clinical domain
_CODE_FAMILY_DOMAINS: Dict[str, str] = {
    "cbc": "hematology",
    "bmp": "chemistry",
    "cmp": "chemistry",
    "cardiac": "cardiology",
    "coagulation": "hematology",
    "sepsis": "sepsis",
    "abg": "respiratory",
    "thyroid": "endocrine",
    "renal": "nephrology",
    "liver": "gastroenterology",
    "urinalysis": "nephrology",
    "lipid": "cardiology",
    "electrolytes": "chemistry",
    "imaging": "radiology",
    "ecg": "cardiology",
    "drug_levels": "pharmacology",
    "inflammatory": "immunology",
    "toxicology": "emergency",
}


class ObjectTypeResolver:
    """Resolves OCEL object types using FHIR, CodeFamily, and fallback heuristics.

    Multi-layer resolution strategy (priority order):
    1. Custom user mappings (if configured)
    2. FHIR resource type from raw_event
    3. CodeVocabulary matching for specific subtypes
    4. Fallback to string-based inference
    """

    def __init__(self, config: Optional[ObjectTypeConfig] = None):
        self._config = config or ObjectTypeConfig()
        self._vocabulary = None

    def resolve_objects(
        self,
        event: ActivityEvent,
        episode_id: str,
        idx: int,
    ) -> List[Tuple[str, str]]:
        """Resolve object type(s) for an event.

        Returns list of (object_id, object_type) tuples,
        compatible with the original _infer_related_objects interface.

        Args:
            event: ActivityEvent with raw_event data
            episode_id: Episode identifier for object ID generation
            idx: Event index for object ID generation

        Returns:
            List of (object_id, object_type) tuples
        """
        # Layer 0: Custom user mappings
        if self._config.custom_type_mappings:
            custom_type = self._config.custom_type_mappings.get(event.name)
            if custom_type:
                obj_id = f"obj_{episode_id}_{idx:04d}"
                return [(obj_id, custom_type)]

        # Layer 1: FHIR resource type
        fhir_type = None
        codes: List[str] = []
        if self._config.enable_fhir_typing:
            fhir_type, codes = self._extract_fhir_info(event)

        # Layer 2: Code-based subtype
        code_subtype = None
        clinical_domain = None
        if self._config.enable_code_subtypes and codes:
            code_subtype, clinical_domain = self._resolve_code_subtype(codes)

        # Determine final object type
        if code_subtype:
            obj_type = code_subtype
        elif fhir_type:
            obj_type = FHIR_TO_OBJECT_TYPE.get(fhir_type)
            if not obj_type:
                obj_type = self._fallback_type(event)
        else:
            obj_type = self._fallback_type(event)

        if not obj_type:
            return []

        # Generate object ID based on type
        obj_id = self._generate_object_id(obj_type, episode_id, idx)
        return [(obj_id, obj_type)]

    def resolve_enriched(
        self,
        event: ActivityEvent,
        episode_id: str,
        idx: int,
    ) -> List[EnrichedOCELObject]:
        """Resolve enriched objects with full metadata.

        Args:
            event: ActivityEvent
            episode_id: Episode identifier
            idx: Event index

        Returns:
            List of EnrichedOCELObject with type, domain, codes
        """
        fhir_type = None
        codes: List[str] = []
        if self._config.enable_fhir_typing:
            fhir_type, codes = self._extract_fhir_info(event)

        code_subtype = None
        clinical_domain = None
        if self._config.enable_code_subtypes and codes:
            code_subtype, clinical_domain = self._resolve_code_subtype(codes)

        # Custom mapping takes priority
        if self._config.custom_type_mappings:
            custom_type = self._config.custom_type_mappings.get(event.name)
            if custom_type:
                obj_id = f"obj_{episode_id}_{idx:04d}"
                parent = TYPE_HIERARCHY.get(custom_type)
                return [EnrichedOCELObject(
                    object_id=obj_id,
                    object_type=custom_type,
                    parent_type=parent,
                    fhir_resource_type=fhir_type,
                    clinical_domain=clinical_domain,
                    codes=codes,
                )]

        obj_type = code_subtype or (
            FHIR_TO_OBJECT_TYPE.get(fhir_type) if fhir_type else None
        ) or self._fallback_type(event)

        if not obj_type:
            return []

        obj_id = self._generate_object_id(obj_type, episode_id, idx)
        parent = TYPE_HIERARCHY.get(obj_type) if self._config.enable_type_hierarchy else None

        return [EnrichedOCELObject(
            object_id=obj_id,
            object_type=obj_type,
            parent_type=parent,
            fhir_resource_type=fhir_type,
            clinical_domain=clinical_domain,
            codes=codes,
        )]

    def get_type_hierarchy(self, type_id: str) -> List[str]:
        """Return full type hierarchy path from specific to general.

        Args:
            type_id: Starting type

        Returns:
            List like ["cbc_test", "lab_test", "order"]
        """
        path = [type_id]
        current = type_id
        visited: Set[str] = {type_id}
        while current in TYPE_HIERARCHY:
            parent = TYPE_HIERARCHY[current]
            if parent in visited:
                break
            path.append(parent)
            visited.add(parent)
            current = parent
        return path

    def get_all_type_hierarchies(self) -> Dict[str, ObjectTypeHierarchy]:
        """Return all known object types with hierarchy info."""
        types: Dict[str, ObjectTypeHierarchy] = {}

        # FHIR-derived types
        for fhir_resource, obj_type in FHIR_TO_OBJECT_TYPE.items():
            types[obj_type] = ObjectTypeHierarchy(
                type_id=obj_type,
                parent_type=TYPE_HIERARCHY.get(obj_type),
                fhir_resource=fhir_resource,
            )

        # Code family subtypes
        for family_id, subtype in CODE_FAMILY_TO_SUBTYPE.items():
            if subtype not in types:
                types[subtype] = ObjectTypeHierarchy(
                    type_id=subtype,
                    parent_type=TYPE_HIERARCHY.get(subtype),
                    clinical_domain=_CODE_FAMILY_DOMAINS.get(family_id),
                )

        return types

    def _extract_fhir_info(self, event: ActivityEvent) -> Tuple[Optional[str], List[str]]:
        """Extract FHIR resource type and codes from event raw data."""
        raw = event.raw_event or {}
        tool_call = raw.get("tool_call") or {}
        url = tool_call.get("url") or ""
        payload = tool_call.get("payload") or {}

        if not url and not payload:
            return None, []

        resource_type, codes = parse_fhir_call(url, payload)
        return resource_type, codes

    def _resolve_code_subtype(self, codes: List[str]) -> Tuple[Optional[str], Optional[str]]:
        """Resolve specific subtype from codes using CodeVocabulary.

        Returns (subtype, clinical_domain) or (None, None).
        """
        if not codes:
            return None, None

        vocab = self._get_vocabulary()
        if vocab is None:
            return None, None

        code_set = set(codes)
        match = vocab.match(code_set, "GET")  # method doesn't matter for typing
        if match:
            _, _, family_id = match
            subtype = CODE_FAMILY_TO_SUBTYPE.get(family_id)
            domain = _CODE_FAMILY_DOMAINS.get(family_id)
            return subtype, domain

        return None, None

    def _get_vocabulary(self):
        """Lazy-init CodeVocabulary singleton."""
        if self._vocabulary is None:
            try:
                from ..conformance.activity_codes import CodeVocabulary
                self._vocabulary = CodeVocabulary()
            except ImportError:
                return None
        return self._vocabulary

    def _fallback_type(self, event: ActivityEvent) -> Optional[str]:
        """Original string-based type inference (fallback)."""
        name = event.name.upper()

        if "ORDER" in name or "QUERY" in name:
            if "LAB" in name or "TEST" in name or "OBSERVATION" in name:
                return "lab_test"
            elif "IMAGING" in name or "ECG" in name or "XRAY" in name:
                return "imaging_test"
            elif "MEDICATION" in name:
                return "medication_order"
            else:
                return "order"

        elif "PRESCRIBE" in name or "MEDICATION" in name:
            return "medication_order"

        elif "PROCEDURE" in name:
            return "procedure"

        return None

    def _generate_object_id(self, obj_type: str, episode_id: str, idx: int) -> str:
        """Generate object ID based on type category."""
        if "medication" in obj_type:
            prefix = "med"
        elif "procedure" in obj_type:
            prefix = "proc"
        elif obj_type in ("patient", "encounter", "diagnosis"):
            prefix = obj_type[:4]
        else:
            prefix = "order"
        return f"{prefix}_{episode_id}_{idx:04d}"
