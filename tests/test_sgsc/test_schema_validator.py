"""Tests for sgsc.extraction.schema_validator — business-rule validation."""

from __future__ import annotations

from sgsc.extraction.schema_validator import validate_atoms
from sgsc.schemas.atom import (
    AtomAction,
    AtomConstraint,
    AtomEvidence,
    AtomSequence,
    PopulationCriteria,
    RecommendationAtom,
    SourceReference,
)


def _make_atom(
    atom_id: str = "test_001",
    canonical_id: str = "give_medication",
    constraint_type: str = "REQUIRED",
    deadline_minutes: int | None = None,
    quote: str = "A long enough quote for validation purposes here.",
    evidence_system: str = "GRADE",
    before: list[str] | None = None,
) -> RecommendationAtom:
    """Helper to create a minimal valid atom with overrides."""
    return RecommendationAtom(
        atom_id=atom_id,
        source=SourceReference(
            guideline_id="test_guideline",
            section="Section A",
            quote=quote,
        ),
        population=PopulationCriteria(inclusion=["all"], exclusion=[]),
        action=AtomAction(canonical_id=canonical_id, action_type="medication"),
        constraint=AtomConstraint(
            type=constraint_type,
            deadline_minutes=deadline_minutes,
        ),
        sequence=AtomSequence(before=before or []),
        evidence=AtomEvidence(
            system=evidence_system,
            recommendation_class="I",
            level="A",
        ),
    )


class TestValidateAtoms:
    """Tests for validate_atoms function."""

    def test_valid_atom_passes(self) -> None:
        atom = _make_atom()
        result = validate_atoms([atom])
        assert len(result.valid_atoms) == 1
        assert len(result.rejected_atoms) == 0
        assert result.error_count == 0

    def test_non_snake_case_action_id_rejected(self) -> None:
        atom = _make_atom(canonical_id="GiveMedication")
        result = validate_atoms([atom])
        assert len(result.rejected_atoms) == 1
        assert any("snake_case" in i.message for i in result.issues)

    def test_action_id_with_hyphens_rejected(self) -> None:
        atom = _make_atom(canonical_id="give-medication")
        result = validate_atoms([atom])
        assert len(result.rejected_atoms) == 1

    def test_action_id_too_long_rejected(self) -> None:
        atom = _make_atom(canonical_id="a" * 81)
        result = validate_atoms([atom])
        assert len(result.rejected_atoms) == 1
        assert any("exceeds" in i.message for i in result.issues)

    def test_short_quote_warning_not_rejection(self) -> None:
        atom = _make_atom(quote="Short quote text.")
        result = validate_atoms([atom])
        # Short quote is a warning, not an error — should still pass
        assert len(result.valid_atoms) == 1
        assert any(i.severity == "warning" and "short" in i.message for i in result.issues)

    def test_within_without_deadline_rejected(self) -> None:
        atom = _make_atom(constraint_type="WITHIN", deadline_minutes=None)
        result = validate_atoms([atom])
        assert len(result.rejected_atoms) == 1
        assert any("deadline_minutes" in i.message for i in result.issues)

    def test_within_with_deadline_passes(self) -> None:
        atom = _make_atom(constraint_type="WITHIN", deadline_minutes=60)
        result = validate_atoms([atom])
        assert len(result.valid_atoms) == 1

    def test_before_empty_list_warning(self) -> None:
        atom = _make_atom(constraint_type="BEFORE", before=[])
        result = validate_atoms([atom])
        # Warning, not error — still valid
        assert len(result.valid_atoms) == 1
        assert any(i.severity == "warning" and "before" in i.message.lower() for i in result.issues)

    def test_before_with_list_no_warning(self) -> None:
        atom = _make_atom(constraint_type="BEFORE", before=["prior_action"])
        result = validate_atoms([atom])
        before_warnings = [i for i in result.issues if "before" in i.message.lower()]
        assert len(before_warnings) == 0

    def test_unknown_evidence_system_warning(self) -> None:
        atom = _make_atom(evidence_system="UNKNOWN_SYSTEM")
        result = validate_atoms([atom])
        assert len(result.valid_atoms) == 1
        assert any("Unknown evidence system" in i.message for i in result.issues)

    def test_known_evidence_systems_no_warning(self) -> None:
        for system in ("AHA", "GRADE", "NICE", "ESC", "ACC"):
            atom = _make_atom(evidence_system=system)
            result = validate_atoms([atom])
            system_warnings = [i for i in result.issues if "evidence system" in i.message.lower()]
            assert len(system_warnings) == 0, f"Unexpected warning for {system}"

    def test_reject_on_error_false_keeps_all(self) -> None:
        atom = _make_atom(canonical_id="InvalidCamelCase")
        result = validate_atoms([atom], reject_on_error=False)
        assert len(result.valid_atoms) == 1
        assert len(result.rejected_atoms) == 0
        assert result.error_count > 0

    def test_multiple_atoms_mixed(self) -> None:
        good = _make_atom(atom_id="good_001")
        bad = _make_atom(atom_id="bad_001", canonical_id="BadCase")
        result = validate_atoms([good, bad])
        assert len(result.valid_atoms) == 1
        assert len(result.rejected_atoms) == 1
        assert result.valid_atoms[0].atom_id == "good_001"

    def test_empty_list(self) -> None:
        result = validate_atoms([])
        assert len(result.valid_atoms) == 0
        assert result.total_issues == 0

    def test_result_properties(self) -> None:
        atom = _make_atom(canonical_id="BadCase", quote="Short.")
        result = validate_atoms([atom])
        assert result.total_issues >= 2  # error + warning
        assert result.error_count >= 1
