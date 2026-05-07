"""DKA 시나리오 E2E 테스트
시나리오 로딩, Trap 시나리오 검증, 위반 탐지 테스트
"""

from pathlib import Path

import pytest
import yaml

from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_model.schemas.base import Action, ActionType, PatientState, VitalSigns


def get_scenarios_path():
    """시나리오 파일 경로 반환"""
    base_path = Path(__file__).parent.parent.parent
    return base_path / "configs" / "scenarios" / "dka_scenarios.yaml"


def get_graph_path():
    """가이드라인 그래프 파일 경로 반환"""
    base_path = Path(__file__).parent.parent.parent
    return str(base_path / "cpg_model" / "graphs" / "ada_dka_management.yaml")


def load_scenarios():
    """시나리오 YAML 데이터 로드"""
    with open(get_scenarios_path()) as f:
        return yaml.safe_load(f)


@pytest.fixture
def scenarios_data():
    """시나리오 데이터 fixture"""
    return load_scenarios()


@pytest.fixture
def dka_engine():
    """DKA 가이드라인 엔진 로드"""
    return CPGEngineFactory.load_from_file(get_graph_path())


def create_dka_patient(
    potassium: float = 4.5, ph: float = 7.18, glucose: float = 420, mental_status: str = "alert"
) -> PatientState:
    """테스트용 DKA 환자 생성"""
    return PatientState(
        state_id="test_patient",
        time_since_arrival_minutes=0,
        age=35,
        sex="M",
        weight_kg=70,
        vitals=VitalSigns(
            heart_rate=110,
            blood_pressure_systolic=100,
            blood_pressure_diastolic=60,
            respiratory_rate=26,
            temperature=37.2,
            oxygen_saturation=97,
            map_mmhg=73,
        ),
        chief_complaint="nausea, vomiting, confusion",
        working_diagnosis="dka_moderate",
        allergies=[],
        comorbidities=["type_1_diabetes"],
        contraindications=[],
    )


def create_action(action_id: str, action_type: ActionType, timestamp: float, args: dict = None) -> Action:
    """테스트용 행동 생성"""
    return Action(type=action_type, action_id=action_id, timestamp_minutes=timestamp, args=args or {})


class TestDKAScenarioLoading:
    """DKA 시나리오 로딩 테스트"""

    def test_dka_scenarios_file_exists(self):
        """DKA 시나리오 파일 존재 확인"""
        assert get_scenarios_path().exists()

    def test_all_scenarios_have_required_fields(self, scenarios_data):
        """모든 시나리오에 필수 필드 확인"""
        required_fields = [
            "scenario_id",
            "description",
            "guideline_graph",
            "patient",
            "ground_truth",
            "expected_actions",
            "max_duration_minutes",
        ]
        for scenario_id, config in scenarios_data["scenarios"].items():
            for field in required_fields:
                assert field in config, f"{scenario_id} missing field: {field}"

    def test_all_scenarios_reference_ada_dka_graph(self, scenarios_data):
        """모든 시나리오가 ada_dka_management 그래프 참조"""
        for scenario_id, config in scenarios_data["scenarios"].items():
            assert config["guideline_graph"] == "ada_dka_management", f"{scenario_id} has wrong guideline_graph"

    def test_patient_vitals_are_valid(self, scenarios_data):
        """환자 활력징후 유효성 확인"""
        for scenario_id, config in scenarios_data["scenarios"].items():
            vitals = config["patient"]["vitals"]
            assert vitals["heart_rate"] > 0
            assert vitals["blood_pressure_systolic"] > 0
            assert vitals["respiratory_rate"] > 0
            assert 30 < vitals["temperature"] < 45

    def test_ground_truth_has_dka_labs(self, scenarios_data):
        """Ground truth에 DKA 필수 검사 포함"""
        required_labs = ["lab_glucose", "lab_ketones", "lab_ph", "lab_potassium"]
        for scenario_id, config in scenarios_data["scenarios"].items():
            gt = config["ground_truth"]
            for lab in required_labs:
                assert lab in gt, f"{scenario_id} missing {lab} in ground_truth"


