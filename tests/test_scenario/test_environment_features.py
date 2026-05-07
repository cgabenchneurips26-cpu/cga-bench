"""
시나리오 엔진 기능 상세 검증 테스트

검증 항목:
1. 시간의 흐름: 검사 결과 지연, bundle 마감, 상태 악화/호전
2. 부분 관측: 처음엔 모르는 정보가 많고, 툴로 얻어야 함
3. 행동의 부작용: 수액/약물/전원 결정이 상태를 바꿈
4. 종료 조건: 안전한 disposition + 필수 조치 완료 (또는 중대한 위해 발생)
"""
import pytest
from copy import deepcopy

from cga_bench.cpg_model.schemas.base import (
    PatientState, VitalSigns, Action, ActionType
)
from cga_bench.scenario_engine.environment import (
    ClinicalEnvironment, EnvironmentConfig,
    MedicationEffectConfig, DeteriorationConfig, TerminationConfig, LabThreshold
)


@pytest.fixture
def base_patient():
    """기본 환자 상태"""
    return PatientState(
        state_id="test_patient",
        time_since_arrival_minutes=0,
        age=60,
        sex="M",
        weight_kg=70,
        vitals=VitalSigns(
            heart_rate=100,
            blood_pressure_systolic=90,
            blood_pressure_diastolic=55,
            respiratory_rate=22,
            temperature=38.5,
            oxygen_saturation=94,
            map_mmhg=65
        ),
        chief_complaint="fever and hypotension",
        working_diagnosis="sepsis",
        contraindications=[],
        allergies=[],
        comorbidities=[]
    )


@pytest.fixture
def base_ground_truth():
    """기본 Ground Truth"""
    return {
        "lab_lactate": 4.2,
        "lab_blood_culture": 1.0,
        "lab_procalcitonin": 5.5,
        "imaging_chest_xray": {"finding": "infiltrate", "interpretation": "pneumonia"}
    }


class TestTimeProgression:
    """1. 시간 흐름 테스트: 검사 지연, 마감, 상태 변화"""

    def test_lab_result_delay(self, base_patient, base_ground_truth):
        """검사 결과가 지연 시간 후에 도착하는지 확인"""
        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=30,  # 30분 지연
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False,
            lab_thresholds=[LabThreshold(test_code="lactate", low=0.0, high=2.0)]
        )

        env = ClinicalEnvironment(base_patient, config, base_ground_truth)

        # Lactate 검사 오더
        order_action = Action(
            type=ActionType.ORDER_LAB,
            action_id="order_001",
            args={"test_code": "lactate"},
            timestamp_minutes=0
        )
        obs, _, _, _ = env.step(order_action)

        # 즉시 확인 - 결과 없어야 함
        assert len(env.current_state.lab_results) == 0
        assert "lab_lactate" in env.current_state.pending_orders

        # 25분까지 대기 (아직 결과 없음)
        for _ in range(5):  # 5*5=25분
            dummy = Action(type=ActionType.REASSESS, action_id="wait", args={}, timestamp_minutes=env.current_time)
            env.step(dummy)

        assert len(env.current_state.lab_results) == 0, "30분 전에는 결과가 없어야 함"

        # 30분 이후 - 결과 도착
        dummy = Action(type=ActionType.REASSESS, action_id="wait2", args={}, timestamp_minutes=env.current_time)
        env.step(dummy)

        assert len(env.current_state.lab_results) == 1, "30분 후에는 결과가 있어야 함"
        assert env.current_state.lab_results[0].test_code == "lactate"
        assert env.current_state.lab_results[0].value == 4.2

    def test_state_deterioration_without_treatment(self, base_patient, base_ground_truth):
        """치료 없이 시간이 지나면 상태가 악화되는지 확인"""
        initial_map = base_patient.vitals.map_mmhg

        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=30,
            imaging_result_delay_minutes=45,
            enable_state_deterioration=True,
            deterioration_rules=[
                DeteriorationConfig(
                    vital="map_mmhg",
                    rate_min=1.0,
                    rate_max=3.0,
                    direction="decrease"
                )
            ],
            random_seed=42  # 재현성을 위한 시드
        )

        env = ClinicalEnvironment(base_patient, config, base_ground_truth)

        # 치료 없이 시간 경과 (20분)
        for _ in range(4):
            dummy = Action(type=ActionType.REASSESS, action_id="wait", args={}, timestamp_minutes=env.current_time)
            env.step(dummy)

        # MAP가 감소했어야 함
        current_map = env.current_state.vitals.map_mmhg
        assert current_map < initial_map, f"MAP가 감소해야 함: {initial_map} -> {current_map}"

    def test_time_progression_in_environment(self, base_patient, base_ground_truth):
        """환경에서 시간이 올바르게 진행되는지 확인"""
        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=30,
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False
        )

        env = ClinicalEnvironment(base_patient, config, base_ground_truth)

        assert env.current_time == 0

        # 3 스텝 진행
        for i in range(3):
            dummy = Action(type=ActionType.REASSESS, action_id=f"step_{i}", args={}, timestamp_minutes=env.current_time)
            env.step(dummy)

        assert env.current_time == 15  # 3 * 5분 = 15분


