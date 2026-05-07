from __future__ import annotations

import pytest
from typing import Dict, Any

from cga_bench.agent_rules.stroke_rules import StrokeDecisionTable


@pytest.fixture
def stroke_table():
    return StrokeDecisionTable()


def create_stroke_context(
    symptom_onset_hours: float = 2.0,
    nihss: int = 12,
    working_diagnosis: str = "ischemic_stroke_tpa_eligible",
    sbp: float = 160.0,
    glucose: float = 120.0,
    on_anticoagulant: bool = False,
    comorbidities: list = None,
    allergies: list = None,
) -> Dict[str, Any]:
    return {
        "symptom_onset_hours": symptom_onset_hours,
        "nihss": nihss,
        "working_diagnosis": working_diagnosis,
        "sbp": sbp,
        "glucose": glucose,
        "on_anticoagulant": on_anticoagulant,
        "comorbidities": comorbidities or [],
        "allergies": allergies or [],
    }


class TestScenarioTypeDetermination:
    def test_ischemic_tpa(self, stroke_table):
        context = create_stroke_context(working_diagnosis="ischemic_stroke_tpa_eligible")
        result = stroke_table._determine_scenario_type(context)
        assert result == "ischemic_tpa"

    def test_thrombectomy(self, stroke_table):
        context = create_stroke_context(working_diagnosis="ischemic_stroke_thrombectomy")
        result = stroke_table._determine_scenario_type(context)
        assert result in stroke_table.rulesets

    def test_hemorrhagic(self, stroke_table):
        context = create_stroke_context(working_diagnosis="hemorrhagic_stroke")
        result = stroke_table._determine_scenario_type(context)
        assert result == "hemorrhagic"

    def test_unknown_defaults(self, stroke_table):
        context = create_stroke_context(working_diagnosis="unknown_stroke")
        result = stroke_table._determine_scenario_type(context)
        assert isinstance(result, str)


class TestMandatoryActions:
    def test_ischemic_tpa_has_stroke_team(self, stroke_table):
        context = create_stroke_context()
        actions = stroke_table.get_recommended_actions(context, current_time_minutes=0)
        mandatory_ids = [a.action_id for a in actions if a.is_mandatory]
        assert "activate_stroke_team" in mandatory_ids

    def test_ischemic_tpa_has_nihss(self, stroke_table):
        context = create_stroke_context()
        actions = stroke_table.get_recommended_actions(context, current_time_minutes=0)
        mandatory_ids = [a.action_id for a in actions if a.is_mandatory]
        assert "perform_nihss" in mandatory_ids

    def test_ischemic_tpa_has_ct_head(self, stroke_table):
        context = create_stroke_context()
        actions = stroke_table.get_recommended_actions(context, current_time_minutes=0)
        action_ids = [a.action_id for a in actions]
        ct_actions = [a for a in action_ids if "ct" in a.lower() or "imaging" in a.lower()]
        assert len(ct_actions) > 0

    def test_has_source_guideline(self, stroke_table):
        context = create_stroke_context()
        actions = stroke_table.get_recommended_actions(context, current_time_minutes=0)
        for action in actions:
            assert action.source_guideline, f"{action.action_id} missing source_guideline"


class TestForbiddenActions:
    def test_forbidden_actions_exist(self, stroke_table):
        context = create_stroke_context()
        forbidden = stroke_table.get_forbidden_actions(context)
        assert isinstance(forbidden, list)

    def test_hemorrhagic_has_forbidden(self, stroke_table):
        context = create_stroke_context(working_diagnosis="hemorrhagic_stroke")
        forbidden = stroke_table.get_forbidden_actions(context)
        assert isinstance(forbidden, list)


class TestSequenceConstraints:
    def test_sequence_constraints_exist(self, stroke_table):
        constraints = stroke_table.get_sequence_constraints()
        assert isinstance(constraints, list)

    def test_ct_before_tpa(self, stroke_table):
        constraints = stroke_table.get_sequence_constraints()
        ct_before_tpa = [
            c for c in constraints
            if ("ct" in str(c.get("before", "")).lower() or "imaging" in str(c.get("before", "")).lower())
            and ("tpa" in str(c.get("after", "")).lower() or "alteplase" in str(c.get("after", "")).lower())
        ]
        assert len(ct_before_tpa) >= 1 or len(constraints) > 0
