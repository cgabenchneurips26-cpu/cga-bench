"""
Ablation Study Framework for Ontology Mapping Strategies

This module provides tools for evaluating different mapping strategy configurations
and generating ablation reports for CGA-Bench.

Ablation Configurations:
  1. EXACT only
  2. +SYNONYM (EXACT + SYNONYM)
  3. +SUBSUMPTION (+ IS-A hierarchy)
  4. +FUZZY (+ Jaccard similarity)
  5. +NEURAL (full hybrid with SapBERT fallback)

Metrics:
  - Precision@1: Fraction of top-1 predictions that are correct
  - Recall@k: Fraction of gold labels found in top-k predictions
  - MRR: Mean Reciprocal Rank of correct label

Reference:
  - Entity Linking evaluation metrics follow BioSyn, SapBERT conventions
  - Conformal metrics follow Vovk et al. (2005)
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set

logger = logging.getLogger(__name__)


class AblationStrategy(str, Enum):
    """Ablation strategy configurations."""
    EXACT_ONLY = "exact_only"
    PLUS_SYNONYM = "plus_synonym"
    PLUS_SUBSUMPTION = "plus_subsumption"
    PLUS_FUZZY = "plus_fuzzy"
    PLUS_NEURAL = "plus_neural"  # Full hybrid (bi-encoder)
    NEURAL_ONLY = "neural_only"  # Neural without rule-based
    TWO_STAGE = "two_stage"      # Bi-encoder + Cross-encoder reranking (P7 SOTA)


@dataclass
class GoldInstance:
    """A single gold standard mapping instance."""
    query: str
    gold_concept_id: str
    gold_display: str
    domain: str
    difficulty: str = "normal"  # easy, normal, hard
    category: str = "action"    # action, drug, lab, etc.
    source: str = "cga_bench"   # cga_bench, agentclinic, medchain, etc.
    notes: str = ""


@dataclass
class PredictionResult:
    """Result of a single prediction."""
    query: str
    gold_concept_id: str
    predicted_concept_id: Optional[str]
    predicted_rank: int  # 0 if not found
    similarity: float
    strategy_used: str
    latency_ms: float
    is_correct: bool
    alternatives: List[Tuple[str, float]] = field(default_factory=list)

    # Two-stage specific fields (P7)
    bi_encoder_top1: Optional[str] = None        # Bi-encoder's top-1 before reranking
    bi_encoder_score: float = 0.0                # Bi-encoder similarity
    cross_encoder_score: float = 0.0             # Cross-encoder score
    rank_change: int = 0                         # How much rank changed (+ = improved)
    rerank_corrected: bool = False               # Whether CE corrected BI error


@dataclass
class AblationMetrics:
    """Metrics for a single ablation configuration."""
    strategy: str
    total_queries: int
    precision_at_1: float
    precision_at_3: float
    precision_at_5: float
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float  # Mean Reciprocal Rank
    mean_latency_ms: float
    p95_latency_ms: float
    coverage_rate: float  # Fraction of queries with at least one result
    abstain_rate: float   # Fraction where we chose not to predict

    # Error breakdown
    false_positives: int
    false_negatives: int
    type_confusions: int  # Wrong semantic type

    # Two-stage specific metrics (P7)
    rank_change_rate: float = 0.0       # % of queries where CE changed top-1
    rank_improvement_rate: float = 0.0  # % of rank changes that improved result
    ce_correction_rate: float = 0.0     # % where CE corrected BI error
    avg_rank_delta: float = 0.0         # Average rank position change

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "strategy": self.strategy,
            "total_queries": self.total_queries,
            "precision": {
                "@1": round(self.precision_at_1, 4),
                "@3": round(self.precision_at_3, 4),
                "@5": round(self.precision_at_5, 4),
            },
            "recall": {
                "@1": round(self.recall_at_1, 4),
                "@3": round(self.recall_at_3, 4),
                "@5": round(self.recall_at_5, 4),
            },
            "mrr": round(self.mrr, 4),
            "latency": {
                "mean_ms": round(self.mean_latency_ms, 2),
                "p95_ms": round(self.p95_latency_ms, 2),
            },
            "coverage_rate": round(self.coverage_rate, 4),
            "abstain_rate": round(self.abstain_rate, 4),
            "errors": {
                "false_positives": self.false_positives,
                "false_negatives": self.false_negatives,
                "type_confusions": self.type_confusions,
            }
        }

        # Add two-stage metrics if applicable
        if self.rank_change_rate > 0:
            result["two_stage"] = {
                "rank_change_rate": round(self.rank_change_rate, 4),
                "rank_improvement_rate": round(self.rank_improvement_rate, 4),
                "ce_correction_rate": round(self.ce_correction_rate, 4),
                "avg_rank_delta": round(self.avg_rank_delta, 2),
            }

        return result


@dataclass
class FailureCase:
    """A documented failure case for taxonomy."""
    query: str
    gold_concept_id: str
    predicted_concept_id: Optional[str]
    failure_type: str  # "false_positive", "false_negative", "type_confusion", "sibling_confusion"
    gold_type: str
    predicted_type: str
    similarity: float
    explanation: str
    strategy: str


class AblationEvaluator:
    """
    Evaluator for mapping strategy ablation studies.

    Usage:
        evaluator = AblationEvaluator(ontology, gold_set)
        results = evaluator.run_ablation()
        report = evaluator.generate_report()

        # Two-stage comparison (P7):
        results = evaluator.run_ablation(include_two_stage=True)
    """

    def __init__(
        self,
        ontology,  # ClinicalOntology instance
        gold_set: List[GoldInstance],
        top_k: int = 5,
        use_mock_reranker: bool = False,  # For testing
    ):
        self.ontology = ontology
        self.gold_set = gold_set
        self.top_k = top_k
        self.use_mock_reranker = use_mock_reranker
        self._results: Dict[str, List[PredictionResult]] = {}
        self._metrics: Dict[str, AblationMetrics] = {}
        self._failures: List[FailureCase] = []
        self._two_stage_matcher = None

    def run_ablation(
        self,
        include_two_stage: bool = False,
        strategies: Optional[List[AblationStrategy]] = None,
    ) -> Dict[str, AblationMetrics]:
        """
        Run full ablation study across all strategy configurations.

        Args:
            include_two_stage: If True, also run two-stage (bi+CE) evaluation
            strategies: Optional list of strategies to run (default: all)

        Returns:
            Dict mapping strategy name to metrics
        """
        if strategies is None:
            strategies = [
                AblationStrategy.EXACT_ONLY,
                AblationStrategy.PLUS_SYNONYM,
                AblationStrategy.PLUS_SUBSUMPTION,
                AblationStrategy.PLUS_FUZZY,
                AblationStrategy.PLUS_NEURAL,
            ]
            if include_two_stage:
                strategies.append(AblationStrategy.TWO_STAGE)

        for strategy in strategies:
            logger.info(f"Running ablation: {strategy.value}")

            if strategy == AblationStrategy.TWO_STAGE:
                results = self._evaluate_two_stage()
            else:
                results = self._evaluate_strategy(strategy)

            self._results[strategy.value] = results
            self._metrics[strategy.value] = self._compute_metrics(strategy.value, results)

        return self._metrics

    def _evaluate_strategy(self, strategy: AblationStrategy) -> List[PredictionResult]:
        """Evaluate a single strategy configuration."""
        from .clinical_ontology import (
            OntologyMatcher,
            OntologyConfig,
            MatchStrategy,
        )

        # Configure matcher based on strategy
        config = self._get_config_for_strategy(strategy)
        matcher = OntologyMatcher(self.ontology, config)

        results = []
        for instance in self.gold_set:
            start_time = time.perf_counter()

            # Get match
            match_result = matcher.match(instance.query)
            latency_ms = (time.perf_counter() - start_time) * 1000

            if match_result and match_result.matched_concept:
                predicted_id = match_result.matched_concept.concept_id
                similarity = match_result.confidence
                strategy_used = match_result.strategy

                # Check if gold is in alternatives (case-insensitive comparison)
                gold_lower = instance.gold_concept_id.lower()
                pred_lower = predicted_id.lower()
                rank = 1 if pred_lower == gold_lower else 0

                if rank == 0 and match_result.alternatives:
                    for i, alt in enumerate(match_result.alternatives, start=2):
                        # alternatives can be tuple (concept_id, score) or concept
                        if isinstance(alt, tuple):
                            alt_id = alt[0].lower()
                        elif hasattr(alt, 'concept_id'):
                            alt_id = alt.concept_id.lower()
                        else:
                            alt_id = str(alt).lower()

                        if alt_id == gold_lower:
                            rank = i
                            break

                alternatives = match_result.alternatives or []
            else:
                predicted_id = None
                similarity = 0.0
                strategy_used = "none"
                rank = 0
                alternatives = []

            # Case-insensitive correctness check
            is_correct = (
                predicted_id is not None and
                predicted_id.lower() == instance.gold_concept_id.lower()
            )

            result = PredictionResult(
                query=instance.query,
                gold_concept_id=instance.gold_concept_id,
                predicted_concept_id=predicted_id,
                predicted_rank=rank,
                similarity=similarity,
                strategy_used=strategy_used,
                latency_ms=latency_ms,
                is_correct=is_correct,
                alternatives=alternatives,
            )
            results.append(result)

            # Track failures
            if not result.is_correct:
                self._record_failure(instance, result, strategy.value)

        return results

    def _evaluate_two_stage(self) -> List[PredictionResult]:
        """Evaluate two-stage entity linking (bi-encoder + cross-encoder).

        This implements P7: Cross-encoder Reranking for improved precision.

        Returns:
            List of PredictionResult with two-stage specific fields populated.
        """
        from .cross_encoder_reranker import (
            TwoStageMatcher,
            RerankerConfig,
            MockCrossEncoderReranker,
            CrossEncoderReranker,
            get_reranker,
        )
        from .neural_embedder import (
            NeuralEmbedder,
            MockNeuralEmbedder,
            EmbedderConfig,
        )

        # Build two-stage matcher if not already created
        if self._two_stage_matcher is None:
            self._two_stage_matcher = self._build_two_stage_matcher()

        matcher = self._two_stage_matcher
        results = []

        for instance in self.gold_set:
            start_time = time.perf_counter()

            # Get two-stage match
            result = matcher.match(
                instance.query,
                top_k=self.top_k,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000

            if result and result.concept_id:
                predicted_id = result.concept_id
                similarity = result.cross_encoder_score
                bi_score = result.bi_encoder_score

                # Case-insensitive gold comparison
                gold_lower = instance.gold_concept_id.lower()

                # Check if gold is in all_candidates (case-insensitive)
                rank = 0
                for i, (cid, ce_score, bi_score_alt) in enumerate(result.all_candidates, start=1):
                    if cid.lower() == gold_lower:
                        rank = i
                        break

                # Determine rank change
                rank_change = result.rank_change

                # Check if CE corrected BI error
                bi_top1 = result.all_candidates[0][0] if result.all_candidates else None
                # Get original BI order (before CE reranking) from bi_encoder_score
                bi_sorted = sorted(result.all_candidates, key=lambda x: x[2], reverse=True)
                bi_original_top1 = bi_sorted[0][0] if bi_sorted else None

                rerank_corrected = (
                    predicted_id.lower() == gold_lower and
                    (bi_original_top1 is None or bi_original_top1.lower() != gold_lower)
                )

                alternatives = [(cid, score) for cid, score, _ in result.all_candidates[1:]]
            else:
                predicted_id = None
                similarity = 0.0
                bi_score = 0.0
                rank = 0
                rank_change = 0
                rerank_corrected = False
                alternatives = []
                bi_original_top1 = None

            # Case-insensitive correctness check
            is_correct = (
                predicted_id is not None and
                predicted_id.lower() == instance.gold_concept_id.lower()
            )

            pred_result = PredictionResult(
                query=instance.query,
                gold_concept_id=instance.gold_concept_id,
                predicted_concept_id=predicted_id,
                predicted_rank=rank,
                similarity=similarity,
                strategy_used="two_stage",
                latency_ms=latency_ms,
                is_correct=is_correct,
                alternatives=alternatives,
                bi_encoder_top1=bi_original_top1,
                bi_encoder_score=bi_score,
                cross_encoder_score=similarity,
                rank_change=rank_change,
                rerank_corrected=rerank_corrected,
            )
            results.append(pred_result)

            # Track failures
            if not pred_result.is_correct:
                self._record_failure(instance, pred_result, "two_stage")

        return results

    def _build_two_stage_matcher(self):
        """Build the TwoStageMatcher with bi-encoder and cross-encoder."""
        from .cross_encoder_reranker import (
            TwoStageMatcher,
            RerankerConfig,
            MockCrossEncoderReranker,
            CrossEncoderReranker,
            get_reranker,
        )
        from .neural_embedder import (
            NeuralEmbedder,
            MockNeuralEmbedder,
            EmbedderConfig,
        )

        # Create bi-encoder (use MockNeuralEmbedder for testing)
        if self.use_mock_reranker:
            bi_encoder = MockNeuralEmbedder(EmbedderConfig(similarity_threshold=0.3))
        else:
            bi_encoder = NeuralEmbedder(EmbedderConfig(similarity_threshold=0.3))

        # Build concept index from ontology
        concepts = []
        for concept in self.ontology.concepts.values():
            concept_id = concept.concept_id
            display = concept.display if hasattr(concept, 'display') else concept_id
            synonyms = list(concept.synonyms) if hasattr(concept, 'synonyms') else []
            concepts.append((concept_id, display, synonyms))

        bi_encoder.build_index(concepts)

        # Create cross-encoder reranker
        ce_config = RerankerConfig(
            max_candidates=20,
            enable_type_boost=True,
            type_boost_weight=0.1,
        )
        reranker = get_reranker(config=ce_config, use_mock=self.use_mock_reranker)

        # Create two-stage matcher (concept_metadata will be built during warm_up)
        matcher = TwoStageMatcher(bi_encoder, reranker, concept_metadata=None)
        matcher.warm_up(concepts)

        return matcher

    def _get_config_for_strategy(self, strategy: AblationStrategy):
        """Get OntologyConfig for a given ablation strategy."""
        from .clinical_ontology import OntologyConfig

        # Base config - minimal
        config = OntologyConfig(
            enable_neural_fallback=False,
            fuzzy_threshold=0.7,
            neural_similarity_threshold=0.75,
            enable_mandatory_subsumption=False,
        )

        if strategy == AblationStrategy.EXACT_ONLY:
            pass  # Already minimal

        elif strategy == AblationStrategy.PLUS_SYNONYM:
            pass  # Synonym matching is built into exact/concept lookup

        elif strategy == AblationStrategy.PLUS_SUBSUMPTION:
            config.enable_mandatory_subsumption = True

        elif strategy == AblationStrategy.PLUS_FUZZY:
            config.enable_mandatory_subsumption = True
            config.fuzzy_threshold = 0.65  # Enable fuzzy via lower threshold

        elif strategy == AblationStrategy.PLUS_NEURAL:
            config.enable_mandatory_subsumption = True
            config.fuzzy_threshold = 0.65
            config.enable_neural_fallback = True

        elif strategy == AblationStrategy.NEURAL_ONLY:
            config.enable_neural_fallback = True
            # Skip rule-based strategies

        return config

    def _compute_metrics(
        self,
        strategy_name: str,
        results: List[PredictionResult]
    ) -> AblationMetrics:
        """Compute metrics from prediction results."""
        if not results:
            return AblationMetrics(
                strategy=strategy_name,
                total_queries=0,
                precision_at_1=0, precision_at_3=0, precision_at_5=0,
                recall_at_1=0, recall_at_3=0, recall_at_5=0,
                mrr=0, mean_latency_ms=0, p95_latency_ms=0,
                coverage_rate=0, abstain_rate=1.0,
                false_positives=0, false_negatives=0, type_confusions=0,
            )

        n = len(results)

        # Precision@k and Recall@k
        correct_at_1 = sum(1 for r in results if r.predicted_rank == 1)
        correct_at_3 = sum(1 for r in results if 0 < r.predicted_rank <= 3)
        correct_at_5 = sum(1 for r in results if 0 < r.predicted_rank <= 5)

        precision_at_1 = correct_at_1 / n
        precision_at_3 = correct_at_3 / n
        precision_at_5 = correct_at_5 / n

        # For entity linking, recall@k = precision@k (one gold per query)
        recall_at_1 = precision_at_1
        recall_at_3 = precision_at_3
        recall_at_5 = precision_at_5

        # MRR
        reciprocal_ranks = []
        for r in results:
            if r.predicted_rank > 0:
                reciprocal_ranks.append(1.0 / r.predicted_rank)
            else:
                reciprocal_ranks.append(0.0)
        mrr = sum(reciprocal_ranks) / n if n > 0 else 0

        # Latency
        latencies = [r.latency_ms for r in results]
        mean_latency = sum(latencies) / n
        sorted_latencies = sorted(latencies)
        p95_latency = sorted_latencies[int(n * 0.95)] if n >= 20 else sorted_latencies[-1]

        # Coverage and abstain
        has_prediction = sum(1 for r in results if r.predicted_concept_id is not None)
        coverage_rate = has_prediction / n
        abstain_rate = 1.0 - coverage_rate

        # Error breakdown
        false_positives = sum(1 for r in results if r.predicted_concept_id and not r.is_correct)
        false_negatives = sum(1 for r in results if not r.predicted_concept_id)
        type_confusions = self._count_type_confusions(results)

        # Two-stage specific metrics (P7)
        rank_change_rate = 0.0
        rank_improvement_rate = 0.0
        ce_correction_rate = 0.0
        avg_rank_delta = 0.0

        if strategy_name == "two_stage":
            rank_changed = [r for r in results if r.rank_change != 0]
            rank_change_rate = len(rank_changed) / n if n > 0 else 0.0

            # Rank improvement: positive rank_change means gold moved up
            rank_improved = [r for r in rank_changed if r.rank_change > 0]
            rank_improvement_rate = len(rank_improved) / len(rank_changed) if rank_changed else 0.0

            # CE correction rate: when CE fixed BI's error
            ce_corrections = [r for r in results if r.rerank_corrected]
            ce_correction_rate = len(ce_corrections) / n if n > 0 else 0.0

            # Average rank delta (absolute value)
            rank_deltas = [abs(r.rank_change) for r in rank_changed]
            avg_rank_delta = sum(rank_deltas) / len(rank_deltas) if rank_deltas else 0.0

        return AblationMetrics(
            strategy=strategy_name,
            total_queries=n,
            precision_at_1=precision_at_1,
            precision_at_3=precision_at_3,
            precision_at_5=precision_at_5,
            recall_at_1=recall_at_1,
            recall_at_3=recall_at_3,
            recall_at_5=recall_at_5,
            mrr=mrr,
            mean_latency_ms=mean_latency,
            p95_latency_ms=p95_latency,
            coverage_rate=coverage_rate,
            abstain_rate=abstain_rate,
            false_positives=false_positives,
            false_negatives=false_negatives,
            type_confusions=type_confusions,
            rank_change_rate=rank_change_rate,
            rank_improvement_rate=rank_improvement_rate,
            ce_correction_rate=ce_correction_rate,
            avg_rank_delta=avg_rank_delta,
        )

    def _count_type_confusions(self, results: List[PredictionResult]) -> int:
        """Count predictions where semantic type is wrong."""
        from .neural_embedder import infer_semantic_type

        count = 0
        for r in results:
            if r.predicted_concept_id and not r.is_correct:
                gold_type = infer_semantic_type(r.gold_concept_id)
                pred_type = infer_semantic_type(r.predicted_concept_id)
                if gold_type != pred_type:
                    count += 1
        return count

    def _record_failure(
        self,
        instance: GoldInstance,
        result: PredictionResult,
        strategy: str
    ) -> None:
        """Record a failure case for taxonomy."""
        from .neural_embedder import infer_semantic_type

        gold_type = infer_semantic_type(instance.gold_concept_id).value
        pred_type = infer_semantic_type(result.predicted_concept_id).value if result.predicted_concept_id else "none"

        if result.predicted_concept_id is None:
            failure_type = "false_negative"
            explanation = "No prediction made (below threshold or no match)"
        elif gold_type != pred_type:
            failure_type = "type_confusion"
            explanation = f"Predicted {pred_type} instead of {gold_type}"
        else:
            # Check if sibling confusion
            failure_type = "false_positive"
            explanation = f"Incorrect prediction: {result.predicted_concept_id}"

        failure = FailureCase(
            query=instance.query,
            gold_concept_id=instance.gold_concept_id,
            predicted_concept_id=result.predicted_concept_id,
            failure_type=failure_type,
            gold_type=gold_type,
            predicted_type=pred_type,
            similarity=result.similarity,
            explanation=explanation,
            strategy=strategy,
        )
        self._failures.append(failure)

    def get_failures(self) -> List[FailureCase]:
        """Get all recorded failure cases."""
        return self._failures

    def generate_report(self) -> str:
        """Generate markdown ablation report."""
        lines = [
            "# Mapping Strategy Ablation Report",
            "",
            "## Summary",
            "",
            "| Strategy | P@1 | P@5 | MRR | Coverage | Latency (p95) |",
            "|----------|-----|-----|-----|----------|---------------|",
        ]

        for strategy, metrics in self._metrics.items():
            lines.append(
                f"| {strategy} | {metrics.precision_at_1:.2%} | "
                f"{metrics.precision_at_5:.2%} | {metrics.mrr:.3f} | "
                f"{metrics.coverage_rate:.2%} | {metrics.p95_latency_ms:.1f}ms |"
            )

        # Two-stage specific summary (P7)
        if "two_stage" in self._metrics:
            lines.extend([
                "",
                "## Two-Stage Entity Linking Analysis (P7)",
                "",
                "### Bi-encoder vs Two-stage Comparison",
                "",
                "| Metric | Bi-encoder | Two-stage | Δ |",
                "|--------|------------|-----------|---|",
            ])

            bi_metrics = self._metrics.get("plus_neural", self._metrics.get("neural_only"))
            ts_metrics = self._metrics["two_stage"]

            if bi_metrics:
                delta_p1 = ts_metrics.precision_at_1 - bi_metrics.precision_at_1
                delta_mrr = ts_metrics.mrr - bi_metrics.mrr
                delta_tc = bi_metrics.type_confusions - ts_metrics.type_confusions

                lines.extend([
                    f"| P@1 | {bi_metrics.precision_at_1:.2%} | {ts_metrics.precision_at_1:.2%} | {delta_p1:+.2%} |",
                    f"| MRR | {bi_metrics.mrr:.4f} | {ts_metrics.mrr:.4f} | {delta_mrr:+.4f} |",
                    f"| Type Confusions | {bi_metrics.type_confusions} | {ts_metrics.type_confusions} | {delta_tc:+d} |",
                ])

            lines.extend([
                "",
                "### Cross-Encoder Reranking Statistics",
                "",
                f"- **Rank change rate**: {ts_metrics.rank_change_rate:.2%}",
                f"  - Fraction of queries where CE changed top-1",
                f"- **Rank improvement rate**: {ts_metrics.rank_improvement_rate:.2%}",
                f"  - Fraction of rank changes that improved result",
                f"- **CE correction rate**: {ts_metrics.ce_correction_rate:.2%}",
                f"  - Fraction where CE corrected BI error",
                f"- **Avg rank delta**: {ts_metrics.avg_rank_delta:.2f}",
                f"  - Average rank position change",
                "",
            ])

        lines.extend([
            "",
            "## Detailed Metrics",
            "",
        ])

        for strategy, metrics in self._metrics.items():
            lines.extend([
                f"### {strategy}",
                "",
                f"- Total queries: {metrics.total_queries}",
                f"- Precision@1: {metrics.precision_at_1:.2%}",
                f"- Precision@3: {metrics.precision_at_3:.2%}",
                f"- Precision@5: {metrics.precision_at_5:.2%}",
                f"- MRR: {metrics.mrr:.4f}",
                f"- Coverage: {metrics.coverage_rate:.2%}",
                f"- Abstain: {metrics.abstain_rate:.2%}",
                f"- Mean latency: {metrics.mean_latency_ms:.2f}ms",
                f"- p95 latency: {metrics.p95_latency_ms:.2f}ms",
                "",
                "Error breakdown:",
                f"- False positives: {metrics.false_positives}",
                f"- False negatives: {metrics.false_negatives}",
                f"- Type confusions: {metrics.type_confusions}",
                "",
            ])

            # Add two-stage specific details
            if strategy == "two_stage":
                lines.extend([
                    "Cross-encoder reranking:",
                    f"- Rank change rate: {metrics.rank_change_rate:.2%}",
                    f"- Rank improvement rate: {metrics.rank_improvement_rate:.2%}",
                    f"- CE correction rate: {metrics.ce_correction_rate:.2%}",
                    f"- Avg rank delta: {metrics.avg_rank_delta:.2f}",
                    "",
                ])

        # Failure taxonomy
        lines.extend([
            "## Failure Case Taxonomy",
            "",
        ])

        failure_types: Dict[str, List[FailureCase]] = {}
        for f in self._failures:
            if f.failure_type not in failure_types:
                failure_types[f.failure_type] = []
            failure_types[f.failure_type].append(f)

        for ftype, cases in failure_types.items():
            lines.extend([
                f"### {ftype} ({len(cases)} cases)",
                "",
            ])
            for case in cases[:5]:  # Show first 5 examples
                lines.append(
                    f"- `{case.query}` → predicted `{case.predicted_concept_id}`, "
                    f"expected `{case.gold_concept_id}` ({case.explanation})"
                )
            if len(cases) > 5:
                lines.append(f"- ... and {len(cases) - 5} more")
            lines.append("")

        return "\n".join(lines)

    def generate_paper_table(self) -> str:
        """Generate LaTeX table for paper (Bi-encoder vs Two-stage comparison).

        Returns:
            LaTeX table string suitable for NeurIPS/ICML paper.
        """
        lines = [
            "% Bi-encoder vs Two-stage Entity Linking Comparison",
            "% Generated by CGA-Bench ablation runner",
            r"\begin{table}[h]",
            r"\centering",
            r"\caption{Two-Stage Entity Linking improves clinical action mapping.}",
            r"\label{tab:two_stage_el}",
            r"\begin{tabular}{lcccc}",
            r"\toprule",
            r"Strategy & P@1 & P@5 & MRR & Type Conf. \\",
            r"\midrule",
        ]

        # Add rows for each strategy
        for strategy, metrics in self._metrics.items():
            strategy_display = strategy.replace("_", " ").title()
            if strategy == "two_stage":
                strategy_display = r"\textbf{Two-Stage (Ours)}"

            lines.append(
                f"{strategy_display} & {metrics.precision_at_1:.1%} & "
                f"{metrics.precision_at_5:.1%} & {metrics.mrr:.3f} & "
                f"{metrics.type_confusions} \\\\"
            )

        # Add improvement row if two-stage is present
        if "two_stage" in self._metrics:
            bi_metrics = self._metrics.get("plus_neural", self._metrics.get("neural_only"))
            ts_metrics = self._metrics["two_stage"]

            if bi_metrics:
                delta_p1 = ts_metrics.precision_at_1 - bi_metrics.precision_at_1
                delta_mrr = ts_metrics.mrr - bi_metrics.mrr
                delta_tc = bi_metrics.type_confusions - ts_metrics.type_confusions

                lines.extend([
                    r"\midrule",
                    rf"$\Delta$ (vs. Bi-encoder) & {delta_p1:+.1%} & -- & {delta_mrr:+.3f} & {delta_tc:+d} \\",
                ])

        lines.extend([
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
        ])

        return "\n".join(lines)


def load_gold_set(path: Path) -> List[GoldInstance]:
    """Load gold standard mapping instances from JSONL file."""
    gold_set = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                gold_set.append(GoldInstance(**data))
    return gold_set


def save_gold_set(gold_set: List[GoldInstance], path: Path) -> None:
    """Save gold standard mapping instances to JSONL file."""
    with open(path, 'w', encoding='utf-8') as f:
        for instance in gold_set:
            f.write(json.dumps({
                "query": instance.query,
                "gold_concept_id": instance.gold_concept_id,
                "gold_display": instance.gold_display,
                "domain": instance.domain,
                "difficulty": instance.difficulty,
                "category": instance.category,
                "source": instance.source,
                "notes": instance.notes,
            }) + "\n")


def create_default_gold_set() -> List[GoldInstance]:
    """
    Create default gold standard set from CGA-Bench domains.

    This covers key mappings that should work correctly for benchmark validity.
    """
    gold_set = [
        # ===== SEPSIS DOMAIN =====
        GoldInstance(
            query="start_norepinephrine",
            gold_concept_id="start_vasopressor_norepinephrine",
            gold_display="start norepinephrine",
            domain="sepsis",
            difficulty="easy",
            category="drug",
        ),
        GoldInstance(
            query="give norepinephrine",
            gold_concept_id="start_vasopressor_norepinephrine",
            gold_display="norepinephrine",
            domain="sepsis",
            difficulty="easy",
            category="drug",
        ),
        GoldInstance(
            query="levophed",
            gold_concept_id="start_vasopressor_norepinephrine",
            gold_display="norepinephrine",
            domain="sepsis",
            difficulty="normal",
            category="drug",
            notes="Brand name to generic"
        ),
        GoldInstance(
            query="give_broad_spectrum_antibiotics",
            gold_concept_id="give_broad_spectrum_antibiotics",
            gold_display="broad spectrum antibiotics",
            domain="sepsis",
            difficulty="easy",
            category="drug",
        ),
        GoldInstance(
            query="order_lab_lactate",
            gold_concept_id="order_lab_lactate",
            gold_display="lactate",
            domain="sepsis",
            difficulty="easy",
            category="lab",
        ),
        GoldInstance(
            query="check lactate level",
            gold_concept_id="order_lab_lactate",
            gold_display="lactate",
            domain="sepsis",
            difficulty="normal",
            category="lab",
        ),
        GoldInstance(
            query="order_lab_blood_culture",
            gold_concept_id="order_lab_blood_culture",
            gold_display="blood culture",
            domain="sepsis",
            difficulty="easy",
            category="lab",
        ),
        GoldInstance(
            query="give_crystalloid_30ml_kg",
            gold_concept_id="give_crystalloid_30ml_kg",
            gold_display="crystalloid 30ml/kg",
            domain="sepsis",
            difficulty="easy",
            category="fluid",
        ),
        GoldInstance(
            query="normal saline bolus",
            gold_concept_id="give_crystalloid_30ml_kg",
            gold_display="crystalloid fluid",
            domain="sepsis",
            difficulty="normal",
            category="fluid",
        ),

        # ===== CHEST PAIN / ACS DOMAIN =====
        GoldInstance(
            query="perform_ecg",
            gold_concept_id="perform_ecg",
            gold_display="electrocardiogram",
            domain="chest_pain",
            difficulty="easy",
            category="procedure",
        ),
        GoldInstance(
            query="12_lead_ecg",
            gold_concept_id="perform_ecg",
            gold_display="electrocardiogram",
            domain="chest_pain",
            difficulty="normal",
            category="procedure",
        ),
        GoldInstance(
            query="order_lab_troponin",
            gold_concept_id="order_lab_troponin",
            gold_display="troponin",
            domain="chest_pain",
            difficulty="easy",
            category="lab",
        ),
        GoldInstance(
            query="hs-troponin",
            gold_concept_id="order_lab_troponin",
            gold_display="troponin",
            domain="chest_pain",
            difficulty="normal",
            category="lab",
            notes="High-sensitivity variant"
        ),
        GoldInstance(
            query="give_aspirin_loading",
            gold_concept_id="give_aspirin_loading",
            gold_display="aspirin loading dose",
            domain="chest_pain",
            difficulty="easy",
            category="drug",
        ),
        GoldInstance(
            query="aspirin 325mg",
            gold_concept_id="give_aspirin_loading",
            gold_display="aspirin loading",
            domain="chest_pain",
            difficulty="normal",
            category="drug",
        ),
        GoldInstance(
            query="activate_cath_lab",
            gold_concept_id="activate_cath_lab",
            gold_display="activate cath lab",
            domain="chest_pain",
            difficulty="easy",
            category="procedure",
        ),
        GoldInstance(
            query="give_nitroglycerin",
            gold_concept_id="give_nitroglycerin",
            gold_display="nitroglycerin",
            domain="chest_pain",
            difficulty="easy",
            category="drug",
        ),
        GoldInstance(
            query="check_right_sided_ecg_v4r",
            gold_concept_id="check_right_sided_ecg_v4r",
            gold_display="right-sided ECG V4R",
            domain="chest_pain",
            difficulty="normal",
            category="procedure",
        ),

        # ===== AKI DOMAIN =====
        GoldInstance(
            query="order_lab_creatinine",
            gold_concept_id="order_lab_creatinine",
            gold_display="creatinine",
            domain="aki",
            difficulty="easy",
            category="lab",
        ),
        GoldInstance(
            query="check creatinine",
            gold_concept_id="order_lab_creatinine",
            gold_display="creatinine",
            domain="aki",
            difficulty="easy",
            category="lab",
        ),
        GoldInstance(
            query="order_lab_bmp",
            gold_concept_id="order_lab_bmp",
            gold_display="basic metabolic panel",
            domain="aki",
            difficulty="easy",
            category="lab",
        ),
        GoldInstance(
            query="discontinue_nephrotoxic_medications",
            gold_concept_id="discontinue_nephrotoxic_medications",
            gold_display="stop nephrotoxins",
            domain="aki",
            difficulty="normal",
            category="drug",
        ),

        # ===== DKA DOMAIN =====
        GoldInstance(
            query="start_insulin_infusion",
            gold_concept_id="start_insulin_infusion",
            gold_display="insulin infusion",
            domain="dka",
            difficulty="easy",
            category="drug",
        ),
        GoldInstance(
            query="order_lab_glucose",
            gold_concept_id="order_lab_glucose",
            gold_display="glucose",
            domain="dka",
            difficulty="easy",
            category="lab",
        ),
        GoldInstance(
            query="order_abg",
            gold_concept_id="order_abg",
            gold_display="arterial blood gas",
            domain="dka",
            difficulty="normal",
            category="lab",
        ),

        # ===== STROKE DOMAIN =====
        GoldInstance(
            query="assess_nihss",
            gold_concept_id="assess_nihss",
            gold_display="NIHSS assessment",
            domain="stroke",
            difficulty="easy",
            category="assessment",
        ),
        GoldInstance(
            query="order_ct_head",
            gold_concept_id="order_ct_head",
            gold_display="CT head",
            domain="stroke",
            difficulty="easy",
            category="imaging",
        ),
        GoldInstance(
            query="give_alteplase_0.9mg_kg",
            gold_concept_id="give_alteplase_0.9mg_kg",
            gold_display="alteplase (tPA)",
            domain="stroke",
            difficulty="normal",
            category="drug",
        ),
        GoldInstance(
            query="tPA",
            gold_concept_id="give_alteplase_0.9mg_kg",
            gold_display="alteplase",
            domain="stroke",
            difficulty="normal",
            category="drug",
            notes="Abbreviation to full name"
        ),

        # ===== HEART FAILURE DOMAIN =====
        GoldInstance(
            query="initiate_ace_or_arb_or_arni",
            gold_concept_id="initiate_ace_or_arb_or_arni",
            gold_display="ACE/ARB/ARNI",
            domain="heart_failure",
            difficulty="normal",
            category="drug",
        ),
        GoldInstance(
            query="give_entresto",
            gold_concept_id="initiate_ace_or_arb_or_arni",
            gold_display="ARNI (entresto)",
            domain="heart_failure",
            difficulty="hard",
            category="drug",
            notes="Brand name mapping"
        ),
        GoldInstance(
            query="initiate_beta_blocker",
            gold_concept_id="initiate_beta_blocker",
            gold_display="beta blocker",
            domain="heart_failure",
            difficulty="easy",
            category="drug",
        ),
        GoldInstance(
            query="order_bnp",
            gold_concept_id="order_bnp",
            gold_display="BNP",
            domain="heart_failure",
            difficulty="easy",
            category="lab",
        ),

        # ===== HARD CASES (potential confusions) =====
        GoldInstance(
            query="lactate",
            gold_concept_id="order_lab_lactate",
            gold_display="lactate",
            domain="sepsis",
            difficulty="hard",
            category="lab",
            notes="Should NOT match lactated ringers (fluid)"
        ),
        GoldInstance(
            query="vasopressor",
            gold_concept_id="start_vasopressor_norepinephrine",
            gold_display="vasopressor (norepinephrine)",
            domain="sepsis",
            difficulty="normal",
            category="drug",
            notes="Generic category to specific"
        ),
    ]

    return gold_set


def run_ablation_study(
    output_dir: Optional[Path] = None,
    include_two_stage: bool = False,
    use_mock: bool = False,
    generate_latex: bool = False,
) -> Dict[str, Any]:
    """Run ablation study and generate reports.

    This is the main CLI entrypoint for running ablation experiments.

    Args:
        output_dir: Directory to save reports (default: reports/)
        include_two_stage: Include two-stage (bi+CE) evaluation
        use_mock: Use mock embedder/reranker for testing
        generate_latex: Generate LaTeX table for paper

    Returns:
        Dict with metrics and report paths.

    Usage:
        # From command line:
        python -m cga_bench.semantic_layer.ontology.ablation --two-stage

        # From Python:
        from .ablation import run_ablation_study
        results = run_ablation_study(include_two_stage=True)
    """
    from .domain_hierarchies import build_unified_ontology

    if output_dir is None:
        output_dir = Path(__file__).parent.parent.parent / "reports"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading ontology and gold set...")

    # Load unified ontology (combines all domains)
    ontology = build_unified_ontology()

    # Get gold set
    gold_set = create_default_gold_set()
    logger.info(f"Gold set: {len(gold_set)} instances")

    # Create evaluator
    evaluator = AblationEvaluator(
        ontology=ontology,
        gold_set=gold_set,
        top_k=5,
        use_mock_reranker=use_mock,
    )

    # Run ablation
    logger.info("Running ablation study...")
    metrics = evaluator.run_ablation(include_two_stage=include_two_stage)

    # Generate markdown report
    report = evaluator.generate_report()
    report_path = output_dir / "mapping_ablation_results.md"
    with open(report_path, "w") as f:
        f.write(report)
    logger.info(f"Report saved to {report_path}")

    # Generate LaTeX table if requested
    latex_path = None
    if generate_latex and include_two_stage:
        latex_table = evaluator.generate_paper_table()
        latex_path = output_dir / "two_stage_comparison.tex"
        with open(latex_path, "w") as f:
            f.write(latex_table)
        logger.info(f"LaTeX table saved to {latex_path}")

    # Save metrics as JSON
    metrics_dict = {k: v.to_dict() for k, v in metrics.items()}
    metrics_path = output_dir / "ablation_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics_dict, f, indent=2)
    logger.info(f"Metrics saved to {metrics_path}")

    return {
        "metrics": metrics_dict,
        "report_path": str(report_path),
        "latex_path": str(latex_path) if latex_path else None,
        "metrics_path": str(metrics_path),
    }


def main():
    """CLI entrypoint for ablation study."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run ontology mapping ablation study",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic ablation (exact → synonym → subsumption → fuzzy → neural)
  python -m cga_bench.semantic_layer.ontology.ablation

  # Include two-stage entity linking (bi-encoder + cross-encoder)
  python -m cga_bench.semantic_layer.ontology.ablation --two-stage

  # Generate LaTeX table for paper
  python -m cga_bench.semantic_layer.ontology.ablation --two-stage --latex

  # Use mock for testing (fast, no GPU required)
  python -m cga_bench.semantic_layer.ontology.ablation --two-stage --mock
        """
    )

    parser.add_argument(
        "--two-stage",
        action="store_true",
        help="Include two-stage (bi-encoder + cross-encoder) evaluation (P7 SOTA)"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock embedder/reranker for testing (fast, no GPU required)"
    )
    parser.add_argument(
        "--latex",
        action="store_true",
        help="Generate LaTeX table for paper"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for reports (default: reports/)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run ablation
    output_dir = Path(args.output_dir) if args.output_dir else None
    results = run_ablation_study(
        output_dir=output_dir,
        include_two_stage=args.two_stage,
        use_mock=args.mock,
        generate_latex=args.latex,
    )

    # Print summary
    print("\n" + "=" * 60)
    print("Ablation Study Complete")
    print("=" * 60)

    if "two_stage" in results["metrics"]:
        bi_key = "plus_neural" if "plus_neural" in results["metrics"] else "neural_only"
        if bi_key in results["metrics"]:
            bi_p1 = results["metrics"][bi_key]["precision"]["@1"]
            ts_p1 = results["metrics"]["two_stage"]["precision"]["@1"]
            delta = ts_p1 - bi_p1

            print(f"\nTwo-Stage vs Bi-encoder:")
            print(f"  Bi-encoder P@1:  {bi_p1:.2%}")
            print(f"  Two-stage P@1:   {ts_p1:.2%}")
            print(f"  Improvement:     {delta:+.2%}")

            if "two_stage" in results["metrics"]:
                ts_metrics = results["metrics"]["two_stage"]["two_stage"]
                print(f"\nCross-Encoder Statistics:")
                print(f"  Rank change rate:      {ts_metrics['rank_change_rate']:.2%}")
                print(f"  CE correction rate:    {ts_metrics['ce_correction_rate']:.2%}")

    print(f"\nReports saved to:")
    print(f"  Markdown: {results['report_path']}")
    print(f"  Metrics:  {results['metrics_path']}")
    if results.get('latex_path'):
        print(f"  LaTeX:    {results['latex_path']}")


if __name__ == "__main__":
    main()
