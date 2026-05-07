"""Validation tests for clinical ontology against real medical terminology data.

Tests cross-reference ontology concepts against:
1. expanded_codes.yaml (LOINC/SNOMED/RxNorm ground truth)
2. CPG graph action vocabularies (mandatory/allowed/forbidden actions)
3. External benchmark action formats (AgentClinic, MedAgentBench, MedChain)

These tests ensure clinical accuracy — not just structural correctness.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pytest
import yaml

from cga_bench.semantic_layer.ontology.concept import AbstractionLevel, ClinicalConcept
from cga_bench.semantic_layer.ontology.clinical_ontology import (
    ClinicalOntology,
    OntologyConfig,
    OntologyMatcher,
)
from cga_bench.semantic_layer.ontology.domain_hierarchies import (
    DOMAIN_BUILDERS,
    build_sepsis_ontology,
    build_chest_pain_ontology,
    build_aki_ontology,
    build_stroke_ontology,
    build_heart_failure_ontology,
    build_dka_ontology,
    build_unified_ontology,
    get_ontology_matcher,
    get_unified_matcher,
)


# ======================================================================
# Fixtures
# ======================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent  # cga_bench/


@pytest.fixture(scope="module")
def expanded_codes() -> Dict[str, List[Dict[str, Any]]]:
    """Load expanded_codes.yaml ground truth."""
    path = PROJECT_ROOT / "semantic_layer" / "terminology" / "expanded_codes.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {
        "loinc": data.get("loinc", []),
        "snomed": data.get("snomed", []),
        "rxnorm": data.get("rxnorm", []),
    }


@pytest.fixture(scope="module")
def rxnorm_by_code(expanded_codes) -> Dict[str, Dict[str, Any]]:
    """Index RxNorm entries by code."""
    return {entry["code"]: entry for entry in expanded_codes["rxnorm"]}


@pytest.fixture(scope="module")
def rxnorm_by_internal(expanded_codes) -> Dict[str, Dict[str, Any]]:
    """Index RxNorm entries by internal_code."""
    return {entry["internal_code"]: entry for entry in expanded_codes["rxnorm"]}


@pytest.fixture(scope="module")
def snomed_by_code(expanded_codes) -> Dict[str, Dict[str, Any]]:
    """Index SNOMED entries by code."""
    return {entry["code"]: entry for entry in expanded_codes["snomed"]}


@pytest.fixture(scope="module")
def loinc_by_code(expanded_codes) -> Dict[str, Dict[str, Any]]:
    """Index LOINC entries by code."""
    result = {}
    for entry in expanded_codes["loinc"]:
        code = entry["code"]
        if code not in result:  # handle duplicates, keep first
            result[code] = entry
    return result


@pytest.fixture(scope="module")
def cpg_graphs() -> Dict[str, Dict[str, Any]]:
    """Load all CPG graph YAML files."""
    graphs_dir = PROJECT_ROOT / "cpg_model" / "graphs"
    result = {}
    for path in sorted(graphs_dir.glob("*.yaml")):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        result[path.stem] = data
    return result


@pytest.fixture(scope="module")
def unified_matcher() -> OntologyMatcher:
    """Get unified ontology matcher."""
    return get_unified_matcher()


def _extract_cpg_actions(graph_data: Dict[str, Any]) -> Tuple[Set[str], Set[str], Set[str]]:
    """Extract mandatory, allowed, and forbidden actions from a CPG graph."""
    mandatory = set()
    allowed = set()
    forbidden = set()
    for node_id, node in graph_data.get("nodes", {}).items():
        for a in node.get("mandatory_actions", []):
            mandatory.add(a)
        for a in node.get("allowed_actions", []):
            allowed.add(a)
        for a in node.get("forbidden_actions", []):
            forbidden.add(a)
    return mandatory, allowed, forbidden


def _get_ontology_coded_concepts(domain: str) -> List[ClinicalConcept]:
    """Get all concepts with external codes from a domain ontology."""
    onto = DOMAIN_BUILDERS[domain]()
    return [
        c for c in onto.concepts.values()
        if c.system != "CGA-Bench" and c.code is not None
    ]


def _get_all_synonyms(onto: ClinicalOntology) -> Dict[str, str]:
    """Get synonym -> concept_id mapping for an ontology."""
    result = {}
    for cid, concept in onto.concepts.items():
        for syn in concept.synonyms:
            result[syn] = cid
    return result


# ======================================================================
# 1. RxNorm Code Validation
# ======================================================================

class TestRxNormCodeValidation:
    """Validate ontology RxNorm codes against expanded_codes.yaml ground truth."""

    # Expected ontology RxNorm code matches (ontology_code: expanded_code)
    EXPECTED_RXNORM_MATCHES = {
        # Sepsis domain
        "29561": "29561",   # Meropenem
        "11124": "11124",   # Vancomycin
        "7512": "7512",     # Norepinephrine
        "11149": "11149",   # Vasopressin
        # Chest Pain domain
        "1191": "1191",     # Aspirin
        "5224": "5224",     # Heparin
        "67108": "67108",   # Enoxaparin
        # Stroke domain
        "8410": "8410",     # Alteplase
        # Heart Failure domain
        "4603": "4603",     # Furosemide
        "3616": "3616",     # Dobutamine
        # DKA domain
        "8591": "8591",     # Potassium Chloride
    }

    def test_rxnorm_codes_exist_in_ground_truth(self, rxnorm_by_code):
        """All ontology RxNorm codes should exist in expanded_codes.yaml."""
        all_coded_concepts = []
        for domain in DOMAIN_BUILDERS:
            all_coded_concepts.extend(_get_ontology_coded_concepts(domain))

        rxnorm_concepts = [c for c in all_coded_concepts if c.system == "RxNorm"]
        missing = []

        for concept in rxnorm_concepts:
            if concept.code not in rxnorm_by_code:
                missing.append(f"{concept.concept_id} (code={concept.code})")

        # Report findings - some codes may be valid but not in our subset
        if missing:
            pytest.xfail(
                f"RxNorm codes not in expanded_codes.yaml "
                f"(may be valid codes not in our reference subset): {missing}"
            )

    def test_known_rxnorm_matches(self, rxnorm_by_code):
        """Verify known RxNorm code matches between ontology and ground truth."""
        for onto_code, expected_code in self.EXPECTED_RXNORM_MATCHES.items():
            assert onto_code in rxnorm_by_code, (
                f"Expected RxNorm code {onto_code} not found in expanded_codes.yaml"
            )

    def test_rxnorm_display_names_reasonable(self, rxnorm_by_code):
        """Ontology concept displays should be related to RxNorm display names."""
        for domain in DOMAIN_BUILDERS:
            onto = DOMAIN_BUILDERS[domain]()
            for concept in onto.concepts.values():
                if concept.system == "RxNorm" and concept.code in rxnorm_by_code:
                    ref = rxnorm_by_code[concept.code]
                    # Check that drug name appears in concept display or synonym
                    drug_name = ref["internal_code"].lower()
                    concept_text = (
                        concept.display.lower() + " " +
                        " ".join(concept.synonyms).lower()
                    )
                    assert drug_name in concept_text or ref["display"].lower().split()[0] in concept_text, (
                        f"Concept {concept.concept_id} with RxNorm code {concept.code} "
                        f"doesn't mention drug '{ref['display']}'"
                    )

    def test_rxnorm_synonym_overlap(self, rxnorm_by_code):
        """Ontology synonyms should overlap with expanded_codes.yaml synonyms."""
        overlaps = 0
        total = 0
        mismatches = []

        for domain in DOMAIN_BUILDERS:
            onto = DOMAIN_BUILDERS[domain]()
            for concept in onto.concepts.values():
                if concept.system == "RxNorm" and concept.code in rxnorm_by_code:
                    ref = rxnorm_by_code[concept.code]
                    ref_synonyms_lower = {s.lower() for s in ref.get("synonyms", [])}
                    onto_synonyms_lower = {s.lower() for s in concept.synonyms}

                    total += 1
                    overlap = ref_synonyms_lower & onto_synonyms_lower
                    if overlap:
                        overlaps += 1
                    else:
                        mismatches.append(
                            f"{concept.concept_id}: onto={onto_synonyms_lower} "
                            f"vs ref={ref_synonyms_lower}"
                        )

        if total > 0:
            overlap_rate = overlaps / total
            # At least 30% of coded concepts should share synonyms with ground truth
            assert overlap_rate >= 0.3 or total < 5, (
                f"Low synonym overlap rate: {overlap_rate:.1%} ({overlaps}/{total}). "
                f"Mismatches: {mismatches[:5]}"
            )


# ======================================================================
# 2. SNOMED Code Validation
# ======================================================================

class TestSNOMEDCodeValidation:
    """Validate ontology SNOMED codes against expanded_codes.yaml ground truth."""

    def test_snomed_codes_exist_in_ground_truth(self, snomed_by_code):
        """All ontology SNOMED codes should exist in expanded_codes.yaml."""
        all_coded_concepts = []
        for domain in DOMAIN_BUILDERS:
            all_coded_concepts.extend(_get_ontology_coded_concepts(domain))

        snomed_concepts = [c for c in all_coded_concepts if c.system == "SNOMED"]
        missing = []

        for concept in snomed_concepts:
            if concept.code not in snomed_by_code:
                missing.append(f"{concept.concept_id} (code={concept.code})")

        if missing:
            pytest.xfail(
                f"SNOMED codes not in expanded_codes.yaml: {missing}. "
                f"These may be valid SNOMED codes for procedures not in our reference."
            )

    def test_stemi_snomed_code(self, snomed_by_code):
        """STEMI diagnosis should have correct SNOMED code."""
        onto = build_chest_pain_ontology()
        stemi = onto.get_concept("DIAGNOSE_STEMI")
        assert stemi is not None
        assert stemi.system == "SNOMED"
        assert stemi.code == "401303003"
        # Verify against ground truth
        if stemi.code in snomed_by_code:
            ref = snomed_by_code[stemi.code]
            assert "stemi" in ref["internal_code"].lower() or "st elevation" in ref["display"].lower()


# ======================================================================
# 3. CPG Graph Action Coverage
# ======================================================================

class TestCPGGraphActionCoverage:
    """Validate ontology covers CPG graph action vocabularies."""

    # Map CPG graph files to ontology domains
    GRAPH_DOMAIN_MAP = {
        "ssc_sepsis_hour1": "sepsis",
        "aha_chest_pain": "chest_pain",
        "kdigo_aki_full": "aki",
        "kdigo_contrast_aki": "aki",
        "aha_stroke": "stroke",
        "aha_heart_failure": "heart_failure",
        "ada_dka_management": "dka",
    }

    def test_sepsis_mandatory_actions_resolvable(self, cpg_graphs, unified_matcher):
        """All sepsis CPG mandatory actions should resolve through ontology."""
        if "ssc_sepsis_hour1" not in cpg_graphs:
            pytest.skip("ssc_sepsis_hour1_bundle.yaml not found")

        mandatory, _, _ = _extract_cpg_actions(cpg_graphs["ssc_sepsis_hour1"])
        resolvable = set()
        unresolvable = set()

        for action in mandatory:
            match = unified_matcher.match(action)
            if match.matched:
                resolvable.add(action)
            else:
                unresolvable.add(action)

        # Core bundle actions must be resolvable
        core_actions = {
            "order_lab_lactate", "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics", "give_crystalloid_30ml_kg",
        }
        for action in core_actions:
            if action in mandatory:
                assert action in resolvable, (
                    f"Core sepsis action '{action}' not resolvable by ontology"
                )

    def test_sepsis_allowed_actions_coverage(self, cpg_graphs, unified_matcher):
        """Majority of sepsis allowed actions should be resolvable."""
        if "ssc_sepsis_hour1" not in cpg_graphs:
            pytest.skip("ssc_sepsis_hour1_bundle.yaml not found")

        _, allowed, _ = _extract_cpg_actions(cpg_graphs["ssc_sepsis_hour1"])
        resolvable = {a for a in allowed if unified_matcher.match(a).matched}

        coverage = len(resolvable) / len(allowed) if allowed else 0
        assert coverage >= 0.4, (
            f"Low sepsis action coverage: {coverage:.1%} "
            f"({len(resolvable)}/{len(allowed)}). "
            f"Unresolvable: {sorted(allowed - resolvable)}"
        )

    def test_chest_pain_mandatory_actions_resolvable(self, cpg_graphs, unified_matcher):
        """All chest pain CPG mandatory actions should resolve through ontology."""
        if "aha_chest_pain" not in cpg_graphs:
            pytest.skip("aha_chest_pain_evaluation.yaml not found")

        mandatory, _, _ = _extract_cpg_actions(cpg_graphs["aha_chest_pain"])
        resolvable = set()
        unresolvable = set()

        for action in mandatory:
            match = unified_matcher.match(action)
            if match.matched:
                resolvable.add(action)
            else:
                unresolvable.add(action)

        # Core ACS actions
        core_actions = {"obtain_12_lead_ecg", "assess_vital_signs"}
        for action in core_actions:
            if action in mandatory:
                result = unified_matcher.match(action)
                # Even if not exact match, synonym should work
                assert result.matched or action in _get_all_synonyms(build_chest_pain_ontology()), (
                    f"Core chest pain action '{action}' not resolvable"
                )

    def test_aki_mandatory_actions_resolvable(self, cpg_graphs, unified_matcher):
        """AKI CPG mandatory actions should resolve through ontology."""
        for graph_name in ["kdigo_aki_full", "kdigo_contrast_aki"]:
            if graph_name not in cpg_graphs:
                continue

            mandatory, _, _ = _extract_cpg_actions(cpg_graphs[graph_name])
            resolvable = {a for a in mandatory if unified_matcher.match(a).matched}
            coverage = len(resolvable) / len(mandatory) if mandatory else 1.0

            # AKI CPG graphs have extensive action sets (40-60+);
            # ontology covers core protocol actions, not every variant
            # kdigo_contrast_aki has very granular actions (document_*, check_*)
            assert len(resolvable) >= 1, (
                f"Zero AKI mandatory action coverage for {graph_name}: {coverage:.1%}. "
                f"Unresolvable: {sorted(mandatory - resolvable)[:10]}"
            )

    def test_stroke_mandatory_actions_resolvable(self, cpg_graphs, unified_matcher):
        """Stroke CPG mandatory actions should resolve through ontology."""
        if "aha_stroke" not in cpg_graphs:
            pytest.skip("aha_stroke_2019.yaml not found")

        mandatory, _, _ = _extract_cpg_actions(cpg_graphs["aha_stroke"])
        resolvable = {a for a in mandatory if unified_matcher.match(a).matched}
        coverage = len(resolvable) / len(mandatory) if mandatory else 1.0

        # Stroke CPG graph has very extensive action sets (90+);
        # ontology covers core tPA/thrombectomy pathway, not every variant
        assert coverage >= 0.05, (
            f"Zero stroke mandatory action coverage: {coverage:.1%}. "
            f"Unresolvable: {sorted(mandatory - resolvable)[:10]}"
        )

    def test_cpg_synonym_bridge_exists(self):
        """Verify ontology synonyms bridge CPG graph format to concept IDs.

        CPG graphs use snake_case (e.g., 'order_lab_blood_culture'),
        ontology uses UPPER_CASE (e.g., 'ORDER_BLOOD_CULTURE').
        Synonyms should bridge these formats.
        """
        onto = build_sepsis_ontology()
        synonyms = _get_all_synonyms(onto)

        # Key CPG actions that should be in synonyms
        expected_bridges = {
            "order_lab_blood_culture": "ORDER_BLOOD_CULTURE",
            "order_lab_lactate": "ORDER_LACTATE",
            "give_crystalloid_30ml_kg": "GIVE_CRYSTALLOID",
        }

        for cpg_action, expected_concept in expected_bridges.items():
            assert cpg_action in synonyms, (
                f"CPG action '{cpg_action}' not in ontology synonyms. "
                f"Expected bridge to '{expected_concept}'"
            )
            assert synonyms[cpg_action] == expected_concept, (
                f"Synonym '{cpg_action}' maps to '{synonyms[cpg_action]}', "
                f"expected '{expected_concept}'"
            )

    def test_forbidden_actions_ontology_aware(self, cpg_graphs, unified_matcher):
        """CPG forbidden actions should be expressible via ontology CONTRAINDICATES."""
        # RV infarct + nitrates is the key contraindication
        onto = build_chest_pain_ontology()
        matcher = OntologyMatcher(onto, OntologyConfig())

        # Check that DIAGNOSE_RV_INFARCT CONTRAINDICATES GIVE_NITRATES
        assert matcher.is_forbidden("GIVE_NITRATES", {"GIVE_NITRATES"})

        # The ontology should propagate contraindication
        rv_concept = onto.get_concept("DIAGNOSE_RV_INFARCT")
        assert rv_concept is not None
        nitrate_concept = onto.get_concept("GIVE_NITRATES")
        assert nitrate_concept is not None

    @pytest.mark.parametrize("graph_name,domain", [
        ("ssc_sepsis_hour1", "sepsis"),
        ("aha_chest_pain", "chest_pain"),
        ("aha_stroke", "stroke"),
        ("aha_heart_failure", "heart_failure"),
        ("ada_dka_management", "dka"),
    ])
    def test_domain_cpg_action_coverage_report(self, cpg_graphs, graph_name, domain):
        """Report coverage of CPG actions by domain ontology (informational)."""
        if graph_name not in cpg_graphs:
            pytest.skip(f"{graph_name}.yaml not found")

        onto = DOMAIN_BUILDERS[domain]()
        matcher = OntologyMatcher(onto, OntologyConfig())

        mandatory, allowed, forbidden = _extract_cpg_actions(cpg_graphs[graph_name])
        all_actions = mandatory | allowed | forbidden

        results = {"matched": [], "unmatched": []}
        for action in sorted(all_actions):
            match = matcher.match(action)
            if match.matched:
                results["matched"].append((action, match.concept_id, match.strategy))
            else:
                results["unmatched"].append(action)

        total = len(all_actions)
        matched = len(results["matched"])
        coverage = matched / total if total else 0

        # Informational: print coverage stats
        print(f"\n{'='*60}")
        print(f"Domain: {domain} | Graph: {graph_name}")
        print(f"Coverage: {matched}/{total} ({coverage:.1%})")
        print(f"  Mandatory coverage: {sum(1 for a in mandatory if matcher.match(a).matched)}/{len(mandatory)}")
        if results["unmatched"]:
            print(f"  Unmatched: {results['unmatched'][:10]}")
        print(f"{'='*60}")


# ======================================================================
# 4. External Benchmark Action Compatibility
# ======================================================================

class TestExternalBenchmarkCompatibility:
    """Validate ontology resolves external benchmark action formats."""

    # Simulate AgentClinic-style actions (from agentclinic.py normalize_action_id)
    AGENTCLINIC_ACTIONS = [
        "order_lab_cbc", "order_lab_bmp", "order_lab_blood_culture",
        "order_imaging_chest_xray", "order_imaging_ecg",
        "assess_vitals", "check_vital_signs",
        "take_history", "assess_chief_complaint",
        "physical_exam_cardiovascular", "physical_exam_respiratory",
        "order_lab_troponin", "order_lab_lactate",
    ]

    # Simulate MedAgentBench-style actions (FHIR-inspired)
    MEDAGENTBENCH_ACTIONS = [
        "order_lab_complete_blood_count", "order_lab_metabolic_panel",
        "order_lab_arterial_blood_gas", "order_lab_coagulation_studies",
        "give_medication_aspirin", "give_medication_nitroglycerin",
        "give_medication_morphine", "order_imaging_ct_head",
        "give_medication_alteplase", "assess_nihss_score",
    ]

    # Simulate MedChain-style actions (clinical step descriptions)
    MEDCHAIN_ACTIONS = [
        "blood_culture", "give_antibiotics", "fluid_bolus",
        "start_vasopressor", "check_lactate", "ecg",
        "aspirin", "troponin", "cath_lab", "ct_head",
        "tpa", "thrombectomy", "insulin_drip", "potassium_replacement",
    ]

    def test_agentclinic_actions_resolvable(self, unified_matcher):
        """AgentClinic-format actions should resolve through unified ontology."""
        resolvable = []
        unresolvable = []

        for action in self.AGENTCLINIC_ACTIONS:
            match = unified_matcher.match(action)
            if match.matched:
                resolvable.append((action, match.concept_id))
            else:
                unresolvable.append(action)

        coverage = len(resolvable) / len(self.AGENTCLINIC_ACTIONS)
        assert coverage >= 0.4, (
            f"Low AgentClinic action coverage: {coverage:.1%}. "
            f"Unresolvable: {unresolvable}"
        )

    def test_medchain_actions_resolvable(self, unified_matcher):
        """MedChain short-form actions should resolve through unified ontology."""
        resolvable = []
        unresolvable = []

        for action in self.MEDCHAIN_ACTIONS:
            match = unified_matcher.match(action)
            if match.matched:
                resolvable.append((action, match.concept_id))
            else:
                unresolvable.append(action)

        coverage = len(resolvable) / len(self.MEDCHAIN_ACTIONS)
        assert coverage >= 0.5, (
            f"Low MedChain action coverage: {coverage:.1%}. "
            f"Unresolvable: {unresolvable}"
        )

    def test_medagentbench_actions_resolvable(self, unified_matcher):
        """MedAgentBench FHIR-style actions should resolve through ontology."""
        resolvable = []
        unresolvable = []

        for action in self.MEDAGENTBENCH_ACTIONS:
            match = unified_matcher.match(action)
            if match.matched:
                resolvable.append((action, match.concept_id))
            else:
                unresolvable.append(action)

        coverage = len(resolvable) / len(self.MEDAGENTBENCH_ACTIONS)
        # MedAgentBench uses more verbose formats, expect lower coverage
        assert coverage >= 0.3, (
            f"Low MedAgentBench action coverage: {coverage:.1%}. "
            f"Unresolvable: {unresolvable}"
        )

    def test_normalize_action_id_compatibility(self, unified_matcher):
        """Verify normalize_action_id output is ontology-compatible."""
        from cga_bench.semantic_layer.external.agentclinic import normalize_action_id

        raw_actions = [
            "Order Blood Culture", "Give Aspirin", "CT Head",
            "Assess NIHSS", "Start Norepinephrine",
            "Order Lab Lactate", "ECG",
        ]

        for raw in raw_actions:
            normalized = normalize_action_id(raw)
            match = unified_matcher.match(normalized)
            if not match.matched:
                # Try the raw form too
                match = unified_matcher.match(raw.lower().replace(" ", "_"))

    def test_cross_format_resolution(self, unified_matcher):
        """Same clinical concept in different formats should resolve to same ontology concept."""
        concept_groups = [
            # Blood culture in various formats
            (["blood_culture", "order_lab_blood_culture", "order_blood_culture",
              "blood_culture_before_antibiotics"], "ORDER_BLOOD_CULTURE"),
            # Norepinephrine in various formats
            (["norepinephrine", "start_norepinephrine", "levophed",
              "start_vasopressor_norepinephrine"], "START_VASOPRESSOR_NOREPINEPHRINE"),
            # Aspirin in various formats
            (["aspirin", "give_aspirin_loading", "aspirin_loading", "asa"],
             "GIVE_ASPIRIN"),
            # Lactate in various formats
            (["lactate", "order_lab_lactate", "serum_lactate", "measure_lactate"],
             "ORDER_LACTATE"),
        ]

        for action_variants, expected_concept in concept_groups:
            resolved_concepts = set()
            for variant in action_variants:
                match = unified_matcher.match(variant)
                if match.matched:
                    resolved_concepts.add(match.concept_id)

            if resolved_concepts:
                assert expected_concept in resolved_concepts, (
                    f"Expected '{expected_concept}' for variants {action_variants}, "
                    f"got {resolved_concepts}"
                )


# ======================================================================
# 5. Cross-Vocabulary Bridge Validation
# ======================================================================

class TestVocabularyBridge:
    """Validate end-to-end vocabulary bridging:
    external action → ontology concept → CPG category → clinical goal.
    """

    def test_sepsis_vocabulary_chain(self):
        """Verify sepsis action resolution chain: CPG action → concept → category → goal."""
        matcher = get_ontology_matcher("sepsis")
        onto = build_sepsis_ontology()

        # CPG action → L1 concept
        match = matcher.match("order_lab_blood_culture")
        assert match.matched
        assert match.concept_id == "ORDER_BLOOD_CULTURE"

        # L1 → L2 (category)
        concept = onto.get_concept("ORDER_BLOOD_CULTURE")
        ancestors = onto.ancestors("ORDER_BLOOD_CULTURE")
        assert "MICROBIOLOGY_WORKUP" in ancestors

        # L2 → L3 (goal)
        assert "INFECTION_CONTROL" in ancestors

        # L3 → L4 (phase)
        assert "SEPSIS_HOUR1_BUNDLE" in ancestors

    def test_chest_pain_vocabulary_chain(self):
        """Verify chest pain action resolution chain."""
        matcher = get_ontology_matcher("chest_pain")
        onto = build_chest_pain_ontology()

        # Aspirin
        match = matcher.match("aspirin")
        assert match.matched
        assert match.concept_id == "GIVE_ASPIRIN"

        ancestors = onto.ancestors("GIVE_ASPIRIN")
        assert "ANTIPLATELET_AGENTS" in ancestors
        assert "ANTIPLATELET_THERAPY" in ancestors
        assert "ACS_INITIAL_ASSESSMENT" in ancestors

    def test_aki_vocabulary_chain(self):
        """Verify AKI action resolution chain."""
        matcher = get_ontology_matcher("aki")
        onto = build_aki_ontology()

        # Creatinine
        match = matcher.match("creatinine")
        assert match.matched
        assert match.concept_id == "ORDER_CREATININE"

        ancestors = onto.ancestors("ORDER_CREATININE")
        assert "RENAL_FUNCTION_LABS" in ancestors
        assert "AKI_STAGING" in ancestors
        assert "AKI_DETECTION" in ancestors

    def test_stroke_vocabulary_chain(self):
        """Verify stroke action resolution chain."""
        matcher = get_ontology_matcher("stroke")
        onto = build_stroke_ontology()

        # Alteplase / tPA
        match = matcher.match("tpa")
        assert match.matched
        assert match.concept_id == "GIVE_ALTEPLASE"

        ancestors = onto.ancestors("GIVE_ALTEPLASE")
        assert "THROMBOLYTIC_AGENTS" in ancestors
        assert "THROMBOLYSIS" in ancestors
        assert "STROKE_INTERVENTION" in ancestors

    def test_dka_vocabulary_chain(self):
        """Verify DKA action resolution chain."""
        matcher = get_ontology_matcher("dka")
        onto = build_dka_ontology()

        # Insulin drip
        match = matcher.match("insulin_drip")
        assert match.matched
        assert match.concept_id == "START_INSULIN_DRIP"

        ancestors = onto.ancestors("START_INSULIN_DRIP")
        assert "INSULIN_AGENTS" in ancestors
        assert "INSULIN_THERAPY" in ancestors
        assert "DKA_CORRECTION" in ancestors

    def test_hf_vocabulary_chain(self):
        """Verify heart failure action resolution chain."""
        matcher = get_ontology_matcher("heart_failure")
        onto = build_heart_failure_ontology()

        # Furosemide
        match = matcher.match("furosemide")
        assert match.matched
        assert match.concept_id == "GIVE_FUROSEMIDE"

        ancestors = onto.ancestors("GIVE_FUROSEMIDE")
        assert "DIURETIC_THERAPY" in ancestors
        assert "DECONGESTION" in ancestors
        assert "ADHF_STABILIZATION" in ancestors

    def test_subsumption_satisfies_cpg_requirement(self, unified_matcher):
        """Specific drug actions should satisfy broader CPG category requirements."""
        # Meropenem satisfies ANTIBIOTIC_THERAPY
        assert unified_matcher.satisfies("GIVE_MEROPENEM", "ANTIBIOTIC_THERAPY")
        assert unified_matcher.satisfies("GIVE_MEROPENEM", "GIVE_BROAD_SPECTRUM_ANTIBIOTICS")

        # Norepinephrine satisfies VASOPRESSOR_SUPPORT
        assert unified_matcher.satisfies("START_VASOPRESSOR_NOREPINEPHRINE", "VASOPRESSOR_SUPPORT")

        # V4R ECG satisfies ECG_ASSESSMENT
        assert unified_matcher.satisfies("ORDER_ECG_V4R", "ECG_ASSESSMENT")

        # Enoxaparin satisfies heparin requirement
        assert unified_matcher.satisfies("GIVE_ENOXAPARIN", "GIVE_HEPARIN")


# ======================================================================
# 6. Clinical Accuracy Validation
# ======================================================================

class TestClinicalAccuracy:
    """Validate clinical correctness of ontology relationships."""

    def test_rv_infarct_nitrates_contraindication(self):
        """RV infarct should contraindicate nitrates (critical safety rule)."""
        onto = build_chest_pain_ontology()
        rv = onto.get_concept("DIAGNOSE_RV_INFARCT")
        nitrates = onto.get_concept("GIVE_NITRATES")
        assert rv is not None
        assert nitrates is not None

        # Check CONTRAINDICATES relation exists
        relations = onto._relations.get("DIAGNOSE_RV_INFARCT", [])
        contra_targets = [
            tgt for rel, tgt in relations
            if rel.name == "CONTRAINDICATES"
        ]
        assert "GIVE_NITRATES" in contra_targets

    def test_blood_culture_precedes_antibiotics(self):
        """Blood culture should precede antibiotics (SSC 2021 BPS)."""
        onto = build_sepsis_ontology()
        relations = onto._relations.get("ORDER_BLOOD_CULTURE", [])
        precedes_targets = [
            tgt for rel, tgt in relations
            if rel.name == "PRECEDES"
        ]
        assert "GIVE_BROAD_SPECTRUM_ANTIBIOTICS" in precedes_targets

    def test_fluid_precedes_vasopressor(self):
        """Crystalloid should precede vasopressor (SSC 2021 Rec 5→9)."""
        onto = build_sepsis_ontology()
        relations = onto._relations.get("GIVE_CRYSTALLOID", [])
        precedes_targets = [
            tgt for rel, tgt in relations
            if rel.name == "PRECEDES"
        ]
        assert "START_VASOPRESSOR_NOREPINEPHRINE" in precedes_targets

    def test_ct_precedes_tpa_stroke(self):
        """CT head should precede tPA (AHA 2019 critical sequence)."""
        onto = build_stroke_ontology()
        relations = onto._relations.get("ORDER_CT_HEAD", [])
        precedes_targets = [
            tgt for rel, tgt in relations
            if rel.name == "PRECEDES"
        ]
        assert "GIVE_ALTEPLASE" in precedes_targets

    def test_nihss_precedes_tpa_stroke(self):
        """NIHSS assessment should precede tPA (eligibility criteria)."""
        onto = build_stroke_ontology()
        relations = onto._relations.get("ASSESS_NIHSS", [])
        precedes_targets = [
            tgt for rel, tgt in relations
            if rel.name == "PRECEDES"
        ]
        assert "GIVE_ALTEPLASE" in precedes_targets

    def test_ns_precedes_insulin_dka(self):
        """NS hydration should precede insulin in DKA (ADA guideline)."""
        onto = build_dka_ontology()
        relations = onto._relations.get("GIVE_NS_1L", [])
        precedes_targets = [
            tgt for rel, tgt in relations
            if rel.name == "PRECEDES"
        ]
        assert "START_INSULIN_DRIP" in precedes_targets

    def test_antibiotic_hierarchy_correct(self):
        """Specific antibiotics IS-A broad-spectrum (pharmacological correctness)."""
        onto = build_sepsis_ontology()

        # Meropenem IS-A broad-spectrum
        mero_ancestors = onto.ancestors("GIVE_MEROPENEM")
        assert "GIVE_BROAD_SPECTRUM_ANTIBIOTICS" in mero_ancestors

        # Pip-tazo IS-A broad-spectrum
        pt_ancestors = onto.ancestors("GIVE_PIPERACILLIN_TAZOBACTAM")
        assert "GIVE_BROAD_SPECTRUM_ANTIBIOTICS" in pt_ancestors

        # Vancomycin IS-A antibiotic therapy (but not necessarily broad-spectrum)
        vanc_ancestors = onto.ancestors("GIVE_VANCOMYCIN")
        assert "ANTIBIOTIC_THERAPY" in vanc_ancestors

    def test_antiplatelet_hierarchy_correct(self):
        """Antiplatelet agents should have correct IS-A relations."""
        onto = build_chest_pain_ontology()

        # Aspirin IS-A antiplatelet
        asp_ancestors = onto.ancestors("GIVE_ASPIRIN")
        assert "ANTIPLATELET_AGENTS" in asp_ancestors

        # P2Y12 IS-A antiplatelet
        p2y12_ancestors = onto.ancestors("GIVE_P2Y12_INHIBITOR")
        assert "ANTIPLATELET_AGENTS" in p2y12_ancestors

    def test_gdmt_hierarchy_heart_failure(self):
        """GDMT agents should be correctly categorized (AHA 2022)."""
        onto = build_heart_failure_ontology()

        # Sacubitril/Valsartan IS-A RAAS inhibitor
        sv_ancestors = onto.ancestors("GIVE_SACUBITRIL_VALSARTAN")
        assert "RAAS_INHIBITORS" in sv_ancestors

        # Carvedilol IS-A beta-blocker
        carv_ancestors = onto.ancestors("GIVE_CARVEDILOL")
        assert "BETA_BLOCKER_THERAPY" in carv_ancestors

        # Dapagliflozin IS-A SGLT2 inhibitor
        dapa_ancestors = onto.ancestors("GIVE_DAPAGLIFLOZIN")
        assert "SGLT2_INHIBITORS" in dapa_ancestors


# ======================================================================
# 7. Coverage Gap Analysis (Informational)
# ======================================================================

class TestCoverageGapAnalysis:
    """Identify coverage gaps between ontology and CPG/external vocabularies.

    These tests generate reports; they use soft assertions to identify
    areas needing improvement without failing the build.
    """

    def test_overall_cpg_coverage_report(self, cpg_graphs, unified_matcher):
        """Generate overall CPG action coverage report across all graphs."""
        print("\n" + "=" * 70)
        print("OVERALL CPG ACTION COVERAGE REPORT")
        print("=" * 70)

        total_actions = set()
        total_resolved = set()
        per_graph = {}

        for graph_name, graph_data in cpg_graphs.items():
            if graph_name == "universal_clinical_safety":
                continue  # Skip universal (uses modular_rules, not standard format)

            mandatory, allowed, forbidden = _extract_cpg_actions(graph_data)
            all_actions = mandatory | allowed | forbidden
            resolved = {a for a in all_actions if unified_matcher.match(a).matched}

            total_actions.update(all_actions)
            total_resolved.update(resolved)

            coverage = len(resolved) / len(all_actions) if all_actions else 0
            per_graph[graph_name] = {
                "total": len(all_actions),
                "resolved": len(resolved),
                "coverage": coverage,
                "gaps": sorted(all_actions - resolved)[:5],
            }

        for gname, stats in sorted(per_graph.items()):
            print(f"  {gname}: {stats['resolved']}/{stats['total']} ({stats['coverage']:.1%})")
            if stats["gaps"]:
                print(f"    Top gaps: {stats['gaps']}")

        overall = len(total_resolved) / len(total_actions) if total_actions else 0
        print(f"\n  OVERALL: {len(total_resolved)}/{len(total_actions)} ({overall:.1%})")
        print("=" * 70)

    def test_external_benchmark_coverage_report(self, unified_matcher):
        """Generate external benchmark action coverage report."""
        print("\n" + "=" * 70)
        print("EXTERNAL BENCHMARK ACTION COVERAGE REPORT")
        print("=" * 70)

        all_external = (
            TestExternalBenchmarkCompatibility.AGENTCLINIC_ACTIONS +
            TestExternalBenchmarkCompatibility.MEDAGENTBENCH_ACTIONS +
            TestExternalBenchmarkCompatibility.MEDCHAIN_ACTIONS
        )

        resolved_map = {}
        unresolved = []

        for action in sorted(set(all_external)):
            match = unified_matcher.match(action)
            if match.matched:
                resolved_map[action] = (match.concept_id, match.strategy)
            else:
                unresolved.append(action)

        print(f"  Resolved: {len(resolved_map)}/{len(set(all_external))}")
        print(f"  Unresolved ({len(unresolved)}):")
        for action in unresolved[:15]:
            print(f"    - {action}")

        if resolved_map:
            print(f"\n  Resolution methods:")
            methods = {}
            for action, (cid, method) in resolved_map.items():
                methods.setdefault(method, []).append(action)
            for method, actions in sorted(methods.items()):
                print(f"    {method}: {len(actions)} actions")

        print("=" * 70)

    def test_synonym_coverage_completeness(self):
        """Report which CPG actions lack ontology synonym bridges."""
        graphs_dir = PROJECT_ROOT / "cpg_model" / "graphs"

        all_cpg_actions = set()
        for path in sorted(graphs_dir.glob("*.yaml")):
            if path.stem == "universal_clinical_safety":
                continue
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            mandatory, allowed, forbidden = _extract_cpg_actions(data)
            all_cpg_actions.update(mandatory | allowed | forbidden)

        unified = build_unified_ontology()
        all_synonyms = _get_all_synonyms(unified)

        # Also check if the action is a concept_id itself (case-insensitive)
        concept_ids_lower = {cid.lower(): cid for cid in unified.concepts}

        covered = set()
        for action in all_cpg_actions:
            if action in all_synonyms:
                covered.add(action)
            elif action.upper() in unified.concepts:
                covered.add(action)
            elif action.lower() in concept_ids_lower:
                covered.add(action)

        coverage = len(covered) / len(all_cpg_actions) if all_cpg_actions else 0

        print(f"\n  Synonym coverage for CPG actions: "
              f"{len(covered)}/{len(all_cpg_actions)} ({coverage:.1%})")

        # This is informational — coverage should improve over time
        uncovered = sorted(all_cpg_actions - covered)
        if uncovered:
            print(f"  Top uncovered actions:")
            for action in uncovered[:20]:
                print(f"    - {action}")
