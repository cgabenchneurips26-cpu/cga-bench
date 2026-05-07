#!/usr/bin/env python3
"""T2-9 (pragmatic form): π-class vs marginal-BSR independence on extended pool.

The original T2-9 plan called for constructing synthetic adversarial
evaluators with identical marginal BSR but different pi-classes. On
the canonical-6 pool this is combinatorially constrained (dxem is
all-True, so any same-marginal synthesis collapses to the same
vector). We pivot to a direct empirical question on the existing
19-eval extended pool:

  "Does marginal BSR predict pi-class?"

If the answer is yes, the audit taxonomy is reducible to a scalar
marginal BSR cutoff — a substantive reviewer attack (A6). If the
answer is no (low ordinal correlation + cross-class BSR overlap), the
two signals are distinct.

We use the extended pool because the question is about whether the
taxonomy disentangles from a single summary statistic. The canonical-
6 numbers remain the headline paper claim; this test informs whether
the taxonomy *structure* is a reparameterisation of BSR.

Outputs:
  evidence_pack/audit/piclass_bsr_independence_results.json
  evidence_pack/audit/piclass_bsr_independence_macros.tex
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import statistics
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "evidence_pack" / "audit"
POOL_PATH = ROOT / "evidence_pack" / "audit" / "piclass_pool_expand_selection_results.json"
VERIFY_PATH = ROOT / "/tmp/cga_audit_verify/verify_summary.json"

PI_ORDER = ["term", "aset", "nord", "nctx"]


def _load_pool() -> tuple[dict[str, str], list[str]]:
    with open(POOL_PATH) as f:
        data = json.load(f)
    return data["pi_classes"], data["evaluators"]


def _compute_marginal_bsr(names: list[str]) -> dict[str, float]:
    """BSR of each shim vs v4_hard reference on the W8 corpus."""
    from audit.shims import SHIM_REGISTRY
    from audit.shims._verdict_cache import get_verdict, load_w8_episodes

    eps = load_w8_episodes()
    ep_ids = sorted(eps.keys())
    ref = [get_verdict(eid, "v4_hard") for eid in ep_ids]
    out: dict[str, float] = {}
    for n in names:
        ev = SHIM_REGISTRY[n]()
        verd = [ev.verdict({"episode_id": eid}) for eid in ep_ids]
        n_dis = sum(1 for v, r in zip(verd, ref) if v != r)
        out[n] = round(n_dis / len(ep_ids), 4)
    return out


def _class_bsr_distribution(
    bsr: dict[str, float], pi: dict[str, str]
) -> dict[str, dict]:
    buckets: dict[str, list[float]] = {}
    for n, b in bsr.items():
        buckets.setdefault(pi[n], []).append(b)
    out: dict[str, dict] = {}
    for c, vals in buckets.items():
        out[c] = {
            "n": len(vals),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
            "mean": round(statistics.fmean(vals), 4),
            "sd": round(statistics.pstdev(vals), 4) if len(vals) > 1 else 0.0,
        }
    return out


def _overlap_range(class_dist: dict[str, dict]) -> dict:
    """Do any two classes have overlapping BSR ranges?"""
    classes = sorted(class_dist.keys())
    overlaps: list[tuple[str, str]] = []
    for i in range(len(classes)):
        for j in range(i + 1, len(classes)):
            a, b = class_dist[classes[i]], class_dist[classes[j]]
            if a["min"] <= b["max"] and b["min"] <= a["max"]:
                overlaps.append((classes[i], classes[j]))
    return {
        "pairs": [list(p) for p in overlaps],
        "n_overlapping": len(overlaps),
        "total_pairs": len(classes) * (len(classes) - 1) // 2,
    }


def _ordinal_correlation(
    bsr: dict[str, float], pi: dict[str, str]
) -> dict:
    from scipy import stats

    names = sorted(bsr.keys())
    b = [bsr[n] for n in names]
    p = [PI_ORDER.index(pi[n]) if pi[n] in PI_ORDER else 0 for n in names]
    with np.errstate(invalid="ignore"):
        s = stats.spearmanr(b, p)
    return {
        "spearman_rho": round(float(s.correlation) if np.isfinite(s.correlation) else 0.0, 4),
        "spearman_p": round(float(s.pvalue) if np.isfinite(s.pvalue) else 1.0, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="T2-9 pragmatic: pi-class vs marginal BSR")
    parser.add_argument("--out-dir", type=str, default=str(OUT_DIR))
    args = parser.parse_args()

    pi, names = _load_pool()
    print(f"Extended pool: {len(names)} evaluators")
    bsr = _compute_marginal_bsr(names)
    cdist = _class_bsr_distribution(bsr, pi)
    overlap = _overlap_range(cdist)
    rho = _ordinal_correlation(bsr, pi)

    print("\nPer-class BSR distribution:")
    for c, s in cdist.items():
        print(
            f"  {c:>5s} (n={s['n']:>2d}): mean={s['mean']:.4f}  "
            f"sd={s['sd']:.4f}  range=[{s['min']:.4f}, {s['max']:.4f}]"
        )
    print(
        f"\nOverlapping pi-class pairs (by BSR range): "
        f"{overlap['n_overlapping']}/{overlap['total_pairs']}"
    )
    print(f"Spearman ρ(BSR, pi-class ordinal): {rho['spearman_rho']}  (p={rho['spearman_p']})")

    result = {
        "timestamp": datetime.now(UTC).isoformat(),
        "n_evaluators": len(names),
        "pi_classes": pi,
        "bsr": bsr,
        "class_distribution": cdist,
        "range_overlap": overlap,
        "ordinal_correlation": rho,
    }
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "piclass_bsr_independence_results.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "% Auto-generated by scripts/experiments/exp_piclass_bsr_independence.py",
        f"\\providecommand{{\\piBsrIndepNEval}}{{{len(names)}}}",
        f"\\providecommand{{\\piBsrIndepRho}}{{{rho['spearman_rho']:.4f}}}",
        f"\\providecommand{{\\piBsrIndepRhoP}}{{{rho['spearman_p']:.4f}}}",
        f"\\providecommand{{\\piBsrIndepNOverlap}}{{{overlap['n_overlapping']}}}",
        f"\\providecommand{{\\piBsrIndepNTotal}}{{{overlap['total_pairs']}}}",
    ]
    for c in sorted(cdist.keys()):
        C = c.capitalize()
        s = cdist[c]
        lines.append(f"\\providecommand{{\\piBsrIndep{C}Mean}}{{{s['mean']:.4f}}}")
        lines.append(f"\\providecommand{{\\piBsrIndep{C}Min}}{{{s['min']:.4f}}}")
        lines.append(f"\\providecommand{{\\piBsrIndep{C}Max}}{{{s['max']:.4f}}}")
    (out / "piclass_bsr_independence_macros.tex").write_text("\n".join(lines) + "\n")
    print("Saved: piclass_bsr_independence_{results.json, macros.tex}")


if __name__ == "__main__":
    main()
