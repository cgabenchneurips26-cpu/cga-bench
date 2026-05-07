"""
Core data models for terminology grounding.

Provides CodedConcept, ConceptPivot, QuantityWithUnit, and MedicationCoding
for standardized medical code representation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConceptPivot:
    """Cross-terminology pivot identifiers for interoperability."""
    umls_cui: Optional[str] = None          # UMLS Concept Unique Identifier
    omop_concept_id: Optional[int] = None   # OMOP CDM concept ID


@dataclass
class CodedConcept:
    """A coded medical concept from a standard terminology system.

    Supports LOINC (observations), SNOMED CT (diagnoses/findings),
    and other FHIR-compatible coding systems.
    """
    system: str         # e.g., "http://loinc.org", "http://snomed.info/sct"
    code: str           # e.g., "2524-7" (Lactate LOINC)
    display: str        # Human-readable name, e.g., "Lactate"
    concept_pivot: Optional[ConceptPivot] = None


@dataclass
class QuantityWithUnit:
    """A numeric value with both raw and UCUM-normalized units.

    UCUM (Unified Code for Units of Measure) provides unambiguous
    unit representation per ISO 11240.
    """
    value: float
    unit_raw: str       # Original unit string as received
    unit_ucum: str      # UCUM-normalized unit (e.g., "mmol/L")


@dataclass
class MedicationCoding:
    """Medication identification with RxNorm coding.

    RxNorm provides normalized medication names and codes
    from the National Library of Medicine.
    """
    name: str                               # Generic medication name
    rxnorm_code: Optional[str] = None       # RxNorm CUI
    rxnorm_display: Optional[str] = None    # RxNorm preferred display name
    concept_pivot: Optional[ConceptPivot] = None


@dataclass
class GroundedLabResult:
    """A lab result with full terminology grounding.

    Combines the original internal code with standard terminology
    mappings for external interoperability.
    """
    internal_code: str                          # CGA-Bench internal code
    concept: Optional[CodedConcept] = None      # LOINC/SNOMED coding
    quantity: Optional[QuantityWithUnit] = None  # Value with UCUM unit
    # Neural match metadata (populated when neural fallback is used)
    neural_match_used: bool = False
    neural_confidence: Optional[float] = None
