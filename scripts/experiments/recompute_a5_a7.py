"""Recompute A5 (WITHIN-only episode breakdown) + A7 (CRES-1D bootstrap CI).

A5: per-domain WITHIN-only count on V6 base 16,944 substrate. Verifies macro
    \\instrWithinOnlyN against the canonical verdict_matrix_v6_full.json
    (v4_hard = commission/timing/sequence only).

A7: re-runs paired bootstrap on cv-fold AUC gaps for cresOneD coverage_free
    vs asc_only models. Existing CI [3.89, 4.40] does NOT contain point
    4.74 — investigate and produce corrected CI.

Outputs:
  - evidence_pack/analysis/a5_within_only_breakdown.json
  - evidence_pack/analysis/a7_cres_1d_bootstrap_corrected.json
  - paper/auto_numbers_a5_a7_corrected.tex
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import random
import statistics

REPO = Path(__file__).resolve().parents[2]
VERDICT_MATRIX = REPO / "evidence_pack" / "analysis" / "verdict_matrix_v6_full.json"
V6_MANIFEST = REPO / "evidence_pack" / "frontier" / "w8_706_manifest.json"
CRES_1D = REPO / "evidence_pack" / "cres_1d" / "cres_1d_results.json"
OUT_A5 = REPO / "evidence_pack" / "analysis" / "a5_within_only_breakdown.json"
OUT_A7 = REPO / "evidence_pack" / "analysis" / "a7_cres_1d_bootstrap_corrected.json"
OUT_TEX = REPO / "paper" / "auto_numbers_a5_a7_corrected.tex"


def _domain_from_scenario_id(sid: str) -> str:
    """Heuristic CPG-domain extraction from scenario_id prefix."""
    parts = sid.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}_{parts[1]}"
    return parts[0]


def recompute_a5() -> dict:
    print("=" * 60)
    print("A5: WITHIN-only breakdown (V6 base 16,944 substrate)")
    print("=" * 60)
    m = json.load(open(VERDICT_MATRIX))
    v6_ids = {s["scenario_id"] for s in json.load(open(V6_MANIFEST))["scenarios"]}
    eps = [e for e in m["per_episode"] if e["scenario_id"] in v6_ids]

    n_total = len(eps)
    hard = [e for e in eps if e.get("v4_hard")]
    within_only = [e for e in hard if set(e.get("viol_types", [])) == {"WITHIN"}]
    within_with_others = [
        e for e in hard if "WITHIN" in e.get("viol_types", []) and len(set(e.get("viol_types", []))) > 1
    ]
    no_within_hard = [e for e in hard if "WITHIN" not in set(e.get("viol_types", []))]

    print(f"  Total V6 base eps: {n_total:,}")
    print(f"  v4_hard:           {len(hard):,}")
    print(f"  WITHIN-only:       {len(within_only):,} (macro claim: 6921; recomputed: {len(within_only)})")
    print(f"  WITHIN+other:      {len(within_with_others):,} (macro claim: 1632)")
    print(f"  No-WITHIN hard:    {len(no_within_hard):,}")
    print(f"  Sum check:         {len(within_only) + len(within_with_others) + len(no_within_hard)} == {len(hard)}")

    # Per-domain breakdown
    dist_within_only = Counter(_domain_from_scenario_id(e["scenario_id"]) for e in within_only)
    dist_hard_total = Counter(_domain_from_scenario_id(e["scenario_id"]) for e in hard)
    dist_all = Counter(_domain_from_scenario_id(e["scenario_id"]) for e in eps)

    per_domain = []
    for dom in dist_all:
        per_domain.append(
            {
                "domain": dom,
                "n_episodes": dist_all[dom],
                "n_v4_hard": dist_hard_total.get(dom, 0),
                "n_within_only": dist_within_only.get(dom, 0),
                "within_only_rate_pct": round(100.0 * dist_within_only.get(dom, 0) / max(dist_all[dom], 1), 2),
            }
        )
    per_domain.sort(key=lambda r: -r["n_within_only"])

    print("\n  Top 10 domains by WITHIN-only count:")
    for r in per_domain[:10]:
        print(
            f"    {r['domain']:30s} n={r['n_episodes']:5d}  v4_hard={r['n_v4_hard']:4d}  within_only={r['n_within_only']:4d}  ({r['within_only_rate_pct']:.1f}%)"
        )

    rate_pct = round(100.0 * len(within_only) / n_total, 2)
    return {
        "n_episodes": n_total,
        "n_v4_hard": len(hard),
        "n_within_only": len(within_only),
        "n_within_with_others": len(within_with_others),
        "n_no_within_hard": len(no_within_hard),
        "within_only_rate_pct": rate_pct,
        "macro_claim_within_only": 6921,
        "delta_vs_macro": len(within_only) - 6921,
        "delta_vs_macro_pct": round(100.0 * (len(within_only) - 6921) / 6921, 2),
        "n_unique_domains": len(per_domain),
        "per_domain_top10": per_domain[:10],
        "per_domain_full": per_domain,
        "v4_hard_definition": m["metadata"]["hard_viol_definition"],
    }


def _paired_bootstrap_ci(
    cf_folds: list[float],
    asc_folds: list[float],
    n_bootstrap: int = 10000,
    seed: int = 42,
) -> dict:
    """Paired bootstrap CI on per-fold AUC gap (cf - asc).

    Resamples folds with replacement (n=5 per resample), computes mean
    gap on each resample, returns 2.5/97.5 percentile CI.
    """
    assert len(cf_folds) == len(asc_folds), "fold count mismatch"
    rng = random.Random(seed)
    n_folds = len(cf_folds)
    gaps = [cf - asc for cf, asc in zip(cf_folds, asc_folds)]
    point = statistics.mean(gaps)

    bootstrap_means = []
    for _ in range(n_bootstrap):
        idx = [rng.randint(0, n_folds - 1) for _ in range(n_folds)]
        resampled = [gaps[i] for i in idx]
        bootstrap_means.append(statistics.mean(resampled))

    bootstrap_means.sort()
    lo = bootstrap_means[int(0.025 * n_bootstrap)]
    hi = bootstrap_means[int(0.975 * n_bootstrap)]
    return {
        "point_estimate": round(point, 6),
        "point_pp": round(100 * point, 2),
        "ci_95_lo": round(lo, 6),
        "ci_95_lo_pp": round(100 * lo, 2),
        "ci_95_hi": round(hi, 6),
        "ci_95_hi_pp": round(100 * hi, 2),
        "ci_contains_point": lo <= point <= hi,
        "bootstrap_n": n_bootstrap,
        "method": "paired bootstrap on per-fold gap (n=5 folds, seed=42)",
        "per_fold_gaps": [round(g, 6) for g in gaps],
        "per_fold_pp": [round(100 * g, 2) for g in gaps],
    }


def recompute_a7() -> dict:
    print("\n" + "=" * 60)
    print("A7: CRES-1D bootstrap CI re-run (paired fold-level)")
    print("=" * 60)
    r = json.load(open(CRES_1D))
    cf_folds = r["coverage_free_model"]["fold_aucs"]
    asc_folds = r["asc_only_model"]["fold_aucs"]
    clean_folds = r["clean_model"]["fold_aucs"]
    stored = r["coverage_free_model"]["delta_vs_asc"]

    print(f"  Stored point: {stored['point_estimate']:.6f} = {100 * stored['point_estimate']:.2f} pp")
    print(
        f"  Stored CI:    [{stored['ci_95_lo']:.6f}, {stored['ci_95_hi']:.6f}] = [{100 * stored['ci_95_lo']:.2f}, {100 * stored['ci_95_hi']:.2f}] pp"
    )
    print(f"  Stored CI contains point: {stored['ci_95_lo'] <= stored['point_estimate'] <= stored['ci_95_hi']}")

    print("\n  Recompute (paired bootstrap on 5 cv folds, n=10000):")
    cf_vs_asc = _paired_bootstrap_ci(cf_folds, asc_folds, n_bootstrap=10000)
    print("    coverage_free vs asc_only:")
    print(f"      point: {cf_vs_asc['point_pp']:.2f} pp")
    print(f"      CI:    [{cf_vs_asc['ci_95_lo_pp']:.2f}, {cf_vs_asc['ci_95_hi_pp']:.2f}] pp")
    print(f"      CI contains point: {cf_vs_asc['ci_contains_point']}")
    print(f"      Per-fold gaps: {cf_vs_asc['per_fold_pp']}")

    clean_vs_asc = _paired_bootstrap_ci(clean_folds, asc_folds, n_bootstrap=10000)
    print("    clean vs asc_only:")
    print(f"      point: {clean_vs_asc['point_pp']:.2f} pp")
    print(f"      CI:    [{clean_vs_asc['ci_95_lo_pp']:.2f}, {clean_vs_asc['ci_95_hi_pp']:.2f}] pp")
    print(f"      CI contains point: {clean_vs_asc['ci_contains_point']}")

    clean_vs_cf = _paired_bootstrap_ci(clean_folds, cf_folds, n_bootstrap=10000)
    print("    clean vs coverage_free (control):")
    print(f"      point: {clean_vs_cf['point_pp']:.2f} pp")
    print(f"      CI:    [{clean_vs_cf['ci_95_lo_pp']:.2f}, {clean_vs_cf['ci_95_hi_pp']:.2f}] pp")

    return {
        "stored": stored,
        "stored_ci_contains_point": stored["ci_95_lo"] <= stored["point_estimate"] <= stored["ci_95_hi"],
        "recompute_method": "paired bootstrap on per-fold AUC gap, n=10000 resamples, seed=42",
        "coverage_free_vs_asc": cf_vs_asc,
        "clean_vs_asc": clean_vs_asc,
        "clean_vs_coverage_free": clean_vs_cf,
        "fold_aucs": {
            "clean": clean_folds,
            "asc_only": asc_folds,
            "coverage_free": cf_folds,
        },
    }


def emit_macros(a5: dict, a7: dict) -> str:
    cf = a7["coverage_free_vs_asc"]
    cv_asc = a7["clean_vs_asc"]
    return (
        "\n".join(
            [
                "% A5 + A7 corrected macros (auto_numbers_a5_a7_corrected.tex)",
                "% Source: verdict_matrix_v6_full.json (v4_hard = commission/timing/sequence)",
                "% Source: cres_1d_results.json (paired bootstrap on 5-fold AUC gap, n=10000)",
                "",
                "% --- A5: WITHIN-only on V6 base 16,944 ---",
                f"\\providecommand{{\\instrWithinOnlyN}}{{{a5['n_within_only']}}}",
                f"\\providecommand{{\\instrFullHard}}{{{a5['n_v4_hard']}}}",
                f"\\providecommand{{\\withinOnlyRate}}{{{a5['within_only_rate_pct']:.1f}}}",
                f"\\providecommand{{\\instrNonWithinHard}}{{{a5['n_no_within_hard']}}}",
                f"\\providecommand{{\\instrWithinPlusOther}}{{{a5['n_within_with_others']}}}",
                f"% Macro old value: 6921 (v4_hard def n_viols>0). New value: {a5['n_within_only']} (v4_hard = commission/timing/sequence)",
                f"% Domain count: {a5['n_unique_domains']} unique domains (prefix-2 grouping)",
                "",
                "% --- A7: CRES-1D coverage_free vs asc_only gap ---",
                f"\\providecommand{{\\cresOneDCoverageFreeGapPP}}{{{cf['point_pp']:.2f}}}",
                f"\\providecommand{{\\cresOneDCoverageFreeCILo}}{{{cf['ci_95_lo_pp']:.2f}}}",
                f"\\providecommand{{\\cresOneDCoverageFreeCIHi}}{{{cf['ci_95_hi_pp']:.2f}}}",
                f"% CI contains point: {cf['ci_contains_point']}",
                "% Method: paired bootstrap on 5-fold AUC gaps, n=10000 resamples",
                f"% Per-fold gaps (pp): {cf['per_fold_pp']}",
                "",
                "% --- A7 alt: clean vs asc_only ---",
                f"\\providecommand{{\\cresOneDCleanGapPP}}{{{cv_asc['point_pp']:.2f}}}",
                f"\\providecommand{{\\cresOneDCleanCILo}}{{{cv_asc['ci_95_lo_pp']:.2f}}}",
                f"\\providecommand{{\\cresOneDCleanCIHi}}{{{cv_asc['ci_95_hi_pp']:.2f}}}",
            ]
        )
        + "\n"
    )


def main() -> None:
    a5 = recompute_a5()
    a7 = recompute_a7()

    OUT_A5.write_text(json.dumps(a5, indent=2))
    OUT_A7.write_text(json.dumps(a7, indent=2))
    OUT_TEX.write_text(emit_macros(a5, a7))
    print("\n" + "=" * 60)
    print(f"  A5 audit: {OUT_A5}")
    print(f"  A7 audit: {OUT_A7}")
    print(f"  Macros:   {OUT_TEX}")
    print("=" * 60)


if __name__ == "__main__":
    main()
