"""ScenarioSeed — declarative test specification for scenario generation.

A seed declares *what* a scenario should test (coverage targets, boundary
values, mutation templates) before the scenario compiler instantiates the
concrete patient state, action trace, and expected verdicts.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BoundarySpec(BaseModel):
    """Boundary values for a single clinical variable."""

    model_config = ConfigDict(frozen=True)

    variable: str = Field(..., description="Clinical variable name, e.g. 'lactate'")
    values: list[float | int | str] = Field(
        ...,
        min_length=1,
        description="Boundary values to test, e.g. [3.9, 4.0, 4.1]",
    )


VALID_MUTATION_TYPES = frozenset({"omit", "delay", "swap", "sequence_break"})


class MutationTemplate(BaseModel):
    """A perturbation template for generating violation scenarios."""

    model_config = ConfigDict(frozen=True)

    mutation_id: str = Field(..., description="Unique mutation identifier")
    mutation_type: str = Field(..., description="omit | delay | swap | sequence_break")
    target_action: str = Field(..., description="Action to perturb")
    description: str = Field("", description="Human-readable description")
    delay_minutes: int | None = Field(None, ge=0, description="Delay amount for 'delay' type")

    def model_post_init(self, __context: object) -> None:
        if self.mutation_type not in VALID_MUTATION_TYPES:
            msg = f"mutation_type must be one of {sorted(VALID_MUTATION_TYPES)}, got '{self.mutation_type}'"
            raise ValueError(msg)


class PrivateFields(BaseModel):
    """Scoring-only fields invisible to agents.

    These are stripped before writing agent-visible scenario YAML.
    The leakage scanner verifies they never appear in agent-accessible output.
    """

    model_config = ConfigDict(frozen=True)

    activated_constraint_ids: list[str] = Field(default_factory=list)
    expected_trace_family: list[str] = Field(default_factory=list)
    coverage_targets_met: list[str] = Field(default_factory=list)


class ScenarioSeed(BaseModel):
    """Declarative test specification that drives scenario generation.

    The scenario compiler reads seeds and produces concrete scenario YAML
    entries compatible with ``ScenarioLoader.load_all_scenarios()``.
    """

    model_config = ConfigDict(frozen=False)

    seed_id: str = Field(..., description="Unique seed identifier")
    source_atoms: list[str] = Field(
        ...,
        min_length=1,
        description="RecommendationAtom.atom_id references",
    )
    coverage_targets: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Coverage target names grouped by type, e.g. {'constraints': ['MUST(x)'], ...}",
    )
    boundaries: list[BoundarySpec] = Field(default_factory=list)
    patient_state_constraints: dict[str, str | float | bool] = Field(
        default_factory=dict,
        description="Patient state requirements, e.g. {'diagnosis': 'sepsis'}",
    )
    observability: dict[str, str] = Field(
        default_factory=dict,
        description="Hidden-until rules, e.g. {'lactate': 'order_lactate'}",
    )
    mutation_templates: list[MutationTemplate] = Field(default_factory=list)
    private_fields: PrivateFields = Field(default_factory=PrivateFields)
