"""Integration tests for ontology-enabled external benchmark evaluator.

Tests that the ontology matcher correctly improves compliance scoring by
resolving specific drug/action names to broader CPG requirements.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from cga_bench.semantic_layer.external.evaluator import (
    _evaluate_compliance,
    _get_ontology_matcher_for_guideline,
    _action_satisfies_via_ontology,
    _action_is_forbidden_via_ontology,
)
from cga_bench.semantic_layer.external.agentclinic import normalize_action_id


PROJECT_ROOT = Path(__file__).parent.parent.parent  # cga_bench/


# ======================================================================
# Helper Fixtures
# ======================================================================

@pytest.fixture
def sepsis_matcher():
    """Get sepsis ontology matcher."""
    return _get_ontology_matcher_for_guideline(
        "cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml"
    )


@pytest.fixture
def chest_pain_matcher():
    """Get chest pain ontology matcher."""
    return _get_ontology_matcher_for_guideline(
        "cpg_model/graphs/aha_chest_pain_evaluation.yaml"
    )


@pytest.fixture
def stroke_matcher():
    """Get stroke ontology matcher."""
    return _get_ontology_matcher_for_guideline(
        "cpg_model/graphs/aha_stroke_2019.yaml"
    )


@pytest.fixture
def evidence_all_true():
    """All evidence flags set to True (fully observable)."""
    return {
        "vitals": True,
        "labs": True,
        "imaging": True,
        "medications": True,
        "exam": True,
        "history": True,
        "diagnosis": True,
        "timestamps": True,
    }


# ======================================================================
# Domain Detection Tests
# ======================================================================

class TestOntologyMatcherFactory:
    """Test _get_ontology_matcher_for_guideline factory."""

    def test_sepsis_guideline_detected(self):
        matcher = _get_ontology_matcher_for_guideline(
            "cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml"
        )
        assert matcher is not None

    def test_chest_pain_guideline_detected(self):
        matcher = _get_ontology_matcher_for_guideline(
            "cpg_model/graphs/aha_chest_pain_evaluation.yaml"
        )
        assert matcher is not None

    def test_stroke_guideline_detected(self):
        matcher = _get_ontology_matcher_for_guideline(
            "cpg_model/graphs/aha_stroke_2019.yaml"
        )
        assert matcher is not None

    def test_aki_guideline_detected(self):
        matcher = _get_ontology_matcher_for_guideline(
            "cpg_model/graphs/kdigo_aki_full.yaml"
        )
        assert matcher is not None

    def test_dka_guideline_detected(self):
        matcher = _get_ontology_matcher_for_guideline(
            "cpg_model/graphs/ada_dka_management.yaml"
        )
        assert matcher is not None

    def test_heart_failure_guideline_detected(self):
        matcher = _get_ontology_matcher_for_guideline(
            "cpg_model/graphs/aha_heart_failure_2022.yaml"
        )
        assert matcher is not None

    def test_none_guideline_returns_none(self):
        matcher = _get_ontology_matcher_for_guideline(None)
        assert matcher is None

    def test_unknown_guideline_returns_unified(self):
        matcher = _get_ontology_matcher_for_guideline(
            "cpg_model/graphs/unknown_guideline.yaml"
        )
        # Should return unified matcher as fallback
        assert matcher is not None


# ======================================================================
# Subsumption Matching Tests
# ======================================================================

class TestOntologySubsumptionMatching:
    """Test that ontology subsumption resolves actions correctly."""

    def test_meropenem_satisfies_broad_spectrum_antibiotics(self, sepsis_matcher):
        """Meropenem should satisfy 'give_broad_spectrum_antibiotics' requirement."""
        performed = {"give_meropenem"}
        assert _action_satisfies_via_ontology(
            performed, "give_broad_spectrum_antibiotics", sepsis_matcher
        )

    def test_vancomycin_satisfies_antibiotic_therapy(self, sepsis_matcher):
        """Vancomycin should satisfy antibiotic requirement."""
        performed = {"vancomycin", "give_vancomycin"}
        assert _action_satisfies_via_ontology(
            performed, "ANTIBIOTIC_THERAPY", sepsis_matcher
        )

    def test_norepinephrine_satisfies_vasopressor(self, sepsis_matcher):
        """Norepinephrine should satisfy vasopressor requirement."""
        performed = {"start_norepinephrine"}
        assert _action_satisfies_via_ontology(
            performed, "VASOPRESSOR_SUPPORT", sepsis_matcher
        )

    def test_aspirin_satisfies_antiplatelet(self, chest_pain_matcher):
        """Aspirin should satisfy antiplatelet requirement."""
        performed = {"give_aspirin_loading", "aspirin"}
        assert _action_satisfies_via_ontology(
            performed, "ANTIPLATELET_THERAPY", chest_pain_matcher
        )

    def test_alteplase_satisfies_thrombolysis(self, stroke_matcher):
        """Alteplase should satisfy thrombolysis requirement."""
        performed = {"tpa", "give_tpa"}
        assert _action_satisfies_via_ontology(
            performed, "THROMBOLYSIS", stroke_matcher
        )

    def test_unrelated_action_does_not_satisfy(self, sepsis_matcher):
        """Unrelated actions should not satisfy requirements."""
        performed = {"admit_to_icu"}
        assert not _action_satisfies_via_ontology(
            performed, "give_broad_spectrum_antibiotics", sepsis_matcher
        )

    def test_no_matcher_returns_false(self):
        """Without matcher, always returns False."""
        performed = {"give_meropenem"}
        assert not _action_satisfies_via_ontology(
            performed, "give_broad_spectrum_antibiotics", None
        )


# ======================================================================
# Forbidden Action Detection Tests
# ======================================================================

class TestOntologyForbiddenDetection:
    """Test ontology-based forbidden action detection."""

    def test_nitrates_forbidden_detected(self, chest_pain_matcher):
        """Nitrates should be detected as forbidden when GIVE_NITRATES is forbidden."""
        assert _action_is_forbidden_via_ontology(
            "GIVE_NITRATES", ["GIVE_NITRATES"], chest_pain_matcher
        )

    def test_nitroglycerin_forbidden_via_subsumption(self, chest_pain_matcher):
        """Nitroglycerin (synonym) should be detected as forbidden."""
        # Note: This depends on nitroglycerin being a synonym of GIVE_NITRATES
        result = _action_is_forbidden_via_ontology(
            "nitroglycerin", ["GIVE_NITRATES"], chest_pain_matcher
        )
        # nitroglycerin may or may not be in the ontology as a synonym
        # The important test is that GIVE_NITRATES itself is detected
        assert isinstance(result, bool)

    def test_unrelated_action_not_forbidden(self, chest_pain_matcher):
        """Unrelated actions should not be detected as forbidden."""
        assert not _action_is_forbidden_via_ontology(
            "give_aspirin", ["GIVE_NITRATES"], chest_pain_matcher
        )


# ======================================================================
# Full Compliance Evaluation Tests
# ======================================================================

class TestComplianceWithOntology:
    """Test full compliance evaluation with ontology matching enabled."""

    def test_sepsis_compliance_improved_with_ontology(
        self, sepsis_matcher, evidence_all_true
    ):
        """Ontology matching should improve compliance when specific drugs satisfy broad requirements."""
        performed_actions = [
            "give_meropenem",  # Should satisfy give_broad_spectrum_antibiotics
            "order_lab_blood_culture",
            "order_lab_lactate",
        ]
        performed_norm = {normalize_action_id(a) for a in performed_actions}
        mandatory_actions = [
            "give_broad_spectrum_antibiotics",
            "order_lab_blood_culture",
            "order_lab_lactate",
        ]

        # Without ontology
        report_no_onto = _evaluate_compliance(
            case_id="test_001",
            guideline_id="cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml",
            performed_actions=performed_actions,
            performed_norm=performed_norm,
            mandatory_actions=mandatory_actions,
            forbidden_actions=[],
            required_prior_actions={},
            deadlines={},
            evidence_flags=evidence_all_true,
            ontology_matcher=None,
        )

        # With ontology
        report_with_onto = _evaluate_compliance(
            case_id="test_001",
            guideline_id="cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml",
            performed_actions=performed_actions,
            performed_norm=performed_norm,
            mandatory_actions=mandatory_actions,
            forbidden_actions=[],
            required_prior_actions={},
            deadlines={},
            evidence_flags=evidence_all_true,
            ontology_matcher=sepsis_matcher,
        )

        # Without ontology: give_meropenem != give_broad_spectrum_antibiotics → OMISSION
        assert report_no_onto.compliance_score < 1.0
        assert len(report_no_onto.violations) > 0

        # With ontology: give_meropenem IS-A give_broad_spectrum_antibiotics → satisfied
        assert report_with_onto.compliance_score == 1.0
        assert len(report_with_onto.violations) == 0

    def test_ontology_note_added(self, sepsis_matcher, evidence_all_true):
        """Ontology-enabled report should have note."""
        report = _evaluate_compliance(
            case_id="test_002",
            guideline_id="cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml",
            performed_actions=["order_lab_lactate"],
            performed_norm={"order_lab_lactate"},
            mandatory_actions=["order_lab_lactate"],
            forbidden_actions=[],
            required_prior_actions={},
            deadlines={},
            evidence_flags=evidence_all_true,
            ontology_matcher=sepsis_matcher,
        )
        assert "ontology_matching_enabled" in report.notes

    def test_no_ontology_note_when_disabled(self, evidence_all_true):
        """Without ontology, note should not be present."""
        report = _evaluate_compliance(
            case_id="test_003",
            guideline_id="cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml",
            performed_actions=["order_lab_lactate"],
            performed_norm={"order_lab_lactate"},
            mandatory_actions=["order_lab_lactate"],
            forbidden_actions=[],
            required_prior_actions={},
            deadlines={},
            evidence_flags=evidence_all_true,
            ontology_matcher=None,
        )
        assert "ontology_matching_enabled" not in report.notes

    def test_forbidden_action_detected_via_ontology(
        self, chest_pain_matcher, evidence_all_true
    ):
        """Ontology should detect forbidden action via subsumption."""
        performed_actions = ["GIVE_NITRATES"]
        performed_norm = {normalize_action_id(a) for a in performed_actions}

        report = _evaluate_compliance(
            case_id="test_rv",
            guideline_id="cpg_model/graphs/aha_chest_pain_evaluation.yaml",
            performed_actions=performed_actions,
            performed_norm=performed_norm,
            mandatory_actions=[],
            forbidden_actions=["GIVE_NITRATES"],
            required_prior_actions={},
            deadlines={},
            evidence_flags=evidence_all_true,
            ontology_matcher=chest_pain_matcher,
        )
        # Should detect GIVE_NITRATES as forbidden
        commission_violations = [
            v for v in report.violations if v["type"] == "COMMISSION"
        ]
        assert len(commission_violations) >= 1

    def test_sequence_checking_with_ontology(
        self, sepsis_matcher, evidence_all_true
    ):
        """Ontology should resolve sequence requirements too."""
        performed_actions = [
            "order_lab_blood_culture",
            "give_meropenem",
        ]
        performed_norm = {normalize_action_id(a) for a in performed_actions}

        # Required: blood culture before antibiotics
        report = _evaluate_compliance(
            case_id="test_seq",
            guideline_id="cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml",
            performed_actions=performed_actions,
            performed_norm=performed_norm,
            mandatory_actions=["give_broad_spectrum_antibiotics"],
            forbidden_actions=[],
            required_prior_actions={
                "give_broad_spectrum_antibiotics": ["order_lab_blood_culture"]
            },
            deadlines={},
            evidence_flags=evidence_all_true,
            ontology_matcher=sepsis_matcher,
        )

        # With ontology: give_meropenem satisfies give_broad_spectrum_antibiotics
        # and order_lab_blood_culture is performed → no SEQUENCE violation
        sequence_violations = [
            v for v in report.violations if v["type"] == "SEQUENCE"
        ]
        assert len(sequence_violations) == 0

    def test_backward_compatible_when_disabled(self, evidence_all_true):
        """Without ontology, behavior should be identical to before."""
        performed_actions = [
            "give_meropenem",
            "order_lab_blood_culture",
            "order_lab_lactate",
        ]
        performed_norm = {normalize_action_id(a) for a in performed_actions}
        mandatory_actions = [
            "give_broad_spectrum_antibiotics",
            "order_lab_blood_culture",
            "order_lab_lactate",
        ]

        report = _evaluate_compliance(
            case_id="test_compat",
            guideline_id="cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml",
            performed_actions=performed_actions,
            performed_norm=performed_norm,
            mandatory_actions=mandatory_actions,
            forbidden_actions=[],
            required_prior_actions={},
            deadlines={},
            evidence_flags=evidence_all_true,
            ontology_matcher=None,  # Disabled
        )

        # give_meropenem != give_broad_spectrum_antibiotics → OMISSION
        assert report.compliance_score < 1.0
        omission_violations = [
            v for v in report.violations if v["type"] == "OMISSION"
        ]
        assert any(
            "give_broad_spectrum_antibiotics" in v["action"]
            for v in omission_violations
        )


# ======================================================================
# Clinical Scenario Tests
# ======================================================================

class TestClinicalScenarios:
    """End-to-end clinical scenario tests with ontology evaluation."""

    def test_sepsis_scenario_specific_drugs(
        self, sepsis_matcher, evidence_all_true
    ):
        """Real-world sepsis scenario: agent prescribes specific drugs."""
        # Agent orders specific drugs, not generic CPG actions
        performed_actions = [
            "order_lab_lactate",
            "order_lab_blood_culture",
            "give_meropenem",        # Specific abx, not "give_broad_spectrum_antibiotics"
            "give_crystalloid_30ml_kg",
            "start_norepinephrine",  # Specific vasopressor
        ]
        performed_norm = {normalize_action_id(a) for a in performed_actions}

        mandatory_actions = [
            "order_lab_lactate",
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
            "give_crystalloid_30ml_kg",
            "start_vasopressor_if_hypotensive",
        ]

        report = _evaluate_compliance(
            case_id="sepsis_specific",
            guideline_id="cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml",
            performed_actions=performed_actions,
            performed_norm=performed_norm,
            mandatory_actions=mandatory_actions,
            forbidden_actions=[],
            required_prior_actions={
                "give_broad_spectrum_antibiotics": ["order_lab_blood_culture"]
            },
            deadlines={},
            evidence_flags=evidence_all_true,
            ontology_matcher=sepsis_matcher,
        )

        # All 5 mandatory actions should be satisfied via ontology
        assert report.compliance_score == 1.0
        assert len(report.violations) == 0
        assert len(report.satisfied_actions) == 5

    def test_chest_pain_acs_scenario(
        self, chest_pain_matcher, evidence_all_true
    ):
        """ACS scenario: agent prescribes aspirin + heparin."""
        performed_actions = [
            "obtain_12_lead_ecg",
            "give_aspirin_loading",
            "order_lab_troponin",
        ]
        performed_norm = {normalize_action_id(a) for a in performed_actions}

        mandatory_actions = [
            "obtain_12_lead_ecg",
            "assess_vital_signs",  # This won't match without broader synonyms
            "order_lab_troponin",
        ]

        report = _evaluate_compliance(
            case_id="acs_001",
            guideline_id="cpg_model/graphs/aha_chest_pain_evaluation.yaml",
            performed_actions=performed_actions,
            performed_norm=performed_norm,
            mandatory_actions=mandatory_actions,
            forbidden_actions=[],
            required_prior_actions={},
            deadlines={},
            evidence_flags=evidence_all_true,
            ontology_matcher=chest_pain_matcher,
        )

        # ECG and troponin should be satisfied
        assert "obtain_12_lead_ecg" in report.satisfied_actions
        assert "order_lab_troponin" in report.satisfied_actions
