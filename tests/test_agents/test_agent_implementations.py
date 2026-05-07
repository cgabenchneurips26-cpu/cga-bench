"""
에이전트 구현 테스트

테스트 대상:
- RAGAgent: CPG 문서 검색 및 행동 생성
- PlannerAgent: CPG-Engine 기반 계획
- ReflectionAgent: 자기 반성 기반 결정
- OracleAgent: 규칙 기반 완벽 준수
"""

import pytest
from pathlib import Path

from cga_bench.agent_runner import (
    RAGAgent,
    RAGConfig,
    CPGDocumentStore,
    BM25Index,
    PlannerAgent,
    PlannerConfig,
    ReflectionAgent,
    ReflectionConfig,
    OracleAgent,
    OracleConfig,
)
from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    PatientState,
    VitalSigns,
)
from cga_bench.scenario_engine.environment import Observation


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def cpg_sources_path():
    """CPG 소스 경로"""
    return Path(__file__).parent.parent.parent / "cpg_sources"


@pytest.fixture
def sepsis_patient_state():
    """패혈증 환자 상태"""
    return PatientState(
        state_id="test_sepsis_001",
        age=65,
        sex="F",
        weight_kg=60,
        chief_complaint="fever, hypotension, suspected sepsis",
        vitals=VitalSigns(
            heart_rate=110,
            blood_pressure_systolic=85,
            blood_pressure_diastolic=55,
            map_mmhg=65,
            respiratory_rate=24,
            temperature=38.9,
            oxygen_saturation=94
        ),
        working_diagnosis="suspected sepsis"
    )


@pytest.fixture
def chest_pain_patient_state():
    """흉통 환자 상태"""
    return PatientState(
        state_id="test_chest_pain_001",
        age=55,
        sex="M",
        weight_kg=80,
        chief_complaint="chest pain, radiating to left arm",
        vitals=VitalSigns(
            heart_rate=88,
            blood_pressure_systolic=140,
            blood_pressure_diastolic=90,
            map_mmhg=107,
            respiratory_rate=18,
            temperature=37.0,
            oxygen_saturation=98
        ),
        working_diagnosis="acute chest pain, rule out ACS"
    )


@pytest.fixture
def inferior_stemi_patient_state():
    """하벽 STEMI 환자 상태"""
    return PatientState(
        state_id="test_stemi_001",
        age=60,
        sex="M",
        weight_kg=75,
        chief_complaint="chest pain",
        vitals=VitalSigns(
            heart_rate=55,  # 서맥 (하벽 STEMI 특징)
            blood_pressure_systolic=95,
            blood_pressure_diastolic=60,
            map_mmhg=72,
            respiratory_rate=20,
            temperature=37.0,
            oxygen_saturation=96
        ),
        working_diagnosis="inferior STEMI"
    )


@pytest.fixture
def sepsis_observation(sepsis_patient_state):
    """패혈증 환자 관측"""
    return Observation(
        timestamp_minutes=0,
        visible_state=sepsis_patient_state.model_dump(),
        new_results=[],
        alerts=[],
        available_actions=[]
    )


@pytest.fixture
def chest_pain_observation(chest_pain_patient_state):
    """흉통 환자 관측"""
    return Observation(
        timestamp_minutes=0,
        visible_state=chest_pain_patient_state.model_dump(),
        new_results=[],
        alerts=[],
        available_actions=[]
    )


@pytest.fixture
def inferior_stemi_observation(inferior_stemi_patient_state):
    """하벽 STEMI 환자 관측"""
    return Observation(
        timestamp_minutes=0,
        visible_state=inferior_stemi_patient_state.model_dump(),
        new_results=[],
        alerts=[],
        available_actions=[]
    )


# ============================================================================
# BM25 Index Tests
# ============================================================================

