"""Concept Mapper: Entity Linking / Concept Normalization Layer.

Responsible for answering: "What standardized concept does this input represent?"

This module is SEPARATE from Policy/Conformance decisions. It only identifies
and normalizes concepts without making clinical judgments about whether
actions are allowed, forbidden, or mandatory in a given context.

Architecture:
    Raw Input (action string, drug name, etc.)
           ↓
    ┌─────────────────────────────────────────┐
    │           ConceptMapper                  │
    │  ┌───────────┐  ┌─────────────────────┐ │
    │  │ Rule-based │→│ Neural Embeddings   │ │
    │  │ (Exact/Syn)│  │ (SapBERT/FAISS)    │ │
    │  └───────────┘  └─────────────────────┘ │
    │           ↓                 ↓            │
    │      ConformalMatcher (Calibrated)      │
    │           ↓                              │
    │      SiblingReranker (Hard negatives)   │
    └─────────────────────────────────────────┘
           ↓
    MappingResult (concept_id, confidence, alternatives, uncertainty)

References:
- Sung et al. (2020): Biomedical Entity Linking
- Fisch et al. (2022): Conformal Risk Control
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .concept import (
    AbstractionLevel,
    ClinicalConcept,
    MatchResult,
)
from .conformal_matcher import (
    ConformalConfig,
    ConformalMatcher,
    PredictionSet,
    SiblingReranker,
)

logger = logging.getLogger(__name__)


class MappingStrategy(str, Enum):
    """Strategy used for concept mapping."""
    EXACT = "exact"           # Direct concept_id match
    SYNONYM = "synonym"       # Known synonym match
    SUBSUMPTION = "subsumption"  # Parent/child relationship
    NEURAL = "neural"         # Neural embedding similarity
    CONFORMAL = "conformal"   # Conformal prediction set
    UNKNOWN = "unknown"       # No confident mapping


class UncertaintyLevel(str, Enum):
    """Uncertainty level of mapping result."""
    LOW = "low"         # Singleton prediction set, high confidence
    MEDIUM = "medium"   # Small set (2-3), moderate confidence
    HIGH = "high"       # Large set or low confidence
    ABSTAIN = "abstain" # Too uncertain to map


@dataclass
class MappingResult:
    """Result of concept mapping (entity linking).

    Note: This only identifies WHAT concept something is.
    It does NOT determine if the concept is allowed/forbidden.
    That is the job of Policy/Conformance layer.

    Attributes:
        query: Original input string
        concept_id: Best matching concept ID (or None if abstained)
        confidence: Confidence score [0, 1]
        strategy: How the mapping was determined
        uncertainty: Uncertainty level of the mapping
        prediction_set: Full conformal prediction set (if available)
        alternatives: Alternative concept mappings
        metadata: Additional mapping information
    """
    query: str
    concept_id: Optional[str]
    confidence: float
    strategy: MappingStrategy
    uncertainty: UncertaintyLevel
    prediction_set: Optional[PredictionSet] = None
    alternatives: List[Tuple[str, float]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_confident(self) -> bool:
        """Whether the mapping is confident (low uncertainty)."""
        return self.uncertainty == UncertaintyLevel.LOW

    @property
    def is_ambiguous(self) -> bool:
        """Whether the mapping is ambiguous (multiple plausible matches)."""
        return self.uncertainty in [UncertaintyLevel.MEDIUM, UncertaintyLevel.HIGH]

    @property
    def did_abstain(self) -> bool:
        """Whether the mapper abstained from mapping."""
        return self.uncertainty == UncertaintyLevel.ABSTAIN

    def get_all_candidates(self) -> List[str]:
        """Get all candidate concept IDs (best + alternatives)."""
        candidates = []
        if self.concept_id:
            candidates.append(self.concept_id)
        candidates.extend(c[0] for c in self.alternatives)
        return candidates


@dataclass
class MapperConfig:
    """Configuration for ConceptMapper.

    Attributes:
        enable_exact_match: Enable direct concept_id matching
        enable_synonym_match: Enable synonym-based matching
        enable_neural_fallback: Enable neural embedding fallback
        enable_conformal: Enable conformal prediction sets
        enable_sibling_reranking: Enable sibling-based reranking
        confidence_threshold: Minimum confidence for single mapping
        ambiguity_threshold: Confidence gap for ambiguity detection
        conformal_config: Configuration for conformal prediction
    """
    enable_exact_match: bool = True
    enable_synonym_match: bool = True
    enable_neural_fallback: bool = True
    enable_conformal: bool = True
    enable_sibling_reranking: bool = True
    confidence_threshold: float = 0.75
    ambiguity_threshold: float = 0.1  # If gap to #2 < this, ambiguous
    conformal_config: ConformalConfig = field(default_factory=ConformalConfig)


class ConceptMapper:
    """Entity Linking / Concept Normalization Layer.

    Responsible only for identifying and normalizing concepts.
    Does NOT make clinical policy decisions (allowed/forbidden/mandatory).

    Example:
        mapper = ConceptMapper(ontology, matcher, config)

        # Calibrate on held-out data
        mapper.calibrate(calibration_data)

        # Map a concept
        result = mapper.map("start norepinephrine infusion")

        # result.concept_id = "VASOPRESSOR_NOREPINEPHRINE"
        # result.confidence = 0.92
        # result.uncertainty = UncertaintyLevel.LOW

        # Policy decisions are made elsewhere:
        # policy.is_allowed(result.concept_id, patient_context)  # Policy layer
    """

    def __init__(
        self,
        ontology: Any,  # ClinicalOntology
        base_matcher: Any,  # OntologyMatcher
        config: Optional[MapperConfig] = None,
    ):
        self._ontology = ontology
        self._base_matcher = base_matcher
        self._config = config or MapperConfig()

        # Initialize conformal matcher if enabled
        self._conformal_matcher: Optional[ConformalMatcher] = None
        if self._config.enable_conformal:
            self._conformal_matcher = ConformalMatcher(
                base_matcher,
                self._config.conformal_config,
            )

        # Initialize sibling reranker if enabled
        self._sibling_reranker: Optional[SiblingReranker] = None
        if self._config.enable_sibling_reranking:
            self._sibling_reranker = SiblingReranker(ontology)

        self._is_calibrated = False

    @property
    def is_calibrated(self) -> bool:
        """Whether the mapper has been calibrated."""
        return self._is_calibrated

    def calibrate(
        self,
        calibration_data: List[Tuple[str, str]],  # (query, true_concept_id)
    ) -> Dict[str, Any]:
        """Calibrate the mapper on held-out data.

        This calibrates the conformal prediction layer for
        coverage guarantees.

        Args:
            calibration_data: List of (query, true_concept_id) pairs

        Returns:
            Calibration statistics
        """
        if not self._conformal_matcher:
            logger.warning("Conformal matcher not enabled, skipping calibration")
            return {"status": "skipped", "reason": "conformal disabled"}

        result = self._conformal_matcher.calibrate(calibration_data)
        self._is_calibrated = True

        return {
            "status": "success",
            "threshold": result.threshold,
            "n_calibration": result.n_calibration,
            "empirical_coverage": result.empirical_coverage,
            "avg_set_size": result.avg_set_size,
            "ece": result.ece,
        }

    def map(
        self,
        query: str,
        expected_type: Optional[str] = None,  # "medication", "lab", "procedure"
    ) -> MappingResult:
        """Map input to standardized concept.

        This ONLY identifies what concept the input represents.
        It does NOT make policy decisions about whether the
        concept is allowed/forbidden/mandatory.

        Args:
            query: Input string (action name, drug name, etc.)
            expected_type: Expected concept type for disambiguation

        Returns:
            MappingResult with concept identification
        """
        if not query or not query.strip():
            return MappingResult(
                query=query,
                concept_id=None,
                confidence=0.0,
                strategy=MappingStrategy.UNKNOWN,
                uncertainty=UncertaintyLevel.ABSTAIN,
            )

        # Step 1: Try rule-based matching first (exact, synonym)
        rule_result = self._try_rule_based(query)
        if rule_result and rule_result.confidence >= self._config.confidence_threshold:
            return rule_result

        # Step 2: Try conformal prediction for uncertainty quantification
        if self._conformal_matcher and self._is_calibrated:
            conformal_result = self._try_conformal(query, expected_type)
            if conformal_result:
                return conformal_result

        # Step 3: Fallback to base matcher
        base_result = self._base_matcher.match(query)

        if base_result.matched:
            alternatives = list(base_result.alternatives)

            # Apply sibling reranking
            if self._sibling_reranker and alternatives:
                candidates = [(base_result.concept_id, base_result.confidence)]
                candidates.extend(alternatives)
                reranked = self._sibling_reranker.rerank(query, candidates, expected_type)
                if reranked:
                    best_cid, best_score = reranked[0]
                    alternatives = reranked[1:]

                    return MappingResult(
                        query=query,
                        concept_id=best_cid,
                        confidence=best_score,
                        strategy=self._map_strategy(base_result.strategy),
                        uncertainty=self._determine_uncertainty(best_score, alternatives),
                        alternatives=alternatives,
                    )

            return MappingResult(
                query=query,
                concept_id=base_result.concept_id,
                confidence=base_result.confidence,
                strategy=self._map_strategy(base_result.strategy),
                uncertainty=self._determine_uncertainty(
                    base_result.confidence, alternatives
                ),
                alternatives=alternatives,
            )

        # No match found
        return MappingResult(
            query=query,
            concept_id=None,
            confidence=0.0,
            strategy=MappingStrategy.UNKNOWN,
            uncertainty=UncertaintyLevel.ABSTAIN,
        )

    def map_batch(
        self,
        queries: List[str],
        expected_types: Optional[List[str]] = None,
    ) -> List[MappingResult]:
        """Map multiple inputs to concepts.

        Args:
            queries: List of input strings
            expected_types: Optional list of expected types per query

        Returns:
            List of MappingResult
        """
        if expected_types is None:
            expected_types = [None] * len(queries)

        return [
            self.map(q, t) for q, t in zip(queries, expected_types)
        ]

    def get_mapping_uncertainty(self, query: str) -> Dict[str, Any]:
        """Get detailed uncertainty analysis for a query.

        Useful for debugging and understanding mapper behavior.
        """
        result = self.map(query)

        uncertainty_info = {
            "query": query,
            "concept_id": result.concept_id,
            "confidence": result.confidence,
            "strategy": result.strategy.value,
            "uncertainty_level": result.uncertainty.value,
            "is_confident": result.is_confident,
            "is_ambiguous": result.is_ambiguous,
            "did_abstain": result.did_abstain,
            "n_alternatives": len(result.alternatives),
            "alternatives": result.alternatives[:5],
        }

        if result.prediction_set:
            uncertainty_info["prediction_set"] = {
                "set_size": result.prediction_set.set_size,
                "threshold": result.prediction_set.threshold,
                "coverage_guarantee": result.prediction_set.coverage,
                "concept_ids": result.prediction_set.concept_ids,
            }

        return uncertainty_info

    def _try_rule_based(self, query: str) -> Optional[MappingResult]:
        """Try rule-based matching (exact, synonym)."""
        if not self._config.enable_exact_match and not self._config.enable_synonym_match:
            return None

        result = self._base_matcher.match(query)

        if result.matched and result.strategy in ["exact", "synonym"]:
            return MappingResult(
                query=query,
                concept_id=result.concept_id,
                confidence=result.confidence,
                strategy=MappingStrategy.EXACT if result.strategy == "exact" else MappingStrategy.SYNONYM,
                uncertainty=UncertaintyLevel.LOW,  # Rule-based is confident
                alternatives=list(result.alternatives),
            )

        return None

    def _try_conformal(
        self,
        query: str,
        expected_type: Optional[str],
    ) -> Optional[MappingResult]:
        """Try conformal prediction with calibrated threshold."""
        if not self._conformal_matcher:
            return None

        pred_set = self._conformal_matcher.predict(query)

        # Abstain if set is empty or flagged
        if pred_set.is_empty or pred_set.abstain:
            return MappingResult(
                query=query,
                concept_id=None,
                confidence=0.0,
                strategy=MappingStrategy.CONFORMAL,
                uncertainty=UncertaintyLevel.ABSTAIN,
                prediction_set=pred_set,
            )

        # Get best candidate
        candidates = pred_set.candidates
        if not candidates:
            return None

        best_cid, best_score, _ = candidates[0]
        alternatives = [(c[0], c[1]) for c in candidates[1:pred_set.set_size]]

        # Apply sibling reranking
        if self._sibling_reranker and len(candidates) > 1:
            rerank_input = [(c[0], c[1]) for c in candidates[:pred_set.set_size]]
            reranked = self._sibling_reranker.rerank(query, rerank_input, expected_type)
            if reranked:
                best_cid, best_score = reranked[0]
                alternatives = reranked[1:]

        # Determine uncertainty based on set size
        if pred_set.is_singleton:
            uncertainty = UncertaintyLevel.LOW
        elif pred_set.set_size <= 3:
            uncertainty = UncertaintyLevel.MEDIUM
        else:
            uncertainty = UncertaintyLevel.HIGH

        return MappingResult(
            query=query,
            concept_id=best_cid,
            confidence=best_score,
            strategy=MappingStrategy.CONFORMAL,
            uncertainty=uncertainty,
            prediction_set=pred_set,
            alternatives=alternatives,
        )

    def _determine_uncertainty(
        self,
        confidence: float,
        alternatives: List[Tuple[str, float]],
    ) -> UncertaintyLevel:
        """Determine uncertainty level from confidence and alternatives."""
        if confidence >= self._config.confidence_threshold:
            # Check for close alternatives (ambiguity)
            if alternatives:
                gap = confidence - alternatives[0][1]
                if gap < self._config.ambiguity_threshold:
                    return UncertaintyLevel.MEDIUM
            return UncertaintyLevel.LOW

        elif confidence >= 0.5:
            return UncertaintyLevel.MEDIUM

        else:
            return UncertaintyLevel.HIGH

    def _map_strategy(self, strategy_str: str) -> MappingStrategy:
        """Map strategy string to MappingStrategy enum."""
        mapping = {
            "exact": MappingStrategy.EXACT,
            "synonym": MappingStrategy.SYNONYM,
            "subsumption": MappingStrategy.SUBSUMPTION,
            "fuzzy": MappingStrategy.NEURAL,
            "neural": MappingStrategy.NEURAL,
        }
        return mapping.get(strategy_str, MappingStrategy.UNKNOWN)


# ============================================================
# Utility Functions
# ============================================================

def create_mapper(
    ontology: Any,
    matcher: Any,
    enable_conformal: bool = True,
    enable_sibling_reranking: bool = True,
) -> ConceptMapper:
    """Factory function to create a ConceptMapper.

    Args:
        ontology: ClinicalOntology instance
        matcher: OntologyMatcher instance
        enable_conformal: Enable conformal prediction
        enable_sibling_reranking: Enable sibling-based reranking

    Returns:
        Configured ConceptMapper
    """
    config = MapperConfig(
        enable_conformal=enable_conformal,
        enable_sibling_reranking=enable_sibling_reranking,
    )
    return ConceptMapper(ontology, matcher, config)
