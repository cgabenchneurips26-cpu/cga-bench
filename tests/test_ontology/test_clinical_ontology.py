"""Tests for Clinical Ontology Layer.

Tests cover:
1. Core ontology structure (concepts, IS-A hierarchy)
2. Subsumption queries (ancestors, descendants, distance)
3. Multi-level abstraction
4. OntologyMatcher (exact, synonym, subsumption, fuzzy)
5. Conformance helpers (satisfies, is_forbidden)
6. Domain hierarchies (sepsis, chest_pain, AKI, stroke, HF, DKA)
7. Unified ontology
8. Edge cases
"""
import pytest

from cga_bench.semantic_layer.ontology.concept import (
    AbstractionLevel,
    ClinicalConcept,
    ConceptRelation,
    MatchResult,
)
from cga_bench.semantic_layer.ontology.clinical_ontology import (
    ClinicalOntology,
    OntologyConfig,
    OntologyMatcher,
    MatchStrategy,
)
from cga_bench.semantic_layer.ontology.domain_hierarchies import (
    build_sepsis_ontology,
    build_chest_pain_ontology,
    build_aki_ontology,
    build_stroke_ontology,
    build_heart_failure_ontology,
    build_dka_ontology,
    build_domain_ontology,
    build_unified_ontology,
    get_ontology_matcher,
    get_unified_matcher,
)


# ======================================================================
# Fixtures
# ======================================================================

@pytest.fixture
def simple_ontology():
    """Simple 3-level ontology for testing."""
    onto = ClinicalOntology()

    # L3: Goal
    goal = ClinicalConcept(
        concept_id="HEMODYNAMIC_SUPPORT",
        display="Hemodynamic Support",
        level=AbstractionLevel.GOAL,
        domain="test",
    )
    # L2: Category
    vasopressor = ClinicalConcept(
        concept_id="VASOPRESSOR",
        display="Vasopressor",
        level=AbstractionLevel.CATEGORY,
        domain="test",
        synonyms=frozenset(["pressor", "vasopressor_support"]),
    )
    fluid = ClinicalConcept(
        concept_id="FLUID_THERAPY",
        display="Fluid Therapy",
        level=AbstractionLevel.CATEGORY,
        domain="test",
        synonyms=frozenset(["fluids", "iv_fluids"]),
    )
    # L1: Normalized
    norepi = ClinicalConcept(
        concept_id="NOREPINEPHRINE",
        display="Norepinephrine",
        level=AbstractionLevel.NORMALIZED,
        domain="test",
        synonyms=frozenset(["levophed", "norepi", "start_norepinephrine"]),
        system="RxNorm",
        code="7512",
    )
    vasopressin = ClinicalConcept(
        concept_id="VASOPRESSIN",
        display="Vasopressin",
        level=AbstractionLevel.NORMALIZED,
        domain="test",
        synonyms=frozenset(["adh"]),
    )
    ns_bolus = ClinicalConcept(
        concept_id="NS_BOLUS",
        display="Normal Saline Bolus",
        level=AbstractionLevel.NORMALIZED,
        domain="test",
        synonyms=frozenset(["saline_bolus", "give_ns"]),
    )

    onto.add_concept(goal)
    onto.add_concept(vasopressor)
    onto.add_concept(fluid)
    onto.add_concept(norepi)
    onto.add_concept(vasopressin)
    onto.add_concept(ns_bolus)

    # IS-A hierarchy
    onto.add_relation(vasopressor, ConceptRelation.IS_A, goal)
    onto.add_relation(fluid, ConceptRelation.IS_A, goal)
    onto.add_relation(norepi, ConceptRelation.IS_A, vasopressor)
    onto.add_relation(vasopressin, ConceptRelation.IS_A, vasopressor)
    onto.add_relation(ns_bolus, ConceptRelation.IS_A, fluid)

    # PRECEDES: fluid before vasopressor
    onto.add_relation(ns_bolus, ConceptRelation.PRECEDES, norepi)

    return onto


@pytest.fixture
def sepsis_ontology():
    """Full sepsis domain ontology."""
    return build_sepsis_ontology()


@pytest.fixture
def chest_pain_ontology():
    """Full chest pain domain ontology."""
    return build_chest_pain_ontology()


# ======================================================================
# Test Core Ontology Structure
# ======================================================================

