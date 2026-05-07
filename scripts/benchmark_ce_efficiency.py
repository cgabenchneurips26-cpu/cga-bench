#!/usr/bin/env python
"""Benchmark Cross-Encoder Efficiency.

Compares standard vs efficient (BioNLP 2025) cross-encoder modes.

Usage:
    PYTHONPATH=. python scripts/benchmark_ce_efficiency.py

Output:
    - Latency comparison (standard vs efficient)
    - Throughput metrics
    - Memory usage (if available)
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Benchmark result for a single mode."""
    mode: str
    k: int
    n_queries: int
    total_time_ms: float
    mean_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    throughput_qps: float  # queries per second
    warm_up_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "k": self.k,
            "n_queries": self.n_queries,
            "total_time_ms": round(self.total_time_ms, 2),
            "mean_latency_ms": round(self.mean_latency_ms, 2),
            "p50_latency_ms": round(self.p50_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "p99_latency_ms": round(self.p99_latency_ms, 2),
            "throughput_qps": round(self.throughput_qps, 2),
            "warm_up_time_ms": round(self.warm_up_time_ms, 2),
        }


def run_benchmark(
    mode: str,  # "standard" or "efficient"
    k_values: List[int],
    n_iterations: int = 3,
    use_mock: bool = False,
) -> List[BenchmarkResult]:
    """Run benchmark for a specific mode.

    Args:
        mode: Reranker mode ("standard" or "efficient")
        k_values: List of K values to test
        n_iterations: Number of iterations per K value
        use_mock: Use mock models for quick testing

    Returns:
        List of BenchmarkResult for each K value.
    """
    from cga_bench.semantic_layer.ontology.cross_encoder_reranker import (
        RerankerConfig,
        RerankCandidate,
        get_reranker,
    )
    from cga_bench.semantic_layer.ontology.ablation import create_default_gold_set
    from cga_bench.semantic_layer.ontology.domain_hierarchies import build_unified_ontology
    from cga_bench.semantic_layer.ontology.neural_embedder import (
        NeuralEmbedder,
        MockNeuralEmbedder,
        EmbedderConfig,
    )

    logger.info(f"Running benchmark for mode={mode}")

    # Build components
    config = RerankerConfig(
        max_candidates=max(k_values),
        use_efficient_mode=(mode == "efficient"),
    )

    reranker = get_reranker(
        config=config,
        use_mock=use_mock,
        use_efficient=(mode == "efficient"),
    )

    # Build bi-encoder for candidate generation
    ontology = build_unified_ontology()
    concepts = [
        (c.concept_id, c.display if hasattr(c, 'display') else c.concept_id,
         list(c.synonyms) if hasattr(c, 'synonyms') else [])
        for c in ontology.concepts.values()
    ]

    if use_mock:
        bi_encoder = MockNeuralEmbedder(EmbedderConfig(similarity_threshold=0.2))
    else:
        bi_encoder = NeuralEmbedder(EmbedderConfig(similarity_threshold=0.3))

    bi_encoder.build_index(concepts)

    # Warm-up
    warm_up_start = time.perf_counter()
    reranker.warm_up()
    warm_up_time = (time.perf_counter() - warm_up_start) * 1000

    # Get gold set queries
    gold_set = create_default_gold_set()
    queries = [inst.query for inst in gold_set]

    results = []

    for k in k_values:
        logger.info(f"  K={k}...")
        latencies = []

        for _ in range(n_iterations):
            for query in queries:
                # Get bi-encoder candidates
                bi_results = bi_encoder.find_similar(query, top_k=k)
                candidates = [
                    RerankCandidate(
                        concept_id=m.concept_id,
                        display=m.display,
                        bi_encoder_score=m.similarity,
                    )
                    for m in bi_results
                ]

                # Time the reranking
                start = time.perf_counter()
                _ = reranker.rerank(query, candidates)
                latency_ms = (time.perf_counter() - start) * 1000
                latencies.append(latency_ms)

        latencies = np.array(latencies)
        n_queries = len(latencies)
        total_time = np.sum(latencies)

        result = BenchmarkResult(
            mode=mode,
            k=k,
            n_queries=n_queries,
            total_time_ms=total_time,
            mean_latency_ms=np.mean(latencies),
            p50_latency_ms=np.percentile(latencies, 50),
            p95_latency_ms=np.percentile(latencies, 95),
            p99_latency_ms=np.percentile(latencies, 99),
            throughput_qps=n_queries / (total_time / 1000) if total_time > 0 else 0,
            warm_up_time_ms=warm_up_time,
        )
        results.append(result)

    return results


