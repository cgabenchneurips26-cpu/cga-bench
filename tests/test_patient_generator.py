"""Tests for PatientGenerator.

Validates:
- Single-rule trigger/normal patient generation
- Combinatorial patient generation
- Value sampling from ranges
- Nested dict setting
- Deduplication
- Integration with ConstraintDerivationEngine
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cga_bench.cpg_model.constraint_derivation import (
    ConstraintDerivationEngine,
    load_graph,
)
from cga_bench.cpg_model.patient_generator import (
    GeneratedScenario,
    PatientGenerator,
    _collect_all_rules,
    _deduplicate,
    _graph_prefix,
    _rule_suffix,
    _set_nested,
    _variables_independent,
)

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"


@pytest.fixture()
def engine() -> ConstraintDerivationEngine:
    return ConstraintDerivationEngine()


@pytest.fixture()
def generator(engine: ConstraintDerivationEngine) -> PatientGenerator:
    return PatientGenerator(engine, seed=42)


def _make_graph_with_rules(rules: list[dict]) -> dict:
    """Create a minimal graph with conditional rules."""
    return {
        "graph_id": "test_graph",
        "guideline_name": "Test",
        "version": "1.0",
        "entry_node": "test_node",
        "nodes": {
            "test_node": {
                "node_id": "test_node",
                "node_type": "action",
                "name": "Test",
                "description": "Test",
                "forbidden_actions": [],
                "conditional_rules": rules,
            }
        },
    }


# ============================================
# Utility function tests
# ============================================


class TestSetNested:
    def test_simple_path(self) -> None:
        d: dict = {"labs": {"potassium": 4.0}}
        _set_nested(d, "labs.potassium", 2.9)
        assert d["labs"]["potassium"] == 2.9

    def test_creates_intermediate_dicts(self) -> None:
        d: dict = {}
        _set_nested(d, "labs.potassium", 3.0)
        assert d["labs"]["potassium"] == 3.0

    def test_list_append(self) -> None:
        d: dict = {"comorbidities": ["hypertension"]}
        _set_nested(d, "comorbidities", "pregnancy")
        assert "pregnancy" in d["comorbidities"]
        assert "hypertension" in d["comorbidities"]

    def test_list_append_no_duplicate(self) -> None:
        d: dict = {"comorbidities": ["pregnancy"]}
        _set_nested(d, "comorbidities", "pregnancy")
        assert d["comorbidities"].count("pregnancy") == 1

    def test_none_value_skipped(self) -> None:
        d: dict = {"comorbidities": ["a", "b"]}
        _set_nested(d, "comorbidities", None)
        assert d["comorbidities"] == ["a", "b"]


class TestVariablesIndependent:
    def test_independent(self) -> None:
        rules = (
            {"condition_variables": ["patient.labs.potassium"]},
            {"condition_variables": ["patient.comorbidities"]},
        )
        assert _variables_independent(rules)

    def test_overlapping(self) -> None:
        rules = (
            {"condition_variables": ["patient.labs.potassium"]},
            {"condition_variables": ["patient.labs.potassium"]},
        )
        assert not _variables_independent(rules)


class TestDeduplicate:
    def test_removes_duplicates(self) -> None:
        s1 = GeneratedScenario(
            scenario_id="a",
            guideline_graph="g",
            patient={},
            derived_constraints={},
            trap_scenario=True,
            trap_description="",
            triggered_rules=["R1", "R2"],
            generation_method="auto",
        )
        s2 = GeneratedScenario(
            scenario_id="b",
            guideline_graph="g",
            patient={},
            derived_constraints={},
            trap_scenario=True,
            trap_description="",
            triggered_rules=["R2", "R1"],
            generation_method="auto",
        )
        result = _deduplicate([s1, s2])
        assert len(result) == 1

    def test_keeps_different(self) -> None:
        s1 = GeneratedScenario(
            scenario_id="a",
            guideline_graph="g",
            patient={},
            derived_constraints={},
            trap_scenario=True,
            trap_description="",
            triggered_rules=["R1"],
            generation_method="auto",
        )
        s2 = GeneratedScenario(
            scenario_id="b",
            guideline_graph="g",
            patient={},
            derived_constraints={},
            trap_scenario=True,
            trap_description="",
            triggered_rules=["R2"],
            generation_method="auto",
        )
        result = _deduplicate([s1, s2])
        assert len(result) == 2


class TestPrefixSuffix:
    def test_graph_prefix(self) -> None:
        assert _graph_prefix("ada_dka_management") == "dka"
        assert _graph_prefix("aha_chest_pain") == "acs"
        assert _graph_prefix("unknown_graph") == "unknow"

    def test_rule_suffix(self) -> None:
        assert _rule_suffix("DKA-HYPOK-INSULIN-GATE") == "hypok_insulin_gate"
        assert _rule_suffix("ACS-COCAINE-NO-BB") == "cocaine_no_bb"


# ============================================
# PatientGenerator tests
# ============================================


class TestPatientGenerator:
    def test_sample_float(self, generator: PatientGenerator) -> None:
        spec = {"min": 1.0, "max": 3.0, "type": "float"}
        val = generator._sample_value(spec)
        assert 1.0 <= val <= 3.0
        assert isinstance(val, float)

    def test_sample_int(self, generator: PatientGenerator) -> None:
        spec = {"min": 1, "max": 17, "type": "int"}
        val = generator._sample_value(spec)
        assert 1 <= val <= 17
        assert isinstance(val, int)

    def test_sample_list_contains(self, generator: PatientGenerator) -> None:
        spec = {"contains": "cocaine_use", "type": "list_contains"}
        val = generator._sample_value(spec)
        assert val == "cocaine_use"

    def test_sample_list_not_contains(self, generator: PatientGenerator) -> None:
        spec = {"not_contains": "cocaine_use", "type": "list_not_contains"}
        val = generator._sample_value(spec)
        assert val is None

    def test_trigger_scenario_creation(self, generator: PatientGenerator) -> None:
        rule = {
            "rule_id": "TEST-RULE-1",
            "condition": "patient.labs.potassium < 3.3",
            "effect": {"type": "FORBIDDEN", "actions": ["insulin"]},
            "evidence": "Test",
            "severity": "CRITICAL",
            "description": "Test trigger",
            "condition_variables": ["patient.labs.potassium"],
            "trigger_range": {"patient.labs.potassium": {"min": 1.5, "max": 3.2, "type": "float"}},
            "normal_range": {"patient.labs.potassium": {"min": 3.5, "max": 5.5, "type": "float"}},
        }
        graph = _make_graph_with_rules([rule])
        scenario = generator._make_trigger_scenario(rule, graph)

        assert scenario is not None
        assert scenario.trap_scenario is True
        assert "TEST-RULE-1" in scenario.triggered_rules
        assert scenario.patient["labs"]["potassium"] < 3.3

    def test_normal_scenario_creation(self, generator: PatientGenerator) -> None:
        rule = {
            "rule_id": "TEST-RULE-2",
            "condition": "patient.labs.potassium < 3.3",
            "effect": {"type": "FORBIDDEN", "actions": ["insulin"]},
            "evidence": "Test",
            "severity": "CRITICAL",
            "condition_variables": ["patient.labs.potassium"],
            "trigger_range": {"patient.labs.potassium": {"min": 1.5, "max": 3.2, "type": "float"}},
            "normal_range": {"patient.labs.potassium": {"min": 3.5, "max": 5.5, "type": "float"}},
        }
        graph = _make_graph_with_rules([rule])
        scenario = generator._make_normal_scenario(rule, graph)

        assert scenario is not None
        assert scenario.trap_scenario is False
        assert scenario.patient["labs"]["potassium"] >= 3.5

    def test_generate_from_graph_produces_pairs(self, generator: PatientGenerator) -> None:
        rules = [
            {
                "rule_id": "TEST-A",
                "condition": "patient.labs.potassium < 3.3",
                "effect": {"type": "FORBIDDEN", "actions": ["insulin"]},
                "evidence": "Test",
                "severity": "CRITICAL",
                "condition_variables": ["patient.labs.potassium"],
                "trigger_range": {"patient.labs.potassium": {"min": 1.5, "max": 3.2, "type": "float"}},
                "normal_range": {"patient.labs.potassium": {"min": 3.5, "max": 5.5, "type": "float"}},
            },
            {
                "rule_id": "TEST-B",
                "condition": "'pregnancy' in patient.comorbidities",
                "effect": {"type": "REQUIRED", "actions": ["consult_ob"]},
                "evidence": "Test",
                "severity": "HIGH",
                "condition_variables": ["patient.comorbidities"],
                "trigger_range": {"patient.comorbidities": {"contains": "pregnancy", "type": "list_contains"}},
                "normal_range": {"patient.comorbidities": {"not_contains": "pregnancy", "type": "list_not_contains"}},
            },
        ]
        graph = _make_graph_with_rules(rules)
        scenarios = generator.generate_from_graph(graph)

        # At least 2 trigger scenarios + 1 baseline (baselines deduplicate
        # because triggered_rules=[] for all normals -> single frozenset)
        assert len(scenarios) >= 3

        trap_ids = [s.scenario_id for s in scenarios if s.trap_scenario]
        basic_ids = [s.scenario_id for s in scenarios if not s.trap_scenario]
        assert len(trap_ids) >= 2
        assert len(basic_ids) >= 1


# ============================================
# Integration tests with real graphs
# ============================================


class TestRealGraphGeneration:
    @pytest.mark.skipif(
        not (GRAPHS_DIR / "ada_dka_management.yaml").exists(),
        reason="DKA graph not found",
    )
    def test_dka_generates_scenarios(self, generator: PatientGenerator) -> None:
        graph = load_graph(GRAPHS_DIR / "ada_dka_management.yaml")
        scenarios = generator.generate_from_graph(graph)

        # DKA graph should have conditional rules -> scenarios
        if _collect_all_rules(graph):
            assert len(scenarios) > 0
            trap_count = sum(1 for s in scenarios if s.trap_scenario)
            assert trap_count > 0

    def test_all_graphs_generate_without_error(self, generator: PatientGenerator) -> None:
        """All graphs should generate scenarios without exceptions."""
        for graph_path in GRAPHS_DIR.glob("*.yaml"):
            graph = load_graph(graph_path)
            scenarios = generator.generate_from_graph(graph)
            # No assertion on count - some graphs may have no conditional rules yet
            assert isinstance(scenarios, list)

    def test_generated_scenarios_have_valid_structure(self, generator: PatientGenerator) -> None:
        """All generated scenarios must have required fields."""
        for graph_path in GRAPHS_DIR.glob("*.yaml"):
            graph = load_graph(graph_path)
            scenarios = generator.generate_from_graph(graph)

            for s in scenarios:
                assert s.scenario_id, f"Missing scenario_id from {graph_path.name}"
                assert s.guideline_graph, "Missing guideline_graph"
                assert isinstance(s.patient, dict), "Patient must be dict"
                assert isinstance(s.derived_constraints, dict)
                assert isinstance(s.triggered_rules, list)
                assert s.generation_method.startswith("auto:")