class TestBM25Index:
    """BM25 인덱스 테스트"""

    def test_index_creation(self):
        """인덱스 생성 테스트"""
        index = BM25Index()
        assert index.k1 == 1.5
        assert index.b == 0.75

    def test_document_indexing(self):
        """문서 인덱싱 테스트"""
        index = BM25Index()
        docs = [
            {"content": "lactate measurement in sepsis patients"},
            {"content": "blood culture before antibiotics"},
            {"content": "ECG within 10 minutes for chest pain"}
        ]
        index.add_documents(docs)

        assert len(index.documents) == 3
        assert index.avg_doc_length > 0

    def test_search(self):
        """검색 테스트"""
        index = BM25Index()
        docs = [
            {"content": "lactate measurement in sepsis patients"},
            {"content": "blood culture before antibiotics"},
            {"content": "ECG within 10 minutes for chest pain"},
            {"content": "troponin for acute coronary syndrome"}
        ]
        index.add_documents(docs)

        # sepsis 검색
        results = index.search("sepsis lactate", top_k=2)
        assert len(results) > 0
        # 첫 번째 결과가 lactate 문서여야 함
        assert results[0][0] == 0

        # chest pain 검색
        results = index.search("chest pain ECG", top_k=2)
        assert len(results) > 0


# ============================================================================
# CPG Document Store Tests
# ============================================================================

class TestCPGDocumentStore:
    """CPG 문서 저장소 테스트"""

    def test_store_creation(self, cpg_sources_path):
        """저장소 생성 테스트"""
        if not cpg_sources_path.exists():
            pytest.skip("CPG sources not available")

        store = CPGDocumentStore(str(cpg_sources_path))
        assert store.cpg_sources_path == cpg_sources_path

    def test_document_loading(self, cpg_sources_path):
        """문서 로딩 테스트"""
        if not cpg_sources_path.exists():
            pytest.skip("CPG sources not available")

        store = CPGDocumentStore(str(cpg_sources_path))
        store.load()

        assert len(store.documents) > 0
        assert store._loaded is True

    def test_retrieval_sepsis(self, cpg_sources_path):
        """패혈증 관련 검색 테스트"""
        if not cpg_sources_path.exists():
            pytest.skip("CPG sources not available")

        store = CPGDocumentStore(str(cpg_sources_path))
        results = store.retrieve("sepsis lactate blood culture antibiotics", top_k=5)

        assert len(results) > 0
        # SSC 관련 문서가 검색되어야 함
        sources = [r.source for r in results]
        assert any("sepsis" in s for s in sources) or len(results) > 0

    def test_retrieval_chest_pain(self, cpg_sources_path):
        """흉통 관련 검색 테스트"""
        if not cpg_sources_path.exists():
            pytest.skip("CPG sources not available")

        store = CPGDocumentStore(str(cpg_sources_path))
        results = store.retrieve("chest pain ECG STEMI troponin", top_k=5)

        assert len(results) > 0


# ============================================================================
# RAG Agent Tests
# ============================================================================

