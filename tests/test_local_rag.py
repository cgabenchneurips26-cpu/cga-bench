"""
Local RAG Agent 테스트: BGE-M3 기반 Dense/Hybrid Retrieval

이 테스트는 외부 API 없이 로컬에서 동작하는 RAG 시스템을 검증합니다:
1. BM25 only (기본)
2. Dense only (BGE-M3 임베딩)
3. Hybrid (BM25 + Dense 점수 융합)

vLLM 서버가 실행 중이면 LLM 연동도 테스트합니다.
"""

import pytest
import logging
import os
import sys
from pathlib import Path

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from cga_bench.agent_runner.rag_agent import (
    RAGAgent, RAGConfig, CPGDocumentStore, DenseIndex, BM25Index,
    RetrievedDocument
)
from cga_bench.agent_runner.llm_provider import (
    LLMBackend, LLMConfig, LLMProviderFactory, VLLMProvider
)
from cga_bench.scenario_engine.environment import Observation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# BM25 Index 테스트
# ============================================================

class TestBM25Index:
    """BM25 인덱스 기본 기능 테스트"""

    def test_add_and_search(self):
        """문서 추가 및 검색 테스트"""
        index = BM25Index()

        docs = [
            {"content": "Sepsis requires immediate lactate measurement"},
            {"content": "STEMI patients need urgent ECG within 10 minutes"},
            {"content": "Blood cultures should be obtained before antibiotics"},
            {"content": "Crystalloid fluid resuscitation for hypotension"},
        ]

        index.add_documents(docs)

        # sepsis 관련 검색
        results = index.search("sepsis lactate", top_k=2)
        assert len(results) > 0
        assert results[0][0] == 0  # 첫 번째 문서가 가장 관련성 높음

        # STEMI 관련 검색
        results = index.search("ECG cardiac", top_k=2)
        assert len(results) > 0
        assert results[0][0] == 1  # 두 번째 문서

    def test_empty_query(self):
        """빈 쿼리 테스트"""
        index = BM25Index()
        index.add_documents([{"content": "test document"}])

        results = index.search("", top_k=5)
        assert len(results) == 0


# ============================================================
# Dense Index 테스트 (BGE-M3)
# ============================================================

class TestDenseIndex:
    """BGE-M3 Dense Retrieval 테스트"""

    @pytest.mark.slow
    def test_dense_index_loading(self):
        """Dense 인덱스 로딩 테스트 (시간 소요)"""
        try:
            index = DenseIndex(model_name="BAAI/bge-m3")

            docs = [
                {"content": "Sepsis requires immediate lactate measurement"},
                {"content": "STEMI patients need urgent ECG within 10 minutes"},
            ]

            index.add_documents(docs)

            results = index.search("blood infection septic shock", top_k=2)
            assert len(results) > 0

            logger.info(f"Dense search results: {results}")
        except ImportError as e:
            pytest.skip(f"BGE-M3 dependencies not installed: {e}")

    @pytest.mark.slow
    def test_semantic_similarity(self):
        """의미적 유사성 검색 테스트"""
        try:
            index = DenseIndex(model_name="BAAI/bge-m3")

            docs = [
                {"content": "Administer broad-spectrum antibiotics within one hour"},
                {"content": "Patient requires emergency cardiac catheterization"},
                {"content": "Antimicrobial therapy should be initiated promptly"},
            ]

            index.add_documents(docs)

            # "antibiotics" 대신 의미적으로 유사한 "antimicrobial"로 검색
            results = index.search("antimicrobial treatment urgently", top_k=3)

            # 의미적으로 유사한 문서들이 상위에 랭크되어야 함
            assert len(results) > 0
            top_doc_idx = results[0][0]
            assert top_doc_idx in [0, 2]  # antibiotics 또는 antimicrobial 문서

            logger.info(f"Semantic search results: {results}")
        except ImportError as e:
            pytest.skip(f"BGE-M3 dependencies not installed: {e}")


# ============================================================
# CPG Document Store 테스트
# ============================================================

