"""Integration tests for Ontology + LTL Verifier + Activity Extraction.

Tests:
1. LTL verification with subsumption-based atom matching
2. Activity extraction with ontology normalization
3. Pipeline integration with ontology-aware verification
4. Clinical scenarios with multi-level matching
"""
import pytest

from cga_bench.semantic_layer.conformance.activity import (
    ActivityEvent,
    ActivityExtractionConfig,
    extract_activity_events,
)
from cga_bench.semantic_layer.export.temporal_logic_verifier import (
    LTLVerifier,
    TLFormula,
    TemporalOp,
    PropertySpec,
    response_property,
    precedence_property,
    existence_property,
    absence_property,
    response_within_property,
)
from cga_bench.semantic_layer.ontology.clinical_ontology import (
    OntologyConfig,
    OntologyMatcher,
)
from cga_bench.semantic_layer.ontology.domain_hierarchies import (
    build_sepsis_ontology,
    build_chest_pain_ontology,
    get_ontology_matcher,
    get_unified_matcher,
)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def sepsis_matcher():
    return get_ontology_matcher("sepsis")


@pytest.fixture
def chest_pain_matcher():
    return get_ontology_matcher("chest_pain")


@pytest.fixture
def unified_matcher():
    return get_unified_matcher()


def _make_trace(actions_and_times):
    """Create a list of ActivityEvents from (name, time_min) pairs."""
    return [
        ActivityEvent(name=name, timestamp_min=t, raw_event={})
        for name, t in actions_and_times
    ]


# ======================================================================
# Test LTL + Ontology Subsumption
# ======================================================================

