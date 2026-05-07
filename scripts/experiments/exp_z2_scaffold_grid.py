#!/usr/bin/env python3
"""Z.2: 8 × 4 (model × scaffold) cell aggregation + Friedman χ² update.

Reads 32 cells from results/full_706_v6_aliasfix_* (ReAct) and
results/full_706_v6_scaffolds_* (Direct / Checklist / Tooluse).
Each cell aggregates ~2118 episode JSONs (706 scenarios × 3 runs).
Per-cell metric = mean `compliance_score` (TCC's primary output).

Friedman χ² is computed across scaffolds (4 groups) with models as
blocks (n=8), replacing the paper's current χ²=1.0 (p=0.80, n=3)
number. AO-FA band is reported per scaffold as the [min, max] range
of cell means.

Output: evidence_pack/ex_w8_crossmodel/w8_results_v2.json + macros.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import statistics
import sys

from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "evidence_pack" / "ex_w8_crossmodel"

SCAFFOLD_DIRS = {
    "react": ROOT / "results" / "full_706_v6_aliasfix_20260422_0048",
    "direct": ROOT / "results" / "full_706_v6_scaffolds_20260422_1022",
    "checklist": ROOT / "results" / "full_706_v6_scaffolds_20260422_1022",
    "tooluse": ROOT / "results" / "full_706_v6_scaffolds_20260422_1022",
}


def _iter_cell_files(model: str, scaffold: str) -> list[Path]:
    base = SCAFFOLD_DIRS[scaffold]
    if not base.exists():
        return []
    subdir_name = f"{model}_{scaffold}" if scaffold != "react" else f"{model}_react"
    sub = base / subdir_name
    if not sub.exists():
        return []
    return sorted(sub.glob("*.json"))


def _cell_metrics(files: list[Path]) -> dict:
    scores: list[float] = []
    viol_counts: list[int] = []
    compliance_pass_count = 0  # compliance == 1.0 exactly
    v4_hard_proxy_pass = 0     # total_violations == 0 (TCC pass proxy)
    for f in files:
        try:
            d = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        s = float(d.get("compliance_score") or 0.0)
        tv = int(d.get("total_violations") or 0)
        scores.append(s)
        viol_counts.append(tv)
        if s >= 1.0:
            compliance_pass_count += 1
        if tv == 0:
            v4_hard_proxy_pass += 1
    n = len(scores)
    if n == 0:
        return {"n": 0, "compliance_mean": 0.0, "compliance_pass_rate": 0.0, "v4_hard_pass_rate": 0.0, "viol_mean": 0.0}
    return {
        "n": n,
        "compliance_mean": round(statistics.fmean(scores), 4),
        "compliance_pass_rate": round(compliance_pass_count / n, 4),
        "v4_hard_pass_rate": round(v4_hard_proxy_pass / n, 4),
        "viol_mean": round(statistics.fmean(viol_counts), 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Z.2 scaffold × model grid")
    parser.add_argument("--out-dir", type=str, default=str(OUT_DIR))
    args = parser.parse_args()

    models = [
        "deepseek_r1_7b",
        "gemma31b",
        "nemotron30b",
        "oss120b",
        "qwen27b",
        "qwen35b",
        "qwen397b",
        "qwen4b",
    ]
    scaffolds = ["react", "direct", "checklist", "tooluse"]

    print(f"Loading 8 × 4 = 32 cells ...")
    grid: dict[tuple[str, str], dict] = {}
    for m in models:
        for s in scaffolds:
            files = _iter_cell_files(m, s)
            grid[(m, s)] = _cell_metrics(files)
            print(
                f"  {m:<15s} × {s:<10s}: n={grid[(m, s)]['n']:>5d}  "
                f"compliance_mean={grid[(m, s)]['compliance_mean']:.4f}  "
                f"v4_hard_pass={grid[(m, s)]['v4_hard_pass_rate']:.4f}"
            )

    # Friedman χ² on compliance_mean: 4 scaffolds (groups), 8 models (blocks)
    mat = [
        [grid[(m, s)]["compliance_mean"] for s in scaffolds] for m in models
    ]
    fried = stats.friedmanchisquare(*zip(*mat))
    chi2 = float(fried.statistic)
    p = float(fried.pvalue)
    print(f"\nFriedman χ² (compliance_mean, 8 models × 4 scaffolds): chi2={chi2:.4f}  p={p:.4g}")

    # Also on v4_hard_pass
    mat_v4 = [
        [grid[(m, s)]["v4_hard_pass_rate"] for s in scaffolds] for m in models
    ]
    fried_v4 = stats.friedmanchisquare(*zip(*mat_v4))
    chi2_v4 = float(fried_v4.statistic)
    p_v4 = float(fried_v4.pvalue)
    print(f"Friedman χ² (v4_hard_pass_rate):                    chi2={chi2_v4:.4f}  p={p_v4:.4g}")

    # AO-FA band: min/max across cells per scaffold
    bands: dict[str, dict] = {}
    for s in scaffolds:
        means = [grid[(m, s)]["compliance_mean"] for m in models]
        bands[s] = {
            "min": round(min(means), 4),
            "max": round(max(means), 4),
            "range_pp": round(100.0 * (max(means) - min(means)), 2),
            "mean": round(statistics.fmean(means), 4),
        }
    print("\nAO-FA band per scaffold (compliance_mean across 8 models):")
    for s, b in bands.items():
        print(f"  {s:<10s}: [{b['min']:.4f}, {b['max']:.4f}]  range {b['range_pp']:.2f} pp  mean {b['mean']:.4f}")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "models": models,
        "scaffolds": scaffolds,
        "grid": {f"{m}__{s}": grid[(m, s)] for m in models for s in scaffolds},
        "friedman_compliance": {"chi2": round(chi2, 4), "p_value": p, "n_models": len(models), "n_scaffolds": len(scaffolds)},
        "friedman_v4_hard": {"chi2": round(chi2_v4, 4), "p_value": p_v4},
        "scaffold_band": bands,
    }
    (out / "w8_results_v2.json").write_text(json.dumps(summary, indent=2) + "\n")

    macros = [
        "% Auto-generated by exp_z2_scaffold_grid.py",
        f"\\providecommand{{\\wEightFriedmanChiV2}}{{{chi2:.4f}}}",
        f"\\providecommand{{\\wEightFriedmanPV2}}{{{p:.4g}}}",
        f"\\providecommand{{\\wEightFriedmanNV2}}{{{len(models)}}}",
        f"\\providecommand{{\\wEightFriedmanChiVhV2}}{{{chi2_v4:.4f}}}",
        f"\\providecommand{{\\wEightFriedmanPVhV2}}{{{p_v4:.4g}}}",
    ]
    for s in scaffolds:
        b = bands[s]
        macros.append(f"\\providecommand{{\\wEightBand{s.capitalize()}Min}}{{{b['min']:.4f}}}")
        macros.append(f"\\providecommand{{\\wEightBand{s.capitalize()}Max}}{{{b['max']:.4f}}}")
        macros.append(f"\\providecommand{{\\wEightBand{s.capitalize()}RangePp}}{{{b['range_pp']:.2f}}}")
    (out / "w8_scaffold_macros_v2.tex").write_text("\n".join(macros) + "\n")
    print(f"\nSaved: {out}/w8_results_v2.json + w8_scaffold_macros_v2.tex")


if __name__ == "__main__":
    main()
