"""
Action Module
에이전트 행동 정의 및 검증
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from enum import Enum


class ActionType2(str, Enum):
    """확장된 행동 타입 - MedAgentBench/AgentClinic 호환"""
    # 검사
    ORDER_LAB = "order_lab"
    ORDER_IMAGING = "order_imaging"

    # 치료
    PRESCRIBE = "prescribe"
    GIVE_MEDICATION = "give_medication"
    PROCEDURE = "procedure"

    # 의뢰/협진
    CONSULT = "consult"

    # 배치
    ADMIT = "admit"
    DISCHARGE = "discharge"
    TRANSFER = "transfer"

    # 관찰
    OBSERVE = "observe"
    REASSESS = "reassess"
    PHYSICAL_EXAM = "physical_exam"

    # 문서화
    DOCUMENT = "document"
    WRITE_NOTE = "write_note"

    # 의사소통
    ASK_QUESTION = "ask_question"
    EXPLAIN = "explain"

    # 상황 확대
    ESCALATE = "escalate"

    # 대기
    WAIT = "wait"

    # 기타 (Unknown/Fallback)
    OTHER = "other"


class ActionStatus(str, Enum):
    """행동 상태"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Action2:
    """
    에이전트 행동 스키마
    구조화된 JSON으로만 행동 가능
    """
    action_type: ActionType2
    action_id: str
    target: str  # 검사명, 약물명, 협진과 등
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp_minutes: Optional[float] = None
    justification: Optional[str] = None  # Justified Deviation용

    # 추적 정보
    status: ActionStatus = ActionStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_canonical_id(self) -> str:
        """정규화된 행동 ID 생성"""
        base_id = f"{self.action_type.value}_{self.target}"
        return base_id.lower().replace(" ", "_").replace("-", "_")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Action2:
        """딕셔너리에서 Action2 생성"""
        action_type_raw = data.get("action_type") or data.get("type")
        if isinstance(action_type_raw, str):
            action_type = ActionType2(action_type_raw)
        elif isinstance(action_type_raw, ActionType2):
            action_type = action_type_raw
        else:
            action_type = ActionType2.OTHER  # Default for unknown types

        return cls(
            action_type=action_type,
            action_id=data.get("action_id", ""),
            target=data.get("target", ""),
            parameters=data.get("parameters", data.get("args", {})),
            timestamp_minutes=data.get("timestamp_minutes"),
            justification=data.get("justification"),
        )


@dataclass
class ActionResult:
    """행동 수행 결과"""
    action_id: str
    success: bool
    outcome: Dict[str, Any] = field(default_factory=dict)
    state_changes: Dict[str, Any] = field(default_factory=dict)
    time_elapsed_minutes: float = 0.0
    error_message: Optional[str] = None


class ActionValidator:
    """
    행동 유효성 검증
    CPG 제약과의 일치 여부 확인
    """

    def __init__(
        self,
        allowed_actions: Optional[Set[str]] = None,
        mandatory_actions: Optional[Set[str]] = None,
        forbidden_actions: Optional[Set[str]] = None
    ):
        self.allowed = allowed_actions or set()
        self.mandatory = mandatory_actions or set()
        self.forbidden = forbidden_actions or set()

    def is_allowed(self, action: Action2) -> bool:
        """허용 행동인지 확인"""
        canonical_id = action.to_canonical_id()

        # 금기 행동 체크
        if canonical_id in self.forbidden:
            return False

        # 허용 목록이 비어있으면 기본 허용
        if not self.allowed:
            return True

        return canonical_id in self.allowed

    def is_forbidden(self, action: Action2) -> bool:
        """금기 행동인지 확인"""
        canonical_id = action.to_canonical_id()
        return canonical_id in self.forbidden

    def is_mandatory(self, action: Action2) -> bool:
        """필수 행동인지 확인"""
        canonical_id = action.to_canonical_id()
        return canonical_id in self.mandatory

    def get_missing_mandatory(self, performed_actions: List[Action2]) -> Set[str]:
        """누락된 필수 행동 목록"""
        performed_ids = {a.to_canonical_id() for a in performed_actions}
        return self.mandatory - performed_ids

    def validate(self, action: Action2) -> tuple:
        """
        행동 유효성 검증

        Returns:
            (is_valid: bool, violation_type: Optional[str], message: str)
        """
        canonical_id = action.to_canonical_id()

        # 금기 체크
        if canonical_id in self.forbidden:
            return (False, "commission", f"Forbidden action: {canonical_id}")

        # 허용 체크
        if self.allowed and canonical_id not in self.allowed:
            return (False, "deviation", f"Not in allowed actions: {canonical_id}")

        return (True, None, "Valid action")


# Action type normalization mappings
ACTION_TYPE_MAPPING: Dict[str, ActionType2] = {
    # Lab orders
    "order_test": ActionType2.ORDER_LAB,
    "order_lab": ActionType2.ORDER_LAB,
    "lab_order": ActionType2.ORDER_LAB,

    # Imaging
    "order_imaging": ActionType2.ORDER_IMAGING,
    "imaging_order": ActionType2.ORDER_IMAGING,
    "order_xray": ActionType2.ORDER_IMAGING,
    "order_ct": ActionType2.ORDER_IMAGING,
    "order_mri": ActionType2.ORDER_IMAGING,
    "obtain_12_lead_ecg": ActionType2.ORDER_IMAGING,

    # Medications
    "prescribe": ActionType2.PRESCRIBE,
    "give_medication": ActionType2.GIVE_MEDICATION,
    "give_med": ActionType2.GIVE_MEDICATION,
    "administer": ActionType2.GIVE_MEDICATION,
    "give_crystalloid_30ml_kg": ActionType2.GIVE_MEDICATION,
    "give_broad_spectrum_antibiotics": ActionType2.GIVE_MEDICATION,
    "give_aspirin": ActionType2.GIVE_MEDICATION,
    "give_nitroglycerin": ActionType2.GIVE_MEDICATION,
    "start_vasopressor": ActionType2.GIVE_MEDICATION,

    # Procedures
    "procedure": ActionType2.PROCEDURE,
    "perform_procedure": ActionType2.PROCEDURE,

    # Consults
    "consult": ActionType2.CONSULT,
    "consultation": ActionType2.CONSULT,

    # Disposition
    "admit": ActionType2.ADMIT,
    "admission": ActionType2.ADMIT,
    "discharge": ActionType2.DISCHARGE,
    "transfer": ActionType2.TRANSFER,

    # Documentation
    "document": ActionType2.DOCUMENT,
    "write_note": ActionType2.WRITE_NOTE,

    # Observation
    "observe": ActionType2.OBSERVE,
    "reassess": ActionType2.REASSESS,
    "physical_exam": ActionType2.PHYSICAL_EXAM,
    "exam": ActionType2.PHYSICAL_EXAM,

    # Communication
    "ask_question": ActionType2.ASK_QUESTION,
    "explain": ActionType2.EXPLAIN,

    # Escalation
    "escalate": ActionType2.ESCALATE,
    "activate_cath_lab": ActionType2.ESCALATE,

    # Wait
    "wait": ActionType2.WAIT,
}


def normalize_action_type(raw_type: str) -> ActionType2:
    """행동 타입 정규화"""
    raw_lower = raw_type.lower().strip()

    # Direct mapping
    if raw_lower in ACTION_TYPE_MAPPING:
        return ACTION_TYPE_MAPPING[raw_lower]

    # Try enum value
    try:
        return ActionType2(raw_lower)
    except ValueError:
        pass

    # Default fallback
    return ActionType2.PROCEDURE
