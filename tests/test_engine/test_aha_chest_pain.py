"""AHA Chest Pain Evaluation 가이드라인 엔진 테스트
핵심: 도착 후 10분 내 12-lead ECG 획득
"""

from pathlib import Path

import pytest

from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_engine.node_types import DecisionNode
from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns


def get_graph_path():
    """AHA Chest Pain 가이드라인 그래프 파일 경로"""
    base_path = Path(__file__).parent.parent.parent
    return str(base_path / "cpg_model" / "graphs" / "aha_chest_pain_evaluation.yaml")


@pytest.fixture
def aha_engine():
    """AHA Chest Pain 가이드라인 엔진"""
    return CPGEngineFactory.load_from_file(get_graph_path())


@pytest.fixture
def stemi_patient():
    """STEMI 환자 상태"""
    return PatientState(
        state_id="test_stemi_001",
        time_since_arrival_minutes=0,
        age=58,
        sex="M",
        weight_kg=75,
        vitals=VitalSigns(
            heart_rate=95,
            blood_pressure_systolic=140,
            blood_pressure_diastolic=85,
            respiratory_rate=18,
            temperature=37.0,
            oxygen_saturation=97,
            map_mmhg=103,
        ),
        chief_complaint="crushing chest pain radiating to left arm",
        working_diagnosis="STEMI",
        contraindications=[],
        allergies=[],
        comorbidities=[],
    )


@pytest.fixture
def nstemi_patient():
    """NSTEMI 환자 상태"""
    return PatientState(
        state_id="test_nstemi_001",
        time_since_arrival_minutes=0,
        age=62,
        sex="F",
        weight_kg=65,
        vitals=VitalSigns(
            heart_rate=88,
            blood_pressure_systolic=130,
            blood_pressure_diastolic=80,
            respiratory_rate=16,
            temperature=36.8,
            oxygen_saturation=98,
            map_mmhg=97,
        ),
        chief_complaint="chest pressure with shortness of breath",
        working_diagnosis="NSTEMI",
        contraindications=[],
        allergies=[],
        comorbidities=["diabetes", "hypertension"],
    )


@pytest.fixture
def low_risk_patient():
    """저위험 흉통 환자 상태"""
    return PatientState(
        state_id="test_low_risk_001",
        time_since_arrival_minutes=0,
        age=35,
        sex="M",
        weight_kg=70,
        vitals=VitalSigns(
            heart_rate=72,
            blood_pressure_systolic=120,
            blood_pressure_diastolic=78,
            respiratory_rate=14,
            temperature=36.6,
            oxygen_saturation=99,
            map_mmhg=92,
        ),
        chief_complaint="sharp chest pain worse with breathing",
        working_diagnosis=None,
        contraindications=[],
        allergies=[],
        comorbidities=[],
    )


class TestGraphLoading:
    """그래프 로딩 테스트"""

    def test_aha_graph_loads_successfully(self, aha_engine):
        """AHA 가이드라인 그래프 로드 성공"""
        assert aha_engine is not None
        assert aha_engine.graph.graph_id == "aha_chest_pain_evaluation"
        assert aha_engine.graph.guideline_name == "AHA Chest Pain Evaluation"

    def test_entry_node_is_initial_assessment(self, aha_engine):
        """시작 노드가 initial_assessment인지 확인"""
        assert aha_engine.graph.entry_node == "initial_assessment"

    def test_all_required_nodes_exist(self, aha_engine):
        """필수 노드 존재 확인"""
        required_nodes = [
            "initial_assessment",
            "ecg_interpretation",
            "stemi_pathway",
            "nste_acs_pathway",
            "risk_stratification",
            "low_risk_pathway",
        ]
        for node_id in required_nodes:
            assert node_id in aha_engine.nodes, f"Missing node: {node_id}"


