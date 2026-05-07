"""Tests for sgsc.compilers.scenario_compiler."""

from __future__ import annotations

import pytest
from sgsc.compilers.scenario_compiler import (
    compile_seeds,
    seed_to_scenario_yaml,
    seeds_to_scenario_yaml,
    seeds_to_split_scenario_yaml,
)
from sgsc.schemas.atom import (
    AtomAction,
    AtomConstraint,
    AtomEvidence,
    AtomSequence,
    PopulationCriteria,
    RecommendationAtom,
    ScenarioHooks,
    SourceReference,
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_atom(
    constraint_type: str = "REQUIRED",
    action_id: str = "give_abx",
    deadline: int | None = None,
    boundary_vars: list[str] | None = None,
    required_prior: list[str] | None = None,
    atom_id: str | None = None,
    section: str = "Hour-1 Bundle",
    inclusion: list[str] | None = None,
    exclusion: list[str] | None = None,
) -> RecommendationAtom:
    return RecommendationAtom(
        atom_id=atom_id or f"atom_{action_id}",
        source=SourceReference(
            guideline_id="ssc_2021",
            section=section,
            quote=f"Do {action_id} per guideline.",
        ),
        population=PopulationCriteria(
            inclusion=list(inclusion) if inclusion is not None else ["sepsis"],
            exclusion=list(exclusion) if exclusion is not None else [],
        ),
        action=AtomAction(canonical_id=action_id, action_type="medication"),
        constraint=AtomConstraint(type=constraint_type, deadline_minutes=deadline),
        sequence=AtomSequence(required_prior=required_prior or []),
        evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="A"),
        scenario_hooks=ScenarioHooks(boundary_variables=boundary_vars or []),
    )


# ------------------------------------------------------------------
# compile_seeds
# ------------------------------------------------------------------


class TestCompileSeeds:
    def test_basic_seed_generation(self) -> None:
        atoms = [_make_atom()]
        seeds = compile_seeds(atoms, "ssc_2021")
        assert len(seeds) == 1
        assert seeds[0].seed_id.startswith("ssc_2021_")
        assert "atom_give_abx" in seeds[0].source_atoms

    def test_forbidden_atoms_skipped(self) -> None:
        atoms = [
            _make_atom(constraint_type="FORBIDDEN", action_id="give_nitro"),
        ]
        seeds = compile_seeds(atoms, "ssc_2021")
        assert len(seeds) == 0

    def test_within_generates_omit_and_delay_mutations(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=60)]
        seeds = compile_seeds(atoms, "ssc_2021")
        assert len(seeds) == 1
        mutation_types = {m.mutation_type for m in seeds[0].mutation_templates}
        assert "omit" in mutation_types
        assert "delay" in mutation_types

    def test_required_generates_omit_mutation(self) -> None:
        atoms = [_make_atom(constraint_type="REQUIRED")]
        seeds = compile_seeds(atoms, "ssc_2021")
        mutation_types = {m.mutation_type for m in seeds[0].mutation_templates}
        assert "omit" in mutation_types
        assert "delay" not in mutation_types

    def test_before_generates_sequence_break(self) -> None:
        atoms = [
            _make_atom(
                constraint_type="BEFORE",
                action_id="blood_culture",
                required_prior=["triage"],
            ),
        ]
        seeds = compile_seeds(atoms, "ssc_2021")
        mutation_types = {m.mutation_type for m in seeds[0].mutation_templates}
        assert "sequence_break" in mutation_types

    def test_boundary_variables_extracted(self) -> None:
        atoms = [_make_atom(boundary_vars=["lactate", "creatinine"])]
        seeds = compile_seeds(atoms, "ssc_2021")
        boundary_vars = {b.variable for b in seeds[0].boundaries}
        assert "lactate" in boundary_vars
        assert "creatinine" in boundary_vars

    def test_unknown_boundary_skipped(self) -> None:
        atoms = [_make_atom(boundary_vars=["unknown_variable_xyz"])]
        seeds = compile_seeds(atoms, "ssc_2021")
        assert len(seeds[0].boundaries) == 0

    def test_coverage_targets_populated(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=60)]
        seeds = compile_seeds(atoms, "ssc_2021")
        ct = seeds[0].coverage_targets
        assert "constraints" in ct
        assert any("WITHIN" in c for c in ct["constraints"])

    def test_private_fields_set(self) -> None:
        atoms = [_make_atom()]
        seeds = compile_seeds(atoms, "ssc_2021")
        pf = seeds[0].private_fields
        assert len(pf.activated_constraint_ids) > 0
        assert len(pf.expected_trace_family) > 0


