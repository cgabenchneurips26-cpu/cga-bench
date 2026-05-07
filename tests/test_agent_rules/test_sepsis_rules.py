"""Tests for SepsisDecisionTable (SSC 2021 rules)."""
from __future__ import annotations

import pytest
from typing import Dict, Any

from cga_bench.agent_rules.sepsis_rules import SepsisDecisionTable


@pytest.fixture
def sepsis_table():
    return SepsisDecisionTable()


def create_sepsis_context(
    map_mmhg: float = 70.0,
    lactate: float = 1.0,
    sbp_mmhg: float = 100.0,
    vasopressor_required: bool = False,
    fluid_resuscitation_complete: bool = False,
    working_diagnosis: str = "suspected sepsis",
    comorbidities: list = None,
    allergies: list = None,
) -> Dict[str, Any]:
    return {
        "map_mmhg": map_mmhg,
        "lactate": lactate,
        "sbp_mmhg": sbp_mmhg,
        "vasopressor_required": vasopressor_required,
        "fluid_resuscitation_complete": fluid_resuscitation_complete,
        "working_diagnosis": working_diagnosis,
        "comorbidities": comorbidities or [],
        "allergies": allergies or [],
    }


# ============================================================================
# Scenario Type Determination
# ============================================================================

class TestScenarioTypeDetermination:
    def test_septic_shock_by_diagnosis(self, sepsis_table):
        context = create_sepsis_context(working_diagnosis="septic_shock")
        assert sepsis_table._determine_scenario_type(context) == "septic_shock"

    def test_septic_shock_by_low_map(self, sepsis_table):
        context = create_sepsis_context(map_mmhg=55)
        assert sepsis_table._determine_scenario_type(context) == "septic_shock"

    def test_septic_shock_by_vasopressor(self, sepsis_table):
        context = create_sepsis_context(vasopressor_required=True)
        assert sepsis_table._determine_scenario_type(context) == "septic_shock"

    def test_septic_shock_by_elevated_lactate(self, sepsis_table):
        context = create_sepsis_context(lactate=4.0)
        assert sepsis_table._determine_scenario_type(context) == "septic_shock"

    def test_sepsis_without_shock(self, sepsis_table):
        context = create_sepsis_context(map_mmhg=80, lactate=1.0)
        assert sepsis_table._determine_scenario_type(context) == "sepsis"

    def test_type_safe_pending_values(self, sepsis_table):
        """Non-numeric map/lactate values should not crash."""
        context = create_sepsis_context()
        context["map_mmhg"] = "pending"
        context["lactate"] = "pending"
        result = sepsis_table._determine_scenario_type(context)
        assert result in ("sepsis", "septic_shock")

    def test_type_safe_none_values(self, sepsis_table):
        context = create_sepsis_context()
        context["map_mmhg"] = None
        context["lactate"] = None
        result = sepsis_table._determine_scenario_type(context)
        assert result in ("sepsis", "septic_shock")


# ============================================================================
# Ruleset Structure
# ============================================================================

class TestRulesetStructure:
    def test_two_rulesets_loaded(self, sepsis_table):
        assert "septic_shock" in sepsis_table.rulesets
        assert "sepsis" in sepsis_table.rulesets

    def test_septic_shock_mandatory_ids(self, sepsis_table):
        mandatory_ids = {
            a.action_id for a in sepsis_table.rulesets["septic_shock"].always_mandatory
        }
        assert "measure_lactate" in mandatory_ids
        assert "blood_culture_before_antibiotics" in mandatory_ids
        assert "broad_spectrum_antibiotics" in mandatory_ids
        assert "assess_infection_source" in mandatory_ids
        assert "assess_organ_dysfunction" in mandatory_ids

    def test_sepsis_mandatory_ids(self, sepsis_table):
        mandatory_ids = {
            a.action_id for a in sepsis_table.rulesets["sepsis"].always_mandatory
        }
        assert "measure_lactate" in mandatory_ids
        assert "blood_culture_before_antibiotics" in mandatory_ids
        assert "broad_spectrum_antibiotics" in mandatory_ids

    def test_septic_shock_has_forbidden(self, sepsis_table):
        forbidden_ids = {
            a.action_id for a in sepsis_table.rulesets["septic_shock"].always_forbidden
        }
        assert "delay_antibiotics_over_3h" in forbidden_ids


# ============================================================================
# Recommended Actions
# ============================================================================

