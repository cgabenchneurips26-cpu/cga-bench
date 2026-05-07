"""
ADA DKA Management 가이드라인 테스트
CPG Graph 로딩, 노드 구조, 제약조건 검증
"""
import pytest
from pathlib import Path
import yaml

from cga_bench.cpg_engine.engine import CPGEngine, CPGEngineFactory
from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns, Action, ActionType


def get_graph_path():
    """가이드라인 그래프 파일 경로 반환"""
    base_path = Path(__file__).parent.parent.parent
    return str(base_path / "cpg_model" / "graphs" / "ada_dka_management.yaml")


def get_graph_data():
    """그래프 YAML 데이터 로드"""
    with open(get_graph_path()) as f:
        return yaml.safe_load(f)


@pytest.fixture
def dka_engine():
    """DKA 가이드라인 엔진 로드"""
    return CPGEngineFactory.load_from_file(get_graph_path())


class TestGraphLoading:
    """CPG Graph 로딩 테스트"""

    def test_ada_dka_graph_loads_successfully(self):
        """DKA 그래프 로딩 성공 테스트"""
        graph_path = Path(get_graph_path())
        assert graph_path.exists(), f"Graph file not found: {graph_path}"
        engine = CPGEngineFactory.load_from_file(str(graph_path))
        assert engine is not None

    def test_graph_has_correct_id(self, dka_engine):
        """그래프 ID 확인"""
        assert dka_engine.graph.graph_id == "ada_dka_management"

    def test_entry_node_is_initial_assessment(self, dka_engine):
        """진입 노드 확인"""
        assert dka_engine.graph.entry_node == "initial_assessment"

    def test_all_required_nodes_exist(self, dka_engine):
        """필수 노드 존재 확인"""
        required_nodes = [
            "initial_assessment",
            "severity_classification",
            "potassium_replacement_first",
            "insulin_therapy",
            "severe_dka_pathway",
            "ongoing_monitoring",
            "transition_to_maintenance",
            "disposition"
        ]
        for node_id in required_nodes:
            assert node_id in dka_engine.graph.nodes, f"Missing node: {node_id}"


class TestInitialAssessmentNode:
    """초기 평가 노드 테스트"""

    def test_initial_assessment_mandatory_actions(self, dka_engine):
        """초기 평가 필수 행동 확인"""
        node = dka_engine.graph.nodes["initial_assessment"]
        expected_mandatory = [
            "assess_vital_signs",
            "assess_mental_status",
            "establish_iv_access",
            "order_lab_glucose",
            "order_lab_bmp",
            "order_lab_ketones",
            "order_lab_abg",
            "start_iv_fluid_ns"
        ]
        for action in expected_mandatory:
            assert action in node.mandatory_actions, f"Missing mandatory action: {action}"

    def test_iv_fluid_deadline_is_15_minutes(self, dka_engine):
        """수액 투여 마감시간 15분 확인"""
        node = dka_engine.graph.nodes["initial_assessment"]
        assert node.deadlines.get("start_iv_fluid_ns") == 15

    def test_vital_signs_deadline_is_5_minutes(self, dka_engine):
        """활력징후 확인 마감시간 5분"""
        node = dka_engine.graph.nodes["initial_assessment"]
        assert node.deadlines.get("assess_vital_signs") == 5

    def test_iv_access_deadline_is_10_minutes(self, dka_engine):
        """IV 접근 마감시간 10분"""
        node = dka_engine.graph.nodes["initial_assessment"]
        assert node.deadlines.get("establish_iv_access") == 10

    def test_forbidden_actions(self, dka_engine):
        """금기 행동 확인"""
        node = dka_engine.graph.nodes["initial_assessment"]
        assert "discharge_home" in node.forbidden_actions
        assert "delay_iv_access" in node.forbidden_actions


class TestPotassiumReplacementNode:
    """칼륨 보충 노드 테스트 (Hypokalemia Trap)"""

    def test_potassium_node_exists(self, dka_engine):
        """칼륨 보충 노드 존재 확인"""
        assert "potassium_replacement_first" in dka_engine.graph.nodes

    def test_potassium_node_precondition(self, dka_engine):
        """K+ < 3.3 조건 확인"""
        node = dka_engine.graph.nodes["potassium_replacement_first"]
        assert "potassium < 3.3" in node.precondition

    def test_insulin_is_forbidden_when_hypokalemic(self, dka_engine):
        """저칼륨 시 인슐린 금기 확인"""
        node = dka_engine.graph.nodes["potassium_replacement_first"]
        assert "start_insulin_infusion" in node.forbidden_actions
        assert "give_insulin_bolus" in node.forbidden_actions

    def test_potassium_replacement_is_mandatory(self, dka_engine):
        """칼륨 투여 필수 확인"""
        node = dka_engine.graph.nodes["potassium_replacement_first"]
        assert "give_potassium_iv" in node.mandatory_actions
        assert "hold_insulin_until_k_above_3.3" in node.mandatory_actions

    def test_potassium_deadline(self, dka_engine):
        """칼륨 투여 마감시간 30분"""
        node = dka_engine.graph.nodes["potassium_replacement_first"]
        assert node.deadlines.get("give_potassium_iv") == 30