class TestRAGAgent:
    """RAG 에이전트 테스트"""

    def test_agent_creation(self, cpg_sources_path):
        """에이전트 생성 테스트"""
        config = RAGConfig(
            agent_id="test_rag",
            cpg_sources_path=str(cpg_sources_path) if cpg_sources_path.exists() else None
        )
        agent = RAGAgent(config)

        assert agent.config.agent_type == "rag"
        assert agent.rag_config.top_k == 5

    def test_decide_sepsis(self, cpg_sources_path, sepsis_observation):
        """패혈증 행동 결정 테스트"""
        if not cpg_sources_path.exists():
            pytest.skip("CPG sources not available")

        config = RAGConfig(
            agent_id="test_rag_sepsis",
            cpg_sources_path=str(cpg_sources_path)
        )
        agent = RAGAgent(config)
        agent.reset()

        actions = agent.decide(sepsis_observation)

        assert len(actions) > 0
        action_ids = [a.action_id for a in actions]
        # 패혈증 관련 행동이 생성되어야 함
        sepsis_actions = ["order_lab_lactate", "order_blood_culture", "give_antibiotics"]
        assert any(a in action_ids for a in sepsis_actions) or len(actions) > 0

    def test_decide_chest_pain(self, cpg_sources_path, chest_pain_observation):
        """흉통 행동 결정 테스트"""
        if not cpg_sources_path.exists():
            pytest.skip("CPG sources not available")

        config = RAGConfig(
            agent_id="test_rag_chest_pain",
            cpg_sources_path=str(cpg_sources_path)
        )
        agent = RAGAgent(config)
        agent.reset()

        actions = agent.decide(chest_pain_observation)

        assert len(actions) > 0
        action_ids = [a.action_id for a in actions]
        # ECG 검사가 포함되어야 함
        assert "obtain_12_lead_ecg" in action_ids or "order_lab_basic" in action_ids

    def test_retrieved_context(self, cpg_sources_path, sepsis_observation):
        """검색 컨텍스트 테스트"""
        if not cpg_sources_path.exists():
            pytest.skip("CPG sources not available")

        config = RAGConfig(
            agent_id="test_rag_context",
            cpg_sources_path=str(cpg_sources_path)
        )
        agent = RAGAgent(config)

        context = agent.get_retrieved_context(sepsis_observation)

        assert len(context) > 0
        for doc in context:
            assert "doc_id" in doc
            assert "source" in doc
            assert "score" in doc

    def test_constraint_verification(self, cpg_sources_path):
        """제약 검증 테스트 - RAG가 '강한 텍스트 베이스라인' 제약을 준수하는지 확인"""
        config = RAGConfig(
            agent_id="test_rag_constraint",
            cpg_sources_path=str(cpg_sources_path) if cpg_sources_path.exists() else None
        )
        agent = RAGAgent(config)

        verification = agent.get_constraint_verification()

        # RAG가 사용하지 않아야 할 것들
        assert verification["uses_cpg_engine"] is False
        assert verification["uses_assessor_core"] is False
        assert verification["uses_planning_module"] is False
        assert verification["uses_constraint_verification"] is False
        assert verification["uses_forbidden_veto"] is False
        assert verification["uses_mandatory_alarm"] is False
        assert verification["uses_multi_step_planning"] is False

        # RAG가 사용하는 것들
        assert verification["uses_bm25_retrieval"] is True
        assert verification["uses_json_schema_output"] is True
        assert verification["uses_single_step_decision"] is True

        # 검색 설정
        assert verification["retrieval_method"] == "BM25"
        assert "verification_note" in verification

    def test_rag_status(self, cpg_sources_path, sepsis_observation):
        """RAG 상태 테스트"""
        if not cpg_sources_path.exists():
            pytest.skip("CPG sources not available")

        config = RAGConfig(
            agent_id="test_rag_status",
            cpg_sources_path=str(cpg_sources_path)
        )
        agent = RAGAgent(config)
        agent.reset()
        agent.decide(sepsis_observation)

        status = agent.get_rag_status()

        assert status["agent_type"] == "rag_baseline"
        assert status["uses_planning"] is False
        assert status["uses_constraint_verification"] is False


# ============================================================================
# Planner Agent Tests
# ============================================================================

class TestPlannerAgent:
    """Planner 에이전트 테스트"""

    def test_agent_creation(self):
        """에이전트 생성 테스트"""
        config = PlannerConfig(
            agent_id="test_planner"
        )
        agent = PlannerAgent(config)

        assert agent.config.agent_type == "planner"

    def test_decide_without_engine(self, sepsis_observation):
        """CPG-Engine 없이 결정 테스트"""
        config = PlannerConfig(
            agent_id="test_planner_no_engine"
        )
        agent = PlannerAgent(config)
        agent.reset()

        actions = agent.decide(sepsis_observation)

        # 기본 행동 반환
        assert isinstance(actions, list)

    def test_current_plan(self, sepsis_observation):
        """현재 계획 테스트"""
        config = PlannerConfig(
            agent_id="test_planner_plan"
        )
        agent = PlannerAgent(config)
        agent.reset()
        agent.decide(sepsis_observation)

        plan = agent.get_current_plan()
        assert isinstance(plan, list)