class TestLTLWithOntology:
    """Test LTL verification using ontology-based atom matching."""

    def test_strict_verifier_no_subsumption(self):
        """Without ontology, specific drugs don't satisfy generic requirements."""
        verifier = LTLVerifier()  # No ontology
        prop = existence_property("GIVE_BROAD_SPECTRUM_ANTIBIOTICS")
        trace = _make_trace([
            ("GIVE_PIPERACILLIN_TAZOBACTAM", 5.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert not result.satisfied  # Strict: pip-tazo != broad-spectrum

    def test_ontology_verifier_subsumption(self, sepsis_matcher):
        """With ontology, pip-tazo satisfies broad-spectrum requirement."""
        verifier = LTLVerifier(ontology_matcher=sepsis_matcher)
        prop = existence_property("GIVE_BROAD_SPECTRUM_ANTIBIOTICS")
        trace = _make_trace([
            ("GIVE_PIPERACILLIN_TAZOBACTAM", 5.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert result.satisfied  # Subsumption: pip-tazo IS-A broad-spectrum

    def test_ontology_response_subsumption(self, sepsis_matcher):
        """G(culture → F antibiotics): meropenem satisfies antibiotics."""
        verifier = LTLVerifier(ontology_matcher=sepsis_matcher)
        prop = response_property("ORDER_BLOOD_CULTURE", "GIVE_BROAD_SPECTRUM_ANTIBIOTICS")
        trace = _make_trace([
            ("ORDER_BLOOD_CULTURE", 0.0),
            ("GIVE_MEROPENEM", 10.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert result.satisfied

    def test_ontology_vasopressor_subsumption(self, sepsis_matcher):
        """Norepinephrine satisfies VASOPRESSOR_SUPPORT requirement."""
        verifier = LTLVerifier(ontology_matcher=sepsis_matcher)
        prop = existence_property("VASOPRESSOR_SUPPORT")
        trace = _make_trace([
            ("START_VASOPRESSOR_NOREPINEPHRINE", 30.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert result.satisfied

    def test_ontology_synonym_matching(self, sepsis_matcher):
        """Synonym 'levophed' matches START_VASOPRESSOR_NOREPINEPHRINE concept."""
        verifier = LTLVerifier(ontology_matcher=sepsis_matcher)
        # The ontology matcher resolves levophed → START_VASOPRESSOR_NOREPINEPHRINE
        # But the trace has the raw string - verifier checks via satisfies()
        prop = existence_property("START_VASOPRESSOR_NOREPINEPHRINE")
        trace = _make_trace([
            ("levophed", 30.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert result.satisfied

    def test_ontology_precedence_with_subsumption(self, sepsis_matcher):
        """Precedence: fluid before vasopressor (both via subsumption)."""
        verifier = LTLVerifier(ontology_matcher=sepsis_matcher)
        prop = precedence_property("FLUID_RESUSCITATION", "VASOPRESSOR_SUPPORT")
        trace = _make_trace([
            ("GIVE_CRYSTALLOID", 10.0),
            ("START_VASOPRESSOR_NOREPINEPHRINE", 30.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert result.satisfied

    def test_ontology_precedence_violated(self, sepsis_matcher):
        """Precedence violated: vasopressor before fluid."""
        verifier = LTLVerifier(ontology_matcher=sepsis_matcher)
        prop = precedence_property("FLUID_RESUSCITATION", "VASOPRESSOR_SUPPORT")
        trace = _make_trace([
            ("START_VASOPRESSOR_NOREPINEPHRINE", 5.0),
            ("GIVE_CRYSTALLOID", 30.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert not result.satisfied

    def test_ontology_absence_with_subsumption(self, sepsis_matcher):
        """Absence: no vasopressor should detect norepinephrine."""
        verifier = LTLVerifier(ontology_matcher=sepsis_matcher)
        prop = absence_property("VASOPRESSOR_SUPPORT")
        trace = _make_trace([
            ("ORDER_BLOOD_CULTURE", 0.0),
            ("START_VASOPRESSOR_NOREPINEPHRINE", 20.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert not result.satisfied  # norepi violates "no vasopressor"

    def test_ontology_sibling_no_confusion(self, sepsis_matcher):
        """Vasopressin doesn't satisfy norepinephrine requirement."""
        verifier = LTLVerifier(ontology_matcher=sepsis_matcher)
        prop = existence_property("START_VASOPRESSOR_NOREPINEPHRINE")
        trace = _make_trace([
            ("START_VASOPRESSOR_VASOPRESSIN", 30.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert not result.satisfied  # Siblings are not IS-A

    def test_ontology_mtl_with_subsumption(self, sepsis_matcher):
        """MTL response_within with subsumption matching."""
        verifier = LTLVerifier(ontology_matcher=sepsis_matcher)
        prop = response_within_property(
            "ORDER_BLOOD_CULTURE",
            "ANTIBIOTIC_THERAPY",  # Category level
            max_minutes=60,
        )
        trace = _make_trace([
            ("ORDER_BLOOD_CULTURE", 0.0),
            ("GIVE_PIPERACILLIN_TAZOBACTAM", 25.0),  # pip-tazo IS-A antibiotic
        ])
        result = verifier.verify(trace, prop.formula)
        assert result.satisfied

    def test_ontology_mtl_subsumption_late_violation(self, sepsis_matcher):
        """MTL response_within violated: antibiotic too late."""
        verifier = LTLVerifier(ontology_matcher=sepsis_matcher)
        prop = response_within_property(
            "ORDER_BLOOD_CULTURE",
            "ANTIBIOTIC_THERAPY",
            max_minutes=60,
        )
        trace = _make_trace([
            ("ORDER_BLOOD_CULTURE", 0.0),
            ("GIVE_MEROPENEM", 90.0),  # Beyond 60 min window
        ])
        result = verifier.verify(trace, prop.formula)
        assert not result.satisfied


# ======================================================================
# Test Chest Pain Ontology + LTL
# ======================================================================

class TestChestPainLTL:
    """Test chest pain domain with ontology-based LTL."""

    def test_nitrate_forbidden_via_category(self, chest_pain_matcher):
        """Absence of NITRATE_THERAPY catches nitroglycerin."""
        verifier = LTLVerifier(ontology_matcher=chest_pain_matcher)
        prop = absence_property("NITRATE_THERAPY")
        trace = _make_trace([
            ("ORDER_ECG", 0.0),
            ("GIVE_NITRATES", 15.0),  # Nitrates IS-A NITRATE_THERAPY
        ])
        result = verifier.verify(trace, prop.formula)
        assert not result.satisfied

    def test_reperfusion_subsumption(self, chest_pain_matcher):
        """Cath lab satisfies REPERFUSION_PROCEDURES requirement."""
        verifier = LTLVerifier(ontology_matcher=chest_pain_matcher)
        prop = existence_property("REPERFUSION_PROCEDURES")
        trace = _make_trace([
            ("ACTIVATE_CATH_LAB", 45.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert result.satisfied

    def test_ecg_before_reperfusion_ontology(self, chest_pain_matcher):
        """ECG before reperfusion using ontology subsumption."""
        verifier = LTLVerifier(ontology_matcher=chest_pain_matcher)
        prop = precedence_property("ECG_ASSESSMENT", "REPERFUSION_PROCEDURES")
        trace = _make_trace([
            ("ORDER_ECG", 2.0),
            ("ACTIVATE_CATH_LAB", 45.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert result.satisfied

    def test_anticoagulant_hierarchy(self, chest_pain_matcher):
        """Enoxaparin satisfies ANTICOAGULANT_AGENTS requirement."""
        verifier = LTLVerifier(ontology_matcher=chest_pain_matcher)
        prop = existence_property("ANTICOAGULANT_AGENTS")
        trace = _make_trace([
            ("GIVE_ENOXAPARIN", 20.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert result.satisfied


# ======================================================================
# Test Activity Extraction with Ontology
# ======================================================================

class TestActivityExtractionOntology:
    """Test activity extraction with ontology normalization."""

    def test_ontology_disabled_no_normalization(self):
        """Without ontology, activities pass through unchanged."""
        config = ActivityExtractionConfig(enable_ontology=False)
        events = [
            {"activity": "levophed", "timestamp_ms": 1000},
        ]
        result, _ = extract_activity_events(events, config=config)
        assert len(result) == 1
        assert result[0].name == "levophed"  # Unchanged

    def test_ontology_enabled_synonym_normalization(self):
        """With ontology, 'levophed' normalizes to concept ID."""
        config = ActivityExtractionConfig(
            enable_ontology=True,
            ontology_domain="sepsis",
        )
        events = [
            {"activity": "levophed", "timestamp_ms": 1000},
        ]
        result, _ = extract_activity_events(events, config=config)
        assert len(result) == 1
        assert result[0].name == "START_VASOPRESSOR_NOREPINEPHRINE"
        assert "ontology" in result[0].match_source

    def test_ontology_normalizes_multiple_synonyms(self):
        """Multiple synonyms all normalize to canonical concepts."""
        config = ActivityExtractionConfig(
            enable_ontology=True,
            ontology_domain="sepsis",
        )
        events = [
            {"activity": "lactic_acid", "timestamp_ms": 1000},
            {"activity": "broad_spectrum_antibiotics", "timestamp_ms": 2000},
            {"activity": "fluid_bolus", "timestamp_ms": 3000},
        ]
        result, _ = extract_activity_events(events, config=config)
        assert result[0].name == "ORDER_LACTATE"
        assert result[1].name == "GIVE_BROAD_SPECTRUM_ANTIBIOTICS"
        assert result[2].name == "GIVE_CRYSTALLOID"

    def test_ontology_unified_domain(self):
        """Unified ontology handles cross-domain concepts."""
        config = ActivityExtractionConfig(
            enable_ontology=True,
            ontology_domain=None,  # Unified
        )
        events = [
            {"activity": "nihss", "timestamp_ms": 1000},  # stroke
            {"activity": "entresto", "timestamp_ms": 2000},  # HF
            {"activity": "insulin_infusion", "timestamp_ms": 3000},  # DKA
        ]
        result, _ = extract_activity_events(events, config=config)
        assert result[0].name == "ASSESS_NIHSS"
        assert result[1].name == "GIVE_SACUBITRIL_VALSARTAN"
        assert result[2].name == "START_INSULIN_DRIP"

    def test_ontology_unknown_activity_passthrough(self):
        """Unknown activities pass through when ontology can't match."""
        config = ActivityExtractionConfig(
            enable_ontology=True,
            ontology_domain="sepsis",
        )
        events = [
            {"activity": "COMPLETELY_UNKNOWN_ACTION", "timestamp_ms": 1000},
        ]
        result, _ = extract_activity_events(events, config=config)
        assert len(result) == 1
        assert result[0].name == "COMPLETELY_UNKNOWN_ACTION"

    def test_ontology_preserves_timestamps(self):
        """Ontology normalization preserves correct timestamps."""
        config = ActivityExtractionConfig(
            enable_ontology=True,
            ontology_domain="sepsis",
        )
        events = [
            {"activity": "levophed", "timestamp_ms": 60000},
            {"activity": "lactic_acid", "timestamp_ms": 120000},
        ]
        result, _ = extract_activity_events(events, config=config)
        assert result[0].timestamp_min == 0.0  # base offset
        assert result[1].timestamp_min == 1.0  # 60s later = 1 minute


# ======================================================================
# Test Clinical Scenarios (End-to-End)
# ======================================================================

class TestClinicalScenarios:
    """End-to-end clinical scenarios combining ontology + LTL."""

    def test_sepsis_bundle_with_specific_drugs(self, sepsis_matcher):
        """Full sepsis bundle compliance with specific drug names."""
        verifier = LTLVerifier(ontology_matcher=sepsis_matcher)

        # Properties at category level
        props = [
            existence_property("MICROBIOLOGY_WORKUP"),
            existence_property("ANTIBIOTIC_THERAPY"),
            existence_property("FLUID_RESUSCITATION"),
            existence_property("LACTATE_MONITORING"),
            precedence_property("MICROBIOLOGY_WORKUP", "ANTIBIOTIC_THERAPY"),
        ]

        # Trace with specific actions
        trace = _make_trace([
            ("ORDER_LACTATE", 0.0),
            ("ORDER_BLOOD_CULTURE", 5.0),
            ("GIVE_PIPERACILLIN_TAZOBACTAM", 15.0),
            ("GIVE_CRYSTALLOID", 20.0),
        ])

        report = verifier.verify_properties(trace, [PropertySpec(f"prop_{i}", f, "") for i, f in enumerate(p.formula for p in props)] if False else props)
        # Actually just verify each:
        for prop in props:
            result = verifier.verify(trace, prop.formula)
            assert result.satisfied, f"Property {prop.name} violated"

    def test_stemi_pathway_abstract_compliance(self, chest_pain_matcher):
        """STEMI pathway compliance using category-level properties."""
        verifier = LTLVerifier(ontology_matcher=chest_pain_matcher)

        trace = _make_trace([
            ("ASSESS_VITALS_ACS", 0.0),
            ("ORDER_ECG", 2.0),
            ("GIVE_ASPIRIN", 5.0),
            ("DIAGNOSE_STEMI", 10.0),
            ("GIVE_HEPARIN", 20.0),
            ("ACTIVATE_CATH_LAB", 30.0),
        ])

        # ECG assessment exists
        result = verifier.verify(trace, existence_property("ECG_ASSESSMENT").formula)
        assert result.satisfied

        # Antiplatelet given
        result = verifier.verify(trace, existence_property("ANTIPLATELET_AGENTS").formula)
        assert result.satisfied

        # Reperfusion given
        result = verifier.verify(trace, existence_property("REPERFUSION_PROCEDURES").formula)
        assert result.satisfied

    def test_mixed_abstraction_levels(self, sepsis_matcher):
        """Properties at different abstraction levels work together."""
        verifier = LTLVerifier(ontology_matcher=sepsis_matcher)

        trace = _make_trace([
            ("ORDER_BLOOD_CULTURE", 0.0),
            ("GIVE_MEROPENEM", 20.0),
            ("GIVE_CRYSTALLOID", 25.0),
            ("START_VASOPRESSOR_NOREPINEPHRINE", 40.0),
        ])

        # L1: specific action exists
        r1 = verifier.verify(trace, existence_property("ORDER_BLOOD_CULTURE").formula)
        assert r1.satisfied

        # L2: category-level existence
        r2 = verifier.verify(trace, existence_property("ANTIBIOTIC_THERAPY").formula)
        assert r2.satisfied

        # L3: goal-level existence
        r3 = verifier.verify(trace, existence_property("HEMODYNAMIC_RESUSCITATION").formula)
        assert r3.satisfied

    def test_backward_compatible_no_ontology(self):
        """Verify that LTLVerifier without ontology works as before."""
        verifier = LTLVerifier()  # No ontology
        prop = response_property("ORDER_BLOOD_CULTURE", "GIVE_ANTIBIOTICS")
        trace = _make_trace([
            ("ORDER_BLOOD_CULTURE", 0.0),
            ("GIVE_ANTIBIOTICS", 15.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert result.satisfied  # Exact string match works

    def test_backward_compatible_strict_equality(self):
        """Without ontology, no subsumption occurs."""
        verifier = LTLVerifier()
        prop = existence_property("ANTIBIOTIC_THERAPY")
        trace = _make_trace([
            ("GIVE_MEROPENEM", 20.0),
        ])
        result = verifier.verify(trace, prop.formula)
        assert not result.satisfied  # No subsumption without ontology
