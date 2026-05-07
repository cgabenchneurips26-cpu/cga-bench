"""Tests for sgsc.optimizer.set_cover_solver."""

from __future__ import annotations

from sgsc.optimizer.set_cover_solver import SetCoverConfig, SetCoverResult, solve_set_cover
from sgsc.schemas.coverage import CoverageVector

# ------------------------------------------------------------------
# Basic solver behavior
# ------------------------------------------------------------------


class TestSetCoverSolver:
    def test_single_vector_covers_all(self) -> None:
        vectors = [
            CoverageVector(scenario_id="s1", covered_items=frozenset({"a", "b", "c"})),
        ]
        universe = frozenset({"a", "b", "c"})
        result = solve_set_cover(vectors, universe)
        assert result.selected_ids == ["s1"]
        assert result.coverage_ratio == 1.0
        assert len(result.uncovered_items) == 0

    def test_greedy_selects_best_first(self) -> None:
        vectors = [
            CoverageVector(scenario_id="small", covered_items=frozenset({"a"})),
            CoverageVector(scenario_id="big", covered_items=frozenset({"a", "b", "c"})),
        ]
        universe = frozenset({"a", "b", "c"})
        result = solve_set_cover(vectors, universe)
        assert result.selected_ids[0] == "big"
        assert result.coverage_ratio == 1.0

    def test_two_complementary_vectors(self) -> None:
        vectors = [
            CoverageVector(scenario_id="s1", covered_items=frozenset({"a", "b"})),
            CoverageVector(scenario_id="s2", covered_items=frozenset({"c", "d"})),
        ]
        universe = frozenset({"a", "b", "c", "d"})
        result = solve_set_cover(vectors, universe)
        assert set(result.selected_ids) == {"s1", "s2"}
        assert result.coverage_ratio == 1.0

    def test_partial_coverage(self) -> None:
        vectors = [
            CoverageVector(scenario_id="s1", covered_items=frozenset({"a"})),
        ]
        universe = frozenset({"a", "b"})
        result = solve_set_cover(vectors, universe)
        assert result.selected_ids == ["s1"]
        assert result.uncovered_items == frozenset({"b"})
        assert result.coverage_ratio == 0.5

    def test_empty_universe(self) -> None:
        vectors = [
            CoverageVector(scenario_id="s1", covered_items=frozenset({"a"})),
        ]
        result = solve_set_cover(vectors, frozenset())
        assert result.selected_ids == []
        assert result.coverage_ratio == 1.0

    def test_empty_vectors(self) -> None:
        universe = frozenset({"a", "b"})
        result = solve_set_cover([], universe)
        assert result.selected_ids == []
        assert result.uncovered_items == universe

    def test_max_scenarios_respected(self) -> None:
        vectors = [CoverageVector(scenario_id=f"s{i}", covered_items=frozenset({f"item_{i}"})) for i in range(20)]
        universe = frozenset(f"item_{i}" for i in range(20))
        config = SetCoverConfig(max_scenarios=5)
        result = solve_set_cover(vectors, universe, config)
        assert len(result.selected_ids) <= 5

    def test_iterations_tracked(self) -> None:
        vectors = [
            CoverageVector(scenario_id="s1", covered_items=frozenset({"a"})),
            CoverageVector(scenario_id="s2", covered_items=frozenset({"b"})),
        ]
        universe = frozenset({"a", "b"})
        result = solve_set_cover(vectors, universe)
        assert result.iterations == 2


# ------------------------------------------------------------------
# Weighted preferences
# ------------------------------------------------------------------


class TestWeightedPreferences:
    def test_mutation_weight_bonus(self) -> None:
        """Mutation items should be preferred when weights are higher."""
        vectors = [
            CoverageVector(
                scenario_id="with_mut",
                covered_items=frozenset({"mut:s1:omit_abx", "rec:a1"}),
            ),
            CoverageVector(
                scenario_id="no_mut",
                covered_items=frozenset({"rec:a1", "rec:a2"}),
            ),
        ]
        universe = frozenset({"mut:s1:omit_abx", "rec:a1", "rec:a2"})
        config = SetCoverConfig(weight_mutation=2.0)
        result = solve_set_cover(vectors, universe, config)
        # With high mutation weight, "with_mut" should be preferred first
        assert result.selected_ids[0] == "with_mut"

    def test_guard_weight_bonus(self) -> None:
        vectors = [
            CoverageVector(
                scenario_id="with_guard",
                covered_items=frozenset({"guard:a1:renal"}),
            ),
            CoverageVector(
                scenario_id="basic",
                covered_items=frozenset({"rec:a1"}),
            ),
        ]
        universe = frozenset({"guard:a1:renal", "rec:a1"})
        config = SetCoverConfig(weight_guard=3.0)
        result = solve_set_cover(vectors, universe, config)
        assert result.selected_ids[0] == "with_guard"


# ------------------------------------------------------------------
# SetCoverResult properties
# ------------------------------------------------------------------


class TestSetCoverResult:
    def test_coverage_ratio_full(self) -> None:
        result = SetCoverResult(
            selected_ids=["s1"],
            covered_items=frozenset({"a", "b"}),
            uncovered_items=frozenset(),
            total_universe=2,
            iterations=1,
        )
        assert result.coverage_ratio == 1.0

    def test_coverage_ratio_half(self) -> None:
        result = SetCoverResult(
            selected_ids=["s1"],
            covered_items=frozenset({"a"}),
            uncovered_items=frozenset({"b"}),
            total_universe=2,
            iterations=1,
        )
        assert result.coverage_ratio == 0.5

    def test_coverage_ratio_empty_universe(self) -> None:
        result = SetCoverResult(
            selected_ids=[],
            covered_items=frozenset(),
            uncovered_items=frozenset(),
            total_universe=0,
            iterations=0,
        )
        assert result.coverage_ratio == 1.0
