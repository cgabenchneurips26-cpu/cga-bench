#!/usr/bin/env python3
"""Merge CRES-1A shard results and compute overall Cohen's kappa.

Loads all cres_1a_full_shard*of*_results.json files, concatenates
per_record arrays, recomputes kappa/agreement, and writes:
  - cres_1a_full_merged_results.json  (overall + per-record)
  - cres_1a_macros.tex               (LaTeX macros)

Usage:
    python scripts/experiments/merge_cres_1a_shards.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "evidence_pack" / "cres_1a"


def cohen_kappa_binary(labels_a: list[int], labels_b: list[int]) -> float:
    """Cohen's kappa for two binary label sequences."""
    if len(labels_a) != len(labels_b) or not labels_a:
        return float("nan")
    n = len(labels_a)
    observed_agree = sum(1 for a, b in zip(labels_a, labels_b, strict=True) if a == b) / n
    p_a = sum(labels_a) / n
    p_b = sum(labels_b) / n
    expected_agree = p_a * p_b + (1 - p_a) * (1 - p_b)
    if expected_agree >= 1.0:
        return 1.0 if observed_agree == 1.0 else 0.0
    return (observed_agree - expected_agree) / (1 - expected_agree)


def kappa_se(kappa: float, n: int, p_e: float) -> float:
    """Approximate standard error for Cohen's kappa (Fleiss 1981)."""
    if p_e >= 1.0 or n <= 0:
        return float("nan")
    return math.sqrt(p_e / (n * (1 - p_e)))


def main() -> int:
    """Merge CRES-1A shard results and write overall kappa + LaTeX macros."""
    shard_files = sorted(EVIDENCE_DIR.glob("cres_1a_full_shard*of*_results.json"))
    if not shard_files:
        print("ERROR: No shard result files found in", EVIDENCE_DIR)
        return 1

    print(f"Found {len(shard_files)} shard files:")
    for f in shard_files:
        print(f"  {f.name}")

    all_records: list[dict] = []
    total_tokens = 0
    shard_kappas: list[dict] = []

    for sf in shard_files:
        with open(sf) as f:
            data = json.load(f)
        n = data["n_evaluated"]
        k = data["cohen_kappa_tcc_vs_free"]
        a = data["raw_agreement"]
        total_tokens += data.get("total_tokens", 0)
        all_records.extend(data["per_record"])
        shard_kappas.append(
            {
                "shard": sf.name,
                "n": n,
                "kappa": round(k, 4),
                "agreement": round(a, 4),
            }
        )
        print(f"  {sf.name}: n={n}, kappa={k:.4f}, agreement={a:.4f}")

    # Recompute overall kappa from merged records
    tcc_labels = [1 if r["tcc_pass"] else 0 for r in all_records]
    free_labels = [1 if r["free_pass"] else 0 for r in all_records]

    overall_kappa = cohen_kappa_binary(tcc_labels, free_labels)
    n_total = len(tcc_labels)
    overall_agreement = (
        sum(1 for a, b in zip(tcc_labels, free_labels, strict=True) if a == b) / n_total
        if n_total > 0
        else float("nan")
    )

    # Marginals
    tcc_pass_rate = sum(tcc_labels) / n_total if n_total > 0 else 0
    free_pass_rate = sum(free_labels) / n_total if n_total > 0 else 0
    p_e = tcc_pass_rate * free_pass_rate + (1 - tcc_pass_rate) * (1 - free_pass_rate)

    # SE and 95% CI
    se = kappa_se(overall_kappa, n_total, p_e)
    ci_lo = overall_kappa - 1.96 * se
    ci_hi = overall_kappa + 1.96 * se

    # Confusion matrix
    tp = sum(1 for a, b in zip(tcc_labels, free_labels, strict=True) if a == 1 and b == 1)
    tn = sum(1 for a, b in zip(tcc_labels, free_labels, strict=True) if a == 0 and b == 0)
    fp = sum(1 for a, b in zip(tcc_labels, free_labels, strict=True) if a == 0 and b == 1)
    fn = sum(1 for a, b in zip(tcc_labels, free_labels, strict=True) if a == 1 and b == 0)

    # Per-evaluator pass rates
    tcc_pass_n = sum(tcc_labels)
    free_pass_n = sum(free_labels)

    print(f"\n{'=' * 60}")
    print(f"MERGED RESULTS ({n_total} records from {len(shard_files)} shards)")
    print(f"{'=' * 60}")
    print(f"  Overall kappa:     {overall_kappa:.4f}")
    print(f"  95% CI:            [{ci_lo:.4f}, {ci_hi:.4f}]")
    print(f"  Raw agreement:     {overall_agreement:.4f} ({overall_agreement * 100:.1f}%)")
    print(f"  TCC pass rate:     {tcc_pass_rate:.4f} ({tcc_pass_n}/{n_total})")
    print(f"  Free pass rate:    {free_pass_rate:.4f} ({free_pass_n}/{n_total})")
    print(f"  Confusion: TP={tp} TN={tn} FP={fp} FN={fn}")
    print(f"  Total tokens:      {total_tokens:,}")

    # Save merged results (without per_record to keep file manageable)
    merged = {
        "experiment": "CRES-1A",
        "description": "Catalogue-free LLM judge vs TCC verdicts (merged shards)",
        "n_total": n_total,
        "n_shards": len(shard_files),
        "cohen_kappa": round(overall_kappa, 4),
        "kappa_se": round(se, 4),
        "kappa_ci_95": [round(ci_lo, 4), round(ci_hi, 4)],
        "raw_agreement": round(overall_agreement, 4),
        "tcc_pass_rate": round(tcc_pass_rate, 4),
        "free_pass_rate": round(free_pass_rate, 4),
        "confusion_matrix": {"TP": tp, "TN": tn, "FP": fp, "FN": fn},
        "total_tokens": total_tokens,
        "per_shard": shard_kappas,
    }

    out_json = EVIDENCE_DIR / "cres_1a_full_merged_results.json"
    with open(out_json, "w") as f:
        json.dump(merged, f, indent=2)
    print(f"\nSaved merged results to {out_json}")

    # Generate LaTeX macros
    macros = [
        f"\\providecommand{{\\cresOneAKappa}}{{{overall_kappa:.3f}}}",
        f"\\providecommand{{\\cresOneAKappaCI}}{{{ci_lo:.3f}--{ci_hi:.3f}}}",
        f"\\providecommand{{\\cresOneAAgreement}}{{{overall_agreement * 100:.1f}}}",
        f"\\providecommand{{\\cresOneAN}}{{{n_total}}}",
        f"\\providecommand{{\\cresOneATCCPassRate}}{{{tcc_pass_rate * 100:.1f}}}",
        f"\\providecommand{{\\cresOneAFreePassRate}}{{{free_pass_rate * 100:.1f}}}",
        f"\\providecommand{{\\cresOneATP}}{{{tp}}}",
        f"\\providecommand{{\\cresOneATN}}{{{tn}}}",
        f"\\providecommand{{\\cresOneAFP}}{{{fp}}}",
        f"\\providecommand{{\\cresOneAFN}}{{{fn}}}",
        f"\\providecommand{{\\cresOneATokens}}{{{total_tokens / 1e6:.1f}M}}",
    ]
    out_tex = EVIDENCE_DIR / "cres_1a_macros.tex"
    with open(out_tex, "w") as f:
        f.write("% CRES-1A: Catalogue-Free LLM Judge — merged shards\n")
        f.write(f"% Generated from {len(shard_files)} shards, {n_total} records\n")
        for m in macros:
            f.write(m + "\n")
    print(f"Saved macros to {out_tex}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
