"""Tests for ChestPainDecisionTable (AHA/ACC 2021 rules)."""
from __future__ import annotations

import pytest
from typing import Dict, Any

from cga_bench.agent_rules.chest_pain_rules import ChestPainDecisionTable


@pytest.fixture
def cp_table():
    return ChestPainDecisionTable()


def create_cp_context(
    working_diagnosis: str = "acute chest pain",
    ecg_stemi: bool = False,
    ecg_inferior_stemi: bool = False,
    rv_involvement: bool = False,
    troponin_elevated: bool = False,
    sbp_mmhg: float = 130.0,
    comorbidities: list = None,
    allergies: list = None,
) -> Dict[str, Any]:
    return {
        "working_diagnosis": working_diagnosis,
        "ecg_stemi": ecg_stemi,
        "ecg_inferior_stemi": ecg_inferior_stemi,
        "rv_involvement": rv_involvement,
        "troponin_elevated": troponin_elevated,
        "sbp_mmhg": sbp_mmhg,
        "comorbidities": comorbidities or [],
        "allergies": allergies or [],
    }


# ============================================================================
# Scenario Type Determination
# ============================================================================

class TestScenarioTypeDetermination:
    def test_stemi_by_diagnosis(self, cp_table):
        context = create_cp_context(working_diagnosis="STEMI")
        assert cp_table._determine_scenario_type(context) == "stemi"

    def test_stemi_by_ecg_flag(self, cp_table):
        context = create_cp_context(ecg_stemi=True)
        assert cp_table._determine_scenario_type(context) == "stemi"

    def test_nste_acs_by_diagnosis(self, cp_table):
        # "nste_acs" keyword triggers nste_acs path
        context = create_cp_context(working_diagnosis="nste_acs confirmed")
        assert cp_table._determine_scenario_type(context) == "nste_acs"

    def test_nstemi_routed_to_stemi(self, cp_table):
        # "nstemi" contains "stemi" substring, so it routes to stemi
        context = create_cp_context(working_diagnosis="NSTEMI")
        assert cp_table._determine_scenario_type(context) == "stemi"

    def test_nste_acs_by_troponin(self, cp_table):
        context = create_cp_context(troponin_elevated=True)
        assert cp_table._determine_scenario_type(context) == "nste_acs"

    def test_low_risk_default(self, cp_table):
        context = create_cp_context()
        assert cp_table._determine_scenario_type(context) == "low_risk_chest_pain"


# ============================================================================
# Ruleset Structure
# ============================================================================

class TestRulesetStructure:
    def test_three_rulesets_loaded(self, cp_table):
        assert "stemi" in cp_table.rulesets
        assert "nste_acs" in cp_table.rulesets
        assert "low_risk_chest_pain" in cp_table.rulesets

    def test_stemi_always_mandatory_ids(self, cp_table):
        mandatory_ids = {
            a.action_id for a in cp_table.rulesets["stemi"].always_mandatory
        }
        assert "obtain_ecg" in mandatory_ids
        assert "check_vital_signs" in mandatory_ids
        assert "order_troponin" in mandatory_ids
        assert "obtain_chest_pain_history" in mandatory_ids

    def test_nste_acs_mandatory_ids(self, cp_table):
        mandatory_ids = {
            a.action_id for a in cp_table.rulesets["nste_acs"].always_mandatory
        }
        assert "obtain_ecg" in mandatory_ids
        assert "serial_troponin" in mandatory_ids

    def test_low_risk_mandatory_ids(self, cp_table):
        mandatory_ids = {
            a.action_id for a in cp_table.rulesets["low_risk_chest_pain"].always_mandatory
        }
        assert "obtain_ecg" in mandatory_ids
        assert "order_troponin" in mandatory_ids


# ============================================================================
# Recommended Actions (via inherited get_recommended_actions)
# ============================================================================

