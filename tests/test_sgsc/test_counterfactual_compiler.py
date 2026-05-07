"""Tests for sgsc.compilers.counterfactual_compiler."""

from __future__ import annotations

from sgsc.compilers.counterfactual_compiler import (
    compile_exclusion_families,
    compile_families,
    compile_timing_families,
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
    exclusion: list[str] | None = None,
    counterfactual_pairs: list[str] | None = None,
    required_prior: list[str] | None = None,
) -> RecommendationAtom:
    return RecommendationAtom(
        atom_id=f"atom_{action_id}",
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
        sequence=AtomSequence(required_prior=required_prior or []),
        evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="A"),
        scenario_hooks=ScenarioHooks(counterfactual_pairs=counterfactual_pairs or []),
    )


# ------------------------------------------------------------------
# Exclusion families
# ------------------------------------------------------------------


class TestExclusionFamilies:
    def test_atom_with_exclusion_generates_family(self) -> None:
        atoms = [
            _make_atom(
                exclusion=["renal_failure"],
                counterfactual_pairs=["renal_failure"],
            ),
        ]
        families = compile_exclusion_families(atoms)
        assert len(families) == 1

    def test_family_has_two_members(self) -> None:
        atoms = [
            _make_atom(
                exclusion=["allergy_penicillin"],
                counterfactual_pairs=["allergy_penicillin"],
            ),
        ]
        families = compile_exclusion_families(atoms)
        assert len(families[0].members) == 2

    def test_eligible_vs_contraindicated(self) -> None:
        atoms = [
            _make_atom(
                exclusion=["renal_failure"],
                counterfactual_pairs=["renal_failure"],
            ),
        ]
        families = compile_exclusion_families(atoms)
        verdicts = {m.expected_verdict for m in families[0].members}
        assert "conformant" in verdicts
        assert "commission_violation" in verdicts

    def test_pivot_variable_set(self) -> None:
        atoms = [
            _make_atom(
                exclusion=["renal_failure"],
                counterfactual_pairs=["renal_failure"],
            ),
        ]
        families = compile_exclusion_families(atoms)
        assert families[0].pivot_variable == "renal_failure"

    def test_no_exclusion_no_family(self) -> None:
        atoms = [_make_atom(exclusion=[])]
        families = compile_exclusion_families(atoms)
        assert len(families) == 0

    def test_no_counterfactual_hook_no_family(self) -> None:
        atoms = [
            _make_atom(exclusion=["renal_failure"], counterfactual_pairs=[]),
        ]
        families = compile_exclusion_families(atoms)
        assert len(families) == 0


# ------------------------------------------------------------------
# Timing families
# ------------------------------------------------------------------


class TestTimingFamilies:
    def test_within_generates_timing_family(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=60)]
        families = compile_timing_families(atoms)
        assert len(families) == 1

    def test_timing_family_two_members(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=60)]
        families = compile_timing_families(atoms)
        assert len(families[0].members) == 2

    def test_timely_vs_late(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=60)]
        families = compile_timing_families(atoms)
        verdicts = {m.expected_verdict for m in families[0].members}
        assert "conformant" in verdicts
        assert "timing_violation" in verdicts

    def test_pivot_is_action_time(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=60)]
        families = compile_timing_families(atoms)
        assert families[0].pivot_variable == "action_time"

    def test_pivot_threshold_is_deadline(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=60)]
        families = compile_timing_families(atoms)
        assert families[0].pivot_threshold == 60.0

    def test_timely_at_60_pct(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=100)]
        families = compile_timing_families(atoms)
        timely_member = next(m for m in families[0].members if m.expected_verdict == "conformant")
        assert timely_member.patient_state["action_time"] == 60.0

    def test_late_at_150_pct(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=100)]
        families = compile_timing_families(atoms)
        late_member = next(m for m in families[0].members if m.expected_verdict == "timing_violation")
        assert late_member.patient_state["action_time"] == 150.0

    def test_required_no_timing_family(self) -> None:
        atoms = [_make_atom(constraint_type="REQUIRED")]
        families = compile_timing_families(atoms)
        assert len(families) == 0

    def test_within_no_deadline_no_family(self) -> None:
        atoms = [_make_atom(constraint_type="WITHIN", deadline=None)]
        families = compile_timing_families(atoms)
        assert len(families) == 0


# ------------------------------------------------------------------
# Combined compile_families
# ------------------------------------------------------------------


class TestCompileFamilies:
    def test_combines_both_types(self) -> None:
        atoms = [
            _make_atom(
                constraint_type="WITHIN",
                deadline=60,
                action_id="give_abx",
            ),
            _make_atom(
                constraint_type="REQUIRED",
                action_id="give_contrast",
                exclusion=["renal_failure"],
                counterfactual_pairs=["renal_failure"],
            ),
        ]
        families = compile_families(atoms)
        # Phase D: compile_families now also generates alternative families,
        # so give_contrast produces exclusion + alternative = 2, plus timing for give_abx = 1 total 3.
        assert len(families) == 3

    def test_empty_atoms(self) -> None:
        families = compile_families([])
        assert families == []


