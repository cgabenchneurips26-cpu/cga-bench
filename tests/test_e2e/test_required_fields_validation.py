"""
필수 필드 검증 테스트

시나리오 설정 파일에서 필수 필드가 누락되었을 때 적절한 오류가 발생하는지 검증합니다.
"""
import pytest
import yaml
import uuid
from pathlib import Path

from cga_bench.cpg_model.schemas.base import (
    PatientState, VitalSigns, Action, ActionType
)
from cga_bench.scenario_engine.environment import (
    ClinicalEnvironment, EnvironmentConfig,
    MedicationEffectConfig, DeteriorationConfig, TerminationConfig, LabThreshold
)
from cga_bench.eval_harness.runner import EvaluationRunner, ExperimentConfig


# ============================================================================
# 테스트용 시나리오 설정
# ============================================================================

# 완전한 시나리오 (모든 필수 필드 포함)
COMPLETE_SCENARIO = """
scenarios:
  complete_scenario:
    description: "Complete scenario with all required fields"

    patient:
      age: 65
      sex: "M"
      weight_kg: 70.0
      chief_complaint: "fever, hypotension"
      working_diagnosis: "septic_shock"
      vitals:
        heart_rate: 120
        blood_pressure_systolic: 85
        blood_pressure_diastolic: 50
        map_mmhg: 62
        temperature: 38.9
        respiratory_rate: 24
        oxygen_saturation: 92
      allergies: []
      comorbidities: []
      contraindications: []

    max_duration_minutes: 120
    time_step_minutes: 5.0
    lab_result_delay_minutes: 30.0
    imaging_result_delay_minutes: 45.0
    enable_state_deterioration: false

    medication_effects: []
    deterioration_rules: []
    termination_conditions: []

    lab_thresholds:
      - test_code: "lactate"
        low: 0.0
        high: 2.0

    ground_truth:
      lab_lactate: 4.5

    total_mandatory_count: 3

    violation_extractor_config:
      harm_severity_mappings:
        - action_pattern: "lactate"
          severity: "major"
      timing_severity_thresholds:
        - max_delay_minutes: 30.0
          severity: "minor"
      default_deviation_severity: "moderate"
      default_deviation_preventability: 0.8

    harm_scorer_config:
      severity_weights:
        minor: 0.1
        moderate: 0.3
        major: 0.6
        severe: 0.85
        catastrophic: 1.0
      guideline_strength_weights:
        "I": 1.0
        "null": 0.5
      violation_type_weights:
        omission: 0.8
        commission: 1.0
        timing: 0.7
        sequence: 0.6
        deviation: 0.4
"""

# 환자 필수 필드 누락 시나리오
MISSING_PATIENT_AGE = """
scenarios:
  missing_age:
    patient:
      sex: "M"
      chief_complaint: "fever"
      vitals:
        heart_rate: 100
        map_mmhg: 65
"""

MISSING_PATIENT_SEX = """
scenarios:
  missing_sex:
    patient:
      age: 65
      chief_complaint: "fever"
      vitals:
        heart_rate: 100
        map_mmhg: 65
"""

MISSING_PATIENT_CHIEF_COMPLAINT = """
scenarios:
  missing_complaint:
    patient:
      age: 65
      sex: "M"
      vitals:
        heart_rate: 100
        map_mmhg: 65
"""

MISSING_PATIENT_VITALS = """
scenarios:
  missing_vitals:
    patient:
      age: 65
      sex: "M"
      chief_complaint: "fever"
"""

# 환경 설정 필수 필드 누락 시나리오
MISSING_ENV_MAX_DURATION = """
scenarios:
  missing_max_duration:
    patient:
      age: 65
      sex: "M"
      chief_complaint: "fever"
      vitals:
        heart_rate: 100
        map_mmhg: 65

    time_step_minutes: 5.0
    lab_result_delay_minutes: 30.0
    imaging_result_delay_minutes: 45.0
    enable_state_deterioration: false
    ground_truth:
      lab_lactate: 4.5
"""

