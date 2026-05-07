"""Tests for ConstraintDerivationEngine.

Validates:
- Conditional rule evaluation against patient context
- Unconditional forbidden/sequence extraction
- Allergy-based forbidden derivation
- Provenance chain completeness
- DotDict utility
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cga_bench.cpg_model.constraint_derivation import (
    ConstraintDerivationEngine,
    DerivedConstraint,
    DerivedConstraintSet,
    DotDict,
    load_graph,
)

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"


@pytest.fixture()
def engine() -> ConstraintDerivationEngine:
    return ConstraintDerivationEngine()


def _make_mini_graph(
    conditional_rules: list[dict] | None = None,
    forbidden_actions: list[str] | None = None,
    sequence_rules: list[list[str]] | None = None,
) -> dict:
    """Create a minimal graph dict for testing."""
    node: dict = {
        "node_id": "test_node",
        "node_type": "action",
        "name": "Test Node",
        "description": "Test",
        "forbidden_actions": forbidden_actions or [],
        "sequence_rules": sequence_rules or [],
        "conditional_rules": conditional_rules or [],
    }
    return {
        "graph_id": "test_graph",
        "guideline_name": "Test",
        "version": "1.0",
        "entry_node": "test_node",
        "nodes": {"test_node": node},
    }


# ============================================
# DotDict tests
# ============================================


class TestDotDict:
    def test_simple_access(self) -> None:
        d = DotDict({"a": 1, "b": "hello"})
        assert d.a == 1
        assert d.b == "hello"

    def test_nested_access(self) -> None:
        d = DotDict({"labs": {"potassium": 3.0, "glucose": 400}})
        assert d.labs.potassium == 3.0
        assert d.labs.glucose == 400

    def test_missing_key_returns_empty(self) -> None:
        d = DotDict({"a": 1})
        result = d.nonexistent
        assert isinstance(result, DotDict)
        assert not result

    def test_list_access(self) -> None:
        d = DotDict({"allergies": ["penicillin", "aspirin"]})
        assert "penicillin" in d.allergies
        assert "morphine" not in d.allergies


# ============================================
# Condition evaluation tests
# ============================================


class TestConditionEvaluation:
    def test_numeric_less_than(self, engine: ConstraintDerivationEngine) -> None:
        patient = {"labs": {"potassium": 2.9}}
        assert engine._evaluate_condition("patient.labs.potassium < 3.3", patient)

    def test_numeric_greater_than(self, engine: ConstraintDerivationEngine) -> None:
        patient = {"labs": {"potassium": 6.0}}
        assert engine._evaluate_condition("patient.labs.potassium > 5.5", patient)

    def test_numeric_not_triggered(self, engine: ConstraintDerivationEngine) -> None:
        patient = {"labs": {"potassium": 4.2}}
        assert not engine._evaluate_condition("patient.labs.potassium < 3.3", patient)

    def test_in_list(self, engine: ConstraintDerivationEngine) -> None:
        patient = {"comorbidities": ["cocaine_use", "hypertension"]}
        assert engine._evaluate_condition("'cocaine_use' in patient.comorbidities", patient)

    def test_not_in_list(self, engine: ConstraintDerivationEngine) -> None:
        patient = {"comorbidities": ["hypertension"]}
        assert not engine._evaluate_condition("'cocaine_use' in patient.comorbidities", patient)

    def test_compound_and(self, engine: ConstraintDerivationEngine) -> None:
        patient = {
            "medications": ["sglt2_inhibitor"],
            "labs": {"glucose": 200},
        }
        assert engine._evaluate_condition(
            "'sglt2_inhibitor' in patient.medications and patient.labs.glucose < 250",
            patient,
        )

    def test_compound_or(self, engine: ConstraintDerivationEngine) -> None:
        patient = {"vitals": {"sbp": 190, "dbp": 100}}
        assert engine._evaluate_condition(
            "patient.vitals.sbp > 185 or patient.vitals.dbp > 110",
            patient,
        )

    def test_age_comparison(self, engine: ConstraintDerivationEngine) -> None:
        patient = {"age": 12}
        assert engine._evaluate_condition("patient.age < 18", patient)

    def test_missing_field_returns_false(self, engine: ConstraintDerivationEngine) -> None:
        patient = {"labs": {}}
        assert not engine._evaluate_condition("patient.labs.potassium < 3.3", patient)


# ============================================
# Derivation tests
# ============================================


class TestDerive:
    def test_unconditional_forbidden(self, engine: ConstraintDerivationEngine) -> None:
        graph = _make_mini_graph(forbidden_actions=["bad_action1", "bad_action2"])
        result = engine.derive(graph, {"allergies": []})
        assert len(result.forbidden) == 2
        assert all(not c.is_conditional for c in result.forbidden)

    def test_unconditional_sequence(self, engine: ConstraintDerivationEngine) -> None:
        graph = _make_mini_graph(sequence_rules=[["action_a", "action_b"]])
        result = engine.derive(graph, {"allergies": []})
        assert len(result.before) == 1
        assert result.before[0].actions == ["action_a", "action_b"]
        assert not result.before[0].is_conditional

    def test_conditional_rule_triggered(self, engine: ConstraintDerivationEngine) -> None:
        graph = _make_mini_graph(
            conditional_rules=[
                {
                    "rule_id": "TEST-RULE-1",
                    "condition": "patient.labs.potassium < 3.3",
                    "effect": {
                        "type": "FORBIDDEN",
                        "actions": ["start_insulin"],
                    },
                    "evidence": "Test Evidence",
                    "severity": "CRITICAL",
                    "description": "Test description",
                    "condition_variables": ["patient.labs.potassium"],
                    "trigger_range": {"patient.labs.potassium": {"min": 1.5, "max": 3.2, "type": "float"}},
                    "normal_range": {"patient.labs.potassium": {"min": 3.5, "max": 5.5, "type": "float"}},
                }
            ]
        )
        patient = {"labs": {"potassium": 2.9}, "allergies": []}
        result = engine.derive(graph, patient, "test_scenario")

        conditional_forbidden = [c for c in result.forbidden if c.is_conditional]
        assert len(conditional_forbidden) == 1
        assert "start_insulin" in conditional_forbidden[0].actions
        assert "TEST-RULE-1" in conditional_forbidden[0].provenance
        assert conditional_forbidden[0].severity == "CRITICAL"

    def test_conditional_rule_not_triggered(self, engine: ConstraintDerivationEngine) -> None:
        graph = _make_mini_graph(
            conditional_rules=[
                {
                    "rule_id": "TEST-RULE-2",
                    "condition": "patient.labs.potassium < 3.3",
                    "effect": {
                        "type": "FORBIDDEN",
                        "actions": ["start_insulin"],
                    },
                    "evidence": "Test",
                    "severity": "CRITICAL",
                    "condition_variables": ["patient.labs.potassium"],
                    "trigger_range": {},
                    "normal_range": {},
                }
            ]
        )
        patient = {"labs": {"potassium": 4.2}, "allergies": []}
        result = engine.derive(graph, patient, "test_scenario")

        conditional_forbidden = [c for c in result.forbidden if c.is_conditional]
        assert len(conditional_forbidden) == 0
        assert result.total_rules_evaluated == 1
        assert result.total_rules_triggered == 0

    def test_allergy_forbidden(self, engine: ConstraintDerivationEngine) -> None:
        graph = _make_mini_graph()
        patient = {"allergies": ["penicillin_anaphylaxis"]}
        result = engine.derive(graph, patient, "test_allergy")

        allergy_forbidden = [c for c in result.forbidden if "allergy_map" in c.provenance]
        assert len(allergy_forbidden) > 0
        allergy_actions = [a for c in allergy_forbidden for a in c.actions]
        assert "give_ampicillin" in allergy_actions

    def test_required_constraint(self, engine: ConstraintDerivationEngine) -> None:
        graph = _make_mini_graph(
            conditional_rules=[
                {
                    "rule_id": "TEST-REQ-1",
                    "condition": "'pregnancy' in patient.comorbidities",
                    "effect": {
                        "type": "REQUIRED",
                        "actions": ["consult_obstetrics"],
                    },
                    "evidence": "Test",
                    "severity": "HIGH",
                    "condition_variables": ["patient.comorbidities"],
                    "trigger_range": {},
                    "normal_range": {},
                }
            ]
        )
        patient = {"comorbidities": ["pregnancy"], "allergies": []}
        result = engine.derive(graph, patient)

        assert len(result.required) == 1
        assert "consult_obstetrics" in result.required[0].actions


# ============================================
# Provenance tests
# ============================================


class TestProvenance:
    def test_provenance_format(self, engine: ConstraintDerivationEngine) -> None:
        graph = _make_mini_graph(
            conditional_rules=[
                {
                    "rule_id": "PROV-TEST-1",
                    "condition": "patient.age < 18",
                    "effect": {"type": "FORBIDDEN", "actions": ["action1"]},
                    "evidence": "Test Guideline, Section 1",
                    "severity": "HIGH",
                    "condition_variables": ["patient.age"],
                    "trigger_range": {},
                    "normal_range": {},
                }
            ]
        )
        patient = {"age": 12, "allergies": []}
        result = engine.derive(graph, patient)

        conditional = [c for c in result.forbidden if c.is_conditional]
        assert len(conditional) == 1
        prov = conditional[0].provenance
        assert prov == "graph:test_graph:node:test_node:rule:PROV-TEST-1"

    def test_unconditional_provenance(self, engine: ConstraintDerivationEngine) -> None:
        graph = _make_mini_graph(forbidden_actions=["bad_action"])
        result = engine.derive(graph, {"allergies": []})
        assert "unconditional" in result.forbidden[0].provenance


# ============================================
# DerivedConstraintSet tests
# ============================================


class TestDerivedConstraintSet:
    def test_add_routes_correctly(self) -> None:
        cs = DerivedConstraintSet(scenario_id="test", graph_id="test")
        cs.add(
            DerivedConstraint(
                constraint_type="FORBIDDEN",
                actions=["a"],
                provenance="p",
                evidence="e",
                severity="HIGH",
                description="d",
                condition_met="c",
                is_conditional=False,
            )
        )
        cs.add(
            DerivedConstraint(
                constraint_type="REQUIRED",
                actions=["b"],
                provenance="p",
                evidence="e",
                severity="HIGH",
                description="d",
                condition_met="c",
                is_conditional=True,
            )
        )
        cs.add(
            DerivedConstraint(
                constraint_type="BEFORE",
                actions=["c", "d"],
                provenance="p",
                evidence="e",
                severity="HIGH",
                description="d",
                condition_met="c",
                is_conditional=False,
            )
        )
        assert len(cs.forbidden) == 1
        assert len(cs.required) == 1
        assert len(cs.before) == 1
        assert len(cs.all_constraints()) == 3

    def test_to_yaml(self) -> None:
        cs = DerivedConstraintSet(scenario_id="test", graph_id="test")
        cs.add(
            DerivedConstraint(
                constraint_type="FORBIDDEN",
                actions=["a"],
                provenance="p",
                evidence="e",
                severity="HIGH",
                description="d",
                condition_met="c",
                is_conditional=True,
            )
        )
        result = cs.to_yaml()
        assert result["scenario_id"] == "test"
        assert len(result["forbidden"]) == 1
        assert result["forbidden"][0]["actions"] == ["a"]

    def test_to_audit_row(self) -> None:
        cs = DerivedConstraintSet(scenario_id="test", graph_id="test")
        cs.add(
            DerivedConstraint(
                constraint_type="FORBIDDEN",
                actions=["a"],
                provenance="p",
                evidence="e",
                severity="HIGH",
                description="d",
                condition_met="c",
                is_conditional=True,
            )
        )
        row = cs.to_audit_row()
        assert row["num_forbidden"] == 1
        assert row["total_constraints"] == 1
        assert row["conditional_count"] == 1


# ============================================
# Format condition met tests
# ============================================


class TestFormatConditionMet:
    def test_numeric_substitution(self, engine: ConstraintDerivationEngine) -> None:
        patient = {"labs": {"potassium": 2.9}}
        result = engine._format_condition_met("patient.labs.potassium < 3.3", patient)
        assert "2.9" in result

    def test_list_no_crash(self, engine: ConstraintDerivationEngine) -> None:
        patient = {"comorbidities": ["pregnancy"]}
        result = engine._format_condition_met("'pregnancy' in patient.comorbidities", patient)
        assert "patient.comorbidities" in result


# ============================================
# Integration: real graph tests (if available)
# ============================================


class TestRealGraphs:
    @pytest.mark.skipif(
        not (GRAPHS_DIR / "ada_dka_management.yaml").exists(),
        reason="DKA graph not found",
    )
    def test_dka_graph_loads(self, engine: ConstraintDerivationEngine) -> None:
        graph = load_graph(GRAPHS_DIR / "ada_dka_management.yaml")
        patient = {
            "age": 28,
            "sex": "M",
            "labs": {"potassium": 4.0, "glucose": 450, "ph": 7.15},
            "comorbidities": ["type_1_diabetes"],
            "allergies": [],
            "medications": [],
        }
        result = engine.derive(graph, patient, "test_dka_basic")
        # Should have unconditional forbidden at minimum
        assert len(result.forbidden) > 0

    @pytest.mark.skipif(
        not (GRAPHS_DIR / "ada_dka_management.yaml").exists(),
        reason="DKA graph not found",
    )
    def test_dka_hypokalemia_insulin_gate(self, engine: ConstraintDerivationEngine) -> None:
        graph = load_graph(GRAPHS_DIR / "ada_dka_management.yaml")
        patient = {
            "age": 28,
            "sex": "M",
            "labs": {"potassium": 2.9, "glucose": 450, "ph": 7.15},
            "comorbidities": ["type_1_diabetes"],
            "allergies": [],
            "medications": [],
        }
        result = engine.derive(graph, patient, "test_hypokalemia")

        forbidden_actions = [a for c in result.forbidden for a in c.actions]
        assert "start_insulin_infusion" in forbidden_actions or "give_insulin_bolus" in forbidden_actions

    @pytest.mark.skipif(
        not (GRAPHS_DIR / "ada_dka_management.yaml").exists(),
        reason="DKA graph not found",
    )
    def test_dka_normal_potassium_no_gate(self, engine: ConstraintDerivationEngine) -> None:
        graph = load_graph(GRAPHS_DIR / "ada_dka_management.yaml")
        patient = {
            "age": 28,
            "sex": "M",
            "labs": {"potassium": 4.2, "glucose": 450, "ph": 7.15},
            "comorbidities": ["type_1_diabetes"],
            "allergies": [],
            "medications": [],
        }
        result = engine.derive(graph, patient, "test_normal_k")

        conditional_insulin = [
            c for c in result.forbidden if c.is_conditional and "start_insulin_infusion" in c.actions
        ]
        assert len(conditional_insulin) == 0

    def test_all_graphs_provenance_complete(self, engine: ConstraintDerivationEngine) -> None:
        """All derived constraints must have provenance and severity."""
        patient = {
            "age": 50,
            "sex": "M",
            "labs": {},
            "comorbidities": [],
            "allergies": [],
            "medications": [],
        }
        for graph_path in GRAPHS_DIR.glob("*.yaml"):
            graph = load_graph(graph_path)
            result = engine.derive(graph, patient)
            for constraint in result.all_constraints():
                assert constraint.provenance, f"{graph_path.name}: constraint without provenance"
                assert constraint.severity, f"{graph_path.name}: constraint without severity"