# ------------------------------------------------------------------
# Sequence families — Phase D
# ------------------------------------------------------------------


class TestSequenceFamilies:
    def test_sequence_family_generated(self) -> None:
        """Atoms with required_prior generate sequence families."""
        from sgsc.compilers.counterfactual_compiler import compile_sequence_families

        atoms = [_make_atom(required_prior=["obtain_blood_cultures"])]
        families = compile_sequence_families(atoms)
        assert len(families) == len(atoms)

    def test_sequence_family_has_correct_and_wrong_order(self) -> None:
        """Each sequence family has conformant + sequence_violation members."""
        from sgsc.compilers.counterfactual_compiler import compile_sequence_families

        atoms = [_make_atom(required_prior=["obtain_blood_cultures"])]
        families = compile_sequence_families(atoms)
        for fam in families:
            verdicts = {m.expected_verdict for m in fam.members}
            assert "conformant" in verdicts
            assert "sequence_violation" in verdicts

    def test_sequence_family_correct_trace_order(self) -> None:
        """Correct trace should have priors before the main action."""
        from sgsc.compilers.counterfactual_compiler import compile_sequence_families

        atoms = [_make_atom(required_prior=["obtain_blood_cultures"])]
        families = compile_sequence_families(atoms)
        for fam in families:
            trace = fam.shared_trace_template
            if len(trace) >= 2:
                assert trace[-1].time_minutes >= trace[0].time_minutes

    def test_no_sequence_no_family(self) -> None:
        """Atoms without sequence constraints produce no families."""
        from sgsc.compilers.counterfactual_compiler import compile_sequence_families

        atoms = [_make_atom()]
        families = compile_sequence_families(atoms)
        assert len(families) == 0

    def test_sequence_family_pivot_variable(self) -> None:
        """Sequence families use 'action_order' as pivot variable."""
        from sgsc.compilers.counterfactual_compiler import compile_sequence_families

        atoms = [_make_atom(required_prior=["step_a", "step_b"])]
        families = compile_sequence_families(atoms)
        assert families[0].pivot_variable == "action_order"


# ------------------------------------------------------------------
# Alternative families — Phase D
# ------------------------------------------------------------------


class TestAlternativeFamilies:
    def test_alternative_family_generated(self) -> None:
        """Atoms with counterfactual_pairs generate alternative families."""
        from sgsc.compilers.counterfactual_compiler import compile_alternative_families

        atoms = [_make_atom(counterfactual_pairs=["sepsis_vs_viral", "aki_vs_normal"])]
        families = compile_alternative_families(atoms)
        assert len(families) == 2

    def test_alternative_family_has_two_branches(self) -> None:
        """Each alternative family has primary + alternative members."""
        from sgsc.compilers.counterfactual_compiler import compile_alternative_families

        atoms = [_make_atom(counterfactual_pairs=["sepsis_vs_viral"])]
        families = compile_alternative_families(atoms)
        for fam in families:
            assert len(fam.members) >= 2
            verdicts = {m.expected_verdict for m in fam.members}
            assert "conformant" in verdicts
            assert "alternative_path" in verdicts

    def test_no_counterfactual_pairs_no_family(self) -> None:
        """Atoms without counterfactual_pairs produce no alternative families."""
        from sgsc.compilers.counterfactual_compiler import compile_alternative_families

        atoms = [_make_atom(counterfactual_pairs=[])]
        families = compile_alternative_families(atoms)
        assert len(families) == 0

    def test_alternative_family_pivot_variable(self) -> None:
        """Alternative family pivot_variable matches the pair name."""
        from sgsc.compilers.counterfactual_compiler import compile_alternative_families

        atoms = [_make_atom(counterfactual_pairs=["renal_failure"])]
        families = compile_alternative_families(atoms)
        assert families[0].pivot_variable == "renal_failure"

    def test_compile_families_includes_sequence_and_alternative(self) -> None:
        """compile_families now includes sequence and alternative families."""
        atoms = [
            _make_atom(
                constraint_type="WITHIN",
                deadline=60,
                action_id="give_abx",
                required_prior=["blood_culture"],
                counterfactual_pairs=["sepsis_vs_viral"],
            ),
        ]
        families = compile_families(atoms)
        family_ids = [f.family_id for f in families]
        # Should have timing, sequence, and alternative families
        assert any("timing" in fid for fid in family_ids)
        assert any("sequence" in fid for fid in family_ids)
        assert any("branch" in fid for fid in family_ids)