MISSING_ENV_TIME_STEP = """
scenarios:
  missing_time_step:
    patient:
      age: 65
      sex: "M"
      chief_complaint: "fever"
      vitals:
        heart_rate: 100
        map_mmhg: 65

    max_duration_minutes: 120
    lab_result_delay_minutes: 30.0
    imaging_result_delay_minutes: 45.0
    enable_state_deterioration: false
    ground_truth:
      lab_lactate: 4.5
"""

# Ground Truth 누락 시나리오
MISSING_GROUND_TRUTH = """
scenarios:
  missing_ground_truth:
    patient:
      age: 65
      sex: "M"
      chief_complaint: "fever"
      vitals:
        heart_rate: 100
        map_mmhg: 65

    max_duration_minutes: 120
    time_step_minutes: 5.0
    lab_result_delay_minutes: 30.0
    imaging_result_delay_minutes: 45.0
    enable_state_deterioration: false
"""


# ============================================================================
# 헬퍼 함수
# ============================================================================

def parse_yaml(yaml_content: str) -> dict:
    """YAML 문자열을 딕셔너리로 파싱"""
    return yaml.safe_load(yaml_content)


def create_patient_from_config(patient_config: dict) -> PatientState:
    """설정에서 PatientState 생성 - 필수 필드 검증 포함"""
    required_fields = ['age', 'sex', 'chief_complaint', 'vitals']
    for field in required_fields:
        if field not in patient_config:
            raise ValueError(f"Required patient field '{field}' missing in patient_config")

    vitals_config = patient_config['vitals']
    vitals = VitalSigns(**vitals_config)

    return PatientState(
        state_id=f"patient_{uuid.uuid4().hex[:8]}",
        age=patient_config['age'],
        sex=patient_config['sex'],
        weight_kg=patient_config.get('weight_kg'),
        vitals=vitals,
        chief_complaint=patient_config['chief_complaint'],
        working_diagnosis=patient_config.get('working_diagnosis'),
        allergies=patient_config.get('allergies', []),
        comorbidities=patient_config.get('comorbidities', []),
        contraindications=patient_config.get('contraindications', [])
    )


def create_environment_config(scenario_config: dict) -> EnvironmentConfig:
    """시나리오 설정에서 EnvironmentConfig 생성 - 필수 필드 검증 포함"""
    required_fields = [
        'max_duration_minutes', 'time_step_minutes',
        'lab_result_delay_minutes', 'imaging_result_delay_minutes',
        'enable_state_deterioration', 'ground_truth'
    ]
    for field in required_fields:
        if field not in scenario_config:
            raise ValueError(f"Required field '{field}' missing in scenario_config")

    medication_effects = [
        MedicationEffectConfig(**effect)
        for effect in scenario_config.get('medication_effects', [])
    ]

    deterioration_rules = [
        DeteriorationConfig(**rule)
        for rule in scenario_config.get('deterioration_rules', [])
    ]

    termination_conditions = [
        TerminationConfig(**condition)
        for condition in scenario_config.get('termination_conditions', [])
    ]

    lab_thresholds = [
        LabThreshold(**threshold)
        for threshold in scenario_config.get('lab_thresholds', [])
    ]

    return EnvironmentConfig(
        max_duration_minutes=scenario_config['max_duration_minutes'],
        time_step_minutes=scenario_config['time_step_minutes'],
        lab_result_delay_minutes=scenario_config['lab_result_delay_minutes'],
        imaging_result_delay_minutes=scenario_config['imaging_result_delay_minutes'],
        enable_state_deterioration=scenario_config['enable_state_deterioration'],
        medication_effects=medication_effects,
        deterioration_rules=deterioration_rules,
        termination_conditions=termination_conditions,
        lab_thresholds=lab_thresholds
    )