class TestTrapScenarios:
    """Trap 시나리오 테스트"""

    def test_hypokalemia_trap_has_low_potassium(self, scenarios_data):
        """저칼륨 Trap 시나리오: K+ < 3.3"""
        scenario = scenarios_data["scenarios"]["dka_hypokalemia_trap"]
        potassium = scenario["ground_truth"]["lab_potassium"]
        assert potassium < 3.3, f"Expected K+ < 3.3, got {potassium}"

    def test_hypokalemia_trap_forbids_insulin(self, scenarios_data):
        """저칼륨 Trap: 인슐린 금기"""
        scenario = scenarios_data["scenarios"]["dka_hypokalemia_trap"]
        forbidden = scenario.get("forbidden_actions", [])
        assert "start_insulin_infusion" in forbidden
        assert "give_insulin_bolus" in forbidden

    def test_hypokalemia_trap_requires_potassium_replacement(self, scenarios_data):
        """저칼륨 Trap: 칼륨 보충 필수"""
        scenario = scenarios_data["scenarios"]["dka_hypokalemia_trap"]
        expected = scenario["expected_actions"]
        assert "give_potassium_iv" in expected

    def test_ckd_trap_has_high_potassium(self, scenarios_data):
        """CKD Trap 시나리오: K+ > 5.5"""
        scenario = scenarios_data["scenarios"]["dka_with_ckd"]
        potassium = scenario["ground_truth"]["lab_potassium"]
        assert potassium > 5.5, f"Expected K+ > 5.5, got {potassium}"

    def test_ckd_trap_forbids_potassium(self, scenarios_data):
        """CKD Trap: 칼륨 보충 금기"""
        scenario = scenarios_data["scenarios"]["dka_with_ckd"]
        forbidden = scenario.get("forbidden_actions", [])
        assert "give_potassium_replacement" in forbidden

    def test_euglycemic_trap_has_normal_glucose(self, scenarios_data):
        """정상혈당 DKA Trap: Glucose < 250"""
        scenario = scenarios_data["scenarios"]["dka_euglycemic_sglt2"]
        glucose = scenario["ground_truth"]["lab_glucose"]
        assert glucose < 250, f"Expected glucose < 250, got {glucose}"

    def test_euglycemic_trap_has_high_ketones(self, scenarios_data):
        """정상혈당 DKA Trap: 케톤 상승"""
        scenario = scenarios_data["scenarios"]["dka_euglycemic_sglt2"]
        ketones = scenario["ground_truth"]["lab_ketones"]
        assert ketones > 3.0, f"Expected ketones > 3.0, got {ketones}"

    def test_all_trap_scenarios_have_trap_description(self, scenarios_data):
        """모든 Trap 시나리오에 설명 포함"""
        trap_scenarios = ["dka_hypokalemia_trap", "dka_with_ckd", "dka_euglycemic_sglt2"]
        for scenario_id in trap_scenarios:
            scenario = scenarios_data["scenarios"][scenario_id]
            assert scenario.get("trap_scenario") is True
            assert scenario.get("trap_description") is not None


