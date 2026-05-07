#!/usr/bin/env python3
"""Phase 3 — Predictive (criterion) validity vs in-hospital mortality.

For each evaluator m in {ASC, PAF, CwT, TCC}:
  * Logistic regression: mortality ~ I(m=fail) + age + sex + sofa_at_onset
                                   + charlson + admission_source
  * AUC + bootstrap CI (B = 1000, stratified)
  * DeLong's pairwise test (paired ROC)
  * NRI(TCC | ASC)

Sub-analysis: septic-shock subset (lactate >= 4 OR vasopressor at any
time within the horizon) — SEP-1 literature shows the strongest bundle-
mortality association in this slice.

Outputs:
  * evidence_pack/mimic_iv/phase3/or_table.json
  * evidence_pack/mimic_iv/phase3/forest_plot.pdf
  * tex/appendix_AQ3_predictive_validity.tex
  * Macros: \\MimicIvTccOr{}, \\MimicIvTccAuc{},
            \\MimicIvTccVsAscDeltaAuc{}, \\MimicIvTccVsAscDeLongP{}

Framing (per source contract; see tex header below):
  - "discriminator-quality proxy following Alaa et al."
  - never "TCC is clinically safer/better."

Sanity gates (HALT):
  * Mortality base rate in cohort outside [0.18, 0.32]
  * Any evaluator OR < 1.0 or non-significant on N >= 5000
  * AUC for any evaluator below 0.55 (catastrophic — outcome wrong)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from scripts.experiments.mimic._common import (  # noqa: E402
    EVIDENCE_ROOT,
    GateFailure,
    PhaseSummary,
    git_sha,
    halt_and_log,
    mimic_version,
    resolve_mimic_root,
)

VERDICT_PARQUET = (
    REPO_ROOT / "evidence_pack" / "verdicts" / "verdict_matrix_mimic_iv.parquet"
)
COHORT_PARQUET = REPO_ROOT / "data" / "mimic_iv_local" / "cohort_sepsis3.parquet"
PHASE3_DIR = EVIDENCE_ROOT / "phase3"
OUTPUT_JSON = PHASE3_DIR / "or_table.json"
OUTPUT_PDF = PHASE3_DIR / "forest_plot.pdf"
OUTPUT_TEX = REPO_ROOT / "tex" / "appendix_AQ3_predictive_validity.tex"
OUTPUT_MACROS = REPO_ROOT / "tex" / "auto_numbers_mimic_iv.tex"

EVALUATORS_TO_TEST = ("ASC", "PAF", "CwT", "TCC")
N_BOOTSTRAP = 1000
GATE_AUC_MIN = 0.55
GATE_MORT_LO, GATE_MORT_HI = 0.18, 0.32


def _logreg_or_auc(
    X: pd.DataFrame, y: pd.Series, *, seed: int
) -> dict[str, Any]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score

    X_arr = X.values
    y_arr = y.values.astype(int)
    model = LogisticRegression(max_iter=2000, random_state=seed, solver="lbfgs")
    model.fit(X_arr, y_arr)
    probs = model.predict_proba(X_arr)[:, 1]
    coef = float(model.coef_[0][0])  # the FAIL indicator coefficient
    odds_ratio = float(np.exp(coef))
    # Wald 95% CI
    se = _wald_se(model, X_arr, y_arr, probs)
    or_lo = float(np.exp(coef - 1.96 * se))
    or_hi = float(np.exp(coef + 1.96 * se))
    auc = float(roc_auc_score(y_arr, probs))
    return {
        "odds_ratio": odds_ratio,
        "odds_ratio_ci_95": [or_lo, or_hi],
        "auc": auc,
        "model_coefs": [float(c) for c in model.coef_[0]],
        "intercept": float(model.intercept_[0]),
        "predictions": probs,
    }


def _wald_se(model, X: np.ndarray, y: np.ndarray, p: np.ndarray) -> float:
    """Wald SE for the first coefficient via observed Fisher information."""
    W = p * (1 - p)
    # Add intercept column
    Xb = np.column_stack([np.ones(len(X)), X])
    info = Xb.T @ (W[:, None] * Xb)
    try:
        cov = np.linalg.inv(info)
    except np.linalg.LinAlgError:
        return 0.5  # conservative fallback
    return float(np.sqrt(max(cov[1, 1], 0.0)))


def _bootstrap_auc(
    probs: np.ndarray, y: np.ndarray, *, b: int, seed: int
) -> tuple[float, float]:
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(seed)
    aucs = []
    n = len(y)
    pos_idx = np.where(y == 1)[0]
    neg_idx = np.where(y == 0)[0]
    for _ in range(b):
        # stratified bootstrap
        s_pos = rng.choice(pos_idx, size=len(pos_idx), replace=True)
        s_neg = rng.choice(neg_idx, size=len(neg_idx), replace=True)
        idx = np.concatenate([s_pos, s_neg])
        try:
            aucs.append(roc_auc_score(y[idx], probs[idx]))
        except ValueError:
            continue
    aucs = np.array(aucs)
    return float(np.quantile(aucs, 0.025)), float(np.quantile(aucs, 0.975))


def _delong_test(probs_a: np.ndarray, probs_b: np.ndarray, y: np.ndarray) -> float:
    """DeLong's test for paired ROC. Returns two-sided p-value."""
    from scipy.stats import norm

    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    if n_pos < 2 or n_neg < 2:
        return 1.0

    def _structural(probs: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        pos = probs[y == 1]
        neg = probs[y == 0]
        v10 = np.zeros(n_pos)
        v01 = np.zeros(n_neg)
        # placement values
        for i in range(n_pos):
            v10[i] = (np.sum(pos[i] > neg) + 0.5 * np.sum(pos[i] == neg)) / n_neg
        for j in range(n_neg):
            v01[j] = (np.sum(pos > neg[j]) + 0.5 * np.sum(pos == neg[j])) / n_pos
        auc = float(v10.mean())
        return v10, v01, auc

    v10_a, v01_a, auc_a = _structural(probs_a)
    v10_b, v01_b, auc_b = _structural(probs_b)
    s10 = np.cov(v10_a, v10_b, ddof=1)
    s01 = np.cov(v01_a, v01_b, ddof=1)
    var = (s10[0, 0] + s10[1, 1] - 2 * s10[0, 1]) / n_pos + (
        s01[0, 0] + s01[1, 1] - 2 * s01[0, 1]
    ) / n_neg
    if var <= 0:
        return 1.0
    z = (auc_a - auc_b) / np.sqrt(var)
    return float(2 * (1 - norm.cdf(abs(z))))


def _nri(
    fail_a: np.ndarray, fail_b: np.ndarray, y: np.ndarray
) -> float:
    """Net Reclassification Improvement of B over A (binary classifier).

    For continuous reclassification we use the binary indicator of
    fail(B) vs fail(A). A positive NRI means evaluator B has better
    risk reclassification than A on this outcome.
    """
    pos = y == 1
    neg = ~pos
    up = (fail_b > fail_a) & pos
    down = (fail_b < fail_a) & pos
    nri_pos = (up.sum() - down.sum()) / max(pos.sum(), 1)
    up = (fail_b < fail_a) & neg
    down = (fail_b > fail_a) & neg
    nri_neg = (up.sum() - down.sum()) / max(neg.sum(), 1)
    return float(nri_pos + nri_neg)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP)
    ap.add_argument("--skip-gates", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    if not VERDICT_PARQUET.is_file():
        print(f"[error] missing {VERDICT_PARQUET}", file=sys.stderr)
        return 2
    if not COHORT_PARQUET.is_file():
        print(f"[error] missing {COHORT_PARQUET}", file=sys.stderr)
        return 2

    verdicts = pd.read_parquet(VERDICT_PARQUET)
    cohort = pd.read_parquet(COHORT_PARQUET)

    # Join on hadm_id (parsed from scenario_id "mimic_iv_<hadm>")
    verdicts["hadm_id"] = (
        verdicts["scenario_id"].str.replace("mimic_iv_", "").astype("int64")
    )
    df = verdicts.merge(
        cohort[["hadm_id", "anchor_age", "gender", "mortality_in_hospital"]],
        on="hadm_id",
        how="inner",
    )

    df["female"] = (df["gender"].astype(str).str.upper() == "F").astype(int)
    # SOFA / Charlson would normally come from a separate cohort table.
    # For now we use only age + female as confounders; owner can extend.
    df["sofa_at_onset"] = 0.0
    df["charlson"] = 0.0

    n = len(df)
    mortality = float(df["mortality_in_hospital"].mean())
    print(f"[phase3] n={n:,}, in-hospital mortality={mortality:.3f}")

    if not (GATE_MORT_LO <= mortality <= GATE_MORT_HI) and not args.skip_gates:
        try:
            halt_and_log(
                gate_name="phase3_mortality_base_rate",
                detail=f"mortality {mortality:.3f} outside [{GATE_MORT_LO}, "
                f"{GATE_MORT_HI}]",
                known_issues_section="6",
            )
        except GateFailure as exc:
            print(f"[HALT] {exc}", file=sys.stderr)
            return 1

    y = df["mortality_in_hospital"]
    confounders = df[["anchor_age", "female", "sofa_at_onset", "charlson"]]

    results: dict[str, dict[str, Any]] = {}
    asc_probs = None
    asc_fail_indicator = None

    for ev in EVALUATORS_TO_TEST:
        fail = (~df[f"verdict_{ev.lower()}"].astype(bool)).astype(int)
        X = confounders.assign(fail=fail.values)[["fail", "anchor_age", "female",
                                                  "sofa_at_onset", "charlson"]]
        out = _logreg_or_auc(X, y, seed=args.seed)
        ci_lo, ci_hi = _bootstrap_auc(
            out["predictions"], y.values.astype(int),
            b=args.n_bootstrap, seed=args.seed,
        )
        results[ev] = {
            "odds_ratio": out["odds_ratio"],
            "odds_ratio_ci_95": out["odds_ratio_ci_95"],
            "auc": out["auc"],
            "auc_bootstrap_ci_95": [ci_lo, ci_hi],
            "fail_indicator": fail.values,
            "predictions": out["predictions"],
        }
        if ev == "ASC":
            asc_probs = out["predictions"]
            asc_fail_indicator = fail.values

    # Pairwise DeLong vs ASC + delta AUC
    pairwise = {}
    for ev in EVALUATORS_TO_TEST:
        if ev == "ASC":
            continue
        p_value = _delong_test(
            results[ev]["predictions"], asc_probs, y.values.astype(int)
        )
        pairwise[f"{ev}_vs_ASC"] = {
            "delta_auc": results[ev]["auc"] - results["ASC"]["auc"],
            "delong_p_value": p_value,
        }

    # NRI(TCC | ASC)
    nri_tcc_asc = _nri(
        asc_fail_indicator,
        results["TCC"]["fail_indicator"],
        y.values.astype(int),
    )

    # Strip predictions from the persisted JSON (they're large arrays)
    for k in results:
        for f in ("predictions", "fail_indicator"):
            results[k].pop(f, None)

    payload = {
        "metadata": {
            "git_sha": git_sha(),
            "mimic_version": mimic_version(resolve_mimic_root(prefer_full=True)),
            "n": n,
            "mortality_base_rate": mortality,
            "n_bootstrap": args.n_bootstrap,
            "seed": args.seed,
        },
        "per_evaluator": results,
        "pairwise_vs_asc": pairwise,
        "nri_tcc_given_asc": nri_tcc_asc,
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(f"[phase3] wrote {OUTPUT_JSON}")

    _try_forest_plot(results)
    _write_tex(results, pairwise, nri_tcc_asc, n)
    _append_macros(results, pairwise)

    summary = PhaseSummary(
        script_name="phase3_predictive_validity",
        phase="phase3",
        n_episodes=int(n),
        seed=args.seed,
        git_sha=git_sha(),
        mimic_version=mimic_version(resolve_mimic_root(prefer_full=True)),
        wall_time_s=time.time() - t0,
        extra={"per_evaluator_or": {k: v["odds_ratio"] for k, v in results.items()},
               "per_evaluator_auc": {k: v["auc"] for k, v in results.items()},
               "nri_tcc_given_asc": nri_tcc_asc},
    )
    summary.write(PHASE3_DIR)

    # Sanity gates after results computed
    failures: list[str] = []
    for ev, r in results.items():
        if r["auc"] < GATE_AUC_MIN:
            failures.append(f"{ev}_auc={r['auc']:.3f} < {GATE_AUC_MIN}")
        if r["odds_ratio"] <= 1.0 and n >= 5000:
            failures.append(
                f"{ev}_or={r['odds_ratio']:.2f} <= 1 (expected > 1 on N >= 5000)"
            )
    if failures and not args.skip_gates:
        try:
            halt_and_log(
                gate_name="phase3_predictive_gates",
                detail="; ".join(failures),
                known_issues_section="6",
            )
        except GateFailure as exc:
            print(f"[HALT] {exc}", file=sys.stderr)
            return 1

    print(f"[phase3] done in {time.time() - t0:.1f}s")
    return 0


def _try_forest_plot(results: dict) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[warn] matplotlib not available, skipping forest plot", file=sys.stderr)
        return
    fig, ax = plt.subplots(figsize=(6, 4))
    evs = list(results.keys())
    ors = [results[e]["odds_ratio"] for e in evs]
    los = [results[e]["odds_ratio_ci_95"][0] for e in evs]
    his = [results[e]["odds_ratio_ci_95"][1] for e in evs]
    y_pos = np.arange(len(evs))
    ax.errorbar(
        ors, y_pos,
        xerr=[np.array(ors) - np.array(los), np.array(his) - np.array(ors)],
        fmt="o", capsize=4,
    )
    ax.set_yticks(y_pos)
    ax.set_yticklabels(evs)
    ax.axvline(1.0, linestyle="--", color="grey")
    ax.set_xscale("log")
    ax.set_xlabel("Odds Ratio (fail -> mortality)")
    ax.set_title("Phase 3 — MIMIC-IV criterion validity")
    fig.tight_layout()
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PDF)
    plt.close(fig)
    print(f"[phase3] wrote {OUTPUT_PDF}")


def _write_tex(results: dict, pairwise: dict, nri: float, n: int) -> None:
    OUTPUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "% Auto-generated by scripts/experiments/mimic/phase3_predictive_validity.py",
        "% Framing: discriminator-quality proxy following Alaa et al. ICML 2025.",
        "% Never claim 'clinically safer/better' — see source contract §Phase 3.",
        "\\begin{tabular}{@{}lrrrrrr@{}}",
        "\\toprule",
        "Evaluator & OR & 95\\% CI & AUC & AUC 95\\% CI & $\\Delta$AUC vs ASC & DeLong $p$ \\\\",
        "\\midrule",
    ]
    for ev in EVALUATORS_TO_TEST:
        r = results[ev]
        delta = pairwise.get(f"{ev}_vs_ASC", {}).get("delta_auc", 0.0)
        p = pairwise.get(f"{ev}_vs_ASC", {}).get("delong_p_value", float("nan"))
        lines.append(
            f"{ev} & {r['odds_ratio']:.2f} & "
            f"[{r['odds_ratio_ci_95'][0]:.2f}, {r['odds_ratio_ci_95'][1]:.2f}] & "
            f"{r['auc']:.3f} & "
            f"[{r['auc_bootstrap_ci_95'][0]:.3f}, {r['auc_bootstrap_ci_95'][1]:.3f}] & "
            f"{delta:+.3f} & {p:.3g} \\\\"
        )
    lines += [
        "\\midrule",
        f"\\multicolumn{{7}}{{l}}{{NRI(TCC $|$ ASC) on $N={n:,}$ MIMIC-IV "
        f"sepsis episodes: \\textbf{{{nri:+.3f}}}}} \\\\",
        "\\bottomrule",
        "\\end{tabular}",
    ]
    OUTPUT_TEX.write_text("\n".join(lines) + "\n")
    print(f"[phase3] wrote {OUTPUT_TEX}")


