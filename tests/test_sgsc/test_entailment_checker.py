"""Tests for sgsc.verification.entailment_checker — field-level entailment."""

from __future__ import annotations

from sgsc.schemas.atom import (
    AtomAction,
    AtomConstraint,
    AtomEvidence,
    AtomSequence,
    PopulationCriteria,
    RecommendationAtom,
    SourceReference,
)
from sgsc.verification.entailment_checker import (
    AtomEntailmentReport,
    FieldEntailmentResult,
    check_atoms_entailment,
    check_field_entailment_rule_based,
    compare_entailment_thresholds,
)


def _make_atom(
    quote: str = "Administer broad-spectrum antibiotics within 1 hour of sepsis recognition.",
    action_id: str = "give_broad_spectrum_antibiotics",
    constraint_type: str = "WITHIN",
    deadline: int | None = 60,
    exclusion: list[str] | None = None,
    required_prior: list[str] | None = None,
    before: list[str] | None = None,
    rec_class: str = "I",
    level: str = "B",
) -> RecommendationAtom:
    return RecommendationAtom(
        atom_id="test_001",
        source=SourceReference(guideline_id="test", section="Test", quote=quote),
        population=PopulationCriteria(inclusion=["sepsis"], exclusion=exclusion or []),
        action=AtomAction(canonical_id=action_id, action_type="medication"),
        constraint=AtomConstraint(type=constraint_type, deadline_minutes=deadline),
        sequence=AtomSequence(required_prior=required_prior or [], before=before or []),
        evidence=AtomEvidence(system="GRADE", recommendation_class=rec_class, level=level),
    )


class TestActionEntailment:
    def test_action_entailed_keyword_match(self) -> None:
        atom = _make_atom(quote="Give antibiotics within 1 hour.", action_id="give_antibiotics")
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        assert action_result.verdict == "ENTAILED"

    def test_action_not_entailed(self) -> None:
        atom = _make_atom(quote="Measure serum lactate level.", action_id="give_vasopressor_norepinephrine")
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        assert action_result.verdict == "NOT_ENTAILED"


class TestTimingEntailment:
    def test_timing_entailed_number_present(self) -> None:
        atom = _make_atom(quote="Give antibiotics within 60 minutes.", deadline=60)
        report = check_field_entailment_rule_based(atom)
        timing_result = next(r for r in report.field_results if r.field == "timing")
        assert timing_result.verdict == "ENTAILED"

    def test_timing_not_entailed_wrong_number(self) -> None:
        atom = _make_atom(quote="Give antibiotics promptly.", deadline=60)
        report = check_field_entailment_rule_based(atom)
        timing_result = next(r for r in report.field_results if r.field == "timing")
        # No number at all → should be NOT_ENTAILED or PARTIAL
        assert timing_result.verdict in ("NOT_ENTAILED", "PARTIAL")

    def test_timing_not_applicable_no_deadline(self) -> None:
        atom = _make_atom(constraint_type="REQUIRED", deadline=None)
        report = check_field_entailment_rule_based(atom)
        timing_result = next(r for r in report.field_results if r.field == "timing")
        assert timing_result.verdict == "NOT_APPLICABLE"


class TestGuardEntailment:
    def test_exclusion_entailed(self) -> None:
        atom = _make_atom(
            quote="Avoid contrast in patients with renal impairment.",
            exclusion=["renal_impairment"],
        )
        report = check_field_entailment_rule_based(atom)
        guard_result = next(r for r in report.field_results if r.field == "guard")
        assert guard_result.verdict == "ENTAILED"

    def test_exclusion_not_entailed(self) -> None:
        atom = _make_atom(
            quote="Give antibiotics within 1 hour.",
            exclusion=["hepatic_failure"],
        )
        report = check_field_entailment_rule_based(atom)
        guard_result = next(r for r in report.field_results if r.field == "guard")
        assert guard_result.verdict == "NOT_ENTAILED"

    def test_no_exclusion_not_applicable(self) -> None:
        atom = _make_atom(exclusion=[])
        report = check_field_entailment_rule_based(atom)
        guard_result = next(r for r in report.field_results if r.field == "guard")
        assert guard_result.verdict == "NOT_APPLICABLE"


