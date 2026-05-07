"""CounterfactualFamily — matched-pair scenario families.

A family shares the same action trace template but varies patient context
so that the expected clinical verdict differs across members.  This directly
tests context-conditioned evaluator sensitivity (e.g., ``pi_nctx`` blind spots).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TraceStep(BaseModel):
    """One step in a shared action trace template."""

    model_config = ConfigDict(frozen=True)

    time_minutes: float = Field(..., ge=0.0, description="Time offset from scenario start")
    action_id: str = Field(..., description="Canonical action identifier")


class FamilyMember(BaseModel):
    """One scenario within a counterfactual family."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(..., description="Unique scenario identifier")
    patient_state: dict[str, float | int | str | bool] = Field(
        ...,
        description="Patient state overrides for this member",
    )
    expected_verdict: str = Field(
        ...,
        description="Expected verdict: 'conformant', 'omission_violation', 'commission_violation', "
        "'timing_violation', 'sequence_violation', 'deviation_violation'",
    )


class CounterfactualFamily(BaseModel):
    """A family of scenarios sharing the same trace but different contexts.

    The ``pivot_variable`` identifies which single patient-state variable
    is flipped between members, producing different expected verdicts.
    """

    model_config = ConfigDict(frozen=False)

    family_id: str = Field(..., description="Unique family identifier")
    source_atoms: list[str] = Field(
        ...,
        min_length=1,
        description="RecommendationAtom.atom_id references defining the decision boundary",
    )
    shared_trace_template: list[TraceStep] = Field(
        ...,
        min_length=1,
        description="Action trace shared by all family members",
    )
    members: list[FamilyMember] = Field(
        ...,
        min_length=2,
        description="At least 2 members with different expected verdicts",
    )
    pivot_variable: str = Field(
        ...,
        description="Patient-state variable that flips the verdict",
    )
    pivot_threshold: float | str | None = Field(
        None,
        description="Threshold value at the decision boundary",
    )
