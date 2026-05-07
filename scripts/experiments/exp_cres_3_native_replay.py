#!/usr/bin/env python3
"""CRES-3: Native External Scorer Replay.

Runs the authors' own scorers from MedAgentBench / AgentClinic / AMEGA on
CGA-Bench traces and compares their verdicts to our AC-Proxy. This is
the "straw-man evaluator" rebuttal: if the native scorers agree with
AC-Proxy at kappa >= 0.75, the attack "CGA-Bench re-implemented the
baseline evaluators so it could rig them" is falsified.

This runner defaults to --dry-run with a stub scorer so it never calls
out to external repos without explicit operator action. See
`external_scorers/README.md` for the anonymity-safe clone protocol.

Usage:
    # Dry-run (stub scorer, no clone, no API):
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_cres_3_native_replay.py \
        --benchmark medagentbench --pilot-n 10 --dry-run

    # Real run (after cloning + wiring the scorer — not this session):
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_cres_3_native_replay.py \
        --benchmark medagentbench --pilot-n 100 \
        --clone-dir external_scorers/native/medagentbench
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._episode_cache import (  # noqa: E402
    EVIDENCE_DIR,
    load_cached_verdicts,
)

from cga_bench.external_scorers.medagentbench_adapter import (  # noqa: E402
    MedAgentBenchAdapter,
    MedAgentBenchRecord,
    bind_native_scorer_from_clone,
)

OUTPUT_DIR = EVIDENCE_DIR / "cres_3"
SUPPORTED_BENCHMARKS: tuple[str, ...] = ("medagentbench", "agentclinic", "amega")


def _stub_medagentbench_scorer(rec: MedAgentBenchRecord) -> tuple[bool, float]:
    """Deterministic stub: Jaccard similarity over action sets."""
    performed = set(rec.predicted_actions)
    expected = set(rec.ground_truth_actions)
    if not expected:
        return (True, 1.0)
    jacc = len(performed & expected) / len(performed | expected) if (performed | expected) else 0.0
    return (jacc >= 0.5, jacc)


def cohen_kappa_binary(labels_a: list[int], labels_b: list[int]) -> float:
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


def run_medagentbench(
    records: list[dict],
    dry_run: bool,
    clone_dir: Path | None,
) -> dict:
    """Execute the MedAgentBench native replay on the sampled records."""
    if dry_run:
        adapter = MedAgentBenchAdapter(_stub_medagentbench_scorer)
        scorer_mode = "stub_jaccard_0.5_threshold"
    else:
        if clone_dir is None:
            raise SystemExit("Non-dry-run requires --clone-dir pointing at the native repo")
        scorer = bind_native_scorer_from_clone(clone_dir)
        adapter = MedAgentBenchAdapter(scorer)
        scorer_mode = f"native@{clone_dir}"

    rows, rejections = adapter.score_batch(records)
    native_labels = [1 if r.native_pass else 0 for r in rows]
    proxy_labels = [1 if r.proxy_pass else 0 for r in rows]
    kappa = cohen_kappa_binary(native_labels, proxy_labels)
    agreement = sum(1 for a, b in zip(native_labels, proxy_labels) if a == b) / len(rows) if rows else float("nan")

    return {
        "experiment": "CRES-3",
        "benchmark": "medagentbench",
        "scorer_mode": scorer_mode,
        "n_evaluated": len(rows),
        "n_rejected": len(rejections),
        "rejection_reasons": _tally_reasons(rejections),
        "cohen_kappa_native_vs_proxy": kappa,
        "raw_agreement": agreement,
        "per_record": [
            {
                "scenario_id": r.scenario_id,
                "run_index": r.run_index,
                "model": r.model,
                "native_pass": r.native_pass,
                "native_score": round(r.native_score, 4),
                "proxy_pass": r.proxy_pass,
            }
            for r in rows
        ],
    }


def _tally_reasons(rejections: list[dict]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for r in rejections:
        key = r.get("reason", "unknown")[:80]
        tally[key] = tally.get(key, 0) + 1
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark",
        choices=SUPPORTED_BENCHMARKS,
        required=True,
    )
    parser.add_argument(
        "--pilot-n",
        type=int,
        default=100,
        help="Number of cached records to sample.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )
    # Dry-run is the SAFE DEFAULT. Operators must explicitly opt in to
    # calling a real external scorer via --no-dry-run to avoid accidental
    # API calls or repo interactions.
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Disable dry-run. Real scorer invocation — requires --clone-dir.",
    )
    parser.set_defaults(dry_run=True)
    parser.add_argument(
        "--clone-dir",
        type=Path,
        default=None,
        help="Path to the shallow-cloned external repo (real runs only).",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"CRES-3: Native Replay — benchmark={args.benchmark}")
    print("=" * 60)

    _episodes, records = load_cached_verdicts()
    rng = random.Random(args.seed)
    sample_n = min(args.pilot_n, len(records))
    sampled = rng.sample(records, sample_n)

    if args.benchmark == "medagentbench":
        results = run_medagentbench(sampled, args.dry_run, args.clone_dir)
    else:
        print(
            f"ERROR: benchmark {args.benchmark} adapter not yet implemented.",
            file=sys.stderr,
        )
        return 3

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "stub" if args.dry_run else "native"
    out_path = OUTPUT_DIR / f"cres_3_{args.benchmark}_{suffix}_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nn_evaluated={results['n_evaluated']}, rejected={results['n_rejected']}")
    print(f"kappa(native, proxy) = {results['cohen_kappa_native_vs_proxy']:.4f}")
    print(f"raw agreement        = {results['raw_agreement']:.4f}")
    print(f"Saved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
