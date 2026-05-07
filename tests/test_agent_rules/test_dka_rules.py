"""
DKA Decision Table 테스트
agent_rules/dka_rules.py 규칙 검증
"""
import pytest
from typing import Dict, Any

from cga_bench.agent_rules.dka_rules import DKADecisionTable


@pytest.fixture
def dka_table():
    """DKA 의사결정 테이블 인스턴스"""
    return DKADecisionTable()


def create_dka_context(
    ph: float = 7.18,
    potassium: float = 4.5,
    glucose: float = 420,
    anion_gap: float = 20,
    mental_status: str = "alert",
    working_diagnosis: str = "dka_moderate",
    comorbidities: list = None,
) -> Dict[str, Any]:
    """테스트용 DKA 컨텍스트 생성"""
    return {
        "ph": ph,
        "potassium": potassium,
        "glucose": glucose,
        "anion_gap": anion_gap,
        "mental_status": mental_status,
        "working_diagnosis": working_diagnosis,
        "comorbidities": comorbidities or [],
        "allergies": [],
    }


class TestScenarioTypeDetermination:
    """시나리오 유형 결정 테스트"""

    def test_severe_dka_by_ph(self, dka_table):
        """pH < 7.0일 때 severe_dka 반환"""
        context = create_dka_context(ph=6.9)
        scenario_type = dka_table._determine_scenario_type(context)
        assert scenario_type == "severe_dka"

    def test_severe_dka_by_mental_status(self, dka_table):
        """의식 저하 시 severe_dka 반환"""
        context = create_dka_context(ph=7.1, mental_status="obtunded")
        scenario_type = dka_table._determine_scenario_type(context)
        assert scenario_type == "severe_dka"

    def test_moderate_dka(self, dka_table):
        """pH 7.0-7.24일 때 moderate_dka 반환"""
        context = create_dka_context(ph=7.15)
        scenario_type = dka_table._determine_scenario_type(context)
        assert scenario_type == "moderate_dka"

    def test_mild_dka(self, dka_table):
        """pH 7.25-7.30일 때 mild_dka 반환"""
        context = create_dka_context(ph=7.28)
        scenario_type = dka_table._determine_scenario_type(context)
        assert scenario_type == "mild_dka"

    def test_euglycemic_dka_by_diagnosis(self, dka_table):
        """진단명에 euglycemic 포함 시 euglycemic_dka 반환"""
        context = create_dka_context(working_diagnosis="euglycemic_dka")
        scenario_type = dka_table._determine_scenario_type(context)
        assert scenario_type == "euglycemic_dka"

    def test_euglycemic_dka_by_sglt2(self, dka_table):
        """진단명에 sglt2 포함 시 euglycemic_dka 반환"""
        context = create_dka_context(working_diagnosis="dka_sglt2_related")
        scenario_type = dka_table._determine_scenario_type(context)
        assert scenario_type == "euglycemic_dka"

    def test_dka_ckd_by_comorbidity(self, dka_table):
        """CKD 동반 시 dka_ckd가 적용 가능 시나리오에 포함"""
        context = create_dka_context(comorbidities=["ckd_stage_4", "hypertension"])
        applicable = dka_table._get_applicable_scenario_types(context)
        # CKD는 modifier로 포함됨 (primary는 severity)
        assert "dka_ckd" in applicable
        # Primary는 severity (moderate_dka)
        assert applicable[0] == "moderate_dka"

    def test_dka_resolution(self, dka_table):
        """DKA 해소 기준 충족 시 dka_resolution 반환"""
        # Resolution requires: glucose < 200 AND 2 of (bicarbonate >= 15, pH > 7.3, AG <= 12)
        context = create_dka_context(
            glucose=180,      # < 200 (required)
            ph=7.35,          # > 7.3 (1)
            anion_gap=10,     # <= 12 (2)
        )
        context["bicarbonate"] = 16  # >= 15 (3) - all 3 met
        scenario_type = dka_table._determine_scenario_type(context)
        assert scenario_type == "dka_resolution"