class TestECGDeadline:
    """핵심: 10분 내 ECG 마감 테스트"""

    def test_ecg_deadline_is_10_minutes(self, aha_engine, stemi_patient):
        """ECG 마감이 10분인지 확인 (AHA Class I, Level B)"""
        aha_engine.current_node_id = "initial_assessment"

        output = aha_engine.evaluate(stemi_patient)

        # ECG 마감 10분
        assert output.deadlines.get("obtain_12_lead_ecg") == 10

    def test_vital_signs_deadline_is_5_minutes(self, aha_engine, stemi_patient):
        """활력징후 평가 마감이 5분인지 확인"""
        aha_engine.current_node_id = "initial_assessment"

        output = aha_engine.evaluate(stemi_patient)

        # 활력징후 마감 5분
        assert output.deadlines.get("assess_vital_signs") == 5

    def test_ecg_at_15_minutes_is_timing_violation(self, aha_engine, stemi_patient):
        """15분에 ECG 수행은 타이밍 위반"""
        aha_engine.current_node_id = "initial_assessment"

        output = aha_engine.evaluate(stemi_patient)

        deadline = output.deadlines.get("obtain_12_lead_ecg")
        action_time = 15

        # 15분 > 10분 마감 -> 위반
        assert action_time > deadline

    def test_ecg_at_8_minutes_is_compliant(self, aha_engine, stemi_patient):
        """8분에 ECG 수행은 준수"""
        aha_engine.current_node_id = "initial_assessment"

        output = aha_engine.evaluate(stemi_patient)

        deadline = output.deadlines.get("obtain_12_lead_ecg")
        action_time = 8

        # 8분 < 10분 마감 -> 준수
        assert action_time < deadline


class TestMandatoryActions:
    """필수 행동 테스트"""

    def test_initial_assessment_mandatory_actions(self, aha_engine, stemi_patient):
        """초기 평가에서 필수 행동 확인"""
        aha_engine.current_node_id = "initial_assessment"

        output = aha_engine.evaluate(stemi_patient)

        # 필수 행동
        assert "obtain_12_lead_ecg" in output.mandatory_actions
        assert "assess_vital_signs" in output.mandatory_actions
        assert "obtain_chest_pain_history" in output.mandatory_actions

    def test_stemi_pathway_mandatory_actions(self, aha_engine, stemi_patient):
        """STEMI 경로에서 필수 행동 확인"""
        aha_engine.current_node_id = "stemi_pathway"

        output = aha_engine.evaluate(stemi_patient)

        # STEMI 필수 행동
        assert "activate_cath_lab" in output.mandatory_actions
        assert "give_aspirin_loading" in output.mandatory_actions
        assert "give_p2y12_inhibitor" in output.mandatory_actions
        assert "give_anticoagulation" in output.mandatory_actions
        assert "arrange_pci" in output.mandatory_actions

    def test_nste_acs_pathway_mandatory_actions(self, aha_engine, nstemi_patient):
        """NSTE-ACS 경로에서 필수 행동 확인"""
        aha_engine.current_node_id = "nste_acs_pathway"

        output = aha_engine.evaluate(nstemi_patient)

        # NSTE-ACS 필수 행동
        assert "order_lab_troponin" in output.mandatory_actions
        assert "give_aspirin_loading" in output.mandatory_actions
        assert "give_anticoagulation" in output.mandatory_actions
        assert "calculate_risk_score" in output.mandatory_actions


class TestForbiddenActions:
    """금기 행동 테스트"""

    def test_initial_assessment_forbidden_actions(self, aha_engine, stemi_patient):
        """초기 평가에서 금기 행동 확인.

        B3 fix: forbidden_actions are now post-processed by ActionNormalizer at the
        engine boundary, so abbreviations like 'ecg' are expanded to 'electrocardiogram'.
        Pre-fix this test asserted the raw graph strings; now we assert the canonical
        normalized form (which is what downstream commission/deviation checks compare against).
        """
        aha_engine.current_node_id = "initial_assessment"

        output = aha_engine.evaluate(stemi_patient)

        # ECG 없이 퇴원 금기 (canonical: ecg -> electrocardiogram)
        assert "discharge_without_electrocardiogram" in output.forbidden_actions
        # 등록 대기로 ECG 지연 금기
        assert "delay_electrocardiogram_for_registration" in output.forbidden_actions

    def test_stemi_pathway_forbidden_actions(self, aha_engine, stemi_patient):
        """STEMI 경로에서 금기 행동 확인"""
        aha_engine.current_node_id = "stemi_pathway"

        output = aha_engine.evaluate(stemi_patient)

        # 우심실 경색시 니트로 금기
        assert "give_nitrates_if_rv_infarct" in output.forbidden_actions
        # 퇴원 금기
        assert "discharge_home" in output.forbidden_actions
        # 재관류 지연 금기
        assert "delay_reperfusion" in output.forbidden_actions


