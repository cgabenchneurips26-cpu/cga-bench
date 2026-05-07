"""Scenario selector: orchestrate coverage tracking + set-cover optimization.

End-to-end: atoms -> coverage universe -> seed vectors -> optimized set.
"""

from __future__ import annotations

from dataclasses import dataclass

from sgsc.optimizer.coverage_tracker import (
    build_family_coverage_vector,
    build_seed_coverage_vector,
    extract_all_items,
)
from sgsc.optimizer.set_cover_solver import SetCoverConfig, SetCoverResult, solve_set_cover
from sgsc.schemas.atom import RecommendationAtom
from sgsc.schemas.coverage import CoverageReport, CoverageVector
from sgsc.schemas.family import CounterfactualFamily
from sgsc.schemas.seed import ScenarioSeed

# ------------------------------------------------------------------
# Selection result
# ------------------------------------------------------------------


@dataclass
class SelectionResult:
    """Result of scenario selection with coverage report."""

    selected_seed_ids: list[str]
    """IDs of selected seeds."""

    selected_family_ids: list[str]
    """IDs of selected families."""

    coverage_report: CoverageReport
    """Full coverage report after selection."""

    solver_result: SetCoverResult
    """Raw set-cover solver result."""

    @property
    def total_selected(self) -> int:
        """Total number of selected scenarios (seeds + families)."""
        return len(self.selected_seed_ids) + len(self.selected_family_ids)


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def select_scenarios(
    atoms: list[RecommendationAtom],
    seeds: list[ScenarioSeed],
    families: list[CounterfactualFamily] | None = None,
    config: SetCoverConfig | None = None,
) -> SelectionResult:
    """Select minimal scenario set covering all coverage items.

    Steps:
    1. Extract coverage universe from atoms + seeds.
    2. Build coverage vectors for each seed and family.
    3. Run greedy set-cover solver.
    4. Partition selected IDs into seeds vs families.
    5. Build coverage report.

    Args:
        atoms: All recommendation atoms.
        seeds: All scenario seeds.
        families: Optional counterfactual families.
        config: Set-cover solver configuration.

    Returns:
        SelectionResult with selected IDs and coverage report.
    """
    families = families or []

    # Step 1: Extract universe
    all_items = extract_all_items(atoms, seeds)
    universe = frozenset(item.item_id for item in all_items)

    # Step 2: Build vectors
    vectors: list[CoverageVector] = []
    for seed in seeds:
        vectors.append(build_seed_coverage_vector(seed, atoms))
    for family in families:
        vectors.append(build_family_coverage_vector(family, atoms))

    # Step 3: Solve
    result = solve_set_cover(vectors, universe, config)

    # Step 4: Partition
    seed_id_set = {s.seed_id for s in seeds}
    family_id_set = {f.family_id for f in families}

    selected_seeds = [sid for sid in result.selected_ids if sid in seed_id_set]
    selected_families = [sid for sid in result.selected_ids if sid in family_id_set]

    # Step 5: Coverage report
    report = CoverageReport(
        total_items=len(all_items),
        covered_count=len(result.covered_items),
        coverage_items=all_items,
        vectors=[v for v in vectors if v.scenario_id in set(result.selected_ids)],
    )

    return SelectionResult(
        selected_seed_ids=selected_seeds,
        selected_family_ids=selected_families,
        coverage_report=report,
        solver_result=result,
    )
