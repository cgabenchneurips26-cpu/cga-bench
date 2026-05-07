"""
Rule-based Decision Table: 채점용 CPG-Engine과 분리된 독립적 규칙 시스템

설계 원칙 (NeurIPS 리뷰어 비판 대응):
1. 채점용 CPG-Engine의 그래프 구조/노드ID를 재사용하지 않음
2. CPG 텍스트 가이드라인에서 사람이 작성한 Decision Table 사용
3. Oracle은 "Upper-bound 참고치"로 위치 - 완벽한 규칙 준수의 이론적 상한

이 모듈은 다음을 직접 참조하지 않음:
- cpg_engine/
- cpg_model/graphs/
- assessor_core/
"""

from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class ConditionOperator(Enum):
    """조건 연산자"""
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_EQUAL = "ge"
    LESS_THAN = "lt"
    LESS_EQUAL = "le"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"


@dataclass
class ClinicalCondition:
    """
    임상 조건 정의

    CPG 텍스트에서 추출한 조건을 표현합니다.
    예: "MAP < 65 mmHg", "Lactate > 2 mmol/L"
    """
    variable: str  # 변수명 (예: "map_mmhg", "lactate")
    operator: ConditionOperator
    value: Any  # 비교값
    description: str = ""  # 사람이 읽을 수 있는 설명
    source_guideline: str = ""  # 출처 가이드라인 (예: "SSC 2021 Hour-1 Bundle")

    def evaluate(self, context: Dict[str, Any]) -> bool:
        """조건 평가"""
        actual_value = context.get(self.variable)

        if actual_value is None:
            return False

        try:
            if self.operator == ConditionOperator.EQUALS:
                return actual_value == self.value
            elif self.operator == ConditionOperator.NOT_EQUALS:
                return actual_value != self.value
            elif self.operator == ConditionOperator.GREATER_THAN:
                return float(actual_value) > float(self.value)
            elif self.operator == ConditionOperator.GREATER_EQUAL:
                return float(actual_value) >= float(self.value)
            elif self.operator == ConditionOperator.LESS_THAN:
                return float(actual_value) < float(self.value)
            elif self.operator == ConditionOperator.LESS_EQUAL:
                return float(actual_value) <= float(self.value)
            elif self.operator == ConditionOperator.IN:
                return actual_value in self.value
            elif self.operator == ConditionOperator.NOT_IN:
                return actual_value not in self.value
            elif self.operator == ConditionOperator.CONTAINS:
                return self.value in str(actual_value)
            elif self.operator == ConditionOperator.IS_TRUE:
                return bool(actual_value)
            elif self.operator == ConditionOperator.IS_FALSE:
                return not bool(actual_value)
        except (ValueError, TypeError):
            return False

        return False


@dataclass
class ActionRecommendation:
    """
    행동 권고사항

    CPG 텍스트에서 추출한 권고 행동입니다.
    """
    action_id: str  # 독립적인 ID (CPG-Engine 노드ID와 무관)
    action_type: str  # "order_lab", "give_medication", "procedure", etc.
    parameters: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # 우선순위 (높을수록 먼저)
    deadline_minutes: Optional[int] = None  # 시간 제한 (분)
    is_mandatory: bool = False  # 필수 여부
    is_forbidden: bool = False  # 금기 여부
    required_prior_actions: List[str] = field(default_factory=list)  # 선행 필수 행동
    contraindication_conditions: List[str] = field(default_factory=list)  # 금기 조건
    source_guideline: str = ""  # 출처 가이드라인
    source_recommendation: str = ""  # 출처 권고사항 ID
    evidence_level: str = ""  # 근거 수준 (예: "1A", "2B")


@dataclass
class DecisionTableEntry:
    """
    의사결정 테이블 엔트리

    조건 집합과 해당 행동 권고의 매핑입니다.
    """
    entry_id: str
    description: str
    conditions: List[ClinicalCondition]  # AND 조건
    actions: List[ActionRecommendation]
    priority: int = 0  # 엔트리 우선순위
    source_guideline: str = ""

    def matches(self, context: Dict[str, Any]) -> bool:
        """모든 조건이 충족되는지 확인"""
        return all(cond.evaluate(context) for cond in self.conditions)