# ============================================================================
# 테스트 클래스
# ============================================================================

class TestPatientRequiredFields:
    """환자 정보 필수 필드 검증 테스트"""

    def test_missing_age_raises_error(self):
        """age 필드 누락시 ValueError 발생"""
        config = parse_yaml(MISSING_PATIENT_AGE)
        patient_config = config['scenarios']['missing_age']['patient']

        with pytest.raises(ValueError, match="Required patient field 'age' missing"):
            create_patient_from_config(patient_config)

    def test_missing_sex_raises_error(self):
        """sex 필드 누락시 ValueError 발생"""
        config = parse_yaml(MISSING_PATIENT_SEX)
        patient_config = config['scenarios']['missing_sex']['patient']

        with pytest.raises(ValueError, match="Required patient field 'sex' missing"):
            create_patient_from_config(patient_config)

    def test_missing_chief_complaint_raises_error(self):
        """chief_complaint 필드 누락시 ValueError 발생"""
        config = parse_yaml(MISSING_PATIENT_CHIEF_COMPLAINT)
        patient_config = config['scenarios']['missing_complaint']['patient']

        with pytest.raises(ValueError, match="Required patient field 'chief_complaint' missing"):
            create_patient_from_config(patient_config)

    def test_missing_vitals_raises_error(self):
        """vitals 필드 누락시 ValueError 발생"""
        config = parse_yaml(MISSING_PATIENT_VITALS)
        patient_config = config['scenarios']['missing_vitals']['patient']

        with pytest.raises(ValueError, match="Required patient field 'vitals' missing"):
            create_patient_from_config(patient_config)

    def test_complete_patient_config_succeeds(self):
        """완전한 환자 설정은 성공적으로 생성"""
        config = parse_yaml(COMPLETE_SCENARIO)
        patient_config = config['scenarios']['complete_scenario']['patient']

        patient = create_patient_from_config(patient_config)

        assert patient.age == 65
        assert patient.sex == "M"
        assert patient.chief_complaint == "fever, hypotension"
        assert patient.vitals.heart_rate == 120


class TestEnvironmentRequiredFields:
    """환경 설정 필수 필드 검증 테스트"""

    def test_missing_max_duration_raises_error(self):
        """max_duration_minutes 필드 누락시 ValueError 발생"""
        config = parse_yaml(MISSING_ENV_MAX_DURATION)
        scenario_config = config['scenarios']['missing_max_duration']

        with pytest.raises(ValueError, match="Required field 'max_duration_minutes' missing"):
            create_environment_config(scenario_config)

    def test_missing_time_step_raises_error(self):
        """time_step_minutes 필드 누락시 ValueError 발생"""
        config = parse_yaml(MISSING_ENV_TIME_STEP)
        scenario_config = config['scenarios']['missing_time_step']

        with pytest.raises(ValueError, match="Required field 'time_step_minutes' missing"):
            create_environment_config(scenario_config)

    def test_missing_ground_truth_raises_error(self):
        """ground_truth 필드 누락시 ValueError 발생"""
        config = parse_yaml(MISSING_GROUND_TRUTH)
        scenario_config = config['scenarios']['missing_ground_truth']

        with pytest.raises(ValueError, match="Required field 'ground_truth' missing"):
            create_environment_config(scenario_config)

    def test_complete_env_config_succeeds(self):
        """완전한 환경 설정은 성공적으로 생성"""
        config = parse_yaml(COMPLETE_SCENARIO)
        scenario_config = config['scenarios']['complete_scenario']

        env_config = create_environment_config(scenario_config)

        assert env_config.max_duration_minutes == 120
        assert env_config.time_step_minutes == 5.0
        assert env_config.lab_result_delay_minutes == 30.0


