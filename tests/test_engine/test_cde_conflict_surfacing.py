"""CDE conflict-surfacing unit tests (B-cde-rescoring v1.1).

Verifies that ConstraintDerivationEngine emits CONFLICT entries when actions
are simultaneously REQUIRED and FORBIDDEN under co-satisfiable conditions —
the gap that the runtime engine misses (it never reads conditional_rules).
"""

from __future__ import annotations

import pytest

from cga_bench.cpg_model.constraint_derivation import (
    ConstraintDerivationEngine,
    DerivedConstraintSet,
)


def _scn012_graph() -> dict:
    """Synthesised PE graph mirroring SCN-012 (ESC 2019 PE)."""
    return {
        "graph_id": "test_pe",
        "nodes": {
            "init": {
                "mandatory_actions": [],
                "forbidden_actions": [],
                "conditional_rules": [
                    {
                        "rule_id": "PE-MASSIVE-THROMBOLYSIS",
                        "condition": "patient.vitals.sbp < 90",
                        "effect": {
                            "type": "REQUIRED",
                            "actions": ["give_alteplase_pe"],
                        },
                        "evidence": "ESC 2019 Class I",
                        "severity": "CRITICAL",
                        "description": "Massive PE thrombolysis",
                    },
                    {
                        "rule_id": "PE-RECENT-SURGERY-NO-THROMBOLYSIS",
                        "condition": "'recent_surgery' in patient.comorbidities",
                        "effect": {
                            "type": "FORBIDDEN",
                            "actions": ["give_alteplase_pe"],
                        },
                        "evidence": "ESC 2019 absolute contraindication",
                        "severity": "CRITICAL",
                        "description": "Recent surgery contraindication",
                    },
                ],
            }
        },
    }


@pytest.fixture
def cde() -> ConstraintDerivationEngine:
    return ConstraintDerivationEngine()


def test_cde_required_forbidden_conflict_surfacing(cde: ConstraintDerivationEngine) -> None:
    """REQUIRED + FORBIDDEN on same action with co-satisfied conditions
    -> exactly one CONFLICT in result.conflicts."""
    patient = {
        "vitals": {"sbp": 80},
        "comorbidities": ["recent_surgery"],
        "allergies": [],
    }
    result = cde.derive(_scn012_graph(), patient, scenario_id="SCN-012-test")

    assert len(result.required) == 1
    assert len(result.forbidden) == 1
    assert len(result.conflicts) == 1

    c = result.conflicts[0]
    assert c.actions == ["give_alteplase_pe"]
    assert c.constraint_type == "CONFLICT"
    assert "PE-MASSIVE-THROMBOLYSIS" in c.provenance
    assert "PE-RECENT-SURGERY-NO-THROMBOLYSIS" in c.provenance
    assert c.severity == "CRITICAL"


def test_cde_mandatory_static_vs_forbidden_conditional(cde: ConstraintDerivationEngine) -> None:
    """Static mandatory + unconditional FORBIDDEN on the same action
    -> CONFLICT surfaced (replacing the silent-drop behaviour)."""
    graph = {
        "graph_id": "test_static",
        "nodes": {
            "n1": {
                "mandatory_actions": ["give_alteplase_pe"],
                "forbidden_actions": ["give_alteplase_pe"],
            }
        },
    }
    patient = {"vitals": {"sbp": 100}, "comorbidities": [], "allergies": []}
    result = cde.derive(graph, patient, scenario_id="static-conflict")

    assert any(
        c.actions == ["give_alteplase_pe"] and c.constraint_type == "CONFLICT"
        for c in result.conflicts
    )
    # The action MUST NOT be in the expected list (silent drop replaced by surfacing)
    assert all(c.actions != ["give_alteplase_pe"] for c in result.expected)


def test_cde_no_conflict_when_unrelated(cde: ConstraintDerivationEngine) -> None:
    """REQUIRED on action_a and FORBIDDEN on action_b -> no conflict."""
    graph = {
        "graph_id": "test_unrelated",
        "nodes": {
            "init": {
                "mandatory_actions": [],
                "forbidden_actions": [],
                "conditional_rules": [
                    {
                        "rule_id": "R1",
                        "condition": "patient.age > 18",
                        "effect": {"type": "REQUIRED", "actions": ["give_action_a"]},
                        "severity": "HIGH",
                        "description": "",
                    },
                    {
                        "rule_id": "R2",
                        "condition": "patient.age > 18",
                        "effect": {"type": "FORBIDDEN", "actions": ["give_action_b"]},
                        "severity": "HIGH",
                        "description": "",
                    },
                ],
            }
        },
    }
    patient = {"age": 55, "comorbidities": [], "allergies": []}
    result = cde.derive(graph, patient, scenario_id="unrelated")
    assert result.conflicts == []


def test_cde_idempotent(cde: ConstraintDerivationEngine) -> None:
    """Calling derive() twice with same inputs -> identical conflict count."""
    patient = {
        "vitals": {"sbp": 80},
        "comorbidities": ["recent_surgery"],
        "allergies": [],
    }
    r1 = cde.derive(_scn012_graph(), patient, scenario_id="idem")
    r2 = cde.derive(_scn012_graph(), patient, scenario_id="idem")
    assert len(r1.conflicts) == len(r2.conflicts) == 1
    assert r1.conflicts[0].actions == r2.conflicts[0].actions


def test_dcs_to_yaml_includes_conflicts(cde: ConstraintDerivationEngine) -> None:
    """DerivedConstraintSet.to_yaml() exposes conflicts channel for audit pipelines."""
    patient = {
        "vitals": {"sbp": 80},
        "comorbidities": ["recent_surgery"],
        "allergies": [],
    }
    result: DerivedConstraintSet = cde.derive(_scn012_graph(), patient, scenario_id="yaml-test")
    payload = result.to_yaml()
    assert "conflicts" in payload
    assert payload["conflicts"]
    assert payload["conflicts"][0]["constraint_type"] == "CONFLICT"


def test_dcs_audit_row_reports_num_conflicts(cde: ConstraintDerivationEngine) -> None:
    """audit_row exposes num_conflicts for the Rule Coverage Audit Matrix."""
    patient = {
        "vitals": {"sbp": 80},
        "comorbidities": ["recent_surgery"],
        "allergies": [],
    }
    result = cde.derive(_scn012_graph(), patient, scenario_id="audit-row")
    row = result.to_audit_row()
    assert row["num_conflicts"] == 1
