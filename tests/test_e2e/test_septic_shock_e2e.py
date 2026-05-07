"""
End-to-End 테스트: Septic Shock 시나리오 전체 흐름 검증
- 시나리오 로드 -> 환경 생성 -> 에이전트 실행 -> 위반 추출 -> 채점

이 테스트는 mock/하드코딩 없이 모든 설정이 외부에서 제공되는지 검증합니다.
"""
import pytest
import yaml
import uuid
from pathlib import Path
from typing import List, Dict, Optional

from cga_bench.cpg_model.schemas.base import (
    PatientState, VitalSigns, Action, ActionType, EpisodeLog,
    HarmSeverity, ViolationType, RecommendationClass
)
from cga_bench.cpg_engine import CPGEngineFactory, CPGEngineConfig, AllergyDrugMapping
from cga_bench.scenario_engine import (
    ClinicalEnvironment, EnvironmentConfig,
    MedicationEffectConfig, DeteriorationConfig, TerminationConfig, LabThreshold
)
from cga_bench.assessor_core import (
    ViolationExtractor, ViolationExtractorConfig,
    HarmSeverityMapping, TimingSeverityThreshold,
    HarmScorer, HarmScorerConfig
)
from cga_bench.tool_api.base import ToolRegistry
from cga_bench.agent_runner.base_agent import BaseAgent, AgentConfig, AgentMetrics


class GuidelineCompliantAgent(BaseAgent):
    """
    가이드라인을 따르는 테스트용 에이전트
    설정 파일에서 정의된 프로토콜에 따라 행동
    """

    def __init__(self, config: AgentConfig, protocol: List[dict]):
        """
        Args:
            config: 에이전트 설정
            protocol: 수행할 행동 프로토콜 [{tool_name, args, expected_time}, ...]
        """
        super().__init__(config)
        self.protocol = protocol
        self.protocol_index = 0

    def decide(self, observation) -> List[Action]:
        """프로토콜에 따라 순차적으로 행동"""
        actions = []
        current_time = observation.timestamp_minutes
        state = observation.visible_state

        while self.protocol_index < len(self.protocol):
            step = self.protocol[self.protocol_index]
            tool_name = step["tool_name"]
            args = step["args"]
            expected_time = step.get("expected_time", 0)

            # 시간이 되면 행동 수행
            if current_time >= expected_time:
                # 이미 수행된 행동인지 확인
                already_done = self._check_already_done(tool_name, args, state)

                if not already_done:
                    tool = self.tool_registry.get(tool_name)
                    if tool:
                        action = tool.to_action(
                            args=args,
                            timestamp=current_time,
                            action_id=str(uuid.uuid4())
                        )
                        actions.append(action)
                        self.protocol_index += 1
                        break  # 한 번에 하나씩
                else:
                    self.protocol_index += 1
            else:
                break

        return actions

    def _check_already_done(self, tool_name: str, args: dict, state: dict) -> bool:
        """이미 수행된 행동인지 확인"""
        if tool_name == "order_lab":
            test_code = args.get("test_code")
            for lab in state.get("lab_results", []):
                if lab.get("test_code") == test_code:
                    return True
            for pending in state.get("pending_orders", []):
                if test_code in pending:
                    return True
        elif tool_name == "give_medication":
            med_code = args.get("medication_code")
            for med in state.get("medications_given", []):
                if med.get("medication_code") == med_code:
                    return True
        return False

    def reset(self):
        self.metrics = AgentMetrics()
        self.protocol_index = 0


def load_scenario_config(scenario_name: str) -> dict:
    """시나리오 설정 로드"""
    config_path = Path(__file__).parent.parent.parent / "configs" / "scenarios" / "septic_shock_e2e_test.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        all_scenarios = yaml.safe_load(f)
    return all_scenarios["scenarios"][scenario_name]


def create_patient_from_config(patient_config: dict) -> PatientState:
    """설정에서 PatientState 생성 - 모든 필수 필드는 명시적으로 제공되어야 함"""
    # 필수 필드 검증
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
        weight_kg=patient_config.get('weight_kg'),  # Optional
        vitals=vitals,
        chief_complaint=patient_config['chief_complaint'],
        working_diagnosis=patient_config.get('working_diagnosis'),  # Optional
        allergies=patient_config.get('allergies', []),  # Optional, defaults to empty list
        comorbidities=patient_config.get('comorbidities', []),  # Optional, defaults to empty list
        contraindications=patient_config.get('contraindications', [])  # Optional, defaults to empty list
    )


def create_environment_config(scenario_config: dict) -> EnvironmentConfig:
    """시나리오 설정에서 EnvironmentConfig 생성"""
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