class TestActionRequiredArgs:
    """액션 필수 인자 검증 테스트"""

    def _create_test_environment(self) -> ClinicalEnvironment:
        """테스트용 환경 생성"""
        config = parse_yaml(COMPLETE_SCENARIO)
        scenario_config = config['scenarios']['complete_scenario']
        patient_config = scenario_config['patient']

        patient = create_patient_from_config(patient_config)
        env_config = create_environment_config(scenario_config)
        ground_truth = scenario_config['ground_truth']

        return ClinicalEnvironment(
            initial_state=patient,
            config=env_config,
            ground_truth=ground_truth
        )

    def test_order_lab_missing_test_code_raises_error(self):
        """ORDER_LAB에서 test_code 누락시 ValueError 발생"""
        env = self._create_test_environment()
        env.reset()

        action = Action(
            type=ActionType.ORDER_LAB,
            action_id="test_action",
            args={},  # test_code 누락
            timestamp_minutes=0.0
        )

        with pytest.raises(ValueError, match="ORDER_LAB action requires 'test_code' in args"):
            env.step(action)

    def test_order_lab_with_test_code_succeeds(self):
        """ORDER_LAB에 test_code가 있으면 성공"""
        env = self._create_test_environment()
        env.reset()

        action = Action(
            type=ActionType.ORDER_LAB,
            action_id="test_action",
            args={"test_code": "lactate"},
            timestamp_minutes=0.0
        )

        obs, _, _, _ = env.step(action)
        assert "lab_lactate" in env.current_state.pending_orders

    def test_order_imaging_missing_imaging_type_raises_error(self):
        """ORDER_IMAGING에서 imaging_type 누락시 ValueError 발생"""
        env = self._create_test_environment()
        env.reset()

        action = Action(
            type=ActionType.ORDER_IMAGING,
            action_id="test_action",
            args={},  # imaging_type 누락
            timestamp_minutes=0.0
        )

        with pytest.raises(ValueError, match="ORDER_IMAGING action requires 'imaging_type' in args"):
            env.step(action)

    def test_give_medication_missing_medication_code_raises_error(self):
        """GIVE_MEDICATION에서 medication_code 누락시 ValueError 발생"""
        env = self._create_test_environment()
        env.reset()

        action = Action(
            type=ActionType.GIVE_MEDICATION,
            action_id="test_action",
            args={"dose": "standard"},  # medication_code 누락
            timestamp_minutes=0.0
        )

        with pytest.raises(ValueError, match="GIVE_MEDICATION action requires 'medication_code' in args"):
            env.step(action)

    def test_give_medication_missing_dose_raises_error(self):
        """GIVE_MEDICATION에서 dose 누락시 ValueError 발생"""
        env = self._create_test_environment()
        env.reset()

        action = Action(
            type=ActionType.GIVE_MEDICATION,
            action_id="test_action",
            args={"medication_code": "antibiotic"},  # dose 누락
            timestamp_minutes=0.0
        )

        with pytest.raises(ValueError, match="GIVE_MEDICATION action requires 'dose' in args"):
            env.step(action)

    def test_give_medication_with_all_args_succeeds(self):
        """GIVE_MEDICATION에 모든 필수 인자가 있으면 성공"""
        env = self._create_test_environment()
        env.reset()

        action = Action(
            type=ActionType.GIVE_MEDICATION,
            action_id="test_action",
            args={
                "medication_code": "broad_spectrum_antibiotics",
                "dose": "standard"
            },
            timestamp_minutes=0.0
        )

        obs, _, _, _ = env.step(action)
        assert len(env.current_state.medications_given) == 1
        assert env.current_state.medications_given[0]["medication_code"] == "broad_spectrum_antibiotics"
        assert env.current_state.medications_given[0]["dose"] == "standard"

    def test_disposition_missing_disposition_uses_action_id_fallback(self):
        """DISPOSITION에서 disposition 누락시 action_id를 fallback으로 사용"""
        env = self._create_test_environment()
        env.reset()

        action = Action(
            type=ActionType.DISPOSITION,
            action_id="test_action",
            args={},  # disposition 누락
            timestamp_minutes=0.0
        )

        # graceful fallback: no ValueError, uses action_id as disposition
        obs, _, _, _ = env.step(action)
        assert env.current_state.disposition_status == "test_action"

    def test_procedure_missing_procedure_code_uses_action_id_fallback(self):
        """PROCEDURE에서 procedure_code 누락시 action_id를 fallback으로 사용"""
        env = self._create_test_environment()
        env.reset()

        action = Action(
            type=ActionType.PROCEDURE,
            action_id="test_action",
            args={},  # procedure_code 누락
            timestamp_minutes=0.0
        )

        # graceful fallback: no ValueError, uses action_id as procedure_code
        obs, _, _, _ = env.step(action)
        assert "test_action" in env.current_state.procedures_done


