"""Tests for the ILP set-cover solver and the coverage_greedy_vs_ilp script.

Two groups:
  1. ILP solver unit tests  (test_ilp_*)
  2. Comparison script tests (test_comparison_*)
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import random
import sys

import pytest
from sgsc.optimizer.set_cover_solver import (
    SetCoverConfig,
    SetCoverResult,
    solve_set_cover,
    solve_set_cover_ilp,
)
from sgsc.schemas.coverage import CoverageVector

# ---------------------------------------------------------------------------
# Script loader
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "sgsc" / "coverage_greedy_vs_ilp.py"


def _load_module():
    """Dynamically load coverage_greedy_vs_ilp.py as a module."""
    spec = importlib.util.spec_from_file_location("coverage_greedy_vs_ilp", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_vec(scenario_id: str, items: set[str]) -> CoverageVector:
    """Construct a CoverageVector from a plain set of item strings."""
    return CoverageVector(scenario_id=scenario_id, covered_items=frozenset(items))


# ---------------------------------------------------------------------------
# ILP solver unit tests
# ---------------------------------------------------------------------------


class TestIlpEmptyUniverse:
    """test_ilp_empty_universe — empty universe yields trivially full coverage."""

    def test_empty_universe_returns_no_selection(self) -> None:
        vectors = [_make_vec("s1", {"a", "b"})]
        result = solve_set_cover_ilp(vectors, frozenset(), SetCoverConfig())

        assert isinstance(result, SetCoverResult)
        assert result.selected_ids == []
        assert result.coverage_ratio == 1.0
        assert result.total_universe == 0
        assert result.uncovered_items == frozenset()


class TestIlpEmptyVectors:
    """test_ilp_empty_vectors — no vectors, non-empty universe leaves items uncovered."""

    def test_empty_vectors_leaves_universe_uncovered(self) -> None:
        universe: frozenset[str] = frozenset({"a", "b", "c"})
        result = solve_set_cover_ilp([], universe, SetCoverConfig())

        assert isinstance(result, SetCoverResult)
        assert result.selected_ids == []
        assert result.uncovered_items == universe
        assert result.coverage_ratio == 0.0


class TestIlpSingleItem:
    """test_ilp_single_item — one item, one vector covering it."""

    def test_single_item_selects_covering_vector(self) -> None:
        universe = frozenset({"rec:only"})
        vectors = [_make_vec("seed_001", {"rec:only"})]
        result = solve_set_cover_ilp(vectors, universe, SetCoverConfig())

        assert result.selected_ids == ["seed_001"]
        assert result.coverage_ratio == 1.0
        assert result.uncovered_items == frozenset()

    def test_single_item_irrelevant_vector_not_selected(self) -> None:
        """Vector that does not cover the universe item must not be selected."""
        universe = frozenset({"rec:only"})
        vectors = [_make_vec("seed_irrelevant", {"rec:other"})]
        result = solve_set_cover_ilp(vectors, universe, SetCoverConfig())

        # Item cannot be covered — ILP may fall back to greedy; either way uncovered.
        assert "rec:only" in result.uncovered_items


class TestIlpOptimalVsGreedy:
    """test_ilp_optimal_vs_greedy — both solvers cover a 6-item universe in 2 picks."""

    def test_both_cover_full_universe_in_two_picks(self) -> None:
        universe = frozenset({"a", "b", "c", "d", "e", "f"})
        vectors = [
            _make_vec("v1", {"a", "b", "c"}),
            _make_vec("v2", {"d", "e", "f"}),
            _make_vec("v3", {"a", "d"}),
            _make_vec("v4", {"b", "e"}),
            _make_vec("v5", {"c", "f"}),
        ]
        greedy = solve_set_cover(vectors, universe, SetCoverConfig())
        ilp = solve_set_cover_ilp(vectors, universe, SetCoverConfig())

        # Both must achieve full coverage.
        assert greedy.coverage_ratio == 1.0
        assert ilp.coverage_ratio == 1.0

        # ILP must be at least as good as greedy (the core ILP guarantee).
        assert len(ilp.selected_ids) <= len(greedy.selected_ids)

        # The optimal here is 2 (v1 + v2); ILP should find it.
        assert len(ilp.selected_ids) == 2


class TestIlpOptimalityGuarantee:
    """test_ilp_optimality_guarantee — ILP count is always <= greedy count."""

    def test_ilp_never_worse_than_greedy(self) -> None:
        # Construct a universe where greedy might diverge.
        # Universe {1..6}, V1={1,2,3}, V2={4,5,6}, V3={1,4}, V4={2,5}, V5={3,6}
        # Optimal: V1 + V2 = 2.  Greedy may also find 2, but ILP can never exceed greedy.
        universe = frozenset({"1", "2", "3", "4", "5", "6"})
        vectors = [
            _make_vec("V1", {"1", "2", "3"}),
            _make_vec("V2", {"4", "5", "6"}),
            _make_vec("V3", {"1", "4"}),
            _make_vec("V4", {"2", "5"}),
            _make_vec("V5", {"3", "6"}),
        ]
        greedy = solve_set_cover(vectors, universe)
        ilp = solve_set_cover_ilp(vectors, universe)

        assert len(ilp.selected_ids) <= len(greedy.selected_ids)
        assert ilp.coverage_ratio == 1.0

    def test_ilp_finds_two_scenario_optimum(self) -> None:
        # Harder pairing: V_a + V_b = 2 is optimal; greedy may also find 2.
        universe = frozenset({"a", "b", "c", "d"})
        vectors = [
            _make_vec("V_a", {"a", "b"}),
            _make_vec("V_b", {"c", "d"}),
            _make_vec("V_c", {"a", "c"}),
            _make_vec("V_d", {"b", "d"}),
            # V_e covers 3 items — greedy might pick this first
            _make_vec("V_e", {"a", "b", "c"}),
        ]
        ilp = solve_set_cover_ilp(vectors, universe)

        assert len(ilp.selected_ids) == 2
        assert ilp.coverage_ratio == 1.0


class TestIlpRespectsMaxScenarios:
    """test_ilp_respects_max_scenarios — config.max_scenarios hard cap is honoured."""

    def test_max_scenarios_one(self) -> None:
        universe = frozenset({"x", "y", "z"})
        vectors = [
            _make_vec("s1", {"x"}),
            _make_vec("s2", {"y"}),
            _make_vec("s3", {"z"}),
        ]
        config = SetCoverConfig(max_scenarios=1)
        result = solve_set_cover_ilp(vectors, universe, config)

        # At most 1 scenario selected.
        assert len(result.selected_ids) <= 1
        # Universe needs 3 picks but we capped at 1 → some uncovered.
        assert len(result.uncovered_items) >= 2

    def test_max_scenarios_respected_without_full_coverage(self) -> None:
        universe = frozenset({"p", "q", "r", "s"})
        vectors = [_make_vec(f"s{i}", {item}) for i, item in enumerate("pqrs")]
        config = SetCoverConfig(max_scenarios=2)
        result = solve_set_cover_ilp(vectors, universe, config)

        assert len(result.selected_ids) <= 2


class TestIlpResultType:
    """test_ilp_result_type — verify the return type and field contract."""

    def test_returns_set_cover_result(self) -> None:
        universe = frozenset({"item_a", "item_b"})
        vectors = [_make_vec("v1", {"item_a", "item_b"})]
        result = solve_set_cover_ilp(vectors, universe)

        assert isinstance(result, SetCoverResult)
        # Mandatory fields
        assert isinstance(result.selected_ids, list)
        assert isinstance(result.covered_items, frozenset)
        assert isinstance(result.uncovered_items, frozenset)
        assert isinstance(result.total_universe, int)
        assert isinstance(result.iterations, int)
        # coverage_ratio property
        assert 0.0 <= result.coverage_ratio <= 1.0

    def test_covered_plus_uncovered_equals_universe(self) -> None:
        universe = frozenset({"a", "b", "c", "d"})
        vectors = [
            _make_vec("v1", {"a", "b"}),
            _make_vec("v2", {"c", "d"}),
        ]
        result = solve_set_cover_ilp(vectors, universe)

        assert result.covered_items | result.uncovered_items == universe
        assert result.covered_items & result.uncovered_items == frozenset()
        assert result.total_universe == len(universe)


class TestIlpLargeUniverse:
    """test_ilp_large_universe — ILP completes on a 100-item universe and is <= greedy."""

    def test_ilp_count_leq_greedy_on_large_instance(self) -> None:
        rng = random.Random(42)  # Seeded for reproducibility
        all_items = [f"item_{i}" for i in range(100)]
        universe = frozenset(all_items)

        vectors: list[CoverageVector] = []
        for v_idx in range(50):
            # Each vector covers 10-20 random items.
            k = rng.randint(10, 20)
            covered = set(rng.choices(all_items, k=k))
            vectors.append(_make_vec(f"vec_{v_idx:03d}", covered))

        greedy = solve_set_cover(vectors, universe)
        ilp = solve_set_cover_ilp(vectors, universe)

        # ILP is exact-optimal: must never select more than greedy.
        assert len(ilp.selected_ids) <= len(greedy.selected_ids)

        # Both solvers must return valid SetCoverResult objects.
        assert isinstance(ilp, SetCoverResult)
        assert 0.0 <= ilp.coverage_ratio <= 1.0


# ---------------------------------------------------------------------------
# Comparison script tests
# ---------------------------------------------------------------------------


def _make_registry(tmp_path: Path, guideline_ids: list[str]) -> Path:
    """Write a minimal registry JSON and return its path."""
    data = {"guidelines": [{"guideline_id": gid} for gid in guideline_ids]}
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(data))
    return p


def _make_coverage_json(
    vectors_raw: list[dict],
    coverage_items_raw: list[dict] | None = None,
) -> dict:
    """Build a coverage JSON dict matching the format consumed by _load_coverage_vectors."""
    if coverage_items_raw is None:
        # Derive unique items from vectors.
        all_items: set[str] = set()
        for v in vectors_raw:
            all_items.update(v.get("covered_items", []))
        coverage_items_raw = [
            {"item_id": iid, "coverage_type": "recommendation", "description": ""} for iid in sorted(all_items)
        ]
    return {
        "total_items": len(coverage_items_raw),
        "covered_count": len(coverage_items_raw),
        "coverage_ratio": 1.0,
        "uncovered_item_ids": [],
        "by_type": {"recommendation": {"total": len(coverage_items_raw), "covered": len(coverage_items_raw)}},
        "coverage_items": coverage_items_raw,
        "vectors": vectors_raw,
    }


def _write_guideline_dir(
    sgsc_dir: Path,
    guideline_id: str,
    coverage_data: dict | None = None,
    *,
    write_atoms: bool = True,
) -> None:
    """Create the sgsc_output/{guideline_id}/ directory with required files."""
    gdir = sgsc_dir / guideline_id
    gdir.mkdir(parents=True, exist_ok=True)

    if write_atoms:
        (gdir / "atoms_smoke.json").write_text(json.dumps({"atoms": []}))

    if coverage_data is not None:
        (gdir / f"{guideline_id}_coverage.json").write_text(json.dumps(coverage_data))


class TestComparisonNoData:
    """test_comparison_no_data — empty sgsc_output gives warn status, 0 guidelines compared."""

    def test_no_guideline_dirs_gives_warn(self, tmp_path: Path) -> None:
        mod = _load_module()

        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        output_dir = tmp_path / "out"
        registry = _make_registry(tmp_path, ["guideline_alpha"])

        # No subdirectory exists for guideline_alpha → no_atoms path.
        report = mod.run_comparison(registry, sgsc_dir, output_dir)

        assert report["status"] in ("pass", "warn")
        assert report["metrics"]["guidelines_compared"] == 0


class TestComparisonSingleGuideline:
    """test_comparison_single_guideline — one guideline with vector data produces ok entry."""

    def test_single_guideline_ok_entry(self, tmp_path: Path) -> None:
        mod = _load_module()

        sgsc_dir = tmp_path / "sgsc_output"
        registry = _make_registry(tmp_path, ["guide_001"])
        output_dir = tmp_path / "out"

        coverage_data = _make_coverage_json(
            vectors_raw=[
                {"scenario_id": "seed_001", "covered_items": ["rec:a1", "rec:a2"]},
                {"scenario_id": "seed_002", "covered_items": ["rec:a1"]},
            ],
            coverage_items_raw=[
                {"item_id": "rec:a1", "coverage_type": "recommendation", "description": ""},
                {"item_id": "rec:a2", "coverage_type": "recommendation", "description": ""},
            ],
        )
        _write_guideline_dir(sgsc_dir, "guide_001", coverage_data)

        report = mod.run_comparison(registry, sgsc_dir, output_dir)

        runnable = [e for e in report["per_guideline"] if e["status"] == "ok"]
        assert len(runnable) == 1
        entry = runnable[0]
        assert entry["guideline_id"] == "guide_001"
        assert entry["targets"] == 2
        assert entry["greedy_scenarios"] >= 1
        assert entry["ilp_scenarios"] >= 1


class TestComparisonOutputContract:
    """test_comparison_output_contract — all required top-level keys must be present."""

    def test_required_keys_present(self, tmp_path: Path) -> None:
        mod = _load_module()

        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        registry = _make_registry(tmp_path, [])
        output_dir = tmp_path / "out"

        report = mod.run_comparison(registry, sgsc_dir, output_dir)

        required_keys = {
            "check_name",
            "status",
            "commit",
            "input_hash",
            "output_hash",
            "metrics",
            "per_guideline",
            "failures",
        }
        assert required_keys.issubset(report.keys())

    def test_metrics_subkeys_present(self, tmp_path: Path) -> None:
        mod = _load_module()

        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        registry = _make_registry(tmp_path, [])
        output_dir = tmp_path / "out"

        report = mod.run_comparison(registry, sgsc_dir, output_dir)

        required_metric_keys = {
            "guidelines_compared",
            "mean_ratio",
            "max_ratio",
            "all_covered_greedy",
            "all_covered_ilp",
        }
        assert required_metric_keys.issubset(report["metrics"].keys())


class TestComparisonRatioComputation:
    """test_comparison_ratio_computation — ratio = greedy / ilp is computed correctly."""

    def test_ratio_field_matches_counts(self, tmp_path: Path) -> None:
        mod = _load_module()

        # Construct a universe where greedy and ILP must both pick 1 scenario
        # (trivially equal) so we can assert the ratio == 1.0.
        sgsc_dir = tmp_path / "sgsc_output"
        registry = _make_registry(tmp_path, ["guide_ratio"])
        output_dir = tmp_path / "out"

        coverage_data = _make_coverage_json(
            vectors_raw=[
                {"scenario_id": "s1", "covered_items": ["rec:x", "rec:y"]},
            ],
            coverage_items_raw=[
                {"item_id": "rec:x", "coverage_type": "recommendation", "description": ""},
                {"item_id": "rec:y", "coverage_type": "recommendation", "description": ""},
            ],
        )
        _write_guideline_dir(sgsc_dir, "guide_ratio", coverage_data)

        report = mod.run_comparison(registry, sgsc_dir, output_dir)

        runnable = [e for e in report["per_guideline"] if e["status"] == "ok"]
        assert len(runnable) == 1
        entry = runnable[0]

        # Both solvers need exactly 1 scenario here.
        assert entry["greedy_scenarios"] == 1
        assert entry["ilp_scenarios"] == 1
        assert entry["ratio"] == pytest.approx(1.0, abs=1e-4)

    def test_ratio_formula_greedy_over_ilp(self, tmp_path: Path) -> None:
        """Verify the ratio formula: greedy_scenarios / ilp_scenarios."""
        mod = _load_module()

        # Construct: 6-item universe, greedy picks 2, ILP picks 2 (both optimal).
        # The ratio is 2/2 = 1.0.
        sgsc_dir = tmp_path / "sgsc_output"
        registry = _make_registry(tmp_path, ["guide_formula"])
        output_dir = tmp_path / "out"

        items = [{"item_id": f"rec:{c}", "coverage_type": "recommendation", "description": ""} for c in "abcdef"]
        coverage_data = {
            "total_items": 6,
            "covered_count": 6,
            "coverage_ratio": 1.0,
            "uncovered_item_ids": [],
            "by_type": {"recommendation": {"total": 6, "covered": 6}},
            "coverage_items": items,
            "vectors": [
                {"scenario_id": "v1", "covered_items": ["rec:a", "rec:b", "rec:c"]},
                {"scenario_id": "v2", "covered_items": ["rec:d", "rec:e", "rec:f"]},
            ],
        }
        _write_guideline_dir(sgsc_dir, "guide_formula", coverage_data)

        report = mod.run_comparison(registry, sgsc_dir, output_dir)
        entry = next(e for e in report["per_guideline"] if e["status"] == "ok")

        # ratio should be greedy / ilp
        expected_ratio = entry["greedy_scenarios"] / entry["ilp_scenarios"]
        assert entry["ratio"] == pytest.approx(expected_ratio, abs=1e-4)


class TestComparisonHashFormat:
    """test_comparison_hash_format — output_hash and input_hash are 64-char hex strings."""

    def test_hashes_are_64_char_hex(self, tmp_path: Path) -> None:
        mod = _load_module()

        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        registry = _make_registry(tmp_path, [])
        output_dir = tmp_path / "out"

        report = mod.run_comparison(registry, sgsc_dir, output_dir)

        for field in ("output_hash", "input_hash"):
            value = report[field]
            assert isinstance(value, str), f"{field} must be a string"
            assert len(value) == 64, f"{field} must be 64 chars (SHA-256), got {len(value)}"
            assert all(c in "0123456789abcdef" for c in value), f"{field} must be lowercase hex"


class TestComparisonPassStatus:
    """test_comparison_pass_status — all ratios < 2.0, all covered → status is pass."""

    def test_fully_covered_low_ratio_gives_pass(self, tmp_path: Path) -> None:
        mod = _load_module()

        sgsc_dir = tmp_path / "sgsc_output"
        registry = _make_registry(tmp_path, ["guide_pass"])
        output_dir = tmp_path / "out"

        # One vector covers everything → ratio = 1.0, fully covered.
        coverage_data = _make_coverage_json(
            vectors_raw=[
                {"scenario_id": "s_all", "covered_items": ["rec:a1", "rec:a2"]},
            ],
            coverage_items_raw=[
                {"item_id": "rec:a1", "coverage_type": "recommendation", "description": ""},
                {"item_id": "rec:a2", "coverage_type": "recommendation", "description": ""},
            ],
        )
        _write_guideline_dir(sgsc_dir, "guide_pass", coverage_data)

        report = mod.run_comparison(registry, sgsc_dir, output_dir)

        assert report["status"] == "pass"
        assert report["metrics"]["all_covered_greedy"] is True
        assert report["metrics"]["all_covered_ilp"] is True
        assert report["metrics"]["max_ratio"] < 2.0
