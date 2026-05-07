"""CLI entry point for the SGSC pipeline.

Usage:
    PYTHONPATH=. python -m sgsc.cli \
        --corpus data_release/v5.0/rag_corpus/SSC-2021.parsed.json \
        --guideline-id ssc_sepsis_hour1 \
        --guideline-name "SSC 2021 Hour-1 Bundle" \
        --output-dir sgsc_output/ssc_2021/ \
        --endpoint http://localhost:8013/v1
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

from sgsc.extraction.atom_proposer import AtomProposerConfig
from sgsc.pipeline import PipelineConfig, run_pipeline


def _load_corpus(corpus_path: str) -> tuple[str, list[dict]]:
    """Load corpus JSON and extract full text + recommendations."""
    data = json.loads(Path(corpus_path).read_text())

    if isinstance(data, dict):
        recommendations = data.get("recommendations", [])
        full_text = data.get("full_text", "")
        if not full_text and recommendations:
            full_text = " ".join(str(r.get("text", "")) for r in recommendations)
    elif isinstance(data, list):
        recommendations = data
        full_text = " ".join(str(r.get("text", "")) for r in data)
    else:
        recommendations = []
        full_text = str(data)

    return full_text, recommendations


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Source-Grounded Scenario Compiler (SGSC)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--corpus", required=True, help="Path to corpus JSON file")
    parser.add_argument("--guideline-id", required=True, help="Guideline identifier")
    parser.add_argument("--guideline-name", required=True, help="Guideline display name")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--endpoint", default=None, help="vLLM endpoint URL")
    parser.add_argument("--model", default="default", help="Model name for endpoint")
    parser.add_argument("--atoms-json", default=None, help="Precomputed atoms JSON file (skip LLM)")
    parser.add_argument("--threshold", type=float, default=0.4, help="Grounding threshold")
    parser.add_argument("--max-scenarios", type=int, default=500, help="Max scenarios to generate")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Load corpus
    full_text, recommendations = _load_corpus(args.corpus)
    logging.info("Loaded corpus: %d chars, %d recommendations", len(full_text), len(recommendations))

    # Build LLM config
    llm_config = None
    if args.endpoint:
        llm_config = AtomProposerConfig(
            endpoint=args.endpoint,
            model=args.model,
            timeout_seconds=600.0,
        )

    # Load precomputed atoms
    precomputed = None
    if args.atoms_json:
        from sgsc.schemas.atom import RecommendationAtom

        atoms_data = json.loads(Path(args.atoms_json).read_text())
        precomputed = [RecommendationAtom.model_validate(a) for a in atoms_data]
        logging.info("Loaded %d precomputed atoms", len(precomputed))

    # Build pipeline config
    config = PipelineConfig(
        guideline_id=args.guideline_id,
        guideline_name=args.guideline_name,
        output_dir=args.output_dir,
        llm_config=llm_config,
        grounding_threshold=args.threshold,
        max_scenarios=args.max_scenarios,
    )

    # Run pipeline
    result = run_pipeline(config, full_text, recommendations, precomputed)

    # Summary
    print("\n=== SGSC Pipeline Complete ===")
    print(f"Atoms: {len(result.atoms)}")
    print(f"Seeds: {result.total_seeds}")
    print(f"Families: {result.total_families}")
    print(f"Mutations: {result.total_mutations}")
    print(f"Scenarios: {len(result.scenarios)}")
    print(f"Hallucination rate: {result.hallucination_rate:.3f}")
    print(f"Leakage audit: {'PASS' if result.leakage_passed else 'FAIL'}")
    for fmt, path in result.coverage_paths.items():
        print(f"Coverage ({fmt}): {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