@dataclass
class ClinicalRuleSet:
    """
    임상 규칙 집합

    특정 임상 시나리오에 대한 규칙들의 집합입니다.
    """
    ruleset_id: str
    name: str
    description: str
    source_guidelines: List[str]

    # 항상 필수인 행동들 (조건 무관)
    always_mandatory: List[ActionRecommendation] = field(default_factory=list)

    # 항상 금기인 행동들 (조건 무관)
    always_forbidden: List[ActionRecommendation] = field(default_factory=list)

    # 조건부 규칙들
    decision_entries: List[DecisionTableEntry] = field(default_factory=list)

    # 알러지/동반질환 기반 금기 매핑
    allergy_contraindications: Dict[str, List[str]] = field(default_factory=dict)
    comorbidity_contraindications: Dict[str, List[str]] = field(default_factory=dict)


class RuleBasedDecisionTable(ABC):
    """
    규칙 기반 의사결정 테이블 (추상 클래스)

    이 클래스는 채점용 CPG-Engine과 완전히 독립적입니다.
    - CPG-Engine의 그래프 구조를 사용하지 않음
    - CPG-Engine의 노드 ID를 참조하지 않음
    - CPG 텍스트 가이드라인에서 사람이 작성한 규칙만 사용

    Oracle 에이전트는 이 클래스를 사용하여 "이론적 상한(Upper Bound)"을 제공합니다.
    이는 비교 기준으로만 사용되며, 실제 채점에는 영향을 주지 않습니다.
    """

    def __init__(self):
        self.rulesets: Dict[str, ClinicalRuleSet] = {}
        self._completed_actions: Set[str] = set()
        self._action_timestamps: Dict[str, int] = {}
        self._load_rulesets()

    @abstractmethod
    def _load_rulesets(self):
        """규칙 집합 로드 (서브클래스에서 구현)"""
        pass

    def reset(self):
        """상태 초기화"""
        self._completed_actions = set()
        self._action_timestamps = {}

    def record_action(self, action_id: str, timestamp_minutes: int):
        """수행한 행동 기록"""
        self._completed_actions.add(action_id)
        self._action_timestamps[action_id] = timestamp_minutes

    def get_recommended_actions(
        self,
        context: Dict[str, Any],
        current_time_minutes: int = 0
    ) -> List[ActionRecommendation]:
        """
        현재 상태에서 권고되는 행동 목록 반환

        Args:
            context: 환자 상태 및 임상 컨텍스트
            current_time_minutes: 현재 시간 (분)

        Returns:
            우선순위 순으로 정렬된 권고 행동 목록
        """
        recommendations: List[ActionRecommendation] = []

        # 현재 시나리오 유형 결정
        scenario_type = self._determine_scenario_type(context)

        if scenario_type not in self.rulesets:
            logger.warning(f"Unknown scenario type: {scenario_type}")
            return recommendations

        ruleset = self.rulesets[scenario_type]

        # H5 Fix: 금기 행동 집합을 미리 계산하여 O(1) 조회로 변경
        forbidden_set = set(self.get_forbidden_actions(context))

        # 1. 항상 필수인 행동 추가 (아직 수행하지 않은 것만)
        for action in ruleset.always_mandatory:
            if action.action_id not in self._completed_actions:
                if not self._is_action_forbidden(action, context, forbidden_set):
                    recommendations.append(action)

        # 2. 조건부 규칙 평가
        for entry in ruleset.decision_entries:
            if entry.matches(context):
                for action in entry.actions:
                    if action.action_id not in self._completed_actions:
                        if not self._is_action_forbidden(action, context, forbidden_set):
                            # 선행 조건 확인
                            if self._prerequisites_met(action):
                                recommendations.append(action)

        # 3. 우선순위 및 데드라인 기준 정렬
        recommendations = self._sort_by_priority_and_deadline(
            recommendations, current_time_minutes
        )

        return recommendations

    def get_forbidden_actions(self, context: Dict[str, Any]) -> List[str]:
        """현재 상태에서 금기인 행동 목록 반환"""
        forbidden = []

        scenario_type = self._determine_scenario_type(context)

        if scenario_type in self.rulesets:
            ruleset = self.rulesets[scenario_type]

            # 항상 금기인 행동
            for action in ruleset.always_forbidden:
                forbidden.append(action.action_id)

            # 알러지 기반 금기
            allergies = context.get("allergies", [])
            for allergy in allergies:
                allergy_lower = allergy.lower()
                if allergy_lower in ruleset.allergy_contraindications:
                    forbidden.extend(ruleset.allergy_contraindications[allergy_lower])

            # 동반질환 기반 금기
            comorbidities = context.get("comorbidities", [])
            for comorbidity in comorbidities:
                comorbidity_lower = comorbidity.lower()
                if comorbidity_lower in ruleset.comorbidity_contraindications:
                    forbidden.extend(ruleset.comorbidity_contraindications[comorbidity_lower])

        return list(set(forbidden))

    def _is_action_forbidden(
        self,
        action: ActionRecommendation,
        context: Dict[str, Any],
        forbidden_set: Set[str]
    ) -> bool:
        """행동이 금기인지 확인 (사전 계산된 forbidden_set 사용)"""
        if action.action_id in forbidden_set:
            return True

        # 행동 자체의 금기 조건 확인
        for condition_name in action.contraindication_conditions:
            if context.get(condition_name):
                return True

        return False

    def _is_contraindicated(
        self,
        action: ActionRecommendation,
        context: Dict[str, Any]
    ) -> bool:
        """행동이 금기인지 확인 (호환성 유지)"""
        forbidden_set = set(self.get_forbidden_actions(context))
        return self._is_action_forbidden(action, context, forbidden_set)

    def _prerequisites_met(self, action: ActionRecommendation) -> bool:
        """선행 조건이 충족되었는지 확인"""
        for prereq in action.required_prior_actions:
            if prereq not in self._completed_actions:
                return False
        return True

    def _sort_by_priority_and_deadline(
        self,
        actions: List[ActionRecommendation],
        current_time: int
    ) -> List[ActionRecommendation]:
        """우선순위와 데드라인 기준 정렬"""
        def sort_key(action: ActionRecommendation):
            # 데드라인이 임박한 것 우선 (작은 값 = 높은 우선순위)
            time_urgency = float('inf')  # 데드라인 없으면 가장 낮은 우선순위
            if action.deadline_minutes is not None:
                remaining = action.deadline_minutes - current_time
                if remaining <= 0:
                    time_urgency = -1000  # 이미 지남 - 최우선
                else:
                    time_urgency = remaining  # FIX: 남은 시간이 적을수록 먼저

            # 필수 행동 우선
            mandatory_bonus = -500 if action.is_mandatory else 0

            return (mandatory_bonus, time_urgency, -action.priority)

        return sorted(actions, key=sort_key)

    @abstractmethod
    def _determine_scenario_type(self, context: Dict[str, Any]) -> str:
        """시나리오 유형 결정 (서브클래스에서 구현)"""
        pass

    def get_status(self) -> Dict[str, Any]:
        """현재 상태 반환"""
        return {
            "completed_actions": list(self._completed_actions),
            "action_timestamps": dict(self._action_timestamps),
            "available_rulesets": list(self.rulesets.keys()),
        }

    def get_sequence_constraints(self) -> List[Dict[str, str]]:
        """
        시퀀스 제약 조건 반환

        Returns:
            [{"before": action_id, "after": action_id}, ...]
            형태의 선행 관계 제약 목록
        """
        constraints = []

        # 모든 ruleset에서 required_prior_actions 기반으로 시퀀스 제약 추출
        for ruleset_name, ruleset in self.rulesets.items():
            # always_mandatory에서 추출
            for action in ruleset.always_mandatory:
                for prereq in action.required_prior_actions:
                    constraints.append({
                        "before": prereq,
                        "after": action.action_id
                    })

            # decision_entries에서 추출
            for entry in ruleset.decision_entries:
                for action in entry.actions:
                    for prereq in action.required_prior_actions:
                        constraints.append({
                            "before": prereq,
                            "after": action.action_id
                        })

        # 중복 제거
        seen = set()
        unique_constraints = []
        for c in constraints:
            key = (c["before"], c["after"])
            if key not in seen:
                seen.add(key)
                unique_constraints.append(c)

        return unique_constraints
