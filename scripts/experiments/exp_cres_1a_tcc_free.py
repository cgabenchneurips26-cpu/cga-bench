#!/usr/bin/env python3
"""CRES-1A: Catalogue-Free LLM Judge Evaluator (TCC-Free).

Runs the TCCFreeEvaluator (evaluators/tcc_free.py) on cached verdict
records and reports Cohen's kappa versus the existing TCC verdicts.

By default this script is safe: the --mock flag uses the MockLLMProvider
so no API calls happen. The --full flag requires an explicit cost
acknowledgement via --i-know-it-costs.

Usage:
    # Dry-run: 5 traces, mock LLM, no cost.
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_cres_1a_tcc_free.py --mock --n 5

    # Pilot: 100 traces, real GPT-4o, ~$30.
    PYTHONPATH=${CGA_BENCH_ROOT} \
      OPENAI_API_KEY=sk-... python scripts/experiments/exp_cres_1a_tcc_free.py \
        --model gpt-4o --n 100 --i-know-it-costs

    # Full: 16944 traces. Requires explicit budget flag.
    PYTHONPATH=${CGA_BENCH_ROOT} \
      OPENAI_API_KEY=sk-... python scripts/experiments/exp_cres_1a_tcc_free.py \
        --model gpt-4o --full --i-know-it-costs
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evaluators.tcc_free import build_default_evaluator  # noqa: E402
from scripts.experiments._episode_cache import (  # noqa: E402
    EVIDENCE_DIR,
    load_cached_verdicts,
)

OUTPUT_DIR = EVIDENCE_DIR / "cres_1a"

PILOT_DEFAULT_N = 100
FULL_N = 16944
ESTIMATED_USD_PER_1K_CALLS = 300.0  # GPT-4o at ~$0.30/call estimate


def cohen_kappa_binary(labels_a: list[int], labels_b: list[int]) -> float:
    """Cohen's kappa for two binary label sequences."""
    if len(labels_a) != len(labels_b) or not labels_a:
        return float("nan")
    n = len(labels_a)
    observed_agree = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    p_a = sum(labels_a) / n
    p_b = sum(labels_b) / n
    expected_agree = p_a * p_b + (1 - p_a) * (1 - p_b)
    if expected_agree >= 1.0:
        return 1.0 if observed_agree == 1.0 else 0.0
    return (observed_agree - expected_agree) / (1 - expected_agree)