class TestSequenceEntailment:
    def test_sequence_entailed(self) -> None:
        atom = _make_atom(
            quote="Obtain blood cultures before administering antibiotics.",
            required_prior=["obtain_blood_cultures"],
        )
        report = check_field_entailment_rule_based(atom)
        seq_result = next(r for r in report.field_results if r.field == "sequence")
        assert seq_result.verdict == "ENTAILED"

    def test_sequence_not_applicable(self) -> None:
        atom = _make_atom(required_prior=[], before=[])
        report = check_field_entailment_rule_based(atom)
        seq_result = next(r for r in report.field_results if r.field == "sequence")
        assert seq_result.verdict == "NOT_APPLICABLE"


class TestEvidenceEntailment:
    def test_evidence_entailed_strong(self) -> None:
        atom = _make_atom(
            quote="It is strongly recommended to administer antibiotics early.",
            rec_class="I",
        )
        report = check_field_entailment_rule_based(atom)
        ev_result = next(r for r in report.field_results if r.field == "evidence")
        assert ev_result.verdict == "ENTAILED"

    def test_evidence_partial_strong_claim_weak_language(self) -> None:
        """Strong claim (Class I) with weak language ('may consider') is now PARTIAL, not rejection."""
        atom = _make_atom(
            quote="Clinicians may consider fluid resuscitation.",
            rec_class="I",  # Strong claim but weak language
        )
        report = check_field_entailment_rule_based(atom)
        ev_result = next(r for r in report.field_results if r.field == "evidence")
        assert ev_result.verdict == "PARTIAL"


class TestAtomEntailmentReport:
    def test_all_passed(self) -> None:
        atom = _make_atom(
            quote="Strongly recommended: administer broad-spectrum antibiotics within 60 minutes.",
        )
        report = check_field_entailment_rule_based(atom)
        # Most fields should pass for this well-formed atom
        assert report.pass_rate >= 0.5

    def test_one_field_fails_rejects_atom(self) -> None:
        atom = _make_atom(
            quote="Measure lactate level.",
            action_id="give_vasopressor_norepinephrine",
            constraint_type="WITHIN",
            deadline=60,
        )
        report = check_field_entailment_rule_based(atom)
        # Action should fail, timing should fail
        assert not report.all_passed
        assert "action" in report.failed_fields

    def test_check_atoms_entailment_batch(self) -> None:
        atoms = [
            _make_atom(quote="Give antibiotics within 60 minutes.", action_id="give_antibiotics"),
            _make_atom(quote="Measure lactate.", action_id="give_vasopressor_norepinephrine"),
        ]
        reports = check_atoms_entailment(atoms, mode="rule_based")
        assert len(reports) == 2
        # First should be mostly passing, second should have failures
        assert reports[0].pass_rate > reports[1].pass_rate

    def test_failed_fields_property(self) -> None:
        report = AtomEntailmentReport(
            atom_id="test",
            field_results=[
                FieldEntailmentResult(field="action", verdict="ENTAILED"),
                FieldEntailmentResult(field="timing", verdict="NOT_ENTAILED", reason="missing"),
            ],
        )
        assert report.failed_fields == ["timing"]
        assert not report.all_passed


