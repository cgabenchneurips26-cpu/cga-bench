"""Tests for sgsc.compilers.constraint_compiler."""

from __future__ import annotations

import pytest
from sgsc.compilers.constraint_compiler import (
    atom_to_derived_constraint,
    atoms_to_derived_constraints,
)
from sgsc.schemas.atom import (
    AtomAction,
    AtomConstraint,
    AtomEvidence,
    PopulationCriteria,
    RecommendationAtom,
    ScenarioHooks,
    SourceReference,
)

# Import DerivedConstraint to verify output type
from cga_bench.cpg_model.constraint_derivation import DerivedConstraint

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_atom(
    constraint_type: str = "REQUIRED",
    rec_class: str = "I",
    evidence_level: str = "A",
    action_id: str = "give_abx",
    atom_id: str = "atom_1",
    guideline_id: str = "ssc_2021",
    exclusion: list[str] | None = None,
) -> RecommendationAtom:
    return RecommendationAtom(
        atom_id=atom_id,
        source=SourceReference(
            guideline_id=guideline_id,
            section="Hour-1 Bundle",
            page="42",
            quote="Administer antibiotics within 1 hour.",
        ),
        population=PopulationCriteria(
            inclusion=["sepsis"],
            exclusion=exclusion or [],
        ),
        action=AtomAction(canonical_id=action_id, action_type="medication"),
        constraint=AtomConstraint(type=constraint_type, deadline_minutes=60),
        evidence=AtomEvidence(system="GRADE", recommendation_class=rec_class, level=evidence_level),
        scenario_hooks=ScenarioHooks(),
    )


# ------------------------------------------------------------------
# Output type
# ------------------------------------------------------------------


class TestOutputType:
    def test_returns_dataclass(self) -> None:
        atom = _make_atom()
        result = atom_to_derived_constraint(atom)
        assert isinstance(result, DerivedConstraint)

    def test_not_pydantic(self) -> None:
        atom = _make_atom()
        result = atom_to_derived_constraint(atom)
        # DerivedConstraint is a @dataclass, not BaseModel
        assert not hasattr(result, "model_dump")


# ------------------------------------------------------------------
# Field mapping
# ------------------------------------------------------------------


class TestFieldMapping:
    def test_constraint_type(self) -> None:
        atom = _make_atom(constraint_type="FORBIDDEN")
        dc = atom_to_derived_constraint(atom)
        assert dc.constraint_type == "FORBIDDEN"

    def test_actions_list(self) -> None:
        atom = _make_atom(action_id="order_troponin")
        dc = atom_to_derived_constraint(atom)
        assert dc.actions == ["order_troponin"]

    def test_provenance_format(self) -> None:
        atom = _make_atom(atom_id="atom_42", guideline_id="aha_2021")
        dc = atom_to_derived_constraint(atom)
        assert dc.provenance == "sgsc:atom:atom_42:source:aha_2021"

    def test_evidence_field(self) -> None:
        atom = _make_atom()
        dc = atom_to_derived_constraint(atom)
        assert "Hour-1 Bundle" in dc.evidence
        assert "page 42" in dc.evidence

    def test_recommendation_class(self) -> None:
        atom = _make_atom(rec_class="IIa")
        dc = atom_to_derived_constraint(atom)
        assert dc.recommendation_class == "IIa"

    def test_evidence_level(self) -> None:
        atom = _make_atom(evidence_level="B-R")
        dc = atom_to_derived_constraint(atom)
        assert dc.evidence_level == "B-R"

    def test_source_guideline(self) -> None:
        atom = _make_atom(guideline_id="kdigo_aki")
        dc = atom_to_derived_constraint(atom)
        assert dc.source_guideline == "kdigo_aki"


# ------------------------------------------------------------------
# Authority classification
# ------------------------------------------------------------------


class TestAuthorityClassification:
    @pytest.mark.parametrize(
        ("rec_class", "level", "expected"),
        [
            ("I", "A", "high"),
            ("I", "B", "high"),
            ("I", "B-R", "high"),
            ("I", "B-NR", "high"),
            ("IIa", "A", "high"),
            ("I", "C", "low"),
            ("IIa", "C", "low"),
            ("IIb", "A", "low"),
            ("III", "A", "low"),
            ("IIb", "C", "low"),
        ],
    )
    def test_authority_tier(self, rec_class: str, level: str, expected: str) -> None:
        atom = _make_atom(rec_class=rec_class, evidence_level=level)
        dc = atom_to_derived_constraint(atom)
        assert dc.authority_tier == expected


# ------------------------------------------------------------------
# Severity mapping
# ------------------------------------------------------------------


class TestSeverityMapping:
    def test_forbidden_high_evidence(self) -> None:
        atom = _make_atom(constraint_type="FORBIDDEN", evidence_level="A")
        dc = atom_to_derived_constraint(atom)
        assert dc.severity == "CRITICAL"

    def test_forbidden_low_evidence(self) -> None:
        atom = _make_atom(constraint_type="FORBIDDEN", evidence_level="C")
        dc = atom_to_derived_constraint(atom)
        assert dc.severity == "HIGH"  # downgraded from CRITICAL

    def test_required_high_evidence(self) -> None:
        atom = _make_atom(constraint_type="REQUIRED", evidence_level="A")
        dc = atom_to_derived_constraint(atom)
        assert dc.severity == "HIGH"

    def test_required_low_evidence(self) -> None:
        atom = _make_atom(constraint_type="REQUIRED", evidence_level="C")
        dc = atom_to_derived_constraint(atom)
        assert dc.severity == "MODERATE"

    def test_before_severity(self) -> None:
        atom = _make_atom(constraint_type="BEFORE", evidence_level="A")
        dc = atom_to_derived_constraint(atom)
        assert dc.severity == "MODERATE"


# ------------------------------------------------------------------
# Conditionality
# ------------------------------------------------------------------


class TestConditionality:
    def test_unconditional(self) -> None:
        atom = _make_atom(exclusion=[])
        dc = atom_to_derived_constraint(atom)
        assert dc.is_conditional is False
        assert dc.condition_met == "unconditional"

    def test_conditional_with_exclusion(self) -> None:
        atom = _make_atom(exclusion=["renal_failure"])
        dc = atom_to_derived_constraint(atom)
        assert dc.is_conditional is True
        assert dc.condition_met == "population_criteria"


# ------------------------------------------------------------------
# Batch conversion
# ------------------------------------------------------------------


class TestBatchConversion:
    def test_multiple_atoms(self) -> None:
        atoms = [_make_atom(atom_id=f"a{i}") for i in range(5)]
        results = atoms_to_derived_constraints(atoms)
        assert len(results) == 5
        assert all(isinstance(r, DerivedConstraint) for r in results)

    def test_empty_list(self) -> None:
        assert atoms_to_derived_constraints([]) == []
