"""
LLM Provider 테스트
"""
import pytest
from unittest.mock import Mock, patch
import json

from cga_bench.agent_runner.llm_provider import (
    LLMConfig,
    LLMBackend,
    LLMMessage,
    LLMResponse,
    BaseLLMProvider,
    MockLLMProvider,
    LLMProviderFactory,
    CLINICAL_SYSTEM_PROMPT,
    ACTION_RECOMMENDATION_SCHEMA,
)


class TestLLMConfig:
    """LLMConfig 테스트"""

    def test_default_config(self):
        """기본 설정 테스트"""
        config = LLMConfig()
        assert config.backend == LLMBackend.OPENAI
        assert config.model == "gpt-4"
        assert config.temperature == 0.1
        # max_tokens default was raised 2048 -> 4096 (commit 3f902c9c, 2026-04-04)
        # to accommodate DeepSeek reasoning-block outputs and larger JSON payloads.
        assert config.max_tokens == 4096

    def test_custom_config(self):
        """커스텀 설정 테스트"""
        config = LLMConfig(
            backend=LLMBackend.ANTHROPIC,
            model="claude-3-5-sonnet-20241022",
            temperature=0.2,
            max_tokens=4096
        )
        assert config.backend == LLMBackend.ANTHROPIC
        assert config.model == "claude-3-5-sonnet-20241022"
        assert config.temperature == 0.2
        assert config.max_tokens == 4096

    def test_vllm_config(self):
        """vLLM 설정 테스트"""
        config = LLMConfig(
            backend=LLMBackend.VLLM,
            model="Qwen/Qwen2.5-72B-Instruct",
            base_url="http://localhost:8000/v1"
        )
        assert config.backend == LLMBackend.VLLM
        assert config.base_url == "http://localhost:8000/v1"


class TestMockLLMProvider:
    """Mock Provider 테스트"""

    def test_provider_creation(self):
        """Mock Provider 생성 테스트"""
        config = LLMConfig(backend=LLMBackend.MOCK)
        provider = MockLLMProvider(config)
        assert provider is not None
        assert provider.call_count == 0

    def test_complete(self):
        """기본 complete 테스트"""
        config = LLMConfig(backend=LLMBackend.MOCK)
        provider = MockLLMProvider(config)

        messages = [
            LLMMessage(role="user", content="What should we do for sepsis?")
        ]

        response = provider.complete(messages)
        assert isinstance(response, LLMResponse)
        assert response.content is not None
        assert len(response.content) > 0
        assert response.model == "mock"
        assert provider.call_count == 1

    def test_complete_with_predefined_responses(self):
        """사전 정의된 응답 테스트"""
        config = LLMConfig(backend=LLMBackend.MOCK)
        responses = ["First response", "Second response"]
        provider = MockLLMProvider(config, responses=responses)

        messages = [LLMMessage(role="user", content="test")]

        response1 = provider.complete(messages)
        assert response1.content == "First response"

        response2 = provider.complete(messages)
        assert response2.content == "Second response"

    def test_complete_json_sepsis(self):
        """Sepsis 시나리오 JSON 응답 테스트"""
        config = LLMConfig(backend=LLMBackend.MOCK)
        provider = MockLLMProvider(config)

        messages = [
            LLMMessage(role="system", content="You are a medical AI"),
            LLMMessage(role="user", content="Patient has sepsis. Recommend actions.")
        ]

        result = provider.complete_json(messages, ACTION_RECOMMENDATION_SCHEMA)

        assert "actions" in result
        assert "reasoning" in result
        assert len(result["actions"]) > 0

        # Sepsis 관련 행동 확인
        action_ids = [a["action_id"] for a in result["actions"]]
        assert any("lactate" in aid for aid in action_ids)
        assert any("blood_culture" in aid or "culture" in aid for aid in action_ids)

    def test_complete_json_chest_pain(self):
        """Chest Pain 시나리오 JSON 응답 테스트"""
        config = LLMConfig(backend=LLMBackend.MOCK)
        provider = MockLLMProvider(config)

        messages = [
            LLMMessage(role="system", content="You are a medical AI"),
            LLMMessage(role="user", content="Patient has chest pain, suspected STEMI.")
        ]

        result = provider.complete_json(messages, ACTION_RECOMMENDATION_SCHEMA)

        assert "actions" in result
        action_ids = [a["action_id"] for a in result["actions"]]
        assert any("ecg" in aid for aid in action_ids)

    def test_call_history_tracking(self):
        """호출 이력 추적 테스트"""
        config = LLMConfig(backend=LLMBackend.MOCK)
        provider = MockLLMProvider(config)

        messages1 = [LLMMessage(role="user", content="first")]
        messages2 = [LLMMessage(role="user", content="second")]

        provider.complete(messages1)
        provider.complete(messages2)

        assert len(provider.call_history) == 2
        assert provider.call_history[0][0].content == "first"
        assert provider.call_history[1][0].content == "second"


