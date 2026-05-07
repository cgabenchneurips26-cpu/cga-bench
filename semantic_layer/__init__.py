"""
Semantic Layer: LLM-Assist CPG Interpretation Module

이 모듈은 rule_based의 높은 정확도와 LLM의 확장성을 결합합니다.

핵심 컴포넌트:
1. CPGParser - CPG 문서를 구조화된 추천사항으로 파싱
2. ConstraintSynthesizer - LLM으로 동적 규칙 생성
3. ActionNormalizer - LLM 출력을 유효한 액션으로 변환
4. SemanticValidator - 임상 컨텍스트 기반 검증

설계 원칙:
- 새로운 CPG 도메인에 대한 자동 확장
- rule_based 수준의 정확도 목표
- 수동 Decision Table 작성 불필요
"""

from .cpg_parser import CPGParser, ParsedGuideline
from .constraint_synthesizer import (
    ConstraintSynthesizer,
    SynthesizedConstraints,
)
from .action_normalizer import SemanticActionNormalizer
from .semantic_validator import SemanticValidator
from .llm_assist_agent import LLMAssistAgent, LLMAssistConfig
from .mining import PathwayMiner, MiningConfig, MiningResult

__all__ = [
    "CPGParser",
    "ParsedGuideline",
    "ConstraintSynthesizer",
    "SynthesizedConstraints",
    "SemanticActionNormalizer",
    "SemanticValidator",
    "LLMAssistAgent",
    "LLMAssistConfig",
    "PathwayMiner",
    "MiningConfig",
    "MiningResult",
]
