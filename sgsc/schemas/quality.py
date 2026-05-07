"""GuidelineQualityCard — AGREE-II and RIGHT reporting quality metadata.

Each CPG source gets a quality card that informs scenario weight,
review priority, and constraint hardness decisions.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AGREEScores(BaseModel):
    """AGREE-II domain scores (1-7 Likert scale)."""

    model_config = ConfigDict(frozen=True)

    scope_purpose: int = Field(..., ge=1, le=7)
    rigor_development: int = Field(..., ge=1, le=7)
    applicability: int = Field(..., ge=1, le=7)


class RIGHTItems(BaseModel):
    """RIGHT reporting checklist items."""

    model_config = ConfigDict(frozen=True)

    recommendation_clarity: bool = Field(False, description="Recommendations are clearly stated")
    evidence_linkage: bool = Field(False, description="Evidence is linked to recommendations")
    funding_disclosure: bool = Field(False, description="Funding sources are disclosed")


class ExtractionRisk(BaseModel):
    """Risk factors for automated extraction quality."""

    model_config = ConfigDict(frozen=True)

    layout_complexity: str = Field("low", description="low | medium | high")
    recommendation_tables_present: bool = False
    algorithm_figures_present: bool = False
    paywall_or_web_summary: bool = False


class ScenarioPolicy(BaseModel):
    """Policy decisions derived from quality card."""

    model_config = ConfigDict(frozen=True)

    allow_hard_constraints: bool = Field(
        True,
        description="Whether constraints from this source can be treated as hard violations",
    )
    require_clinician_review_for_weak_recommendations: bool = Field(
        False,
        description="Weak recommendations need manual review before becoming constraints",
    )


class GuidelineQualityCard(BaseModel):
    """Quality metadata for a CPG source.

    Informs the scenario compiler about extraction reliability and
    constraint hardness decisions.
    """

    model_config = ConfigDict(frozen=False)

    source_id: str = Field(..., description="CPG source identifier matching guideline_id")
    agree_ii: AGREEScores
    right_items: RIGHTItems = Field(default_factory=lambda: RIGHTItems())
    extraction_risk: ExtractionRisk = Field(default_factory=lambda: ExtractionRisk())
    scenario_policy: ScenarioPolicy = Field(default_factory=lambda: ScenarioPolicy())
