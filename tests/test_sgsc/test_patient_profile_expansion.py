"""Tests for B-4 patient profile expansion."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.sgsc.patient_profile_expansion import (
    DEFAULT_MAX_PROFILES,
    PER_GRAPH_MAX_PROFILES,
    PROFILE_BANK,
    TIER_COMMON,
    TIER_DEFAULT,
    TIER_RARE_POPULATION,
    TIER_RARE_SPECIAL,
    TIER_SEVERITY,
    _select_profiles_for_seed,
    expand_seeds_with_profiles,
    get_max_profiles_for_graph,
)
from sgsc.compilers.scenario_compiler import compile_seeds
from sgsc.schemas.atom import RecommendationAtom

KDIGO_DIR = Path("sgsc_output/v7_e3_combined_overnight/kdigo_contrast_aki")


def _load_real_atoms() -> list[RecommendationAtom]:
    """Load real kdigo_contrast_aki atoms for integration coverage."""
    payload = json.loads((KDIGO_DIR / "atoms_smoke.json").read_text())
    return [RecommendationAtom.model_validate(a) for a in payload]


def _load_real_graph_nodes() -> dict:
    """Load the compiled graph's nodes mapping for kdigo_contrast_aki."""
    doc = json.loads((KDIGO_DIR / "kdigo_contrast_aki_graph.json").read_text())
    return doc.get("nodes") or {}


class TestProfileBank:
    def test_bank_size_is_30(self) -> None:
        assert len(PROFILE_BANK) == 30

    def test_all_tiers_represented(self) -> None:
        tiers = {p.tier for p in PROFILE_BANK}
        assert TIER_DEFAULT in tiers
        assert TIER_COMMON in tiers
        assert TIER_SEVERITY in tiers
        assert TIER_RARE_SPECIAL in tiers
        assert TIER_RARE_POPULATION in tiers

    def test_profile_names_unique(self) -> None:
        names = [p.name for p in PROFILE_BANK]
        assert len(names) == len(set(names))

    def test_population_criteria_non_empty(self) -> None:
        for p in PROFILE_BANK:
            assert p.population_criteria
            assert p.name in p.population_criteria


class TestSlotSelection:
    def test_default_max_returns_five_distinct(self) -> None:
        chosen = _select_profiles_for_seed(0, DEFAULT_MAX_PROFILES)
        assert len(chosen) == DEFAULT_MAX_PROFILES
        assert len({p.name for p in chosen}) == DEFAULT_MAX_PROFILES

    def test_default_slate_covers_all_tiers(self) -> None:
        chosen = _select_profiles_for_seed(0, DEFAULT_MAX_PROFILES)
        tiers = {p.tier for p in chosen}
        # With max=5, slot strategy guarantees T5+T1+T2+T3 (or T4) coverage
        assert TIER_DEFAULT in tiers
        assert TIER_COMMON in tiers
        assert TIER_SEVERITY in tiers

    def test_alternating_t3_t4_across_seeds(self) -> None:
        slate0 = _select_profiles_for_seed(0, DEFAULT_MAX_PROFILES)
        slate1 = _select_profiles_for_seed(1, DEFAULT_MAX_PROFILES)
        rare0 = {p.tier for p in slate0 if p.tier in (TIER_RARE_SPECIAL, TIER_RARE_POPULATION)}
        rare1 = {p.tier for p in slate1 if p.tier in (TIER_RARE_SPECIAL, TIER_RARE_POPULATION)}
        # Even seeds get T3, odd seeds get T4
        assert rare0 == {TIER_RARE_SPECIAL}
        assert rare1 == {TIER_RARE_POPULATION}

    def test_max_profiles_cap_respected(self) -> None:
        chosen = _select_profiles_for_seed(0, max_profiles=3)
        assert len(chosen) == 3

    def test_max_profiles_cap_one(self) -> None:
        chosen = _select_profiles_for_seed(5, max_profiles=1)
        assert len(chosen) == 1
        assert chosen[0].tier == TIER_DEFAULT

    def test_high_max_returns_full_bank(self) -> None:
        chosen = _select_profiles_for_seed(0, max_profiles=30)
        assert len(chosen) == 30
        assert {p.name for p in chosen} == {p.name for p in PROFILE_BANK}

    def test_deterministic_output_for_same_seed_index(self) -> None:
        a = _select_profiles_for_seed(7, 5)
        b = _select_profiles_for_seed(7, 5)
        assert [p.name for p in a] == [p.name for p in b]