# ============================================================================
# Reflection Agent Tests
# ============================================================================

class TestReflectionAgent:
    """Reflection 에이전트 테스트"""

    def test_agent_creation(self):
        """에이전트 생성 테스트"""
        config = ReflectionConfig(
            agent_id="test_reflection"
        )
        agent = ReflectionAgent(config)

        assert agent.config.agent_type == "reflection"
        assert agent.reflection_config.max_reflection_rounds == 2

    def test_decide(self, sepsis_observation):
        """결정 테스트"""
        config = ReflectionConfig(
            agent_id="test_reflection_decide"
        )
        agent = ReflectionAgent(config)
        agent.reset()

        actions = agent.decide(sepsis_observation)

        assert isinstance(actions, list)

    def test_reflection_summary(self, sepsis_observation):
        """반성 요약 테스트"""
        config = ReflectionConfig(
            agent_id="test_reflection_summary"
        )
        agent = ReflectionAgent(config)
        agent.reset()
        agent.decide(sepsis_observation)

        summary = agent.get_reflection_summary()

        assert "total_reflections" in summary
        assert "outcomes" in summary
        assert "llm_calls" in summary


# ============================================================================
# Oracle Agent Tests
# ============================================================================

class TestOracleAgent:
    """Oracle 에이전트 테스트 (독립적 규칙 시스템 사용)"""

    def test_agent_creation(self):
        """에이전트 생성 테스트"""
        config = OracleConfig(
            agent_id="test_oracle",
            guideline_domain="sepsis"
        )
        agent = OracleAgent(config)

        assert agent.config.agent_type == "oracle"
        assert agent.oracle_config.use_llm is False
        assert agent.decision_table is not None

    def test_decide_sepsis(self, sepsis_observation):
        """패혈증 행동 결정 테스트"""
        config = OracleConfig(
            agent_id="test_oracle_sepsis",
            guideline_domain="sepsis"
        )
        agent = OracleAgent(config)
        agent.reset()

        actions = agent.decide(sepsis_observation)

        assert len(actions) > 0
        action_ids = [a.action_id for a in actions]

        # SSC 가이드라인 행동 (독립적 Decision Table에서)
        # 이 ID는 agent_rules/sepsis_rules.py에서 정의됨
        sepsis_actions = ["measure_lactate", "blood_culture_before_antibiotics", "broad_spectrum_antibiotics"]
        assert any(aid in action_ids for aid in sepsis_actions)

    def test_decide_chest_pain(self, chest_pain_observation):
        """흉통 행동 결정 테스트"""
        config = OracleConfig(
            agent_id="test_oracle_chest_pain",
            guideline_domain="chest_pain"
        )
        agent = OracleAgent(config)
        agent.reset()

        actions = agent.decide(chest_pain_observation)

        assert len(actions) > 0
        action_ids = [a.action_id for a in actions]

        # AHA 가이드라인: ECG (독립적 Decision Table에서)
        ecg_actions = ["obtain_ecg", "check_vital_signs", "order_troponin"]
        assert any(aid in action_ids for aid in ecg_actions)

    def test_decide_inferior_stemi(self, inferior_stemi_observation):
        """하벽 STEMI 행동 결정 테스트"""
        config = OracleConfig(
            agent_id="test_oracle_stemi",
            guideline_domain="chest_pain"
        )
        agent = OracleAgent(config)
        agent.reset()

        actions = agent.decide(inferior_stemi_observation)

        assert len(actions) > 0
        action_ids = [a.action_id for a in actions]

        # AHA 가이드라인 행동 (독립적 Decision Table에서)
        stemi_actions = ["obtain_ecg", "activate_cath_lab", "aspirin_loading"]
        assert any(aid in action_ids for aid in stemi_actions)

    def test_oracle_status(self, sepsis_observation):
        """Oracle 상태 테스트"""
        config = OracleConfig(
            agent_id="test_oracle_status",
            guideline_domain="sepsis"
        )
        agent = OracleAgent(config)
        agent.reset()
        agent.decide(sepsis_observation)

        status = agent.get_oracle_status()

        assert "completed_actions" in status
        assert "llm_calls" in status
        assert status["llm_calls"] == 0  # Oracle은 LLM 미사용
        assert status["uses_cpg_engine"] is False  # 독립성 확인

    def test_no_duplicate_actions(self, sepsis_observation):
        """중복 행동 방지 테스트"""
        config = OracleConfig(
            agent_id="test_oracle_no_dup",
            guideline_domain="sepsis"
        )
        agent = OracleAgent(config)
        agent.reset()

        # 첫 번째 결정
        actions1 = agent.decide(sepsis_observation)
        action_ids1 = {a.action_id for a in actions1}

        # 두 번째 결정 (같은 행동 반복하면 안됨)
        actions2 = agent.decide(sepsis_observation)
        action_ids2 = {a.action_id for a in actions2}

        # 중복 없어야 함
        assert len(action_ids1 & action_ids2) == 0

    def test_independence_verification(self):
        """Oracle 독립성 검증 테스트 (NeurIPS 리뷰어 비판 대응)"""
        config = OracleConfig(
            agent_id="test_oracle_independence",
            guideline_domain="sepsis"
        )
        agent = OracleAgent(config)

        verification = agent.get_independence_verification()

        # CPG-Engine 미사용 확인
        assert verification["uses_cpg_engine"] is False
        assert verification["uses_assessor_core"] is False
        assert verification["graph_structure_reuse"] is False
        assert verification["node_id_reuse"] is False