class TestClinicalOntologyStructure:
    """Test basic ontology operations."""

    def test_add_concept(self, simple_ontology):
        assert simple_ontology.size == 6
        assert simple_ontology.get_concept("NOREPINEPHRINE") is not None
        assert simple_ontology.get_concept("NONEXISTENT") is None

    def test_concept_properties(self, simple_ontology):
        norepi = simple_ontology.get_concept("NOREPINEPHRINE")
        assert norepi.display == "Norepinephrine"
        assert norepi.level == AbstractionLevel.NORMALIZED
        assert norepi.system == "RxNorm"
        assert norepi.code == "7512"
        assert "levophed" in norepi.synonyms

    def test_concept_hashable(self):
        c1 = ClinicalConcept("A", "A", AbstractionLevel.NORMALIZED)
        c2 = ClinicalConcept("A", "A", AbstractionLevel.NORMALIZED)
        c3 = ClinicalConcept("B", "B", AbstractionLevel.NORMALIZED)
        assert c1 == c2
        assert c1 != c3
        assert len({c1, c2, c3}) == 2

    def test_concepts_at_level(self, simple_ontology):
        l1 = simple_ontology.concepts_at_level(AbstractionLevel.NORMALIZED)
        assert len(l1) == 3
        l2 = simple_ontology.concepts_at_level(AbstractionLevel.CATEGORY)
        assert len(l2) == 2
        l3 = simple_ontology.concepts_at_level(AbstractionLevel.GOAL)
        assert len(l3) == 1


# ======================================================================
# Test IS-A Hierarchy (Subsumption)
# ======================================================================

class TestSubsumption:
    """Test IS-A hierarchy traversal."""

    def test_direct_parents(self, simple_ontology):
        parents = simple_ontology.direct_parents("NOREPINEPHRINE")
        assert "VASOPRESSOR" in parents
        assert len(parents) == 1

    def test_direct_children(self, simple_ontology):
        children = simple_ontology.direct_children("VASOPRESSOR")
        assert "NOREPINEPHRINE" in children
        assert "VASOPRESSIN" in children
        assert len(children) == 2

    def test_transitive_ancestors(self, simple_ontology):
        ancestors = simple_ontology.ancestors("NOREPINEPHRINE")
        assert "VASOPRESSOR" in ancestors
        assert "HEMODYNAMIC_SUPPORT" in ancestors
        assert len(ancestors) == 2

    def test_transitive_descendants(self, simple_ontology):
        descendants = simple_ontology.descendants("HEMODYNAMIC_SUPPORT")
        assert "VASOPRESSOR" in descendants
        assert "FLUID_THERAPY" in descendants
        assert "NOREPINEPHRINE" in descendants
        assert "VASOPRESSIN" in descendants
        assert "NS_BOLUS" in descendants
        assert len(descendants) == 5

    def test_is_a(self, simple_ontology):
        norepi = simple_ontology.get_concept("NOREPINEPHRINE")
        vaso = simple_ontology.get_concept("VASOPRESSOR")
        goal = simple_ontology.get_concept("HEMODYNAMIC_SUPPORT")
        fluid = simple_ontology.get_concept("FLUID_THERAPY")

        assert simple_ontology.is_a(norepi, vaso)        # direct
        assert simple_ontology.is_a(norepi, goal)        # transitive
        assert not simple_ontology.is_a(vaso, norepi)    # not reverse
        assert not simple_ontology.is_a(norepi, fluid)   # not sibling parent

    def test_subsumption_distance(self, simple_ontology):
        assert simple_ontology.subsumption_distance("NOREPINEPHRINE", "VASOPRESSOR") == 1
        assert simple_ontology.subsumption_distance("NOREPINEPHRINE", "HEMODYNAMIC_SUPPORT") == 2
        assert simple_ontology.subsumption_distance("NOREPINEPHRINE", "NOREPINEPHRINE") == 0
        assert simple_ontology.subsumption_distance("NOREPINEPHRINE", "FLUID_THERAPY") == -1

    def test_lca(self, simple_ontology):
        lca = simple_ontology.lca("NOREPINEPHRINE", "VASOPRESSIN")
        assert lca == "VASOPRESSOR"

        lca2 = simple_ontology.lca("NOREPINEPHRINE", "NS_BOLUS")
        assert lca2 == "HEMODYNAMIC_SUPPORT"

    def test_no_ancestors_for_root(self, simple_ontology):
        assert len(simple_ontology.ancestors("HEMODYNAMIC_SUPPORT")) == 0

    def test_no_descendants_for_leaf(self, simple_ontology):
        assert len(simple_ontology.descendants("NOREPINEPHRINE")) == 0