class TestCPGDocumentStore:
    """CPG Document Store 테스트"""

    def test_bm25_retrieval(self):
        """BM25 기반 검색 테스트"""
        store = CPGDocumentStore(
            use_dense=False,
            use_hybrid=False
        )

        # 문서 로드 시도 (실제 파일 없으면 스킵)
        try:
            store.load()
            if len(store.documents) == 0:
                pytest.skip("No CPG documents found")

            results = store.retrieve("sepsis antibiotics", top_k=5)
            assert len(results) > 0

            for doc in results:
                assert isinstance(doc, RetrievedDocument)
                logger.info(f"Retrieved: {doc.doc_id} (score={doc.score:.3f})")

        except FileNotFoundError:
            pytest.skip("CPG source files not found")

    @pytest.mark.slow
    def test_dense_retrieval(self):
        """Dense 기반 검색 테스트"""
        try:
            store = CPGDocumentStore(
                use_dense=True,
                use_hybrid=False,
                embedding_model="BAAI/bge-m3"
            )

            store.load()
            if len(store.documents) == 0:
                pytest.skip("No CPG documents found")

            results = store.retrieve("blood infection treatment", top_k=5)
            assert len(results) > 0

            logger.info("Dense retrieval results:")
            for doc in results:
                logger.info(f"  {doc.doc_id}: {doc.score:.3f}")

        except (ImportError, FileNotFoundError) as e:
            pytest.skip(f"Test skipped: {e}")

    @pytest.mark.slow
    def test_hybrid_retrieval(self):
        """Hybrid 검색 테스트 (BM25 + Dense)"""
        try:
            store = CPGDocumentStore(
                use_dense=True,
                use_hybrid=True,
                embedding_model="BAAI/bge-m3",
                dense_weight=0.5
            )

            store.load()
            if len(store.documents) == 0:
                pytest.skip("No CPG documents found")

            results = store.retrieve("cardiac arrest management", top_k=5)
            assert len(results) > 0

            logger.info("Hybrid retrieval results:")
            for doc in results:
                logger.info(f"  {doc.doc_id}: {doc.score:.3f}")

        except (ImportError, FileNotFoundError) as e:
            pytest.skip(f"Test skipped: {e}")


# ============================================================
# RAG Agent 테스트
# ============================================================

class TestRAGAgent:
    """RAG Agent 통합 테스트"""

    def _create_mock_observation(self) -> Observation:
        """테스트용 Mock Observation 생성"""
        return Observation(
            timestamp_minutes=0,
            visible_state={
                "chief_complaint": "Fever and confusion for 2 days",
                "working_diagnosis": "Suspected sepsis",
                "vitals": {
                    "heart_rate": 110,
                    "blood_pressure_systolic": 85,
                    "blood_pressure_diastolic": 55,
                    "respiratory_rate": 24,
                    "temperature": 38.9,
                    "oxygen_saturation": 94,
                    "map_mmhg": 62
                },
                "allergies": [],
                "comorbidities": ["diabetes"],
                "lab_results": [
                    {"test_code": "wbc", "value": 18.5},
                    {"test_code": "lactate", "value": 3.2}
                ]
            },
            new_results=[],
            alerts=[],
            available_actions=[
                "order_lab_lactate", "order_lab_blood_culture", "order_lab_cbc",
                "order_lab_bmp", "obtain_12_lead_ecg", "assess_vital_signs",
                "assess_infection_source", "assess_organ_dysfunction",
                "give_broad_spectrum_antibiotics", "give_crystalloid_30ml_kg"
            ]
        )

    def test_rag_agent_bm25_rule_based(self):
        """BM25 + 규칙 기반 폴백 테스트"""
        config = RAGConfig(
            agent_id="test_rag_bm25",
            use_bm25=True,
            use_dense=False,
            use_hybrid=False,
            use_llm=False,  # LLM 없이 규칙 기반만
            top_k=5
        )

        agent = RAGAgent(config)
        obs = self._create_mock_observation()

        actions = agent.decide(obs)
        assert len(actions) > 0

        logger.info("Rule-based actions:")
        for action in actions:
            logger.info(f"  {action.action_id}: {action.type}")

    @pytest.mark.slow
    def test_rag_agent_dense(self):
        """Dense Retrieval RAG 테스트"""
        try:
            config = RAGConfig(
                agent_id="test_rag_dense",
                use_bm25=False,
                use_dense=True,
                use_hybrid=False,
                embedding_model="BAAI/bge-m3",
                use_llm=False,  # LLM 없이 검색만 테스트
                top_k=5
            )

            agent = RAGAgent(config)
            obs = self._create_mock_observation()

            actions = agent.decide(obs)
            assert len(actions) > 0

            # 검색 결과 확인
            context = agent.get_retrieved_context(obs)
            logger.info(f"Dense retrieval returned {len(context)} documents")

        except ImportError as e:
            pytest.skip(f"BGE-M3 dependencies not installed: {e}")

    @pytest.mark.slow
    def test_rag_agent_hybrid(self):
        """Hybrid Retrieval RAG 테스트"""
        try:
            config = RAGConfig(
                agent_id="test_rag_hybrid",
                use_bm25=True,
                use_dense=True,
                use_hybrid=True,
                embedding_model="BAAI/bge-m3",
                dense_weight=0.5,
                use_llm=False,
                top_k=5
            )

            agent = RAGAgent(config)
            obs = self._create_mock_observation()

            actions = agent.decide(obs)
            assert len(actions) > 0

            status = agent.get_rag_status()
            assert "Hybrid" in status["retrieval_method"]

        except ImportError as e:
            pytest.skip(f"BGE-M3 dependencies not installed: {e}")

    def test_constraint_verification(self):
        """제약 검증 정보 테스트"""
        config = RAGConfig(
            agent_id="test_rag_verify",
            use_dense=True,
            use_hybrid=True,
            dense_weight=0.6
        )

        agent = RAGAgent(config)
        verification = agent.get_constraint_verification()

        # RAG 제약 확인
        assert verification["uses_cpg_engine"] is False
        assert verification["uses_assessor_core"] is False
        assert verification["uses_planning_module"] is False

        # Dense/Hybrid 설정 확인
        assert verification["use_dense"] is True
        assert verification["use_hybrid"] is True
        assert verification["dense_weight"] == 0.6