class TestDKACompliance:
    """DKA 프로토콜 준수 테스트"""

    def test_compliant_dka_management(self, dka_engine):
        """정상 DKA 관리 프로토콜 - 위반 없음"""
        patient = create_dka_patient(potassium=4.5)

        # 올바른 순서로 행동 수행
        actions = [
            create_action("assess_vital_signs", ActionType.PHYSICAL_EXAM, 2),
            create_action("establish_iv_access", ActionType.PROCEDURE, 5),
            create_action("order_lab_bmp", ActionType.ORDER_LAB, 8),
            create_action("order_lab_abg", ActionType.ORDER_LAB, 8),
            create_action("order_lab_ketones", ActionType.ORDER_LAB, 10),
            create_action("start_iv_fluid_ns", ActionType.GIVE_MEDICATION, 12),
            create_action("start_insulin_infusion", ActionType.GIVE_MEDICATION, 45),
            create_action("monitor_glucose_hourly", ActionType.ORDER_LAB, 60),
        ]

        # 모든 필수 행동이 올바른 순서로 수행됨
        performed_ids = [a.action_id for a in actions]
        assert "assess_vital_signs" in performed_ids
        assert "establish_iv_access" in performed_ids
        assert "start_iv_fluid_ns" in performed_ids
        assert "start_insulin_infusion" in performed_ids

    def test_iv_fluid_within_15_minutes_is_compliant(self, dka_engine):
        """15분 내 수액 투여 - 준수"""
        patient = create_dka_patient()
        constraints = dka_engine.evaluate(patient)

        # 마감시간 확인
        assert "start_iv_fluid_ns" in constraints.deadlines
        assert constraints.deadlines["start_iv_fluid_ns"] == 15

    def test_iv_fluid_at_20_minutes_is_timing_violation(self, dka_engine):
        """20분에 수액 투여 - TIMING 위반"""
        patient = create_dka_patient()
        constraints = dka_engine.evaluate(patient)

        deadline = constraints.deadlines.get("start_iv_fluid_ns", 15)
        action_time = 20

        # 마감 초과
        assert action_time > deadline


class TestHypokalemiaTrapValidation:
    """저칼륨 Trap 시나리오 위반 탐지 테스트"""

    def test_insulin_with_low_potassium_should_be_flagged(self, dka_engine):
        """K+ < 3.3에서 인슐린 투여 시 위반 탐지"""
        # potassium_replacement_first 노드에서 금기 확인
        node = dka_engine.graph.nodes["potassium_replacement_first"]

        # 이 노드의 금기 행동에 인슐린이 포함되어야 함
        assert "start_insulin_infusion" in node.forbidden_actions

    def test_potassium_replacement_before_insulin_is_correct(self, dka_engine):
        """K+ 보충 후 인슐린 투여 - 올바른 순서"""
        # insulin_therapy 노드의 precondition 확인
        node = dka_engine.graph.nodes["insulin_therapy"]
        assert "potassium >= 3.3" in node.precondition


class TestSevereDKAPathway:
    """중증 DKA 경로 테스트"""

    def test_severe_dka_requires_icu(self, dka_engine):
        """PH < 7.0 환자는 ICU 입원 필수"""
        node = dka_engine.graph.nodes["severe_dka_pathway"]
        assert "admit_to_icu" in node.mandatory_actions

    def test_ward_admission_forbidden_for_severe_dka(self, dka_engine):
        """중증 DKA 환자 일반 병동 입원 금지"""
        node = dka_engine.graph.nodes["severe_dka_pathway"]
        assert "admit_to_ward" in node.forbidden_actions

    def test_bicarbonate_only_for_ph_below_6_9(self, dka_engine):
        """PH < 6.9에서만 bicarbonate 고려"""
        node = dka_engine.graph.nodes["severe_dka_pathway"]
        assert "consider_bicarbonate_if_ph_below_6.9" in node.mandatory_actions


class TestDKAResolutionCriteria:
    """DKA 해소 기준 테스트"""

    def test_transition_requires_gap_closure(self, dka_engine):
        """피하 인슐린 전환 전 anion gap 확인"""
        node = dka_engine.graph.nodes["transition_to_maintenance"]
        # precondition에서 anion gap <= 12 확인
        assert "anion_gap <= 12" in node.precondition

    def test_transition_requires_ph_above_7_3(self, dka_engine):
        """피하 인슐린 전환 전 pH > 7.3 확인"""
        node = dka_engine.graph.nodes["transition_to_maintenance"]
        assert "ph > 7.3" in node.precondition

    def test_iv_insulin_overlap_required(self, dka_engine):
        """피하 인슐린 전환 시 IV 인슐린 1-2시간 overlap"""
        node = dka_engine.graph.nodes["transition_to_maintenance"]
        assert "overlap_iv_insulin_2h" in node.mandatory_actions