class TestSTEMIDeadlines:
    """STEMI 경로 마감 시간 테스트"""

    def test_door_to_balloon_90_minutes(self, aha_engine, stemi_patient):
        """Door-to-balloon time 90분 확인"""
        aha_engine.current_node_id = "stemi_pathway"

        output = aha_engine.evaluate(stemi_patient)

        # PCI 마감 90분 (Door-to-balloon target)
        assert output.deadlines.get("arrange_pci") == 90

    def test_cath_lab_activation_10_minutes(self, aha_engine, stemi_patient):
        """카테터실 활성화 10분 확인"""
        aha_engine.current_node_id = "stemi_pathway"

        output = aha_engine.evaluate(stemi_patient)

        # 카테터실 활성화 10분
        assert output.deadlines.get("activate_cath_lab") == 10

    def test_aspirin_loading_15_minutes(self, aha_engine, stemi_patient):
        """아스피린 로딩 15분 확인"""
        aha_engine.current_node_id = "stemi_pathway"

        output = aha_engine.evaluate(stemi_patient)

        # 아스피린 로딩 15분
        assert output.deadlines.get("give_aspirin_loading") == 15


class TestNodeTransitions:
    """노드 전이 테스트"""

    def test_stemi_finding_routes_to_stemi_pathway(self, aha_engine, stemi_patient):
        """STEMI 발견시 STEMI 경로로 전이"""
        aha_engine.current_node_id = "ecg_interpretation"
        stemi_patient.working_diagnosis = None  # 아직 진단 전

        # ecg_finding 상태 설정
        stemi_patient.__dict__["ecg_finding"] = "STEMI"

        current_node = aha_engine.nodes["ecg_interpretation"]
        if isinstance(current_node, DecisionNode):
            # 조건부 다음 노드 확인
            assert "state.ecg_finding == 'STEMI'" in aha_engine.graph.nodes["ecg_interpretation"].conditional_next

    def test_nstemi_finding_routes_to_nste_acs_pathway(self, aha_engine, nstemi_patient):
        """NSTEMI 발견시 NSTE-ACS 경로로 전이"""
        aha_engine.current_node_id = "ecg_interpretation"

        # 조건부 전이 확인
        conditional_next = aha_engine.graph.nodes["ecg_interpretation"].conditional_next
        assert any("NSTEMI" in cond for cond in conditional_next.keys())

    def test_normal_ecg_routes_to_risk_stratification(self, aha_engine, low_risk_patient):
        """정상 ECG시 위험도 층화로 전이"""
        aha_engine.current_node_id = "ecg_interpretation"

        # True 조건이 risk_stratification으로 가는지 확인
        conditional_next = aha_engine.graph.nodes["ecg_interpretation"].conditional_next
        assert conditional_next.get("True") == "risk_stratification"


class TestSequenceDependencies:
    """순서 의존성 테스트"""

    def test_cath_lab_requires_ecg_first(self, aha_engine, stemi_patient):
        """카테터실 활성화 전 ECG 필요"""
        aha_engine.current_node_id = "stemi_pathway"

        output = aha_engine.evaluate(stemi_patient)

        # 카테터실 활성화의 선행 필수 행동 확인
        required_priors = output.required_prior_actions.get("activate_cath_lab", [])
        assert "obtain_12_lead_ecg" in required_priors
        assert "interpret_ecg" in required_priors

    def test_nitrates_requires_vital_signs(self, aha_engine, stemi_patient):
        """니트로글리세린 투여 전 활력징후 평가 필요"""
        aha_engine.current_node_id = "stemi_pathway"

        output = aha_engine.evaluate(stemi_patient)

        # 니트로 투여의 선행 필수 행동 확인
        required_priors = output.required_prior_actions.get("give_nitrates_if_indicated", [])
        assert "assess_vital_signs" in required_priors


class TestRiskStratificationPathways:
    """위험도 층화 경로 테스트"""

    def test_high_risk_routes_to_nste_acs(self, aha_engine, low_risk_patient):
        """고위험군은 NSTE-ACS 경로로"""
        conditional_next = aha_engine.graph.nodes["risk_stratification"].conditional_next
        assert conditional_next.get("state.risk_score == 'high'") == "nste_acs_pathway"

    def test_intermediate_risk_routes_to_observation(self, aha_engine, low_risk_patient):
        """중간위험군은 관찰 경로로"""
        conditional_next = aha_engine.graph.nodes["risk_stratification"].conditional_next
        assert conditional_next.get("state.risk_score == 'intermediate'") == "observation_pathway"

    def test_low_risk_routes_to_low_risk_pathway(self, aha_engine, low_risk_patient):
        """저위험군은 저위험 경로로"""
        conditional_next = aha_engine.graph.nodes["risk_stratification"].conditional_next
        assert conditional_next.get("True") == "low_risk_pathway"


