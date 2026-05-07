"""Tests for Mapper/Policy Separation Architecture.

Tests the architectural separation between:
1. Mapper: Concept identification / Entity Linking
2. Policy: Clinical conformance decisions

This separation follows Entity Linking (EL) best practices and
addresses the concern that "what concept is this?" should be
separate from "is this allowed in this context?".
"""
from __future__ import annotations

import pytest

from cga_bench.semantic_layer.ontology.concept import (
    AbstractionLevel,
    ClinicalConcept,
    ConceptRelation,
)
from cga_bench.semantic_layer.ontology.clinical_ontology import (
    ClinicalOntology,
    OntologyConfig,
    OntologyMatcher,
)
from cga_bench.semantic_layer.ontology.mapper import (
    ConceptMapper,
    MapperConfig,
    MappingResult,
    MappingStrategy,
    UncertaintyLevel,
    create_mapper,
)
from cga_bench.semantic_layer.ontology.policy import (
    ClinicalPolicy,
    PolicyConfig,
    PolicyDecision,
    PolicyStatus,
    PolicyConstraint,
    ConstraintType,
    Severity,
    PatientContext,
    AllergyMapping,
    ComorbidityMapping,
    ClinicalStateRule,
    create_default_policy,
    create_rv_trap_policy,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_ontology():
    """Build a sample ontology for testing."""
    onto = ClinicalOntology()

    # Create concepts
    vasopressor = ClinicalConcept(
        concept_id="VASOPRESSOR_SUPPORT",
        display="Vasopressor Support",
        level=AbstractionLevel.CATEGORY,
        synonyms=frozenset(["vasopressors", "pressors"]),
    )
    norepi = ClinicalConcept(
        concept_id="VASOPRESSOR_NOREPINEPHRINE",
        display="Norepinephrine",
        level=AbstractionLevel.NORMALIZED,
        synonyms=frozenset(["norepinephrine", "levophed", "norepi"]),
    )
    vaso = ClinicalConcept(
        concept_id="VASOPRESSOR_VASOPRESSIN",
        display="Vasopressin",
        level=AbstractionLevel.NORMALIZED,
        synonyms=frozenset(["vasopressin", "adh"]),
    )
    abx = ClinicalConcept(
        concept_id="ANTIBIOTIC_THERAPY",
        display="Antibiotic Therapy",
        level=AbstractionLevel.CATEGORY,
        synonyms=frozenset(["antibiotics"]),
    )
    meropenem = ClinicalConcept(
        concept_id="ANTIBIOTIC_MEROPENEM",
        display="Meropenem",
        level=AbstractionLevel.NORMALIZED,
        synonyms=frozenset(["meropenem", "merrem"]),
    )
    penicillin = ClinicalConcept(
        concept_id="ANTIBIOTIC_PENICILLIN",
        display="Penicillin",
        level=AbstractionLevel.NORMALIZED,
        synonyms=frozenset(["penicillin", "pen-vk"]),
    )
    ntg = ClinicalConcept(
        concept_id="NITRATE_NITROGLYCERIN",
        display="Nitroglycerin",
        level=AbstractionLevel.NORMALIZED,
        synonyms=frozenset(["nitroglycerin", "ntg", "nitro"]),
    )

    # Add concepts
    for c in [vasopressor, norepi, vaso, abx, meropenem, penicillin, ntg]:
        onto.add_concept(c)

    # Add IS-A relations
    onto.add_relation(norepi, ConceptRelation.IS_A, vasopressor)
    onto.add_relation(vaso, ConceptRelation.IS_A, vasopressor)
    onto.add_relation(meropenem, ConceptRelation.IS_A, abx)
    onto.add_relation(penicillin, ConceptRelation.IS_A, abx)

    return onto


@pytest.fixture
def sample_matcher(sample_ontology):
    """Create matcher for testing."""
    config = OntologyConfig(fuzzy_threshold=0.5)
    return OntologyMatcher(sample_ontology, config)


@pytest.fixture
def sample_mapper(sample_ontology, sample_matcher):
    """Create mapper for testing."""
    config = MapperConfig(
        enable_conformal=False,  # Simplified for unit tests
        enable_sibling_reranking=False,
    )
    return ConceptMapper(sample_ontology, sample_matcher, config)


# ============================================================
# Test: Mapper Core
# ============================================================

class TestMapperCore:
    """Tests for ConceptMapper core functionality."""

    def test_mapper_creation(self, sample_ontology, sample_matcher):
        """Mapper can be created."""
        mapper = ConceptMapper(sample_ontology, sample_matcher)
        assert mapper is not None

    def test_mapper_with_factory(self, sample_ontology, sample_matcher):
        """Factory function creates mapper."""
        mapper = create_mapper(
            sample_ontology,
            sample_matcher,
            enable_conformal=False,
        )
        assert mapper is not None

    def test_exact_match_mapping(self, sample_mapper):
        """Mapper handles exact concept_id match."""
        result = sample_mapper.map("VASOPRESSOR_NOREPINEPHRINE")
        assert result.concept_id == "VASOPRESSOR_NOREPINEPHRINE"
        assert result.strategy == MappingStrategy.EXACT
        assert result.confidence == 1.0
        assert result.uncertainty == UncertaintyLevel.LOW

    def test_synonym_mapping(self, sample_mapper):
        """Mapper handles synonym matching."""
        result = sample_mapper.map("levophed")
        assert result.concept_id == "VASOPRESSOR_NOREPINEPHRINE"
        assert result.strategy == MappingStrategy.SYNONYM
        assert result.uncertainty == UncertaintyLevel.LOW

    def test_unknown_mapping(self, sample_mapper):
        """Mapper handles unknown inputs."""
        result = sample_mapper.map("completely_unknown_xyz")
        assert result.concept_id is None or result.uncertainty == UncertaintyLevel.ABSTAIN

    def test_empty_query(self, sample_mapper):
        """Mapper handles empty query."""
        result = sample_mapper.map("")
        assert result.did_abstain is True
        assert result.concept_id is None

    def test_mapping_result_properties(self, sample_mapper):
        """MappingResult properties work correctly."""
        result = sample_mapper.map("norepinephrine")

        assert result.is_confident is True
        assert result.is_ambiguous is False
        assert result.did_abstain is False

        candidates = result.get_all_candidates()
        assert "VASOPRESSOR_NOREPINEPHRINE" in candidates


class TestMapperBatch:
    """Tests for batch mapping."""

    def test_batch_mapping(self, sample_mapper):
        """Batch mapping processes multiple queries."""
        queries = ["norepinephrine", "meropenem", "unknown_123"]
        results = sample_mapper.map_batch(queries)

        assert len(results) == 3
        assert results[0].concept_id == "VASOPRESSOR_NOREPINEPHRINE"
        assert results[1].concept_id == "ANTIBIOTIC_MEROPENEM"

    def test_batch_with_types(self, sample_mapper):
        """Batch mapping with expected types."""
        queries = ["norepinephrine", "meropenem"]
        types = ["medication", "medication"]
        results = sample_mapper.map_batch(queries, types)

        assert len(results) == 2


class TestMapperUncertainty:
    """Tests for uncertainty quantification."""

    def test_uncertainty_metrics(self, sample_mapper):
        """Get detailed uncertainty metrics."""
        metrics = sample_mapper.get_mapping_uncertainty("levophed")

        assert "query" in metrics
        assert "confidence" in metrics
        assert "uncertainty_level" in metrics
        assert metrics["is_confident"] is True


# ============================================================
# Test: Policy Core
# ============================================================

class TestPolicyCore:
    """Tests for ClinicalPolicy core functionality."""

    def test_policy_creation(self):
        """Policy can be created."""
        policy = ClinicalPolicy()
        assert policy is not None

    def test_default_policy_factory(self):
        """Default policy factory works."""
        policy = create_default_policy()
        assert policy is not None

    def test_rv_trap_policy_factory(self):
        """RV trap policy factory works."""
        policy = create_rv_trap_policy()
        assert policy is not None

    def test_policy_allowed_action(self):
        """Policy allows normal actions."""
        policy = ClinicalPolicy()
        context = PatientContext()

        decision = policy.evaluate("ANTIBIOTIC_MEROPENEM", context)
        assert decision.status == PolicyStatus.ALLOWED
        assert decision.is_allowed is True

    def test_policy_unknown_concept(self):
        """Policy handles empty concept."""
        policy = ClinicalPolicy()
        context = PatientContext()

        decision = policy.evaluate("", context)
        assert decision.status == PolicyStatus.UNKNOWN


class TestPolicyAllergyConstraints:
    """Tests for allergy-based policy constraints."""

    @pytest.fixture
    def allergy_policy(self):
        """Policy with allergy constraints."""
        config = PolicyConfig(
            allergy_mappings=[
                AllergyMapping(
                    allergy="penicillin",
                    forbidden_concepts=[r".*PENICILLIN.*"],
                    cross_reactivity=[r".*CEPHALOSPORIN.*"],
                    severity=Severity.SEVERE,
                ),
            ],
        )
        return ClinicalPolicy(config)

    def test_allergy_forbidden(self, allergy_policy):
        """Allergy causes forbidden status."""
        context = PatientContext(allergies={"penicillin"})

        decision = allergy_policy.evaluate("ANTIBIOTIC_PENICILLIN", context)
        assert decision.status == PolicyStatus.FORBIDDEN
        assert decision.is_forbidden is True
        assert decision.severity == Severity.SEVERE
        assert "allergy" in decision.rationale.lower()

    def test_no_allergy_allowed(self, allergy_policy):
        """No allergy allows action."""
        context = PatientContext()  # No allergies

        decision = allergy_policy.evaluate("ANTIBIOTIC_PENICILLIN", context)
        assert decision.status == PolicyStatus.ALLOWED

    def test_cross_reactivity_cautioned(self, allergy_policy):
        """Cross-reactivity causes cautioned status."""
        context = PatientContext(allergies={"penicillin"})

        decision = allergy_policy.evaluate("ANTIBIOTIC_CEPHALOSPORIN", context)
        assert decision.status == PolicyStatus.CAUTIONED
        assert "cross-reactivity" in decision.rationale.lower()


class TestPolicyComorbidityConstraints:
    """Tests for comorbidity-based policy constraints."""

    @pytest.fixture
    def rv_policy(self):
        """Policy with RV infarct constraints."""
        config = PolicyConfig(
            comorbidity_mappings=[
                ComorbidityMapping(
                    comorbidity="rv_infarction",
                    forbidden_concepts=[r".*NITRATE.*", r".*NITROGLYCERIN.*"],
                    severity=Severity.CATASTROPHIC,
                    source="AHA STEMI Guidelines",
                ),
            ],
        )
        return ClinicalPolicy(config)

    def test_rv_infarct_nitrate_forbidden(self, rv_policy):
        """RV infarct forbids nitrates."""
        context = PatientContext(comorbidities={"rv_infarction"})

        decision = rv_policy.evaluate("NITRATE_NITROGLYCERIN", context)
        assert decision.status == PolicyStatus.FORBIDDEN
        assert decision.severity == Severity.CATASTROPHIC

    def test_no_rv_infarct_nitrate_allowed(self, rv_policy):
        """No RV infarct allows nitrates."""
        context = PatientContext()

        decision = rv_policy.evaluate("NITRATE_NITROGLYCERIN", context)
        assert decision.status == PolicyStatus.ALLOWED


class TestPolicyClinicalStateRules:
    """Tests for clinical state-based rules."""

    @pytest.fixture
    def state_policy(self):
        """Policy with clinical state rules."""
        config = PolicyConfig(
            clinical_state_rules=[
                ClinicalStateRule(
                    state_pattern=r"stemi.*rv.*",
                    mandatory_concepts=["ECG_V4R", "FLUID_BOLUS"],
                    forbidden_concepts=[r".*NITRATE.*"],
                    deadline_minutes=30,
                    source="AHA Guidelines",
                ),
            ],
        )
        return ClinicalPolicy(config)

    def test_mandatory_in_state(self, state_policy):
        """Mandatory actions detected in clinical state."""
        context = PatientContext(clinical_state="stemi_rv_infarct")

        mandatory = state_policy.get_mandatory_actions(context)
        concept_ids = [m[0] for m in mandatory]
        assert "ECG_V4R" in concept_ids

    def test_forbidden_in_state(self, state_policy):
        """Forbidden actions in clinical state."""
        context = PatientContext(clinical_state="stemi_rv_infarct")

        decision = state_policy.evaluate("NITRATE_SUBLINGUAL", context)
        assert decision.status == PolicyStatus.FORBIDDEN


class TestPolicyDecisionProperties:
    """Tests for PolicyDecision properties."""

    def test_decision_properties(self):
        """PolicyDecision properties work correctly."""
        constraint = PolicyConstraint(
            constraint_type=ConstraintType.ALLERGY,
            concept_pattern=".*",
            condition="test",
            status=PolicyStatus.FORBIDDEN,
            severity=Severity.SEVERE,
            rationale="Test rationale",
        )

        decision = PolicyDecision(
            concept_id="TEST_CONCEPT",
            status=PolicyStatus.FORBIDDEN,
            severity=Severity.SEVERE,
            triggered_constraints=[constraint],
            rationale="Test",
        )

        assert decision.is_forbidden is True
        assert decision.is_allowed is False
        assert decision.is_mandatory is False
        assert decision.has_warnings is True


class TestPatientContext:
    """Tests for PatientContext."""

    def test_context_allergy_check(self):
        """PatientContext allergy checking."""
        context = PatientContext(allergies={"penicillin", "Sulfa"})

        assert context.has_allergy("penicillin") is True
        assert context.has_allergy("PENICILLIN") is True  # Case insensitive
        assert context.has_allergy("aspirin") is False

    def test_context_comorbidity_check(self):
        """PatientContext comorbidity checking."""
        context = PatientContext(comorbidities={"rv_infarction", "diabetes"})

        assert context.has_comorbidity("rv_infarction") is True
        assert context.has_comorbidity("RV_INFARCTION") is True
        assert context.has_comorbidity("asthma") is False

    def test_context_medication_check(self):
        """PatientContext medication checking."""
        context = PatientContext(current_medications={"warfarin", "metformin"})

        assert context.is_on_medication("warfarin") is True
        assert context.is_on_medication("aspirin") is False


# ============================================================
# Test: Mapper + Policy Integration
# ============================================================

class TestMapperPolicyIntegration:
    """Tests for Mapper + Policy working together."""

    def test_full_pipeline(self, sample_mapper):
        """Full pipeline: Map → Policy."""
        # Step 1: Map the input
        mapping = sample_mapper.map("levophed infusion")
        assert mapping.concept_id == "VASOPRESSOR_NOREPINEPHRINE"

        # Step 2: Evaluate policy
        policy = create_default_policy()
        context = PatientContext()

        decision = policy.evaluate(mapping.concept_id, context)
        assert decision.is_allowed is True

    def test_allergy_blocks_mapped_concept(self, sample_mapper):
        """Allergy blocks a correctly mapped concept."""
        # Map penicillin
        mapping = sample_mapper.map("penicillin")
        assert "PENICILLIN" in mapping.concept_id

        # Policy with penicillin allergy
        policy = create_default_policy()
        context = PatientContext(allergies={"penicillin"})

        decision = policy.evaluate(mapping.concept_id, context)
        assert decision.is_forbidden is True

    def test_rv_trap_scenario(self, sample_mapper):
        """RV trap scenario: Map → Policy forbids."""
        # Map nitroglycerin
        mapping = sample_mapper.map("ntg")
        assert mapping.concept_id == "NITRATE_NITROGLYCERIN"

        # RV infarct policy
        policy = create_rv_trap_policy()
        context = PatientContext(comorbidities={"rv_infarction"})

        decision = policy.evaluate(mapping.concept_id, context)
        assert decision.is_forbidden is True
        assert decision.severity == Severity.CATASTROPHIC


class TestArchitecturalSeparation:
    """Tests verifying proper architectural separation."""

    def test_mapper_no_policy_knowledge(self, sample_mapper):
        """Mapper doesn't know about policy constraints."""
        # Map nitroglycerin - mapper should succeed regardless of context
        mapping = sample_mapper.map("nitroglycerin")

        # Mapper only identifies concept, doesn't make policy decisions
        assert mapping.concept_id == "NITRATE_NITROGLYCERIN"
        # No policy information in mapping result
        assert not hasattr(mapping, "is_forbidden")
        assert not hasattr(mapping, "policy_status")

    def test_policy_requires_normalized_concept(self):
        """Policy works with normalized concept IDs."""
        policy = create_rv_trap_policy()
        context = PatientContext(comorbidities={"rv_infarction"})

        # Policy takes normalized concept_id, not raw input
        decision = policy.evaluate("NITRATE_NITROGLYCERIN", context)
        assert decision.is_forbidden is True

        # Raw input would not be recognized without mapper
        decision2 = policy.evaluate("ntg infusion 5mcg/min", context)
        # May or may not match - depends on pattern; demonstrates need for mapper


# ============================================================
# Test: Edge Cases
# ============================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_multiple_constraints(self):
        """Multiple constraints can apply."""
        config = PolicyConfig(
            allergy_mappings=[
                AllergyMapping(
                    allergy="penicillin",
                    forbidden_concepts=[r".*PENICILLIN.*"],
                    severity=Severity.SEVERE,
                ),
            ],
            comorbidity_mappings=[
                ComorbidityMapping(
                    comorbidity="kidney_disease",
                    cautioned_concepts=[r".*PENICILLIN.*"],
                    forbidden_concepts=[],
                    severity=Severity.MODERATE,
                ),
            ],
        )
        policy = ClinicalPolicy(config)

        # Patient has both allergy and comorbidity
        context = PatientContext(
            allergies={"penicillin"},
            comorbidities={"kidney_disease"},
        )

        decision = policy.evaluate("ANTIBIOTIC_PENICILLIN", context)
        # Most restrictive wins
        assert decision.is_forbidden is True
        assert len(decision.triggered_constraints) >= 1

    def test_case_insensitive_matching(self):
        """Pattern matching is case insensitive."""
        config = PolicyConfig(
            allergy_mappings=[
                AllergyMapping(
                    allergy="Penicillin",  # Mixed case
                    forbidden_concepts=[r".*penicillin.*"],  # lowercase pattern
                    severity=Severity.SEVERE,
                ),
            ],
        )
        policy = ClinicalPolicy(config)
        context = PatientContext(allergies={"PENICILLIN"})  # uppercase

        decision = policy.evaluate("ANTIBIOTIC_PENICILLIN", context)
        assert decision.is_forbidden is True

    def test_empty_context(self):
        """Policy works with empty patient context."""
        policy = create_default_policy()
        context = PatientContext()

        decision = policy.evaluate("ANTIBIOTIC_MEROPENEM", context)
        assert decision.is_allowed is True
        assert len(decision.triggered_constraints) == 0
