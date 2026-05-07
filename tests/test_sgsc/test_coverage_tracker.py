"""Tests for sgsc.optimizer.coverage_tracker."""

from __future__ import annotations

from sgsc.optimizer.coverage_tracker import (
    build_family_coverage_vector,
    build_seed_coverage_vector,
    extract_all_items,
    extract_alternative_items,
    extract_boundary_items,
    extract_constraint_items,
    extract_guard_items,
    extract_guard_pair_items,
    extract_mutation_items,
    extract_order_pair_items,
    extract_recommendation_items,
    extract_source_items,
    extract_timing_pair_items,
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
from sgsc.schemas.coverage import CoverageType
from sgsc.schemas.family import CounterfactualFamily, FamilyMember, TraceStep
from sgsc.schemas.seed import BoundarySpec, MutationTemplate, PrivateFields, ScenarioSeed

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_atom(
    atom_id: str = "atom_1",
    action_id: str = "give_abx",
    constraint_type: str = "REQUIRED",
    deadline: int | None = None,
    exclusion: list[str] | None = None,
    boundary_vars: list[str] | None = None,
) -> RecommendationAtom:
    return RecommendationAtom(
        atom_id=atom_id,
        source=SourceReference(
            guideline_id="ssc_2021",
            section="Treatment",
            quote="Guideline text.",
        ),
        population=PopulationCriteria(
            inclusion=["sepsis"],
            exclusion=exclusion or [],
        ),
        action=AtomAction(canonical_id=action_id, action_type="medication"),
        constraint=AtomConstraint(type=constraint_type, deadline_minutes=deadline),
        sequence=AtomSequence(),
        evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="A"),
        scenario_hooks=ScenarioHooks(boundary_variables=boundary_vars or []),
    )


# ------------------------------------------------------------------
# Item extraction per type
# ------------------------------------------------------------------


class TestExtractRecommendationItems:
    def test_one_per_atom(self) -> None:
        atoms = [_make_atom("a1"), _make_atom("a2", action_id="order_lab")]
        items = extract_recommendation_items(atoms)
        assert len(items) == 2
        assert all(i.coverage_type == CoverageType.RECOMMENDATION for i in items)

    def test_item_id_format(self) -> None:
        items = extract_recommendation_items([_make_atom("a1")])
        assert items[0].item_id == "rec:a1"


class TestExtractConstraintItems:
    def test_basic_constraint(self) -> None:
        atoms = [_make_atom(constraint_type="REQUIRED")]
        items = extract_constraint_items(atoms)
        assert len(items) == 1
        assert "REQUIRED" in items[0].item_id

    def test_within_generates_two(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=60)]
        items = extract_constraint_items(atoms)
        assert len(items) == 2
        ids = {i.item_id for i in items}
        assert any("WITHIN" in i and "60" in i for i in ids)


class TestExtractGuardItems:
    def test_one_per_exclusion(self) -> None:
        atoms = [_make_atom(exclusion=["renal_failure", "allergy"])]
        items = extract_guard_items(atoms)
        assert len(items) == 2
        assert all(i.coverage_type == CoverageType.GUARD for i in items)

    def test_no_exclusion(self) -> None:
        atoms = [_make_atom(exclusion=[])]
        items = extract_guard_items(atoms)
        assert len(items) == 0


class TestExtractBoundaryItems:
    def test_one_per_boundary_var(self) -> None:
        atoms = [_make_atom(boundary_vars=["lactate", "creatinine"])]
        items = extract_boundary_items(atoms)
        assert len(items) == 2

    def test_no_boundary_vars(self) -> None:
        items = extract_boundary_items([_make_atom()])
        assert len(items) == 0


class TestExtractSourceItems:
    def test_one_per_atom(self) -> None:
        atoms = [_make_atom("a1"), _make_atom("a2", action_id="x")]
        items = extract_source_items(atoms)
        assert len(items) == 2
        assert items[0].item_id == "src:a1"


class TestExtractMutationItems:
    def test_one_per_mutation(self) -> None:
        seeds = [
            ScenarioSeed(
                seed_id="s1",
                source_atoms=["a1"],
                coverage_targets={},
                mutation_templates=[
                    MutationTemplate(
                        mutation_id="omit_abx",
                        mutation_type="omit",
                        target_action="give_abx",
                        description="Omit abx",
                    ),
                ],
                private_fields=PrivateFields(),
            ),
        ]
        items = extract_mutation_items(seeds)
        assert len(items) == 1
        assert "mut:" in items[0].item_id


# ------------------------------------------------------------------
# extract_all_items
# ------------------------------------------------------------------


class TestExtractAllItems:
    def test_all_types_present(self) -> None:
        atoms = [
            _make_atom(
                constraint_type="WITHIN",
                deadline=60,
                exclusion=["renal"],
                boundary_vars=["lactate"],
            ),
        ]
        seeds = [
            ScenarioSeed(
                seed_id="s1",
                source_atoms=["atom_1"],
                coverage_targets={},
                mutation_templates=[
                    MutationTemplate(
                        mutation_id="m1",
                        mutation_type="omit",
                        target_action="give_abx",
                        description="test",
                    ),
                ],
                private_fields=PrivateFields(),
            ),
        ]
        items = extract_all_items(atoms, seeds)
        types = {i.coverage_type for i in items}
        assert CoverageType.RECOMMENDATION in types
        assert CoverageType.CONSTRAINT in types
        assert CoverageType.GUARD in types
        assert CoverageType.BOUNDARY in types
        assert CoverageType.SOURCE in types
        assert CoverageType.MUTATION in types