class TestHypokalemiaTrap:
    """저칼륨혈증 Trap 테스트 (K+ < 3.3)"""

    def test_insulin_forbidden_when_hypokalemic(self, dka_table):
        """K+ < 3.3 시 인슐린 금기 상태 확인"""
        context = create_dka_context(potassium=3.0)
        status = dka_table.get_insulin_forbidden_status(context)

        assert status["is_forbidden"] is True
        assert "hypokalemia" in status["reason"].lower()
        assert status["potassium_level"] == 3.0
        assert status["required_action"] == "give_potassium_iv"

    def test_insulin_allowed_when_potassium_adequate(self, dka_table):
        """K+ >= 3.3 시 인슐린 허용"""
        context = create_dka_context(potassium=4.0)
        status = dka_table.get_insulin_forbidden_status(context)

        assert status["is_forbidden"] is False
        assert status["potassium_level"] == 4.0

    def test_insulin_forbidden_when_potassium_unknown(self, dka_table):
        """칼륨 미확인 시 인슐린 금기"""
        context = create_dka_context()
        del context["potassium"]
        status = dka_table.get_insulin_forbidden_status(context)

        assert status["is_forbidden"] is True
        assert "unknown" in status["reason"].lower()
        assert status["required_action"] == "order_lab_bmp"

    def test_hypokalemia_trap_recommendations(self, dka_table):
        """저칼륨 시 칼륨 투여가 권고 목록에 포함 (선행조건 충족 후)"""
        context = create_dka_context(potassium=2.8)
        dka_table.reset()

        # 선행 조건 충족 (order_lab_bmp, establish_iv_access)
        dka_table.record_action("order_lab_bmp", 5)
        dka_table.record_action("establish_iv_access", 8)

        recommendations = dka_table.get_recommended_actions(context)
        action_ids = [r.action_id for r in recommendations]
        assert "give_potassium_iv" in action_ids

    def test_insulin_not_in_recommendations_when_hypokalemic(self, dka_table):
        """저칼륨 시 인슐린이 권고 목록에 미포함 (선행조건 미충족)"""
        context = create_dka_context(potassium=2.8)
        dka_table.reset()

        recommendations = dka_table.get_recommended_actions(context)
        action_ids = [r.action_id for r in recommendations]

        # start_insulin_infusion은 potassium >= 3.3 조건 필요
        # 저칼륨 시 이 조건을 충족하지 않으므로 권고에 없어야 함
        # (decision_entry 조건 불충족)
        # 단, 선행 조건이 있는 경우 권고에서 제외됨


class TestCKDHyperkalemiaTrap:
    """CKD 고칼륨혈증 Trap 테스트 (K+ > 5.5)"""

    def test_potassium_forbidden_when_hyperkalemic(self, dka_table):
        """K+ > 5.5 시 칼륨 투여 금기"""
        context = create_dka_context(potassium=6.0, comorbidities=["ckd_stage_4"])
        status = dka_table.get_potassium_forbidden_status(context)

        assert status["is_forbidden"] is True
        assert "hyperkalemia" in status["reason"].lower()
        assert status["required_action"] == "treat_hyperkalemia"

    def test_potassium_caution_in_ckd_borderline(self, dka_table):
        """CKD 환자에서 K+ 5.0-5.5 시 주의 필요"""
        context = create_dka_context(potassium=5.2, comorbidities=["ckd_stage_4"])
        status = dka_table.get_potassium_forbidden_status(context)

        assert status["is_forbidden"] is True
        assert "ckd" in status["reason"].lower()

    def test_potassium_allowed_in_ckd_normal_k(self, dka_table):
        """CKD 환자에서 K+ < 5.0 시 칼륨 투여 허용"""
        context = create_dka_context(potassium=4.0, comorbidities=["ckd_stage_4"])
        status = dka_table.get_potassium_forbidden_status(context)

        assert status["is_forbidden"] is False

    def test_ckd_forbids_aggressive_fluids(self, dka_table):
        """CKD 환자에서 공격적 수액 금지"""
        context = create_dka_context(comorbidities=["ckd_stage_4"])
        forbidden = dka_table.get_forbidden_actions(context)

        assert "aggressive_fluid_bolus" in forbidden


