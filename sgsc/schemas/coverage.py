"""Coverage tracking models — coverage types for set-cover optimization.

The coverage optimizer selects the minimal scenario set S such that
every coverage item is covered at least k times.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CoverageType(str, Enum):
    """Coverage dimensions tracked by the SGSC optimizer.

    10 actively extracted (expanded from original 6):
    RECOMMENDATION, CONSTRAINT, GUARD_TRUE, GUARD_FALSE, BOUNDARY,
    ALTERNATIVE, MUTATION, SOURCE, TIMING_COMPLIANT, TIMING_VIOLATED.

    ORDER_COMPLIANT and ORDER_VIOLATED are extracted when sequence constraints exist.
    """

    RECOMMENDATION = "recommendation"
    CONSTRAINT = "constraint"
    GUARD = "guard"  # Deprecated — use GUARD_TRUE/GUARD_FALSE
    GUARD_TRUE = "guard_true"
    GUARD_FALSE = "guard_false"
    BOUNDARY = "boundary"
    ALTERNATIVE = "alternative"  # NOW ACTIVE — extracted from counterfactual_pairs
    MUTATION = "mutation"
    SOURCE = "source"
    TIMING_COMPLIANT = "timing_compliant"
    TIMING_VIOLATED = "timing_violated"
    ORDER_COMPLIANT = "order_compliant"
    ORDER_VIOLATED = "order_violated"


class CoverageItem(BaseModel):
    """One atomic element that must be covered by at least ``required_k`` scenarios."""

    model_config = ConfigDict(frozen=True)

    item_id: str = Field(..., description="Unique coverage item identifier")
    coverage_type: CoverageType
    description: str = Field("", description="Human-readable description")
    source_atom_id: str | None = Field(None, description="Originating atom, if any")
    required_k: int = Field(1, ge=1, description="Minimum times this item must be covered")


class CoverageVector(BaseModel):
    """Which coverage items a single scenario covers."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    covered_items: frozenset[str] = Field(
        default_factory=frozenset,
        description="Set of CoverageItem.item_id values covered by this scenario",
    )


class CoverageReport(BaseModel):
    """Aggregate coverage status across all items and scenarios."""

    model_config = ConfigDict(frozen=False)

    total_items: int = Field(0, ge=0)
    covered_count: int = Field(0, ge=0)
    uncovered_item_ids: list[str] = Field(default_factory=list)
    coverage_ratio: float = Field(0.0, ge=0.0, le=1.0)
    by_type: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="Per-type breakdown: {type: {'total': N, 'covered': M}}",
    )
    coverage_items: list[CoverageItem] = Field(
        default_factory=list,
        description="All coverage items in the universe",
    )
    vectors: list[CoverageVector] = Field(
        default_factory=list,
        description="Coverage vectors for selected scenarios",
    )

    @property
    def is_fully_covered(self) -> bool:
        """Return True if every item is covered at least once."""
        return self.covered_count >= self.total_items and self.total_items > 0
