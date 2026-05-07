#!/usr/bin/env python3
"""T2-8: Alternative correlation metrics beyond Kendall τ (canonical-6).

We already report Kendall τ-b / phi in c6_audit_guided_selection.json.
This script recomputes pair-wise agreement with four additional metrics
and checks that all of them reproduce the within > cross ordering.

Metrics:
  - Spearman ρ         (rank correlation; degenerates toward τ on binary)
  - Pearson r          (for binary == phi == τ-b, but we compute it
                        explicitly from numpy for schema-level sanity)
  - Cohen's κ          (chance-adjusted agreement, 2-level)
  - Matthews φ (MCC)   (balanced 2x2 correlation)

For each metric we report same/cross nondegen means and the
within-cross gap. A single within ≤ cross reversal across any metric
would flag brittleness in the Kendall-τ result.

Canonical-6 scope.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import itertools
import json
from pathlib import Path
import statistics
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audit.shims._verdict_cache import load_w8_episodes  # noqa: E402
from scripts.experiments.exp_piclass_heldout import (  # noqa: E402
    CANONICAL_SIX,
    _verdict_col,
)

OUT_DIR = ROOT / "evidence_pack" / "audit"
C6_PATH = ROOT / "evidence_pack" / "audit" / "c6_audit_guided_selection.json"
NONDEGEN_EPS = 1e-3


def _cohens_kappa(a: np.ndarray, b: np.ndarray) -> float:
    po = float(np.mean(a == b))
    p1a = float(np.mean(a))
    p1b = float(np.mean(b))
    pe = p1a * p1b + (1 - p1a) * (1 - p1b)
    if 1 - pe <= 0:
        return 0.0
    return (po - pe) / (1 - pe)


def _phi(a: np.ndarray, b: np.ndarray) -> float:
    tp = float(np.sum(a & b))
    fn = float(np.sum(a & ~b))
    fp = float(np.sum(~a & b))
    tn = float(np.sum(~a & ~b))
    denom = np.sqrt((tp + fn) * (fp + tn) * (tp + fp) * (fn + tn))
    return 0.0 if denom == 0 else (tp * tn - fn * fp) / float(denom)


def _pair_metrics(va: list[bool], vb: list[bool]) -> dict[str, float]:
    from scipy import stats

    a = np.array(va, dtype=bool)
    b = np.array(vb, dtype=bool)
    with np.errstate(invalid="ignore"):
        kendall = stats.kendalltau(a, b, variant="b").correlation
        spearman = stats.spearmanr(a, b).correlation
        pearson = stats.pearsonr(a.astype(float), b.astype(float))[0]
    vals = {
        "kendall": float(kendall) if np.isfinite(kendall) else 0.0,
        "spearman": float(spearman) if np.isfinite(spearman) else 0.0,
        "pearson": float(pearson) if np.isfinite(pearson) else 0.0,
        "kappa": _cohens_kappa(a, b),
        "phi": _phi(a, b),
    }
    return vals


def _same_cross(
    pair_rows: list[dict], pi_classes: dict[str, str], metric: str
) -> tuple[float, float]:
    same, cross = [], []
    for p in pair_rows:
        v = p["metrics"][metric]
        if abs(v) <= NONDEGEN_EPS:
            continue
        if pi_classes[p["evaluator_a"]] == pi_classes[p["evaluator_b"]]:
            same.append(v)
        else:
            cross.append(v)
    s = statistics.fmean(same) if same else 0.0
    c = statistics.fmean(cross) if cross else 0.0
    return s, c


def main() -> None:
    parser = argparse.ArgumentParser(description="T2-8 alt correlation metrics (canonical-6)")
    parser.add_argument("--out-dir", type=str, default=str(OUT_DIR))
    args = parser.parse_args()

    with open(C6_PATH) as f:
        pi_classes = json.load(f)["pi_classes"]
    eps = load_w8_episodes()
    ep_ids = sorted(eps.keys())
    print(f"Computing canonical-6 verdict vectors on {len(ep_ids)} W8 episodes ...")
    verdicts = {n: [_verdict_col(eps[e], n) for e in ep_ids] for n in CANONICAL_SIX}

    pair_rows: list[dict] = []
    for a, b in itertools.combinations(CANONICAL_SIX, 2):
        metrics = _pair_metrics(verdicts[a], verdicts[b])
        pair_rows.append(
            {
                "evaluator_a": a,
                "evaluator_b": b,
                "pi_class_a": pi_classes[a],
                "pi_class_b": pi_classes[b],
                "metrics": {k: round(v, 4) for k, v in metrics.items()},
            }
        )

    summary: dict[str, dict] = {}
    metric_names = ("kendall", "spearman", "pearson", "kappa", "phi")
    header = f"{'metric':<10s} {'same':>8s} {'cross':>8s} {'gap':>8s}"
    print(f"\n{header}")
    print("-" * len(header))
    for m in metric_names:
        s, c = _same_cross(pair_rows, pi_classes, m)
        gap = s - c
        summary[m] = {"same": round(s, 4), "cross": round(c, 4), "gap": round(gap, 4)}
        print(f"{m:<10s} {s:>8.4f} {c:>8.4f} {gap:>+8.4f}")

    n_reversal = sum(1 for m in metric_names if summary[m]["gap"] <= 0)
    print(f"\nReversal count (within ≤ cross) across metrics: {n_reversal}/{len(metric_names)}")

    result = {
        "timestamp": datetime.now(UTC).isoformat(),
        "canonical_six": list(CANONICAL_SIX),
        "pi_classes": pi_classes,
        "metrics": list(metric_names),
        "pairs": pair_rows,
        "summary": summary,
        "n_reversals": n_reversal,
    }
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "piclass_alt_metrics_canonical6_results.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    lines = ["% Auto-generated by scripts/experiments/exp_piclass_alt_metrics.py"]
    for m in metric_names:
        M = m.capitalize()
        lines.append(f"\\providecommand{{\\piAlt{M}Same}}{{{summary[m]['same']:.4f}}}")
        lines.append(f"\\providecommand{{\\piAlt{M}Cross}}{{{summary[m]['cross']:.4f}}}")
        lines.append(f"\\providecommand{{\\piAlt{M}Gap}}{{{summary[m]['gap']:.4f}}}")
    lines.append(f"\\providecommand{{\\piAltReversalCount}}{{{n_reversal}}}")
    (out / "piclass_alt_metrics_canonical6_macros.tex").write_text("\n".join(lines) + "\n")
    print("Saved: piclass_alt_metrics_canonical6_{results.json, macros.tex}")


if __name__ == "__main__":
    main()
