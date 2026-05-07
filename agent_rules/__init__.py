"""
Agent Rules: 에이전트 전용 규칙 기반 의사결정 모듈

이 모듈은 채점용 CPG-Engine과 완전히 분리된 독립적인 규칙 기반 시스템입니다.

설계 원칙:
1. 채점용 CPG-Engine의 그래프 구조/노드ID/메타데이터를 재사용하지 않음
2. 동일한 CPG 텍스트 가이드라인을 참조하되, 독립적으로 구현
3. Oracle은 "Upper-bound 참고치"로 위치하며, 치팅 방지를 위해 분리됨

주요 컴포넌트:
- RuleBasedDecisionTable: 규칙 기반 의사결정 테이블 (Oracle용)
- ClinicalRuleSet: 임상 규칙 집합
- DecisionTableEntry: 의사결정 테이블 엔트리
"""

from cga_bench.agent_rules.decision_table import (
    RuleBasedDecisionTable,
    ClinicalRuleSet,
    DecisionTableEntry,
    ClinicalCondition,
    ActionRecommendation,
)

from cga_bench.agent_rules.sepsis_rules import SepsisDecisionTable
from cga_bench.agent_rules.chest_pain_rules import ChestPainDecisionTable
from cga_bench.agent_rules.aki_rules import AKIDecisionTable
from cga_bench.agent_rules.dka_rules import DKADecisionTable
from cga_bench.agent_rules.heart_failure_rules import HeartFailureDecisionTable
from cga_bench.agent_rules.stroke_rules import StrokeDecisionTable

__all__ = [
    # Base classes
    "RuleBasedDecisionTable",
    "ClinicalRuleSet",
    "DecisionTableEntry",
    "ClinicalCondition",
    "ActionRecommendation",
    # Domain-specific tables
    "SepsisDecisionTable",
    "ChestPainDecisionTable",
    "AKIDecisionTable",
    "DKADecisionTable",
    "HeartFailureDecisionTable",
    "StrokeDecisionTable",
]
