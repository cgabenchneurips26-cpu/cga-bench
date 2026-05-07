#!/usr/bin/env python3
"""T1-7: Regression on pair-level τ ~ SameClass + evaluator random effects.

With 15 pair observations on 6 evaluators, we fit:

  1. OLS   τ_ij = β_0 + β_1 · SameClass_ij + ε_ij                    (primary effect)
  2. ANOVA decomposition → ICC ≈ Var(evaluator) / (Var(evaluator) + Var(residual))
  3. Leave-one-evaluator-out jackknife CI on β̂_1                     (robust SE)
  4. statsmodels.MixedLM 1-way random intercept on evaluator_a as sensitivity
     (crossed 2-way RE is over-parameterised on 15 obs; single grouping is the
     honest ceiling).

Canonical-6 scope per docs/260423_piclass_pool_dilution_finding.md.

Outputs
-------
  evidence_pack/audit/piclass_mixed_canonical6_results.json
  evidence_pack/audit/piclass_mixed_canonical6_macros.tex
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import statistics
import sys
import warnings

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "evidence_pack" / "audit"
C6_PATH = ROOT / "evidence_pack" / "audit" / "c6_audit_guided_selection.json"


def _long_table(
    pairs: list[dict], pi_classes: dict[str, str]
) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]:
    """Return tau vector, same-class design column, and matching evaluator ids."""
    tau = np.array([float(p["tau"]) for p in pairs])
    same = np.array(
        [1.0 if pi_classes[p["evaluator_a"]] == pi_classes[p["evaluator_b"]] else 0.0
         for p in pairs]
    )
    eval_a = [p["evaluator_a"] for p in pairs]
    eval_b = [p["evaluator_b"] for p in pairs]
    return tau, same, eval_a, eval_b


def _ols_fit(tau: np.ndarray, same: np.ndarray) -> dict:
    X = np.column_stack([np.ones_like(tau), same])
    beta, resid, _, _ = np.linalg.lstsq(X, tau, rcond=None)
    y_hat = X @ beta
    resid = tau - y_hat
    n, k = X.shape
    if n - k > 0:
        sigma2 = float((resid @ resid) / (n - k))
    else:
        sigma2 = 0.0
    cov = sigma2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    from scipy import stats

    t_stat = float(beta[1] / se[1]) if se[1] > 0 else 0.0
    p_two = float(2 * (1 - stats.t.cdf(abs(t_stat), df=max(1, n - k)))) if se[1] > 0 else 1.0
    return {
        "beta_0": float(beta[0]),
        "beta_1": float(beta[1]),
        "se_beta_1": float(se[1]),
        "t_stat": t_stat,
        "p_value_two_sided": p_two,
        "n": int(n),
        "df_resid": int(n - k),
        "sigma2": sigma2,
    }


def _icc_anova(
    tau: np.ndarray, eval_a: list[str], eval_b: list[str]
) -> dict:
    """Rough ICC: each pair τ contributes to two evaluator groups.

    We treat the pair value as a joint observation of both evaluators
    (duplicated rows), then:
       ICC ≈ Var(evaluator_mean) / (Var(evaluator_mean) + Var(residual))
    """
    by_eval: dict[str, list[float]] = {}
    for t, a, b in zip(tau, eval_a, eval_b):
        by_eval.setdefault(a, []).append(float(t))
        by_eval.setdefault(b, []).append(float(t))
    means = [statistics.fmean(v) for v in by_eval.values()]
    overall = statistics.fmean([vv for vs in by_eval.values() for vv in vs])
    between = statistics.pvariance(means) if len(means) > 1 else 0.0
    within = statistics.fmean([statistics.pvariance(v) for v in by_eval.values() if len(v) > 1])
    total = between + within
    icc = between / total if total > 0 else 0.0
    return {
        "icc": round(float(icc), 4),
        "between_var": round(float(between), 4),
        "within_var": round(float(within), 4),
        "overall_mean": round(float(overall), 4),
    }


def _jackknife_beta(
    tau: np.ndarray, same: np.ndarray, eval_a: list[str], eval_b: list[str]
) -> dict:
    """Leave-one-evaluator-out jackknife on β̂_1."""
    evaluators = sorted(set(eval_a) | set(eval_b))
    beta_vals: list[float] = []
    for held in evaluators:
        keep = [i for i, (a, b) in enumerate(zip(eval_a, eval_b)) if a != held and b != held]
        if len(keep) < 3:
            continue
        fit = _ols_fit(tau[keep], same[keep])
        beta_vals.append(fit["beta_1"])
    if not beta_vals:
        return {"jackknife_mean": 0.0, "jackknife_sd": 0.0}
    return {
        "jackknife_mean": round(statistics.fmean(beta_vals), 4),
        "jackknife_sd": round(statistics.pstdev(beta_vals), 4) if len(beta_vals) > 1 else 0.0,
        "n_leaves": len(beta_vals),
    }


def _mixedlm_sensitivity(
    tau: np.ndarray, same: np.ndarray, eval_a: list[str]
) -> dict | None:
    """1-way random intercept on evaluator_a (honest given n=15)."""
    try:
        import pandas as pd
        import statsmodels.formula.api as smf
    except ImportError:
        return None
    df = pd.DataFrame({"tau": tau, "same": same, "eva": eval_a})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            md = smf.mixedlm("tau ~ same", df, groups=df["eva"])
            mdf = md.fit(reml=True)
        except Exception:
            return None
    try:
        re_cov = mdf.cov_re
        if hasattr(re_cov, "iloc"):
            re_var = float(re_cov.iloc[0, 0])
        else:
            re_var = float(np.asarray(re_cov)[0, 0])
    except Exception:
        re_var = 0.0
    return {
        "beta_0": float(mdf.params.get("Intercept", 0.0)),
        "beta_1": float(mdf.params.get("same", 0.0)),
        "se_beta_1": float(mdf.bse.get("same", 0.0)),
        "p_value": float(mdf.pvalues.get("same", 1.0)),
        "re_var": re_var,
    }


def _emit_macros(res: dict, path: Path) -> None:
    ols = res["ols"]
    icc = res["icc"]
    jk = res["jackknife"]
    mlm = res["mixedlm_sensitivity"] or {}
    lines = [
        "% Auto-generated by scripts/experiments/exp_piclass_mixed_effects.py",
        f"\\providecommand{{\\piMixedN}}{{{ols['n']}}}",
        f"\\providecommand{{\\piMixedBeta}}{{{ols['beta_1']:.4f}}}",
        f"\\providecommand{{\\piMixedSE}}{{{ols['se_beta_1']:.4f}}}",
        f"\\providecommand{{\\piMixedT}}{{{ols['t_stat']:.3f}}}",
        f"\\providecommand{{\\piMixedP}}{{{ols['p_value_two_sided']:.4f}}}",
        f"\\providecommand{{\\piMixedICC}}{{{icc['icc']:.4f}}}",
        f"\\providecommand{{\\piMixedJkMean}}{{{jk.get('jackknife_mean', 0.0):.4f}}}",
        f"\\providecommand{{\\piMixedJkSd}}{{{jk.get('jackknife_sd', 0.0):.4f}}}",
    ]
    if mlm:
        lines.append(f"\\providecommand{{\\piMixedLmBeta}}{{{mlm['beta_1']:.4f}}}")
        lines.append(f"\\providecommand{{\\piMixedLmSE}}{{{mlm['se_beta_1']:.4f}}}")
        lines.append(f"\\providecommand{{\\piMixedLmP}}{{{mlm['p_value']:.4f}}}")
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="T1-7 mixed-effects-ish regression (canonical-6)")
    parser.add_argument("--out-dir", type=str, default=str(OUT_DIR))
    args = parser.parse_args()

    with open(C6_PATH) as f:
        data = json.load(f)
    pairs = data["pairs"]
    pi_classes = data["pi_classes"]
    print(f"Loaded {len(pi_classes)} evaluators, {len(pairs)} pairs")

    tau, same, eva, evb = _long_table(pairs, pi_classes)
    ols = _ols_fit(tau, same)
    icc = _icc_anova(tau, eva, evb)
    jk = _jackknife_beta(tau, same, eva, evb)
    mlm = _mixedlm_sensitivity(tau, same, eva)

    print("\n[OLS] τ ~ β0 + β1·SameClass")
    print(
        f"  β0={ols['beta_0']:.4f}  β1={ols['beta_1']:.4f}  "
        f"SE(β1)={ols['se_beta_1']:.4f}  t={ols['t_stat']:.3f}  "
        f"p={ols['p_value_two_sided']:.4f}  df={ols['df_resid']}"
    )
    print(f"[ICC-ANOVA]  ICC={icc['icc']}  between={icc['between_var']}  within={icc['within_var']}")
    print(f"[Jackknife]  β1 mean={jk.get('jackknife_mean')}  sd={jk.get('jackknife_sd')}")
    if mlm:
        print(
            f"[MixedLM 1-way sensitivity]  β1={mlm['beta_1']:.4f}  "
            f"SE={mlm['se_beta_1']:.4f}  p={mlm['p_value']:.4f}"
        )
    else:
        print("[MixedLM] statsmodels unavailable; skipping sensitivity fit")

    result = {
        "timestamp": datetime.now(UTC).isoformat(),
        "pi_classes": pi_classes,
        "ols": ols,
        "icc": icc,
        "jackknife": jk,
        "mixedlm_sensitivity": mlm,
    }
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "piclass_mixed_canonical6_results.json").write_text(json.dumps(result, indent=2) + "\n")
    _emit_macros(result, out / "piclass_mixed_canonical6_macros.tex")
    print("Saved: piclass_mixed_canonical6_{results.json, macros.tex}")


if __name__ == "__main__":
    main()
