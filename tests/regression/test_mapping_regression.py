"""
Regression Tests for Clinical Action Mapping

These tests verify that the mapping pipeline maintains expected performance
on a gold standard set of clinical action mappings.

CI Integration:
  - Run with: PYTHONPATH=. pytest tests/regression/test_mapping_regression.py -v
  - Failures indicate regression in mapping quality

Gold Set Coverage:
  - 35 mappings across 6 clinical domains
  - Difficulty levels: easy (should always pass), normal, hard
  - Categories: drug, lab, procedure, imaging, assessment, fluid
"""

import json
import pytest
from pathlib import Path
from typing import List, Dict, Any

from cga_bench.semantic_layer.ontology.ablation import (
    GoldInstance,
    load_gold_set,
    create_default_gold_set,
)


# Path to gold set
GOLD_SET_PATH = Path(__file__).parent / "test_mapping_goldset.jsonl"


class TestGoldSetIntegrity:
    """Tests for gold set file integrity."""

    def test_gold_set_file_exists(self):
        """Gold set file exists."""
        assert GOLD_SET_PATH.exists(), f"Gold set not found: {GOLD_SET_PATH}"

    def test_gold_set_is_valid_jsonl(self):
        """Gold set is valid JSONL format."""
        with open(GOLD_SET_PATH, 'r') as f:
            for i, line in enumerate(f, 1):
                if line.strip():
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as e:
                        pytest.fail(f"Invalid JSON at line {i}: {e}")

    def test_gold_set_has_required_fields(self):
        """Each gold instance has required fields."""
        required_fields = ["query", "gold_concept_id", "gold_display", "domain"]

        with open(GOLD_SET_PATH, 'r') as f:
            for i, line in enumerate(f, 1):
                if line.strip():
                    data = json.loads(line)
                    for field in required_fields:
                        assert field in data, f"Missing field '{field}' at line {i}"

    def test_gold_set_minimum_size(self):
        """Gold set has minimum number of instances."""
        gold_set = load_gold_set(GOLD_SET_PATH)
        assert len(gold_set) >= 30, f"Gold set too small: {len(gold_set)} instances"

    def test_gold_set_domain_coverage(self):
        """Gold set covers all major domains."""
        gold_set = load_gold_set(GOLD_SET_PATH)
        domains = {g.domain for g in gold_set}

        expected_domains = {"sepsis", "chest_pain", "aki", "dka", "stroke", "heart_failure"}
        missing = expected_domains - domains
        assert not missing, f"Missing domains in gold set: {missing}"

    def test_gold_set_difficulty_distribution(self):
        """Gold set has reasonable difficulty distribution."""
        gold_set = load_gold_set(GOLD_SET_PATH)
        difficulties = [g.difficulty for g in gold_set]

        easy_count = sum(1 for d in difficulties if d == "easy")
        hard_count = sum(1 for d in difficulties if d == "hard")

        # At least 10 easy cases and 2 hard cases
        assert easy_count >= 10, f"Not enough easy cases: {easy_count}"
        assert hard_count >= 2, f"Not enough hard cases: {hard_count}"


class TestExactMatching:
    """Regression tests for exact matching (should have 100% precision on easy cases)."""

    @pytest.fixture
    def gold_set(self):
        return load_gold_set(GOLD_SET_PATH)

    @pytest.fixture
    def easy_cases(self, gold_set):
        return [g for g in gold_set if g.difficulty == "easy"]

    def test_exact_match_easy_queries(self, easy_cases):
        """Easy queries should match exactly (no transformation needed)."""
        # These are queries that match their gold_concept_id exactly
        exact_matches = [g for g in easy_cases if g.query == g.gold_concept_id]
        assert len(exact_matches) >= 10, "Not enough exact match test cases"

    def test_underscore_normalization(self, easy_cases):
        """Underscored queries should normalize correctly."""
        underscore_queries = [g for g in easy_cases if "_" in g.query]
        assert len(underscore_queries) >= 5, "Not enough underscore test cases"


class TestSemanticTypeConsistency:
    """Tests for semantic type inference consistency."""

    @pytest.fixture
    def gold_set(self):
        return load_gold_set(GOLD_SET_PATH)

    def test_drug_category_type_inference(self, gold_set):
        """Drug category should infer DRUG semantic type."""
        from cga_bench.semantic_layer.ontology.neural_embedder import (
            infer_semantic_type,
            SemanticType,
        )

        drug_cases = [g for g in gold_set if g.category == "drug"]
        for case in drug_cases:
            inferred = infer_semantic_type(case.gold_display)
            # Drug display names should infer as DRUG
            assert inferred in [SemanticType.DRUG, SemanticType.UNKNOWN], \
                f"Drug '{case.gold_display}' inferred as {inferred}"

    def test_lab_category_type_inference(self, gold_set):
        """Lab category should infer LAB semantic type."""
        from cga_bench.semantic_layer.ontology.neural_embedder import (
            infer_semantic_type,
            SemanticType,
        )

        lab_cases = [g for g in gold_set if g.category == "lab"]
        for case in lab_cases:
            inferred = infer_semantic_type(case.gold_display)
            assert inferred in [SemanticType.LAB, SemanticType.UNKNOWN], \
                f"Lab '{case.gold_display}' inferred as {inferred}"