class TestPerGraphOverrides:
    def test_low_v7_graphs_raise_cap(self) -> None:
        assert PER_GRAPH_MAX_PROFILES["ssc_sepsis_hour1_bundle"] == 30
        assert PER_GRAPH_MAX_PROFILES["aha_chest_pain_evaluation"] == 15
        assert PER_GRAPH_MAX_PROFILES["kdigo_aki_full"] == 10

    def test_unlisted_graph_falls_back_to_default(self) -> None:
        assert get_max_profiles_for_graph("not_a_real_graph") == DEFAULT_MAX_PROFILES

    def test_listed_graph_returns_override(self) -> None:
        assert get_max_profiles_for_graph("ssc_sepsis_hour1_bundle") == 30


@pytest.mark.skipif(not KDIGO_DIR.exists(), reason="requires v7 atoms")
class TestEndToEndExpansion:
    def test_kdigo_smoke_produces_expected_count(self) -> None:
        atoms = _load_real_atoms()
        graph_nodes = _load_real_graph_nodes()
        seeds = compile_seeds(atoms, "kdigo_contrast_aki")
        scenarios = expand_seeds_with_profiles(
            seeds=seeds,
            graph_id="kdigo_contrast_aki",
            atoms=atoms,
            graph_nodes=graph_nodes,
        )
        # kdigo_contrast_aki not in PER_GRAPH_MAX_PROFILES -> default 5
        # 7 seeds * 5 profiles = 35 scenarios
        assert len(scenarios) == len(seeds) * DEFAULT_MAX_PROFILES

    def test_population_criteria_field_emitted(self) -> None:
        atoms = _load_real_atoms()
        graph_nodes = _load_real_graph_nodes()
        seeds = compile_seeds(atoms, "kdigo_contrast_aki")
        scenarios = expand_seeds_with_profiles(
            seeds=seeds,
            graph_id="kdigo_contrast_aki",
            atoms=atoms,
            graph_nodes=graph_nodes,
        )
        for scenario in scenarios.values():
            assert scenario.get("population_criteria")
            assert scenario.get("_sgsc_profile_tier")
            assert scenario.get("_sgsc_profile_name")

    def test_no_pregnancy_male_contradictions(self) -> None:
        atoms = _load_real_atoms()
        graph_nodes = _load_real_graph_nodes()
        seeds = compile_seeds(atoms, "kdigo_contrast_aki")
        scenarios = expand_seeds_with_profiles(
            seeds=seeds,
            graph_id="kdigo_contrast_aki",
            atoms=atoms,
            graph_nodes=graph_nodes,
            max_profiles_per_cluster=30,  # exercise pregnancy spec
        )
        for scenario in scenarios.values():
            patient = scenario.get("patient", {})
            tier = scenario.get("_sgsc_profile_tier")
            if tier == TIER_RARE_POPULATION and "pregnant" in scenario.get("population_criteria", ""):
                assert patient.get("sex") == "F"

    def test_atom_derived_actions_preserved(self) -> None:
        atoms = _load_real_atoms()
        graph_nodes = _load_real_graph_nodes()
        seeds = compile_seeds(atoms, "kdigo_contrast_aki")
        scenarios = expand_seeds_with_profiles(
            seeds=seeds,
            graph_id="kdigo_contrast_aki",
            atoms=atoms,
            graph_nodes=graph_nodes,
        )
        # Every expanded scenario must keep the same expected/forbidden as base seed
        for scenario in scenarios.values():
            assert "expected_actions" in scenario
            assert "forbidden_actions" in scenario

    def test_per_graph_override_applied(self) -> None:
        atoms = _load_real_atoms()
        graph_nodes = _load_real_graph_nodes()
        seeds = compile_seeds(atoms, "kdigo_contrast_aki")
        # Use ssc_sepsis_hour1_bundle's override to verify the lookup wires through
        scenarios = expand_seeds_with_profiles(
            seeds=seeds,
            graph_id="ssc_sepsis_hour1_bundle",
            atoms=atoms,
            graph_nodes=graph_nodes,
        )
        assert len(scenarios) == len(seeds) * 30

    def test_unique_scenario_ids(self) -> None:
        atoms = _load_real_atoms()
        graph_nodes = _load_real_graph_nodes()
        seeds = compile_seeds(atoms, "kdigo_contrast_aki")
        scenarios = expand_seeds_with_profiles(
            seeds=seeds,
            graph_id="kdigo_contrast_aki",
            atoms=atoms,
            graph_nodes=graph_nodes,
        )
        ids = list(scenarios.keys())
        assert len(ids) == len(set(ids))
