"""Tests for AMEGA loader and DOMAIN_CPG_MAP integrity."""

from __future__ import annotations

from pathlib import Path

import pytest

# Module under test
from cga_bench.run_external_benchmark import (
    AMEGA_CRITERIA_ACTION_MAP,
    AMEGA_DOMAIN_MAP,
    DOMAIN_CPG_MAP,
    load_amega_scenarios,
)

CPG_GRAPHS_DIR = Path(__file__).resolve().parent.parent.parent / "cpg_model" / "graphs"


# ---------------------------------------------------------------------------
# DOMAIN_CPG_MAP regression tests
# ---------------------------------------------------------------------------


class TestDomainCPGMap:
    """Verify all DOMAIN_CPG_MAP entries point to existing graph files."""

    def test_all_files_exist(self) -> None:
        """Every DOMAIN_CPG_MAP value must correspond to an existing YAML file."""
        missing = []
        for domain, fname in DOMAIN_CPG_MAP.items():
            path = CPG_GRAPHS_DIR / fname
            if not path.exists():
                missing.append(f"{domain}: {fname}")
        assert not missing, f"Missing CPG graph files: {missing}"

    def test_minimum_domain_count(self) -> None:
        """DOMAIN_CPG_MAP should have at least 15 domains (was 7 pre-fix)."""
        assert len(DOMAIN_CPG_MAP) >= 15

    def test_required_domains_present(self) -> None:
        """Core domains must be present in the map."""
        required = ["sepsis", "chest_pain", "stroke", "heart_failure", "aki", "dka", "general"]
        for domain in required:
            assert domain in DOMAIN_CPG_MAP, f"Missing required domain: {domain}"

    def test_no_stale_filenames(self) -> None:
        """Regression: ensure the 4 known stale filenames are NOT present."""
        stale = {
            "ssc_sepsis_hour1.yaml",
            "aha_chest_pain.yaml",
            "aha_stroke.yaml",
            "aha_heart_failure.yaml",
        }
        values = set(DOMAIN_CPG_MAP.values())
        overlap = stale & values
        assert not overlap, f"Stale filenames still present: {overlap}"


# ---------------------------------------------------------------------------
# AMEGA loader tests
# ---------------------------------------------------------------------------


class TestLoadAmegaScenarios:
    """Tests for load_amega_scenarios()."""

    @pytest.fixture(scope="class")
    def scenarios(self) -> list:
        """Load scenarios once for the class."""
        return load_amega_scenarios()

    def test_returns_24_cases(self, scenarios: list) -> None:
        """AMEGA dataset has exactly 24 cases."""
        assert len(scenarios) == 24

    def test_scenario_has_required_fields(self, scenarios: list) -> None:
        """Each scenario must have the ExternalScenario required fields."""
        for s in scenarios:
            assert s.scenario_id.startswith("amega_"), f"Bad id: {s.scenario_id}"
            assert s.source_benchmark == "AMEGA"
            assert len(s.description) > 10, f"Description too short for {s.scenario_id}"
            assert s.expected_diagnosis, f"No diagnosis for {s.scenario_id}"
            assert len(s.expected_actions) >= 1, f"No actions for {s.scenario_id}"
            assert s.detected_domain, f"No domain for {s.scenario_id}"

    def test_domain_matched_count(self, scenarios: list) -> None:
        """Exactly 7 cases should be domain-matched."""
        matched = [s for s in scenarios if s.metadata.get("domain_matched")]
        assert len(matched) == 7

    def test_domain_matched_cases_have_specific_domains(self, scenarios: list) -> None:
        """Domain-matched cases should NOT be 'general'."""
        for s in scenarios:
            if s.metadata.get("domain_matched"):
                assert s.detected_domain != "general", f"{s.scenario_id} is domain_matched but has domain='general'"

    def test_unmatched_cases_have_detected_domain(self, scenarios: list) -> None:
        """Non-matched cases should still have a detected domain (possibly 'general')."""
        for s in scenarios:
            assert s.detected_domain is not None and s.detected_domain != ""

    def test_metadata_fields(self, scenarios: list) -> None:
        """Each scenario metadata has expected keys."""
        for s in scenarios:
            assert "case_id" in s.metadata
            assert "guideline_specialty" in s.metadata
            assert "n_questions" in s.metadata
            assert "n_criteria" in s.metadata
            assert s.metadata["n_questions"] > 0
            assert s.metadata["n_criteria"] > 0

    def test_patient_state_has_narrative(self, scenarios: list) -> None:
        """Patient state should contain the full narrative."""
        for s in scenarios:
            assert "narrative" in s.patient_state
            assert len(s.patient_state["narrative"]) > 50

    def test_limit_parameter(self) -> None:
        """Limit parameter restricts number of scenarios."""
        limited = load_amega_scenarios(limit=5)
        assert len(limited) == 5


# ---------------------------------------------------------------------------
# AMEGA domain mapping tests
# ---------------------------------------------------------------------------


class TestAmegaDomainMap:
    """Tests for AMEGA_DOMAIN_MAP correctness."""

    def test_all_mapped_cases_exist(self) -> None:
        """All case_ids in AMEGA_DOMAIN_MAP should exist in the dataset."""
        scenarios = load_amega_scenarios()
        case_ids = {s.metadata["case_id"] for s in scenarios}
        for cid in AMEGA_DOMAIN_MAP:
            assert cid in case_ids, f"Case {cid} not found in AMEGA dataset"

    def test_mapped_domains_in_cpg_map(self) -> None:
        """All domains in AMEGA_DOMAIN_MAP should exist in DOMAIN_CPG_MAP."""
        for domain in AMEGA_DOMAIN_MAP.values():
            assert domain in DOMAIN_CPG_MAP, f"AMEGA domain '{domain}' not in DOMAIN_CPG_MAP"


# ---------------------------------------------------------------------------
# Criteria-to-action mapping tests
# ---------------------------------------------------------------------------


class TestAmegaCriteriaActionMap:
    """Tests for AMEGA_CRITERIA_ACTION_MAP patterns."""

    def test_patterns_compile(self) -> None:
        """All regex patterns should compile without error."""
        import re

        for pattern, _action_id in AMEGA_CRITERIA_ACTION_MAP:
            re.compile(pattern, re.IGNORECASE)

    def test_known_criteria_matches(self) -> None:
        """Verify specific criteria text maps to expected actions."""
        from cga_bench.run_external_benchmark import _amega_criteria_to_actions

        test_cases = [
            (["ECG should be performed"], ["order_ecg"]),
            (["Order troponin levels"], ["order_lab_troponin"]),
            (["CT scan of the head"], ["order_imaging_ct_head"]),
            (["chest X-ray or CXR"], ["order_imaging_chest_xray"]),
            (["Administer epinephrine immediately"], ["give_epinephrine"]),
            (["Start broad-spectrum antibiotics"], ["give_broad_spectrum_antibiotics"]),
            (["Perform lumbar puncture"], ["perform_lumbar_puncture"]),
        ]
        for criteria, expected in test_cases:
            result = _amega_criteria_to_actions(criteria)
            for exp_action in expected:
                assert exp_action in result, f"Expected {exp_action} from criteria {criteria}, got {result}"

    def test_minimum_pattern_count(self) -> None:
        """Should have at least 30 patterns for reasonable coverage."""
        assert len(AMEGA_CRITERIA_ACTION_MAP) >= 30
