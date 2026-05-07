"""Core data models for Clinical Ontology concepts.

Implements SNOMED-CT-style concept representation with IS-A hierarchy,
multi-level abstraction, and subsumption semantics.

References:
- SNOMED CT Expression Constraint Language (ECL)
- UMLS Metathesaurus concept structure (CUI-based)
- Leonardi et al. (2018): Semantic labels for multi-level abstraction
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import FrozenSet, List, Optional, Set


class AbstractionLevel(IntEnum):
    """Hierarchical abstraction levels for clinical actions.

    Higher levels represent broader clinical categories.
    Conformance checking can operate at any level.
    """
    RAW = 0          # Raw event string (agent output)
    NORMALIZED = 1   # CPG-standard action ID
    CATEGORY = 2     # Semantic category (drug class, test type)
    GOAL = 3         # Clinical goal (hemodynamic support, infection control)
    PHASE = 4        # Care pathway phase (hour-1 bundle, initial assessment)


class ConceptRelation(Enum):
    """Semantic relationships between concepts.

    IS_A: Subsumption (norepinephrine IS_A vasopressor)
    PART_OF: Compositional (blood_culture PART_OF sepsis_workup)
    PRECEDES: Temporal ordering (culture PRECEDES antibiotics)
    CONTRAINDICATES: Safety constraint (RV_infarct CONTRAINDICATES nitrates)
    EQUIVALENT: Synonym (levophed EQUIVALENT norepinephrine)

    Rail 1 Extensions (NeurIPS D&B Defense):
    PREREQUISITE: Required prior action (labs PREREQUISITE antibiotics)
    CONDITIONAL: Threshold-gated action (MAP<65 → vasopressor)
    INTERACTION: Drug-drug interaction (NSAID INTERACTION ACE_inhibitor)
    """
    IS_A = "is_a"
    PART_OF = "part_of"
    PRECEDES = "precedes"
    CONTRAINDICATES = "contraindicates"
    EQUIVALENT = "equivalent"
    # Rail 1: NeurIPS D&B Defense - 4 core relation types
    PREREQUISITE = "prerequisite"      # Required prior action with enforcement
    CONDITIONAL = "conditional"        # Threshold-gated (includes condition spec)
    INTERACTION = "interaction"        # Drug-drug or action-action interaction


@dataclass(frozen=True)
class StandardAnchors:
    """External terminology anchors for interoperability.

    Rail 1 (NeurIPS D&B Defense): MVP Interoperability via standard anchors.
    Enables external KB linkage without full standard system inclusion.

    References:
    - UMLS CUI: Unified Medical Language System Concept Unique Identifier
    - RxCUI: RxNorm Concept Unique Identifier (drugs)
    - LOINC: Logical Observation Identifiers Names and Codes (labs)
    - SNOMED_CT: SNOMED Clinical Terms (procedures, findings)
    - ICD10: International Classification of Diseases 10th (diagnoses)

    All fields optional - "attach what you have" philosophy.
    """
    umls_cui: Optional[str] = None       # e.g., "C0027051" (Norepinephrine)
    rxcui: Optional[str] = None          # e.g., "7512" (Norepinephrine)
    loinc: Optional[str] = None          # e.g., "2524-7" (Lactate)
    snomed_ct: Optional[str] = None      # e.g., "386341005" (Blood culture)
    icd10: Optional[str] = None          # e.g., "I21.4" (NSTEMI)

    def has_any_anchor(self) -> bool:
        """Check if at least one anchor is present."""
        return any([self.umls_cui, self.rxcui, self.loinc, self.snomed_ct, self.icd10])

    def to_dict(self) -> dict:
        """Export non-None anchors as dict."""
        return {k: v for k, v in {
            "UMLS_CUI": self.umls_cui,
            "RxCUI": self.rxcui,
            "LOINC": self.loinc,
            "SNOMED_CT": self.snomed_ct,
            "ICD10": self.icd10,
        }.items() if v is not None}


@dataclass(frozen=True)
class ConditionalSpec:
    """Specification for CONDITIONAL relation thresholds.

    Rail 1: Enables threshold-gated action recommendations.
    Example: "Start vasopressor if MAP < 65 despite fluids"

    Attributes:
        variable: Clinical variable to check (e.g., "map_mmhg", "lactate")
        operator: Comparison operator (lt, le, gt, ge, eq, ne, in_range)
        threshold: Numeric threshold or tuple for in_range
        unit: Unit of measurement (e.g., "mmHg", "mmol/L")
        context: Additional context requirement (e.g., "after_fluid_bolus")
    """
    variable: str
    operator: str  # "lt", "le", "gt", "ge", "eq", "ne", "in_range"
    threshold: float | tuple  # Single value or (min, max) for in_range
    unit: Optional[str] = None
    context: Optional[str] = None

    def evaluate(self, value: float) -> bool:
        """Evaluate condition against a value."""
        if self.operator == "lt":
            return value < self.threshold
        elif self.operator == "le":
            return value <= self.threshold
        elif self.operator == "gt":
            return value > self.threshold
        elif self.operator == "ge":
            return value >= self.threshold
        elif self.operator == "eq":
            return value == self.threshold
        elif self.operator == "ne":
            return value != self.threshold
        elif self.operator == "in_range":
            low, high = self.threshold
            return low <= value <= high
        return False


class InteractionSeverity(Enum):
    """Severity levels for drug-drug interactions.

    Based on FDA drug interaction classification.
    """
    CONTRAINDICATED = "contraindicated"  # Never combine (e.g., MAOIs + SSRIs)
    MAJOR = "major"                      # Risk usually outweighs benefit
    MODERATE = "moderate"                # Caution, monitor closely
    MINOR = "minor"                      # Minimal clinical significance


@dataclass(frozen=True)
class InteractionSpec:
    """Specification for INTERACTION relation details.

    Rail 1: Drug-drug and action-action interaction modeling.
    Example: "NSAIDs + ACE inhibitors → hyperkalemia risk"

    Attributes:
        severity: Interaction severity level
        mechanism: Pharmacological mechanism (e.g., "CYP3A4 inhibition")
        effect: Clinical effect (e.g., "increased bleeding risk")
        management: Recommended management action
        evidence_level: Evidence quality (e.g., "established", "theoretical")
    """
    severity: InteractionSeverity
    mechanism: Optional[str] = None
    effect: Optional[str] = None
    management: Optional[str] = None
    evidence_level: str = "established"  # "established", "probable", "theoretical"


@dataclass(frozen=True)
class ClinicalConcept:
    """A node in the clinical ontology graph.

    Represents a clinical action/event at a specific abstraction level.
    Frozen for hashability (usable in sets/dict keys).

    Attributes:
        concept_id: Unique identifier (e.g., "VASOPRESSOR_NOREPINEPHRINE")
        display: Human-readable label
        level: Abstraction level in hierarchy
        system: Terminology system (SNOMED, RxNorm, CGA-Bench, etc.)
        code: Optional external code (SNOMED CT ID, RxNorm CUI) [DEPRECATED: use anchors]
        synonyms: Alternative names that map to this concept
        domain: Clinical domain (sepsis, chest_pain, aki, etc.)
        anchors: External terminology anchors (Rail 1: NeurIPS D&B Defense)
    """
    concept_id: str
    display: str
    level: AbstractionLevel
    system: str = "CGA-Bench"
    code: Optional[str] = None  # DEPRECATED: use anchors.rxcui instead
    synonyms: FrozenSet[str] = field(default_factory=frozenset)
    domain: Optional[str] = None
    anchors: Optional[StandardAnchors] = None  # Rail 1: External KB linkage

    def __hash__(self):
        return hash(self.concept_id)

    def __eq__(self, other):
        if isinstance(other, ClinicalConcept):
            return self.concept_id == other.concept_id
        return NotImplemented


@dataclass
class MatchResult:
    """Result of ontology-based concept matching.

    Attributes:
        source: Original query string
        matched_concept: Best matching concept (or None)
        confidence: Match confidence [0.0, 1.0]
        match_level: Abstraction level at which match was found
        distance: Number of IS-A hops from exact match (0 = exact)
        strategy: Which matching strategy succeeded
        alternatives: Other candidate matches with scores
    """
    source: str
    matched_concept: Optional[ClinicalConcept]
    confidence: float
    match_level: AbstractionLevel
    distance: int = 0
    strategy: str = "exact"
    alternatives: List[tuple] = field(default_factory=list)  # (concept, score)

    @property
    def matched(self) -> bool:
        """Whether a match was found."""
        return self.matched_concept is not None

    @property
    def concept_id(self) -> Optional[str]:
        """Shortcut to matched concept ID."""
        return self.matched_concept.concept_id if self.matched_concept else None
