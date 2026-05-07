"""
Semantic Layer: External Benchmark Evaluation

Provides normalization and evaluability-first compliance scoring for
external benchmarks without replacing existing pipelines.

CANONICAL PATH: This is the canonical adapter interface (semantic_layer/external/).
The legacy adapter layer at env/adapters/ is maintained for backward compatibility
only. New dataset integrations should be added here, not in env/adapters/.
"""

from typing import Callable, cast

from . import healthbench_integration as _healthbench_integration

from .models import (
    EpisodeEvidence,
    NormalizedEpisode,
    EvaluableComplianceReport,
)
from .agentclinic import (
    normalize_agentclinic_case,
)
from .medagentbench import (
    evaluate_medagentbench_tasks,
    normalize_medagentbench_task,
)
from .medchain import (
    normalize_medchain_case,
)
from .normalize import (
    normalize_external_case,
)
from .evaluator import (
    evaluate_agentclinic_cases,
    evaluate_medchain_cases,
    evaluate_normalized_episodes,
    summarize_reports,
    reports_to_json,
)
from .healthbench_dialogue import (
    DialogueAct,
    DialogueActConfig,
    DialogueGraph,
    DialogueState,
    DialogueTransition,
    build_dialogue_graph,
    DialogueTurn,
    classify_dialogue_acts,
    graph_summary,
    parse_conversation_to_turns,
    update_dialogue_state,
)
from .healthbench_quality import (
    QualityScoreConfig,
    EmpathyScoreResult,
    AccuracyScoreResult,
    SentimentResult,
    EmpathyScaleResult,
    QualityAssessment,
    JudgeEndpoint,
    MultiJudgeConfig,
    MultiJudgeResult,
    RAGConfig,
    RAGContext,
    ModelTier,
    TieringConfig,
    compute_empathy_score,
    compute_accuracy_score,
    compute_sentiment,
    compute_empathy_scale,
    compute_quality_assessment,
    aggregate_quality_scores,
    evaluate_with_multi_judge,
    retrieve_context,
    estimate_complexity,
    select_model_tier,
)
from .healthbench_integration import (
    CompositeScoreConfig,
    CompositeScoreResult,
    ExtendedReportEntry,
    DashboardReport,
    HITLFlag,
    HITLConfig,
    compute_composite_score,
    summarize_extended_reports,
    render_dashboard_report,
    render_dashboard_text,
    flag_cases_for_review,
)

build_extended_report = cast(
    Callable[[object, dict[str, object] | None, dict[str, object] | None, CompositeScoreConfig], ExtendedReportEntry],
    _healthbench_integration.build_extended_report,
)

from .healthbench import (
    build_extended_meta_eval_episode,
    run_extended_evaluation,
)

__all__ = [
    "EpisodeEvidence",
    "NormalizedEpisode",
    "EvaluableComplianceReport",
    "normalize_agentclinic_case",
    "normalize_medagentbench_task",
    "normalize_medchain_case",
    "normalize_external_case",
    "evaluate_agentclinic_cases",
    "evaluate_medchain_cases",
    "evaluate_normalized_episodes",
    "evaluate_medagentbench_tasks",
    "summarize_reports",
    "reports_to_json",
    # HealthBench dialogue module
    "DialogueAct",
    "DialogueActConfig",
    "DialogueTransition",
    "DialogueGraph",
    "DialogueState",
    "DialogueTurn",
    "classify_dialogue_acts",
    "build_dialogue_graph",
    "graph_summary",
    "parse_conversation_to_turns",
    "update_dialogue_state",
    # HealthBench quality module
    "QualityScoreConfig",
    "EmpathyScoreResult",
    "AccuracyScoreResult",
    "SentimentResult",
    "EmpathyScaleResult",
    "QualityAssessment",
    "JudgeEndpoint",
    "MultiJudgeConfig",
    "MultiJudgeResult",
    "RAGConfig",
    "RAGContext",
    "ModelTier",
    "TieringConfig",
    "compute_empathy_score",
    "compute_accuracy_score",
    "compute_sentiment",
    "compute_empathy_scale",
    "compute_quality_assessment",
    "aggregate_quality_scores",
    "evaluate_with_multi_judge",
    "retrieve_context",
    "estimate_complexity",
    "select_model_tier",
    # HealthBench integration module
    "CompositeScoreConfig",
    "CompositeScoreResult",
    "ExtendedReportEntry",
    "DashboardReport",
    "HITLFlag",
    "HITLConfig",
    "compute_composite_score",
    "build_extended_report",
    "summarize_extended_reports",
    "render_dashboard_report",
    "render_dashboard_text",
    "flag_cases_for_review",
    # HealthBench E2E extended pipeline
    "build_extended_meta_eval_episode",
    "run_extended_evaluation",
]
