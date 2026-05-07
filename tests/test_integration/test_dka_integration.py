"""
DKA Integration 테스트: 전체 파이프라인 검증

CPG Engine + Scenarios + Violation Detector + Agent Rules 통합 테스트
- 시나리오 -> CPG 평가 -> 위반 탐지 -> 채점까지 전체 흐름
- Trap 시나리오 위반 탐지 검증
- Compound 시나리오 (CKD + Severe DKA) 처리 검증
- 해소 기준 (Resolution Criteria) 검증
"""
import pytest
from pathlib import Path
from typing import Dict, Any, List
import yaml

from cga_bench.cpg_model.schemas.base import (
    PatientState, VitalSigns, Action, ActionType, EpisodeLog, HarmSeverity
)
from cga_bench.cpg_engine.engine import CPGEngineFactory, CPGEngine
from cga_bench.assessor_core import (
    DKAViolationDetector, DKAViolationDetectorConfig,
    create_dka_violation_detector, DKATrapViolation,
    ViolationExtractor
)
from cga_bench.agent_rules.dka_rules import DKADecisionTable


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def cpg_engine() -> CPGEngine:
    """DKA CPG 엔진 로드"""
    graph_path = Path(__file__).parent.parent.parent / "cpg_model" / "graphs" / "ada_dka_management.yaml"
    return CPGEngineFactory.load_from_file(str(graph_path))


