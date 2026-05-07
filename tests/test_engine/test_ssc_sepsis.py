"""SSC Sepsis Hour-1 Bundle 가이드라인 엔진 테스트
각 테스트는 "이 상태에선 반드시 X를 해야 한다/Y는 금기다/Z 마감은 N분이다"를 검증
"""

from pathlib import Path

import pytest

from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns


def get_graph_path():
    """가이드라인 그래프 파일 경로 반환"""
    base_path = Path(__file__).parent.parent.parent
    return str(base_path / "cpg_model" / "graphs" / "ssc_sepsis_hour1_bundle.yaml")


@pytest.fixture
def sepsis_engine():
    """Sepsis 가이드라인 엔진 로드"""
    return CPGEngineFactory.load_from_file(get_graph_path())


@pytest.fixture
def septic_shock_patient():
    """Septic Shock 환자 상태"""
    return PatientState(
        state_id="test_septic_shock_001",
        time_since_arrival_minutes=0,
        age=65,
        sex="M",
        weight_kg=70,
        vitals=VitalSigns(
            heart_rate=120,
            blood_pressure_systolic=85,
            blood_pressure_diastolic=50,
            respiratory_rate=24,
            temperature=38.9,
            oxygen_saturation=92,
            map_mmhg=62,  # MAP < 65 = hypotension
        ),
        chief_complaint="fever, altered mental status",
        working_diagnosis="septic_shock",
        contraindications=[],
        allergies=[],
        comorbidities=[],
    )


@pytest.fixture
def sepsis_patient():
    """Sepsis (shock 없음) 환자 상태"""
    return PatientState(
        state_id="test_sepsis_001",
        time_since_arrival_minutes=0,
        age=55,
        sex="F",
        weight_kg=60,
        vitals=VitalSigns(
            heart_rate=100,
            blood_pressure_systolic=110,
            blood_pressure_diastolic=70,
            respiratory_rate=20,
            temperature=38.5,
            oxygen_saturation=96,
            map_mmhg=83,
        ),
        chief_complaint="fever, dysuria",
        working_diagnosis="sepsis",
        contraindications=[],
        allergies=[],
        comorbidities=[],
    )


class TestSepticShockBundle:
    """Septic Shock 환자에 대한 Hour-1 Bundle 테스트"""

    def test_mandatory_actions_for_septic_shock(self, sepsis_engine, septic_shock_patient):
        """Septic Shock에서 필수 행동 확인"""
        # 엔진을 septic shock bundle 노드로 이동
        sepsis_engine.current_node_id = "septic_shock_bundle"

        output = sepsis_engine.evaluate(septic_shock_patient)

        # 필수 행동 확인
        assert "order_lab_lactate" in output.mandatory_actions
        assert "order_lab_blood_culture" in output.mandatory_actions
        assert "give_broad_spectrum_antibiotics" in output.mandatory_actions
        assert "give_crystalloid_30ml_kg" in output.mandatory_actions
        assert "start_vasopressor_if_hypotensive" in output.mandatory_actions

    def test_deadlines_for_septic_shock(self, sepsis_engine, septic_shock_patient):
        """Septic Shock에서 마감 시간 확인 - SSC 2021 Table 1 기준"""
        sepsis_engine.current_node_id = "septic_shock_bundle"

        output = sepsis_engine.evaluate(septic_shock_patient)

        # Hour-1 Bundle (60분): lactate, blood culture, antibiotics, vasopressor
        assert output.deadlines.get("order_lab_lactate") == 60
        assert output.deadlines.get("order_lab_blood_culture") == 60
        assert output.deadlines.get("give_broad_spectrum_antibiotics") == 60
        assert output.deadlines.get("start_vasopressor_if_hypotensive") == 60

        # Fluid resuscitation: 3시간 (Recommendation 5: Weak, Low)
        # "At least 30 mL/kg of IV crystalloid fluid within first 3 hours"
        assert output.deadlines.get("give_crystalloid_30ml_kg") == 180

    def test_forbidden_actions_for_septic_shock(self, sepsis_engine, septic_shock_patient):
        """Septic Shock에서 금기 행동 확인"""
        sepsis_engine.current_node_id = "septic_shock_bundle"

        output = sepsis_engine.evaluate(septic_shock_patient)

        # 퇴원은 금기
        assert "discharge_home" in output.forbidden_actions
        # 항생제 지연 금기
        assert "delay_antibiotics" in output.forbidden_actions
        # 저혈압시 수액 보류 금기
        assert "withhold_fluid_in_hypotension" in output.forbidden_actions


class TestSepsisBundle:
    """Sepsis (shock 없음) 환자에 대한 Bundle 테스트"""

    def test_mandatory_actions_for_sepsis(self, sepsis_engine, sepsis_patient):
        """Sepsis에서 필수 행동 확인"""
        sepsis_engine.current_node_id = "sepsis_bundle"

        output = sepsis_engine.evaluate(sepsis_patient)

        # 필수 행동 (Shock보다 적음)
        assert "order_lab_lactate" in output.mandatory_actions
        assert "order_lab_blood_culture" in output.mandatory_actions
        assert "give_broad_spectrum_antibiotics" in output.mandatory_actions

        # 수액 30mL/kg는 sepsis (shock 없음)에서는 필수가 아님
        assert "give_crystalloid_30ml_kg" not in output.mandatory_actions

    def test_vasopressor_not_mandatory_without_shock(self, sepsis_engine, sepsis_patient):
        """Shock 없는 Sepsis에서 승압제는 필수 아님"""
        sepsis_engine.current_node_id = "sepsis_bundle"

        output = sepsis_engine.evaluate(sepsis_patient)

        assert "start_vasopressor_if_hypotensive" not in output.mandatory_actions