class TestRecommendedActions:
    def test_septic_shock_includes_mandatory(self, sepsis_table):
        context = create_sepsis_context(working_diagnosis="septic_shock")
        actions = sepsis_table.get_recommended_actions(context, current_time_minutes=0)
        action_ids = {a.action_id for a in actions}
        assert "measure_lactate" in action_ids
        assert "blood_culture_before_antibiotics" in action_ids

    def test_hypotension_triggers_crystalloid(self, sepsis_table):
        context = create_sepsis_context(map_mmhg=55)
        actions = sepsis_table.get_recommended_actions(context, current_time_minutes=0)
        action_ids = {a.action_id for a in actions}
        assert "crystalloid_30ml_kg" in action_ids

    def test_vasopressor_after_fluids(self, sepsis_table):
        context = create_sepsis_context(
            map_mmhg=55,
            fluid_resuscitation_complete=True,
        )
        # norepinephrine requires crystalloid_30ml_kg as prerequisite
        sepsis_table.record_action("crystalloid_30ml_kg", timestamp_minutes=30)
        actions = sepsis_table.get_recommended_actions(context, current_time_minutes=35)
        action_ids = {a.action_id for a in actions}
        assert "start_norepinephrine" in action_ids

    def test_elevated_lactate_triggers_remeasure(self, sepsis_table):
        context = create_sepsis_context(lactate=3.5)
        # remeasure requires measure_lactate as prerequisite
        sepsis_table.record_action("measure_lactate", timestamp_minutes=5)
        actions = sepsis_table.get_recommended_actions(context, current_time_minutes=10)
        action_ids = {a.action_id for a in actions}
        assert "remeasure_lactate" in action_ids

    def test_normal_lactate_no_remeasure(self, sepsis_table):
        context = create_sepsis_context(map_mmhg=80, lactate=1.5)
        actions = sepsis_table.get_recommended_actions(context, current_time_minutes=0)
        action_ids = {a.action_id for a in actions}
        assert "remeasure_lactate" not in action_ids


# ============================================================================
# Sequence Constraints
# ============================================================================

class TestSequenceConstraints:
    def test_antibiotics_require_blood_culture(self, sepsis_table):
        shock = sepsis_table.rulesets["septic_shock"]
        abx = next(
            a for a in shock.always_mandatory
            if a.action_id == "broad_spectrum_antibiotics"
        )
        assert "blood_culture_before_antibiotics" in abx.required_prior_actions

    def test_norepinephrine_requires_crystalloid(self, sepsis_table):
        shock = sepsis_table.rulesets["septic_shock"]
        for entry in shock.decision_entries:
            for a in entry.actions:
                if a.action_id == "start_norepinephrine":
                    assert "crystalloid_30ml_kg" in a.required_prior_actions


# ============================================================================
# Forbidden Actions
# ============================================================================

class TestForbiddenActions:
    def test_delay_antibiotics_forbidden(self, sepsis_table):
        context = create_sepsis_context(working_diagnosis="septic_shock")
        forbidden = sepsis_table.get_forbidden_actions(context)
        assert "delay_antibiotics_over_3h" in forbidden


# ============================================================================
# Allergy Contraindications
# ============================================================================

class TestAllergyContraindications:
    def test_penicillin_allergy_forbids_related(self, sepsis_table):
        context = create_sepsis_context(
            working_diagnosis="septic_shock",
            allergies=["penicillin"],
        )
        forbidden = sepsis_table.get_forbidden_actions(context)
        assert "ampicillin" in forbidden
        assert "piperacillin" in forbidden

    def test_cephalosporin_allergy_forbids_related(self, sepsis_table):
        context = create_sepsis_context(
            working_diagnosis="septic_shock",
            allergies=["cephalosporin"],
        )
        forbidden = sepsis_table.get_forbidden_actions(context)
        assert "ceftriaxone" in forbidden
        assert "cefepime" in forbidden

    def test_no_allergy_no_drug_forbidden(self, sepsis_table):
        context = create_sepsis_context(working_diagnosis="septic_shock")
        forbidden = sepsis_table.get_forbidden_actions(context)
        assert "ampicillin" not in forbidden


# ============================================================================
# Comorbidity Contraindications
# ============================================================================

class TestComorbidityContraindications:
    def test_ckd_stage5_forbids_nsaid(self, sepsis_table):
        context = create_sepsis_context(
            working_diagnosis="septic_shock",
            comorbidities=["ckd_stage_5"],
        )
        forbidden = sepsis_table.get_forbidden_actions(context)
        assert "nsaid" in forbidden

    def test_heart_failure_forbids_aggressive_fluid(self, sepsis_table):
        context = create_sepsis_context(
            working_diagnosis="septic_shock",
            comorbidities=["heart_failure"],
        )
        forbidden = sepsis_table.get_forbidden_actions(context)
        assert "aggressive_fluid_bolus" in forbidden


# ============================================================================
# Deadline Verification
# ============================================================================

class TestDeadlines:
    def test_septic_shock_antibiotics_within_60_min(self, sepsis_table):
        shock = sepsis_table.rulesets["septic_shock"]
        abx = next(
            a for a in shock.always_mandatory
            if a.action_id == "broad_spectrum_antibiotics"
        )
        assert abx.deadline_minutes == 60

    def test_sepsis_antibiotics_within_180_min(self, sepsis_table):
        sepsis = sepsis_table.rulesets["sepsis"]
        abx = next(
            a for a in sepsis.always_mandatory
            if a.action_id == "broad_spectrum_antibiotics"
        )
        assert abx.deadline_minutes == 180