def generate_comparison_table(
    standard_results: List[BenchmarkResult],
    efficient_results: List[BenchmarkResult],
) -> str:
    """Generate LaTeX comparison table."""
    lines = [
        r"% Cross-Encoder Efficiency Comparison",
        r"% Standard vs BioNLP 2025 Efficient Mode",
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Cross-Encoder Efficiency: Standard vs Efficient (BioNLP 2025).}",
        r"\label{tab:ce_efficiency}",
        r"\begin{tabular}{lccccc}",
        r"\toprule",
        r"\textbf{K} & \textbf{Mode} & \textbf{Mean (ms)} & \textbf{p95 (ms)} & \textbf{QPS} & \textbf{Speedup} \\",
        r"\midrule",
    ]

    # Group by K
    k_values = sorted(set(r.k for r in standard_results))

    for k in k_values:
        std = next((r for r in standard_results if r.k == k), None)
        eff = next((r for r in efficient_results if r.k == k), None)

        if std and eff:
            speedup = std.mean_latency_ms / eff.mean_latency_ms if eff.mean_latency_ms > 0 else 0

            lines.append(
                f"{k} & Standard & {std.mean_latency_ms:.1f} & {std.p95_latency_ms:.1f} & "
                f"{std.throughput_qps:.0f} & -- \\\\"
            )
            lines.append(
                f" & \\textbf{{Efficient}} & \\textbf{{{eff.mean_latency_ms:.1f}}} & "
                f"\\textbf{{{eff.p95_latency_ms:.1f}}} & \\textbf{{{eff.throughput_qps:.0f}}} & "
                f"\\textbf{{{speedup:.2f}x}} \\\\"
            )
            if k != k_values[-1]:
                lines.append(r"\midrule")

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\parbox{\linewidth}{\small",
        r"\textbf{QPS}: Queries per second. \textbf{Speedup}: Ratio of standard/efficient latency.}",
        r"\end{table}",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark cross-encoder efficiency",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock models for quick testing",
    )
    parser.add_argument(
        "--k-values",
        type=str,
        default="5,10,20,50",
        help="Comma-separated K values to test",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of iterations per K value",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/ce_efficiency",
        help="Output directory",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    k_values = [int(k) for k in args.k_values.split(",")]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run benchmarks
    logger.info("Running standard mode benchmark...")
    standard_results = run_benchmark(
        mode="standard",
        k_values=k_values,
        n_iterations=args.iterations,
        use_mock=args.mock,
    )

    logger.info("Running efficient mode benchmark...")
    efficient_results = run_benchmark(
        mode="efficient",
        k_values=k_values,
        n_iterations=args.iterations,
        use_mock=args.mock,
    )

    # Save JSON results
    all_results = {
        "standard": [r.to_dict() for r in standard_results],
        "efficient": [r.to_dict() for r in efficient_results],
    }

    json_path = output_dir / "ce_efficiency_benchmark.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2)
    logger.info(f"JSON saved to {json_path}")

    # Generate LaTeX table
    latex_table = generate_comparison_table(standard_results, efficient_results)
    latex_path = output_dir / "ce_efficiency_table.tex"
    with open(latex_path, "w") as f:
        f.write(latex_table)
    logger.info(f"LaTeX table saved to {latex_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("Cross-Encoder Efficiency Benchmark Results")
    print("=" * 60)

    print("\nLatency Comparison (mean, ms):")
    print(f"{'K':<6} {'Standard':<12} {'Efficient':<12} {'Speedup':<10}")
    print("-" * 40)

    for k in k_values:
        std = next((r for r in standard_results if r.k == k), None)
        eff = next((r for r in efficient_results if r.k == k), None)
        if std and eff:
            speedup = std.mean_latency_ms / eff.mean_latency_ms if eff.mean_latency_ms > 0 else 0
            print(f"{k:<6} {std.mean_latency_ms:<12.2f} {eff.mean_latency_ms:<12.2f} {speedup:.2f}x")

    print(f"\nOutput files:")
    print(f"  JSON: {json_path}")
    print(f"  LaTeX: {latex_path}")


if __name__ == "__main__":
    main()