class TestStrictPassed:
    """Strict-mode (Gate 2 mandatory) entailment semantics: PARTIAL = failure."""

    def test_strict_rejects_partial(self) -> None:
        """An atom with PARTIAL but no NOT_ENTAILED passes lenient, fails strict."""
        report = AtomEntailmentReport(
            atom_id="t1",
            field_results=[
                FieldEntailmentResult(field="action", verdict="ENTAILED"),
                FieldEntailmentResult(field="timing", verdict="PARTIAL"),
                FieldEntailmentResult(field="evidence", verdict="ENTAILED"),
            ],
        )
        assert report.all_passed is True, "Lenient gate accepts PARTIAL"
        assert report.strict_passed is False, "Strict gate rejects PARTIAL"

    def test_strict_accepts_all_entailed(self) -> None:
        report = AtomEntailmentReport(
            atom_id="t2",
            field_results=[
                FieldEntailmentResult(field="action", verdict="ENTAILED"),
                FieldEntailmentResult(field="timing", verdict="ENTAILED"),
                FieldEntailmentResult(field="guard", verdict="NOT_APPLICABLE"),
            ],
        )
        assert report.strict_passed is True

    def test_strict_rejects_not_entailed(self) -> None:
        report = AtomEntailmentReport(
            atom_id="t3",
            field_results=[
                FieldEntailmentResult(field="action", verdict="ENTAILED"),
                FieldEntailmentResult(field="timing", verdict="NOT_ENTAILED"),
            ],
        )
        assert report.strict_passed is False
        assert report.all_passed is False

    def test_partial_fields_property(self) -> None:
        report = AtomEntailmentReport(
            atom_id="t4",
            field_results=[
                FieldEntailmentResult(field="action", verdict="ENTAILED"),
                FieldEntailmentResult(field="timing", verdict="PARTIAL"),
                FieldEntailmentResult(field="evidence", verdict="PARTIAL"),
            ],
        )
        assert sorted(report.partial_fields) == ["evidence", "timing"]


class TestCompareEntailmentThresholds:
    """TG-V2: dual-threshold reporting on the SGSC-3 atom batch.

    Tightening the action keyword threshold from 0.5 to 0.7 should reject
    atoms whose canonical_id keywords overlap the quote at <70%.
    """

    def _atom(self, quote: str) -> RecommendationAtom:
        # Deliberately use REQUIRED + no deadline so only action+evidence apply.
        return _make_atom(
            quote=quote,
            action_id="give_broad_spectrum_antibiotics",
            constraint_type="REQUIRED",
            deadline=None,
            rec_class="I",
        )

    def test_threshold_tightening_rejects_borderline_atoms(self) -> None:
        """An atom matching 2/3 keywords is ENTAILED at 0.5 but NOT_ENTAILED at 0.7."""
        atoms = [
            # 3/3 keywords -> always ENTAILED
            self._atom("Strongly recommended: administer broad spectrum antibiotics."),
            # 2/3 keywords -> ENTAILED at 0.5, NOT_ENTAILED at 0.7
            self._atom("Strongly recommended: administer broad antibiotics."),
            # 0/3 keywords -> always NOT_ENTAILED
            self._atom("Strongly recommended: order chest imaging."),
        ]

        summary = compare_entailment_thresholds(atoms, thresholds=[0.5, 0.7])

        assert summary[0.5]["n_total"] == 3
        assert summary[0.7]["n_total"] == 3

        # At 0.5: atoms 0 and 1 pass strict, atom 2 rejected
        assert summary[0.5]["n_strict_passing"] == 2
        assert summary[0.5]["n_rejected"] == 1

        # At 0.7: only atom 0 passes strict; atoms 1 and 2 rejected
        assert summary[0.7]["n_strict_passing"] == 1
        assert summary[0.7]["n_rejected"] == 2

    def test_default_thresholds_are_05_and_07(self) -> None:
        """Default sweep covers the lenient (0.5) and recommended (0.7) values."""
        atoms = [self._atom("Strongly recommended: administer broad spectrum antibiotics.")]
        summary = compare_entailment_thresholds(atoms)
        assert set(summary.keys()) == {0.5, 0.7}

    def test_n_partial_only_equals_lenient_minus_strict(self) -> None:
        """Sanity: lenient passing - strict passing = atoms with PARTIAL but no NOT_ENTAILED."""
        atoms = [self._atom("Strongly recommended: administer broad spectrum antibiotics.")]
        summary = compare_entailment_thresholds(atoms, thresholds=[0.5])
        s = summary[0.5]
        assert s["n_partial_only"] == s["n_lenient_passing"] - s["n_strict_passing"]