# ======================================================================
# Test Multi-Level Abstraction
# ======================================================================

class TestAbstraction:
    """Test multi-level abstraction operations."""

    def test_abstract_to_category(self, simple_ontology):
        result = simple_ontology.abstract_to_level(
            "NOREPINEPHRINE", AbstractionLevel.CATEGORY
        )
        assert result is not None
        assert result.concept_id == "VASOPRESSOR"

    def test_abstract_to_goal(self, simple_ontology):
        result = simple_ontology.abstract_to_level(
            "NOREPINEPHRINE", AbstractionLevel.GOAL
        )
        assert result is not None
        assert result.concept_id == "HEMODYNAMIC_SUPPORT"

    def test_abstract_same_level(self, simple_ontology):
        result = simple_ontology.abstract_to_level(
            "VASOPRESSOR", AbstractionLevel.CATEGORY
        )
        assert result is not None
        assert result.concept_id == "VASOPRESSOR"

    def test_abstract_no_parent_at_level(self, simple_ontology):
        result = simple_ontology.abstract_to_level(
            "NOREPINEPHRINE", AbstractionLevel.PHASE
        )
        assert result is None

    def test_abstraction_chain(self, simple_ontology):
        chain = simple_ontology.get_abstraction_chain("NOREPINEPHRINE")
        assert len(chain) == 3
        assert chain[0].concept_id == "NOREPINEPHRINE"
        assert chain[1].concept_id == "VASOPRESSOR"
        assert chain[2].concept_id == "HEMODYNAMIC_SUPPORT"

    def test_abstraction_chain_root(self, simple_ontology):
        chain = simple_ontology.get_abstraction_chain("HEMODYNAMIC_SUPPORT")
        assert len(chain) == 1


# ======================================================================
# Test OntologyMatcher
# ======================================================================