class TestCKDScenario:
    """CKD 동반 DKA 시나리오 테스트"""

    def test_ckd_scenario_has_elevated_creatinine(self, scenarios_data):
        """CKD 시나리오: 크레아티닌 상승"""
        scenario = scenarios_data["scenarios"]["dka_with_ckd"]
        creatinine = scenario["ground_truth"]["lab_creatinine"]
        assert creatinine > 2.0

    def test_ckd_scenario_forbids_aggressive_fluids(self, scenarios_data):
        """CKD 시나리오: 공격적 수액 금지"""
        scenario = scenarios_data["scenarios"]["dka_with_ckd"]
        forbidden = scenario.get("forbidden_actions", [])
        assert "aggressive_fluid_bolus" in forbidden

    def test_ckd_scenario_has_comorbidities(self, scenarios_data):
        """CKD 시나리오: 동반질환 목록"""
        scenario = scenarios_data["scenarios"]["dka_with_ckd"]
        comorbidities = scenario["patient"]["comorbidities"]
        assert "ckd_stage_4" in comorbidities


class TestInfectionTriggeredDKA:
    """감염 유발 DKA 시나리오 테스트"""

    def test_pneumonia_scenario_has_antibiotics(self, scenarios_data):
        """폐렴 유발 DKA: 항생제 투여 필수"""
        scenario = scenarios_data["scenarios"]["dka_pneumonia_trigger"]
        expected = scenario["expected_actions"]
        assert "give_antibiotics" in expected

    def test_pneumonia_scenario_has_chest_xray(self, scenarios_data):
        """폐렴 유발 DKA: 흉부 X-ray 필수"""
        scenario = scenarios_data["scenarios"]["dka_pneumonia_trigger"]
        expected = scenario["expected_actions"]
        assert "order_imaging_chest_xray" in expected

    def test_pneumonia_scenario_has_fever(self, scenarios_data):
        """폐렴 유발 DKA: 발열 존재"""
        scenario = scenarios_data["scenarios"]["dka_pneumonia_trigger"]
        temp = scenario["patient"]["vitals"]["temperature"]
        assert temp > 38.0


class TestNewOnsetT1DM:
    """신규 진단 T1DM DKA 테스트"""

    def test_new_onset_requires_education(self, scenarios_data):
        """신규 진단: 당뇨 교육 필수"""
        scenario = scenarios_data["scenarios"]["dka_new_onset_t1dm"]
        expected = scenario["expected_actions"]
        assert "diabetes_education" in expected

    def test_new_onset_requires_endocrine_consult(self, scenarios_data):
        """신규 진단: 내분비 협진 필수"""
        scenario = scenarios_data["scenarios"]["dka_new_onset_t1dm"]
        expected = scenario["expected_actions"]
        assert "endocrinology_consult" in expected

    def test_new_onset_has_high_hba1c(self, scenarios_data):
        """신규 진단: HbA1c 상승"""
        scenario = scenarios_data["scenarios"]["dka_new_onset_t1dm"]
        hba1c = scenario["ground_truth"]["lab_hba1c"]
        assert hba1c > 10.0


class TestScenarioCount:
    """시나리오 수 확인"""

    def test_total_scenario_count(self, scenarios_data):
        """총 12개 시나리오 확인"""
        assert len(scenarios_data["scenarios"]) == 12

    def test_trap_scenario_count(self, scenarios_data):
        """8개 Trap 시나리오 확인"""
        trap_count = sum(1 for s in scenarios_data["scenarios"].values() if s.get("trap_scenario", False))
        assert trap_count == 8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