class TestLowRiskPathway:
    """저위험 경로 테스트"""

    def test_low_risk_mandatory_actions(self, aha_engine, low_risk_patient):
        """저위험 경로에서 필수 행동"""
        aha_engine.current_node_id = "low_risk_pathway"
        low_risk_patient.working_diagnosis = None
        low_risk_patient.__dict__["risk_score"] = "low"

        output = aha_engine.evaluate(low_risk_patient)

        # 저위험 필수 행동
        assert "document_risk_assessment" in output.mandatory_actions
        assert "provide_discharge_instructions" in output.mandatory_actions

    def test_low_risk_no_deadlines(self, aha_engine, low_risk_patient):
        """저위험 경로에는 특별한 마감 없음"""
        aha_engine.current_node_id = "low_risk_pathway"
        low_risk_patient.__dict__["risk_score"] = "low"

        output = aha_engine.evaluate(low_risk_patient)

        # 마감 없음 (빈 dict)
        assert len(output.deadlines) == 0


class TestObservationPathway:
    """관찰 경로 테스트"""

    def test_observation_mandatory_serial_testing(self, aha_engine, low_risk_patient):
        """관찰 경로에서 연속 검사 필수"""
        aha_engine.current_node_id = "observation_pathway"
        low_risk_patient.__dict__["risk_score"] = "intermediate"

        output = aha_engine.evaluate(low_risk_patient)

        # 연속 검사 필수
        assert "serial_troponin" in output.mandatory_actions
        assert "serial_ecg" in output.mandatory_actions
        assert "stress_testing_or_cta" in output.mandatory_actions

    def test_observation_serial_troponin_deadline(self, aha_engine, low_risk_patient):
        """연속 트로포닌 마감 3시간"""
        aha_engine.current_node_id = "observation_pathway"
        low_risk_patient.__dict__["risk_score"] = "intermediate"

        output = aha_engine.evaluate(low_risk_patient)

        # 3시간 = 180분
        assert output.deadlines.get("serial_troponin") == 180

    def test_discharge_without_serial_testing_forbidden(self, aha_engine, low_risk_patient):
        """연속 검사 없이 퇴원 금기"""
        aha_engine.current_node_id = "observation_pathway"
        low_risk_patient.__dict__["risk_score"] = "intermediate"

        output = aha_engine.evaluate(low_risk_patient)

        assert "discharge_without_serial_testing" in output.forbidden_actions


class TestRecommendationStrength:
    """권고 강도 및 근거 수준 테스트"""

    def test_initial_assessment_class_i_evidence_b(self, aha_engine, stemi_patient):
        """초기 평가 권고 등급 Class I, Level B"""
        node = aha_engine.graph.nodes["initial_assessment"]

        assert node.recommendation_class == "I"
        assert node.evidence_level == "B"

    def test_stemi_pathway_class_i_evidence_a(self, aha_engine, stemi_patient):
        """STEMI 경로 권고 등급 Class I, Level A"""
        node = aha_engine.graph.nodes["stemi_pathway"]

        assert node.recommendation_class == "I"
        assert node.evidence_level == "A"


class TestMetadata:
    """메타데이터 테스트"""

    def test_graph_metadata_has_source(self, aha_engine):
        """그래프 메타데이터에 출처 정보 있음"""
        assert aha_engine.graph.metadata.get("source") == "AHA/ACC Chest Pain Guidelines 2021"

    def test_graph_metadata_has_doi(self, aha_engine):
        """그래프 메타데이터에 DOI 있음"""
        assert "doi" in aha_engine.graph.metadata

    def test_graph_metadata_has_key_recommendation(self, aha_engine):
        """그래프 메타데이터에 핵심 권고사항 있음"""
        key_rec = aha_engine.graph.metadata.get("key_recommendation")
        assert "ECG" in key_rec and "10 minutes" in key_rec


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