def sample_records(
    records: list[dict],
    n: int,
    seed: int = 42,
) -> list[dict]:
    """Random stratified-ish sample of n records without replacement."""
    if n >= len(records):
        return list(records)
    rng = random.Random(seed)
    idxs = rng.sample(range(len(records)), n)
    return [records[i] for i in idxs]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n",
        type=int,
        default=PILOT_DEFAULT_N,
        help="Number of traces to evaluate (ignored if --full).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help=f"Run on all {FULL_N} cached verdicts.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use MockLLMProvider (no API calls).",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="OpenAI model name (ignored in --mock).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random sampling seed.",
    )
    parser.add_argument(
        "--vllm-endpoint",
        default="",
        help="vLLM base URL (e.g. http://localhost:8013/v1). Overrides --model.",
    )
    parser.add_argument(
        "--vllm-model",
        default="Qwen/Qwen3.5-35B-A3B-FP8",
        help="Model name for vLLM endpoint.",
    )
    parser.add_argument(
        "--i-know-it-costs",
        action="store_true",
        help="Required acknowledgement for non-mock, non-vLLM runs.",
    )
    parser.add_argument(
        "--shard",
        default="",
        help="Shard spec M/N (e.g. 1/7). Splits records into N chunks, runs chunk M.",
    )
    args = parser.parse_args()

    use_vllm = bool(args.vllm_endpoint.strip())
    if not args.mock and not use_vllm and not args.i_know_it_costs:
        print(
            "ERROR: Non-mock, non-vLLM runs require --i-know-it-costs to confirm API spend.",
            file=sys.stderr,
        )
        return 2

    print("=" * 60)
    print("CRES-1A: Catalogue-Free LLM Judge Evaluator")
    print("=" * 60)

    _episodes, records = load_cached_verdicts()
    print(f"Loaded {len(records)} cached verdicts.")

    target_n = FULL_N if args.full else args.n
    sampled = sample_records(records, target_n, args.seed)

    # Sharding: split sampled records into N chunks, use chunk M
    shard_m, shard_n = 0, 0
    if args.shard.strip():
        parts = args.shard.strip().split("/")
        shard_m, shard_n = int(parts[0]), int(parts[1])
        chunk_size = len(sampled) // shard_n
        start = (shard_m - 1) * chunk_size
        end = len(sampled) if shard_m == shard_n else shard_m * chunk_size
        sampled = sampled[start:end]
        print(f"Shard {shard_m}/{shard_n}: records [{start}:{end}] = {len(sampled)}")

    est_cost = len(sampled) / 1000.0 * ESTIMATED_USD_PER_1K_CALLS
    print(f"Evaluating {len(sampled)} records (seed={args.seed}).")
    if not args.mock:
        print(f"Estimated API cost: ~${est_cost:,.2f} at ${ESTIMATED_USD_PER_1K_CALLS}/1k calls")

    if use_vllm:
        evaluator = build_default_evaluator(
            use_mock=False,
            model=args.vllm_model,
            vllm_endpoint=args.vllm_endpoint.strip(),
        )
        print(f"  Backend: vLLM @ {args.vllm_endpoint.strip()}")
    else:
        evaluator = build_default_evaluator(use_mock=args.mock, model=args.model)

    # Evaluate
    tcc_labels: list[int] = []
    free_labels: list[int] = []
    out_records: list[dict] = []
    total_tokens = 0

    for i, rec in enumerate(sampled, start=1):
        try:
            verdict = evaluator.evaluate(rec)
        except (RuntimeError, ValueError) as exc:
            print(f"  [{i}/{len(sampled)}] ERROR on {rec.get('scenario_id')}: {exc}")
            continue
        tcc_pass = 1 if bool(rec.get("cga_pass")) else 0
        free_pass = 1 if verdict.verdict_binary == "pass" else 0
        tcc_labels.append(tcc_pass)
        free_labels.append(free_pass)
        total_tokens += verdict.tokens_used
        out_records.append(
            {
                "scenario_id": verdict.scenario_id,
                "run_index": verdict.run_index,
                "model": verdict.model,
                "tcc_pass": bool(tcc_pass),
                "free_pass": bool(free_pass),
                "free_n_violations": len(verdict.violations),
                "free_reasoning": verdict.reasoning[:200],
            }
        )
        if i % 10 == 0 or i == len(sampled):
            print(f"  [{i}/{len(sampled)}] tokens so far: {total_tokens}")

    kappa = cohen_kappa_binary(tcc_labels, free_labels)
    agreement = (
        sum(1 for a, b in zip(tcc_labels, free_labels) if a == b) / len(tcc_labels) if tcc_labels else float("nan")
    )

    results = {
        "experiment": "CRES-1A",
        "n_evaluated": len(tcc_labels),
        "mock_backend": args.mock,
        "model": "mock" if args.mock else args.model,
        "cohen_kappa_tcc_vs_free": kappa,
        "raw_agreement": agreement,
        "total_tokens": total_tokens,
        "per_record": out_records,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = "pilot_mock" if args.mock else ("full" if args.full else "pilot")
    shard_suffix = f"_shard{shard_m}of{shard_n}" if shard_n else ""
    out_path = OUTPUT_DIR / f"cres_1a_{stem}{shard_suffix}_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults: kappa={kappa:.4f}, agreement={agreement:.4f}")
    print(f"Saved to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