class TestPatientSpecificConstraints:
    """환자 특이 조건에 따른 제약 테스트

    NOTE: 알레르기-약물 매핑과 동반질환 제약은 이제 외부 설정(CPGEngineConfig)에서
    제공해야 합니다. 아래 테스트들은 설정이 제공될 때의 동작을 테스트합니다.
    """

    def test_penicillin_allergy_forbids_ampicillin_with_config(self, sepsis_patient):
        """설정이 제공되면 Penicillin 알레르기 환자에게 ampicillin 금기"""
        from cga_bench.cpg_engine.engine import AllergyDrugMapping, CPGEngineConfig, CPGEngineFactory

        # 알레르기-약물 매핑을 설정으로 제공
        config = CPGEngineConfig(
            allergy_drug_mappings=[
                AllergyDrugMapping(
                    allergy_pattern="penicillin", forbidden_actions=["give_ampicillin", "give_amoxicillin"]
                )
            ]
        )

        engine = CPGEngineFactory.load_from_file(get_graph_path())
        engine.config = config  # 설정 주입

        sepsis_patient.allergies = ["penicillin"]
        engine.current_node_id = "sepsis_bundle"

        output = engine.evaluate(sepsis_patient)

        assert "give_ampicillin" in output.forbidden_actions
        assert "give_amoxicillin" in output.forbidden_actions

    def test_ckd_patient_nsaid_forbidden_with_config(self, sepsis_patient):
        """설정이 제공되면 CKD 환자에게 NSAID 금기"""
        from cga_bench.cpg_engine.engine import ComorbidityConstraint, CPGEngineConfig, CPGEngineFactory

        # 동반질환 제약을 설정으로 제공
        config = CPGEngineConfig(
            comorbidity_constraints=[ComorbidityConstraint(comorbidity_pattern="ckd", forbidden_actions=["give_nsaid"])]
        )

        engine = CPGEngineFactory.load_from_file(get_graph_path())
        engine.config = config  # 설정 주입

        sepsis_patient.comorbidities = ["ckd_stage_4"]
        engine.current_node_id = "sepsis_bundle"

        output = engine.evaluate(sepsis_patient)

        assert "give_nsaid" in output.forbidden_actions

    def test_no_extra_constraints_without_config(self, sepsis_engine, sepsis_patient):
        """설정이 없으면 환자 특이 제약이 추가되지 않음"""
        sepsis_patient.allergies = ["penicillin"]
        sepsis_patient.comorbidities = ["ckd_stage_4"]
        sepsis_engine.current_node_id = "sepsis_bundle"

        output = sepsis_engine.evaluate(sepsis_patient)

        # 설정 없이는 알레르기/동반질환 기반 제약이 없음
        assert "give_ampicillin" not in output.forbidden_actions
        assert "give_nsaid" not in output.forbidden_actions


class TestNodeTransitions:
    """노드 전이 테스트"""

    def test_initial_to_septic_shock_bundle(self, sepsis_engine, septic_shock_patient):
        """초기 노드에서 Septic Shock Bundle로 전이"""
        sepsis_engine.current_node_id = "initial_recognition"

        # Decision 노드에서 다음 노드 결정
        from cga_bench.cpg_engine.node_types import DecisionNode

        current_node = sepsis_engine.nodes["initial_recognition"]

        if isinstance(current_node, DecisionNode):
            next_node = current_node.get_next_node(septic_shock_patient)
            assert next_node == "septic_shock_bundle"

    def test_initial_to_sepsis_bundle(self, sepsis_engine, sepsis_patient):
        """초기 노드에서 Sepsis Bundle로 전이"""
        sepsis_engine.current_node_id = "initial_recognition"

        from cga_bench.cpg_engine.node_types import DecisionNode

        current_node = sepsis_engine.nodes["initial_recognition"]

        if isinstance(current_node, DecisionNode):
            next_node = current_node.get_next_node(sepsis_patient)
            assert next_node == "sepsis_bundle"


class TestTimingViolationScenarios:
    """타이밍 위반 시나리오 테스트 (Assessor 연동용)"""

    def test_antibiotic_at_90_minutes_is_violation(self, sepsis_engine, septic_shock_patient):
        """90분에 항생제 투여는 타이밍 위반"""
        sepsis_engine.current_node_id = "septic_shock_bundle"

        output = sepsis_engine.evaluate(septic_shock_patient)

        # 항생제 마감은 60분
        deadline = output.deadlines.get("give_broad_spectrum_antibiotics")
        assert deadline == 60

        # 90분 > 60분 마감 -> 위반
        action_time = 90
        assert action_time > deadline  # 이 조건이 True면 Assessor가 TIMING violation 생성

    def test_lactate_at_45_minutes_is_compliant(self, sepsis_engine, septic_shock_patient):
        """45분에 Lactate 측정은 준수"""
        sepsis_engine.current_node_id = "septic_shock_bundle"

        output = sepsis_engine.evaluate(septic_shock_patient)

        deadline = output.deadlines.get("order_lab_lactate")
        action_time = 45
        assert action_time <= deadline  # 준수


class TestAllowedActions:
    """허용 행동 테스트"""

    def test_allowed_actions_in_septic_shock(self, sepsis_engine, septic_shock_patient):
        """Septic Shock Bundle에서 허용 행동 확인"""
        sepsis_engine.current_node_id = "septic_shock_bundle"

        output = sepsis_engine.evaluate(septic_shock_patient)

        # 중심정맥관 및 동맥관 허용
        assert "place_central_line" in output.allowed_actions
        assert "place_arterial_line" in output.allowed_actions

        # 추가 검사 허용
        assert "order_lab_cbc" in output.allowed_actions
        assert "order_lab_bmp" in output.allowed_actions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