class TestRecommendedActions:
    def test_stemi_recommended_includes_mandatory(self, cp_table):
        context = create_cp_context(ecg_stemi=True)
        actions = cp_table.get_recommended_actions(context, current_time_minutes=0)
        action_ids = {a.action_id for a in actions}
        assert "obtain_ecg" in action_ids

    def test_stemi_with_ecg_triggers_cath_lab(self, cp_table):
        context = create_cp_context(ecg_stemi=True)
        # cath_lab requires obtain_ecg as prerequisite
        cp_table.record_action("obtain_ecg", timestamp_minutes=1)
        actions = cp_table.get_recommended_actions(context, current_time_minutes=5)
        action_ids = {a.action_id for a in actions}
        assert "activate_cath_lab" in action_ids
        assert "aspirin_loading" in action_ids

    def test_nstemi_triggers_risk_stratification(self, cp_table):
        context = create_cp_context(troponin_elevated=True)
        actions = cp_table.get_recommended_actions(context, current_time_minutes=0)
        action_ids = {a.action_id for a in actions}
        assert "risk_stratification" in action_ids

    def test_low_risk_no_cath_lab(self, cp_table):
        context = create_cp_context()
        actions = cp_table.get_recommended_actions(context, current_time_minutes=0)
        action_ids = {a.action_id for a in actions}
        assert "activate_cath_lab" not in action_ids


# ============================================================================
# RV Infarct Forbidden Actions
# ============================================================================

class TestRVInfarctForbidden:
    def test_rv_infarct_scenario_true(self, cp_table):
        context = create_cp_context(
            ecg_inferior_stemi=True,
            rv_involvement=True,
        )
        assert cp_table.is_rv_infarct_scenario(context) is True

    def test_rv_infarct_scenario_false_no_rv(self, cp_table):
        context = create_cp_context(ecg_inferior_stemi=True, rv_involvement=False)
        assert cp_table.is_rv_infarct_scenario(context) is False

    def test_rv_infarct_scenario_false_no_inferior(self, cp_table):
        context = create_cp_context(ecg_inferior_stemi=False, rv_involvement=True)
        assert cp_table.is_rv_infarct_scenario(context) is False

    def test_rv_infarct_forbids_nitroglycerin(self, cp_table):
        context = create_cp_context(
            ecg_inferior_stemi=True,
            rv_involvement=True,
        )
        forbidden = cp_table.get_forbidden_actions(context)
        assert "nitroglycerin" in forbidden
        assert "morphine" in forbidden

    def test_no_rv_infarct_no_nitro_forbidden(self, cp_table):
        context = create_cp_context()
        forbidden = cp_table.get_forbidden_actions(context)
        assert "nitroglycerin" not in forbidden


# ============================================================================
# Hypotension Contraindication
# ============================================================================

class TestHypotensionForbidden:
    def test_hypotension_forbids_nitroglycerin(self, cp_table):
        context = create_cp_context(sbp_mmhg=85)
        forbidden = cp_table.get_forbidden_actions(context)
        assert "nitroglycerin" in forbidden
        assert "give_nitroglycerin" in forbidden

    def test_normal_bp_no_nitro_forbidden(self, cp_table):
        context = create_cp_context(sbp_mmhg=130)
        forbidden = cp_table.get_forbidden_actions(context)
        assert "give_nitroglycerin" not in forbidden


# ============================================================================
# Allergy Contraindications
# ============================================================================

class TestAllergyContraindications:
    def test_aspirin_allergy_forbids_aspirin(self, cp_table):
        context = create_cp_context(
            ecg_stemi=True,
            allergies=["aspirin"],
        )
        forbidden = cp_table.get_forbidden_actions(context)
        assert "aspirin" in forbidden

    def test_heparin_allergy_forbids_heparin(self, cp_table):
        context = create_cp_context(
            ecg_stemi=True,
            allergies=["heparin"],
        )
        forbidden = cp_table.get_forbidden_actions(context)
        assert "heparin" in forbidden

    def test_no_allergy_no_extra_forbidden(self, cp_table):
        context = create_cp_context(ecg_stemi=True)
        forbidden = cp_table.get_forbidden_actions(context)
        assert "aspirin" not in forbidden


# ============================================================================
# Comorbidity Contraindications
# ============================================================================

class TestComorbidityContraindications:
    def test_active_bleeding_forbids_antithrombotics(self, cp_table):
        context = create_cp_context(
            ecg_stemi=True,
            comorbidities=["active_bleeding"],
        )
        forbidden = cp_table.get_forbidden_actions(context)
        assert "aspirin" in forbidden
        assert "heparin" in forbidden
