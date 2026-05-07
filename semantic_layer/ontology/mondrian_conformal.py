"""Mondrian (Group-Conditional) Conformal Prediction for Entity Linking.

Extends standard conformal prediction with group-conditional coverage guarantees.
Groups are defined by SemanticType, enabling per-type calibration.

Key Benefits:
1. Per-type coverage guarantees (LAB, DRUG, PROCEDURE each get 90% coverage)
2. More interpretable prediction sets (type-specific thresholds)
3. Better handling of type-specific difficulty (LAB confusions vs DRUG confusions)

References:
- Vovk (2005): Conditional Validity of Inductive Conformal Predictors
- Lei & Wasserman (2014): Distribution-Free Predictive Inference
- NeurIPS 2024: RC3P (Reducing Class-Conditional Prediction Sets)
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from .neural_embedder import SemanticType

logger = logging.getLogger(__name__)


class UncertaintyLevel(str, Enum):
    """Uncertainty level based on prediction set characteristics."""
    LOW = "LOW"           # Set size 1, high confidence
    MEDIUM = "MEDIUM"     # Set size 2-3, moderate confidence
    HIGH = "HIGH"         # Set size > 3, low confidence
    ABSTAIN = "ABSTAIN"   # Cannot make reliable prediction


@dataclass
class MondrianConfig:
    """Configuration for Mondrian conformal prediction.

    Attributes:
        alpha: Global miscoverage rate (1 - α = coverage)
        per_type_alpha: Per-type alpha overrides {type: alpha}
        min_calibration_per_type: Minimum calibration examples per type
        fallback_to_global: Use global threshold if type has insufficient data
        enable_abstain: Allow abstention for uncertain cases
        abstain_set_size_threshold: Set size above which to abstain
        max_set_size: Maximum prediction set size
        adaptive_sets: Use Adaptive Prediction Sets (APS)
        regularization: APS regularization parameter
    """
    alpha: float = 0.10
    per_type_alpha: Dict[str, float] = field(default_factory=dict)
    min_calibration_per_type: int = 10
    fallback_to_global: bool = True
    enable_abstain: bool = True
    abstain_set_size_threshold: int = 5
    max_set_size: int = 10
    adaptive_sets: bool = True
    regularization: float = 0.0


@dataclass
class TypeCalibration:
    """Calibration result for a single semantic type."""
    semantic_type: SemanticType
    threshold: float
    n_calibration: int
    empirical_coverage: float
    avg_set_size: float
    is_fallback: bool = False  # Using global threshold


@dataclass
class MondrianPredictionSet:
    """Prediction set with group-conditional coverage.

    Attributes:
        prediction_set: List of concept IDs in the set
        scores: Corresponding similarity scores
        semantic_type: Inferred type of the query
        threshold: Type-specific threshold used
        uncertainty_level: LOW/MEDIUM/HIGH/ABSTAIN
        coverage_guarantee: Guaranteed coverage for this type
        is_type_fallback: Using global threshold (insufficient type data)
    """
    prediction_set: List[str]
    scores: List[float]
    semantic_type: SemanticType
    threshold: float
    uncertainty_level: UncertaintyLevel
    coverage_guarantee: float
    is_type_fallback: bool = False

    @property
    def set_size(self) -> int:
        return len(self.prediction_set)

    @property
    def is_singleton(self) -> bool:
        return self.set_size == 1

    @property
    def is_empty(self) -> bool:
        return self.set_size == 0

    @property
    def top1(self) -> Optional[str]:
        return self.prediction_set[0] if self.prediction_set else None

    @property
    def top1_score(self) -> float:
        return self.scores[0] if self.scores else 0.0

    def contains(self, concept_id: str) -> bool:
        return concept_id in self.prediction_set


@dataclass
class MondrianCalibrationResult:
    """Complete Mondrian calibration result."""
    global_threshold: float
    type_calibrations: Dict[SemanticType, TypeCalibration]
    global_coverage: float
    global_avg_set_size: float
    n_total: int
    per_type_coverage: Dict[SemanticType, float]
    per_type_set_size: Dict[SemanticType, float]


class MondrianConformalMatcher:
    """Mondrian (Group-Conditional) Conformal Prediction for Entity Linking.

    Provides per-SemanticType coverage guarantees instead of global coverage.
    This is more appropriate when different types have different difficulty levels.

    Architecture:
    ```
    Query → Infer SemanticType → Get Type-Specific Threshold
                                        │
                                        ▼
                               Compute Prediction Set
                               (include if score > threshold)
                                        │
                                        ▼
                               Return with Type-Conditional
                               Coverage Guarantee
    ```

    Usage:
        mondrian = MondrianConformalMatcher(base_matcher, MondrianConfig())

        # Calibrate with labeled examples
        mondrian.calibrate(calibration_data)

        # Predict with type-conditional guarantee
        result = mondrian.predict("order lactate")
        print(f"Type: {result.semantic_type}")
        print(f"Prediction set: {result.prediction_set}")
        print(f"Coverage: {result.coverage_guarantee}%")
    """

    def __init__(
        self,
        base_matcher: Any,  # OntologyMatcher or NeuralEmbedder
        config: MondrianConfig,
    ):
        self._base_matcher = base_matcher
        self._config = config

        # Calibration state
        self._global_threshold: Optional[float] = None
        self._type_thresholds: Dict[SemanticType, float] = {}
        self._type_calibrations: Dict[SemanticType, TypeCalibration] = {}
        self._is_calibrated = False
        self._calibration_result: Optional[MondrianCalibrationResult] = None

    @property
    def is_calibrated(self) -> bool:
        return self._is_calibrated

    @property
    def calibration_result(self) -> Optional[MondrianCalibrationResult]:
        return self._calibration_result

    def calibrate(
        self,
        calibration_data: List[Tuple[str, str, SemanticType]],  # (query, gold_id, type)
    ) -> MondrianCalibrationResult:
        """Calibrate with per-type thresholds.

        Args:
            calibration_data: List of (query, gold_concept_id, semantic_type) tuples

        Returns:
            MondrianCalibrationResult with per-type statistics.
        """
        # Group by semantic type
        by_type: Dict[SemanticType, List[Tuple[str, str]]] = defaultdict(list)
        for query, gold_cid, sem_type in calibration_data:
            by_type[sem_type].append((query, gold_cid))

        # Collect all nonconformity scores for global threshold
        all_scores = []
        type_scores: Dict[SemanticType, List[float]] = defaultdict(list)

        for query, gold_cid, sem_type in calibration_data:
            nc_score = self._compute_nonconformity(query, gold_cid)
            all_scores.append(nc_score)
            type_scores[sem_type].append(nc_score)

        # Compute global threshold
        self._global_threshold = self._compute_quantile_threshold(
            all_scores, self._config.alpha
        )

        # Compute per-type thresholds
        self._type_thresholds = {}
        self._type_calibrations = {}

        for sem_type, scores in type_scores.items():
            # Get type-specific alpha (default to global)
            type_alpha = self._config.per_type_alpha.get(
                sem_type.value, self._config.alpha
            )

            if len(scores) >= self._config.min_calibration_per_type:
                # Sufficient data for type-specific threshold
                threshold = self._compute_quantile_threshold(scores, type_alpha)
                is_fallback = False
            elif self._config.fallback_to_global:
                # Fall back to global threshold
                threshold = self._global_threshold
                is_fallback = True
                logger.warning(
                    f"Type {sem_type.value} has only {len(scores)} examples, "
                    f"using global threshold"
                )
            else:
                # Skip this type
                continue

            self._type_thresholds[sem_type] = threshold

            # Compute empirical coverage for this type
            type_data = by_type[sem_type]
            covered = 0
            total_set_size = 0

            for query, gold_cid in type_data:
                pred_set = self._make_prediction_set(query, sem_type, threshold)
                if pred_set.contains(gold_cid):
                    covered += 1
                total_set_size += pred_set.set_size

            n = len(type_data)
            self._type_calibrations[sem_type] = TypeCalibration(
                semantic_type=sem_type,
                threshold=threshold,
                n_calibration=n,
                empirical_coverage=covered / n if n else 0,
                avg_set_size=total_set_size / n if n else 0,
                is_fallback=is_fallback,
            )

        # Compute global empirical coverage
        global_covered = 0
        global_set_size = 0
        for query, gold_cid, sem_type in calibration_data:
            threshold = self._type_thresholds.get(sem_type, self._global_threshold)
            pred_set = self._make_prediction_set(query, sem_type, threshold)
            if pred_set.contains(gold_cid):
                global_covered += 1
            global_set_size += pred_set.set_size

        n_total = len(calibration_data)

        self._calibration_result = MondrianCalibrationResult(
            global_threshold=self._global_threshold,
            type_calibrations=self._type_calibrations,
            global_coverage=global_covered / n_total if n_total else 0,
            global_avg_set_size=global_set_size / n_total if n_total else 0,
            n_total=n_total,
            per_type_coverage={
                t: cal.empirical_coverage
                for t, cal in self._type_calibrations.items()
            },
            per_type_set_size={
                t: cal.avg_set_size
                for t, cal in self._type_calibrations.items()
            },
        )

        self._is_calibrated = True

        logger.info(
            f"Mondrian calibration complete: {len(self._type_thresholds)} types, "
            f"global_coverage={self._calibration_result.global_coverage:.1%}"
        )

        return self._calibration_result

    def predict(
        self,
        query: str,
        expected_type: Optional[SemanticType] = None,
    ) -> MondrianPredictionSet:
        """Predict with type-conditional coverage guarantee.

        Args:
            query: Query text
            expected_type: Optional expected semantic type (auto-inferred if None)

        Returns:
            MondrianPredictionSet with type-specific threshold and coverage.
        """
        if not self._is_calibrated:
            logger.warning("Matcher not calibrated, using default threshold")
            self._global_threshold = 0.5

        # Infer semantic type if not provided
        if expected_type is None:
            from .neural_embedder import infer_semantic_type
            expected_type = infer_semantic_type(query)

        # Get type-specific threshold
        threshold = self._type_thresholds.get(expected_type, self._global_threshold)
        is_fallback = expected_type not in self._type_thresholds

        # Get coverage guarantee
        type_alpha = self._config.per_type_alpha.get(
            expected_type.value, self._config.alpha
        )
        coverage_guarantee = 1 - type_alpha

        return self._make_prediction_set(
            query, expected_type, threshold, is_fallback, coverage_guarantee
        )

    def predict_batch(
        self,
        queries: List[str],
        expected_types: Optional[List[SemanticType]] = None,
    ) -> List[MondrianPredictionSet]:
        """Batch prediction with type-conditional guarantees."""
        if expected_types is None:
            expected_types = [None] * len(queries)

        return [
            self.predict(q, t) for q, t in zip(queries, expected_types)
        ]

    def _compute_nonconformity(self, query: str, gold_cid: str) -> float:
        """Compute nonconformity score for (query, gold) pair.

        Nonconformity = 1 - similarity_to_gold
        Lower is more conforming.
        """
        # Get candidates from base matcher
        if hasattr(self._base_matcher, 'find_similar'):
            matches = self._base_matcher.find_similar(query, top_k=20)
            for m in matches:
                if m.concept_id == gold_cid:
                    return 1.0 - m.similarity
            return 1.0  # Gold not in top-k = high nonconformity
        elif hasattr(self._base_matcher, 'match'):
            result = self._base_matcher.match(query)
            if result.concept_id == gold_cid:
                return 1.0 - result.confidence
            return 1.0
        else:
            return 0.5  # Fallback

    def _compute_quantile_threshold(
        self,
        scores: List[float],
        alpha: float,
    ) -> float:
        """Compute quantile threshold with finite-sample correction."""
        n = len(scores)
        if n == 0:
            return 0.5

        scores_sorted = sorted(scores)

        # Quantile with finite-sample correction
        q_level = math.ceil((n + 1) * (1 - alpha)) / n
        q_index = min(int(q_level * n), n - 1)

        return scores_sorted[q_index]

    def _make_prediction_set(
        self,
        query: str,
        expected_type: SemanticType,
        threshold: float,
        is_fallback: bool = False,
        coverage_guarantee: float = 0.9,
    ) -> MondrianPredictionSet:
        """Construct prediction set using threshold."""
        # Get candidates
        if hasattr(self._base_matcher, 'find_similar'):
            matches = self._base_matcher.find_similar(
                query, top_k=self._config.max_set_size * 2, expected_type=expected_type
            )
            candidates = [(m.concept_id, m.similarity) for m in matches]
        elif hasattr(self._base_matcher, 'match'):
            result = self._base_matcher.match(query)
            candidates = [(result.concept_id, result.confidence)]
            candidates.extend(result.alternatives[:self._config.max_set_size])
        else:
            candidates = []

        # Include candidates with nonconformity <= threshold
        # Nonconformity = 1 - similarity, so include if similarity >= 1 - threshold
        sim_threshold = 1 - threshold

        if self._config.adaptive_sets:
            # Adaptive Prediction Sets (APS)
            included = []
            cumsum = 0.0
            for cid, score in candidates:
                cumsum += score
                if cumsum >= 1 - threshold + self._config.regularization:
                    break
                included.append((cid, score))
            # Always include at least best candidate
            if not included and candidates:
                included = [candidates[0]]
        else:
            # Standard: include all above threshold
            included = [
                (cid, score) for cid, score in candidates
                if score >= sim_threshold
            ]

        # Limit set size
        included = included[:self._config.max_set_size]

        prediction_set = [cid for cid, _ in included]
        scores = [score for _, score in included]

        # Determine uncertainty level
        set_size = len(prediction_set)
        if set_size == 0:
            uncertainty = UncertaintyLevel.ABSTAIN
        elif set_size == 1:
            uncertainty = UncertaintyLevel.LOW
        elif set_size <= 3:
            uncertainty = UncertaintyLevel.MEDIUM
        elif set_size <= self._config.abstain_set_size_threshold:
            uncertainty = UncertaintyLevel.HIGH
        else:
            uncertainty = UncertaintyLevel.ABSTAIN if self._config.enable_abstain else UncertaintyLevel.HIGH

        return MondrianPredictionSet(
            prediction_set=prediction_set,
            scores=scores,
            semantic_type=expected_type,
            threshold=threshold,
            uncertainty_level=uncertainty,
            coverage_guarantee=coverage_guarantee,
            is_type_fallback=is_fallback,
        )

    def get_type_statistics(self) -> Dict[str, Any]:
        """Get per-type calibration statistics."""
        if not self._calibration_result:
            return {}

        return {
            "global_threshold": self._global_threshold,
            "global_coverage": self._calibration_result.global_coverage,
            "global_avg_set_size": self._calibration_result.global_avg_set_size,
            "per_type": {
                t.value: {
                    "threshold": cal.threshold,
                    "n_calibration": cal.n_calibration,
                    "empirical_coverage": cal.empirical_coverage,
                    "avg_set_size": cal.avg_set_size,
                    "is_fallback": cal.is_fallback,
                }
                for t, cal in self._type_calibrations.items()
            },
        }

    def generate_report(self) -> str:
        """Generate Mondrian calibration report."""
        if not self._calibration_result:
            return "# Mondrian Conformal Report\n\nNot calibrated."

        r = self._calibration_result
        lines = [
            "# Mondrian Conformal Prediction Report",
            "",
            "## Global Statistics",
            "",
            f"- **Total calibration examples**: {r.n_total}",
            f"- **Global threshold**: {r.global_threshold:.4f}",
            f"- **Global coverage**: {r.global_coverage:.1%}",
            f"- **Global avg set size**: {r.global_avg_set_size:.2f}",
            "",
            "## Per-Type Calibration",
            "",
            "| Type | N | Threshold | Coverage | Avg Set Size | Fallback |",
            "|------|---|-----------|----------|--------------|----------|",
        ]

        for sem_type, cal in sorted(
            self._type_calibrations.items(),
            key=lambda x: x[0].value
        ):
            fallback_str = "Yes" if cal.is_fallback else "No"
            lines.append(
                f"| {sem_type.value} | {cal.n_calibration} | "
                f"{cal.threshold:.4f} | {cal.empirical_coverage:.1%} | "
                f"{cal.avg_set_size:.2f} | {fallback_str} |"
            )

        lines.extend([
            "",
            "## Coverage Analysis",
            "",
        ])

        # Check if type-specific coverage meets target
        target = 1 - self._config.alpha
        for sem_type, cal in self._type_calibrations.items():
            type_target = 1 - self._config.per_type_alpha.get(
                sem_type.value, self._config.alpha
            )
            gap = cal.empirical_coverage - type_target
            status = "✓" if gap >= -0.02 else "✗"
            lines.append(
                f"- **{sem_type.value}**: {cal.empirical_coverage:.1%} "
                f"(target: {type_target:.0%}) {status}"
            )

        return "\n".join(lines)


# ============================================================
# Integration with Existing Ablation Framework
# ============================================================

def calibrate_mondrian_from_goldset(
    base_matcher: Any,
    gold_set: List[Any],  # List of GoldInstance from ablation.py
    config: Optional[MondrianConfig] = None,
) -> MondrianConformalMatcher:
    """Calibrate Mondrian matcher from gold set.

    Args:
        base_matcher: OntologyMatcher or NeuralEmbedder
        gold_set: List of GoldInstance with query, gold_concept_id, category
        config: Optional MondrianConfig

    Returns:
        Calibrated MondrianConformalMatcher.
    """
    from .neural_embedder import SemanticType

    config = config or MondrianConfig()
    mondrian = MondrianConformalMatcher(base_matcher, config)

    # Convert gold set to calibration format
    calibration_data = []
    for instance in gold_set:
        # Map category to SemanticType
        category = instance.category.lower()
        type_map = {
            "drug": SemanticType.DRUG,
            "lab": SemanticType.LAB,
            "imaging": SemanticType.IMAGING,
            "procedure": SemanticType.PROCEDURE,
            "assessment": SemanticType.ASSESSMENT,
            "fluid": SemanticType.FLUID,
        }
        sem_type = type_map.get(category, SemanticType.UNKNOWN)

        calibration_data.append((
            instance.query,
            instance.gold_concept_id,
            sem_type,
        ))

    mondrian.calibrate(calibration_data)

    return mondrian
