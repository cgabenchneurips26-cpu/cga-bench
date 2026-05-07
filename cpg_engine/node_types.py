"""
PROforma 스타일 노드 타입 구현
각 노드 타입은 특정 임상 의사결정 패턴을 표현
"""
from abc import ABC, abstractmethod
from typing import Set, Dict, Optional, Any
import re
import logging

from cga_bench.cpg_model.schemas.base import (
    PatientState, CPGNode, GuidelineEngineOutput,
    NodeType, RecommendationClass
)

logger = logging.getLogger(__name__)


class SafeExpressionEvaluator:
    """
    안전한 조건식 평가기

    지원하는 표현식:
    - state.working_diagnosis == 'septic_shock'
    - state.vitals.map_mmhg < 65
    - 'vasopressor' in str(state.medications_given)
    - True (항상 참)
    """

    # 허용되는 비교 연산자
    ALLOWED_OPERATORS = {'==', '!=', '<', '>', '<=', '>=', 'in', 'not in'}

    @classmethod
    def evaluate(cls, expression: str, state: PatientState) -> bool:
        """
        조건식을 안전하게 평가

        Args:
            expression: 조건식 문자열
            state: 환자 상태

        Returns:
            조건 평가 결과
        """
        if not expression or expression.strip() == '':
            return True

        expression = expression.strip()

        # 단순 True/False 리터럴
        if expression == 'True':
            return True
        if expression == 'False':
            return False
        if expression == 'null' or expression == 'None':
            return True  # 조건 없음 = 항상 참

        try:
            # 'in' 연산자 처리
            if ' in ' in expression:
                return cls._evaluate_in_expression(expression, state)

            # 비교 연산자 처리
            for op in ['==', '!=', '<=', '>=', '<', '>']:
                if op in expression:
                    return cls._evaluate_comparison(expression, op, state)

            # 알 수 없는 표현식
            logger.warning(f"Unknown expression format: {expression}")
            return False

        except Exception as e:
            logger.warning(f"Error evaluating expression '{expression}': {e}")
            return False

    @classmethod
    def _evaluate_in_expression(cls, expression: str, state: PatientState) -> bool:
        """'in' 연산자 표현식 평가"""
        # 패턴: 'value' in str(state.field) 또는 value in state.field
        match = re.match(r"['\"]?(.+?)['\"]?\s+(not\s+)?in\s+(.+)", expression)
        if not match:
            return False

        search_value = match.group(1).strip("'\"")
        is_negated = match.group(2) is not None
        target_expr = match.group(3).strip()

        # str() 래핑 처리
        if target_expr.startswith('str(') and target_expr.endswith(')'):
            target_expr = target_expr[4:-1]
            target_value = str(cls._get_nested_attr(state, target_expr))
        else:
            target_value = cls._get_nested_attr(state, target_expr)

        if isinstance(target_value, (list, tuple, set)):
            result = search_value in target_value
        else:
            result = search_value in str(target_value)

        return not result if is_negated else result

    @classmethod
    def _evaluate_comparison(cls, expression: str, operator: str, state: PatientState) -> bool:
        """비교 연산자 표현식 평가"""
        parts = expression.split(operator)
        if len(parts) != 2:
            return False

        left_expr = parts[0].strip()
        right_expr = parts[1].strip()

        left_value = cls._get_value(left_expr, state)
        right_value = cls._get_value(right_expr, state)

        if left_value is None or right_value is None:
            return False

        if operator == '==':
            return left_value == right_value
        elif operator == '!=':
            return left_value != right_value
        elif operator == '<':
            return float(left_value) < float(right_value)
        elif operator == '>':
            return float(left_value) > float(right_value)
        elif operator == '<=':
            return float(left_value) <= float(right_value)
        elif operator == '>=':
            return float(left_value) >= float(right_value)

        return False

    @classmethod
    def _get_value(cls, expr: str, state: PatientState) -> Any:
        """표현식에서 값 추출"""
        expr = expr.strip()

        # 문자열 리터럴
        if (expr.startswith("'") and expr.endswith("'")) or \
           (expr.startswith('"') and expr.endswith('"')):
            return expr[1:-1]

        # 숫자 리터럴
        try:
            if '.' in expr:
                return float(expr)
            return int(expr)
        except ValueError:
            pass

        # state 속성 참조
        if expr.startswith('state.') or expr.startswith('s.'):
            return cls._get_nested_attr(state, expr)

        return None

    @classmethod
    def _get_nested_attr(cls, obj: Any, path: str) -> Any:
        """중첩 속성 접근 (예: state.vitals.map_mmhg)"""
        # 'state.' 또는 's.' 접두사 제거
        if path.startswith('state.'):
            path = path[6:]
        elif path.startswith('s.'):
            path = path[2:]

        parts = path.split('.')
        current = obj

        for part in parts:
            if current is None:
                return None

            # dict-like 접근 시도
            if isinstance(current, dict):
                current = current.get(part)
            # Pydantic 모델 또는 일반 객체
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return None

        return current

class BaseNode(ABC):
    """노드 기본 클래스"""

    def __init__(self, node_def: CPGNode):
        self.node_def = node_def
        self.node_id = node_def.node_id

    @abstractmethod
    def evaluate(self, state: PatientState) -> GuidelineEngineOutput:
        """현재 상태에서 이 노드의 제약 집합 반환"""
        pass

    def check_precondition(self, state: PatientState) -> bool:
        """노드 적용 조건 확인"""
        if not self.node_def.precondition:
            return True
        return SafeExpressionEvaluator.evaluate(self.node_def.precondition, state)