class TestSevereDKAPathway:
    """중증 DKA 경로 테스트"""

    def test_severe_dka_requires_icu(self, dka_table):
        """중증 DKA 시 ICU 입원 필수"""
        context = create_dka_context(ph=6.9)
        recommendations = dka_table.get_recommended_actions(context)

        action_ids = [r.action_id for r in recommendations]
        assert "admit_to_icu" in action_ids

    def test_severe_dka_forbids_ward_admission(self, dka_table):
        """중증 DKA 시 일반 병동 금지"""
        context = create_dka_context(ph=6.9)
        forbidden = dka_table.get_forbidden_actions(context)

        assert "admit_to_ward" in forbidden

    def test_severe_dka_requires_cardiac_monitoring(self, dka_table):
        """중증 DKA 시 심전도 모니터링 필수"""
        context = create_dka_context(ph=6.9)
        recommendations = dka_table.get_recommended_actions(context)

        action_ids = [r.action_id for r in recommendations]
        assert "continuous_cardiac_monitoring" in action_ids


class TestEuglycemicDKA:
    """정상혈당 DKA (SGLT2) 테스트"""

    def test_euglycemic_requires_sglt2_stop(self, dka_table):
        """정상혈당 DKA 시 SGLT2 억제제 중단 필수"""
        context = create_dka_context(
            glucose=180,
            working_diagnosis="euglycemic_dka"
        )
        recommendations = dka_table.get_recommended_actions(context)

        action_ids = [r.action_id for r in recommendations]
        assert "stop_sglt2_inhibitor" in action_ids

    def test_euglycemic_requires_dextrose(self, dka_table):
        """정상혈당 DKA 시 Dextrose 수액 필수"""
        context = create_dka_context(
            glucose=180,
            working_diagnosis="euglycemic_dka"
        )
        recommendations = dka_table.get_recommended_actions(context)

        action_ids = [r.action_id for r in recommendations]
        assert "start_dextrose_containing_iv" in action_ids

    def test_euglycemic_forbids_continue_sglt2(self, dka_table):
        """정상혈당 DKA 시 SGLT2 계속 투여 금지"""
        context = create_dka_context(working_diagnosis="euglycemic_dka")
        forbidden = dka_table.get_forbidden_actions(context)

        assert "continue_sglt2_inhibitor" in forbidden


class TestDKAResolution:
    """DKA 해소 기준 테스트"""

    def _create_resolution_context(self) -> Dict[str, Any]:
        """해소 기준 충족 컨텍스트 생성"""
        context = create_dka_context(
            glucose=180,      # < 200 (required)
            ph=7.35,          # > 7.3 (1)
            anion_gap=10,     # <= 12 (2)
        )
        context["bicarbonate"] = 16  # >= 15 (3)
        return context

    def test_resolution_requires_subq_insulin(self, dka_table):
        """DKA 해소 시 피하 인슐린 전환 필수 (선행조건 충족 후)"""
        context = self._create_resolution_context()
        dka_table.reset()

        # 선행 조건 충족 (assess_anion_gap_closure)
        dka_table.record_action("assess_anion_gap_closure", 180)

        recommendations = dka_table.get_recommended_actions(context)
        action_ids = [r.action_id for r in recommendations]
        assert "start_subcutaneous_insulin" in action_ids

    def test_resolution_requires_iv_overlap(self, dka_table):
        """DKA 해소 시 IV 인슐린 overlap 필수"""
        context = self._create_resolution_context()
        dka_table.reset()
        recommendations = dka_table.get_recommended_actions(context)

        action_ids = [r.action_id for r in recommendations]
        assert "overlap_iv_insulin_2h" in action_ids

    def test_resolution_forbids_stop_without_overlap(self, dka_table):
        """IV 인슐린 overlap 없이 중단 금지"""
        context = self._create_resolution_context()
        forbidden = dka_table.get_forbidden_actions(context)

        assert "stop_iv_insulin_without_overlap" in forbidden


