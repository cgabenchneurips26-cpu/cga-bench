"""Recompute η² partition + Strict FA on Phase B canonical (76,464 ep).

Resolves auto_numbers_fallback_filled.tex inconsistencies:
  - eta_eval + eta_run > 1 (variance partition broken)
  - eta_run = 0.91 contradicts paper "near-zero run variance" claim
  - Strict FA 28.85% is 8x paper expectation (~3-7%)

Source: evidence_pack/analysis/verdict_matrix_v6_full.json
        (per_episode list with binary verdicts)

Output:
  - paper/auto_numbers_fallback_eta_corrected.tex  (5 corrected macros)
  - evidence_pack/analysis/macros_recompute_v2.json (audit trail)
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "evidence_pack" / "analysis" / "verdict_matrix_v6_full.json"
V6_BASE_MANIFEST = REPO / "evidence_pack" / "frontier" / "w8_706_manifest.json"
OUT_TEX = REPO / "paper" / "auto_numbers_fallback_eta_corrected.tex"
OUT_JSON = REPO / "evidence_pack" / "analysis" / "macros_recompute_v2.json"


def _load_v6_base_ids() -> set[str]:
    return {s["scenario_id"] for s in json.load(open(V6_BASE_MANIFEST))["scenarios"]}


EVALUATORS = ("ac_proxy", "mab_proxy", "c2_pass", "acov_pass", "dxem")


def _bool(v) -> int:
    return 1 if v else 0


def _eta_partition(per_episode: list[dict]) -> dict:
    """Compute η²_eval and η²_run via ANOVA decomposition.

    Treats binary verdicts (0/1) as continuous. Two factors:
      - evaluator: 5 levels (ac_proxy, mab_proxy, c2_pass, acov_pass, dxem)
      - run: 3 levels (0, 1, 2)
    Decomposition (one-way per factor, computed separately for clarity):
      SS_total   = sum_{ij} (y_{ij} - y_bar)^2
      SS_eval    = N_per_eval * sum_e (y_bar_e - y_bar)^2
      SS_run     = N_per_run  * sum_r (y_bar_r - y_bar)^2
      SS_resid   = SS_total - SS_eval - SS_run  (1-way each, not joint partition)
      η²_eval    = SS_eval / SS_total
      η²_run     = SS_run / SS_total

    Both are valid one-way η² shares; sum may be < 1 due to other factors
    (model, scenario, residual).
    """
    rows: list[tuple[str, int, int]] = []  # (evaluator, run, value)
    for ep in per_episode:
        run = ep["run_index"]
        for ev in EVALUATORS:
            rows.append((ev, run, _bool(ep.get(ev))))

    n = len(rows)
    grand_mean = sum(r[2] for r in rows) / n

    ss_total = sum((r[2] - grand_mean) ** 2 for r in rows)

    by_eval: dict[str, list[int]] = defaultdict(list)
    by_run: dict[int, list[int]] = defaultdict(list)
    for ev, run, v in rows:
        by_eval[ev].append(v)
        by_run[run].append(v)

    ss_eval = sum(len(vs) * (sum(vs) / len(vs) - grand_mean) ** 2 for vs in by_eval.values())
    ss_run = sum(len(vs) * (sum(vs) / len(vs) - grand_mean) ** 2 for vs in by_run.values())

    eta_eval = ss_eval / ss_total if ss_total else 0.0
    eta_run = ss_run / ss_total if ss_total else 0.0

    return {
        "n_rows": n,
        "n_episodes": len(per_episode),
        "grand_mean": round(grand_mean, 4),
        "ss_total": round(ss_total, 2),
        "ss_eval": round(ss_eval, 2),
        "ss_run": round(ss_run, 2),
        "eta_eval": round(eta_eval, 6),
        "eta_run": round(eta_run, 6),
        "ratio_eval_over_run": round(eta_eval / eta_run, 4) if eta_run > 1e-9 else None,
        "sum_ok": eta_eval + eta_run <= 1.0,
        "per_eval_pass_rate": {ev: round(sum(vs) / len(vs), 4) for ev, vs in by_eval.items()},
        "per_run_pass_rate": {r: round(sum(vs) / len(vs), 4) for r, vs in by_run.items()},
    }


def _strict_fa_3way(per_episode: list[dict]) -> dict:
    """Strict 3-way FA: (ASC ∩ CwT ∩ PAF) pass AND v4_hard.

    ASC = ac_proxy, CwT = c2_pass, PAF = mab_proxy.
    """
    n = len(per_episode)
    triple_pass = [ep for ep in per_episode if ep.get("ac_proxy") and ep.get("c2_pass") and ep.get("mab_proxy")]
    fa = [ep for ep in triple_pass if ep.get("v4_hard")]
    return {
        "n_episodes": n,
        "n_triple_pass": len(triple_pass),
        "triple_pass_rate": round(100.0 * len(triple_pass) / n, 4) if n else 0.0,
        "n_fa": len(fa),
        "strict_fa_pct": round(100.0 * len(fa) / n, 4) if n else 0.0,
        "strict_fa_rate_among_pass": (round(100.0 * len(fa) / len(triple_pass), 4) if triple_pass else None),
    }


def _strict_fa_2way(per_episode: list[dict]) -> dict:
    """Strict 2-way FA: (ASC ∩ CwT) pass AND v4_hard.

    Reference for comparison with 3-way (likely what filled file actually used).
    """
    n = len(per_episode)
    pair_pass = [ep for ep in per_episode if ep.get("ac_proxy") and ep.get("c2_pass")]
    fa = [ep for ep in pair_pass if ep.get("v4_hard")]
    return {
        "n_episodes": n,
        "n_pair_pass": len(pair_pass),
        "pair_pass_rate": round(100.0 * len(pair_pass) / n, 4) if n else 0.0,
        "n_fa": len(fa),
        "fa_pct": round(100.0 * len(fa) / n, 4) if n else 0.0,
    }


def _compute_substrate(label: str, eps: list[dict]) -> dict:
    return {
        "label": label,
        "eta": _eta_partition(eps),
        "fa3": _strict_fa_3way(eps),
        "fa2": _strict_fa_2way(eps),
    }


def _print_block(s: dict) -> None:
    print(f"\n=== {s['label']} (n={s['eta']['n_episodes']:,}) ===")
    print(f"  η²_eval = {s['eta']['eta_eval']:.6f}")
    print(f"  η²_run  = {s['eta']['eta_run']:.6f}")
    print(f"  ratio   = {s['eta']['ratio_eval_over_run']}")
    print(f"  3-way pass: {s['fa3']['n_triple_pass']:,} ({s['fa3']['triple_pass_rate']:.2f}%)")
    print(f"  Strict FA (% of total) = {s['fa3']['strict_fa_pct']:.2f}%")
    print(f"  Strict FA (among pass) = {s['fa3']['strict_fa_rate_among_pass']}%")


def main() -> None:
    print(f"Loading verdict matrix: {SRC}")
    data = json.load(open(SRC))
    eps_full = data["per_episode"]
    print(f"Total episodes: {len(eps_full):,}")
    print(f"v4_hard episodes: {sum(1 for e in eps_full if e.get('v4_hard')):,}")

    v6_ids = _load_v6_base_ids()
    print(f"V6 base scenario IDs (706 manifest): {len(v6_ids)}")

    eps_v6 = [e for e in eps_full if e["scenario_id"] in v6_ids]
    eps_ts = [e for e in eps_full if e["scenario_id"] not in v6_ids]
    print(f"  V6 base subset:    {len(eps_v6):,}")
    print(f"  Tier-S subset:     {len(eps_ts):,}")

    s_full = _compute_substrate("Phase B canonical (V6+TierS)", eps_full)
    s_v6 = _compute_substrate("V6 base only", eps_v6)
    s_ts = _compute_substrate("Tier-S subset only", eps_ts)
    _print_block(s_full)
    _print_block(s_v6)
    _print_block(s_ts)

    eta_full = s_full["eta"]
    eta_ts = s_ts["eta"]
    fa_full = s_full["fa3"]
    fa_ts = s_ts["fa3"]

    out_obj = {
        "source": str(SRC.relative_to(REPO)),
        "v6_manifest": str(V6_BASE_MANIFEST.relative_to(REPO)),
        "subsets": {
            "full": {"n": len(eps_full), **s_full},
            "v6_base": {"n": len(eps_v6), **s_v6},
            "tier_s": {"n": len(eps_ts), **s_ts},
        },
    }
    OUT_JSON.write_text(json.dumps(out_obj, indent=2))
    print(f"\nAudit JSON written: {OUT_JSON}")

    macros = [
        "% Recomputed Phase B macros (auto_numbers_fallback_eta_corrected.tex)",
        f"% Source: {SRC.relative_to(REPO)}",
        f"% V6 manifest: {V6_BASE_MANIFEST.relative_to(REPO)} ({len(v6_ids)} base scenarios)",
        f"% Subsets: full={len(eps_full):,} v6={len(eps_v6):,} tier_s={len(eps_ts):,}",
        "% Method: one-way ANOVA per factor; eta_factor = SS_factor / SS_total.",
        "",
        "% --- Phase B canonical (V6 + Tier-S) ---",
        f"\\providecommand{{\\tierSFullEtaTwo}}{{{eta_full['eta_eval']:.4f}}}",
        f"\\providecommand{{\\tierSFullEtaRun}}{{{eta_full['eta_run']:.6f}}}",
        f"\\providecommand{{\\tierSFullRatio}}{{{eta_full['ratio_eval_over_run']}}}",
        f"\\providecommand{{\\tierSFullStrictFA}}{{{fa_full['strict_fa_pct']:.2f}}}",
        "",
        f"% --- Tier-S subset only (n={len(eps_ts):,}) ---",
        f"\\providecommand{{\\tierSEtaTwo}}{{{eta_ts['eta_eval']:.4f}}}",
        f"\\providecommand{{\\tierSEtaRun}}{{{eta_ts['eta_run']:.6f}}}",
        f"\\providecommand{{\\tierSRatio}}{{{eta_ts['ratio_eval_over_run']}}}",
        f"\\providecommand{{\\tierSStrictFA}}{{{fa_ts['strict_fa_pct']:.2f}}}",
        "",
        "% --- Audit ---",
        f"% Phase B 3-way pass: {fa_full['n_triple_pass']:,} ({fa_full['triple_pass_rate']:.2f}%) | rate-among-pass: {fa_full['strict_fa_rate_among_pass']}%",
        f"% Tier-S  3-way pass: {fa_ts['n_triple_pass']:,} ({fa_ts['triple_pass_rate']:.2f}%) | rate-among-pass: {fa_ts['strict_fa_rate_among_pass']}%",
        f"% Phase B eta_eval+eta_run = {eta_full['eta_eval'] + eta_full['eta_run']:.4f}",
        f"% Tier-S  eta_eval+eta_run = {eta_ts['eta_eval'] + eta_ts['eta_run']:.4f}",
    ]
    OUT_TEX.write_text("\n".join(macros) + "\n")
    print(f"Corrected macros written: {OUT_TEX}")
    return

    # --- legacy single-substrate block below preserved for reference ---
    eps = data["per_episode"]
    print(f"Total episodes: {len(eps)}")
    print(f"v4_hard episodes: {sum(1 for e in eps if e.get('v4_hard'))}")

    print("\n=== η² Partition (Phase B canonical) ===")
    eta = _eta_partition(eps)
    print(json.dumps(eta, indent=2))

    print("\n=== Strict FA — 3-way (ASC ∩ CwT ∩ PAF) ===")
    fa3 = _strict_fa_3way(eps)
    print(json.dumps(fa3, indent=2))

    print("\n=== Strict FA — 2-way (ASC ∩ CwT) [reference] ===")
    fa2 = _strict_fa_2way(eps)
    print(json.dumps(fa2, indent=2))

    out_obj = {
        "source": str(SRC.relative_to(REPO)),
        "n_episodes": len(eps),
        "eta_partition": eta,
        "strict_fa_3way": fa3,
        "strict_fa_2way": fa2,
    }
    OUT_JSON.write_text(json.dumps(out_obj, indent=2))
    print(f"\nAudit JSON written: {OUT_JSON}")

    macros = [
        "% Recomputed Phase B macros (auto_numbers_fallback_eta_corrected.tex)",
        "% Replaces broken values in auto_numbers_fallback_filled.tex.",
        f"% Source: {SRC.relative_to(REPO)} (n={len(eps)} episodes).",
        f"\\providecommand{{\\tierSFullEtaTwo}}{{{eta['eta_eval']:.4f}}}",
        f"\\providecommand{{\\tierSFullEtaRun}}{{{eta['eta_run']:.4f}}}",
        f"\\providecommand{{\\tierSFullRatio}}{{{eta['ratio_eval_over_run']}}}"
        if eta["ratio_eval_over_run"]
        else "% ratio undefined (eta_run~0)",
        f"\\providecommand{{\\tierSFullStrictFA}}{{{fa3['strict_fa_pct']:.2f}}}",
        f"% Strict FA 3-way pass count: {fa3['n_triple_pass']} / {fa3['n_episodes']} = {fa3['triple_pass_rate']:.4f}%",
        f"% v4_hard among 3-way pass: {fa3['n_fa']} / {fa3['n_triple_pass']} = {fa3['strict_fa_rate_among_pass']}% (rate-among-pass)",
        f"% η² sanity: η²_eval + η²_run = {eta['eta_eval'] + eta['eta_run']:.4f} (must be <=1)",
    ]
    OUT_TEX.write_text("\n".join(macros) + "\n")
    print(f"Corrected macros written: {OUT_TEX}")


if __name__ == "__main__":
    main()
