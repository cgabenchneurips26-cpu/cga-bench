#!/usr/bin/env python3
"""E2E evaluation for AMEGA and LLMEval-Med via CGA pipeline."""
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, str(Path(__file__).parent.parent))

from cga_bench.semantic_layer.external.registry import get_manifest
from cga_bench.semantic_layer.external.pipeline import (
    raw_to_canonical, build_expected_actions, split_amega_questions,
)


def evaluate_dataset(dataset_id: str, data_path: str, limit: int = 50):
    """Evaluate a dataset through the CGA pipeline."""
    manifest = get_manifest(dataset_id)
    print(f"\n{'='*60}")
    print(f"Evaluating: {manifest.dataset_name} ({dataset_id})")
    print(f"{'='*60}")

    with open(data_path) as f:
        raw_cases = [json.loads(l) for l in f.readlines()[:limit]]

    print(f"Loaded {len(raw_cases)} raw cases")

    results = []
    success = 0
    total_actions = 0

    for i, raw in enumerate(raw_cases):
        try:
            # For AMEGA, split into per-question sub-cases
            if dataset_id == "amega" and raw.get("questions"):
                sub_cases = split_amega_questions(raw, manifest)
                # Use first question only for simplicity
                if sub_cases:
                    case = sub_cases[0]
                else:
                    case = raw_to_canonical(raw, manifest)
            else:
                case = raw_to_canonical(raw, manifest)

            # Build expected actions from checklist
            expected = build_expected_actions(case)

            n_mandatory = sum(1 for ea in expected if ea.kind == "mandatory")
            n_forbidden = sum(1 for ea in expected if ea.kind == "forbidden")
            n_assessment = sum(1 for ea in expected if ea.kind == "assessment")
            n_total = len(expected)

            if n_total > 0:
                success += 1
                total_actions += n_total

            results.append({
                "case_id": case.case_id,
                "input_text_len": len(case.input_text or ""),
                "checklist_len": len(case.checklist),
                "expected_actions": n_total,
                "mandatory": n_mandatory,
                "forbidden": n_forbidden,
                "assessment": n_assessment,
                "domain": getattr(case, 'domain', None) or "general",
            })

            if (i + 1) % 10 == 0:
                print(f"  Processed {i+1}/{len(raw_cases)}")

        except Exception as e:
            results.append({
                "case_id": raw.get("case_id", raw.get("id", f"case_{i}")),
                "error": str(e)[:100],
            })

    # Summary
    errors = [r for r in results if "error" in r]
    valid = [r for r in results if "error" not in r]
    with_actions = [r for r in valid if r["expected_actions"] > 0]

    print(f"\n--- Summary ---")
    print(f"Total: {len(results)}, Success: {len(valid)}, Errors: {len(errors)}")
    print(f"Cases with actions: {len(with_actions)}/{len(valid)}")
    if with_actions:
        avg_actions = sum(r["expected_actions"] for r in with_actions) / len(with_actions)
        avg_mandatory = sum(r["mandatory"] for r in with_actions) / len(with_actions)
        avg_forbidden = sum(r["forbidden"] for r in with_actions) / len(with_actions)
        avg_assessment = sum(r["assessment"] for r in with_actions) / len(with_actions)
        print(f"Avg actions: {avg_actions:.1f} (mandatory={avg_mandatory:.1f}, forbidden={avg_forbidden:.1f}, assessment={avg_assessment:.1f})")

    # Domain distribution
    from collections import Counter
    domains = Counter(r.get("domain", "?") for r in valid)
    print(f"Domains: {dict(domains.most_common(10))}")

    return {
        "dataset_id": dataset_id,
        "total": len(results),
        "success": len(valid),
        "errors": len(errors),
        "cases_with_actions": len(with_actions),
        "avg_actions": sum(r.get("expected_actions", 0) for r in with_actions) / max(len(with_actions), 1),
        "domains": dict(domains),
        "results": results,
    }


if __name__ == "__main__":
    output_dir = Path(__file__).parent.parent / "reports" / "evidence_pack" / "external_benchmarks"
    output_dir.mkdir(parents=True, exist_ok=True)

    # AMEGA
    base = Path(__file__).parent.parent
    amega_path = str(base / "data/external_benchmarks/amega/amega.jsonl")
    if Path(amega_path).exists():
        amega_results = evaluate_dataset("amega", amega_path, limit=24)
        with open(output_dir / "amega_pipeline_results.json", "w") as f:
            json.dump(amega_results, f, indent=2, ensure_ascii=False)
        print(f"\nSaved: {output_dir}/amega_pipeline_results.json")

    # LLMEval-Med
    llmeval_path = str(base / "data/external_benchmarks/llmeval_med/llmeval_med.jsonl")
    if Path(llmeval_path).exists():
        llmeval_results = evaluate_dataset("llmeval_med", llmeval_path, limit=50)
        with open(output_dir / "llmeval_med_pipeline_results.json", "w") as f:
            json.dump(llmeval_results, f, indent=2, ensure_ascii=False)
        print(f"\nSaved: {output_dir}/llmeval_med_pipeline_results.json")

    print("\n" + "=" * 60)
    print("DONE")
