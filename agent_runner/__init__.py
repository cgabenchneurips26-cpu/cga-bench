"""
Agent Runner: CGA-Bench 에이전트 모듈

에이전트 유형:
- BaseAgent: 추상 기본 클래스
- RAGAgent: RAG-only Baseline (CPG 문서 검색 기반, 제약 검증 없음)
- PlannerAgent: Planning 기반 에이전트
- ReflectionAgent: 자기 반성 에이전트 (Budget-matched)
- OracleAgent: Rule-based Upper Bound (독립적 규칙 시스템 사용)

LLM Provider:
- LLMProviderFactory: LLM 백엔드 팩토리
- OpenAI, Anthropic, vLLM, Mock 지원

시스템 분리 원칙 (NeurIPS 리뷰어 비판 대응):
- 에이전트는 채점용 CPG-Engine(cpg_engine/)에 직접 접근 불가
- 에이전트는 assessor_core/에 접근 불가
- Oracle은 독립적인 agent_rules/ 사용 (그래프 구조/노드ID 재사용 금지)
- RAG는 planning 모듈 및 제약 검증 금지
- 모든 에이전트는 Budget-matched 평가
"""

from cga_bench.agent_runner.base_agent import (
    BaseAgent,
    AgentConfig,
    AgentMetrics,
)

from cga_bench.agent_runner.llm_provider import (
    LLMConfig,
    LLMBackend,
    LLMMessage,
    LLMResponse,
    BaseLLMProvider,
    OpenAIProvider,
    AnthropicProvider,
    VLLMProvider,
    MockLLMProvider,
    LLMProviderFactory,
    CLINICAL_SYSTEM_PROMPT,
    ACTION_RECOMMENDATION_SCHEMA,
)

from cga_bench.agent_runner.rag_agent import (
    RAGAgent,
    RAGConfig,
    CPGDocumentStore,
    BM25Index,
    RetrievedDocument,
)

from cga_bench.agent_runner.planner_agent import (
    PlannerAgent,
    PlannerConfig,
    PlannedAction,
    PlanStatus,
)

from cga_bench.agent_runner.reflection_agent import (
    ReflectionAgent,
    ReflectionConfig,
    ReflectionResult,
    ReflectionOutcome,
)

from cga_bench.agent_runner.oracle_agent import (
    OracleAgent,
    OracleConfig,
)

__all__ = [
    # Base
    "BaseAgent",
    "AgentConfig",
    "AgentMetrics",
    # LLM Provider
    "LLMConfig",
    "LLMBackend",
    "LLMMessage",
    "LLMResponse",
    "BaseLLMProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "VLLMProvider",
    "MockLLMProvider",
    "LLMProviderFactory",
    "CLINICAL_SYSTEM_PROMPT",
    "ACTION_RECOMMENDATION_SCHEMA",
    # RAG
    "RAGAgent",
    "RAGConfig",
    "CPGDocumentStore",
    "BM25Index",
    "RetrievedDocument",
    # Planner
    "PlannerAgent",
    "PlannerConfig",
    "PlannedAction",
    "PlanStatus",
    # Reflection
    "ReflectionAgent",
    "ReflectionConfig",
    "ReflectionResult",
    "ReflectionOutcome",
    # Oracle
    "OracleAgent",
    "OracleConfig",
]