class TestPartialObservation:
    """2. 부분 관측 테스트: 초기 미공개 정보, 툴로 획득"""

    def test_initial_observation_has_limited_info(self, base_patient, base_ground_truth):
        """초기 관측에 숨겨진 정보가 포함되지 않는지 확인"""
        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=30,
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False
        )

        env = ClinicalEnvironment(base_patient, config, base_ground_truth)
        obs = env.reset()

        # 관측에 포함된 정보
        visible = obs.visible_state
        assert "vitals" in visible
        assert "chief_complaint" in visible
        assert "age" in visible

        # 검사 결과는 비어 있어야 함 (아직 검사 안함)
        assert visible["lab_results"] == []

        # Ground truth는 관측에 직접 포함되지 않음
        assert "lab_lactate" not in str(visible)

    def test_lab_result_obtained_via_action(self, base_patient, base_ground_truth):
        """검사 행동을 통해 정보를 얻는지 확인"""
        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=5,  # 짧은 지연
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False,
            lab_thresholds=[LabThreshold(test_code="lactate", low=0.0, high=2.0)]
        )

        env = ClinicalEnvironment(base_patient, config, base_ground_truth)

        # 검사 전 - lactate 값 모름
        obs = env.reset()
        assert len(obs.visible_state["lab_results"]) == 0

        # 검사 오더
        order = Action(type=ActionType.ORDER_LAB, action_id="o1", args={"test_code": "lactate"}, timestamp_minutes=0)
        obs, _, _, _ = env.step(order)

        # 지연 후 대기
        dummy = Action(type=ActionType.REASSESS, action_id="w1", args={}, timestamp_minutes=env.current_time)
        obs, _, _, _ = env.step(dummy)

        # 결과 도착 후 - lactate 값 알게 됨
        assert len(env.current_state.lab_results) == 1
        assert env.current_state.lab_results[0].value == 4.2

    def test_pending_orders_tracked(self, base_patient, base_ground_truth):
        """대기 중인 오더가 추적되는지 확인"""
        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=60,  # 긴 지연
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False
        )

        env = ClinicalEnvironment(base_patient, config, base_ground_truth)

        # 검사 오더
        order = Action(type=ActionType.ORDER_LAB, action_id="o1", args={"test_code": "lactate"}, timestamp_minutes=0)
        env.step(order)

        # pending_orders에 추가됨
        assert "lab_lactate" in env.current_state.pending_orders


class TestActionSideEffects:
    """3. 행동 부작용 테스트: 수액/약물이 상태 변경"""

    def test_vasopressor_increases_map(self, base_patient, base_ground_truth):
        """승압제 투여 후 MAP가 증가하는지 확인"""
        initial_map = base_patient.vitals.map_mmhg

        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=30,
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False,
            medication_effects=[
                MedicationEffectConfig(
                    medication_pattern="norepinephrine",
                    target_vital="map_mmhg",
                    effect_min=5.0,
                    effect_max=15.0
                )
            ],
            random_seed=42
        )

        env = ClinicalEnvironment(base_patient, config, base_ground_truth)

        # 승압제 투여
        med_action = Action(
            type=ActionType.GIVE_MEDICATION,
            action_id="med_001",
            args={"medication_code": "norepinephrine", "dose": "0.1mcg/kg/min"},
            timestamp_minutes=0
        )
        env.step(med_action)

        # MAP 증가 확인
        new_map = env.current_state.vitals.map_mmhg
        assert new_map > initial_map, f"MAP가 증가해야 함: {initial_map} -> {new_map}"

    def test_crystalloid_improves_blood_pressure(self, base_patient, base_ground_truth):
        """수액 투여 후 혈압이 개선되는지 확인"""
        initial_sbp = base_patient.vitals.blood_pressure_systolic

        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=30,
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False,
            medication_effects=[
                MedicationEffectConfig(
                    medication_pattern="crystalloid",
                    target_vital="blood_pressure_systolic",
                    effect_min=5.0,
                    effect_max=10.0
                )
            ],
            random_seed=42
        )

        env = ClinicalEnvironment(base_patient, config, base_ground_truth)

        # 수액 투여
        fluid_action = Action(
            type=ActionType.GIVE_MEDICATION,
            action_id="fluid_001",
            args={"medication_code": "crystalloid_30ml_kg", "dose": "30ml/kg"},
            timestamp_minutes=0
        )
        env.step(fluid_action)

        # SBP 증가 확인
        new_sbp = env.current_state.vitals.blood_pressure_systolic
        assert new_sbp > initial_sbp, f"SBP가 증가해야 함: {initial_sbp} -> {new_sbp}"

    def test_medication_recorded(self, base_patient, base_ground_truth):
        """투여된 약물이 기록되는지 확인"""
        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=30,
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False
        )

        env = ClinicalEnvironment(base_patient, config, base_ground_truth)

        # 약물 투여
        med_action = Action(
            type=ActionType.GIVE_MEDICATION,
            action_id="med_001",
            args={"medication_code": "antibiotics", "dose": "standard"},
            timestamp_minutes=0
        )
        env.step(med_action)

        # 기록 확인
        assert len(env.current_state.medications_given) == 1
        assert env.current_state.medications_given[0]["medication_code"] == "antibiotics"


