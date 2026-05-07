"""CGA-Bench 핵심 데이터 스키마
모든 스키마는 Pydantic v2 기반으로 정의
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from .contracts import ConstraintOutput
else:
    ConstraintOutput = Any

# ============================================
# 1. Action Schema: "말"이 아닌 "행동"을 강제
# ============================================


class ActionType(str, Enum):
    """에이전트가 수행할 수 있는 행동 타입"""

    ORDER_LAB = "order_lab"
    ORDER_IMAGING = "order_imaging"
    GIVE_MEDICATION = "give_medication"
    PROCEDURE = "procedure"
    CONSULT = "consult"
    DISPOSITION = "disposition"
    ASK_QUESTION = "ask_question"
    PHYSICAL_EXAM = "physical_exam"
    WRITE_NOTE = "write_note"
    REASSESS = "reassess"
    ESCALATE = "escalate"


class Action(BaseModel):
    """에이전트 행동 스키마 - 구조화된 JSON으로만 행동 가능"""

    model_config = ConfigDict(use_enum_values=True)

    type: ActionType
    action_id: str = Field(..., description="고유 행동 ID")
    args: dict[str, Any] = Field(default_factory=dict, description="행동 인자")
    timestamp_minutes: float = Field(..., description="시뮬레이션 시간 (도착 후 분)")
    justification: str | None = Field(None, description="행동 근거 (Justified Deviation용)")
    semantic_tag: str | None = Field(
        None,
        description=(
            "Agent-side normaliser tag from 3-tier _normalize_action_id: "
            "None = Tier 1/2 (exact or alias resolved to scenario's available set), "
            "'GENERAL_WORKUP' = Tier 3 (universal_clinical_safety fallback, no penalty), "
            "'DEVIATION' = Tier 4 (out-of-guideline; scorer flags as DEVIATION violation)."
        ),
    )


# ============================================
# 2. State Schema: 채점 가능한 환자 상태
# ============================================


class VitalSigns(BaseModel):
    """활력 징후"""

    heart_rate: float | None = None
    blood_pressure_systolic: float | None = None
    blood_pressure_diastolic: float | None = None
    respiratory_rate: float | None = None
    temperature: float | None = None
    oxygen_saturation: float | None = None
    map_mmhg: float | None = Field(None, description="Mean Arterial Pressure")


class LabResult(BaseModel):
    """검사 결과"""

    test_code: str
    test_name: str
    value: float | str  # 수치 또는 질적 결과 (예: blood_culture = "positive")
    unit: str
    timestamp_minutes: float
    is_abnormal: bool = False
    critical: bool = False


class PatientState(BaseModel):
    """환자 상태 스키마 - 시뮬레이션의 핵심 상태"""

    state_id: str
    time_since_arrival_minutes: float = 0.0

    # 인구통계
    age: int
    sex: str
    weight_kg: float | None = None

    # 활력징후
    vitals: VitalSigns

    # 검사 결과 (수행된 것만)
    lab_results: list[LabResult] = Field(default_factory=list)
    imaging_results: list[dict[str, Any]] = Field(default_factory=list)

    # 투여된 약물/처치
    medications_given: list[dict[str, Any]] = Field(default_factory=list)
    procedures_done: list[str] = Field(default_factory=list)

    # 대기 중인 오더
    pending_orders: list[str] = Field(default_factory=list)

    # 환자 특이사항 (Justified Deviation 판단용)
    contraindications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    comorbidities: list[str] = Field(default_factory=list)

    # 현재 상태
    chief_complaint: str
    working_diagnosis: str | None = None
    disposition_status: str | None = None  # None, "admitted", "discharged", "transferred"

    # 숨겨진 정보 (에이전트는 직접 접근 불가, 검사로만 확인)
    _ground_truth: dict[str, Any] = {}


# ============================================
# 3. CPG Graph/DSL Schema: 가이드라인 실행 엔진
# ============================================


class NodeType(str, Enum):
    """PROforma 스타일 노드 타입"""

    ENQUIRY = "enquiry"  # 정보 수집 노드
    DECISION = "decision"  # 의사결정 분기 노드
    ACTION = "action"  # 행동 실행 노드
    PLAN = "plan"  # 복합 계획 노드 (서브그래프)


class RecommendationClass(str, Enum):
    """권고 등급 (ACC/AHA 스타일)"""

    CLASS_I = "I"  # 강력 권고 (benefit >>> risk)
    CLASS_IIA = "IIa"  # 중등도 권고 (benefit >> risk)
    CLASS_IIB = "IIb"  # 약한 권고 (benefit >= risk)
    CLASS_III = "III"  # 권고 안함/해로움


class EvidenceLevel(str, Enum):
    """근거 수준"""

    LEVEL_A = "A"  # 다수의 RCT 또는 메타분석
    LEVEL_B = "B"  # 단일 RCT 또는 비무작위 연구
    LEVEL_C = "C"  # 전문가 의견


class ConstraintType(str, Enum):
    """Conditional rule이 도출하는 constraint 타입"""

    FORBIDDEN = "FORBIDDEN"
    REQUIRED = "REQUIRED"
    BEFORE = "BEFORE"
    WITHIN = "WITHIN"


class RuleSeverity(str, Enum):
    """Conditional rule 위반 시 심각도"""

    CRITICAL = "CRITICAL"  # 위반 시 환자 사망/중대 손상 가능
    HIGH = "HIGH"  # 위반 시 심각한 합병증
    MODERATE = "MODERATE"  # 위반 시 차선 치료
    LOW = "LOW"  # 위반 시 경미한 영향


class ConstraintEffect(BaseModel):
    """Conditional rule이 trigger될 때의 효과"""

    type: ConstraintType
    actions: list[str] = Field(..., description="관련 action(s)")
    # BEFORE: actions[0] must come before actions[1]
    # WITHIN: actions[0] must occur within time_limit_minutes
    time_limit_minutes: int | None = None


class ConditionalRule(BaseModel):
    """CPG graph node에 붙는 조건부 규칙 - patient context에 따라 constraint를 도출"""

    rule_id: str = Field(..., description="Unique ID: {GRAPH}-{DOMAIN}-{SHORT_NAME}")
    condition: str = Field(..., description="Python-evaluable condition string")
    effect: ConstraintEffect
    evidence: str = Field(..., description="Guideline 원문 참조 (e.g. ADA 2024, Section 16.2)")
    severity: RuleSeverity
    description: str = Field(default="", description="사람이 읽을 수 있는 설명")

    # condition에 사용되는 변수 목록 (PatientGenerator가 참조)
    condition_variables: list[str] = Field(default_factory=list)

    # condition이 True일 때 trigger되는 값 범위 (PatientGenerator용)
    trigger_range: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # condition이 False일 때 정상 값 범위
    normal_range: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CPGNode(BaseModel):
    """가이드라인 그래프 노드"""

    node_id: str
    node_type: NodeType
    name: str
    description: str

    # 적용 조건 (Python 표현식 문자열, 상태에 대해 eval)
    precondition: str | None = Field(None, description="이 노드 적용 조건")

    # 행동 집합 정의
    mandatory_actions: list[str] = Field(default_factory=list, description="필수 행동")
    forbidden_actions: list[str] = Field(default_factory=list, description="금기 행동")
    allowed_actions: list[str] = Field(default_factory=list, description="허용 행동 (대안 포함)")

    # 시간 제약
    deadlines: dict[str, float] = Field(default_factory=dict, description="필수 행동별 마감 시간 (분 단위)")

    # 순서 의존성 (SEQUENCE 위반 검출용)
    required_prior_actions: dict[str, list[str]] = Field(
        default_factory=dict, description="행동별 선행 필수 행동 {action: [prior_actions]}"
    )

    # 권고 강도/근거
    recommendation_class: RecommendationClass | None = None
    # evidence_level을 String으로 변경: 다양한 가이드라인 시스템 수용
    # GRADE: "Strong", "Weak" / ACC/AHA: "A", "B-NR", "C-LD" / NCCN: "Category 1", etc.
    evidence_level: str | None = None

    # 출처 추적 (GEM 스타일)
    source_guideline: str = ""
    source_section: str = ""
    source_page: str | None = None
    source_figure: str | None = None
    source_quote: str | None = None
    source_loe: str | None = None  # Level of Evidence (A, B, C)

    # 순서 규칙 (unconditional BEFORE constraints)
    sequence_rules: list[list[str]] = Field(
        default_factory=list, description="순서 규칙: [[before_action, after_action], ...]"
    )

    # 조건부 규칙 (patient context 기반 constraint 도출)
    conditional_rules: list[ConditionalRule] = Field(
        default_factory=list, description="Patient context에 따라 trigger되는 조건부 규칙"
    )

    # 다음 노드 연결
    next_nodes: list[str] = Field(default_factory=list)
    conditional_next: dict[str, str] = Field(default_factory=dict, description="조건부 다음 노드 {조건식: 노드ID}")

    # 자동 전이 조건 (SGSC v7 — 엔진은 무시, graph compiler가 인코딩)
    auto_transition_conditions: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Patient state 조건 충족 시 자동 전이. 각 항목: {condition: str, target_node: str, description: str}"
        ),
    )


class CPGGraph(BaseModel):
    """가이드라인 전체 그래프"""

    graph_id: str
    guideline_name: str
    version: str
    nodes: dict[str, CPGNode]
    entry_node: str
    metadata: dict[str, Any] = Field(default_factory=dict)


# ============================================
# 4. Guideline Engine Output Schema
# ============================================


class GuidelineEngineOutput(BaseModel):
    """G(s_t) ->
    가이드라인 엔진이 현재 상태에서 반환하는 제약 집합
    """

    current_node_id: str

    # A_G(s_t): 허용 행동 집합
    allowed_actions: set[str] = Field(default_factory=set)

    # M_G(s_t): 필수 행동 집합
    mandatory_actions: set[str] = Field(default_factory=set)

    # F_G(s_t): 금기 행동 집합
    forbidden_actions: set[str] = Field(default_factory=set)

    # D_G: 필수 행동별 마감 시간 (분)
    deadlines: dict[str, float] = Field(default_factory=dict)

    # S_G: 순서 의존성 (선행 필수 행동)
    required_prior_actions: dict[str, list[str]] = Field(
        default_factory=dict, description="{action: [prior_actions]} - 행동 수행 전 완료되어야 할 선행 행동"
    )

    # R_G: 권고 강도 매핑
    recommendation_strength: dict[str, tuple] = Field(default_factory=dict, description="{action: (class, level)}")

    # 현재 노드 메타데이터
    current_node_name: str = ""
    current_node_description: str = ""

    def to_constraint_output(self) -> ConstraintOutput:
        from .contracts import ConstraintOutput

        return ConstraintOutput(
            mandatory_actions=sorted(self.mandatory_actions),
            forbidden_actions=sorted(self.forbidden_actions),
            deadlines=dict(self.deadlines),
            required_prior_actions={k: list(v) for k, v in self.required_prior_actions.items()},
        )


# ============================================
# 5. Violation Event Schema
# ============================================


class ViolationType(str, Enum):
    """위반 이벤트 타입"""

    OMISSION = "omission"  # 필수 행동 누락
    COMMISSION = "commission"  # 금기 행동 수행
    TIMING = "timing"  # 마감 시간 초과
    SEQUENCE = "sequence"  # 순서 위반
    DEVIATION = "deviation"  # 허용 범위 이탈 (비정당화)
    CONFLICT = "conflict"  # CDE-derived: action mandated AND forbidden under co-satisfiable conditions


class HarmSeverity(str, Enum):
    """위해도 심각도"""

    MINOR = "minor"  # 경미 (임상적 영향 없음)
    MODERATE = "moderate"  # 중등도 (일시적 해로움 가능)
    MAJOR = "major"  # 중대 (진단/치료에 영향)
    SEVERE = "severe"  # 심각 (영구적 해로움 가능)
    CATASTROPHIC = "catastrophic"  # 치명적 (사망/중대 장애)


class ViolationEvent(BaseModel):
    """위반 이벤트 - Assessor가 생성"""

    violation_id: str
    violation_type: ViolationType
    timestamp_minutes: float

    # 위반 상세
    action_involved: str | None = None
    expected_action: str | None = None
    expected_deadline: float | None = None
    actual_time: float | None = None

    # 맥락
    state_at_violation: str  # state_id 참조
    node_at_violation: str  # CPG node_id 참조

    # 위해도 평가
    harm_severity: HarmSeverity
    guideline_class: RecommendationClass | None = None
    preventability: float = Field(1.0, ge=0.0, le=1.0)

    # 설명
    description: str
    guideline_reference: str

    # CDE-rescoring (B-cde-rescoring) — optional, backward-compatible
    source: str | None = None  # "engine" (default runtime) or "cde" (CDE-derived)
    conflict_provenance: list[str] | None = None  # rule provenance chain for CONFLICT


# ============================================
# 6. Episode & Scoring Schema
# ============================================


class EpisodeLog(BaseModel):
    """에피소드 전체 로그"""

    episode_id: str
    scenario_id: str
    agent_id: str

    # 상태-행동 시퀀스
    states: list[PatientState]
    actions: list[Action]
    observations: list[dict[str, Any]]

    # 메타데이터
    total_duration_minutes: float
    total_llm_calls: int
    total_tokens: int
    total_tool_calls: int

    # 종료 정보
    termination_reason: str  # "success", "timeout", "critical_event", "budget_exhausted"
    final_disposition: str | None = None


class SynergyPenalty(BaseModel):
    """Synergistic harm interaction penalty record"""

    group_id: str
    violation_ids: list[str]
    interaction_type: str  # InteractionType.value
    pattern_id: str
    multiplier: float
    additional_risk: float = Field(ge=0.0, description="Extra harm beyond additive scoring")
    clinical_rationale: str


# NOTE: CGAScore is the primary score dataclass used by HarmScorer.
# contracts.ScoreReport is a Pydantic validation schema for external APIs.
# For internal scoring pipelines, use CGAScore.
# For API/export validation, convert CGAScore → ScoreReport via to_score_report().
class CGAScore(BaseModel):
    """CGA-Bench 최종 점수"""

    episode_id: str

    # 준수율 (0~1)
    compliance_score: float = Field(..., ge=0.0, le=1.0)

    # 위험도 (dual-axis)
    peak_risk: float = Field(..., ge=0.0, description="단일 최악 위반의 가중 점수")
    aggregate_risk: float = Field(..., ge=0.0, description="누적 위험 점수")

    # 하위 점수
    sub_scores: dict[str, float] = Field(default_factory=dict, description="C1~C5 하위 능력별 점수")

    # 위반 이벤트 요약
    total_violations: int
    violations_by_type: dict[str, int]
    violation_events: list[ViolationEvent]

    # 정당화된 이탈 수
    justified_deviations: int

    # 예산 사용량
    budget_usage: dict[str, float]

    # Synergistic harm interactions (backward compatible defaults)
    synergistic_penalties: list[SynergyPenalty] = Field(
        default_factory=list, description="Detected synergistic harm interactions and penalties"
    )
    synergistic_risk: float = Field(
        0.0, ge=0.0, description="Total additional aggregate risk from synergistic interactions"
    )

    def to_score_report(self) -> dict:
        """Convert to ScoreReport-compatible dict for API/export."""
        return {
            "final_score": self.compliance_score,
            "action_coverage": self.sub_scores.get("C1_path_selection", 0),
            "compliance_score": self.compliance_score,
            "peak_risk": self.peak_risk,
            "aggregate_risk": self.aggregate_risk,
            "violations_by_type": self.violations_by_type,
            "sub_scores": self.sub_scores,
            "safety_gate": self.peak_risk >= 0.9,  # simplified
        }


# ============================================
# 7. Recommendation System Mapping
# ============================================

# GRADE to ACC/AHA Class Mapping
RECOMMENDATION_MAPPING: dict[str, RecommendationClass] = {
    # GRADE System (SSC, KDIGO)
    "Strong": RecommendationClass.CLASS_I,
    "strong": RecommendationClass.CLASS_I,
    "STRONG": RecommendationClass.CLASS_I,
    "Weak": RecommendationClass.CLASS_IIA,
    "weak": RecommendationClass.CLASS_IIA,
    "WEAK": RecommendationClass.CLASS_IIA,
    "Best Practice Statement": RecommendationClass.CLASS_I,
    "BPS": RecommendationClass.CLASS_I,
    # ACC/AHA Class System
    "I": RecommendationClass.CLASS_I,
    "Class I": RecommendationClass.CLASS_I,
    "CLASS I": RecommendationClass.CLASS_I,
    "IIa": RecommendationClass.CLASS_IIA,
    "Class IIa": RecommendationClass.CLASS_IIA,
    "CLASS IIA": RecommendationClass.CLASS_IIA,
    "IIb": RecommendationClass.CLASS_IIB,
    "Class IIb": RecommendationClass.CLASS_IIB,
    "CLASS IIB": RecommendationClass.CLASS_IIB,
    "III": RecommendationClass.CLASS_III,
    "Class III": RecommendationClass.CLASS_III,
    "CLASS III": RecommendationClass.CLASS_III,
    # Practice Point (KDIGO)
    "Practice Point": RecommendationClass.CLASS_IIA,
}

# Evidence Quality to Level Mapping
EVIDENCE_MAPPING: dict[str, EvidenceLevel] = {
    # GRADE Quality
    "High": EvidenceLevel.LEVEL_A,
    "high": EvidenceLevel.LEVEL_A,
    "HIGH": EvidenceLevel.LEVEL_A,
    "Moderate": EvidenceLevel.LEVEL_B,
    "moderate": EvidenceLevel.LEVEL_B,
    "MODERATE": EvidenceLevel.LEVEL_B,
    "Low": EvidenceLevel.LEVEL_B,  # Conservative: Low maps to B, not C
    "low": EvidenceLevel.LEVEL_B,
    "LOW": EvidenceLevel.LEVEL_B,
    "Very Low": EvidenceLevel.LEVEL_C,
    "very low": EvidenceLevel.LEVEL_C,
    "VERY LOW": EvidenceLevel.LEVEL_C,
    # ACC/AHA LOE
    "A": EvidenceLevel.LEVEL_A,
    "Level A": EvidenceLevel.LEVEL_A,
    "B": EvidenceLevel.LEVEL_B,
    "Level B": EvidenceLevel.LEVEL_B,
    "B-R": EvidenceLevel.LEVEL_B,  # Randomized
    "B-NR": EvidenceLevel.LEVEL_B,  # Non-randomized
    "C": EvidenceLevel.LEVEL_C,
    "Level C": EvidenceLevel.LEVEL_C,
    "C-LD": EvidenceLevel.LEVEL_C,  # Limited Data
    "C-EO": EvidenceLevel.LEVEL_C,  # Expert Opinion
}


def normalize_recommendation_class(value: str) -> RecommendationClass:
    """Convert various recommendation formats to standardized RecommendationClass"""
    if value in RECOMMENDATION_MAPPING:
        return RECOMMENDATION_MAPPING[value]
    # Default to Class IIa if unknown
    return RecommendationClass.CLASS_IIA


def normalize_evidence_level(value: str) -> EvidenceLevel:
    """Convert various evidence formats to standardized EvidenceLevel"""
    if value in EVIDENCE_MAPPING:
        return EVIDENCE_MAPPING[value]
    # Default to Level B if unknown
    return EvidenceLevel.LEVEL_B


# ============================================
# 8. Harm Weight Calculation
# ============================================

# Severity weights for harm calculation (CREOLA-inspired)
SEVERITY_WEIGHTS: dict[HarmSeverity, float] = {
    HarmSeverity.MINOR: 0.1,
    HarmSeverity.MODERATE: 0.3,
    HarmSeverity.MAJOR: 0.5,
    HarmSeverity.SEVERE: 0.8,
    HarmSeverity.CATASTROPHIC: 1.0,
}

# Recommendation class weights
CLASS_WEIGHTS: dict[RecommendationClass, float] = {
    RecommendationClass.CLASS_I: 1.0,  # Strongest recommendation
    RecommendationClass.CLASS_IIA: 0.7,  # Reasonable to perform
    RecommendationClass.CLASS_IIB: 0.4,  # May be considered
    RecommendationClass.CLASS_III: 0.0,  # Should not be done
}

# Violation type base weights
VIOLATION_TYPE_WEIGHTS: dict[ViolationType, float] = {
    ViolationType.OMISSION: 0.7,  # Missing required action
    ViolationType.COMMISSION: 1.0,  # Performing forbidden action
    ViolationType.TIMING: 0.5,  # Late action
    ViolationType.SEQUENCE: 0.6,  # Wrong order
    ViolationType.DEVIATION: 0.3,  # Unjustified deviation
}


def calculate_harm_weight(
    severity: HarmSeverity, guideline_class: RecommendationClass, preventability: float, violation_type: ViolationType
) -> float:
    """Calculate harm weight for violation scoring.

    Formula: w_j = severity × guideline_strength × preventability × violation_type_weight

    Reference: CREOLA harm taxonomy + GRADE/ACC-AHA mapping
    """
    severity_w = SEVERITY_WEIGHTS.get(severity, 0.5)
    class_w = CLASS_WEIGHTS.get(guideline_class, 0.7)
    violation_w = VIOLATION_TYPE_WEIGHTS.get(violation_type, 0.5)

    return severity_w * class_w * preventability * violation_w