class TestLLMProviderFactory:
    """Provider Factory 테스트"""

    def test_create_mock_provider(self):
        """Mock Provider 생성 테스트"""
        config = LLMConfig(backend=LLMBackend.MOCK)
        provider = LLMProviderFactory.create(config)
        assert isinstance(provider, MockLLMProvider)

    def test_create_from_env_without_keys(self):
        """환경변수 없이 생성 시 RuntimeError"""
        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(RuntimeError, match="No LLM configuration found"):
                LLMProviderFactory.create_from_env()


class TestLLMMessage:
    """LLMMessage 테스트"""

    def test_message_creation(self):
        """메시지 생성 테스트"""
        msg = LLMMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_system_message(self):
        """시스템 메시지 테스트"""
        msg = LLMMessage(role="system", content=CLINICAL_SYSTEM_PROMPT)
        assert msg.role == "system"
        assert "clinical decision" in msg.content.lower()


class TestClinicalPrompts:
    """임상 프롬프트 테스트"""

    def test_clinical_system_prompt_exists(self):
        """임상 시스템 프롬프트 존재 확인"""
        assert CLINICAL_SYSTEM_PROMPT is not None
        assert len(CLINICAL_SYSTEM_PROMPT) > 100

    def test_clinical_prompt_has_key_elements(self):
        """프롬프트 핵심 요소 확인"""
        prompt_lower = CLINICAL_SYSTEM_PROMPT.lower()
        assert "clinical" in prompt_lower
        assert "guideline" in prompt_lower
        assert "safety" in prompt_lower

    def test_action_schema_is_valid_json_schema(self):
        """액션 스키마가 유효한 JSON 스키마인지 확인"""
        assert "type" in ACTION_RECOMMENDATION_SCHEMA
        assert ACTION_RECOMMENDATION_SCHEMA["type"] == "object"
        assert "properties" in ACTION_RECOMMENDATION_SCHEMA
        assert "actions" in ACTION_RECOMMENDATION_SCHEMA["properties"]
        assert "reasoning" in ACTION_RECOMMENDATION_SCHEMA["properties"]


class TestLLMResponse:
    """LLMResponse 테스트"""

    def test_response_creation(self):
        """응답 생성 테스트"""
        response = LLMResponse(
            content="Test response",
            model="gpt-4",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        )
        assert response.content == "Test response"
        assert response.model == "gpt-4"
        assert response.usage["total_tokens"] == 150

    def test_response_without_usage(self):
        """usage 없는 응답 테스트"""
        response = LLMResponse(content="Test", model="mock")
        assert response.usage == {}


class TestRAGAgentWithMockLLM:
    """RAG Agent Mock LLM 통합 테스트"""

    def test_rag_agent_with_mock_llm(self):
        """RAG Agent가 Mock LLM과 함께 동작하는지 테스트"""
        from cga_bench.agent_runner import RAGAgent, RAGConfig, LLMBackend
        from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns
        from cga_bench.scenario_engine.environment import Observation

        config = RAGConfig(
            agent_id="test_rag",
            llm_backend=LLMBackend.MOCK,
            use_llm=True
        )
        agent = RAGAgent(config)

        patient_state = PatientState(
            state_id="test_001",
            age=65,
            sex="M",
            weight_kg=70,
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
            working_diagnosis="septic_shock"
        )

        observation = Observation(
            timestamp_minutes=0,
            visible_state=patient_state.model_dump(),
            new_results=[],
            alerts=[],
            available_actions=[]
        )

        actions = agent.decide(observation)

        assert len(actions) > 0
        assert agent.metrics.total_llm_calls == 1


class TestPlannerAgentWithMockLLM:
    """Planner Agent Mock LLM 통합 테스트"""

    def test_planner_agent_with_mock_llm(self):
        """Planner Agent가 Mock LLM과 함께 동작하는지 테스트"""
        from cga_bench.agent_runner import PlannerAgent, PlannerConfig, LLMBackend
        from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns
        from cga_bench.scenario_engine.environment import Observation

        config = PlannerConfig(
            agent_id="test_planner",
            llm_backend=LLMBackend.MOCK,
            use_llm=True
        )
        agent = PlannerAgent(config)

        patient_state = PatientState(
            state_id="test_001",
            age=65,
            sex="M",
            weight_kg=70,
            chief_complaint="chest pain",
            vitals=VitalSigns(
                heart_rate=88,
                blood_pressure_systolic=130,
                blood_pressure_diastolic=80,
                respiratory_rate=18,
                temperature=37.0,
                oxygen_saturation=96
            ),
            working_diagnosis="suspected_acs"
        )

        observation = Observation(
            timestamp_minutes=0,
            visible_state=patient_state.model_dump(),
            new_results=[],
            alerts=[],
            available_actions=[]
        )

        actions = agent.decide(observation)
        # Planner without CPG engine produces default actions
        assert isinstance(actions, list)
