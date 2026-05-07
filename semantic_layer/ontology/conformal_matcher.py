"""Conformal Prediction for Entity Linking / Concept Normalization.

Provides distribution-free uncertainty quantification for ontology matching.
Instead of a single "best match", returns a prediction set with coverage guarantees.

Key concepts:
- Nonconformity score: How "strange" a candidate is (1 - similarity)
- Calibration set: Held-out examples to determine threshold
- Coverage guarantee: P(true_concept ∈ prediction_set) ≥ 1 - α

References:
- Vovk et al. (2005): Algorithmic Learning in a Random World
- Angelopoulos & Bates (2021): A Gentle Introduction to Conformal Prediction
- Fisch et al. (2022): Conformal Risk Control for NLP
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from .concept import (
    AbstractionLevel,
    ClinicalConcept,
    MatchResult,
)

logger = logging.getLogger(__name__)


@dataclass
class ConformalConfig:
    """Configuration for conformal prediction.

    Attributes:
        alpha: Miscoverage rate (1 - α = coverage guarantee)
        min_calibration_size: Minimum calibration examples needed
        adaptive_sets: Use adaptive prediction sets (APS)
        regularization: Regularization for APS (larger = smaller sets)
        max_set_size: Maximum prediction set size (safety cap)
        enable_abstain: Allow "abstain" when set is too large
        abstain_threshold: Set size threshold to trigger abstain
    """
    alpha: float = 0.10  # 90% coverage guarantee
    min_calibration_size: int = 30
    adaptive_sets: bool = True
    regularization: float = 0.0  # λ for APS
    max_set_size: int = 10
    enable_abstain: bool = True
    abstain_threshold: int = 5  # Abstain if set size > threshold


@dataclass
class PredictionSet:
    """Conformal prediction set with coverage guarantee.

    Attributes:
        candidates: List of (concept_id, score, nonconformity) tuples
        threshold: Calibrated nonconformity threshold (q̂)
        coverage: Empirical coverage on calibration set
        set_size: Number of concepts in prediction set
        abstain: Whether to abstain (set too large/uncertain)
        query: Original query string
    """
    candidates: List[Tuple[str, float, float]]  # (concept_id, score, nonconformity)
    threshold: float
    coverage: float
    set_size: int
    abstain: bool
    query: str

    @property
    def concept_ids(self) -> List[str]:
        """Concept IDs in the prediction set."""
        return [c[0] for c in self.candidates if c[2] <= self.threshold]

    @property
    def is_singleton(self) -> bool:
        """Whether the set contains exactly one concept."""
        return self.set_size == 1

    @property
    def is_empty(self) -> bool:
        """Whether the set is empty (likely OOV)."""
        return self.set_size == 0

    def contains(self, concept_id: str) -> bool:
        """Check if concept is in the prediction set."""
        return concept_id in self.concept_ids

    def to_match_result(self) -> Optional[MatchResult]:
        """Convert to MatchResult (best candidate if singleton or small set)."""
        if self.abstain or self.is_empty:
            return None

        # Return best candidate
        best = self.candidates[0] if self.candidates else None
        if not best:
            return None

        return MatchResult(
            source=self.query,
            matched_concept=None,  # Will be filled by caller
            confidence=best[1],
            match_level=AbstractionLevel.NORMALIZED,
            distance=0,
            strategy="conformal",
            alternatives=[(c[0], c[1]) for c in self.candidates[1:self.set_size]],
        )


@dataclass
class CalibrationResult:
    """Result of conformal calibration.

    Attributes:
        threshold: Calibrated nonconformity threshold (q̂)
        n_calibration: Number of calibration examples
        empirical_coverage: Coverage on calibration set
        avg_set_size: Average prediction set size
        ece: Expected Calibration Error
    """
    threshold: float
    n_calibration: int
    empirical_coverage: float
    avg_set_size: float
    ece: float = 0.0


class ConformalMatcher:
    """Conformal prediction wrapper for ontology matching.

    Wraps an existing matcher (OntologyMatcher) and provides:
    1. Calibrated prediction sets with coverage guarantees
    2. Uncertainty quantification (set size indicates confidence)
    3. Abstention for highly ambiguous cases

    Usage:
        base_matcher = OntologyMatcher(ontology, config)
        conformal = ConformalMatcher(base_matcher, ConformalConfig())

        # Calibrate on held-out examples
        conformal.calibrate(calibration_data)

        # Get prediction set with coverage guarantee
        pred_set = conformal.predict("start pressors")
        if not pred_set.abstain:
            for concept_id in pred_set.concept_ids:
                print(f"  {concept_id}")
    """

    def __init__(
        self,
        base_matcher: Any,  # OntologyMatcher (avoid circular import)
        config: ConformalConfig,
    ):
        self._base_matcher = base_matcher
        self._config = config
        self._threshold: Optional[float] = None
        self._calibration_result: Optional[CalibrationResult] = None
        self._is_calibrated = False

    @property
    def is_calibrated(self) -> bool:
        """Whether the matcher has been calibrated."""
        return self._is_calibrated

    @property
    def threshold(self) -> Optional[float]:
        """Calibrated nonconformity threshold."""
        return self._threshold

    @property
    def calibration_result(self) -> Optional[CalibrationResult]:
        """Calibration statistics."""
        return self._calibration_result

    def calibrate(
        self,
        calibration_data: List[Tuple[str, str]],  # (query, true_concept_id)
    ) -> CalibrationResult:
        """Calibrate the conformal predictor on held-out data.

        Args:
            calibration_data: List of (query, true_concept_id) pairs

        Returns:
            CalibrationResult with threshold and statistics
        """
        if len(calibration_data) < self._config.min_calibration_size:
            logger.warning(
                f"Calibration set too small ({len(calibration_data)} < "
                f"{self._config.min_calibration_size}). Using default threshold."
            )
            self._threshold = 0.5
            self._calibration_result = CalibrationResult(
                threshold=0.5,
                n_calibration=len(calibration_data),
                empirical_coverage=0.0,
                avg_set_size=0.0,
            )
            self._is_calibrated = True
            return self._calibration_result

        # Compute nonconformity scores for true labels
        nonconformity_scores = []
        all_candidates_list = []

        for query, true_concept_id in calibration_data:
            candidates = self._get_candidates(query)
            all_candidates_list.append(candidates)

            # Find nonconformity of true label
            true_score = None
            for cid, score, nonconf in candidates:
                if cid == true_concept_id:
                    true_score = nonconf
                    break

            if true_score is None:
                # True concept not in candidates - high nonconformity
                true_score = 1.0

            nonconformity_scores.append(true_score)

        # Compute quantile threshold (with finite-sample correction)
        n = len(nonconformity_scores)
        scores_sorted = sorted(nonconformity_scores)

        # Quantile with finite-sample correction: ceil((n+1)(1-α)) / n
        q_level = math.ceil((n + 1) * (1 - self._config.alpha)) / n
        q_index = min(int(q_level * n), n - 1)
        self._threshold = scores_sorted[q_index]

        # Compute empirical coverage and average set size
        covered = 0
        total_set_size = 0

        for i, (query, true_concept_id) in enumerate(calibration_data):
            candidates = all_candidates_list[i]
            pred_set = self._make_prediction_set(query, candidates, self._threshold)

            if pred_set.contains(true_concept_id):
                covered += 1
            total_set_size += pred_set.set_size

        empirical_coverage = covered / n
        avg_set_size = total_set_size / n

        # Compute ECE (Expected Calibration Error)
        ece = self._compute_ece(calibration_data, all_candidates_list)

        self._calibration_result = CalibrationResult(
            threshold=self._threshold,
            n_calibration=n,
            empirical_coverage=empirical_coverage,
            avg_set_size=avg_set_size,
            ece=ece,
        )
        self._is_calibrated = True

        logger.info(
            f"Conformal calibration complete: threshold={self._threshold:.3f}, "
            f"coverage={empirical_coverage:.2%}, avg_set_size={avg_set_size:.1f}"
        )

        return self._calibration_result

    def predict(self, query: str) -> PredictionSet:
        """Get prediction set with coverage guarantee.

        Args:
            query: Action/concept string to match

        Returns:
            PredictionSet with candidates meeting nonconformity threshold
        """
        if not self._is_calibrated:
            logger.warning("Matcher not calibrated. Using default threshold.")
            self._threshold = 0.5

        candidates = self._get_candidates(query)
        return self._make_prediction_set(
            query, candidates, self._threshold or 0.5
        )

    def predict_batch(
        self, queries: List[str]
    ) -> List[PredictionSet]:
        """Get prediction sets for multiple queries.

        Args:
            queries: List of query strings

        Returns:
            List of PredictionSet
        """
        return [self.predict(q) for q in queries]

    def _get_candidates(
        self, query: str, top_k: int = 20
    ) -> List[Tuple[str, float, float]]:
        """Get candidate concepts with scores and nonconformity.

        Returns list of (concept_id, similarity_score, nonconformity_score).
        """
        candidates = []

        # Get match result from base matcher
        result = self._base_matcher.match(query)

        if result.matched:
            # Best match
            candidates.append((
                result.concept_id,
                result.confidence,
                1.0 - result.confidence,  # Nonconformity = 1 - score
            ))

            # Alternatives
            for alt_cid, alt_score in result.alternatives:
                candidates.append((
                    alt_cid,
                    alt_score,
                    1.0 - alt_score,
                ))

        # If neural fallback available, get more candidates
        if hasattr(self._base_matcher, '_neural_embedder'):
            embedder = self._base_matcher._neural_embedder
            if embedder and embedder.is_initialized:
                neural_matches = embedder.find_similar(query, top_k=top_k)
                for nm in neural_matches:
                    if nm.concept_id not in [c[0] for c in candidates]:
                        candidates.append((
                            nm.concept_id,
                            nm.similarity,
                            1.0 - nm.similarity,
                        ))

        # Sort by nonconformity (ascending = most conforming first)
        candidates.sort(key=lambda x: x[2])

        return candidates[:top_k]

    def _make_prediction_set(
        self,
        query: str,
        candidates: List[Tuple[str, float, float]],
        threshold: float,
    ) -> PredictionSet:
        """Create prediction set from candidates and threshold."""
        # Filter candidates by nonconformity threshold
        if self._config.adaptive_sets:
            # Adaptive Prediction Sets (APS): include cumulative
            included = []
            cumsum = 0.0
            for cid, score, nonconf in candidates:
                cumsum += score
                if cumsum >= 1 - threshold + self._config.regularization:
                    break
                included.append((cid, score, nonconf))
            # Always include at least the best if any candidates
            if not included and candidates:
                included = [candidates[0]]
        else:
            # Standard: include all below threshold
            included = [
                (cid, score, nonconf)
                for cid, score, nonconf in candidates
                if nonconf <= threshold
            ]

        set_size = min(len(included), self._config.max_set_size)
        included = included[:set_size]

        # Check abstention
        abstain = (
            self._config.enable_abstain
            and set_size > self._config.abstain_threshold
        )

        return PredictionSet(
            candidates=candidates,  # Full candidate list
            threshold=threshold,
            coverage=1 - self._config.alpha,
            set_size=set_size,
            abstain=abstain,
            query=query,
        )

    def _compute_ece(
        self,
        calibration_data: List[Tuple[str, str]],
        all_candidates: List[List[Tuple[str, float, float]]],
        n_bins: int = 10,
    ) -> float:
        """Compute Expected Calibration Error.

        ECE measures how well the confidence scores reflect true accuracy.
        """
        bins = [[] for _ in range(n_bins)]

        for i, (query, true_cid) in enumerate(calibration_data):
            candidates = all_candidates[i]
            if not candidates:
                continue

            # Top-1 prediction
            top_cid, top_score, _ = candidates[0]
            correct = 1 if top_cid == true_cid else 0

            # Bin by confidence
            bin_idx = min(int(top_score * n_bins), n_bins - 1)
            bins[bin_idx].append((top_score, correct))

        # Compute ECE
        ece = 0.0
        total = sum(len(b) for b in bins)

        for b in bins:
            if not b:
                continue
            avg_conf = sum(x[0] for x in b) / len(b)
            avg_acc = sum(x[1] for x in b) / len(b)
            ece += len(b) / total * abs(avg_conf - avg_acc)

        return ece

    def get_uncertainty_metrics(self, query: str) -> Dict[str, Any]:
        """Get detailed uncertainty metrics for a query.

        Useful for debugging and analysis.
        """
        pred_set = self.predict(query)

        return {
            "query": query,
            "set_size": pred_set.set_size,
            "is_singleton": pred_set.is_singleton,
            "is_empty": pred_set.is_empty,
            "abstain": pred_set.abstain,
            "threshold": pred_set.threshold,
            "coverage_guarantee": pred_set.coverage,
            "top_candidates": [
                {"concept_id": c[0], "score": c[1], "nonconformity": c[2]}
                for c in pred_set.candidates[:5]
            ],
            "prediction_set": pred_set.concept_ids,
        }


class SiblingReranker:
    """Reranker using ontology sibling relationships as hard negatives.

    When candidates include sibling concepts (same parent, different meaning),
    applies penalty to encourage disambiguation.

    Example:
        "start vasopressor" → norepinephrine vs vasopressin (siblings)
        → Require additional evidence to disambiguate
    """

    def __init__(
        self,
        ontology: Any,  # ClinicalOntology
        sibling_penalty: float = 0.15,
        type_mismatch_penalty: float = 0.3,
    ):
        self._ontology = ontology
        self._sibling_penalty = sibling_penalty
        self._type_mismatch_penalty = type_mismatch_penalty

    def rerank(
        self,
        query: str,
        candidates: List[Tuple[str, float]],  # (concept_id, score)
        query_type: Optional[str] = None,  # Expected type: "medication", "lab", etc.
    ) -> List[Tuple[str, float]]:
        """Rerank candidates with sibling/type penalties.

        Args:
            query: Original query string
            candidates: List of (concept_id, score) from initial ranking
            query_type: Expected concept type (for type mismatch penalty)

        Returns:
            Reranked list of (concept_id, adjusted_score)
        """
        if not candidates:
            return candidates

        reranked = []

        # Get parent sets for sibling detection
        parent_sets = {}
        for cid, _ in candidates:
            parents = self._ontology.direct_parents(cid)
            parent_sets[cid] = parents

        # Detect siblings
        sibling_groups = self._find_sibling_groups(candidates, parent_sets)

        for cid, score in candidates:
            adjusted = score

            # Sibling penalty: if multiple siblings in candidates
            if cid in sibling_groups:
                n_siblings = len(sibling_groups[cid])
                if n_siblings > 1:
                    # More siblings = more ambiguity = larger penalty
                    adjusted -= self._sibling_penalty * (n_siblings - 1)

            # Type mismatch penalty
            if query_type:
                concept = self._ontology.get_concept(cid)
                if concept and concept.domain != query_type:
                    adjusted -= self._type_mismatch_penalty

            reranked.append((cid, max(0.0, adjusted)))

        # Sort by adjusted score
        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked

    def _find_sibling_groups(
        self,
        candidates: List[Tuple[str, float]],
        parent_sets: Dict[str, Set[str]],
    ) -> Dict[str, Set[str]]:
        """Find groups of sibling concepts among candidates."""
        sibling_groups: Dict[str, Set[str]] = {}
        candidate_ids = {c[0] for c in candidates}

        for cid in candidate_ids:
            parents = parent_sets.get(cid, set())
            siblings = set()

            for other_cid in candidate_ids:
                if other_cid == cid:
                    continue
                other_parents = parent_sets.get(other_cid, set())
                # Siblings share at least one parent
                if parents & other_parents:
                    siblings.add(other_cid)

            if siblings:
                sibling_groups[cid] = siblings | {cid}

        return sibling_groups


# ============================================================
# Evaluation Metrics
# ============================================================

@dataclass
class EvaluationMetrics:
    """Comprehensive evaluation metrics for Entity Linking.

    Includes accuracy, calibration, latency, and error analysis.
    """
    # Accuracy metrics
    top1_accuracy: float = 0.0
    top5_accuracy: float = 0.0
    top10_accuracy: float = 0.0

    # Calibration metrics
    ece: float = 0.0  # Expected Calibration Error
    avg_confidence: float = 0.0
    avg_set_size: float = 0.0
    coverage: float = 0.0  # Empirical coverage

    # Latency metrics
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0

    # Error analysis
    n_samples: int = 0
    n_oov: int = 0  # Out-of-vocabulary
    n_ambiguous: int = 0  # Multiple plausible matches
    n_abstained: int = 0  # Abstention count

    # Slice-level accuracy
    slice_accuracy: Dict[str, float] = field(default_factory=dict)


def evaluate_matcher(
    matcher: Any,  # OntologyMatcher or ConformalMatcher
    test_data: List[Tuple[str, str]],  # (query, true_concept_id)
    slices: Optional[Dict[str, List[int]]] = None,  # slice_name -> indices
) -> EvaluationMetrics:
    """Evaluate matcher on test data.

    Args:
        matcher: Matcher to evaluate
        test_data: List of (query, true_concept_id) pairs
        slices: Optional slice definitions for error analysis

    Returns:
        EvaluationMetrics with comprehensive statistics
    """
    import time

    metrics = EvaluationMetrics(n_samples=len(test_data))

    top1_correct = 0
    top5_correct = 0
    top10_correct = 0
    confidences = []
    set_sizes = []
    latencies = []
    covered = 0

    is_conformal = hasattr(matcher, 'predict') and hasattr(matcher, 'is_calibrated')

    for query, true_cid in test_data:
        start = time.perf_counter()

        if is_conformal:
            pred_set = matcher.predict(query)
            elapsed = (time.perf_counter() - start) * 1000

            # Top-k from prediction set
            top_k_ids = [c[0] for c in pred_set.candidates[:10]]
            top1_cid = top_k_ids[0] if top_k_ids else None
            confidence = pred_set.candidates[0][1] if pred_set.candidates else 0.0

            # Coverage
            if pred_set.contains(true_cid):
                covered += 1

            # Abstention
            if pred_set.abstain:
                metrics.n_abstained += 1

            set_sizes.append(pred_set.set_size)
        else:
            result = matcher.match(query)
            elapsed = (time.perf_counter() - start) * 1000

            top1_cid = result.concept_id
            confidence = result.confidence
            top_k_ids = [top1_cid] + [a[0] for a in result.alternatives[:9]]

        latencies.append(elapsed)
        confidences.append(confidence)

        # Top-k accuracy
        if top1_cid == true_cid:
            top1_correct += 1
        if true_cid in top_k_ids[:5]:
            top5_correct += 1
        if true_cid in top_k_ids[:10]:
            top10_correct += 1

        # OOV detection
        if top1_cid is None:
            metrics.n_oov += 1

    # Compute metrics
    n = len(test_data)
    metrics.top1_accuracy = top1_correct / n if n else 0
    metrics.top5_accuracy = top5_correct / n if n else 0
    metrics.top10_accuracy = top10_correct / n if n else 0

    metrics.avg_confidence = np.mean(confidences) if confidences else 0
    metrics.avg_set_size = np.mean(set_sizes) if set_sizes else 0
    metrics.coverage = covered / n if n else 0

    latencies_arr = np.array(latencies)
    metrics.p50_latency_ms = np.percentile(latencies_arr, 50) if latencies else 0
    metrics.p95_latency_ms = np.percentile(latencies_arr, 95) if latencies else 0
    metrics.p99_latency_ms = np.percentile(latencies_arr, 99) if latencies else 0

    # Slice-level evaluation
    if slices:
        for slice_name, indices in slices.items():
            slice_correct = sum(
                1 for i in indices
                if i < n and matcher.match(test_data[i][0]).concept_id == test_data[i][1]
            )
            metrics.slice_accuracy[slice_name] = slice_correct / len(indices) if indices else 0

    return metrics


def print_evaluation_report(metrics: EvaluationMetrics) -> str:
    """Format evaluation metrics as a report."""
    lines = [
        "=" * 60,
        "Entity Linking Evaluation Report",
        "=" * 60,
        "",
        "--- Accuracy ---",
        f"Top-1 Accuracy: {metrics.top1_accuracy:.2%}",
        f"Top-5 Accuracy: {metrics.top5_accuracy:.2%}",
        f"Top-10 Accuracy: {metrics.top10_accuracy:.2%}",
        "",
        "--- Calibration ---",
        f"ECE: {metrics.ece:.4f}",
        f"Avg Confidence: {metrics.avg_confidence:.3f}",
        f"Avg Set Size: {metrics.avg_set_size:.2f}",
        f"Coverage: {metrics.coverage:.2%}",
        "",
        "--- Latency ---",
        f"p50: {metrics.p50_latency_ms:.2f}ms",
        f"p95: {metrics.p95_latency_ms:.2f}ms",
        f"p99: {metrics.p99_latency_ms:.2f}ms",
        "",
        "--- Error Analysis ---",
        f"Total Samples: {metrics.n_samples}",
        f"OOV (not matched): {metrics.n_oov}",
        f"Ambiguous: {metrics.n_ambiguous}",
        f"Abstained: {metrics.n_abstained}",
    ]

    if metrics.slice_accuracy:
        lines.extend(["", "--- Slice Accuracy ---"])
        for slice_name, acc in metrics.slice_accuracy.items():
            lines.append(f"  {slice_name}: {acc:.2%}")

    lines.append("=" * 60)
    return "\n".join(lines)