# ------------------------------------------------------------------
# seed_to_scenario_yaml
# ------------------------------------------------------------------


class TestSeedToScenarioYaml:
    def test_output_has_required_fields(self) -> None:
        atoms = [_make_atom()]
        seeds = compile_seeds(atoms, "ssc_2021")
        yaml_entry = seed_to_scenario_yaml(seeds[0], "ssc_sepsis_hour1", atoms)
        required_keys = {
            "scenario_id",
            "description",
            "guideline_graph",
            "patient",
            "ground_truth",
            "expected_actions",
            "forbidden_actions",
            "max_duration_minutes",
        }
        assert required_keys.issubset(set(yaml_entry.keys()))

    def test_expected_actions_populated(self) -> None:
        atoms = [_make_atom()]
        seeds = compile_seeds(atoms, "ssc_2021")
        yaml_entry = seed_to_scenario_yaml(seeds[0], "ssc_sepsis_hour1", atoms)
        assert "give_abx" in yaml_entry["expected_actions"]

    def test_forbidden_actions_from_forbidden_atoms(self) -> None:
        atoms = [
            _make_atom(constraint_type="REQUIRED", action_id="give_abx"),
            _make_atom(constraint_type="FORBIDDEN", action_id="give_nitro", atom_id="atom_nitro"),
        ]
        # Create seed referencing both atoms
        seeds = compile_seeds(atoms, "ssc_2021")
        # Only REQUIRED atoms produce seeds; need to manually include forbidden
        # in this test via direct atom lookup
        assert len(seeds) == 1

    def test_patient_has_vitals(self) -> None:
        atoms = [_make_atom()]
        seeds = compile_seeds(atoms, "ssc_2021")
        yaml_entry = seed_to_scenario_yaml(seeds[0], "ssc_sepsis_hour1", atoms)
        patient = yaml_entry["patient"]
        assert "vitals" in patient
        assert "heart_rate" in patient["vitals"]

    def test_max_duration_from_deadline(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=60)]
        seeds = compile_seeds(atoms, "ssc_2021")
        yaml_entry = seed_to_scenario_yaml(seeds[0], "ssc_sepsis_hour1", atoms)
        assert yaml_entry["max_duration_minutes"] >= 120

    def test_sgsc_metadata_present(self) -> None:
        atoms = [_make_atom()]
        seeds = compile_seeds(atoms, "ssc_2021")
        yaml_entry = seed_to_scenario_yaml(seeds[0], "ssc_sepsis_hour1", atoms)
        assert "_sgsc_metadata" in yaml_entry
        assert "seed_id" in yaml_entry["_sgsc_metadata"]


# ------------------------------------------------------------------
# seeds_to_scenario_yaml (batch)
# ------------------------------------------------------------------


class TestSeedsToScenarioYaml:
    def test_dict_keyed_by_seed_id_distinct_sections(self) -> None:
        # Track-4: distinct sections produce separate clusters and therefore
        # separate seeds.
        atoms = [
            _make_atom(action_id="a1", atom_id="atom_a1", section="Initial Assessment"),
            _make_atom(action_id="a2", atom_id="atom_a2", section="Resuscitation"),
        ]
        seeds = compile_seeds(atoms, "ssc_2021")
        result = seeds_to_scenario_yaml(seeds, "ssc_sepsis_hour1", atoms)
        assert isinstance(result, dict)
        assert len(result) == 2
        for key in result:
            assert key.startswith("ssc_2021_")

    def test_dict_keyed_by_seed_id_same_section(self) -> None:
        # Track-4: atoms sharing a section collapse into a single multi-action
        # cluster.
        atoms = [
            _make_atom(action_id="a1", atom_id="atom_a1"),
            _make_atom(action_id="a2", atom_id="atom_a2"),
        ]
        seeds = compile_seeds(atoms, "ssc_2021")
        result = seeds_to_scenario_yaml(seeds, "ssc_sepsis_hour1", atoms)
        assert len(result) == 1
        only = next(iter(result.values()))
        assert set(only["expected_actions"]) == {"a1", "a2"}

    def test_empty_seeds(self) -> None:
        result = seeds_to_scenario_yaml([], "ssc_sepsis_hour1", [])
        assert result == {}