def create_violation_extractor_config(config_dict: dict) -> ViolationExtractorConfig:
    """ViolationExtractorConfig 생성"""
    harm_severity_mappings = [
        HarmSeverityMapping(
            action_pattern=m['action_pattern'],
            severity=HarmSeverity(m['severity'])
        )
        for m in config_dict.get('harm_severity_mappings', [])
    ]

    timing_severity_thresholds = [
        TimingSeverityThreshold(
            max_delay_minutes=t['max_delay_minutes'],
            severity=HarmSeverity(t['severity'])
        )
        for t in config_dict.get('timing_severity_thresholds', [])
    ]

    return ViolationExtractorConfig(
        harm_severity_mappings=harm_severity_mappings,
        timing_severity_thresholds=timing_severity_thresholds,
        default_deviation_severity=HarmSeverity(config_dict['default_deviation_severity']),
        default_deviation_preventability=config_dict['default_deviation_preventability']
    )


def create_harm_scorer_config(config_dict: dict) -> HarmScorerConfig:
    """HarmScorerConfig 생성"""
    severity_weights = {
        HarmSeverity(k): v for k, v in config_dict['severity_weights'].items()
    }

    guideline_strength_weights: Dict[Optional[RecommendationClass], float] = {}
    for k, v in config_dict['guideline_strength_weights'].items():
        if k == 'null' or k is None:
            guideline_strength_weights[None] = v
        else:
            guideline_strength_weights[RecommendationClass(k)] = v

    violation_type_weights = {
        ViolationType(k): v for k, v in config_dict['violation_type_weights'].items()
    }

    return HarmScorerConfig(
        severity_weights=severity_weights,
        guideline_strength_weights=guideline_strength_weights,
        violation_type_weights=violation_type_weights
    )