class TestTerminationConditions:
    """4. 종료 조건 테스트: disposition, 필수 조치 완료, 위해 발생"""

    def test_disposition_terminates_environment(self, base_patient, base_ground_truth):
        """disposition 결정 시 환경이 종료되는지 확인"""
        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=30,
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False
        )

        env = ClinicalEnvironment(base_patient, config, base_ground_truth)
        assert not env.terminated

        # Disposition 결정
        disp_action = Action(
            type=ActionType.DISPOSITION,
            action_id="disp_001",
            args={"disposition": "admitted_to_icu"},
            timestamp_minutes=0
        )
        _, _, done, _ = env.step(disp_action)

        assert done
        assert env.terminated
        assert env.termination_reason == "disposition_decided"
        assert env.current_state.disposition_status == "admitted_to_icu"

    def test_critical_event_terminates_environment(self, base_patient, base_ground_truth):
        """위험 상태 도달 시 환경이 종료되는지 확인"""
        # 위험한 초기 상태 설정
        critical_patient = deepcopy(base_patient)
        critical_patient.vitals.map_mmhg = 45  # 위험한 수준

        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=30,
            imaging_result_delay_minutes=45,
            enable_state_deterioration=True,
            deterioration_rules=[
                DeteriorationConfig(
                    vital="map_mmhg",
                    rate_min=5.0,
                    rate_max=10.0,
                    direction="decrease"
                )
            ],
            termination_conditions=[
                TerminationConfig(
                    vital="map_mmhg",
                    threshold=40.0,
                    condition="less_than",
                    reason="critical_hypotension"
                )
            ],
            random_seed=42
        )

        env = ClinicalEnvironment(critical_patient, config, base_ground_truth)

        # 치료 없이 대기 -> 악화 -> 종료
        done = False
        for _ in range(10):
            if done:
                break
            dummy = Action(type=ActionType.REASSESS, action_id="w", args={}, timestamp_minutes=env.current_time)
            _, _, done, _ = env.step(dummy)

        assert env.terminated
        assert env.termination_reason == "critical_hypotension"

    def test_timeout_terminates_environment(self, base_patient, base_ground_truth):
        """시간 초과 시 환경이 종료되는지 확인"""
        config = EnvironmentConfig(
            max_duration_minutes=30,  # 30분 제한
            time_step_minutes=10,  # 10분 스텝
            lab_result_delay_minutes=30,
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False
        )

        env = ClinicalEnvironment(base_patient, config, base_ground_truth)

        # 3 스텝 진행 (30분)
        for _ in range(3):
            dummy = Action(type=ActionType.REASSESS, action_id="w", args={}, timestamp_minutes=env.current_time)
            _, _, done, _ = env.step(dummy)

        assert env.terminated
        assert env.termination_reason == "timeout"


class TestGroundTruthEnforcement:
    """Ground Truth 없이 검사 처리 검증"""

    def test_missing_ground_truth_uses_default(self, base_patient, caplog):
        """ground_truth에 없는 검사는 기본값 사용 (warning 로그)"""
        import logging

        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=30,
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False
        )

        incomplete_ground_truth = {"lab_lactate": 4.2}  # blood_culture 없음

        env = ClinicalEnvironment(base_patient, config, incomplete_ground_truth)

        # 없는 검사 오더
        action = Action(
            type=ActionType.ORDER_LAB,
            action_id="o1",
            args={"test_code": "blood_culture"},  # ground_truth에 없음
            timestamp_minutes=0
        )

        # 에러 발생하지 않고 warning 로그와 함께 진행
        with caplog.at_level(logging.WARNING):
            env.step(action)

        # WARNING 로그 확인
        assert "No ground truth for lab_blood_culture" in caplog.text


class TestAlertGeneration:
    """알림 생성 테스트"""

    def test_hypotension_alert(self, base_patient, base_ground_truth):
        """저혈압 알림 생성 확인"""
        hypotensive_patient = deepcopy(base_patient)
        hypotensive_patient.vitals.map_mmhg = 60  # < 65

        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=30,
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False
        )

        env = ClinicalEnvironment(hypotensive_patient, config, base_ground_truth)
        obs = env.reset()

        assert any("Hypotension" in alert for alert in obs.alerts)

    def test_fever_alert(self, base_patient, base_ground_truth):
        """발열 알림 생성 확인"""
        febrile_patient = deepcopy(base_patient)
        febrile_patient.vitals.temperature = 39.0  # > 38.3

        config = EnvironmentConfig(
            max_duration_minutes=120,
            time_step_minutes=5,
            lab_result_delay_minutes=30,
            imaging_result_delay_minutes=45,
            enable_state_deterioration=False
        )

        env = ClinicalEnvironment(febrile_patient, config, base_ground_truth)
        obs = env.reset()

        assert any("Fever" in alert for alert in obs.alerts)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
