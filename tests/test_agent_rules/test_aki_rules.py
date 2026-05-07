from __future__ import annotations

import pytest
from typing import Dict, Any

from cga_bench.agent_rules.aki_rules import AKIDecisionTable


@pytest.fixture
def aki_table():
    return AKIDecisionTable()


def create_aki_context(
    creatinine: float = 2.5,
    baseline_creatinine: float = 1.0,
    urine_output_ml_hr: float = 25.0,
    working_diagnosis: str = "aki_stage1",
    potassium: float = 4.8,
    ph: float = 7.35,
    comorbidities: list = None,
    allergies: list = None,
) -> Dict[str, Any]:
    return {
        "creatinine": creatinine,
        "baseline_creatinine": baseline_creatinine,
        "urine_output_ml_hr": urine_output_ml_hr,
        "working_diagnosis": working_diagnosis,
        "potassium": potassium,
        "ph": ph,
        "comorbidities": comorbidities or [],
        "allergies": allergies or [],
    }


class TestScenarioTypeDetermination:
    def test_aki_stage1(self, aki_table):
        context = create_aki_context(creatinine=1.8, baseline_creatinine=1.0, working_diagnosis="aki")
        result = aki_table._determine_scenario_type(context)
        assert result in aki_table.rulesets

    def test_aki_stage2(self, aki_table):
        context = create_aki_context(creatinine=2.5, baseline_creatinine=1.0, working_diagnosis="aki")
        result = aki_table._determine_scenario_type(context)
        assert result in aki_table.rulesets

    def test_aki_stage3(self, aki_table):
        context = create_aki_context(creatinine=4.0, baseline_creatinine=1.0, urine_output_ml_hr=5.0, working_diagnosis="aki")
        result = aki_table._determine_scenario_type(context)
        assert result in aki_table.rulesets

    def test_contrast_induced(self, aki_table):
        context = create_aki_context(working_diagnosis="contrast_induced_aki")
        result = aki_table._determine_scenario_type(context)
        assert result == "ci_aki_prevention"


class TestMandatoryActions:
    def test_stage1_has_creatinine(self, aki_table):
        context = create_aki_context()
        actions = aki_table.get_recommended_actions(context, current_time_minutes=0)
        mandatory_ids = [a.action_id for a in actions if a.is_mandatory]
        assert "order_creatinine" in mandatory_ids

    def test_stage1_has_urine_monitoring(self, aki_table):
        context = create_aki_context()
        actions = aki_table.get_recommended_actions(context, current_time_minutes=0)
        mandatory_ids = [a.action_id for a in actions if a.is_mandatory]
        assert "monitor_urine_output" in mandatory_ids

    def test_stage1_has_volume_optimization(self, aki_table):
        context = create_aki_context()
        actions = aki_table.get_recommended_actions(context, current_time_minutes=0)
        action_ids = [a.action_id for a in actions]
        assert any("volume" in a or "nephrotox" in a or "potassium" in a for a in action_ids)

    def test_actions_have_source_guideline(self, aki_table):
        context = create_aki_context()
        actions = aki_table.get_recommended_actions(context, current_time_minutes=0)
        for action in actions:
            assert action.source_guideline, f"{action.action_id} missing source_guideline"

    def test_actions_have_evidence_level(self, aki_table):
        context = create_aki_context()
        actions = aki_table.get_recommended_actions(context, current_time_minutes=0)
        for action in actions[:5]:
            assert action.evidence_level, f"{action.action_id} missing evidence_level"


class TestForbiddenActions:
    def test_forbidden_actions_list(self, aki_table):
        context = create_aki_context()
        forbidden = aki_table.get_forbidden_actions(context)
        assert isinstance(forbidden, list)


class TestSequenceConstraints:
    def test_sequence_constraints_list(self, aki_table):
        constraints = aki_table.get_sequence_constraints()
        assert isinstance(constraints, list)


class TestConditionalActions:
    def test_stage3_has_more_actions_than_stage1(self, aki_table):
        ctx1 = create_aki_context(working_diagnosis="aki_stage1")
        ctx3 = create_aki_context(working_diagnosis="aki_stage3")
        actions1 = aki_table.get_recommended_actions(ctx1, current_time_minutes=0)
        actions3 = aki_table.get_recommended_actions(ctx3, current_time_minutes=0)
        assert len(actions3) >= len(actions1)