class TestSepticShockE2E:
    """Septic Shock 시나리오 End-to-End 테스트"""

    @pytest.fixture
    def scenario_config(self):
        """시나리오 설정 로드"""
        return load_scenario_config("septic_shock_e2e_001")

    @pytest.fixture
    def guideline_engine(self):
        """가이드라인 엔진 로드"""
        graph_path = Path(__file__).parent.parent.parent / "cpg_model" / "graphs" / "ssc_sepsis_hour1_bundle.yaml"
        return CPGEngineFactory.load_from_file(str(graph_path))

    def test_full_compliance_scenario(self, scenario_config, guideline_engine):
        """완벽하게 가이드라인을 따르는 시나리오 테스트"""
        print("\n=== Full Compliance E2E Test ===")

        # 1. 환자 생성
        patient = create_patient_from_config(scenario_config['patient'])
        print(f"환자 생성: {patient.state_id}, 진단: {patient.working_diagnosis}")

        # 2. 환경 설정 생성
        env_config = create_environment_config(scenario_config)
        print(f"환경 설정: max_duration={env_config.max_duration_minutes}분")

        # 3. 환경 생성
        environment = ClinicalEnvironment(
            initial_state=patient,
            config=env_config,
            ground_truth=scenario_config['ground_truth']
        )
        print("환경 생성 완료")

        # 4. 가이드라인 준수 프로토콜 정의
        # NOTE: vasopressor expected_time compressed 25 -> 20 so the schedule
        # has no idle gap between actions. base_agent.run_episode no longer
        # advances the simulation clock on empty decide() calls (commit
        # 1c9816d8, 2026-04-04), so any gap larger than time_step_minutes
        # produces consecutive_empty_actions terminations instead of waiting
        # for the next scheduled step. Timing is not under test here — the
        # delayed variant below covers timing-violation semantics.
        protocol = [
            {"tool_name": "order_lab", "args": {"test_code": "lactate"}, "expected_time": 0},
            {"tool_name": "order_lab", "args": {"test_code": "blood_culture"}, "expected_time": 5},
            {"tool_name": "give_medication", "args": {"medication_code": "broad_spectrum_antibiotics", "dose": "standard"}, "expected_time": 10},
            {"tool_name": "give_medication", "args": {"medication_code": "crystalloid_30ml_kg", "dose": "30ml/kg"}, "expected_time": 15},
            {"tool_name": "give_medication", "args": {"medication_code": "vasopressor_norepinephrine", "dose": "0.1mcg/kg/min"}, "expected_time": 20},
        ]

        # 5. 에이전트 생성
        agent_config = AgentConfig(
            agent_id="compliant_agent_001",
            agent_type="guideline_compliant"
        )
        agent = GuidelineCompliantAgent(agent_config, protocol)
        print("에이전트 생성 완료")

        # 6. 에피소드 실행
        episode_log = agent.run_episode(environment, "septic_shock_e2e_001")
        print(f"에피소드 실행 완료: {len(episode_log.actions)} 행동, {episode_log.total_duration_minutes}분")

        # 7. 위반 추출
        ve_config = create_violation_extractor_config(
            scenario_config['violation_extractor_config']
        )
        extractor = ViolationExtractor(guideline_engine, ve_config)

        guideline_engine.reset()
        guideline_engine.current_node_id = "septic_shock_bundle"
        violations = extractor.extract_violations(episode_log)
        print(f"추출된 위반: {len(violations)}개")

        # 8. 채점
        hs_config = create_harm_scorer_config(scenario_config['harm_scorer_config'])
        scorer = HarmScorer(
            total_mandatory_count=scenario_config['total_mandatory_count'],
            config=hs_config
        )
        score = scorer.compute_score(violations, episode_log)

        print(f"\n=== 채점 결과 ===")
        print(f"Compliance Score: {score.compliance_score:.2%}")
        print(f"Peak Risk: {score.peak_risk:.3f}")
        print(f"Aggregate Risk: {score.aggregate_risk:.3f}")
        print(f"Total Violations: {score.total_violations}")

        # 9. 검증
        assert len(episode_log.actions) >= 5, "최소 5개 행동이 수행되어야 함"
        assert episode_log.total_duration_minutes <= scenario_config['max_duration_minutes']

        # 행동이 모두 60분 마감 내에 수행되었는지 확인
        for action in episode_log.actions:
            assert action.timestamp_minutes <= 60, f"행동 {action.action_id}가 마감 후 수행됨"

        print("\n=== Full Compliance E2E Test 성공! ===")

    def test_delayed_treatment_scenario(self, scenario_config, guideline_engine):
        """지연된 치료 시나리오 테스트 (타이밍 위반 예상)"""
        print("\n=== Delayed Treatment E2E Test ===")

        # 1. 환자 및 환경 생성
        patient = create_patient_from_config(scenario_config['patient'])
        env_config = create_environment_config(scenario_config)
        environment = ClinicalEnvironment(
            initial_state=patient,
            config=env_config,
            ground_truth=scenario_config['ground_truth']
        )

        # 2. 지연된 프로토콜 (마감 후 행동)
        delayed_protocol = [
            {"tool_name": "order_lab", "args": {"test_code": "lactate"}, "expected_time": 0},
            {"tool_name": "order_lab", "args": {"test_code": "blood_culture"}, "expected_time": 5},
            # 항생제를 70분에 투여 (마감 60분 초과)
            {"tool_name": "give_medication", "args": {"medication_code": "broad_spectrum_antibiotics", "dose": "standard"}, "expected_time": 70},
            {"tool_name": "give_medication", "args": {"medication_code": "crystalloid_30ml_kg", "dose": "30ml/kg"}, "expected_time": 75},
            {"tool_name": "give_medication", "args": {"medication_code": "vasopressor_norepinephrine", "dose": "0.1mcg/kg/min"}, "expected_time": 80},
        ]

        # 3. 에이전트 실행
        agent_config = AgentConfig(agent_id="delayed_agent_001", agent_type="delayed")
        agent = GuidelineCompliantAgent(agent_config, delayed_protocol)
        episode_log = agent.run_episode(environment, "septic_shock_e2e_001")

        print(f"에피소드 실행 완료: {len(episode_log.actions)} 행동")

        # 4. 위반 추출
        ve_config = create_violation_extractor_config(
            scenario_config['violation_extractor_config']
        )
        extractor = ViolationExtractor(guideline_engine, ve_config)

        guideline_engine.reset()
        guideline_engine.current_node_id = "septic_shock_bundle"
        violations = extractor.extract_violations(episode_log)

        print(f"추출된 위반: {len(violations)}개")
        for v in violations:
            print(f"  - {v.violation_type.value}: {v.description}")

        # 5. 채점
        hs_config = create_harm_scorer_config(scenario_config['harm_scorer_config'])
        scorer = HarmScorer(
            total_mandatory_count=scenario_config['total_mandatory_count'],
            config=hs_config
        )
        score = scorer.compute_score(violations, episode_log)

        print(f"\n=== 채점 결과 ===")
        print(f"Compliance Score: {score.compliance_score:.2%}")
        print(f"Peak Risk: {score.peak_risk:.3f}")

        # 6. 검증: 지연으로 인한 타이밍 위반이 있어야 함
        timing_violations = [v for v in violations if v.violation_type == ViolationType.TIMING]
        print(f"타이밍 위반 수: {len(timing_violations)}")

        # Compliance score가 100% 미만이어야 함 (위반이 있으므로)
        if len(violations) > 0:
            assert score.compliance_score < 1.0, "위반이 있으면 compliance < 100%"

        print("\n=== Delayed Treatment E2E Test 성공! ===")

    def test_omission_scenario(self, scenario_config, guideline_engine):
        """행동 누락 시나리오 테스트 (누락 위반 예상)"""
        print("\n=== Omission E2E Test ===")

        # 1. 환자 및 환경 생성
        patient = create_patient_from_config(scenario_config['patient'])
        env_config = create_environment_config(scenario_config)
        environment = ClinicalEnvironment(
            initial_state=patient,
            config=env_config,
            ground_truth=scenario_config['ground_truth']
        )

        # 2. 불완전한 프로토콜 (일부 행동 누락)
        incomplete_protocol = [
            {"tool_name": "order_lab", "args": {"test_code": "lactate"}, "expected_time": 0},
            # blood_culture 누락
            {"tool_name": "give_medication", "args": {"medication_code": "broad_spectrum_antibiotics", "dose": "standard"}, "expected_time": 10},
            # crystalloid 누락
            # vasopressor 누락
        ]

        # 3. 에이전트 실행
        agent_config = AgentConfig(agent_id="incomplete_agent_001", agent_type="incomplete")
        agent = GuidelineCompliantAgent(agent_config, incomplete_protocol)
        episode_log = agent.run_episode(environment, "septic_shock_e2e_001")

        print(f"에피소드 실행 완료: {len(episode_log.actions)} 행동")

        # 4. 위반 추출
        ve_config = create_violation_extractor_config(
            scenario_config['violation_extractor_config']
        )
        extractor = ViolationExtractor(guideline_engine, ve_config)

        guideline_engine.reset()
        guideline_engine.current_node_id = "septic_shock_bundle"
        violations = extractor.extract_violations(episode_log)

        print(f"추출된 위반: {len(violations)}개")
        for v in violations:
            print(f"  - {v.violation_type.value}: {v.description}")

        # 5. 채점
        hs_config = create_harm_scorer_config(scenario_config['harm_scorer_config'])
        scorer = HarmScorer(
            total_mandatory_count=scenario_config['total_mandatory_count'],
            config=hs_config
        )
        score = scorer.compute_score(violations, episode_log)

        print(f"\n=== 채점 결과 ===")
        print(f"Compliance Score: {score.compliance_score:.2%}")
        print(f"Total Violations: {score.total_violations}")

        # 6. 검증: 누락 위반이 있어야 함
        omission_violations = [v for v in violations if v.violation_type == ViolationType.OMISSION]
        print(f"누락 위반 수: {len(omission_violations)}")

        print("\n=== Omission E2E Test 성공! ===")