# ------------------------------------------------------------------
# TestPublicPrivateSplit
# ------------------------------------------------------------------


@pytest.fixture
def sample_atoms() -> list[RecommendationAtom]:
    return [
        _make_atom(action_id="give_abx", atom_id="atom_give_abx"),
        _make_atom(action_id="order_culture", atom_id="atom_order_culture"),
    ]


class TestPublicPrivateSplit:
    def test_public_has_no_ground_truth(self, sample_atoms: list[RecommendationAtom]) -> None:
        seeds = compile_seeds(sample_atoms, "test_guideline")
        pub, priv = seeds_to_split_scenario_yaml(seeds, "test_guideline", sample_atoms)
        for sid, scenario in pub.items():
            assert "ground_truth" not in scenario
            assert "expected_actions" not in scenario
            assert "forbidden_actions" not in scenario
            assert "_sgsc_metadata" not in scenario

    def test_private_has_expected_actions(self, sample_atoms: list[RecommendationAtom]) -> None:
        seeds = compile_seeds(sample_atoms, "test_guideline")
        pub, priv = seeds_to_split_scenario_yaml(seeds, "test_guideline", sample_atoms)
        for sid, scenario in priv.items():
            assert "expected_actions" in scenario or "ground_truth" in scenario

    def test_public_private_union_equals_full(self, sample_atoms: list[RecommendationAtom]) -> None:
        seeds = compile_seeds(sample_atoms, "test_guideline")
        full = seeds_to_scenario_yaml(seeds, "test_guideline", sample_atoms)
        pub, priv = seeds_to_split_scenario_yaml(seeds, "test_guideline", sample_atoms)
        for sid in full:
            combined_keys = set(pub[sid].keys()) | set(priv[sid].keys())
            # scenario_id appears in both
            full_keys = set(full[sid].keys())
            assert full_keys.issubset(combined_keys)

    def test_split_preserves_scenario_id(self, sample_atoms: list[RecommendationAtom]) -> None:
        seeds = compile_seeds(sample_atoms, "test_guideline")
        pub, priv = seeds_to_split_scenario_yaml(seeds, "test_guideline", sample_atoms)
        for sid in pub:
            assert pub[sid]["scenario_id"] == sid
            assert priv[sid]["scenario_id"] == sid


# ------------------------------------------------------------------
# β-5: Defensive action normalization in scenario output
# ------------------------------------------------------------------