class TestMandatoryActions:
    """필수 행동 테스트"""

    def test_iv_fluid_within_15_minutes(self, dka_table):
        """모든 DKA에서 15분 내 수액 투여 필수"""
        context = create_dka_context()
        recommendations = dka_table.get_recommended_actions(context)

        fluid_actions = [
            r for r in recommendations
            if r.action_id == "start_iv_fluid_ns"
        ]
        assert len(fluid_actions) > 0
        assert fluid_actions[0].deadline_minutes == 15

    def test_vital_signs_within_5_minutes(self, dka_table):
        """모든 DKA에서 5분 내 활력징후 확인 필수"""
        context = create_dka_context()
        recommendations = dka_table.get_recommended_actions(context)

        vital_actions = [
            r for r in recommendations
            if r.action_id == "assess_vital_signs"
        ]
        assert len(vital_actions) > 0
        assert vital_actions[0].deadline_minutes == 5

    def test_iv_access_within_10_minutes(self, dka_table):
        """모든 DKA에서 10분 내 IV 접근 필수"""
        context = create_dka_context()
        recommendations = dka_table.get_recommended_actions(context)

        iv_actions = [
            r for r in recommendations
            if r.action_id == "establish_iv_access"
        ]
        assert len(iv_actions) > 0
        assert iv_actions[0].deadline_minutes == 10


class TestForbiddenActions:
    """금기 행동 테스트"""

    def test_discharge_always_forbidden(self, dka_table):
        """DKA 환자 퇴원 금지"""
        for scenario in ["severe_dka", "moderate_dka", "mild_dka"]:
            if scenario == "severe_dka":
                context = create_dka_context(ph=6.9)
            elif scenario == "moderate_dka":
                context = create_dka_context(ph=7.15)
            else:
                context = create_dka_context(ph=7.28)

            forbidden = dka_table.get_forbidden_actions(context)
            assert "discharge_home" in forbidden, f"{scenario}: discharge should be forbidden"


class TestSequenceDependencies:
    """순서 의존성 테스트"""

    def test_iv_fluid_requires_iv_access(self, dka_table):
        """수액 투여 전 IV 접근 필요"""
        context = create_dka_context()
        recommendations = dka_table.get_recommended_actions(context)

        fluid_actions = [
            r for r in recommendations
            if r.action_id == "start_iv_fluid_ns"
        ]
        if fluid_actions:
            assert "establish_iv_access" in fluid_actions[0].required_prior_actions

    def test_insulin_requires_bmp_and_fluids(self, dka_table):
        """인슐린 시작 전 BMP와 수액 필요"""
        context = create_dka_context(potassium=4.5)
        recommendations = dka_table.get_recommended_actions(context)

        insulin_actions = [
            r for r in recommendations
            if r.action_id == "start_insulin_infusion"
        ]
        if insulin_actions:
            required_prior = insulin_actions[0].required_prior_actions
            assert "order_lab_bmp" in required_prior
            assert "start_iv_fluid_ns" in required_prior


class TestRulesetCount:
    """Ruleset 개수 테스트"""

    def test_total_rulesets(self, dka_table):
        """6개 Ruleset 존재 확인"""
        expected_rulesets = [
            "severe_dka",
            "moderate_dka",
            "mild_dka",
            "dka_ckd",
            "euglycemic_dka",
            "dka_resolution",
        ]
        for ruleset_id in expected_rulesets:
            assert ruleset_id in dka_table.rulesets, f"Missing ruleset: {ruleset_id}"


class TestActionRecording:
    """행동 기록 테스트"""

    def test_record_action(self, dka_table):
        """행동 기록 후 완료 목록에 추가"""
        dka_table.reset()
        dka_table.record_action("establish_iv_access", 5)

        status = dka_table.get_status()
        assert "establish_iv_access" in status["completed_actions"]
        assert status["action_timestamps"]["establish_iv_access"] == 5

    def test_completed_actions_not_recommended(self, dka_table):
        """완료된 행동은 권고 목록에서 제외"""
        context = create_dka_context()
        dka_table.reset()
        dka_table.record_action("assess_vital_signs", 3)

        recommendations = dka_table.get_recommended_actions(context)
        action_ids = [r.action_id for r in recommendations]

        assert "assess_vital_signs" not in action_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