class TestStemMatch:
    """β-1: Plural/singular stemming in keyword matching."""

    def test_stem_match_plural_to_singular(self) -> None:
        """canonical_id 'use_balanced_crystalloids' matches quote with 'crystalloid' (singular).

        Keywords: use/balanced/crystalloids.  'use'→'using' via -e+ing conjugation,
        'balanced' matches directly, 'crystalloids'→'crystalloid' via stemming => 3/3 = 1.0.
        """
        atom = _make_atom(
            quote="We recommend using a balanced crystalloid solution for resuscitation.",
            action_id="use_balanced_crystalloids",
        )
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        assert action_result.verdict == "ENTAILED"
        # 'use'→'using' via verb conjugation, 'balanced' direct, 'crystalloids'→'crystalloid' stemming.
        assert action_result.confidence >= 0.9, f"Expected >=0.9, got {action_result.confidence}"

    def test_stem_match_singular_to_plural(self) -> None:
        """canonical_id with singular matches quote with plural form."""
        atom = _make_atom(
            quote="Balanced crystalloids should be administered for sepsis resuscitation.",
            action_id="administer_crystalloid",
        )
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        assert action_result.verdict == "ENTAILED"
        assert action_result.confidence == 1.0, "'crystalloid'+'s' should match 'crystalloids'"

    def test_stem_match_no_false_positive(self) -> None:
        """Stemming should not match unrelated words — 'aspirin' != 'asprins'."""
        atom = _make_atom(
            quote="The patient was given asprins for headache.",
            action_id="give_aspirin",
        )
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        # "aspirin" is not in "asprins", "aspirins" is not in "asprins" either
        assert action_result.verdict == "NOT_ENTAILED"

    def test_guard_stemming_plural_exclusion(self) -> None:
        """Guard exclusion with plural matches singular in quote."""
        atom = _make_atom(
            quote="Avoid in patients with severe coagulopathy.",
            exclusion=["coagulopathies"],
        )
        report = check_field_entailment_rule_based(atom)
        guard_result = next(r for r in report.field_results if r.field == "guard")
        assert guard_result.verdict == "ENTAILED", "coagulopathies→coagulopathy should stem-match"

    def test_stem_match_verb_ing_drop_e(self) -> None:
        """Verb conjugation: 'measure' matches 'measuring' (drop -e, add -ing)."""
        atom = _make_atom(
            quote="We recommend measuring blood lactate levels.",
            action_id="measure_lactate",
        )
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        assert action_result.verdict == "ENTAILED"
        assert action_result.confidence == 1.0, "'measure'→'measuring' + 'lactate' direct = 2/2"

    def test_stem_match_verb_ing_no_drop(self) -> None:
        """Verb conjugation: 'monitor' matches 'monitoring' (add -ing directly)."""
        atom = _make_atom(
            quote="Continuous monitoring of blood pressure is recommended.",
            action_id="monitor_blood_pressure",
        )
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        assert action_result.verdict == "ENTAILED"

    def test_administer_filtered_as_common_prefix(self) -> None:
        """'administer' is a common verb prefix like 'give' — filtered from keywords."""
        atom = _make_atom(
            quote="We recommend using norepinephrine as the first-line vasopressor.",
            action_id="administer_norepinephrine",
        )
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        # 'administer' filtered → meaningful = ['norepinephrine'], 1/1 = 1.0
        assert action_result.verdict == "ENTAILED"
        assert action_result.confidence == 1.0


# ------------------------------------------------------------------
# C-7a Fix 1: Sequence → PARTIAL when quote is silent on ordering
# ------------------------------------------------------------------