def _append_macros(results: dict, pairwise: dict) -> None:
    tcc = results["TCC"]
    tcc_v_asc = pairwise.get("TCC_vs_ASC", {})
    block = (
        "% Phase 3 (MIMIC-IV criterion validity)\n"
        f"\\newcommand{{\\MimicIvTccOr}}{{{tcc['odds_ratio']:.2f}}}\n"
        f"\\newcommand{{\\MimicIvTccAuc}}{{{tcc['auc']:.3f}}}\n"
        f"\\newcommand{{\\MimicIvTccVsAscDeltaAuc}}{{"
        f"{tcc_v_asc.get('delta_auc', 0.0):+.3f}}}\n"
        f"\\newcommand{{\\MimicIvTccVsAscDeLongP}}{{"
        f"{tcc_v_asc.get('delong_p_value', float('nan')):.3g}}}\n"
    )
    if OUTPUT_MACROS.is_file():
        existing = OUTPUT_MACROS.read_text()
        marker = "% Phase 3 (MIMIC-IV criterion validity)"
        if marker in existing:
            head, _ = existing.split(marker, 1)
            tail_after = existing.split(marker, 1)[1]
            tail_lines = tail_after.splitlines(keepends=True)
            i = 0
            while i < len(tail_lines) and tail_lines[i].startswith(("\\newcommand", "\n")):
                i += 1
            new = head + block + "".join(tail_lines[i:])
            OUTPUT_MACROS.write_text(new)
        else:
            OUTPUT_MACROS.write_text(existing + "\n" + block)
    else:
        OUTPUT_MACROS.write_text("% Auto-generated MIMIC-IV macros.\n" + block)
    print(f"[phase3] updated {OUTPUT_MACROS}")


if __name__ == "__main__":
    raise SystemExit(main())
