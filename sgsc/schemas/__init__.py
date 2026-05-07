"""SGSC schema definitions — Pydantic v2 models for the SGSC pipeline."""

from __future__ import annotations

from sgsc.schemas.atom import (
    VALID_ACTION_TYPES,
    AtomAction,
    AtomConstraint,
    AtomEvidence,
    AtomSequence,
    PopulationCriteria,
    RecommendationAtom,
    ScenarioHooks,
    SourceReference,
)
from sgsc.schemas.coverage import (
    CoverageItem,
    CoverageReport,
    CoverageType,
    CoverageVector,
)
from sgsc.schemas.family import (
    CounterfactualFamily,
    FamilyMember,
    TraceStep,
)
from sgsc.schemas.quality import (
    AGREEScores,
    GuidelineQualityCard,
    RIGHTItems,
)
from sgsc.schemas.seed import (
    BoundarySpec,
    MutationTemplate,
    PrivateFields,
    ScenarioSeed,
)

__all__ = [
    "AGREEScores",
    "AtomAction",
    "VALID_ACTION_TYPES",
    "AtomConstraint",
    "AtomEvidence",
    "AtomSequence",
    "BoundarySpec",
    "CounterfactualFamily",
    "CoverageItem",
    "CoverageReport",
    "CoverageType",
    "CoverageVector",
    "FamilyMember",
    "GuidelineQualityCard",
    "MutationTemplate",
    "PopulationCriteria",
    "PrivateFields",
    "RIGHTItems",
    "RecommendationAtom",
    "ScenarioHooks",
    "ScenarioSeed",
    "SourceReference",
    "TraceStep",
]
