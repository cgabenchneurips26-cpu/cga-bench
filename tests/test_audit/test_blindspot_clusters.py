"""Tests for C3: blindspot cluster grid (domain x constraint_type).

Validates:
1. Domain extraction from scenario_id
2. Primary constraint type priority selection
3. Marginal consistency: grid BSR == scalar BSR (all 6 core shims)
4. V4Hard grid: uniformly green (0% BSR, self-reference)
5. Episode coverage: all 14,826 episodes assigned to exactly one cell
6. Red cell exemplars exist in the verdict_matrix corpus
"""

from __future__ import annotations

from typing import Any

from audit.metrics.blindspot import (
    BSR_RED_THRESHOLD,
    compute_blindspot_grid,
    count_red_cells,
    extract_domain,
    grid_marginal_bsr,
    primary_constraint_type,
    render_grid_markdown,
)
from audit.shims import SHIM_REGISTRY
from audit.shims._verdict_cache import load_w8_episodes
import pytest


class TestDomainExtraction:
    """Test domain extraction from scenario_id."""

    @pytest.mark.parametrize(
        "scenario_id,expected",
        [
            ("septic_shock_basic_001", "sepsis"),
            ("sepsis_hour1_002", "sepsis"),
            ("stemi_inferior_rv_trap_001", "chest_pain"),
            ("nstemi_troponin_002", "chest_pain"),
            ("stroke_tpa_eligible_001", "stroke"),
            ("aki_contrast_002", "aki"),
            ("dka_management_001", "dka"),
            ("copd_exacerbation_001", "copd"),
            ("anaphylaxis_severe_001", "anaphylaxis"),
            ("pe_submassive_001", "pulmonary_embolism"),
            ("cap_severe_icu_001", "pneumonia"),
            ("acls_vfib_001", "acls"),
            ("unknown_scenario_999", "other"),
        ],
    )
    def test_domain_extraction(self, scenario_id: str, expected: str) -> None:
        assert extract_domain(scenario_id) == expected


class TestPrimaryConstraintType:
    """Test primary constraint type selection by severity."""

    def test_forbidden_highest_priority(self) -> None:
        assert primary_constraint_type(["WITHIN", "FORBIDDEN"]) == "FORBIDDEN"

    def test_within_over_before(self) -> None:
        assert primary_constraint_type(["BEFORE", "WITHIN"]) == "WITHIN"

    def test_none_for_empty(self) -> None:
        assert primary_constraint_type(None) == "NONE"
        assert primary_constraint_type([]) == "NONE"
        assert primary_constraint_type("") == "NONE"

    def test_string_input(self) -> None:
        assert primary_constraint_type("FORBIDDEN, WITHIN") == "FORBIDDEN"

    def test_single_type(self) -> None:
        assert primary_constraint_type(["BEFORE"]) == "BEFORE"

    def test_all_three(self) -> None:
        assert primary_constraint_type(["BEFORE", "WITHIN", "FORBIDDEN"]) == "FORBIDDEN"