class EnquiryNode(BaseNode):
    """
    정보 수집 노드
    예: "Lactate 측정", "12-lead ECG 획득"
    """
    def evaluate(self, state: PatientState) -> GuidelineEngineOutput:
        return GuidelineEngineOutput(
            current_node_id=self.node_id,
            current_node_name=self.node_def.name,
            current_node_description=self.node_def.description,
            allowed_actions=set(self.node_def.allowed_actions),
            mandatory_actions=set(self.node_def.mandatory_actions),
            forbidden_actions=set(self.node_def.forbidden_actions),
            deadlines=self.node_def.deadlines.copy(),
            required_prior_actions=self.node_def.required_prior_actions.copy(),
            recommendation_strength={
                action: (self.node_def.recommendation_class, self.node_def.evidence_level)
                for action in self.node_def.mandatory_actions
            }
        )

class DecisionNode(BaseNode):
    """
    의사결정 분기 노드
    예: "Sepsis vs Septic Shock 판단", "STEMI vs NSTEMI 분류"
    """
    def evaluate(self, state: PatientState) -> GuidelineEngineOutput:
        # 분기 노드는 다음 경로 선택이 핵심
        output = GuidelineEngineOutput(
            current_node_id=self.node_id,
            current_node_name=self.node_def.name,
            current_node_description=self.node_def.description,
            allowed_actions=set(self.node_def.allowed_actions),
            mandatory_actions=set(self.node_def.mandatory_actions),
            forbidden_actions=set(self.node_def.forbidden_actions),
            deadlines=self.node_def.deadlines.copy(),
            required_prior_actions=self.node_def.required_prior_actions.copy()
        )
        return output

    def get_next_node(self, state: PatientState) -> Optional[str]:
        """조건에 따라 다음 노드 결정"""
        for condition, next_node_id in self.node_def.conditional_next.items():
            if SafeExpressionEvaluator.evaluate(condition, state):
                return next_node_id
        # 기본 다음 노드
        return self.node_def.next_nodes[0] if self.node_def.next_nodes else None

class ActionNode(BaseNode):
    """
    행동 실행 노드
    예: "항생제 투여", "수액 30mL/kg 투여"
    """
    def evaluate(self, state: PatientState) -> GuidelineEngineOutput:
        return GuidelineEngineOutput(
            current_node_id=self.node_id,
            current_node_name=self.node_def.name,
            current_node_description=self.node_def.description,
            allowed_actions=set(self.node_def.allowed_actions),
            mandatory_actions=set(self.node_def.mandatory_actions),
            forbidden_actions=set(self.node_def.forbidden_actions),
            deadlines=self.node_def.deadlines.copy(),
            required_prior_actions=self.node_def.required_prior_actions.copy(),
            recommendation_strength={
                action: (self.node_def.recommendation_class, self.node_def.evidence_level)
                for action in self.node_def.mandatory_actions + self.node_def.allowed_actions
            }
        )

class PlanNode(BaseNode):
    """
    복합 계획 노드 (Bundle)
    예: "Sepsis Hour-1 Bundle", "ACS Initial Management"
    여러 하위 행동을 시간 제약과 함께 묶음
    """
    def __init__(self, node_def: CPGNode, sub_nodes: Optional[Dict[str, BaseNode]] = None):
        super().__init__(node_def)
        self.sub_nodes = sub_nodes or {}

    def evaluate(self, state: PatientState) -> GuidelineEngineOutput:
        # Bundle의 모든 필수 행동과 마감을 집계
        all_mandatory = set(self.node_def.mandatory_actions)
        all_deadlines = self.node_def.deadlines.copy()
        all_forbidden = set(self.node_def.forbidden_actions)
        all_allowed = set(self.node_def.allowed_actions)
        all_required_prior = self.node_def.required_prior_actions.copy()

        # 하위 노드들의 제약도 포함
        for sub_node in self.sub_nodes.values():
            if sub_node.check_precondition(state):
                sub_output = sub_node.evaluate(state)
                all_mandatory.update(sub_output.mandatory_actions)
                all_deadlines.update(sub_output.deadlines)
                all_forbidden.update(sub_output.forbidden_actions)
                all_allowed.update(sub_output.allowed_actions)
                # 순서 의존성 병합 (기존 리스트에 추가)
                for action, priors in sub_output.required_prior_actions.items():
                    if action in all_required_prior:
                        all_required_prior[action] = list(set(all_required_prior[action] + priors))
                    else:
                        all_required_prior[action] = priors

        return GuidelineEngineOutput(
            current_node_id=self.node_id,
            current_node_name=self.node_def.name,
            current_node_description=self.node_def.description,
            allowed_actions=all_allowed,
            mandatory_actions=all_mandatory,
            forbidden_actions=all_forbidden,
            deadlines=all_deadlines,
            required_prior_actions=all_required_prior
        )

# 노드 타입 팩토리
NODE_TYPE_MAP = {
    NodeType.ENQUIRY: EnquiryNode,
    NodeType.DECISION: DecisionNode,
    NodeType.ACTION: ActionNode,
    NodeType.PLAN: PlanNode,
}

def create_node(node_def: CPGNode) -> BaseNode:
    """노드 정의로부터 적절한 노드 인스턴스 생성"""
    node_class = NODE_TYPE_MAP.get(node_def.node_type)
    if node_class is None:
        raise ValueError(
            f"Unknown node type '{node_def.node_type}' for node '{node_def.node_id}'. "
            f"Valid types are: {list(NODE_TYPE_MAP.keys())}"
        )
    return node_class(node_def)
