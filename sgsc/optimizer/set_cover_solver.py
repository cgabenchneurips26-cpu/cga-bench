"""Greedy and ILP set-cover solvers for coverage optimization.

Selects a minimal subset of scenario seeds (and families) such that
all coverage items are satisfied. Two solvers are provided:

- ``solve_set_cover``: greedy weighted approximation (fast, O(n·m))
- ``solve_set_cover_ilp``: optimal ILP via PuLP CBC (exact minimum)
"""

from __future__ import annotations

from dataclasses import dataclass

from sgsc.schemas.coverage import CoverageVector

# ------------------------------------------------------------------
# Solver configuration
# ------------------------------------------------------------------


@dataclass(frozen=True)
class SetCoverConfig:
    """Configuration for the set-cover solver."""

    max_scenarios: int = 500
    """Hard cap on selected scenarios."""

    weight_uncovered: float = 1.0
    """Weight multiplier for newly-covered items (higher = prefer broad coverage)."""

    weight_mutation: float = 1.2
    """Bonus weight for mutation coverage items."""

    weight_guard: float = 1.3
    """Bonus weight for guard (conditional) coverage items."""


# ------------------------------------------------------------------
# Solver result
# ------------------------------------------------------------------


@dataclass
class SetCoverResult:
    """Result of the greedy set-cover solver."""

    selected_ids: list[str]
    """Ordered list of scenario IDs selected."""

    covered_items: frozenset[str]
    """All items covered by selected set."""

    uncovered_items: frozenset[str]
    """Items that remain uncovered."""

    total_universe: int
    """Total number of items in the universe."""

    iterations: int
    """Number of greedy iterations performed."""

    @property
    def coverage_ratio(self) -> float:
        """Fraction of universe covered."""
        if self.total_universe == 0:
            return 1.0
        return len(self.covered_items) / self.total_universe


# ------------------------------------------------------------------
# Greedy solver
# ------------------------------------------------------------------


def _item_weight(item_id: str, config: SetCoverConfig) -> float:
    """Compute weight for a single coverage item."""
    if item_id.startswith("mut:"):
        return config.weight_uncovered * config.weight_mutation
    if item_id.startswith("guard:"):
        return config.weight_uncovered * config.weight_guard
    return config.weight_uncovered


def solve_set_cover(
    vectors: list[CoverageVector],
    universe: frozenset[str],
    config: SetCoverConfig | None = None,
) -> SetCoverResult:
    """Greedy weighted set-cover: select minimal scenarios covering universe.

    Algorithm:
    1. While uncovered items remain and budget allows:
       a. For each candidate, compute weighted gain = sum of weights
          of newly-covered items.
       b. Select candidate with maximum weighted gain.
       c. Add to selected set, remove covered items from uncovered.
    2. Return selected set and coverage stats.

    Args:
        vectors: Coverage vectors for candidate scenarios.
        universe: Complete set of coverage items to cover.
        config: Solver configuration.

    Returns:
        SetCoverResult with selected scenarios and stats.
    """
    cfg = config or SetCoverConfig()
    uncovered = set(universe)
    selected: list[str] = []
    selected_set: set[str] = set()
    covered_so_far: set[str] = set()
    iterations = 0

    # Index vectors by ID for fast lookup
    vec_map = {v.scenario_id: v for v in vectors}
    remaining_ids = set(vec_map.keys())

    while uncovered and len(selected) < cfg.max_scenarios and remaining_ids:
        iterations += 1
        best_id: str | None = None
        best_gain = 0.0
        best_newly_covered: frozenset[str] = frozenset()

        for vid in remaining_ids:
            vec = vec_map[vid]
            newly = vec.covered_items & uncovered
            if not newly:
                continue
            gain = sum(_item_weight(item, cfg) for item in newly)
            if gain > best_gain:
                best_gain = gain
                best_id = vid
                best_newly_covered = frozenset(newly)

        if best_id is None:
            break

        selected.append(best_id)
        selected_set.add(best_id)
        remaining_ids.discard(best_id)
        covered_so_far.update(best_newly_covered)
        uncovered -= best_newly_covered

    return SetCoverResult(
        selected_ids=selected,
        covered_items=frozenset(covered_so_far),
        uncovered_items=frozenset(uncovered),
        total_universe=len(universe),
        iterations=iterations,
    )


# ------------------------------------------------------------------
# ILP (optimal) solver
# ------------------------------------------------------------------


def solve_set_cover_ilp(
    vectors: list[CoverageVector],
    universe: frozenset[str],
    config: SetCoverConfig | None = None,
) -> SetCoverResult:
    """Optimal ILP set-cover: find true minimum scenarios covering universe.

    Formulation:
        min  Σ x_i
        s.t. Σ(x_i : j ∈ cover(i)) >= 1   ∀ j ∈ universe
             x_i ∈ {0, 1}

    Uses PuLP with the bundled CBC solver.  Falls back to greedy if PuLP
    is unavailable or the solver fails.

    Args:
        vectors: Coverage vectors for candidate scenarios.
        universe: Complete set of coverage items to cover.
        config: Solver configuration (``max_scenarios`` is respected).

    Returns:
        SetCoverResult with optimal (or near-optimal) selection.
    """
    cfg = config or SetCoverConfig()

    if not vectors or not universe:
        return SetCoverResult(
            selected_ids=[],
            covered_items=frozenset(),
            uncovered_items=frozenset(universe),
            total_universe=len(universe),
            iterations=0,
        )

    try:
        import pulp
    except ImportError:
        # Graceful fallback
        return solve_set_cover(vectors, universe, config)

    # Build index: item_id -> list of vector indices that cover it
    vec_list = list(vectors)
    item_to_vecs: dict[str, list[int]] = {item: [] for item in universe}
    for idx, vec in enumerate(vec_list):
        for item in vec.covered_items & universe:
            item_to_vecs[item].append(idx)

    # ILP model
    prob = pulp.LpProblem("set_cover", pulp.LpMinimize)
    x = [pulp.LpVariable(f"x_{i}", cat=pulp.LpBinary) for i in range(len(vec_list))]

    # Objective: minimise total selected
    prob += pulp.lpSum(x)

    # Coverage constraints: each item must be covered by at least one
    for item, vec_indices in item_to_vecs.items():
        if vec_indices:
            prob += pulp.lpSum(x[i] for i in vec_indices) >= 1

    # Budget constraint
    prob += pulp.lpSum(x) <= cfg.max_scenarios

    # Solve (suppress output)
    prob.solve(pulp.PULP_CBC_CMD(msg=0))

    if prob.status != pulp.constants.LpStatusOptimal:
        # Fallback to greedy on solver failure
        return solve_set_cover(vectors, universe, config)

    # Extract selected
    selected_ids: list[str] = []
    covered: set[str] = set()
    for idx, var in enumerate(x):
        if var.varValue is not None and var.varValue > 0.5:
            selected_ids.append(vec_list[idx].scenario_id)
            covered.update(vec_list[idx].covered_items & universe)

    return SetCoverResult(
        selected_ids=selected_ids,
        covered_items=frozenset(covered),
        uncovered_items=frozenset(universe - covered),
        total_universe=len(universe),
        iterations=1,  # ILP solves in one pass
    )
