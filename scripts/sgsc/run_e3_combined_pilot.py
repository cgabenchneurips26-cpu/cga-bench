#!/usr/bin/env python3
"""E3 combined pilot: taxonomy (E3-a) + multi-pass (E3-b) + corpus context (E3-c).

Runs the SGSC pipeline on a single guideline with all E3 features enabled
natively (no monkeypatching). The expanded 14-type taxonomy is already baked
into atom_proposer.SYSTEM_PROMPT since the E3-a commit.

Usage:
    PYTHONPATH=cga_bench:. python scripts/sgsc/run_e3_combined_pilot.py \
        --endpoint http://localhost:8013/v1 \
        --model "Qwen/Qwen3.5-397B-A17B-FP8"
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT.parent))

GUIDELINE_ID = "kdigo_contrast_aki"
GUIDELINE_NAME = "KDIGO 2012 Contrast AKI"
CORPUS_FILE = REPO_ROOT / "data_release/v5.0/rag_corpus/KDIGO-2012-Contrast-AKI.parsed.json"

CORPUS_CONTEXT_CHARS = 6000
TIMEOUT_SECONDS = 600.0


def _load_corpus(path: Path) -> tuple[list[dict], str]:
    """Load recommendations and full text from parsed corpus JSON."""
    data = json.loads(path.read_text())
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
    return recommendations, full_text


def main() -> int:
    """Run E3 combined pilot."""
    parser = argparse.ArgumentParser(description="E3 combined pilot (E3-a + E3-b + E3-c)")
    parser.add_argument("--endpoint", required=True, help="vLLM endpoint URL")
    parser.add_argument("--model", default="default", help="Model name")
    parser.add_argument("--guideline-id", default=GUIDELINE_ID, help="Target guideline")
    parser.add_argument("--threshold", type=float, default=0.5, help="Grounding threshold")
    parser.add_argument("--max-scenarios", type=int, default=55)
    parser.add_argument("--no-multi-pass", action="store_true", help="Disable E3-b multi-pass")
    parser.add_argument("--corpus-chars", type=int, default=CORPUS_CONTEXT_CHARS)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger("e3_pilot")

    from sgsc.extraction.atom_proposer import AtomProposerConfig
    from sgsc.pipeline import PipelineConfig, run_pipeline

    corpus_path = CORPUS_FILE
    if args.guideline_id != GUIDELINE_ID:
        corpus_path = REPO_ROOT / "data_release/v5.0/rag_corpus" / f"{args.guideline_id}.parsed.json"
        if not corpus_path.exists():
            # Try registry lookup
            registry_path = REPO_ROOT / "configs/sgsc/full_25_registry.json"
            if registry_path.exists():
                registry = json.loads(registry_path.read_text())
                for g in registry["guidelines"]:
                    if g["guideline_id"] == args.guideline_id:
                        corpus_path = REPO_ROOT / g["corpus_file"]
                        break

    if not corpus_path.exists():
        logger.error("Corpus not found: %s", corpus_path)
        return 2

    recommendations, full_text = _load_corpus(corpus_path)
    logger.info("Loaded %d recommendations, %d chars corpus text", len(recommendations), len(full_text))

    enable_multi_pass = not args.no_multi_pass
    tag = "e3abc" if enable_multi_pass else "e3ac"
    output_dir = REPO_ROOT / "sgsc_output" / f"v7_{tag}_pilot" / args.guideline_id
    output_dir.mkdir(parents=True, exist_ok=True)

    llm_config = AtomProposerConfig(
        endpoint=args.endpoint,
        model=args.model,
        timeout_seconds=TIMEOUT_SECONDS,
        enable_multi_pass=enable_multi_pass,
        corpus_context_chars=args.corpus_chars,
    )

    pipeline_config = PipelineConfig(
        guideline_id=args.guideline_id,
        guideline_name=GUIDELINE_NAME if args.guideline_id == GUIDELINE_ID else args.guideline_id,
        output_dir=str(output_dir),
        llm_config=llm_config,
        grounding_threshold=args.threshold,
        max_scenarios=args.max_scenarios,
    )

    logger.info(
        "E3 config: multi_pass=%s, corpus_chars=%d, threshold=%.2f",
        enable_multi_pass,
        args.corpus_chars,
        args.threshold,
    )
    logger.info("Output -> %s", output_dir)

    start = time.monotonic()
    result = run_pipeline(pipeline_config, full_text, recommendations)
    elapsed = time.monotonic() - start

    # Compute metrics
    action_types: dict[str, int] = {}
    short_canonical = 0
    for atom in result.atoms:
        at = atom.action.action_type
        action_types[at] = action_types.get(at, 0) + 1
        if len(atom.action.canonical_id) < 10:
            short_canonical += 1

    truncated_stem_rate = short_canonical / len(result.atoms) if result.atoms else 0.0

    summary = {
        "guideline_id": args.guideline_id,
        "e3_features": {
            "e3a_taxonomy": "14-type (native)",
            "e3b_multi_pass": enable_multi_pass,
            "e3c_corpus_chars": args.corpus_chars,
        },
        "atoms_accepted": len(result.atoms),
        "atoms_rejected": len(result.rejected_atoms),
        "atoms_review_required": len(result.review_required_atoms),
        "scenarios": len(result.scenarios),
        "seeds": result.total_seeds,
        "families": result.total_families,
        "mutations": result.total_mutations,
        "hallucination_rate": round(result.hallucination_rate, 4),
        "leakage_passed": result.leakage_passed,
        "truncated_stem_rate": round(truncated_stem_rate, 4),
        "action_type_distribution": dict(sorted(action_types.items())),
        "unique_actions": sorted({a.action.canonical_id for a in result.atoms}),
        "model": args.model,
        "threshold": args.threshold,
        "elapsed_seconds": round(elapsed, 1),
    }

    summary_path = output_dir / "_e3_pilot_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    logger.info("Summary -> %s", summary_path)

    print("\n=== E3 Combined Pilot Results ===")
    print(f"Guideline:          {args.guideline_id}")
    print(f"E3 features:        a(taxonomy) + b(multi-pass={enable_multi_pass}) + c(corpus={args.corpus_chars})")
    print(f"Atoms accepted:     {len(result.atoms)}")
    print(f"Atoms rejected:     {len(result.rejected_atoms)}")
    print(f"Scenarios:          {len(result.scenarios)}")
    print(f"Truncated stem:     {truncated_stem_rate:.1%} ({short_canonical}/{len(result.atoms)})")
    print(f"Hallucination rate: {result.hallucination_rate:.4f}")
    print(f"Elapsed:            {elapsed:.1f}s")
    print(f"\nAction type distribution:")
    for at, count in sorted(action_types.items()):
        print(f"  {at:20s} {count}")
    print(f"\nUnique actions ({len(summary['unique_actions'])}):")
    for action in summary["unique_actions"]:
        print(f"  {action}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
