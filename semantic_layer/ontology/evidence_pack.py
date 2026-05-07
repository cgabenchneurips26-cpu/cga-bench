"""Evidence Pack Generator for Two-Stage Entity Linking Paper.

Generates comprehensive results for paper submission including:
1. Bootstrap CI for P@1/MRR/Recall@k
2. Rerank K sweep (5/10/20/50) with latency curves
3. Error decomposition (candidate failure vs rerank failure)
4. Cost/latency metrics (warm-up, p50/p95, GPU memory)

Usage:
    PYTHONPATH=. python -m cga_bench.semantic_layer.ontology.evidence_pack

Reference:
    - BioNLP 2025: Multi-candidate cross-encoder acceleration
    - ANGEL (ACL 2025): Hard negative training for BioEL
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import random

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BootstrapResult:
    """Bootstrap confidence interval result."""
    mean: float
    std: float
    ci_lower: float  # 2.5th percentile
    ci_upper: float  # 97.5th percentile
    n_bootstrap: int = 1000

    def to_dict(self) -> Dict[str, float]:
        return {
            "mean": round(self.mean, 4),
            "std": round(self.std, 4),
            "ci_lower": round(self.ci_lower, 4),
            "ci_upper": round(self.ci_upper, 4),
        }

    def __str__(self) -> str:
        return f"{self.mean:.2%} ± {self.std:.2%} (95% CI: [{self.ci_lower:.2%}, {self.ci_upper:.2%}])"


@dataclass
class ErrorDecomposition:
    """Error decomposition for two-stage EL.

    Distinguishes between:
    1. Candidate generation failure: Gold not in bi-encoder top-K
    2. Rerank failure: Gold in top-K but CE didn't rank it #1
    """
    total_queries: int
    correct: int
    candidate_failure: int      # Gold not in bi-encoder top-K
    rerank_failure: int         # Gold in top-K but not ranked #1 by CE
    bi_encoder_correct: int     # Bi-encoder got it right (CE maintained)

    @property
    def candidate_failure_rate(self) -> float:
        return self.candidate_failure / self.total_queries if self.total_queries else 0

    @property
    def rerank_failure_rate(self) -> float:
        return self.rerank_failure / self.total_queries if self.total_queries else 0

    @property
    def ce_correction_rate(self) -> float:
        """Rate where CE corrected bi-encoder errors."""
        bi_errors = self.total_queries - self.bi_encoder_correct - self.candidate_failure
        if bi_errors <= 0:
            return 0.0
        corrections = self.correct - self.bi_encoder_correct
        return corrections / bi_errors if bi_errors > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_queries": self.total_queries,
            "correct": self.correct,
            "candidate_failure": self.candidate_failure,
            "candidate_failure_rate": round(self.candidate_failure_rate, 4),
            "rerank_failure": self.rerank_failure,
            "rerank_failure_rate": round(self.rerank_failure_rate, 4),
            "bi_encoder_correct": self.bi_encoder_correct,
            "ce_correction_rate": round(self.ce_correction_rate, 4),
        }


@dataclass
class LatencyProfile:
    """Latency profile for cost analysis."""
    warm_up_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    std_ms: float
    min_ms: float
    max_ms: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "warm_up_ms": round(self.warm_up_ms, 2),
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "mean_ms": round(self.mean_ms, 2),
            "std_ms": round(self.std_ms, 2),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
        }


@dataclass
class RerankKResult:
    """Result for a specific rerank K value."""
    k: int
    p_at_1: BootstrapResult
    p_at_k: BootstrapResult
    mrr: BootstrapResult
    latency: LatencyProfile
    error_decomposition: ErrorDecomposition

    def to_dict(self) -> Dict[str, Any]:
        return {
            "k": self.k,
            "p_at_1": self.p_at_1.to_dict(),
            f"p_at_{self.k}": self.p_at_k.to_dict(),
            "mrr": self.mrr.to_dict(),
            "latency": self.latency.to_dict(),
            "error_decomposition": self.error_decomposition.to_dict(),
        }


@dataclass
class EvidencePack:
    """Complete evidence pack for paper."""
    # Basic info
    gold_set_size: int
    n_concepts: int
    model_name: str

    # Bi-encoder baseline
    bi_encoder_p1: BootstrapResult
    bi_encoder_mrr: BootstrapResult
    bi_encoder_latency: LatencyProfile

    # Two-stage results by K
    two_stage_results: List[RerankKResult]

    # Summary improvements
    best_improvement_p1: float
    best_improvement_mrr: float
    optimal_k: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": {
                "gold_set_size": self.gold_set_size,
                "n_concepts": self.n_concepts,
                "model_name": self.model_name,
            },
            "bi_encoder_baseline": {
                "p_at_1": self.bi_encoder_p1.to_dict(),
                "mrr": self.bi_encoder_mrr.to_dict(),
                "latency": self.bi_encoder_latency.to_dict(),
            },
            "two_stage_results": [r.to_dict() for r in self.two_stage_results],
            "summary": {
                "best_improvement_p1": round(self.best_improvement_p1, 4),
                "best_improvement_mrr": round(self.best_improvement_mrr, 4),
                "optimal_k": self.optimal_k,
            },
        }


def bootstrap_metric(
    predictions: List[bool],
    n_bootstrap: int = 1000,
    random_seed: int = 42,
) -> BootstrapResult:
    """Compute bootstrap confidence interval for binary metric.

    Args:
        predictions: List of boolean predictions (True=correct)
        n_bootstrap: Number of bootstrap samples
        random_seed: Random seed for reproducibility

    Returns:
        BootstrapResult with mean, std, and 95% CI
    """
    rng = np.random.RandomState(random_seed)
    n = len(predictions)
    if n == 0:
        return BootstrapResult(0.0, 0.0, 0.0, 0.0, n_bootstrap)

    predictions_arr = np.array(predictions, dtype=float)
    bootstrap_means = []

    for _ in range(n_bootstrap):
        indices = rng.randint(0, n, size=n)
        sample = predictions_arr[indices]
        bootstrap_means.append(np.mean(sample))

    bootstrap_means = np.array(bootstrap_means)

    return BootstrapResult(
        mean=np.mean(bootstrap_means),
        std=np.std(bootstrap_means),
        ci_lower=np.percentile(bootstrap_means, 2.5),
        ci_upper=np.percentile(bootstrap_means, 97.5),
        n_bootstrap=n_bootstrap,
    )


def bootstrap_mrr(
    ranks: List[int],  # 0 if not found, 1-indexed otherwise
    n_bootstrap: int = 1000,
    random_seed: int = 42,
) -> BootstrapResult:
    """Compute bootstrap CI for MRR."""
    rng = np.random.RandomState(random_seed)
    n = len(ranks)
    if n == 0:
        return BootstrapResult(0.0, 0.0, 0.0, 0.0, n_bootstrap)

    # Convert ranks to reciprocal ranks
    rr = np.array([1.0 / r if r > 0 else 0.0 for r in ranks])
    bootstrap_mrrs = []

    for _ in range(n_bootstrap):
        indices = rng.randint(0, n, size=n)
        sample = rr[indices]
        bootstrap_mrrs.append(np.mean(sample))

    bootstrap_mrrs = np.array(bootstrap_mrrs)

    return BootstrapResult(
        mean=np.mean(bootstrap_mrrs),
        std=np.std(bootstrap_mrrs),
        ci_lower=np.percentile(bootstrap_mrrs, 2.5),
        ci_upper=np.percentile(bootstrap_mrrs, 97.5),
        n_bootstrap=n_bootstrap,
    )


def compute_latency_profile(latencies: List[float]) -> LatencyProfile:
    """Compute latency profile from list of latencies."""
    if not latencies:
        return LatencyProfile(0, 0, 0, 0, 0, 0, 0, 0)

    latencies_arr = np.array(latencies)

    return LatencyProfile(
        warm_up_ms=latencies[0] if latencies else 0,  # First query (cold)
        p50_ms=np.percentile(latencies_arr, 50),
        p95_ms=np.percentile(latencies_arr, 95),
        p99_ms=np.percentile(latencies_arr, 99),
        mean_ms=np.mean(latencies_arr),
        std_ms=np.std(latencies_arr),
        min_ms=np.min(latencies_arr),
        max_ms=np.max(latencies_arr),
    )


# Gold concept ID to ontology concept ID mapping
# This handles naming convention differences between gold set and ontology
GOLD_TO_ONTOLOGY_MAPPING = {
    # Sepsis
    "start_vasopressor_norepinephrine": "START_VASOPRESSOR_NOREPINEPHRINE",
    "give_broad_spectrum_antibiotics": "GIVE_BROAD_SPECTRUM_ANTIBIOTICS",
    "order_lab_lactate": "ORDER_LACTATE",
    "order_lab_blood_culture": "ORDER_BLOOD_CULTURE",
    "give_crystalloid_30ml_kg": "GIVE_CRYSTALLOID",
    # Chest Pain
    "perform_ecg": "ORDER_ECG",
    "order_lab_troponin": "ORDER_TROPONIN",
    "give_aspirin_loading": "GIVE_ASPIRIN",
    "activate_cath_lab": "ACTIVATE_CATH_LAB",
    "give_nitroglycerin": "GIVE_NITROGLYCERIN",
    "check_right_sided_ecg_v4r": "ORDER_ECG_V4R",
    # AKI
    "order_lab_creatinine": "ORDER_CREATININE",
    "order_lab_bmp": "ORDER_BMP",
    "discontinue_nephrotoxic_medications": "DISCONTINUE_NEPHROTOXINS",
    # DKA
    "start_insulin_infusion": "START_INSULIN_INFUSION",
    "order_lab_glucose": "ORDER_GLUCOSE",
    "order_abg": "ORDER_ABG",
    # Stroke
    "assess_nihss": "ASSESS_NIHSS",
    "order_ct_head": "ORDER_CT_HEAD",
    "give_alteplase_0.9mg_kg": "GIVE_ALTEPLASE",
    # Heart Failure
    "initiate_ace_or_arb_or_arni": "INITIATE_ACEI_ARB_ARNI",
    "initiate_beta_blocker": "INITIATE_BETA_BLOCKER",
    "order_bnp": "ORDER_BNP",
}


def normalize_gold_to_ontology(gold_id: str, ontology_ids: set) -> str:
    """Normalize gold concept ID to match ontology concept ID format.

    Args:
        gold_id: Gold standard concept ID (lowercase with underscores)
        ontology_ids: Set of ontology concept IDs for fuzzy matching

    Returns:
        Normalized concept ID that matches ontology format
    """
    # Direct mapping
    if gold_id in GOLD_TO_ONTOLOGY_MAPPING:
        return GOLD_TO_ONTOLOGY_MAPPING[gold_id]

    # Try uppercase
    upper_id = gold_id.upper()
    if upper_id in ontology_ids:
        return upper_id

    # Try removing 'lab_' prefix
    if gold_id.startswith("order_lab_"):
        base = gold_id.replace("order_lab_", "order_")
        upper_base = base.upper()
        if upper_base in ontology_ids:
            return upper_base

    # Default: uppercase
    return upper_id


class EvidencePackGenerator:
    """Generator for comprehensive evidence pack.

    Usage:
        generator = EvidencePackGenerator(ontology, gold_set)
        pack = generator.generate(k_values=[5, 10, 20, 50])
        pack.save("reports/evidence_pack.json")
    """

    def __init__(
        self,
        ontology,
        gold_set: List,
        use_mock: bool = False,
        use_efficient: bool = False,
        n_bootstrap: int = 1000,
        random_seed: int = 42,
    ):
        self.ontology = ontology
        self.gold_set = gold_set
        self.use_mock = use_mock
        self.use_efficient = use_efficient
        self.n_bootstrap = n_bootstrap
        self.random_seed = random_seed

        self._bi_encoder = None
        self._reranker = None
        self._concepts = None
        self._ontology_ids = None  # For normalization

    def generate(
        self,
        k_values: List[int] = None,
    ) -> EvidencePack:
        """Generate complete evidence pack.

        Args:
            k_values: List of rerank K values to evaluate

        Returns:
            EvidencePack with all results
        """
        if k_values is None:
            k_values = [5, 10, 20, 50]

        logger.info("Building components...")
        self._build_components()

        logger.info("Evaluating bi-encoder baseline...")
        bi_results = self._evaluate_bi_encoder()

        logger.info(f"Evaluating two-stage with K={k_values}...")
        two_stage_results = []
        for k in k_values:
            logger.info(f"  K={k}...")
            result = self._evaluate_two_stage(k)
            two_stage_results.append(result)

        # Find best improvement
        best_k = k_values[0]
        best_improvement_p1 = 0.0
        best_improvement_mrr = 0.0

        for result in two_stage_results:
            delta_p1 = result.p_at_1.mean - bi_results["p1"].mean
            delta_mrr = result.mrr.mean - bi_results["mrr"].mean
            if delta_p1 > best_improvement_p1:
                best_improvement_p1 = delta_p1
                best_improvement_mrr = delta_mrr
                best_k = result.k

        return EvidencePack(
            gold_set_size=len(self.gold_set),
            n_concepts=len(self._concepts),
            model_name="cambridgeltl/SapBERT-from-PubMedBERT-fulltext",
            bi_encoder_p1=bi_results["p1"],
            bi_encoder_mrr=bi_results["mrr"],
            bi_encoder_latency=bi_results["latency"],
            two_stage_results=two_stage_results,
            best_improvement_p1=best_improvement_p1,
            best_improvement_mrr=best_improvement_mrr,
            optimal_k=best_k,
        )

    def _build_components(self):
        """Build bi-encoder and cross-encoder components."""
        from .neural_embedder import (
            NeuralEmbedder,
            MockNeuralEmbedder,
            EmbedderConfig,
        )
        from .cross_encoder_reranker import (
            RerankerConfig,
            get_reranker,
        )

        # Build bi-encoder
        if self.use_mock:
            self._bi_encoder = MockNeuralEmbedder(
                EmbedderConfig(similarity_threshold=0.2)
            )
        else:
            self._bi_encoder = NeuralEmbedder(
                EmbedderConfig(similarity_threshold=0.3)
            )

        # Build concept index from ontology
        self._concepts = []
        for concept in self.ontology.concepts.values():
            concept_id = concept.concept_id
            display = concept.display if hasattr(concept, 'display') else concept_id
            synonyms = list(concept.synonyms) if hasattr(concept, 'synonyms') else []
            self._concepts.append((concept_id, display, synonyms))

        self._bi_encoder.build_index(self._concepts)

        # Store ontology IDs for normalization
        self._ontology_ids = set(c.concept_id for c in self.ontology.concepts.values())

        # Build cross-encoder (optionally with efficient mode)
        self._reranker = get_reranker(
            config=RerankerConfig(max_candidates=50, use_efficient_mode=self.use_efficient),
            use_mock=self.use_mock,
            use_efficient=self.use_efficient,
        )
        self._reranker.initialize()

    def _normalize_gold_id(self, gold_id: str) -> str:
        """Normalize gold concept ID to ontology format."""
        return normalize_gold_to_ontology(gold_id, self._ontology_ids)

    def _ids_match(self, predicted_id: str, gold_id: str) -> bool:
        """Check if predicted ID matches gold ID (case-insensitive + normalization)."""
        pred_upper = predicted_id.upper()
        gold_normalized = self._normalize_gold_id(gold_id)
        return pred_upper == gold_normalized

    def _evaluate_bi_encoder(self) -> Dict[str, Any]:
        """Evaluate bi-encoder baseline."""
        correct_at_1 = []
        ranks = []
        latencies = []

        for instance in self.gold_set:
            start = time.perf_counter()
            results = self._bi_encoder.find_similar(instance.query, top_k=50)
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)

            # Find rank of gold using normalized matching
            rank = 0
            for i, match in enumerate(results, 1):
                if self._ids_match(match.concept_id, instance.gold_concept_id):
                    rank = i
                    break

            ranks.append(rank)
            correct_at_1.append(rank == 1)

        return {
            "p1": bootstrap_metric(correct_at_1, self.n_bootstrap, self.random_seed),
            "mrr": bootstrap_mrr(ranks, self.n_bootstrap, self.random_seed),
            "latency": compute_latency_profile(latencies),
        }

    def _evaluate_two_stage(self, k: int) -> RerankKResult:
        """Evaluate two-stage with specific K."""
        from .cross_encoder_reranker import (
            RerankCandidate,
        )

        correct_at_1 = []
        correct_at_k = []
        ranks = []
        latencies = []

        # Error decomposition counters
        candidate_failures = 0
        rerank_failures = 0
        bi_encoder_correct = 0

        for instance in self.gold_set:
            # Stage 1: Bi-encoder candidates
            start = time.perf_counter()
            bi_results = self._bi_encoder.find_similar(instance.query, top_k=k)

            # Check if gold in candidates (using normalized matching)
            gold_in_candidates = False
            bi_rank = 0
            for i, match in enumerate(bi_results, 1):
                if self._ids_match(match.concept_id, instance.gold_concept_id):
                    gold_in_candidates = True
                    bi_rank = i
                    break

            if not gold_in_candidates:
                # Candidate generation failure
                candidate_failures += 1
                latency_ms = (time.perf_counter() - start) * 1000
                latencies.append(latency_ms)
                correct_at_1.append(False)
                correct_at_k.append(False)
                ranks.append(0)
                continue

            # Check if bi-encoder got it right
            if bi_rank == 1:
                bi_encoder_correct += 1

            # Stage 2: Cross-encoder reranking
            candidates = [
                RerankCandidate(
                    concept_id=m.concept_id,
                    display=m.display,
                    bi_encoder_score=m.similarity,
                )
                for m in bi_results
            ]

            rerank_result = self._reranker.rerank(instance.query, candidates)
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)

            # Find rank after reranking (using normalized matching)
            final_rank = 0
            for i, (cid, ce_score, bi_score) in enumerate(rerank_result.all_candidates, 1):
                if self._ids_match(cid, instance.gold_concept_id):
                    final_rank = i
                    break

            ranks.append(final_rank)
            is_correct_at_1 = (final_rank == 1)
            is_correct_at_k = (0 < final_rank <= k)
            correct_at_1.append(is_correct_at_1)
            correct_at_k.append(is_correct_at_k)

            # Error decomposition
            if not is_correct_at_1 and gold_in_candidates:
                rerank_failures += 1

        # Compute metrics with bootstrap CI
        p_at_1 = bootstrap_metric(correct_at_1, self.n_bootstrap, self.random_seed)
        p_at_k = bootstrap_metric(correct_at_k, self.n_bootstrap, self.random_seed)
        mrr = bootstrap_mrr(ranks, self.n_bootstrap, self.random_seed)
        latency = compute_latency_profile(latencies)

        error_decomp = ErrorDecomposition(
            total_queries=len(self.gold_set),
            correct=sum(correct_at_1),
            candidate_failure=candidate_failures,
            rerank_failure=rerank_failures,
            bi_encoder_correct=bi_encoder_correct,
        )

        return RerankKResult(
            k=k,
            p_at_1=p_at_1,
            p_at_k=p_at_k,
            mrr=mrr,
            latency=latency,
            error_decomposition=error_decomp,
        )


def generate_latex_evidence_table(pack: EvidencePack) -> str:
    """Generate LaTeX table with bootstrap CI."""
    lines = [
        r"% Two-Stage Entity Linking Evidence Pack",
        r"% Generated with bootstrap 95% CI",
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Two-Stage Entity Linking: Bi-encoder vs Cross-encoder Reranking.}",
        r"\label{tab:evidence_pack}",
        r"\begin{tabular}{lccc}",
        r"\toprule",
        r"\textbf{Method} & \textbf{P@1} & \textbf{MRR} & \textbf{Latency (p95)} \\",
        r"\midrule",
    ]

    # Bi-encoder baseline
    bi_p1 = pack.bi_encoder_p1
    bi_mrr = pack.bi_encoder_mrr
    bi_lat = pack.bi_encoder_latency
    lines.append(
        f"Bi-encoder (SapBERT) & {bi_p1.mean:.1%} $\\pm$ {bi_p1.std:.1%} & "
        f"{bi_mrr.mean:.3f} $\\pm$ {bi_mrr.std:.3f} & {bi_lat.p95_ms:.1f}ms \\\\"
    )

    # Two-stage results
    for result in pack.two_stage_results:
        p1 = result.p_at_1
        mrr = result.mrr
        lat = result.latency
        lines.append(
            f"Two-Stage (K={result.k}) & {p1.mean:.1%} $\\pm$ {p1.std:.1%} & "
            f"{mrr.mean:.3f} $\\pm$ {mrr.std:.3f} & {lat.p95_ms:.1f}ms \\\\"
        )

    # Best improvement
    lines.extend([
        r"\midrule",
        f"$\\Delta$ (Best, K={pack.optimal_k}) & "
        f"\\textbf{{+{pack.best_improvement_p1:.1%}}} & "
        f"\\textbf{{+{pack.best_improvement_mrr:.3f}}} & -- \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(lines)


def generate_error_decomposition_table(pack: EvidencePack) -> str:
    """Generate LaTeX table for error decomposition."""
    lines = [
        r"% Error Decomposition: Candidate Generation vs Reranking Failures",
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Error Decomposition: Where does Two-Stage EL fail?}",
        r"\label{tab:error_decomp}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"\textbf{K} & \textbf{Cand. Fail} & \textbf{Rerank Fail} & \textbf{CE Correction} & \textbf{P@1} \\",
        r"\midrule",
    ]

    for result in pack.two_stage_results:
        ed = result.error_decomposition
        lines.append(
            f"K={result.k} & {ed.candidate_failure_rate:.1%} & "
            f"{ed.rerank_failure_rate:.1%} & {ed.ce_correction_rate:.1%} & "
            f"{result.p_at_1.mean:.1%} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\parbox{\linewidth}{\small",
        r"\textbf{Cand. Fail}: Gold not in top-K candidates (bi-encoder issue). ",
        r"\textbf{Rerank Fail}: Gold in candidates but CE didn't rank it \#1. ",
        r"\textbf{CE Correction}: Rate where CE fixed bi-encoder errors.}",
        r"\end{table}",
    ])

    return "\n".join(lines)


def generate_latency_cost_table(pack: EvidencePack) -> str:
    """Generate LaTeX table for latency/cost analysis."""
    lines = [
        r"% Latency and Cost Analysis",
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Latency vs Accuracy Trade-off by Rerank K.}",
        r"\label{tab:latency_cost}",
        r"\begin{tabular}{lccccc}",
        r"\toprule",
        r"\textbf{K} & \textbf{P@1} & \textbf{p50 (ms)} & \textbf{p95 (ms)} & \textbf{p99 (ms)} & \textbf{$\Delta$P@1} \\",
        r"\midrule",
    ]

    bi_p1 = pack.bi_encoder_p1.mean
    bi_lat = pack.bi_encoder_latency
    lines.append(
        f"Bi-only & {bi_p1:.1%} & {bi_lat.p50_ms:.1f} & {bi_lat.p95_ms:.1f} & "
        f"{bi_lat.p99_ms:.1f} & -- \\\\"
    )

    for result in pack.two_stage_results:
        lat = result.latency
        delta = result.p_at_1.mean - bi_p1
        lines.append(
            f"K={result.k} & {result.p_at_1.mean:.1%} & {lat.p50_ms:.1f} & "
            f"{lat.p95_ms:.1f} & {lat.p99_ms:.1f} & +{delta:.1%} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(lines)


def run_evidence_pack_generation(
    output_dir: Path,
    use_mock: bool = False,
    use_efficient: bool = False,
    k_values: List[int] = None,
) -> Dict[str, Any]:
    """Run complete evidence pack generation.

    Args:
        output_dir: Output directory
        use_mock: Use mock models for testing
        use_efficient: Use BioNLP 2025 efficient cross-encoder mode
        k_values: Rerank K values to sweep

    Returns:
        Dict with paths to generated files
    """
    from .ablation import create_default_gold_set
    from .domain_hierarchies import build_unified_ontology

    if k_values is None:
        k_values = [5, 10, 20, 50]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading ontology and gold set...")
    ontology = build_unified_ontology()
    gold_set = create_default_gold_set()

    logger.info(f"Gold set: {len(gold_set)} instances")
    logger.info(f"Ontology: {len(ontology.concepts)} concepts")
    logger.info(f"K values: {k_values}")
    logger.info(f"Efficient mode: {use_efficient}")

    # Generate evidence pack
    generator = EvidencePackGenerator(
        ontology=ontology,
        gold_set=gold_set,
        use_mock=use_mock,
        use_efficient=use_efficient,
    )

    pack = generator.generate(k_values=k_values)

    # Save JSON results
    json_path = output_dir / "evidence_pack.json"
    with open(json_path, "w") as f:
        json.dump(pack.to_dict(), f, indent=2)
    logger.info(f"JSON saved to {json_path}")

    # Generate LaTeX tables
    main_table = generate_latex_evidence_table(pack)
    main_table_path = output_dir / "evidence_main_table.tex"
    with open(main_table_path, "w") as f:
        f.write(main_table)
    logger.info(f"Main table saved to {main_table_path}")

    error_table = generate_error_decomposition_table(pack)
    error_table_path = output_dir / "error_decomposition.tex"
    with open(error_table_path, "w") as f:
        f.write(error_table)
    logger.info(f"Error decomposition table saved to {error_table_path}")

    latency_table = generate_latency_cost_table(pack)
    latency_table_path = output_dir / "latency_cost.tex"
    with open(latency_table_path, "w") as f:
        f.write(latency_table)
    logger.info(f"Latency cost table saved to {latency_table_path}")

    return {
        "json_path": str(json_path),
        "main_table_path": str(main_table_path),
        "error_table_path": str(error_table_path),
        "latency_table_path": str(latency_table_path),
        "summary": pack.to_dict()["summary"],
    }


def main():
    """CLI entrypoint for evidence pack generation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate evidence pack for two-stage EL paper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Quick test with mock models
    PYTHONPATH=. python -m cga_bench.semantic_layer.ontology.evidence_pack --mock

    # Full run with real models and all K values
    PYTHONPATH=. python -m cga_bench.semantic_layer.ontology.evidence_pack

    # Custom K values
    PYTHONPATH=. python -m cga_bench.semantic_layer.ontology.evidence_pack -k 5 10 20
        """
    )

    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock models for testing"
    )
    parser.add_argument(
        "--efficient",
        action="store_true",
        help="Use BioNLP 2025 efficient cross-encoder mode"
    )
    parser.add_argument(
        "-k", "--k-values",
        type=int,
        nargs="+",
        default=[5, 10, 20, 50],
        help="Rerank K values to evaluate (default: 5 10 20 50)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/evidence_pack",
        help="Output directory"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    results = run_evidence_pack_generation(
        output_dir=Path(args.output_dir),
        use_mock=args.mock,
        use_efficient=args.efficient,
        k_values=args.k_values,
    )

    print("\n" + "=" * 60)
    print("Evidence Pack Generation Complete")
    print("=" * 60)
    print(f"\nSummary:")
    print(f"  Best P@1 Improvement: +{results['summary']['best_improvement_p1']:.2%}")
    print(f"  Best MRR Improvement: +{results['summary']['best_improvement_mrr']:.4f}")
    print(f"  Optimal K: {results['summary']['optimal_k']}")
    print(f"\nOutput Files:")
    for key, path in results.items():
        if key.endswith("_path"):
            print(f"  {key}: {path}")


if __name__ == "__main__":
    main()
