"""Tests for sgsc.compilers.mutation_compiler."""

from __future__ import annotations

import pytest
from sgsc.compilers.mutation_compiler import (
    compile_all_mutations,
    compile_mutation_variant,
    compile_mutations,
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
from sgsc.schemas.seed import MutationTemplate, PrivateFields, ScenarioSeed

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_atom(
    action_id: str = "give_abx",
    required_prior: list[str] | None = None,
) -> RecommendationAtom:
    return RecommendationAtom(
        atom_id=f"atom_{action_id}",
        source=SourceReference(
            guideline_id="ssc_2021",
            section="Treatment",
            quote="Guideline text.",
        ),
        population=PopulationCriteria(inclusion=["sepsis"], exclusion=[]),
        action=AtomAction(canonical_id=action_id, action_type="medication"),
        constraint=AtomConstraint(type="REQUIRED"),
        sequence=AtomSequence(required_prior=required_prior or []),
        evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="A"),
        scenario_hooks=ScenarioHooks(),
    )


def _make_seed(
    seed_id: str = "seed_1",
    mutations: list[MutationTemplate] | None = None,
) -> ScenarioSeed:
    return ScenarioSeed(
        seed_id=seed_id,
        source_atoms=["atom_give_abx"],
        coverage_targets={"constraints": ["REQUIRED(give_abx)"]},
        mutation_templates=mutations or [],
        private_fields=PrivateFields(),
    )


def _make_mutation(
    mutation_type: str = "omit",
    target: str = "give_abx",
    delay: int | None = None,
) -> MutationTemplate:
    return MutationTemplate(
        mutation_id=f"{mutation_type}_{target}",
        mutation_type=mutation_type,
        target_action=target,
        description=f"Test {mutation_type} mutation",
        delay_minutes=delay,
    )


# ------------------------------------------------------------------
# compile_mutation_variant
# ------------------------------------------------------------------


class TestCompileMutationVariant:
    def test_omit_variant(self) -> None:
        seed = _make_seed()
        mut = _make_mutation("omit")
        atoms = [_make_atom()]
        result = compile_mutation_variant(seed, mut, atoms)
        assert result["expected_violation_type"] == "OMISSION"
        assert result["trace_modifications"]["action_removed"] == "give_abx"

    def test_delay_variant(self) -> None:
        seed = _make_seed()
        mut = _make_mutation("delay", delay=95)
        atoms = [_make_atom()]
        result = compile_mutation_variant(seed, mut, atoms)
        assert result["expected_violation_type"] == "TIMING"
        assert result["trace_modifications"]["delayed_to_minutes"] == 95

    def test_swap_variant(self) -> None:
        seed = _make_seed()
        mut = _make_mutation("swap")
        atoms = [_make_atom()]
        result = compile_mutation_variant(seed, mut, atoms)
        assert result["expected_violation_type"] == "COMMISSION"
        assert "original_action" in result["trace_modifications"]
        assert "swapped_with" in result["trace_modifications"]

    def test_sequence_break_variant(self) -> None:
        seed = _make_seed()
        mut = _make_mutation("sequence_break")
        atoms = [_make_atom(required_prior=["triage"])]
        result = compile_mutation_variant(seed, mut, atoms)
        assert result["expected_violation_type"] == "SEQUENCE"

    def test_variant_id_format(self) -> None:
        seed = _make_seed(seed_id="seed_abc")
        mut = _make_mutation(mutation_type="omit")
        result = compile_mutation_variant(seed, mut, [_make_atom()])
        assert result["variant_id"] == "seed_abc__omit_give_abx"

    def test_base_seed_id(self) -> None:
        seed = _make_seed(seed_id="seed_xyz")
        mut = _make_mutation()
        result = compile_mutation_variant(seed, mut, [_make_atom()])
        assert result["base_seed_id"] == "seed_xyz"

    def test_mutation_template_rejects_invalid_type(self) -> None:
        with pytest.raises(Exception):
            MutationTemplate(
                mutation_id="custom_1",
                mutation_type="custom_unknown",
                target_action="give_abx",
                description="Unknown mutation",
            )


# ------------------------------------------------------------------
# compile_mutations (per seed)
# ------------------------------------------------------------------


class TestCompileMutations:
    def test_generates_all_from_seed(self) -> None:
        mutations = [
            _make_mutation("omit"),
            _make_mutation("delay", delay=95),
        ]
        seed = _make_seed(mutations=mutations)
        atoms = [_make_atom()]
        results = compile_mutations(seed, atoms)
        assert len(results) == 2

    def test_empty_mutations(self) -> None:
        seed = _make_seed(mutations=[])
        results = compile_mutations(seed, [_make_atom()])
        assert results == []


# ------------------------------------------------------------------
# compile_all_mutations (all seeds)
# ------------------------------------------------------------------


class TestCompileAllMutations:
    def test_across_multiple_seeds(self) -> None:
        s1 = _make_seed(seed_id="s1", mutations=[_make_mutation("omit")])
        s2 = _make_seed(seed_id="s2", mutations=[_make_mutation("delay", delay=90)])
        atoms = [_make_atom()]
        results = compile_all_mutations([s1, s2], atoms)
        assert len(results) == 2

    def test_empty_seeds(self) -> None:
        assert compile_all_mutations([], []) == []