# ------------------------------------------------------------------
# Coverage vectors
# ------------------------------------------------------------------


class TestBuildSeedCoverageVector:
    def test_covers_recommendation_and_constraint(self) -> None:
        atoms = [_make_atom("a1")]
        seed = ScenarioSeed(
            seed_id="s1",
            source_atoms=["a1"],
            coverage_targets={},
            private_fields=PrivateFields(),
        )
        vec = build_seed_coverage_vector(seed, atoms)
        assert "rec:a1" in vec.covered_items
        assert any("cst:" in item for item in vec.covered_items)

    def test_covers_source(self) -> None:
        atoms = [_make_atom("a1")]
        seed = ScenarioSeed(
            seed_id="s1",
            source_atoms=["a1"],
            coverage_targets={},
            private_fields=PrivateFields(),
        )
        vec = build_seed_coverage_vector(seed, atoms)
        assert "src:a1" in vec.covered_items

    def test_covers_boundaries(self) -> None:
        atoms = [_make_atom("a1", boundary_vars=["lactate"])]
        seed = ScenarioSeed(
            seed_id="s1",
            source_atoms=["a1"],
            coverage_targets={},
            boundaries=[BoundarySpec(variable="lactate", values=[1.9, 2.0, 2.1])],
            private_fields=PrivateFields(),
        )
        vec = build_seed_coverage_vector(seed, atoms)
        assert "bnd:a1:lactate" in vec.covered_items

    def test_missing_atom_gracefully_handled(self) -> None:
        atoms = [_make_atom("a1")]
        seed = ScenarioSeed(
            seed_id="s1",
            source_atoms=["nonexistent"],
            coverage_targets={},
            private_fields=PrivateFields(),
        )
        vec = build_seed_coverage_vector(seed, atoms)
        assert len(vec.covered_items) == 0


class TestBuildFamilyCoverageVector:
    def test_covers_guard(self) -> None:
        atoms = [_make_atom("a1", exclusion=["renal"])]
        family = CounterfactualFamily(
            family_id="f1",
            source_atoms=["a1"],
            shared_trace_template=[TraceStep(time_minutes=0, action_id="give_abx")],
            members=[
                FamilyMember(
                    scenario_id="f1_ok",
                    patient_state={},
                    expected_verdict="conformant",
                ),
                FamilyMember(
                    scenario_id="f1_bad",
                    patient_state={},
                    expected_verdict="commission_violation",
                ),
            ],
            pivot_variable="renal",
        )
        vec = build_family_coverage_vector(family, atoms)
        assert "guard:a1:renal" in vec.covered_items
        assert "rec:a1" in vec.covered_items


# ------------------------------------------------------------------
# MC/DC coverage — Phase D
# ------------------------------------------------------------------


class TestMCDCCoverage:
    def test_guard_pair_items_extracted(self, sample_atoms: list[RecommendationAtom]) -> None:
        """Atoms with exclusions generate GUARD_TRUE + GUARD_FALSE pairs."""
        import copy

        atoms_with_excl = [a for a in sample_atoms if a.population.exclusion]
        if not atoms_with_excl:
            a = copy.deepcopy(sample_atoms[0])
            a = a.model_copy(
                update={"population": PopulationCriteria(inclusion=["all"], exclusion=["renal_impairment"])}
            )
            atoms_with_excl = [a]
        items = extract_guard_pair_items(atoms_with_excl)
        types = {i.coverage_type for i in items}
        assert CoverageType.GUARD_TRUE in types
        assert CoverageType.GUARD_FALSE in types

    def test_timing_pair_items_extracted(self, sample_atoms: list[RecommendationAtom]) -> None:
        """WITHIN atoms generate TIMING_COMPLIANT + TIMING_VIOLATED pairs."""
        items = extract_timing_pair_items(sample_atoms)
        within_atoms = [a for a in sample_atoms if a.constraint.type == "WITHIN"]
        if within_atoms:
            assert len(items) == len(within_atoms) * 2
            types = {i.coverage_type for i in items}
            assert CoverageType.TIMING_COMPLIANT in types
            assert CoverageType.TIMING_VIOLATED in types

    def test_order_pair_items_extracted(self, sample_atoms: list[RecommendationAtom]) -> None:
        """Atoms with sequence constraints generate ORDER_COMPLIANT + ORDER_VIOLATED pairs."""
        items = extract_order_pair_items(sample_atoms)
        seq_atoms = [
            a
            for a in sample_atoms
            if a.sequence.required_prior or (a.constraint.type == "BEFORE" and a.sequence.before)
        ]
        if seq_atoms:
            assert len(items) == len(seq_atoms) * 2

    def test_alternative_items_extracted(self, sample_atoms: list[RecommendationAtom]) -> None:
        """Atoms with counterfactual_pairs generate ALTERNATIVE items."""
        items = extract_alternative_items(sample_atoms)
        cf_atoms = [a for a in sample_atoms if a.scenario_hooks.counterfactual_pairs]
        expected = sum(len(a.scenario_hooks.counterfactual_pairs) for a in cf_atoms)
        assert len(items) == expected

    def test_extract_all_includes_new_types(self, sample_atoms: list[RecommendationAtom]) -> None:
        """extract_all_items includes MC/DC pair types."""
        items = extract_all_items(sample_atoms)
        types = {i.coverage_type for i in items}
        assert CoverageType.RECOMMENDATION in types
        assert CoverageType.CONSTRAINT in types
        assert CoverageType.SOURCE in types