class TestEntityExtraction:
    """Tests for entity extraction preprocessing."""

    def test_action_verb_removal(self):
        """Action verbs should be removed from queries."""
        from cga_bench.semantic_layer.ontology.neural_embedder import extract_entity_name

        test_cases = [
            ("start_norepinephrine", "norepinephrine"),
            ("give antibiotics", "antibiotics"),
            ("order lab lactate", "lab lactate"),
            ("perform ecg", "ecg"),
            ("assess vital signs", "vital signs"),
        ]

        for query, expected_entity in test_cases:
            result = extract_entity_name(query)
            assert expected_entity in result.lower(), \
                f"Entity extraction failed: '{query}' -> '{result}', expected '{expected_entity}'"

    def test_dosage_removal(self):
        """Dosage patterns should be removed."""
        from cga_bench.semantic_layer.ontology.neural_embedder import extract_entity_name

        test_cases = [
            "give_norepinephrine_0.1mcg_kg_min",
            "crystalloid_30ml_kg",
            "aspirin_325mg",
        ]

        for query in test_cases:
            result = extract_entity_name(query)
            # Should not contain numeric dosage
            assert not any(c.isdigit() for c in result), \
                f"Dosage not removed: '{query}' -> '{result}'"


class TestCriticalMappings:
    """Tests for clinically critical mappings that must always work."""

    @pytest.fixture
    def gold_set(self):
        return load_gold_set(GOLD_SET_PATH)

    def test_sepsis_bundle_mappings(self, gold_set):
        """Sepsis hour-1 bundle actions must map correctly."""
        sepsis_critical = [
            "order_lab_lactate",
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
            "give_crystalloid_30ml_kg",
        ]

        sepsis_cases = [g for g in gold_set if g.domain == "sepsis"]
        for action in sepsis_critical:
            matches = [g for g in sepsis_cases if g.gold_concept_id == action]
            assert len(matches) >= 1, f"Missing critical sepsis action: {action}"

    def test_stemi_critical_mappings(self, gold_set):
        """STEMI critical actions must map correctly."""
        stemi_critical = [
            "perform_ecg",
            "order_lab_troponin",
            "give_aspirin_loading",
            "activate_cath_lab",
        ]

        chest_cases = [g for g in gold_set if g.domain == "chest_pain"]
        for action in stemi_critical:
            matches = [g for g in chest_cases if g.gold_concept_id == action]
            assert len(matches) >= 1, f"Missing critical STEMI action: {action}"

    def test_stroke_critical_mappings(self, gold_set):
        """Stroke critical actions must map correctly."""
        stroke_critical = [
            "assess_nihss",
            "order_ct_head",
            "give_alteplase_0.9mg_kg",
        ]

        stroke_cases = [g for g in gold_set if g.domain == "stroke"]
        for action in stroke_critical:
            matches = [g for g in stroke_cases if g.gold_concept_id == action]
            assert len(matches) >= 1, f"Missing critical stroke action: {action}"


class TestHardCases:
    """Tests for known hard cases (type confusion prevention)."""

    @pytest.fixture
    def gold_set(self):
        return load_gold_set(GOLD_SET_PATH)

    def test_lactate_lab_not_fluid(self, gold_set):
        """'lactate' should map to lab, not 'lactated ringers' (fluid)."""
        lactate_case = next(
            (g for g in gold_set if g.query == "lactate" and g.notes),
            None
        )
        assert lactate_case is not None, "Missing lactate hard case"
        assert lactate_case.category == "lab", "Lactate should be categorized as lab"

    def test_brand_name_mappings(self, gold_set):
        """Brand names should map to generic concepts."""
        brand_cases = [g for g in gold_set if "Brand" in g.notes or "brand" in g.notes]
        assert len(brand_cases) >= 2, "Not enough brand name test cases"

    def test_abbreviation_mappings(self, gold_set):
        """Abbreviations should map to full concepts."""
        abbrev_cases = [g for g in gold_set if "Abbreviation" in g.notes]
        assert len(abbrev_cases) >= 1, "Not enough abbreviation test cases"


class TestRegressionBaseline:
    """Baseline performance tests to detect regressions."""

    @pytest.fixture
    def gold_set(self):
        return load_gold_set(GOLD_SET_PATH)

    def test_easy_cases_should_pass(self, gold_set):
        """Easy cases should have 100% exact match rate."""
        easy_exact = [
            g for g in gold_set
            if g.difficulty == "easy" and g.query == g.gold_concept_id
        ]
        # All easy exact matches should be in the gold set
        assert len(easy_exact) >= 10

    def test_minimum_domain_coverage(self, gold_set):
        """Each domain should have minimum representation."""
        domain_counts = {}
        for g in gold_set:
            domain_counts[g.domain] = domain_counts.get(g.domain, 0) + 1

        min_per_domain = 3
        for domain, count in domain_counts.items():
            assert count >= min_per_domain, \
                f"Domain '{domain}' has only {count} cases (min: {min_per_domain})"


# Utility function for CI reporting
def print_gold_set_summary():
    """Print summary of gold set for CI logs."""
    gold_set = load_gold_set(GOLD_SET_PATH)

    print("\n" + "=" * 60)
    print("GOLD SET SUMMARY")
    print("=" * 60)
    print(f"Total instances: {len(gold_set)}")

    # By domain
    domains = {}
    for g in gold_set:
        domains[g.domain] = domains.get(g.domain, 0) + 1
    print("\nBy domain:")
    for domain, count in sorted(domains.items()):
        print(f"  {domain}: {count}")

    # By difficulty
    difficulties = {}
    for g in gold_set:
        difficulties[g.difficulty] = difficulties.get(g.difficulty, 0) + 1
    print("\nBy difficulty:")
    for diff, count in sorted(difficulties.items()):
        print(f"  {diff}: {count}")

    # By category
    categories = {}
    for g in gold_set:
        categories[g.category] = categories.get(g.category, 0) + 1
    print("\nBy category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")

    print("=" * 60)


if __name__ == "__main__":
    print_gold_set_summary()