class TestBlindspotGrid:
    """Test grid computation and structural properties."""

    @pytest.fixture(scope="class")
    def episodes(self) -> dict[str, dict[str, Any]]:
        return load_w8_episodes()

    def test_episode_coverage(self, episodes: dict) -> None:
        """All 14,826 episodes must be assigned to exactly one cell."""
        shim = SHIM_REGISTRY["dxem"]()
        grid = compute_blindspot_grid(shim, episodes)
        total = sum(cell["n_episodes"] for domain_cells in grid.values() for cell in domain_cells.values())
        assert total == 14826, f"Grid covers {total} episodes, expected 14,826"

    def test_marginal_consistency_dxem(self, episodes: dict) -> None:
        """Grid marginal BSR must match scalar BSR for DxEM."""
        shim = SHIM_REGISTRY["dxem"]()
        grid = compute_blindspot_grid(shim, episodes)
        grid_bsr = grid_marginal_bsr(grid)

        # Compute scalar BSR directly
        n_disagree = 0
        for ep_id, ep_data in episodes.items():
            eval_v = shim.verdict({"episode_id": ep_id})
            ref_v = bool(ep_data.get("v4_hard", False))
            if eval_v != ref_v:
                n_disagree += 1
        scalar_bsr = n_disagree / len(episodes)

        assert abs(grid_bsr - scalar_bsr) < 1e-4, (
            f"Marginal mismatch: grid_bsr={grid_bsr:.6f}, scalar_bsr={scalar_bsr:.6f}"
        )

    @pytest.mark.parametrize(
        "shim_name",
        ["dxem", "ac_proxy", "mab_proxy", "c2_shim", "acov_shim", "v4_hard"],
    )
    def test_marginal_consistency_all_shims(self, shim_name: str, episodes: dict) -> None:
        """Grid marginal BSR matches scalar BSR for all 6 core shims."""
        shim = SHIM_REGISTRY[shim_name]()
        grid = compute_blindspot_grid(shim, episodes)
        grid_bsr = grid_marginal_bsr(grid)

        n_disagree = 0
        for ep_id, ep_data in episodes.items():
            eval_v = shim.verdict({"episode_id": ep_id})
            ref_v = bool(ep_data.get("v4_hard", False))
            if eval_v != ref_v:
                n_disagree += 1
        scalar_bsr = n_disagree / len(episodes)

        assert abs(grid_bsr - scalar_bsr) < 1e-4, f"{shim_name}: grid_bsr={grid_bsr:.6f} != scalar_bsr={scalar_bsr:.6f}"

    def test_v4_hard_all_green(self, episodes: dict) -> None:
        """V4Hard grid: 0% BSR everywhere (self-reference)."""
        shim = SHIM_REGISTRY["v4_hard"]()
        grid = compute_blindspot_grid(shim, episodes)
        for domain, domain_cells in grid.items():
            for ctype, cell in domain_cells.items():
                assert cell["bsr"] == 0.0, f"V4Hard non-zero BSR at ({domain}, {ctype}): {cell['bsr']}"

    def test_red_cell_exemplars_exist(self, episodes: dict) -> None:
        """Every red cell (>20% BSR) with false accepts has a valid exemplar."""
        shim = SHIM_REGISTRY["dxem"]()
        grid = compute_blindspot_grid(shim, episodes)
        for domain, domain_cells in grid.items():
            for ctype, cell in domain_cells.items():
                if cell["bsr"] > BSR_RED_THRESHOLD and cell["n_false_accept"] > 0:
                    exemplar = cell["exemplar_episode_id"]
                    assert exemplar in episodes, f"Red cell ({domain}, {ctype}) exemplar {exemplar!r} not in corpus"

    def test_always_true_has_red_cells(self, episodes: dict) -> None:
        """AlwaysTrue negative control should produce red cells."""
        from audit.wrappers.metric_evaluators import AlwaysTrueEvaluator

        shim = AlwaysTrueEvaluator()
        grid = compute_blindspot_grid(shim, episodes)
        n_red = count_red_cells(grid)
        assert n_red > 0, "AlwaysTrue should have red cells"

    def test_cell_counts_non_negative(self, episodes: dict) -> None:
        """All cell counts must be non-negative."""
        shim = SHIM_REGISTRY["dxem"]()
        grid = compute_blindspot_grid(shim, episodes)
        for domain_cells in grid.values():
            for cell in domain_cells.values():
                assert cell["n_episodes"] >= 0
                assert cell["n_disagree"] >= 0
                assert cell["n_false_accept"] >= 0
                assert cell["n_false_reject"] >= 0
                assert cell["n_false_accept"] + cell["n_false_reject"] == cell["n_disagree"]


class TestGridRendering:
    """Test markdown rendering of the grid."""

    def test_render_produces_table(self) -> None:
        shim = SHIM_REGISTRY["dxem"]()
        grid = compute_blindspot_grid(shim)
        md = render_grid_markdown(grid)
        assert "|" in md
        assert "Domain" in md
        assert len(md.splitlines()) > 3

    def test_render_has_color_tags(self) -> None:
        shim = SHIM_REGISTRY["dxem"]()
        grid = compute_blindspot_grid(shim)
        md = render_grid_markdown(grid)
        # At least some cells should be tagged
        has_tag = "[G]" in md or "[Y]" in md or "[R]" in md
        assert has_tag, "No color tags in rendered grid"

    def test_render_all_domains_present(self) -> None:
        shim = SHIM_REGISTRY["dxem"]()
        grid = compute_blindspot_grid(shim)
        md = render_grid_markdown(grid)
        for domain in grid:
            assert domain in md, f"Domain {domain!r} missing from rendered grid"