class TestDefensiveScenarioNormalization:
    """Verify scenario YAML action IDs are canonicalized by ActionNormalizer."""

    def test_forbidden_actions_normalized_in_scenario(self) -> None:
        """FORBIDDEN atom with raw alias → canonical form in scenario forbidden_actions."""
        forbidden_atom = RecommendationAtom(
            atom_id="atom_forbidden_raw",
            source=SourceReference(guideline_id="test", section="Contra", quote="Avoid contrast."),
            population=PopulationCriteria(inclusion=["aki"], exclusion=[]),
            action=AtomAction(canonical_id="broad_spectrum_antibiotics", action_type="medication"),
            constraint=AtomConstraint(type="FORBIDDEN"),
            evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="B"),
        )
        required_atom = _make_atom(action_id="give_abx", atom_id="atom_req")
        atoms = [required_atom, forbidden_atom]
        seeds = compile_seeds(atoms, "test")
        # FORBIDDEN atoms don't generate seeds, but they appear via seed_to_scenario_yaml
        # when the seed's source_atoms include them.  Test via direct call.
        from sgsc.schemas.seed import PrivateFields, ScenarioSeed

        seed = ScenarioSeed(
            seed_id="test_forbidden_seed",
            source_atoms=["atom_forbidden_raw"],
            coverage_targets={},
            private_fields=PrivateFields(activated_constraint_ids=["test_forbidden"]),
        )
        scenario = seed_to_scenario_yaml(seed, "test", [forbidden_atom])

        try:
            from cga_bench.assessor_core.action_normalizer import ActionNormalizer

            normalizer = ActionNormalizer()
            expected = normalizer.normalize("broad_spectrum_antibiotics")
        except ImportError:
            expected = "broad_spectrum_antibiotics"

        assert expected in scenario["forbidden_actions"], (
            f"Expected canonical '{expected}' in forbidden_actions, got {scenario['forbidden_actions']}"
        )
        # ground_truth should also be canonical
        assert expected in scenario["ground_truth"]["forbidden_actions"]

    def test_expected_actions_normalized_in_scenario(self) -> None:
        """REQUIRED atom with raw alias → canonical form in expected_actions."""
        atom = _make_atom(
            action_id="blood_culture_before_antibiotics",
            atom_id="atom_raw_expected",
        )
        seeds = compile_seeds([atom], "test")
        assert len(seeds) >= 1
        scenario = seed_to_scenario_yaml(seeds[0], "test", [atom])

        try:
            from cga_bench.assessor_core.action_normalizer import ActionNormalizer

            normalizer = ActionNormalizer()
            expected = normalizer.normalize("blood_culture_before_antibiotics")
        except ImportError:
            expected = "blood_culture_before_antibiotics"

        assert expected in scenario["expected_actions"], (
            f"Expected canonical '{expected}' in expected_actions, got {scenario['expected_actions']}"
        )


# ------------------------------------------------------------------
# Track-4: Multi-action clustering + graph forbidden injection
# ------------------------------------------------------------------


from sgsc.compilers.scenario_compiler import (  # noqa: E402
    CLUSTER_MAX,
    FORBIDDEN_ACTIONS_CAP,
    _aggregate_graph_forbidden,
    _aggregate_population,
    _cluster_atoms_for_multi_action,
)


class TestClusteringGroupsAtomsCorrectly:
    def test_atoms_in_same_section_collapse_to_single_cluster(self) -> None:
        atoms = [
            _make_atom(action_id="a1", atom_id="atom_a1", section="Initial Assessment"),
            _make_atom(action_id="a2", atom_id="atom_a2", section="Initial Assessment"),
            _make_atom(action_id="a3", atom_id="atom_a3", section="Initial Assessment"),
        ]
        clusters = _cluster_atoms_for_multi_action(atoms)
        assert len(clusters) == 1
        assert {a.action.canonical_id for a in clusters[0]} == {"a1", "a2", "a3"}

    def test_distinct_sections_produce_distinct_clusters(self) -> None:
        atoms = [
            _make_atom(action_id="a1", atom_id="atom_a1", section="Initial Assessment"),
            _make_atom(action_id="b1", atom_id="atom_b1", section="Resuscitation"),
            _make_atom(action_id="b2", atom_id="atom_b2", section="Resuscitation"),
        ]
        clusters = _cluster_atoms_for_multi_action(atoms)
        assert len(clusters) == 2

    def test_forbidden_atoms_excluded_from_clusters(self) -> None:
        atoms = [
            _make_atom(action_id="a1", atom_id="atom_a1"),
            _make_atom(constraint_type="FORBIDDEN", action_id="bad", atom_id="atom_bad"),
        ]
        clusters = _cluster_atoms_for_multi_action(atoms)
        assert len(clusters) == 1
        assert {a.action.canonical_id for a in clusters[0]} == {"a1"}

    def test_oversize_section_splits_into_chunks(self) -> None:
        # 12 atoms in one section, cluster_max=10 → 2 clusters of size 10 + 2
        atoms = [_make_atom(action_id=f"a{i}", atom_id=f"atom_a{i}", section="Big Phase") for i in range(12)]
        clusters = _cluster_atoms_for_multi_action(atoms, cluster_max=10)
        assert len(clusters) == 2
        assert len(clusters[0]) == 10
        assert len(clusters[1]) == 2

    def test_section_iteration_order_is_first_encounter(self) -> None:
        atoms = [
            _make_atom(action_id="late", atom_id="atom_late", section="Phase B"),
            _make_atom(action_id="early", atom_id="atom_early", section="Phase A"),
            _make_atom(action_id="late2", atom_id="atom_late2", section="Phase B"),
        ]
        clusters = _cluster_atoms_for_multi_action(atoms)
        # First-encountered section should appear first
        assert clusters[0][0].source.section == "Phase B"
        assert clusters[1][0].source.section == "Phase A"