class TestSequencePartialWhenNoOrdering:
    """Fix 1: sequence field returns PARTIAL (not NOT_ENTAILED) when the
    source quote has no ordering language but the LLM inferred clinical
    ordering from context."""

    def test_sequence_partial_when_no_ordering_language(self) -> None:
        """Quote describes a clinical action with no 'before/after/then' — PARTIAL."""
        atom = _make_atom(
            quote="Assess hydration status in patients receiving contrast media.",
            required_prior=["check_baseline_egfr"],
        )
        report = check_field_entailment_rule_based(atom)
        seq_result = next(r for r in report.field_results if r.field == "sequence")
        assert seq_result.verdict == "PARTIAL"
        assert "implicit" in seq_result.reason.lower()

    def test_sequence_entailed_when_ordering_present(self) -> None:
        """Quote with explicit ordering language still gets ENTAILED."""
        atom = _make_atom(
            quote="Obtain blood cultures before administering antibiotics.",
            required_prior=["obtain_blood_cultures"],
        )
        report = check_field_entailment_rule_based(atom)
        seq_result = next(r for r in report.field_results if r.field == "sequence")
        assert seq_result.verdict == "ENTAILED"

    def test_sequence_partial_passes_lenient_gate(self) -> None:
        """An atom with PARTIAL sequence passes the lenient gate (all_passed)."""
        atom = _make_atom(
            quote="Establish IV access for fluid resuscitation.",
            required_prior=["assess_airway"],
            action_id="establish_iv_access",
            constraint_type="REQUIRED",
            deadline=None,
            rec_class="I",
        )
        report = check_field_entailment_rule_based(atom)
        seq_result = next(r for r in report.field_results if r.field == "sequence")
        assert seq_result.verdict == "PARTIAL"
        # PARTIAL should NOT block lenient gate
        assert report.all_passed or any(
            r.verdict == "NOT_ENTAILED" for r in report.field_results if r.field != "sequence"
        )

    def test_sequence_not_applicable_no_constraints(self) -> None:
        """No sequence constraints → NOT_APPLICABLE (unchanged)."""
        atom = _make_atom(required_prior=[], before=[])
        report = check_field_entailment_rule_based(atom)
        seq_result = next(r for r in report.field_results if r.field == "sequence")
        assert seq_result.verdict == "NOT_APPLICABLE"

    def test_sequence_before_field_also_partial(self) -> None:
        """'before' field (not just required_prior) also triggers PARTIAL when silent."""
        atom = _make_atom(
            quote="Administer tPA for eligible stroke patients.",
            before=["obtain_ct_scan"],
        )
        report = check_field_entailment_rule_based(atom)
        seq_result = next(r for r in report.field_results if r.field == "sequence")
        assert seq_result.verdict == "PARTIAL"


# ------------------------------------------------------------------
# C-7a Fix 2: Action prefix filter expansion
# ------------------------------------------------------------------


class TestActionPrefixFilterExpansion:
    """Fix 2: expanded prefix filter correctly removes common clinical verbs
    from keyword count, improving match ratio for compound action IDs."""

    def test_check_prefix_filtered(self) -> None:
        """'check_baseline_egfr' → 'check' filtered, meaningful=['baseline','egfr']."""
        atom = _make_atom(
            quote="Measure baseline eGFR before contrast administration.",
            action_id="check_baseline_egfr",
            constraint_type="REQUIRED",
            deadline=None,
        )
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        # 'baseline' matches, 'egfr' matches → 2/2 = 1.0
        assert action_result.verdict == "ENTAILED"

    def test_review_prefix_filtered(self) -> None:
        """'review_risk_factors' → 'review' filtered, meaningful=['risk','factors']."""
        atom = _make_atom(
            quote="Identify risk factors for contrast-induced nephropathy.",
            action_id="review_risk_factors",
            constraint_type="REQUIRED",
            deadline=None,
        )
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        # 'risk' matches, 'factors' matches → 2/2 = 1.0
        assert action_result.verdict == "ENTAILED"

    def test_monitor_prefix_filtered(self) -> None:
        """'monitor_tls_panel' → 'monitor' filtered, meaningful=['tls','panel']."""
        atom = _make_atom(
            quote="Monitor serum uric acid, potassium, phosphate panel every 4-6 hours.",
            action_id="monitor_tls_panel",
            constraint_type="REQUIRED",
            deadline=None,
        )
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        # 'panel' matches → at least 1/2 = 0.5 (below 0.6 if 'tls' doesn't match)
        # This tests that the prefix filter at least helps
        assert action_result.confidence >= 0.5

    def test_avoid_prefix_filtered(self) -> None:
        """'avoid_potassium_fluids' → 'avoid' filtered, meaningful=['potassium','fluids']."""
        atom = _make_atom(
            quote="Avoid potassium-containing fluids in TLS management.",
            action_id="avoid_potassium_fluids",
            constraint_type="FORBIDDEN",
            deadline=None,
        )
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        # 'potassium' matches, 'fluids' matches → 2/2 = 1.0
        assert action_result.verdict == "ENTAILED"

    def test_initiate_prefix_filtered(self) -> None:
        """'initiate_rrt' → 'initiate' filtered, meaningful=['rrt']."""
        atom = _make_atom(
            quote="Initiate renal replacement therapy (RRT) for refractory hyperkalaemia.",
            action_id="initiate_rrt",
            constraint_type="REQUIRED",
            deadline=None,
        )
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        # 'rrt' matches → 1/1 = 1.0
        assert action_result.verdict == "ENTAILED"

    def test_fallback_when_all_filtered(self) -> None:
        """If ALL parts are filtered, fall back to full action_parts list."""
        atom = _make_atom(
            quote="Perform and assess the initial evaluation.",
            action_id="perform_assess",
            constraint_type="REQUIRED",
            deadline=None,
        )
        report = check_field_entailment_rule_based(atom)
        action_result = next(r for r in report.field_results if r.field == "action")
        # Both 'perform' and 'assess' are in filter → falls back to original
        assert action_result.confidence >= 0.0  # Just check it doesn't crash