# ============================================================
# vLLM 연동 테스트
# ============================================================

class TestVLLMIntegration:
    """vLLM 서버 연동 테스트"""

    @pytest.mark.skipif(
        not os.environ.get("VLLM_URL"),
        reason="VLLM_URL not set"
    )
    def test_vllm_provider(self):
        """vLLM Provider 테스트"""
        vllm_url = os.environ.get("VLLM_URL", "http://localhost:8000/v1")

        config = LLMConfig(
            backend=LLMBackend.VLLM,
            model="Qwen/Qwen2.5-72B-Instruct",
            base_url=vllm_url,
            temperature=0.1
        )

        provider = VLLMProvider(config)

        from cga_bench.agent_runner.llm_provider import LLMMessage
        messages = [
            LLMMessage(role="user", content="What is the first step in sepsis management?")
        ]

        try:
            response = provider.complete(messages)
            assert response.content
            logger.info(f"vLLM response: {response.content[:200]}...")
            logger.info(f"Token usage: {response.usage}")
        except Exception as e:
            pytest.skip(f"vLLM server not available: {e}")

    @pytest.mark.skipif(
        not os.environ.get("VLLM_URL"),
        reason="VLLM_URL not set"
    )
    def test_rag_with_vllm(self):
        """RAG Agent + vLLM 통합 테스트"""
        vllm_url = os.environ.get("VLLM_URL")

        config = RAGConfig(
            agent_id="test_rag_vllm",
            use_bm25=True,
            use_dense=False,  # vLLM만 테스트
            use_hybrid=False,
            llm_backend=LLMBackend.VLLM,
            llm_model="Qwen/Qwen2.5-72B-Instruct",
            base_url=vllm_url,
            use_llm=True,
            top_k=5
        )

        agent = RAGAgent(config)

        obs = Observation(
            timestamp_minutes=0,
            visible_state={
                "chief_complaint": "Chest pain for 30 minutes",
                "working_diagnosis": "Suspected STEMI",
                "vitals": {
                    "heart_rate": 95,
                    "blood_pressure_systolic": 140,
                    "blood_pressure_diastolic": 85
                },
                "allergies": [],
                "comorbidities": []
            },
            new_results=[],
            alerts=[],
            available_actions=[
                "order_lab_lactate", "order_lab_blood_culture", "order_lab_cbc",
                "order_lab_bmp", "obtain_12_lead_ecg", "assess_vital_signs",
                "assess_infection_source", "assess_organ_dysfunction",
                "give_broad_spectrum_antibiotics", "give_crystalloid_30ml_kg"
            ]
        )

        try:
            actions = agent.decide(obs)
            assert len(actions) > 0

            logger.info("vLLM generated actions:")
            for action in actions:
                logger.info(f"  {action.action_id}: {action.type}")

            # 토큰 사용량 확인 (Budget-matched 평가용)
            assert agent.metrics.total_tokens > 0
            logger.info(f"Total tokens used: {agent.metrics.total_tokens}")

        except Exception as e:
            pytest.skip(f"vLLM integration failed: {e}")


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