class TestInsulinTherapyNode:
    """인슐린 요법 노드 테스트"""

    def test_insulin_precondition_requires_adequate_potassium(self, dka_engine):
        """인슐린 시작 전 K+ >= 3.3 조건"""
        node = dka_engine.graph.nodes["insulin_therapy"]
        assert "potassium >= 3.3" in node.precondition

    def test_insulin_mandatory_actions(self, dka_engine):
        """인슐린 요법 필수 행동"""
        node = dka_engine.graph.nodes["insulin_therapy"]
        assert "start_insulin_infusion" in node.mandatory_actions
        assert "monitor_glucose_hourly" in node.mandatory_actions
        assert "monitor_potassium_q2h" in node.mandatory_actions

    def test_insulin_deadline_is_60_minutes(self, dka_engine):
        """인슐린 시작 마감시간 60분"""
        node = dka_engine.graph.nodes["insulin_therapy"]
        assert node.deadlines.get("start_insulin_infusion") == 60

    def test_insulin_requires_prior_actions(self, dka_engine):
        """인슐린 시작 전 선행 조건"""
        node = dka_engine.graph.nodes["insulin_therapy"]
        required_prior = node.required_prior_actions.get("start_insulin_infusion", [])
        assert "order_lab_bmp" in required_prior
        assert "start_iv_fluid_ns" in required_prior

    def test_forbidden_to_stop_insulin_early(self, dka_engine):
        """인슐린 조기 중단 금지"""
        node = dka_engine.graph.nodes["insulin_therapy"]
        assert "stop_insulin_before_gap_closed" in node.forbidden_actions


class TestSevereDKAPathway:
    """중증 DKA 경로 테스트"""

    def test_severe_dka_precondition(self, dka_engine):
        """중증 DKA 조건 (pH < 7.0 또는 의식저하)"""
        node = dka_engine.graph.nodes["severe_dka_pathway"]
        assert "ph < 7.0" in node.precondition or "obtunded" in node.precondition

    def test_icu_admission_is_mandatory(self, dka_engine):
        """ICU 입원 필수"""
        node = dka_engine.graph.nodes["severe_dka_pathway"]
        assert "admit_to_icu" in node.mandatory_actions

    def test_ward_admission_is_forbidden(self, dka_engine):
        """일반 병동 입원 금지"""
        node = dka_engine.graph.nodes["severe_dka_pathway"]
        assert "admit_to_ward" in node.forbidden_actions

    def test_bicarbonate_consideration(self, dka_engine):
        """pH < 6.9일 때 bicarbonate 고려"""
        node = dka_engine.graph.nodes["severe_dka_pathway"]
        assert "consider_bicarbonate_if_ph_below_6.9" in node.mandatory_actions

    def test_icu_admission_deadline(self, dka_engine):
        """ICU 입원 마감시간 30분"""
        node = dka_engine.graph.nodes["severe_dka_pathway"]
        assert node.deadlines.get("admit_to_icu") == 30


class TestMetadata:
    """가이드라인 메타데이터 테스트"""

    def test_graph_has_source(self):
        """출처 정보 확인"""
        graph_data = get_graph_data()
        assert "metadata" in graph_data
        assert "source" in graph_data["metadata"]
        assert "ADA" in graph_data["metadata"]["source"]

    def test_graph_has_doi(self):
        """DOI 정보 확인"""
        graph_data = get_graph_data()
        assert "doi" in graph_data["metadata"]
        assert graph_data["metadata"]["doi"] is not None

    def test_graph_has_key_recommendation(self):
        """핵심 권고사항 확인"""
        graph_data = get_graph_data()
        assert "key_recommendation" in graph_data["metadata"]
        # 15분 내 수액 투여가 핵심 권고
        assert "15" in graph_data["metadata"]["key_recommendation"]


class TestSequenceDependencies:
    """순서 의존성 테스트"""

    def test_iv_fluid_requires_iv_access(self, dka_engine):
        """수액 투여 전 IV 접근 필요"""
        node = dka_engine.graph.nodes["initial_assessment"]
        required_prior = node.required_prior_actions.get("start_iv_fluid_ns", [])
        assert "establish_iv_access" in required_prior

    def test_insulin_requires_bmp_and_fluids(self, dka_engine):
        """인슐린 전 BMP와 수액 필요"""
        node = dka_engine.graph.nodes["insulin_therapy"]
        required_prior = node.required_prior_actions.get("start_insulin_infusion", [])
        assert "order_lab_bmp" in required_prior
        assert "start_iv_fluid_ns" in required_prior

    def test_transition_requires_gap_closure(self, dka_engine):
        """피하 인슐린 전환 전 anion gap 확인 필요"""
        node = dka_engine.graph.nodes["transition_to_maintenance"]
        required_prior = node.required_prior_actions.get("start_subcutaneous_insulin", [])
        assert "assess_anion_gap_closure" in required_prior


class TestNodeTransitions:
    """노드 전환 테스트"""

    def test_initial_to_severity_classification(self, dka_engine):
        """초기 평가 → 중증도 분류"""
        node = dka_engine.graph.nodes["initial_assessment"]
        assert "severity_classification" in node.next_nodes

    def test_severity_branches_to_potassium_or_insulin(self, dka_engine):
        """중증도 분류에서 K+ 상태에 따른 분기"""
        node = dka_engine.graph.nodes["severity_classification"]
        # conditional_next에서 potassium_replacement_first 또는 insulin_therapy로 분기
        conditions = node.conditional_next
        assert any("potassium" in k.lower() for k in conditions.keys())

    def test_severe_dka_goes_to_insulin_therapy(self, dka_engine):
        """중증 DKA 경로도 결국 인슐린 요법으로"""
        node = dka_engine.graph.nodes["severe_dka_pathway"]
        assert "insulin_therapy" in node.next_nodes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