class TestOntologyMatcher:
    """Test the multi-strategy matcher."""

    def test_exact_match(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        result = matcher.match("NOREPINEPHRINE")
        assert result.matched
        assert result.concept_id == "NOREPINEPHRINE"
        assert result.confidence == 1.0
        assert result.strategy == "exact"

    def test_exact_match_case_insensitive(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        result = matcher.match("norepinephrine")
        assert result.matched
        assert result.concept_id == "NOREPINEPHRINE"

    def test_synonym_match(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        result = matcher.match("levophed")
        assert result.matched
        assert result.concept_id == "NOREPINEPHRINE"
        assert result.confidence == 1.0
        assert result.strategy == "synonym"

    def test_synonym_match_norepi(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        result = matcher.match("norepi")
        assert result.matched
        assert result.concept_id == "NOREPINEPHRINE"

    def test_synonym_match_start_norepinephrine(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        result = matcher.match("start_norepinephrine")
        assert result.matched
        assert result.concept_id == "NOREPINEPHRINE"

    def test_fuzzy_match(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig(fuzzy_threshold=0.5))
        result = matcher.match("vasopressor_support")
        assert result.matched
        assert result.concept_id == "VASOPRESSOR"

    def test_no_match(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        result = matcher.match("completely_unrelated_action")
        assert not result.matched
        assert result.confidence == 0.0
        assert result.strategy == "none"

    def test_match_caching(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        r1 = matcher.match("levophed")
        r2 = matcher.match("levophed")
        assert r1 is r2  # Same cached object

    def test_clear_cache(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        matcher.match("levophed")
        matcher.clear_cache()
        r2 = matcher.match("levophed")
        assert r2.matched

    def test_match_at_level(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        result = matcher.match_at_level("levophed", AbstractionLevel.GOAL)
        assert result.matched
        assert result.concept_id == "HEMODYNAMIC_SUPPORT"
        assert result.match_level == AbstractionLevel.GOAL


# ======================================================================
# Test Conformance Helpers
# ======================================================================

class TestConformanceHelpers:
    """Test satisfies() and is_forbidden() methods."""

    def test_satisfies_exact(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        assert matcher.satisfies("NOREPINEPHRINE", "NOREPINEPHRINE")

    def test_satisfies_synonym(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        assert matcher.satisfies("levophed", "NOREPINEPHRINE")

    def test_satisfies_subsumption(self, simple_ontology):
        """Specific drug satisfies general category requirement."""
        matcher = OntologyMatcher(simple_ontology, OntologyConfig(
            enable_mandatory_subsumption=True
        ))
        # norepinephrine satisfies VASOPRESSOR requirement
        assert matcher.satisfies("levophed", "VASOPRESSOR")
        # norepinephrine satisfies HEMODYNAMIC_SUPPORT requirement
        assert matcher.satisfies("levophed", "HEMODYNAMIC_SUPPORT")

    def test_satisfies_no_subsumption_when_disabled(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig(
            enable_mandatory_subsumption=False
        ))
        # Without subsumption, levophed does NOT satisfy VASOPRESSOR
        assert not matcher.satisfies("levophed", "VASOPRESSOR")

    def test_satisfies_sibling_not_match(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        # Vasopressin does NOT satisfy NOREPINEPHRINE
        assert not matcher.satisfies("adh", "NOREPINEPHRINE")

    def test_is_forbidden_exact(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        assert matcher.is_forbidden("NOREPINEPHRINE", {"NOREPINEPHRINE"})

    def test_is_forbidden_propagation(self, simple_ontology):
        """Forbidden category propagates to descendants."""
        matcher = OntologyMatcher(simple_ontology, OntologyConfig(
            enable_contraindication_propagation=True
        ))
        # If VASOPRESSOR is forbidden, NOREPINEPHRINE is also forbidden
        assert matcher.is_forbidden("levophed", {"VASOPRESSOR"})
        assert matcher.is_forbidden("adh", {"VASOPRESSOR"})

    def test_is_forbidden_no_propagation_when_disabled(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig(
            enable_contraindication_propagation=False
        ))
        assert not matcher.is_forbidden("levophed", {"VASOPRESSOR"})

    def test_is_forbidden_unrelated(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        assert not matcher.is_forbidden("give_ns", {"VASOPRESSOR"})


# ======================================================================
# Test Sepsis Domain
# ======================================================================

class TestSepsisDomain:
    """Test sepsis domain ontology."""

    def test_ontology_size(self, sepsis_ontology):
        assert sepsis_ontology.size >= 25

    def test_antibiotic_hierarchy(self, sepsis_ontology):
        # pip-tazo IS-A antibiotic therapy
        ancestors = sepsis_ontology.ancestors("GIVE_PIPERACILLIN_TAZOBACTAM")
        assert "ANTIBIOTIC_THERAPY" in ancestors
        assert "INFECTION_CONTROL" in ancestors
        assert "SEPSIS_HOUR1_BUNDLE" in ancestors

    def test_vasopressor_hierarchy(self, sepsis_ontology):
        ancestors = sepsis_ontology.ancestors("START_VASOPRESSOR_NOREPINEPHRINE")
        assert "VASOPRESSOR_SUPPORT" in ancestors
        assert "HEMODYNAMIC_RESUSCITATION" in ancestors

    def test_specific_abx_satisfies_broad(self, sepsis_ontology):
        matcher = OntologyMatcher(sepsis_ontology, OntologyConfig())
        # pip-tazo satisfies broad-spectrum antibiotics requirement
        assert matcher.satisfies("pip_tazo", "GIVE_BROAD_SPECTRUM_ANTIBIOTICS")
        assert matcher.satisfies("meropenem", "GIVE_BROAD_SPECTRUM_ANTIBIOTICS")

    def test_vasopressor_synonym_matching(self, sepsis_ontology):
        matcher = OntologyMatcher(sepsis_ontology, OntologyConfig())
        result = matcher.match("levophed")
        assert result.matched
        assert result.concept_id == "START_VASOPRESSOR_NOREPINEPHRINE"

    def test_lactate_synonym(self, sepsis_ontology):
        matcher = OntologyMatcher(sepsis_ontology, OntologyConfig())
        result = matcher.match("lactic_acid")
        assert result.matched
        assert result.concept_id == "ORDER_LACTATE"

    def test_crystalloid_synonyms(self, sepsis_ontology):
        matcher = OntologyMatcher(sepsis_ontology, OntologyConfig())
        for syn in ["give_ns_bolus", "fluid_bolus", "iv_fluid_resuscitation"]:
            result = matcher.match(syn)
            assert result.matched, f"Failed for synonym: {syn}"
            assert result.concept_id == "GIVE_CRYSTALLOID"

    def test_abstraction_chain_norepi(self, sepsis_ontology):
        chain = sepsis_ontology.get_abstraction_chain("START_VASOPRESSOR_NOREPINEPHRINE")
        ids = [c.concept_id for c in chain]
        assert "START_VASOPRESSOR_NOREPINEPHRINE" in ids
        assert "VASOPRESSOR_SUPPORT" in ids
        assert "HEMODYNAMIC_RESUSCITATION" in ids
        assert "SEPSIS_RESUSCITATION" in ids

    def test_precedes_relation(self, sepsis_ontology):
        # Blood culture precedes antibiotics
        rels = sepsis_ontology._relations.get("ORDER_BLOOD_CULTURE", [])
        precedes_targets = [t for r, t in rels if r == ConceptRelation.PRECEDES]
        assert "GIVE_BROAD_SPECTRUM_ANTIBIOTICS" in precedes_targets


# ======================================================================
# Test Chest Pain Domain
# ======================================================================

class TestChestPainDomain:
    """Test chest pain/ACS domain ontology."""

    def test_ontology_size(self, chest_pain_ontology):
        assert chest_pain_ontology.size >= 28

    def test_rv_contraindication(self, chest_pain_ontology):
        # RV infarct CONTRAINDICATES nitrates
        rels = chest_pain_ontology._relations.get("DIAGNOSE_RV_INFARCT", [])
        contra_targets = [t for r, t in rels if r == ConceptRelation.CONTRAINDICATES]
        assert "GIVE_NITRATES" in contra_targets

    def test_ecg_hierarchy(self, chest_pain_ontology):
        ancestors = chest_pain_ontology.ancestors("ORDER_ECG_V4R")
        assert "ECG_ASSESSMENT" in ancestors
        # V4R is also a specialized ECG
        assert "ORDER_ECG" in ancestors

    def test_antiplatelet_subsumption(self, chest_pain_ontology):
        matcher = OntologyMatcher(chest_pain_ontology, OntologyConfig())
        # Aspirin and P2Y12 both satisfy antiplatelet requirement
        assert matcher.satisfies("aspirin", "ANTIPLATELET_AGENTS")
        assert matcher.satisfies("clopidogrel", "GIVE_P2Y12_INHIBITOR")

    def test_nitrate_forbidden_with_rv(self, chest_pain_ontology):
        matcher = OntologyMatcher(chest_pain_ontology, OntologyConfig())
        assert matcher.is_forbidden("nitroglycerin", {"GIVE_NITRATES"})
        assert matcher.is_forbidden("ntg", {"GIVE_NITRATES"})

    def test_reperfusion_hierarchy(self, chest_pain_ontology):
        ancestors = chest_pain_ontology.ancestors("ACTIVATE_CATH_LAB")
        assert "REPERFUSION_PROCEDURES" in ancestors
        assert "REPERFUSION_THERAPY" in ancestors

    def test_stemi_synonym(self, chest_pain_ontology):
        matcher = OntologyMatcher(chest_pain_ontology, OntologyConfig())
        result = matcher.match("st_elevation_mi")
        assert result.matched
        assert result.concept_id == "DIAGNOSE_STEMI"


# ======================================================================
# Test AKI Domain
# ======================================================================

class TestAKIDomain:
    """Test AKI domain ontology."""

    def test_ontology_size(self):
        onto = build_aki_ontology()
        assert onto.size >= 20

    def test_nephrotoxin_hierarchy(self):
        onto = build_aki_ontology()
        ancestors = onto.ancestors("GIVE_NEPHROTOXIC_AGENT")
        assert "NEPHROTOXIC_AGENTS" in ancestors
        assert "NEPHROPROTECTION" in ancestors

    def test_rrt_hierarchy(self):
        onto = build_aki_ontology()
        ancestors = onto.ancestors("START_CRRT")
        assert "RRT_MODALITIES" in ancestors
        assert "RENAL_REPLACEMENT" in ancestors

    def test_creatinine_matching(self):
        matcher = get_ontology_matcher("aki")
        result = matcher.match("serum_creatinine")
        assert result.matched
        assert result.concept_id == "ORDER_CREATININE"


# ======================================================================
# Test Stroke Domain
# ======================================================================

class TestStrokeDomain:
    """Test stroke domain ontology."""

    def test_ontology_size(self):
        onto = build_stroke_ontology()
        assert onto.size >= 18

    def test_tpa_hierarchy(self):
        onto = build_stroke_ontology()
        ancestors = onto.ancestors("GIVE_ALTEPLASE")
        assert "THROMBOLYTIC_AGENTS" in ancestors
        assert "THROMBOLYSIS" in ancestors
        assert "STROKE_INTERVENTION" in ancestors

    def test_nihss_matching(self):
        matcher = get_ontology_matcher("stroke")
        result = matcher.match("nihss")
        assert result.matched
        assert result.concept_id == "ASSESS_NIHSS"

    def test_ct_before_tpa(self):
        onto = build_stroke_ontology()
        rels = onto._relations.get("ORDER_CT_HEAD", [])
        precedes = [t for r, t in rels if r == ConceptRelation.PRECEDES]
        assert "GIVE_ALTEPLASE" in precedes


# ======================================================================
# Test Heart Failure Domain
# ======================================================================

class TestHeartFailureDomain:
    """Test heart failure domain ontology."""

    def test_ontology_size(self):
        onto = build_heart_failure_ontology()
        assert onto.size >= 20

    def test_gdmt_hierarchy(self):
        onto = build_heart_failure_ontology()
        ancestors = onto.ancestors("GIVE_SACUBITRIL_VALSARTAN")
        assert "RAAS_INHIBITORS" in ancestors
        assert "GDMT_INITIATION" in ancestors
        assert "HFREF_OPTIMIZATION" in ancestors

    def test_entresto_synonym(self):
        matcher = get_ontology_matcher("heart_failure")
        result = matcher.match("entresto")
        assert result.matched
        assert result.concept_id == "GIVE_SACUBITRIL_VALSARTAN"


# ======================================================================
# Test DKA Domain
# ======================================================================

class TestDKADomain:
    """Test DKA domain ontology."""

    def test_ontology_size(self):
        onto = build_dka_ontology()
        assert onto.size >= 20

    def test_insulin_hierarchy(self):
        onto = build_dka_ontology()
        ancestors = onto.ancestors("START_INSULIN_DRIP")
        assert "INSULIN_AGENTS" in ancestors
        assert "INSULIN_THERAPY" in ancestors
        assert "DKA_CORRECTION" in ancestors

    def test_insulin_drip_synonym(self):
        matcher = get_ontology_matcher("dka")
        result = matcher.match("insulin_infusion")
        assert result.matched
        assert result.concept_id == "START_INSULIN_DRIP"

    def test_potassium_matching(self):
        matcher = get_ontology_matcher("dka")
        # "potassium_replacement" matches the L2 category directly
        result = matcher.match("potassium_replacement")
        assert result.matched
        assert result.concept_id == "POTASSIUM_REPLACEMENT"
        # Specific synonyms match GIVE_KCL
        result2 = matcher.match("kcl")
        assert result2.matched
        assert result2.concept_id == "GIVE_KCL"


# ======================================================================
# Test Unified Ontology
# ======================================================================

class TestUnifiedOntology:
    """Test the cross-domain unified ontology."""

    def test_unified_size(self):
        onto = build_unified_ontology()
        # Should contain concepts from all 6 domains
        assert onto.size > 100

    def test_cross_domain_concepts(self):
        onto = build_unified_ontology()
        # Sepsis concepts exist
        assert onto.get_concept("ORDER_BLOOD_CULTURE") is not None
        # Chest pain concepts exist
        assert onto.get_concept("ACTIVATE_CATH_LAB") is not None
        # AKI concepts exist
        assert onto.get_concept("START_CRRT") is not None
        # Stroke concepts exist
        assert onto.get_concept("GIVE_ALTEPLASE") is not None
        # HF concepts exist
        assert onto.get_concept("GIVE_SACUBITRIL_VALSARTAN") is not None
        # DKA concepts exist
        assert onto.get_concept("START_INSULIN_DRIP") is not None

    def test_unified_matcher(self):
        matcher = get_unified_matcher()
        # Should match across all domains
        assert matcher.match("levophed").matched  # sepsis
        assert matcher.match("nitroglycerin").matched  # chest pain
        assert matcher.match("serum_creatinine").matched  # AKI
        assert matcher.match("nihss").matched  # stroke
        assert matcher.match("entresto").matched  # HF
        assert matcher.match("insulin_infusion").matched  # DKA


# ======================================================================
# Test Factory Functions
# ======================================================================

class TestFactoryFunctions:
    """Test domain ontology factory functions."""

    def test_build_domain_ontology_valid(self):
        for domain in ["sepsis", "chest_pain", "aki", "stroke", "heart_failure", "dka"]:
            onto = build_domain_ontology(domain)
            assert onto.size > 0

    def test_build_domain_ontology_invalid(self):
        with pytest.raises(ValueError, match="Unknown domain"):
            build_domain_ontology("nonexistent")

    def test_get_ontology_matcher(self):
        matcher = get_ontology_matcher("sepsis")
        assert isinstance(matcher, OntologyMatcher)
        assert matcher.ontology.size > 0

    def test_get_ontology_matcher_custom_config(self):
        config = OntologyConfig(fuzzy_threshold=0.8)
        matcher = get_ontology_matcher("sepsis", config)
        assert matcher._config.fuzzy_threshold == 0.8


# ======================================================================
# Test Edge Cases
# ======================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_ontology(self):
        onto = ClinicalOntology()
        assert onto.size == 0
        assert onto.ancestors("anything") == frozenset()
        assert onto.descendants("anything") == frozenset()

    def test_single_concept(self):
        onto = ClinicalOntology()
        c = ClinicalConcept("SOLO", "Solo Concept", AbstractionLevel.NORMALIZED)
        onto.add_concept(c)
        assert onto.size == 1
        assert onto.ancestors("SOLO") == frozenset()
        assert onto.descendants("SOLO") == frozenset()

    def test_match_empty_string(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        result = matcher.match("")
        assert not result.matched

    def test_lca_no_common_ancestor(self):
        onto = ClinicalOntology()
        a = ClinicalConcept("A", "A", AbstractionLevel.NORMALIZED)
        b = ClinicalConcept("B", "B", AbstractionLevel.NORMALIZED)
        onto.add_concept(a)
        onto.add_concept(b)
        assert onto.lca("A", "B") is None

    def test_lca_self(self, simple_ontology):
        lca = simple_ontology.lca("NOREPINEPHRINE", "NOREPINEPHRINE")
        assert lca == "NOREPINEPHRINE"

    def test_diamond_hierarchy(self):
        """Test with diamond inheritance (A -> B, A -> C, B -> D, C -> D)."""
        onto = ClinicalOntology()
        d = ClinicalConcept("D", "D", AbstractionLevel.PHASE)
        b = ClinicalConcept("B", "B", AbstractionLevel.GOAL)
        c = ClinicalConcept("C", "C", AbstractionLevel.GOAL)
        a = ClinicalConcept("A", "A", AbstractionLevel.NORMALIZED)

        onto.add_concept(d)
        onto.add_concept(b)
        onto.add_concept(c)
        onto.add_concept(a)

        onto.add_relation(a, ConceptRelation.IS_A, b)
        onto.add_relation(a, ConceptRelation.IS_A, c)
        onto.add_relation(b, ConceptRelation.IS_A, d)
        onto.add_relation(c, ConceptRelation.IS_A, d)

        ancestors = onto.ancestors("A")
        assert "B" in ancestors
        assert "C" in ancestors
        assert "D" in ancestors
        assert len(ancestors) == 3

    def test_concept_nonexistent_abstraction(self, simple_ontology):
        result = simple_ontology.abstract_to_level("NONEXISTENT", AbstractionLevel.GOAL)
        assert result is None

    def test_abstraction_chain_nonexistent(self, simple_ontology):
        chain = simple_ontology.get_abstraction_chain("NONEXISTENT")
        assert len(chain) == 0

    def test_satisfies_unknown_requirement(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        # Unknown requirement should not match
        assert not matcher.satisfies("levophed", "UNKNOWN_REQUIREMENT")

    def test_is_forbidden_empty_set(self, simple_ontology):
        matcher = OntologyMatcher(simple_ontology, OntologyConfig())
        assert not matcher.is_forbidden("levophed", set())

    def test_match_result_properties(self):
        r = MatchResult(
            source="test",
            matched_concept=None,
            confidence=0.0,
            match_level=AbstractionLevel.RAW,
        )
        assert not r.matched
        assert r.concept_id is None

    def test_contraindications_query(self, chest_pain_ontology):
        contras = chest_pain_ontology.get_contraindications("DIAGNOSE_RV_INFARCT")
        assert "GIVE_NITRATES" in contras