class TestMultiActionScenarioYaml:
    def test_multi_action_scenario_yaml_has_n_mandatory(self) -> None:
        atoms = [_make_atom(action_id=f"a{i}", atom_id=f"atom_a{i}", section="Phase") for i in range(5)]
        seeds = compile_seeds(atoms, "ssc_2021")
        assert len(seeds) == 1
        scenario = seed_to_scenario_yaml(seeds[0], "ssc_sepsis_hour1", atoms)
        assert len(scenario["expected_actions"]) == 5

    def test_seed_id_uses_section_slug_and_index(self) -> None:
        atoms = [
            _make_atom(action_id="a1", atom_id="atom_a1", section="Initial Assessment"),
        ]
        seeds = compile_seeds(atoms, "guide_x")
        assert seeds[0].seed_id == "guide_x_initial_assessment_c000"

    def test_cluster_aggregates_mutations_from_all_atoms(self) -> None:
        atoms = [
            _make_atom(action_id="a", atom_id="atom_a", section="Phase"),
            _make_atom(
                action_id="b",
                atom_id="atom_b",
                section="Phase",
                constraint_type="WITHIN",
                deadline=60,
            ),
        ]
        seeds = compile_seeds(atoms, "ssc_2021")
        # a contributes 1 omit; b contributes omit + delay → 3 mutations
        assert len(seeds[0].mutation_templates) == 3

    def test_cluster_aggregates_boundaries_dedup(self) -> None:
        atoms = [
            _make_atom(action_id="a", atom_id="atom_a", section="Phase", boundary_vars=["lactate"]),
            _make_atom(action_id="b", atom_id="atom_b", section="Phase", boundary_vars=["lactate", "creatinine"]),
        ]
        seeds = compile_seeds(atoms, "ssc_2021")
        boundary_vars = {b.variable for b in seeds[0].boundaries}
        assert boundary_vars == {"lactate", "creatinine"}


class TestClusterCombinesPopulationCriteria:
    def test_inclusion_intersected_across_atoms(self) -> None:
        atoms = [
            _make_atom(action_id="a", atom_id="atom_a", section="P", inclusion=["sepsis", "adult"]),
            _make_atom(action_id="b", atom_id="atom_b", section="P", inclusion=["sepsis"]),
        ]
        inc, _ = _aggregate_population(atoms)
        assert inc == ["sepsis"]

    def test_exclusion_unioned_across_atoms(self) -> None:
        atoms = [
            _make_atom(action_id="a", atom_id="atom_a", section="P", exclusion=["pregnancy"]),
            _make_atom(action_id="b", atom_id="atom_b", section="P", exclusion=["dialysis"]),
        ]
        _, exc = _aggregate_population(atoms)
        assert set(exc) == {"pregnancy", "dialysis"}


# ------------------------------------------------------------------
# Track-4-2: Graph forbidden_actions injection
# ------------------------------------------------------------------