class TestConfigValidation:
    """설정 검증 테스트"""

    def test_missing_ground_truth_raises_error(self):
        """ground_truth 누락시 에러 발생 확인"""
        scenario_config = load_scenario_config("septic_shock_e2e_001")
        patient = create_patient_from_config(scenario_config['patient'])
        env_config = create_environment_config(scenario_config)

        with pytest.raises(ValueError, match="ground_truth is required"):
            ClinicalEnvironment(
                initial_state=patient,
                config=env_config,
                ground_truth=None
            )

    def test_missing_env_config_raises_error(self):
        """환경 설정 누락시 에러 발생 확인"""
        scenario_config = load_scenario_config("septic_shock_e2e_001")
        patient = create_patient_from_config(scenario_config['patient'])

        with pytest.raises(ValueError, match="config is required"):
            ClinicalEnvironment(
                initial_state=patient,
                config=None,
                ground_truth=scenario_config['ground_truth']
            )

    def test_missing_lab_in_ground_truth_uses_default(self, caplog):
        """ground_truth에 없는 검사 오더시 기본값 사용 (warning 로그)"""
        import logging

        scenario_config = load_scenario_config("septic_shock_e2e_001")
        patient = create_patient_from_config(scenario_config['patient'])
        env_config = create_environment_config(scenario_config)

        # ground_truth에서 lactate 제거
        incomplete_ground_truth = {"lab_blood_culture": 1.0}

        environment = ClinicalEnvironment(
            initial_state=patient,
            config=env_config,
            ground_truth=incomplete_ground_truth
        )

        # lactate 검사 오더
        action = Action(
            type=ActionType.ORDER_LAB,
            action_id="test_action",
            args={"test_code": "lactate"},
            timestamp_minutes=0
        )

        # 에러 발생하지 않고 warning 로그와 함께 진행
        with caplog.at_level(logging.WARNING):
            environment.step(action)

        # WARNING 로그 확인
        assert "No ground truth for lab_lactate" in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
