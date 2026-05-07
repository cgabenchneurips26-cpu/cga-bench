from __future__ import annotations

import pytest
from typing import Dict, Any

from cga_bench.agent_rules.heart_failure_rules import HeartFailureDecisionTable


@pytest.fixture
def hf_table():
    return HeartFailureDecisionTable()


def create_hf_context(
    ef: float = 30.0,
    bnp: float = 1200.0,
    working_diagnosis: str = "hfref",
    nyha_class: int = 3,
    sbp: float = 110.0,
    creatinine: float = 1.2,
    potassium: float = 4.2,
    comorbidities: list = None,
    allergies: list = None,
) -> Dict[str, Any]:
    return {
        "ef": ef,
        "bnp": bnp,
        "working_diagnosis": working_diagnosis,
        "nyha_class": nyha_class,
        "sbp": sbp,
        "creatinine": creatinine,
        "potassium": potassium,
        "comorbidities": comorbidities or [],
        "allergies": allergies or [],
    }


class TestScenarioTypeDetermination:
    def test_hfref(self, hf_table):
        context = create_hf_context(working_diagnosis="hfref")
        assert hf_table._determine_scenario_type(context) == "hfref"

    def test_adhf(self, hf_table):
        context = create_hf_context(working_diagnosis="adhf")
        result = hf_table._determine_scenario_type(context)
        assert result.startswith("adhf")

    def test_cardiogenic_shock(self, hf_table):
        context = create_hf_context(working_diagnosis="cardiogenic_shock")
        assert hf_table._determine_scenario_type(context) == "cardiogenic_shock"


class TestMandatoryActions:
    def test_hfref_has_history(self, hf_table):
        context = create_hf_context()
        actions = hf_table.get_recommended_actions(context, current_time_minutes=0)
        mandatory_ids = [a.action_id for a in actions if a.is_mandatory]
        assert "obtain_history" in mandatory_ids

    def test_hfref_has_bnp(self, hf_table):
        context = create_hf_context()
        actions = hf_table.get_recommended_actions(context, current_time_minutes=0)
        mandatory_ids = [a.action_id for a in actions if a.is_mandatory]
        assert "order_bnp_or_ntprobnp" in mandatory_ids

    def test_actions_have_source(self, hf_table):
        context = create_hf_context()
        actions = hf_table.get_recommended_actions(context, current_time_minutes=0)
        for action in actions:
            assert action.source_guideline, f"{action.action_id} missing source_guideline"

    def test_actions_have_priority(self, hf_table):
        context = create_hf_context()
        actions = hf_table.get_recommended_actions(context, current_time_minutes=0)
        priorities = [a.priority for a in actions]
        assert all(isinstance(p, int) for p in priorities)


class TestForbiddenActions:
    def test_forbidden_actions_exist(self, hf_table):
        context = create_hf_context()
        forbidden = hf_table.get_forbidden_actions(context)
        assert isinstance(forbidden, list)


class TestSequenceConstraints:
    def test_sequence_constraints_exist(self, hf_table):
        constraints = hf_table.get_sequence_constraints()
        assert isinstance(constraints, list)