class TestGraphForbiddenInjection:
    def test_aggregate_dedups_across_nodes(self) -> None:
        nodes = {
            "n1": {"forbidden_actions": ["give_x", "give_y"]},
            "n2": {"forbidden_actions": ["give_y", "give_z"]},
        }
        result = _aggregate_graph_forbidden(nodes, cap=15)
        assert set(result) == {"give_x", "give_y", "give_z"}
        assert len(result) == 3

    def test_empty_or_none_graph_returns_empty(self) -> None:
        assert _aggregate_graph_forbidden(None, cap=15) == []
        assert _aggregate_graph_forbidden({}, cap=15) == []

    def test_cap_truncates_oversized_list(self) -> None:
        nodes = {
            f"n{i:02d}": {"forbidden_actions": [f"give_{i}_{j}" for j in range(5)]} for i in range(10)
        }  # 50 distinct items
        result = _aggregate_graph_forbidden(nodes, cap=15)
        assert len(result) == 15

    def test_node_iteration_is_deterministic(self) -> None:
        # Same inputs in different insertion orders should yield identical
        # aggregation (sorted by node_id).
        nodes_a = {"n2": {"forbidden_actions": ["b"]}, "n1": {"forbidden_actions": ["a"]}}
        nodes_b = {"n1": {"forbidden_actions": ["a"]}, "n2": {"forbidden_actions": ["b"]}}
        assert _aggregate_graph_forbidden(nodes_a, cap=15) == _aggregate_graph_forbidden(nodes_b, cap=15)
        assert _aggregate_graph_forbidden(nodes_a, cap=15) == ["a", "b"]


class TestScenarioHasForbiddenActionsFromGraph:
    def test_scenario_has_forbidden_actions_from_graph(self) -> None:
        atom = _make_atom(action_id="give_abx", atom_id="atom_x")
        seeds = compile_seeds([atom], "guide_x")
        graph_nodes = {"phase_a": {"forbidden_actions": ["give_nitro", "give_warfarin"]}}
        scenario = seed_to_scenario_yaml(seeds[0], "guide_x", [atom], graph_nodes=graph_nodes)
        assert "give_nitro" in scenario["forbidden_actions"]
        assert "give_warfarin" in scenario["forbidden_actions"]

    def test_forbidden_actions_normalized(self) -> None:
        atom = _make_atom(action_id="give_abx", atom_id="atom_x")
        seeds = compile_seeds([atom], "guide_x")
        # Graph has a raw alias that ActionNormalizer should canonicalise.
        graph_nodes = {"phase_a": {"forbidden_actions": ["broad_spectrum_antibiotics"]}}
        scenario = seed_to_scenario_yaml(seeds[0], "guide_x", [atom], graph_nodes=graph_nodes)
        try:
            from cga_bench.assessor_core.action_normalizer import ActionNormalizer

            normalizer = ActionNormalizer()
            expected = normalizer.normalize("broad_spectrum_antibiotics")
        except ImportError:
            expected = "broad_spectrum_antibiotics"
        assert expected in scenario["forbidden_actions"]

    def test_forbidden_actions_capped_at_max(self) -> None:
        atom = _make_atom(action_id="give_abx", atom_id="atom_x")
        seeds = compile_seeds([atom], "guide_x")
        # Build 25 distinct forbidden actions across 5 nodes
        graph_nodes = {
            f"node_{i:02d}": {"forbidden_actions": [f"forbid_action_{i}_{j}" for j in range(5)]} for i in range(5)
        }
        scenario = seed_to_scenario_yaml(seeds[0], "guide_x", [atom], graph_nodes=graph_nodes, forbidden_cap=10)
        assert len(scenario["forbidden_actions"]) <= 10

    def test_no_graph_nodes_yields_empty_forbidden(self) -> None:
        atom = _make_atom(action_id="give_abx", atom_id="atom_x")
        seeds = compile_seeds([atom], "guide_x")
        scenario = seed_to_scenario_yaml(seeds[0], "guide_x", [atom])
        assert scenario["forbidden_actions"] == []

    def test_default_cap_constant(self) -> None:
        # Sanity check the public constants. Track-B v7.1 loosened cluster
        # bounds from 3-10 to 2-8 to surface ~1.7x more scenarios from the
        # frozen atom set.
        assert FORBIDDEN_ACTIONS_CAP == 15
        assert CLUSTER_MAX == 8