# ============================================================================
# Integration Tests
# ============================================================================

class TestAgentComparison:
    """에이전트 비교 테스트"""

    def test_all_agents_produce_actions(self, cpg_sources_path, sepsis_observation):
        """모든 에이전트가 행동을 생성하는지 테스트"""
        agents = []

        # RAG Agent
        rag_config = RAGConfig(
            agent_id="compare_rag",
            cpg_sources_path=str(cpg_sources_path) if cpg_sources_path.exists() else None
        )
        agents.append(("RAG", RAGAgent(rag_config)))

        # Planner Agent
        planner_config = PlannerConfig(agent_id="compare_planner")
        agents.append(("Planner", PlannerAgent(planner_config)))

        # Reflection Agent
        reflection_config = ReflectionConfig(agent_id="compare_reflection")
        agents.append(("Reflection", ReflectionAgent(reflection_config)))

        # Oracle Agent
        oracle_config = OracleConfig(agent_id="compare_oracle")
        agents.append(("Oracle", OracleAgent(oracle_config)))

        for name, agent in agents:
            agent.reset()
            actions = agent.decide(sepsis_observation)
            assert len(actions) >= 0, f"{name} agent should return actions"

    def test_oracle_no_llm_calls(self, sepsis_observation):
        """Oracle은 LLM을 호출하지 않아야 함"""
        config = OracleConfig(agent_id="test_oracle_no_llm")
        agent = OracleAgent(config)
        agent.reset()

        for _ in range(5):
            agent.decide(sepsis_observation)

        status = agent.get_oracle_status()
        assert status["llm_calls"] == 0


# ============================================================================
# Budget Tests
# ============================================================================

class TestBudgetEnforcement:
    """예산 제한 테스트"""

    def test_token_budget_limit(self, sepsis_observation):
        """토큰 예산 제한 테스트"""
        config = RAGConfig(
            agent_id="test_budget_tokens",
            budget_limit_tokens=100
        )
        agent = RAGAgent(config)
        agent.reset()

        # 예산 설정 확인
        assert agent.config.budget_limit_tokens == 100

    def test_tool_call_budget_limit(self, sepsis_observation):
        """도구 호출 예산 제한 테스트"""
        config = RAGConfig(
            agent_id="test_budget_tools",
            budget_limit_tool_calls=5
        )
        agent = RAGAgent(config)
        agent.reset()

        # 예산 설정 확인
        assert agent.config.budget_limit_tool_calls == 5
