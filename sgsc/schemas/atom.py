"""RecommendationAtom — core intermediate representation.

Each ``RecommendationAtom`` represents an **atomic action-constraint pair**,
NOT a guideline recommendation.  One source recommendation may decompose
into multiple atoms.

Example decomposition::

    Source: "Obtain blood cultures before antibiotics within 1 hour"
    →  Atom 1: (blood_culture,  REQUIRED)
    →  Atom 2: (antibiotics,    WITHIN 60)
    →  Atom 3: (blood_culture,  BEFORE antibiotics)

Invariant: ``atom_id`` should follow ``{guideline}_{action}_{constraint}``
naming so that each atom is uniquely identifiable.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

VALID_ACTION_TYPES: frozenset[str] = frozenset({
    "medication",
    "lab",
    "imaging",
    "procedure",
    "consult",
    "reassess",
    "disposition",
    "medication_hold",
    "medication_avoid",
    "monitoring",
    "dose_adjustment",
    "followup",
    "prevention",
    "discharge",
})

# ------------------------------------------------------------------
# Sub-models
# ------------------------------------------------------------------


class SourceReference(BaseModel):
    """Provenance link to original guideline text."""

    model_config = ConfigDict(frozen=True)

    guideline_id: str = Field(..., description="CPG graph identifier, e.g. 'ssc_sepsis_hour1'")
    section: str = Field(..., description="Guideline section heading")
    page: str | None = Field(None, description="Page number or range")
    quote: str = Field(..., min_length=1, description="Verbatim substring from corpus")
    quote_hash: str = Field("", description="SHA-256 hex digest of quote")

    @model_validator(mode="after")
    def _fill_quote_hash(self) -> SourceReference:
        if not self.quote_hash:
            computed = hashlib.sha256(self.quote.encode()).hexdigest()
            object.__setattr__(self, "quote_hash", computed)
        return self


class PopulationCriteria(BaseModel):
    """Who this recommendation applies to."""

    model_config = ConfigDict(frozen=True)

    inclusion: list[str] = Field(default_factory=list, description="Inclusion criteria")
    exclusion: list[str] = Field(default_factory=list, description="Exclusion / contraindication criteria")


class AtomAction(BaseModel):
    """The clinical action this atom recommends."""

    model_config = ConfigDict(frozen=True)

    canonical_id: str = Field(..., description="Snake-case action identifier")
    action_type: str = Field(
        ...,
        description=(
            "medication | lab | imaging | procedure | consult | reassess | disposition"
            " | medication_hold | medication_avoid | monitoring | dose_adjustment"
            " | followup | prevention | discharge"
        ),
    )
    terminology: dict[str, str] = Field(
        default_factory=dict,
        description="Optional coding references, e.g. {'rxnorm': '...', 'snomed': '...'}",
    )

    @model_validator(mode="after")
    def _validate_action_type(self) -> AtomAction:
        if self.action_type not in VALID_ACTION_TYPES:
            msg = (
                f"action_type must be one of {sorted(VALID_ACTION_TYPES)}, "
                f"got '{self.action_type}'"
            )
            raise ValueError(msg)
        return self


VALID_CONSTRAINT_TYPES = frozenset({"FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN", "EXPECTED"})


class AtomConstraint(BaseModel):
    """Temporal / ordering constraint derived from this recommendation."""

    model_config = ConfigDict(frozen=True)

    type: str = Field(..., description="FORBIDDEN | REQUIRED | BEFORE | WITHIN | EXPECTED")
    activation_event: str | None = Field(None, description="Event that activates the constraint")
    deadline_minutes: int | None = Field(None, ge=0, description="Deadline in minutes (for WITHIN)")

    @model_validator(mode="after")
    def _validate_type(self) -> AtomConstraint:
        if self.type not in VALID_CONSTRAINT_TYPES:
            msg = f"constraint type must be one of {sorted(VALID_CONSTRAINT_TYPES)}, got '{self.type}'"
            raise ValueError(msg)
        return self


class AtomSequence(BaseModel):
    """Ordering requirements relative to other actions."""

    model_config = ConfigDict(frozen=True)

    before: list[str] = Field(default_factory=list, description="Actions that must follow this one")
    required_prior: list[str] = Field(default_factory=list, description="Actions that must precede this one")


class AtomEvidence(BaseModel):
    """Evidence grading from the source guideline."""

    model_config = ConfigDict(frozen=True)

    system: str = Field(..., description="Grading system, e.g. 'AHA', 'GRADE'")
    recommendation_class: str = Field(..., description="Recommendation class, e.g. 'I', 'IIa'")
    level: str = Field(..., description="Evidence level, e.g. 'A', 'B-NR'")


class ScenarioHooks(BaseModel):
    """Hints for scenario generation from this atom."""

    model_config = ConfigDict(frozen=True)

    boundary_variables: list[str] = Field(
        default_factory=list,
        description="Variables whose boundary values should be tested",
    )
    counterfactual_pairs: list[str] = Field(
        default_factory=list,
        description="Named counterfactual pair labels, e.g. 'eligible_vs_contraindicated'",
    )
    auto_transitions: list[str] = Field(
        default_factory=list,
        description="Auto-transition labels, e.g. 'lactate_normalization'. "
        "Hints the scenario compiler to test state-driven node progression.",
    )


# ------------------------------------------------------------------
# Main model
# ------------------------------------------------------------------


class RecommendationAtom(BaseModel):
    """One atom = one actionable guideline recommendation with full provenance.

    The LLM *proposes* atoms; deterministic compilers consume them to
    produce graphs, scenarios, and counterfactual families.
    """

    model_config = ConfigDict(frozen=False)

    atom_id: str = Field(..., description="Unique atom identifier")
    source: SourceReference
    population: PopulationCriteria
    action: AtomAction
    constraint: AtomConstraint
    sequence: AtomSequence = Field(default_factory=AtomSequence)
    evidence: AtomEvidence
    scenario_hooks: ScenarioHooks = Field(default_factory=ScenarioHooks)

    # Provenance metadata (mutable — filled post-extraction)
    proposed_by: str = Field("", description="Model that proposed this atom")
    agreement_score: float = Field(0.0, ge=0.0, le=1.0, description="Multi-model agreement ratio")
    entailment_status: str = Field(
        "pending",
        description="'entailed' | 'contradicted' | 'neutral' | 'pending'",
    )
    verified_at: str | None = Field(None, description="ISO-8601 timestamp of last verification")

    def to_flat_dict(self) -> dict[str, Any]:
        """Flatten for tabular export."""
        d = self.model_dump()
        d["source_guideline_id"] = self.source.guideline_id
        d["source_quote_hash"] = self.source.quote_hash
        d["action_canonical_id"] = self.action.canonical_id
        d["constraint_type"] = self.constraint.type
        return d
