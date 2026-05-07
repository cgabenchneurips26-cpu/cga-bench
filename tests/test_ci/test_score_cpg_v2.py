"""Tests for scripts/score_cpg_v2.py — CPG Selection Criteria v2 (C1-C12).

All criteria measure properties of the PUBLISHED CPG source document,
NOT YAML encoding properties. This eliminates circular reasoning.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.score_cpg_v2 import (
    classify_tier,
    compute_all_scores,
    compute_axes,
    extract_year,
    load_gbd_table,
    load_graph,
    load_source_properties,
    score_c1,
    score_c2,
    score_c3,
    score_c4,
    score_c5,
    score_c6,
    score_c7,
    score_c8,
    score_c9,
    score_c10,
    score_c11,
    score_c12,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_graph(
    graph_id: str = "test_graph",
    guideline_name: str = "Test Guideline",
    metadata: dict | None = None,
    version: str = "1.0",
) -> dict:
    """Build a minimal CPG graph dict for testing."""
    if metadata is None:
        metadata = {"source": "Test 2021", "doi": "10.1234/test"}
    return {
        "graph_id": graph_id,
        "guideline_name": guideline_name,
        "version": version,
        "metadata": metadata,
        "entry_node": "n1",
        "nodes": {},
    }


def _gbd_fixture() -> dict:
    """Minimal GBD table for testing."""
    return {
        "gbd_top15_death": [],
        "emergency_conditions": [],
        "graph_id_mapping": {
            "test_graph": {
                "gbd_cause": "Test cause",
                "is_emergency": False,
                "gbd_rank_death": 5,
                "m10_score": 2,
            },
            "low_burden": {
                "gbd_cause": "Low burden",
                "is_emergency": False,
                "gbd_rank_death": 25,
                "m10_score": 1,
            },
            "not_ranked": {
                "gbd_cause": "Unknown",
                "is_emergency": False,
                "gbd_rank_death": None,
                "m10_score": 0,
            },
        },
    }


def _props(**overrides: object) -> dict:
    """Build a source-properties dict with optional overrides."""
    base: dict = {
        "c1_tier1_society": True,
        "c2_evidence_system": "GRADE",
        "c2_evidence_system_score": 2,
        "c3_systematic_review": True,
        "c4_recency_year": 2021,
        "c5_has_doi": True,
        "c7_time_to_harm": "critical",
        "c8_contraindication_explicit": 2,
        "c9_score": 2,
        "c9_has_algorithm_figure": True,
        "c9_figure_count": 4,
        "c10_score": 2,
        "c10_time_constraints_explicit": True,
        "c10_time_statements_count": 5,
        "c11_sequence_dependency_explicit": True,
        "c12_conditional_branching_explicit": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# TestYearExtraction (unchanged — still from metadata)
# ---------------------------------------------------------------------------


class TestYearExtraction:
    def test_publication_year_field(self) -> None:
        graph = _minimal_graph(metadata={"publication_year": 2022})
        assert extract_year(graph) == 2022

    def test_primary_source_year(self) -> None:
        graph = _minimal_graph(metadata={"primary_source": {"year": 2019}})
        assert extract_year(graph) == 2019

    def test_version_regex(self) -> None:
        graph = _minimal_graph(metadata={}, version="2021.1")
        assert extract_year(graph) == 2021

    def test_guideline_name_regex(self) -> None:
        graph = _minimal_graph(
            guideline_name="AHA Stroke 2019 Guidelines",
            metadata={},
            version="1.0",
        )
        assert extract_year(graph) == 2019

    def test_source_regex(self) -> None:
        graph = _minimal_graph(metadata={"source": "SSC Guidelines 2021"}, version="1.0")
        assert extract_year(graph) == 2021

    def test_none_fallback(self) -> None:
        graph = _minimal_graph(
            guideline_name="Test Guideline",
            metadata={},
            version="latest",
        )
        assert extract_year(graph) is None


# ---------------------------------------------------------------------------
# TestC1 — Tier-1 society
# ---------------------------------------------------------------------------


class TestC1TierOneSociety:
    def test_from_props(self) -> None:
        graph = _minimal_graph()
        assert score_c1(graph, _props(c1_tier1_society=True)) == 1

    def test_from_props_false(self) -> None:
        graph = _minimal_graph()
        assert score_c1(graph, _props(c1_tier1_society=False)) == 0

    def test_fallback_guideline_name(self) -> None:
        graph = _minimal_graph(guideline_name="AHA Guidelines 2022")
        assert score_c1(graph, None) == 1

    def test_fallback_unknown(self) -> None:
        graph = _minimal_graph(guideline_name="Local Hospital Protocol")
        assert score_c1(graph, None) == 0


# ---------------------------------------------------------------------------
# TestC2 — Evidence grading system
# ---------------------------------------------------------------------------


class TestC2EvidenceSystem:
    def test_grade_full(self) -> None:
        graph = _minimal_graph()
        assert score_c2(graph, _props(c2_evidence_system_score=2)) == 2

    def test_society_specific(self) -> None:
        graph = _minimal_graph()
        assert score_c2(graph, _props(c2_evidence_system_score=1)) == 1

    def test_none(self) -> None:
        graph = _minimal_graph()
        assert score_c2(graph, _props(c2_evidence_system_score=0)) == 0

    def test_fallback_metadata_grade(self) -> None:
        graph = _minimal_graph(metadata={"recommendation_system": "GRADE"})
        assert score_c2(graph, None) == 2

    def test_fallback_no_system(self) -> None:
        graph = _minimal_graph(metadata={})
        assert score_c2(graph, None) == 0

    def test_from_system_name_grade(self) -> None:
        """Props with system name but no pre-computed score."""
        p = {"c2_evidence_system": "GRADE"}
        graph = _minimal_graph()
        assert score_c2(graph, p) == 2

    def test_from_system_name_society(self) -> None:
        p = {"c2_evidence_system": "AHA Class/LOE"}
        graph = _minimal_graph()
        assert score_c2(graph, p) == 1


# ---------------------------------------------------------------------------
# TestC3 — Systematic review
# ---------------------------------------------------------------------------


class TestC3SystematicReview:
    def test_from_props_true(self) -> None:
        graph = _minimal_graph()
        assert score_c3(graph, _props(c3_systematic_review=True)) == 1

    def test_from_props_false(self) -> None:
        graph = _minimal_graph()
        assert score_c3(graph, _props(c3_systematic_review=False)) == 0

    def test_fallback_yaml_metadata(self) -> None:
        graph = _minimal_graph(metadata={"has_systematic_review": True})
        assert score_c3(graph, None) == 1

    def test_fallback_missing(self) -> None:
        graph = _minimal_graph(metadata={})
        assert score_c3(graph, None) == 0


# ---------------------------------------------------------------------------
# TestC4 — Recency
# ---------------------------------------------------------------------------


class TestC4Recency:
    def test_2020_plus(self) -> None:
        graph = _minimal_graph()
        assert score_c4(graph, _props(c4_recency_year=2022)) == 2

    def test_2015_2019(self) -> None:
        graph = _minimal_graph()
        assert score_c4(graph, _props(c4_recency_year=2017)) == 1

    def test_pre_2015(self) -> None:
        graph = _minimal_graph()
        assert score_c4(graph, _props(c4_recency_year=2012)) == 0

    def test_null_year(self) -> None:
        graph = _minimal_graph(metadata={}, version="latest", guideline_name="Test Protocol")
        assert score_c4(graph, _props(c4_recency_year=None, publication_year=None)) == 0

    def test_last_update_year_priority(self) -> None:
        graph = _minimal_graph(metadata={"publication_year": 2012, "last_update_year": 2023})
        assert score_c4(graph, None) == 2

    def test_fallback_extract_year(self) -> None:
        graph = _minimal_graph(metadata={"publication_year": 2021})
        assert score_c4(graph, None) == 2


# ---------------------------------------------------------------------------
# TestC5 — DOI/URL/ISBN
# ---------------------------------------------------------------------------


class TestC5DocumentedSource:
    def test_from_props_true(self) -> None:
        graph = _minimal_graph()
        assert score_c5(graph, _props(c5_has_doi=True)) == 1

    def test_from_props_false(self) -> None:
        graph = _minimal_graph()
        assert score_c5(graph, _props(c5_has_doi=False)) == 0

    def test_fallback_doi(self) -> None:
        graph = _minimal_graph(metadata={"doi": "10.1234/test"})
        assert score_c5(graph, None) == 1

    def test_fallback_url(self) -> None:
        graph = _minimal_graph(metadata={"source_url": "https://example.com"})
        assert score_c5(graph, None) == 1

    def test_fallback_none(self) -> None:
        graph = _minimal_graph(metadata={})
        assert score_c5(graph, None) == 0


# ---------------------------------------------------------------------------
# TestC6 — GBD disease burden
# ---------------------------------------------------------------------------


class TestC6DiseaseBurden:
    def test_top15(self) -> None:
        gbd = _gbd_fixture()
        graph = _minimal_graph(graph_id="test_graph")
        assert score_c6(graph, gbd) == 2

    def test_top30(self) -> None:
        gbd = _gbd_fixture()
        graph = _minimal_graph(graph_id="low_burden")
        assert score_c6(graph, gbd) == 1

    def test_not_ranked(self) -> None:
        gbd = _gbd_fixture()
        graph = _minimal_graph(graph_id="not_ranked")
        assert score_c6(graph, gbd) == 0

    def test_unmapped_emergency(self) -> None:
        gbd = _gbd_fixture()
        graph = _minimal_graph(graph_id="new_graph", metadata={"is_emergency_condition": True})
        assert score_c6(graph, gbd) == 2


# ---------------------------------------------------------------------------
# TestC7 — Time-to-harm severity
# ---------------------------------------------------------------------------


class TestC7TimeToHarm:
    def test_critical(self) -> None:
        graph = _minimal_graph()
        assert score_c7(graph, _props(c7_time_to_harm="critical")) == 2

    def test_moderate(self) -> None:
        graph = _minimal_graph()
        assert score_c7(graph, _props(c7_time_to_harm="moderate")) == 1

    def test_mild(self) -> None:
        graph = _minimal_graph()
        assert score_c7(graph, _props(c7_time_to_harm="mild")) == 0

    def test_fallback_hardcoded_map(self) -> None:
        graph = _minimal_graph(graph_id="acls_cardiac_arrest")
        assert score_c7(graph, None) == 2

    def test_fallback_default_mild(self) -> None:
        graph = _minimal_graph(graph_id="unknown_graph")
        assert score_c7(graph, None) == 0


# ---------------------------------------------------------------------------
# TestC8 — Contraindication rules in source text
# ---------------------------------------------------------------------------


class TestC8Contraindication:
    def test_high(self) -> None:
        graph = _minimal_graph()
        assert score_c8(graph, _props(c8_contraindication_explicit=2)) == 2

    def test_medium(self) -> None:
        graph = _minimal_graph()
        assert score_c8(graph, _props(c8_contraindication_explicit=1)) == 1

    def test_none(self) -> None:
        graph = _minimal_graph()
        assert score_c8(graph, _props(c8_contraindication_explicit=0)) == 0

    def test_no_props_returns_zero(self) -> None:
        """Without source properties, C8 defaults to 0 (no YAML fallback)."""
        graph = _minimal_graph()
        assert score_c8(graph, None) == 0


# ---------------------------------------------------------------------------
# TestC9 — Algorithm/flowchart in source
# ---------------------------------------------------------------------------


class TestC9Algorithm:
    def test_score_direct(self) -> None:
        graph = _minimal_graph()
        assert score_c9(graph, _props(c9_score=2)) == 2

    def test_score_from_figure_count(self) -> None:
        p = {"c9_has_algorithm_figure": True, "c9_figure_count": 4}
        graph = _minimal_graph()
        assert score_c9(graph, p) == 2

    def test_simple_flowchart(self) -> None:
        p = {"c9_has_algorithm_figure": True, "c9_figure_count": 1}
        graph = _minimal_graph()
        assert score_c9(graph, p) == 1

    def test_no_algorithm(self) -> None:
        p = {"c9_has_algorithm_figure": False}
        graph = _minimal_graph()
        assert score_c9(graph, p) == 0

    def test_no_props_returns_zero(self) -> None:
        graph = _minimal_graph()
        assert score_c9(graph, None) == 0


# ---------------------------------------------------------------------------
# TestC10 — Time constraints in source text
# ---------------------------------------------------------------------------


class TestC10TimeConstraints:
    def test_score_direct(self) -> None:
        graph = _minimal_graph()
        assert score_c10(graph, _props(c10_score=2)) == 2

    def test_many_statements(self) -> None:
        p = {"c10_time_constraints_explicit": True, "c10_time_statements_count": 5}
        graph = _minimal_graph()
        assert score_c10(graph, p) == 2

    def test_few_statements(self) -> None:
        p = {"c10_time_constraints_explicit": True, "c10_time_statements_count": 1}
        graph = _minimal_graph()
        assert score_c10(graph, p) == 1

    def test_no_time_constraints(self) -> None:
        p = {"c10_time_constraints_explicit": False}
        graph = _minimal_graph()
        assert score_c10(graph, p) == 0

    def test_no_props_returns_zero(self) -> None:
        graph = _minimal_graph()
        assert score_c10(graph, None) == 0


# ---------------------------------------------------------------------------
# TestC11 — Sequence dependency in source text
# ---------------------------------------------------------------------------


class TestC11SequenceDependency:
    def test_explicit(self) -> None:
        graph = _minimal_graph()
        assert score_c11(graph, _props(c11_sequence_dependency_explicit=True)) == 1

    def test_not_explicit(self) -> None:
        graph = _minimal_graph()
        assert score_c11(graph, _props(c11_sequence_dependency_explicit=False)) == 0

    def test_no_props_returns_zero(self) -> None:
        graph = _minimal_graph()
        assert score_c11(graph, None) == 0


# ---------------------------------------------------------------------------
# TestC12 — Conditional branching in source text
# ---------------------------------------------------------------------------


class TestC12ConditionalBranching:
    def test_explicit(self) -> None:
        graph = _minimal_graph()
        assert score_c12(graph, _props(c12_conditional_branching_explicit=True)) == 1

    def test_not_explicit(self) -> None:
        graph = _minimal_graph()
        assert score_c12(graph, _props(c12_conditional_branching_explicit=False)) == 0

    def test_no_props_returns_zero(self) -> None:
        graph = _minimal_graph()
        assert score_c12(graph, None) == 0


# ---------------------------------------------------------------------------
# TestAxisComputation
# ---------------------------------------------------------------------------


class TestAxisComputation:
    def test_axis_sums(self) -> None:
        scores = {f"C{i}": 1 for i in range(1, 13)}
        axes = compute_axes(scores)
        # Axis 1: C1+C2+C3+C4+C5 = 5
        assert axes["axis1_trustworthiness"] == 5
        # Axis 2: C6+C7+C8 = 3
        assert axes["axis2_clinical"] == 3
        # Axis 3: C9+C10+C11+C12 = 4
        assert axes["axis3_formalizability"] == 4
        assert axes["total"] == 12

    def test_max_scores(self) -> None:
        scores = {
            "C1": 1,
            "C2": 2,
            "C3": 1,
            "C4": 2,
            "C5": 1,
            "C6": 2,
            "C7": 2,
            "C8": 2,
            "C9": 2,
            "C10": 2,
            "C11": 1,
            "C12": 1,
        }
        axes = compute_axes(scores)
        assert axes["total"] == 19
        assert axes["axis1_trustworthiness"] == 7
        assert axes["axis2_clinical"] == 6
        assert axes["axis3_formalizability"] == 6

    def test_zero_scores(self) -> None:
        scores = {f"C{i}": 0 for i in range(1, 13)}
        axes = compute_axes(scores)
        assert axes["total"] == 0

    def test_axis_maxes(self) -> None:
        scores = {f"C{i}": 0 for i in range(1, 13)}
        axes = compute_axes(scores)
        assert axes["axis1_max"] == 7
        assert axes["axis2_max"] == 6
        assert axes["axis3_max"] == 6
        assert axes["total_max"] == 19


# ---------------------------------------------------------------------------
# TestTierClassification
# ---------------------------------------------------------------------------


class TestTierClassification:
    def test_tier_s(self) -> None:
        assert classify_tier(15) == "S"
        assert classify_tier(19) == "S"

    def test_tier_a(self) -> None:
        assert classify_tier(11) == "A"
        assert classify_tier(14) == "A"

    def test_tier_b(self) -> None:
        assert classify_tier(7) == "B"
        assert classify_tier(10) == "B"

    def test_excluded(self) -> None:
        assert classify_tier(6) == "Excluded"
        assert classify_tier(0) == "Excluded"


# ---------------------------------------------------------------------------
# TestComputeAllScores — integration with props
# ---------------------------------------------------------------------------


class TestComputeAllScores:
    def test_perfect_score_with_props(self) -> None:
        graph = _minimal_graph(graph_id="test_graph")
        gbd = _gbd_fixture()
        props = _props()
        scores = compute_all_scores(graph, gbd, props)
        axes = compute_axes(scores)
        # C1=1, C2=2, C3=1, C4=2, C5=1, C6=2, C7=2, C8=2, C9=2, C10=2, C11=1, C12=1
        assert axes["total"] == 19
        assert classify_tier(axes["total"]) == "S"

    def test_minimal_score_no_props(self) -> None:
        graph = _minimal_graph(
            graph_id="not_ranked",
            guideline_name="Unknown Protocol",
            metadata={},
        )
        gbd = _gbd_fixture()
        scores = compute_all_scores(graph, gbd, None)
        axes = compute_axes(scores)
        # No props -> C8, C9, C10, C11, C12 all 0
        # No society, no evidence system, no systematic review
        assert axes["total"] < TIER_B_MIN

    def test_source_properties_override_yaml(self) -> None:
        """Source properties take priority over YAML metadata."""
        graph = _minimal_graph(metadata={"has_systematic_review": False})
        gbd = _gbd_fixture()
        props = _props(c3_systematic_review=True)
        scores = compute_all_scores(graph, gbd, props)
        assert scores["C3"] == 1  # props say True, overrides YAML False


# ---------------------------------------------------------------------------
# TestNoCircularReasoning — ensure Axis 3 never reads YAML nodes
# ---------------------------------------------------------------------------


class TestNoCircularReasoning:
    """Verify C8-C12 never read YAML node structures."""

    def test_c8_ignores_yaml_forbidden(self) -> None:
        """C8 should NOT count YAML forbidden_actions."""
        graph = _minimal_graph()
        graph["nodes"] = {
            "n1": {"forbidden_actions": ["a", "b", "c", "d", "e"]},
        }
        # Without props, C8 returns 0 regardless of YAML content
        assert score_c8(graph, None) == 0

    def test_c9_ignores_yaml_nodes(self) -> None:
        """C9 should NOT count YAML decision nodes."""
        graph = _minimal_graph()
        graph["nodes"] = {f"d{i}": {"node_type": "decision"} for i in range(10)}
        assert score_c9(graph, None) == 0

    def test_c10_ignores_yaml_deadlines(self) -> None:
        """C10 should NOT count YAML deadline fields."""
        graph = _minimal_graph()
        graph["nodes"] = {
            "n1": {"deadlines": {"a": 30, "b": 60, "c": 45, "d": 15}},
        }
        assert score_c10(graph, None) == 0

    def test_c11_ignores_yaml_prior_actions(self) -> None:
        """C11 should NOT count YAML required_prior_actions."""
        graph = _minimal_graph()
        graph["nodes"] = {
            "n1": {"required_prior_actions": {"a": ["b"], "c": ["d"]}},
        }
        assert score_c11(graph, None) == 0

    def test_c12_ignores_yaml_conditional_next(self) -> None:
        """C12 should NOT count YAML conditional_next."""
        graph = _minimal_graph()
        graph["nodes"] = {
            "n1": {"conditional_next": {"a": "n2", "b": "n3", "c": "n4"}},
        }
        assert score_c12(graph, None) == 0


# ---------------------------------------------------------------------------
# TestRealGraph — Integration tests on actual graphs
# ---------------------------------------------------------------------------


class TestRealGraph:
    @pytest.fixture()
    def gbd_table(self) -> dict:
        gbd_path = REPO_ROOT / "data" / "gbd_top30_causes.json"
        if not gbd_path.exists():
            pytest.skip("GBD lookup table not found")
        return load_gbd_table(gbd_path)

    @pytest.fixture()
    def source_props(self) -> dict:
        props_path = REPO_ROOT / "data" / "cpg_source_properties.json"
        if not props_path.exists():
            pytest.skip("Source properties not found")
        return load_source_properties(props_path)

    def test_ssc_sepsis(self, gbd_table: dict, source_props: dict) -> None:
        """SSC sepsis should score Tier S."""
        path = REPO_ROOT / "cpg_model" / "graphs" / "ssc_sepsis_hour1_bundle.yaml"
        if not path.exists():
            pytest.skip("SSC graph not found")
        graph = load_graph(path)
        props = source_props.get("ssc_sepsis_hour1_bundle")
        scores = compute_all_scores(graph, gbd_table, props)
        axes = compute_axes(scores)
        tier = classify_tier(axes["total"])
        assert tier == "S", f"SSC should be Tier S: {tier} ({axes['total']})"
        assert axes["total"] == 19  # perfect score

    def test_stroke(self, gbd_table: dict, source_props: dict) -> None:
        """AHA Stroke should score Tier S."""
        path = REPO_ROOT / "cpg_model" / "graphs" / "aha_stroke_2019.yaml"
        if not path.exists():
            pytest.skip("Stroke graph not found")
        graph = load_graph(path)
        props = source_props.get("aha_stroke_2019")
        scores = compute_all_scores(graph, gbd_table, props)
        axes = compute_axes(scores)
        tier = classify_tier(axes["total"])
        assert tier in ("S", "A"), f"Stroke should be S or A: {tier}"
        assert scores["C6"] == 2  # GBD #2 death
        assert scores["C7"] == 2  # critical time-to-harm

    def test_universal_safety_excluded(self, gbd_table: dict, source_props: dict) -> None:
        """Universal clinical safety meta-graph should be Excluded."""
        path = REPO_ROOT / "cpg_model" / "graphs" / "universal_clinical_safety.yaml"
        if not path.exists():
            pytest.skip("Universal safety graph not found")
        graph = load_graph(path)
        props = source_props.get("universal_clinical_safety")
        scores = compute_all_scores(graph, gbd_table, props)
        axes = compute_axes(scores)
        tier = classify_tier(axes["total"])
        assert tier == "Excluded", f"Meta-graph should be Excluded: {tier} ({axes['total']})"


TIER_B_MIN = 7  # module-level for test assertions