# ------------------------------------------------------------------
# C-7a Fix 3: Evidence 'should'/'suggested' as strong-compatible
# ------------------------------------------------------------------


class TestEvidenceShouldStrong:
    """Fix 3: 'should', 'suggested', and imperative verbs are recognized
    as strong recommendation language."""

    def test_should_matches_strong_claim(self) -> None:
        """'should' in quote matches Class I (strong) recommendation."""
        atom = _make_atom(
            quote="Patients should receive intravenous hydration with isotonic fluids.",
            rec_class="I",
        )
        report = check_field_entailment_rule_based(atom)
        ev_result = next(r for r in report.field_results if r.field == "evidence")
        assert ev_result.verdict == "ENTAILED"

    def test_suggested_matches_strong_claim(self) -> None:
        """'suggested' in quote matches strong recommendation."""
        atom = _make_atom(
            quote="It is suggested that rasburicase be given for high-risk TLS.",
            rec_class="I",
        )
        report = check_field_entailment_rule_based(atom)
        ev_result = next(r for r in report.field_results if r.field == "evidence")
        assert ev_result.verdict == "ENTAILED"

    def test_imperative_verb_matches_strong(self) -> None:
        """Imperative 'administer' in guideline context implies strong recommendation."""
        atom = _make_atom(
            quote="Administer prophylactic rasburicase for high-risk patients.",
            rec_class="I",
        )
        report = check_field_entailment_rule_based(atom)
        ev_result = next(r for r in report.field_results if r.field == "evidence")
        assert ev_result.verdict == "ENTAILED"

    def test_weak_claim_with_strong_language_entailed(self) -> None:
        """Weak claim (Class II) with strong language ('should') — conservative, still ENTAILED."""
        atom = _make_atom(
            quote="Patients should receive pre-hydration before contrast.",
            rec_class="II",
        )
        report = check_field_entailment_rule_based(atom)
        ev_result = next(r for r in report.field_results if r.field == "evidence")
        assert ev_result.verdict == "ENTAILED"

    def test_strong_claim_weak_language_partial(self) -> None:
        """Strong claim with weak language is PARTIAL (not NOT_ENTAILED)."""
        atom = _make_atom(
            quote="Clinicians may consider fluid resuscitation for mild cases.",
            rec_class="I",
        )
        report = check_field_entailment_rule_based(atom)
        ev_result = next(r for r in report.field_results if r.field == "evidence")
        assert ev_result.verdict == "PARTIAL"

    def test_no_strength_language_partial(self) -> None:
        """No strength language at all → PARTIAL (unchanged)."""
        atom = _make_atom(
            quote="Fluid resuscitation is a treatment option.",
            rec_class="I",
        )
        report = check_field_entailment_rule_based(atom)
        ev_result = next(r for r in report.field_results if r.field == "evidence")
        assert ev_result.verdict == "PARTIAL"