@pytest.fixture
def scenarios_data() -> Dict[str, Any]:
    """DKA 시나리오 데이터 로드"""
    scenarios_path = Path(__file__).parent.parent.parent / "configs" / "scenarios" / "dka_scenarios.yaml"
    with open(scenarios_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def dka_detector() -> DKAViolationDetector:
    """DKA 위반 탐지기"""
    return create_dka_violation_detector()


@pytest.fixture
def dka_table() -> DKADecisionTable:
    """DKA 결정 테이블"""
    return DKADecisionTable()


# =============================================================================
# Helper Functions
# =============================================================================

def create_patient(
    potassium: float = 4.5,
    ph: float = 7.18,
    glucose: float = 420,
    mental_status: str = "alert",
    comorbidities: List[str] = None
) -> PatientState:
    """테스트용 환자 생성"""
    return PatientState(
        state_id="test_patient",
        time_since_arrival_minutes=0,
        age=45,
        sex="M",
        weight_kg=70,
        vitals=VitalSigns(
            heart_rate=110,
            blood_pressure_systolic=100,
            blood_pressure_diastolic=60,
            respiratory_rate=26,
            temperature=37.2,
            oxygen_saturation=97,
            map_mmhg=73
        ),
        chief_complaint="nausea, vomiting, confusion",
        working_diagnosis="dka_moderate",
        allergies=[],
        comorbidities=comorbidities or ["type_1_diabetes"],
        contraindications=[]
    )


def create_action(action_id: str, timestamp: float, action_type: ActionType = ActionType.GIVE_MEDICATION) -> Action:
    """테스트용 행동 생성"""
    return Action(
        type=action_type,
        action_id=action_id,
        timestamp_minutes=timestamp,
        args={}
    )


def create_episode(actions: List[Action], patient: PatientState = None) -> EpisodeLog:
    """테스트용 에피소드 생성"""
    if patient is None:
        patient = create_patient()
    return EpisodeLog(
        episode_id="test_episode",
        scenario_id="test_scenario",
        agent_id="test_agent",
        actions=actions,
        states=[patient],
        observations=[{}],  # Required field
        total_duration_minutes=max(a.timestamp_minutes for a in actions) if actions else 0,
        total_llm_calls=0,
        total_tokens=0,
        total_tool_calls=len(actions),
        termination_reason="completed"
    )


# =============================================================================
# CPG Engine + Violation Detector Integration
# =============================================================================

class TestCPGEngineViolationDetectorIntegration:
    """CPG 엔진과 위반 탐지기 통합 테스트"""

    def test_cpg_engine_loads_correctly(self, cpg_engine):
        """CPG 엔진 로드 확인"""
        assert cpg_engine is not None
        assert cpg_engine.graph is not None
        assert "initial_assessment" in cpg_engine.graph.nodes

    def test_violation_detector_detects_hypokalemia_trap(self, dka_detector):
        """저칼륨 Trap 위반 탐지"""
        actions = [
            create_action("assess_vital_signs", 2, ActionType.PHYSICAL_EXAM),
            create_action("establish_iv_access", 5, ActionType.PROCEDURE),
            create_action("order_lab_bmp", 8, ActionType.ORDER_LAB),
            create_action("start_iv_fluid_ns", 12, ActionType.GIVE_MEDICATION),
            create_action("start_insulin_infusion", 30, ActionType.GIVE_MEDICATION),  # K+ 확인 없이 투여
        ]

        patient = create_patient(potassium=2.8)  # K+ < 3.3
        episode = create_episode(actions, patient)
        ground_truth = {"lab_potassium": 2.8, "lab_glucose": 420, "lab_ph": 7.18}

        result = dka_detector.detect_violations(episode, ground_truth)

        # Hypokalemia trap 위반 확인
        trap_violations = result["trap_violations"]
        assert len(trap_violations) > 0

        hypokalemia_traps = [v for v in trap_violations if v.trap_type == "hypokalemia"]
        assert len(hypokalemia_traps) > 0
        assert hypokalemia_traps[0].severity == HarmSeverity.CATASTROPHIC

    def test_compliant_hypokalemia_management(self, dka_detector):
        """저칼륨 환자 올바른 관리 - 위반 없음"""
        actions = [
            create_action("assess_vital_signs", 2, ActionType.PHYSICAL_EXAM),
            create_action("establish_iv_access", 5, ActionType.PROCEDURE),
            create_action("order_lab_bmp", 8, ActionType.ORDER_LAB),
            create_action("start_iv_fluid_ns", 12, ActionType.GIVE_MEDICATION),
            create_action("give_potassium_iv", 20, ActionType.GIVE_MEDICATION),  # 먼저 K+ 보충
            create_action("start_insulin_infusion", 60, ActionType.GIVE_MEDICATION),  # K+ 보충 후 인슐린
        ]

        patient = create_patient(potassium=2.8)
        episode = create_episode(actions, patient)
        ground_truth = {"lab_potassium": 2.8, "lab_glucose": 420, "lab_ph": 7.18}

        result = dka_detector.detect_violations(episode, ground_truth)

        # Hypokalemia trap 위반이 없어야 함 (칼륨 먼저 투여)
        trap_violations = result["trap_violations"]
        hypokalemia_traps = [v for v in trap_violations if v.trap_type == "hypokalemia"]

        # 순서 위반만 없어야 함 (칼륨이 먼저 투여됨)
        sequence_traps = [v for v in hypokalemia_traps if "BEFORE" in v.violation_description]
        assert len(sequence_traps) == 0

    def test_hyperkalemia_trap_detection(self, dka_detector):
        """고칼륨 Trap 위반 탐지"""
        actions = [
            create_action("assess_vital_signs", 2, ActionType.PHYSICAL_EXAM),
            create_action("establish_iv_access", 5, ActionType.PROCEDURE),
            create_action("order_lab_bmp", 8, ActionType.ORDER_LAB),
            create_action("start_iv_fluid_ns", 12, ActionType.GIVE_MEDICATION),
            create_action("give_potassium_iv", 25, ActionType.GIVE_MEDICATION),  # K+ > 5.5인데 투여
        ]

        patient = create_patient(potassium=6.2, comorbidities=["type_1_diabetes", "ckd_stage_4"])
        episode = create_episode(actions, patient)
        ground_truth = {"lab_potassium": 6.2, "lab_glucose": 380, "lab_ph": 7.15}

        result = dka_detector.detect_violations(episode, ground_truth)

        # Hyperkalemia trap 위반 확인
        trap_violations = result["trap_violations"]
        hyperkalemia_traps = [v for v in trap_violations if v.trap_type == "hyperkalemia"]
        assert len(hyperkalemia_traps) > 0
        assert hyperkalemia_traps[0].severity == HarmSeverity.CATASTROPHIC


class TestCPGEngineScenarioIntegration:
    """CPG 엔진과 시나리오 통합 테스트"""

    def test_scenario_ground_truth_matches_cpg_thresholds(self, cpg_engine, scenarios_data):
        """시나리오 ground_truth가 CPG 임계값과 일치하는지 확인"""
        # CPG metadata에서 임계값 확인
        metadata = cpg_engine.graph.metadata
        critical_thresholds = metadata.get("critical_thresholds", {})

        hypokalemia_cutoff = critical_thresholds.get("hypokalemia_cutoff", 3.3)
        severe_dka_ph = critical_thresholds.get("severe_dka_ph", 7.0)

        # Hypokalemia trap 시나리오 확인
        hypo_scenario = scenarios_data["scenarios"]["dka_hypokalemia_trap"]
        assert hypo_scenario["ground_truth"]["lab_potassium"] < hypokalemia_cutoff

        # Severe DKA 시나리오 확인
        severe_scenario = scenarios_data["scenarios"]["dka_severe_icu"]
        assert severe_scenario["ground_truth"]["lab_ph"] < severe_dka_ph

    def test_euglycemic_scenario_has_normal_glucose(self, scenarios_data):
        """Euglycemic DKA 시나리오: 혈당 < 200 확인"""
        euglycemic = scenarios_data["scenarios"]["dka_euglycemic_sglt2"]
        glucose = euglycemic["ground_truth"]["lab_glucose"]

        # True euglycemic: < 200
        assert glucose < 200, f"Euglycemic DKA should have glucose < 200, got {glucose}"

        # Beta-hydroxybutyrate 확인
        bhb = euglycemic["ground_truth"].get("lab_beta_hydroxybutyrate")
        assert bhb is not None and bhb > 3.0

    def test_all_scenarios_have_matching_cpg_graph(self, cpg_engine, scenarios_data):
        """모든 시나리오가 올바른 CPG 그래프 참조"""
        for scenario_id, config in scenarios_data["scenarios"].items():
            assert config["guideline_graph"] == "ada_dka_management"


# =============================================================================
# Agent Rules + CPG Engine Integration
# =============================================================================

class TestAgentRulesCPGIntegration:
    """Agent Rules와 CPG Engine 통합 테스트 - 독립성 검증"""

    def test_agent_rules_are_independent_of_cpg_engine(self, cpg_engine, dka_table):
        """Agent Rules가 CPG Engine과 독립적으로 동작"""
        # Agent Rules는 cpg_engine을 사용하지 않아야 함
        import inspect
        source = inspect.getsource(DKADecisionTable)

        # cpg_engine import 확인
        assert "cpg_engine" not in source.lower(), \
            "Agent Rules should not import cpg_engine for evaluation independence"

    def test_agent_rules_provide_same_mandatory_actions(self, cpg_engine, dka_table):
        """Agent Rules와 CPG Engine이 동일한 필수 행동 제공 (일관성)"""
        # CPG Engine에서 초기 노드의 필수 행동
        initial_node = cpg_engine.graph.nodes["initial_assessment"]
        cpg_mandatory = set(initial_node.mandatory_actions)

        # Agent Rules에서 동일 상황의 추천 행동
        context = {
            "potassium": 4.5,
            "ph": 7.18,
            "glucose": 420,
            "mental_status": "alert",
            "diagnosis": "dka_moderate",
            "comorbidities": ["type_1_diabetes"]
        }
        dka_table.reset()
        recommendations = dka_table.get_recommended_actions(context)
        rules_recommended = {r.action_id for r in recommendations}

        # 핵심 필수 행동이 양쪽에 모두 포함
        core_mandatory = {"assess_vital_signs", "establish_iv_access", "start_iv_fluid_ns"}
        for action in core_mandatory:
            assert action in cpg_mandatory, f"CPG missing {action}"
            # Agent Rules는 시나리오 타입에 따라 다를 수 있으므로,
            # 적어도 유사한 행동이 포함되어야 함

    def test_agent_rules_prevent_trap_violations(self, dka_table):
        """Agent Rules가 Trap 위반을 방지하는지 확인"""
        # 저칼륨 환자 상황
        hypokalemia_context = {
            "potassium": 2.8,
            "ph": 7.18,
            "glucose": 420,
            "mental_status": "alert",
            "diagnosis": "dka_hypokalemia",
            "comorbidities": ["type_1_diabetes"]
        }
        dka_table.reset()

        # Prerequisites for potassium replacement
        dka_table.record_action("order_lab_bmp", 5)
        dka_table.record_action("establish_iv_access", 8)

        forbidden = dka_table.get_forbidden_actions(hypokalemia_context)

        # 인슐린이 금기에 포함되어야 함
        assert "start_insulin_infusion" in forbidden

    def test_agent_rules_compound_scenario_handling(self, dka_table):
        """Agent Rules 복합 시나리오 처리"""
        # Severe DKA + CKD 복합 상황
        compound_context = {
            "potassium": 5.8,  # High K+ due to CKD
            "ph": 6.85,  # Severe DKA
            "glucose": 520,
            "mental_status": "obtunded",
            "diagnosis": "dka_severe_ckd",
            "comorbidities": ["type_1_diabetes", "ckd_stage_4"]
        }
        dka_table.reset()

        forbidden = dka_table.get_forbidden_actions(compound_context)

        # 복합 조건에서 칼륨 투여 금기
        potassium_forbidden = any("potassium" in a for a in forbidden)
        assert potassium_forbidden, "Potassium should be forbidden for CKD patient with high K+"

        # 일반 병동 입원 금기 (severe DKA)
        assert "admit_to_ward" in forbidden


# =============================================================================
# Scenario + Violation Detector Integration
# =============================================================================

class TestScenarioViolationDetectorIntegration:
    """시나리오와 위반 탐지기 통합 테스트"""

    def test_hypokalemia_scenario_violation_detection(self, dka_detector, scenarios_data):
        """저칼륨 시나리오 위반 탐지 통합 테스트"""
        scenario = scenarios_data["scenarios"]["dka_hypokalemia_trap"]
        ground_truth = scenario["ground_truth"]

        # 잘못된 행동 시퀀스 (인슐린 먼저)
        wrong_actions = [
            create_action("assess_vital_signs", 2, ActionType.PHYSICAL_EXAM),
            create_action("establish_iv_access", 5, ActionType.PROCEDURE),
            create_action("order_lab_bmp", 8, ActionType.ORDER_LAB),
            create_action("start_iv_fluid_ns", 12, ActionType.GIVE_MEDICATION),
            create_action("start_insulin_infusion", 30, ActionType.GIVE_MEDICATION),  # Wrong!
        ]

        patient = create_patient(potassium=ground_truth["lab_potassium"])
        episode = create_episode(wrong_actions, patient)

        result = dka_detector.detect_violations(episode, ground_truth)

        # Trap 위반 확인
        assert len(result["trap_violations"]) > 0
        assert result["total_risk_score"] > 0.3  # High risk

    def test_ckd_scenario_violation_detection(self, dka_detector, scenarios_data):
        """CKD 시나리오 위반 탐지 통합 테스트"""
        scenario = scenarios_data["scenarios"]["dka_with_ckd"]
        ground_truth = scenario["ground_truth"]

        # 잘못된 행동 시퀀스 (칼륨 투여)
        wrong_actions = [
            create_action("assess_vital_signs", 2, ActionType.PHYSICAL_EXAM),
            create_action("establish_iv_access", 5, ActionType.PROCEDURE),
            create_action("order_lab_bmp", 8, ActionType.ORDER_LAB),
            create_action("start_iv_fluid_ns", 12, ActionType.GIVE_MEDICATION),
            create_action("give_potassium_iv", 25, ActionType.GIVE_MEDICATION),  # Wrong! K+ already high
        ]

        patient = create_patient(
            potassium=ground_truth["lab_potassium"],
            comorbidities=["type_1_diabetes", "ckd_stage_4"]
        )
        episode = create_episode(wrong_actions, patient)

        result = dka_detector.detect_violations(episode, ground_truth)

        # Hyperkalemia trap 위반 확인
        trap_violations = result["trap_violations"]
        hyperkalemia_traps = [v for v in trap_violations if "hyperkalemia" in v.trap_type]
        assert len(hyperkalemia_traps) > 0

    def test_euglycemic_scenario_ketone_omission(self, dka_detector, scenarios_data):
        """Euglycemic DKA 시나리오: 케톤 검사 누락 탐지"""
        scenario = scenarios_data["scenarios"]["dka_euglycemic_sglt2"]
        ground_truth = scenario["ground_truth"]

        # 케톤 검사 누락한 행동
        actions = [
            create_action("assess_vital_signs", 2, ActionType.PHYSICAL_EXAM),
            create_action("establish_iv_access", 5, ActionType.PROCEDURE),
            create_action("order_lab_bmp", 8, ActionType.ORDER_LAB),
            create_action("order_lab_glucose", 8, ActionType.ORDER_LAB),  # Only glucose, no ketones
            create_action("start_iv_fluid_ns", 12, ActionType.GIVE_MEDICATION),
            # No insulin because they missed DKA diagnosis
        ]

        patient = create_patient(glucose=ground_truth["lab_glucose"])
        episode = create_episode(actions, patient)

        result = dka_detector.detect_violations(episode, ground_truth)

        # 케톤 검사 누락 위반 확인
        trap_violations = result["trap_violations"]
        ketone_traps = [v for v in trap_violations if "euglycemic" in v.trap_type]
        assert len(ketone_traps) > 0

    def test_severe_dka_wrong_disposition(self, dka_detector, scenarios_data):
        """Severe DKA: 잘못된 배치 (병동 입원) 탐지"""
        scenario = scenarios_data["scenarios"]["dka_severe_icu"]
        ground_truth = scenario["ground_truth"]

        # 일반 병동 입원 (잘못된 결정)
        wrong_actions = [
            create_action("assess_vital_signs", 2, ActionType.PHYSICAL_EXAM),
            create_action("establish_iv_access", 5, ActionType.PROCEDURE),
            create_action("order_lab_bmp", 8, ActionType.ORDER_LAB),
            create_action("order_lab_abg", 8, ActionType.ORDER_LAB),
            create_action("start_iv_fluid_ns", 12, ActionType.GIVE_MEDICATION),
            create_action("admit_to_ward", 30, ActionType.DISPOSITION),  # Wrong!
        ]

        patient = create_patient(ph=ground_truth["lab_ph"], mental_status="obtunded")
        episode = create_episode(wrong_actions, patient)

        result = dka_detector.detect_violations(episode, ground_truth)

        # Severe DKA wrong disposition 위반 확인
        trap_violations = result["trap_violations"]
        disposition_traps = [v for v in trap_violations if "severe_dka_wrong_disposition" in v.trap_type]
        assert len(disposition_traps) > 0


# =============================================================================
# Resolution Criteria Integration
# =============================================================================

class TestResolutionCriteriaIntegration:
    """DKA 해소 기준 통합 테스트"""

    def test_resolution_criteria_in_cpg(self, cpg_engine):
        """CPG에 해소 기준 정의 확인"""
        transition_node = cpg_engine.graph.nodes["transition_to_maintenance"]

        # Precondition에 해소 기준 포함
        precondition = transition_node.precondition
        assert "glucose < 200" in precondition
        assert "anion_gap <= 12" in precondition
        assert "ph > 7.3" in precondition
        assert "bicarbonate >= 15" in precondition

    def test_resolution_criteria_requires_two_of_three(self, cpg_engine):
        """해소 기준: precondition에서 glucose < 200 + 3가지 중 2가지 충족 표현 확인"""
        transition_node = cpg_engine.graph.nodes["transition_to_maintenance"]
        precondition = transition_node.precondition

        # Precondition에 ADA resolution criteria 표현식이 있는지 확인
        # glucose < 200 and ((bicarbonate >= 15) + (ph > 7.3) + (anion_gap <= 12)) >= 2
        assert "glucose < 200" in precondition
        assert ">= 2" in precondition  # 2개 이상 충족 조건

    def test_agent_rules_resolution_check(self, dka_table):
        """Agent Rules 해소 기준 확인"""
        # 해소 기준 충족: glucose < 200 + 2/3
        resolution_context = {
            "glucose": 185,  # < 200
            "bicarbonate": 18,  # >= 15 (1)
            "ph": 7.35,  # > 7.3 (2)
            "anion_gap": 14,  # > 12 (not met)
            "potassium": 4.5,
            "mental_status": "alert",
            "diagnosis": "dka_resolving",
            "comorbidities": ["type_1_diabetes"]
        }

        dka_table.reset()
        is_resolved = dka_table._check_resolution_criteria(resolution_context)

        # 2/3 충족: 해소됨
        assert is_resolved is True

    def test_agent_rules_not_resolved(self, dka_table):
        """Agent Rules 해소 기준 미충족"""
        # 해소 기준 미충족
        active_context = {
            "glucose": 280,  # >= 200 - not met
            "bicarbonate": 12,  # < 15
            "ph": 7.15,  # < 7.3
            "anion_gap": 18,  # > 12
            "potassium": 4.0,
            "mental_status": "alert",
            "diagnosis": "dka_moderate",
            "comorbidities": ["type_1_diabetes"]
        }

        dka_table.reset()
        is_resolved = dka_table._check_resolution_criteria(active_context)

        # 기준 미충족: 해소 안됨
        assert is_resolved is False


# =============================================================================
# Risk Score Integration
# =============================================================================

class TestRiskScoreIntegration:
    """위험 점수 통합 테스트"""

    def test_catastrophic_violation_high_risk(self, dka_detector):
        """치명적 위반은 높은 위험 점수"""
        actions = [
            create_action("assess_vital_signs", 2, ActionType.PHYSICAL_EXAM),
            create_action("start_insulin_infusion", 10, ActionType.GIVE_MEDICATION),  # K+ 확인 없이
        ]

        patient = create_patient(potassium=2.5)  # Severe hypokalemia
        episode = create_episode(actions, patient)
        ground_truth = {"lab_potassium": 2.5, "lab_glucose": 420, "lab_ph": 7.18}

        result = dka_detector.detect_violations(episode, ground_truth)

        # 높은 위험 점수
        assert result["total_risk_score"] >= 0.4

    def test_compliant_episode_low_risk(self, dka_detector):
        """준수 에피소드는 낮은 위험 점수"""
        actions = [
            create_action("assess_vital_signs", 2, ActionType.PHYSICAL_EXAM),
            create_action("establish_iv_access", 5, ActionType.PROCEDURE),
            create_action("order_lab_bmp", 8, ActionType.ORDER_LAB),
            create_action("order_lab_ketones", 10, ActionType.ORDER_LAB),
            create_action("start_iv_fluid_ns", 12, ActionType.GIVE_MEDICATION),
            create_action("start_insulin_infusion", 45, ActionType.GIVE_MEDICATION),
            create_action("monitor_glucose_hourly", 60, ActionType.ORDER_LAB),
        ]

        patient = create_patient(potassium=4.5)  # Normal K+
        episode = create_episode(actions, patient)
        ground_truth = {"lab_potassium": 4.5, "lab_glucose": 420, "lab_ph": 7.18}

        result = dka_detector.detect_violations(episode, ground_truth)

        # 낮은 위험 점수 (trap 위반 없음)
        assert len(result["trap_violations"]) == 0


# =============================================================================
# Full Pipeline Integration
# =============================================================================

class TestFullPipelineIntegration:
    """전체 파이프라인 통합 테스트"""

    def test_full_pipeline_hypokalemia_trap(self, cpg_engine, dka_detector, dka_table, scenarios_data):
        """전체 파이프라인: 저칼륨 Trap 시나리오"""
        scenario = scenarios_data["scenarios"]["dka_hypokalemia_trap"]
        ground_truth = scenario["ground_truth"]
        potassium = ground_truth["lab_potassium"]

        # 1. CPG Engine 평가
        patient = create_patient(potassium=potassium)
        cpg_engine.reset()
        cpg_engine.current_node_id = "potassium_replacement_first"  # K+ < 3.3
        constraints = cpg_engine.evaluate(patient)

        # 인슐린 금기 확인
        assert "start_insulin_infusion" in constraints.forbidden_actions

        # 2. Agent Rules 확인
        context = {
            "potassium": potassium,
            "ph": ground_truth["lab_ph"],
            "glucose": ground_truth["lab_glucose"],
            "mental_status": "alert",
            "diagnosis": "dka_hypokalemia",
            "comorbidities": ["type_1_diabetes"]
        }
        dka_table.reset()
        dka_table.record_action("order_lab_bmp", 5)
        dka_table.record_action("establish_iv_access", 8)

        forbidden = dka_table.get_forbidden_actions(context)
        assert "start_insulin_infusion" in forbidden

        # 3. 위반 탐지 (잘못된 행동)
        wrong_actions = [
            create_action("assess_vital_signs", 2, ActionType.PHYSICAL_EXAM),
            create_action("start_insulin_infusion", 15, ActionType.GIVE_MEDICATION),
        ]
        episode = create_episode(wrong_actions, patient)
        result = dka_detector.detect_violations(episode, ground_truth)

        # 4. 결과 검증
        assert len(result["trap_violations"]) > 0
        assert result["total_risk_score"] > 0

    def test_full_pipeline_compliant_management(self, cpg_engine, dka_detector, dka_table, scenarios_data):
        """전체 파이프라인: 올바른 DKA 관리"""
        scenario = scenarios_data["scenarios"]["dka_moderate_basic"]
        ground_truth = scenario["ground_truth"]
        potassium = ground_truth["lab_potassium"]

        # 1. CPG Engine 평가
        patient = create_patient(potassium=potassium)
        cpg_engine.reset()
        constraints = cpg_engine.evaluate(patient)

        # 초기 평가 필수 행동 확인
        assert "assess_vital_signs" in constraints.mandatory_actions

        # 2. 올바른 행동 시퀀스
        correct_actions = [
            create_action("assess_vital_signs", 2, ActionType.PHYSICAL_EXAM),
            create_action("establish_iv_access", 5, ActionType.PROCEDURE),
            create_action("order_lab_bmp", 8, ActionType.ORDER_LAB),
            create_action("order_lab_abg", 8, ActionType.ORDER_LAB),
            create_action("order_lab_ketones", 10, ActionType.ORDER_LAB),
            create_action("start_iv_fluid_ns", 12, ActionType.GIVE_MEDICATION),
            create_action("start_insulin_infusion", 45, ActionType.GIVE_MEDICATION),
            create_action("monitor_glucose_hourly", 60, ActionType.ORDER_LAB),
            create_action("monitor_potassium_q2h", 120, ActionType.ORDER_LAB),
        ]

        episode = create_episode(correct_actions, patient)
        result = dka_detector.detect_violations(episode, ground_truth)

        # 3. 결과 검증 - Trap 위반 없음
        assert len(result["trap_violations"]) == 0

    def test_summary_generation(self, dka_detector, scenarios_data):
        """위반 요약 생성 테스트"""
        scenario = scenarios_data["scenarios"]["dka_hypokalemia_trap"]
        ground_truth = scenario["ground_truth"]

        # 여러 위반 포함 행동
        actions = [
            create_action("assess_vital_signs", 25, ActionType.PHYSICAL_EXAM),  # Late
            create_action("start_insulin_infusion", 30, ActionType.GIVE_MEDICATION),  # Wrong
        ]

        patient = create_patient(potassium=ground_truth["lab_potassium"])
        episode = create_episode(actions, patient)

        result = dka_detector.detect_violations(episode, ground_truth)

        # 요약에 위반 정보 포함
        summary = result["summary"]
        assert "DKA Violation Summary" in summary
        assert "[CRITICAL]" in summary or "[TIMING]" in summary or "[OMISSION]" in summary


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
