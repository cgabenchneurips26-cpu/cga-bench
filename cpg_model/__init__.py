"""
CPG Model: 임상 가이드라인 모델

스키마:
- Action, ActionType: 행동 정의
- PatientState, VitalSigns: 환자 상태
- CPGNode, CPGGraph: 가이드라인 그래프
- GuidelineEngineOutput: 엔진 출력
- ViolationType, ViolationEvent: 위반 정의
- HarmSeverity: 위해도 정의
- EpisodeLog, CGAScore: 에피소드 및 점수
"""

try:
    from cga_bench.cpg_model.schemas import (
        Action,
        ActionType,
        PatientState,
        VitalSigns,
        LabResult,
        CPGNode,
        CPGGraph,
        GuidelineEngineOutput,
        NodeType,
        RecommendationClass,
        EvidenceLevel,
        ViolationType,
        ViolationEvent,
        HarmSeverity,
        EpisodeLog,
        CGAScore,
    )
except ImportError:
    from .schemas import (
        Action,
        ActionType,
        PatientState,
        VitalSigns,
        LabResult,
        CPGNode,
        CPGGraph,
        GuidelineEngineOutput,
        NodeType,
        RecommendationClass,
        EvidenceLevel,
        ViolationType,
        ViolationEvent,
        HarmSeverity,
        EpisodeLog,
        CGAScore,
    )

__all__ = [
    "Action",
    "ActionType",
    "PatientState",
    "VitalSigns",
    "LabResult",
    "CPGNode",
    "CPGGraph",
    "GuidelineEngineOutput",
    "NodeType",
    "RecommendationClass",
    "EvidenceLevel",
    "ViolationType",
    "ViolationEvent",
    "HarmSeverity",
    "EpisodeLog",
    "CGAScore",
]
