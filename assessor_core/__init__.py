"""Assessor Core: 채점 엔진"""
from cga_bench.assessor_core.violations import (
    ViolationExtractor,
    ViolationExtractorConfig,
    HarmSeverityMapping,
    TimingSeverityThreshold,
)
from cga_bench.assessor_core.harm_scorer import HarmScorer, MetricsReporter, HarmScorerConfig
from cga_bench.assessor_core.action_normalizer import (
    ActionNormalizer,
    ActionNormalizerConfig,
    NormalizationRule,
    normalize_action_id,
    create_default_normalizer,
)
from cga_bench.assessor_core.dka_violation_detector import (
    DKAViolationDetector,
    DKAViolationDetectorConfig,
    DKATrapViolation,
    create_dka_violation_detector,
)
from cga_bench.assessor_core.clinical_interaction_detector import (
    ClinicalInteractionDetector,
    InteractionConfig,
    InteractionPattern,
    InteractionType,
    InteractionGroup,
)

__all__ = [
    "ViolationExtractor",
    "ViolationExtractorConfig",
    "HarmSeverityMapping",
    "TimingSeverityThreshold",
    "HarmScorer",
    "HarmScorerConfig",
    "MetricsReporter",
    "ActionNormalizer",
    "ActionNormalizerConfig",
    "NormalizationRule",
    "normalize_action_id",
    "create_default_normalizer",
    # DKA-specific
    "DKAViolationDetector",
    "DKAViolationDetectorConfig",
    "DKATrapViolation",
    "create_dka_violation_detector",
    # Synergistic harm interactions
    "ClinicalInteractionDetector",
    "InteractionConfig",
    "InteractionPattern",
    "InteractionType",
    "InteractionGroup",
]
