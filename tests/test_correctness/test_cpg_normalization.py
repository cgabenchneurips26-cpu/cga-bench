"""Regression tests for Issue #1: CPG Engine action normalization with cpg_id.

Verifies that _normalize_action_key() passes graph_id to ActionNormalizer
for domain-specific mapping resolution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from unittest.mock import MagicMock, patch

import pytest

from cga_bench.cpg_model.schemas.base import CPGGraph, CPGNode, NodeType, PatientState, VitalSigns


# --- Fixtures ---

def _make_vitals(**kwargs) -> VitalSigns:
    defaults = dict(
        heart_rate=80, blood_pressure_systolic=120,
        blood_pressure_diastolic=80, respiratory_rate=16,
        temperature=37.0, oxygen_saturation=98,
    )
    defaults.update(kwargs)
    return VitalSigns(**defaults)


def _make_patient(**kwargs) -> PatientState:
    defaults = dict(
        state_id="test", age=50, sex="M",
        vitals=_make_vitals(),
        chief_complaint="test",
    )
    defaults.update(kwargs)
    return PatientState(**defaults)


def _make_cpg_node(
    node_id: str = "node1",
    mandatory_actions: Optional[List[str]] = None,
    next_nodes: Optional[List[str]] = None,
) -> CPGNode:
    return CPGNode(
        node_id=node_id,
        node_type=NodeType.ACTION,
        name=node_id,
        description=f"Test node {node_id}",
        mandatory_actions=mandatory_actions or [],
        allowed_actions=list(mandatory_actions or []),
        forbidden_actions=[],
        deadlines={},
        next_nodes=next_nodes or [],
        required_prior_actions={},
        recommendation_strength={},
    )


def _make_graph(graph_id: str, nodes: Dict[str, CPGNode], entry: str) -> CPGGraph:
    return CPGGraph(
        graph_id=graph_id,
        guideline_name="Test",
        version="1.0",
        nodes=nodes,
        entry_node=entry,
    )


# --- Tests ---

class TestNormalizeActionKeyPassesCpgId:
    """Tests that _normalize_action_key uses graph_id for domain-specific mappings."""

    def test_graph_id_resolved_to_domain_key(self):
        """P6 재현: graph_id 'aha_stroke_2019' → domain key 'aha_stroke'."""
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node("n1", mandatory_actions=["antiplatelet_therapy"])
        graph = _make_graph("aha_stroke_2019", {"n1": node}, "n1")
        engine = CPGEngine(graph)

        # "aspirin" in aha_stroke domain → "antiplatelet_therapy"
        result = engine._normalize_action_key("aspirin")
        assert result == "antiplatelet_therapy"

    def test_without_domain_mapping_uses_generic(self):
        """Generic mapping: 'aspirin' → 'give_aspirin_loading' (no domain context)."""
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node("n1")
        graph = _make_graph("unknown_graph_id", {"n1": node}, "n1")
        engine = CPGEngine(graph)

        # Without domain-specific mapping, uses generic direct mapping
        result = engine._normalize_action_key("aspirin")
        assert result == "give_aspirin_loading"

    def test_chest_pain_domain_mapping(self):
        """aha_chest_pain domain: 'aspirin' → 'give_aspirin_loading'."""
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node("n1")
        graph = _make_graph("aha_chest_pain_evaluation", {"n1": node}, "n1")
        engine = CPGEngine(graph)

        result = engine._normalize_action_key("aspirin")
        assert result == "give_aspirin_loading"

    def test_heart_failure_domain_mapping(self):
        """aha_heart_failure domain: 'diuretic' → 'give_iv_furosemide'."""
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node("n1")
        graph = _make_graph("aha_heart_failure_2022", {"n1": node}, "n1")
        engine = CPGEngine(graph)

        result = engine._normalize_action_key("diuretic")
        assert result == "give_iv_furosemide"

    def test_sepsis_domain_fluid_mapping(self):
        """ssc_sepsis domain: 'fluid' → 'give_crystalloid_30ml_kg'."""
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node("n1")
        # ssc_sepsis_hour1_bundle is both graph_id and domain key
        graph = _make_graph("ssc_sepsis_hour1_bundle", {"n1": node}, "n1")
        engine = CPGEngine(graph)

        result = engine._normalize_action_key("fluid")
        assert result == "give_crystalloid_30ml_kg"


class TestMandatoryCompletedWithDomainMapping:
    """Tests that _mandatory_completed uses domain-specific normalization."""

    def test_stroke_mandatory_with_domain_alias(self):
        """P6 영향도: stroke에서 'aspirin' 수행 → 'antiplatelet_therapy' mandatory 충족.

        Before fix: mandatory_completed('antiplatelet_therapy') returns False
                    (aspirin → give_aspirin_loading via generic, mismatch)
        After fix: mandatory_completed('antiplatelet_therapy') returns True
                   (aspirin → antiplatelet_therapy via aha_stroke domain mapping)
        """
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node(
            "stroke_treatment",
            mandatory_actions=["antiplatelet_therapy"],
            next_nodes=["done"],
        )
        done_node = _make_cpg_node("done")
        graph = _make_graph(
            "aha_stroke_2019",
            {"stroke_treatment": node, "done": done_node},
            "stroke_treatment",
        )
        engine = CPGEngine(graph)

        # Patient performed "aspirin" as procedure
        patient = _make_patient(procedures_done=["aspirin"])
        result = engine._mandatory_completed(patient, node)
        assert result is True, (
            "Domain-specific mapping should resolve 'aspirin' → 'antiplatelet_therapy'"
        )

    def test_heart_failure_lasix_mandatory(self):
        """P6 추가 수정: 'lasix' 수행 → 'give_iv_furosemide' mandatory 충족.

        Before fix: give_iv_furosemide → iv_diuretics (generic remapping) → mismatch
        After fix: give_iv_furosemide → give_iv_furosemide (domain identity) → match
        """
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node(
            "hf_treatment",
            mandatory_actions=["give_iv_furosemide"],
            next_nodes=["done"],
        )
        done_node = _make_cpg_node("done")
        graph = _make_graph(
            "aha_heart_failure_2022",
            {"hf_treatment": node, "done": done_node},
            "hf_treatment",
        )
        engine = CPGEngine(graph)

        patient = _make_patient(procedures_done=["lasix"])
        result = engine._mandatory_completed(patient, node)
        assert result is True, (
            "Domain identity mapping should keep 'give_iv_furosemide' terminal"
        )

    def test_heart_failure_bmp_mandatory(self):
        """HF: 'bmp' 수행 → 'order_basic_metabolic_panel' mandatory 충족.

        Domain-specific mapping: bmp → order_basic_metabolic_panel (identity target).
        """
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node(
            "hf_treatment",
            mandatory_actions=["order_basic_metabolic_panel"],
            next_nodes=["done"],
        )
        done_node = _make_cpg_node("done")
        graph = _make_graph(
            "aha_heart_failure_2022",
            {"hf_treatment": node, "done": done_node},
            "hf_treatment",
        )
        engine = CPGEngine(graph)

        patient = _make_patient(procedures_done=["bmp"])
        result = engine._mandatory_completed(patient, node)
        assert result is True, (
            "Domain-specific mapping should resolve 'bmp' → 'order_basic_metabolic_panel'"
        )

    def test_without_fix_generic_mapping_mismatch(self):
        """Verifies that domain-specific mapping makes a difference.

        In 'unknown' graph, 'aspirin' maps to 'give_aspirin_loading' (generic).
        So mandatory 'antiplatelet_therapy' is NOT satisfied.
        """
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node(
            "treatment",
            mandatory_actions=["antiplatelet_therapy"],
        )
        graph = _make_graph("unknown_graph", {"treatment": node}, "treatment")
        engine = CPGEngine(graph)

        patient = _make_patient(procedures_done=["aspirin"])
        result = engine._mandatory_completed(patient, node)
        assert result is False, (
            "Without domain mapping, 'aspirin' → 'give_aspirin_loading' ≠ 'antiplatelet_therapy'"
        )


class TestGraphIdToDomainResolution:
    """Tests for _resolve_cpg_id mapping."""

    def test_aha_stroke_2019(self):
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node("n1")
        graph = _make_graph("aha_stroke_2019", {"n1": node}, "n1")
        engine = CPGEngine(graph)
        assert engine._resolve_cpg_id("aha_stroke_2019") == "aha_stroke"

    def test_aha_chest_pain_evaluation(self):
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node("n1")
        graph = _make_graph("n1", {"n1": node}, "n1")
        engine = CPGEngine(graph)
        assert engine._resolve_cpg_id("aha_chest_pain_evaluation") == "aha_chest_pain"

    def test_aha_heart_failure_2022(self):
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node("n1")
        graph = _make_graph("n1", {"n1": node}, "n1")
        engine = CPGEngine(graph)
        assert engine._resolve_cpg_id("aha_heart_failure_2022") == "aha_heart_failure"

    def test_unknown_graph_id_passthrough(self):
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node("n1")
        graph = _make_graph("n1", {"n1": node}, "n1")
        engine = CPGEngine(graph)
        assert engine._resolve_cpg_id("custom_cpg") == "custom_cpg"

    def test_none_graph_id(self):
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node("n1")
        graph = _make_graph("n1", {"n1": node}, "n1")
        engine = CPGEngine(graph)
        assert engine._resolve_cpg_id(None) is None

    def test_ssc_sepsis_passthrough(self):
        """ssc_sepsis_hour1_bundle is both graph_id and domain key (no mapping needed)."""
        from cga_bench.cpg_engine.engine import CPGEngine

        node = _make_cpg_node("n1")
        graph = _make_graph("n1", {"n1": node}, "n1")
        engine = CPGEngine(graph)
        # Not in _GRAPH_ID_TO_DOMAIN → passthrough
        assert engine._resolve_cpg_id("ssc_sepsis_hour1_bundle") == "ssc_sepsis_hour1_bundle"