class TestCompleteScenarioFromFile:
    """완전한 시나리오 파일에서 로드하여 테스트"""

    def test_load_complete_e2e_scenario_from_file(self):
        """실제 시나리오 파일(septic_shock_e2e_test.yaml)에서 로드 및 검증"""
        config_path = Path(__file__).parent.parent.parent / "configs" / "scenarios" / "septic_shock_e2e_test.yaml"

        with open(config_path, 'r', encoding='utf-8') as f:
            all_scenarios = yaml.safe_load(f)

        scenario_config = all_scenarios["scenarios"]["septic_shock_e2e_001"]

        # 환자 생성 성공
        patient = create_patient_from_config(scenario_config['patient'])
        assert patient.age == 65
        assert patient.sex == "M"
        assert patient.working_diagnosis == "septic_shock"

        # 환경 설정 생성 성공
        env_config = create_environment_config(scenario_config)
        assert env_config.max_duration_minutes == 120
        assert env_config.time_step_minutes == 5.0

        # 환경 생성 성공
        ground_truth = scenario_config['ground_truth']
        env = ClinicalEnvironment(
            initial_state=patient,
            config=env_config,
            ground_truth=ground_truth
        )

        env.reset()

        # 액션 수행 테스트
        action = Action(
            type=ActionType.ORDER_LAB,
            action_id="test_lactate",
            args={"test_code": "lactate"},
            timestamp_minutes=0.0
        )
        obs, _, done, _ = env.step(action)

        assert "lab_lactate" in env.current_state.pending_orders
        assert not done

    def test_all_e2e_scenarios_have_required_fields(self):
        """모든 E2E 시나리오가 필수 필드를 포함하는지 검증"""
        config_path = Path(__file__).parent.parent.parent / "configs" / "scenarios" / "septic_shock_e2e_test.yaml"

        with open(config_path, 'r', encoding='utf-8') as f:
            all_scenarios = yaml.safe_load(f)

        required_patient_fields = ['age', 'sex', 'chief_complaint', 'vitals']
        required_env_fields = [
            'max_duration_minutes', 'time_step_minutes',
            'lab_result_delay_minutes', 'imaging_result_delay_minutes',
            'enable_state_deterioration', 'ground_truth'
        ]
        required_scoring_fields = [
            'total_mandatory_count',
            'violation_extractor_config',
            'harm_scorer_config'
        ]

        for scenario_id, scenario_config in all_scenarios["scenarios"].items():
            # 환자 필드 검증
            patient_config = scenario_config.get('patient', {})
            for field in required_patient_fields:
                assert field in patient_config, \
                    f"Scenario '{scenario_id}' missing patient field '{field}'"

            # 환경 필드 검증
            for field in required_env_fields:
                assert field in scenario_config, \
                    f"Scenario '{scenario_id}' missing env field '{field}'"

            # 채점 필드 검증
            for field in required_scoring_fields:
                assert field in scenario_config, \
                    f"Scenario '{scenario_id}' missing scoring field '{field}'"
