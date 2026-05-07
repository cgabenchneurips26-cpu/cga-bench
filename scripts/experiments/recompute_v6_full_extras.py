"""All remaining macro recomputes on Phase B (76,464 episodes).

Mirrors the statistical functions of:
  - exp_cres_5_effect_size.py  (η², Cohen f², Cliff δ, VPC, rank-biserial, null ratio)
  - exp_cres_5_expansion.py    (partial η², ω², Fleiss κ, post-hoc power, MDE)
  - verify_friedman_eta.py     (Friedman test)
Plus per-domain FA breakdown.

Outputs:
  evidence_pack/analysis/v6_full_extras.json
  evidence_pack/tables/v6_full_extras.tex   (\\vSixFull* macros, with CIs)

Bootstrap n=1000 (n=76K is large; CI precision dominated by sample size).
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np
from scipy import stats

N_BOOTSTRAP = 1000
N_PERMUTATIONS = 1000
SEED = 42
ALPHA = 0.05
POWER_TARGET = 0.80


def build_mat(pe: list, c2_field: str) -> np.ndarray:
    """4-evaluator binary verdict matrix [AC, MAB, C2, CGA]."""
    n = len(pe)
    mat = np.zeros((n, 4), dtype=float)
    for i, ep in enumerate(pe):
        mat[i, 0] = 1.0 if ep["ac_proxy"] else 0.0
        mat[i, 1] = 1.0 if ep["mab_proxy"] else 0.0
        mat[i, 2] = 1.0 if ep[c2_field] else 0.0
        mat[i, 3] = 0.0 if ep["v4_hard"] else 1.0  # cga_pass
    return mat


def eta2_eval(mat: np.ndarray) -> float:
    n, k = mat.shape
    gm = mat.mean()
    em = mat.mean(axis=0)
    ss_eval = n * float(((em - gm) ** 2).sum())
    ss_total = float(((mat - gm) ** 2).sum())
    return ss_eval / ss_total if ss_total > 0 else 0.0


def eta2_run(records: list, mat: np.ndarray) -> float:
    cga = mat[:, 3]
    gm = float(cga.mean())
    ss_total = float(((cga - gm) ** 2).sum())
    groups: dict = defaultdict(list)
    for i, r in enumerate(records):
        groups[(r.get("scenario_id"), r.get("model") or r.get("model_dir"))].append(float(cga[i]))
    ss_run = 0.0
    for vals in groups.values():
        if len(vals) >= 2:
            mu = np.mean(vals)
            ss_run += float(((np.array(vals) - mu) ** 2).sum())
    return ss_run / ss_total if ss_total > 0 else 0.0


def partial_eta2_rm(mat: np.ndarray) -> float:
    n_items, n_raters = mat.shape
    if n_items < 2 or n_raters < 2:
        return 0.0
    grand_mean = mat.mean()
    row_means = mat.mean(axis=1)
    col_means = mat.mean(axis=0)
    ss_total = float(((mat - grand_mean) ** 2).sum())
    ss_episode = float(n_raters * ((row_means - grand_mean) ** 2).sum())
    ss_evaluator = float(n_items * ((col_means - grand_mean) ** 2).sum())
    ss_residual = ss_total - ss_episode - ss_evaluator
    denom = ss_evaluator + ss_residual
    return ss_evaluator / denom if denom > 0 else 0.0


def omega_squared(mat: np.ndarray) -> float:
    n, k = mat.shape
    gm = mat.mean()
    col_means = mat.mean(axis=0)
    ss_b = float(n * ((col_means - gm) ** 2).sum())
    ss_w = float(((mat - col_means) ** 2).sum())
    ss_total = ss_b + ss_w
    df_within = n * k - k
    ms_w = ss_w / df_within if df_within > 0 else 0.0
    num = ss_b - (k - 1) * ms_w
    denom = ss_total + ms_w
    return float(num / denom) if denom > 0 else 0.0


def fleiss_kappa(mat: np.ndarray) -> float:
    n_items, n_raters = mat.shape
    if n_raters < 2 or n_items < 2:
        return 0.0
    p_1 = float(mat.mean())
    p_0 = 1.0 - p_1
    p_e = p_0 * p_0 + p_1 * p_1
    if p_e >= 1.0:
        return 0.0
    row_sum_1 = mat.sum(axis=1)
    row_sum_0 = n_raters - row_sum_1
    sum_sq = (row_sum_1 * row_sum_1 + row_sum_0 * row_sum_0 - n_raters).sum()
    p_o = float(sum_sq) / (n_items * n_raters * (n_raters - 1))
    return (p_o - p_e) / (1 - p_e)


def cohens_f2(eta2: float) -> float:
    return eta2 / (1.0 - eta2) if eta2 < 1.0 else float("inf")


def cliffs_delta(x: np.ndarray, y: np.ndarray) -> float:
    n = len(x)
    if n == 0:
        return 0.0
    return (int((x > y).sum()) - int((x < y).sum())) / n


def vpc(mat: np.ndarray) -> float:
    eval_means = mat.mean(axis=0)
    var_between = float(np.var(eval_means, ddof=0))
    within_vars = np.var(mat, axis=0, ddof=0)
    var_within = float(within_vars.mean())
    denom = var_between + var_within
    return var_between / denom if denom > 0 else 0.0


def rank_biserial(binary_verdict: np.ndarray, continuous_score: np.ndarray) -> float:
    n = len(binary_verdict)
    if n == 0:
        return 0.0
    ranks = stats.rankdata(continuous_score)
    pass_mask = binary_verdict == 1
    fail_mask = binary_verdict == 0
    if not pass_mask.any() or not fail_mask.any():
        return 0.0
    return 2.0 * (float(ranks[pass_mask].mean()) - float(ranks[fail_mask].mean())) / n


def posthoc_power(eta2: float, n: int, k: int, alpha: float = ALPHA) -> float:
    if eta2 <= 0 or n <= 1 or k <= 1:
        return 0.0
    f2 = eta2 / (1 - eta2) if eta2 < 1 else float("inf")
    lam = f2 * n * k
    df1 = k - 1
    df2 = n * k - k
    f_crit = stats.f.ppf(1 - alpha, df1, df2)
    return float(1.0 - stats.ncf.cdf(f_crit, df1, df2, lam))


def mde_eta2(n: int, k: int, power: float = POWER_TARGET, alpha: float = ALPHA) -> float:
    if n <= 1 or k <= 1:
        return 1.0
    lo, hi = 1e-6, 0.99
    for _ in range(60):
        mid = (lo + hi) / 2
        if posthoc_power(mid, n, k, alpha) >= power:
            hi = mid
        else:
            lo = mid
    return float(hi)


def bootstrap_ci(mat: np.ndarray, fn, n_boot: int = N_BOOTSTRAP, seed: int = SEED) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    point = fn(mat)
    n = mat.shape[0]
    boots = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[b] = fn(mat[idx])
    return float(point), float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def null_ratio_test(mat: np.ndarray, observed_eta2: float, n_perm: int = N_PERMUTATIONS, seed: int = SEED) -> dict:
    """Permutation test: shuffle evaluator labels within each episode."""
    rng = np.random.default_rng(seed)
    n, k = mat.shape
    null_vals = np.empty(n_perm)
    for i in range(n_perm):
        idx = rng.permuted(np.arange(k) * np.ones((n, k), dtype=int), axis=1)
        null_vals[i] = eta2_eval(mat[np.arange(n)[:, None], idx])
    null_mean = float(null_vals.mean())
    return {
        "null_ratio": round(observed_eta2 / null_mean, 2) if null_mean > 0 else None,
        "null_mean": round(null_mean, 6),
        "null_ci_lo": round(float(np.percentile(null_vals, 2.5)), 6),
        "null_ci_hi": round(float(np.percentile(null_vals, 97.5)), 6),
    }


def friedman_test(pe: list, c2_field: str) -> dict:
    """Friedman χ² across 5 evaluators on (model, scenario) cells (averaged over runs)."""
    cells: dict = defaultdict(list)
    evs = ["dxem", "ac_proxy", "mab_proxy", c2_field, "v4_hard"]
    # Per (model, scenario, evaluator) → list of binary verdicts → mean
    for ep in pe:
        key = (ep.get("model_dir") or ep.get("model"), ep["scenario_id"])
        cells[key].append(ep)

    samples = {ev: [] for ev in evs}
    for key, eps in cells.items():
        if len(eps) < 1:
            continue
        for ev in evs:
            vals = [(e[ev] if ev != "v4_hard" else (not e[ev])) for e in eps]
            samples[ev].append(float(np.mean(vals)))

    arrs = [np.array(samples[ev]) for ev in evs]
    if min(len(a) for a in arrs) < 5:
        return {"error": "insufficient cells", "n_cells": min(len(a) for a in arrs)}
    chi2, pval = stats.friedmanchisquare(*arrs)
    return {
        "chi2": float(chi2),
        "p_value": float(pval),
        "n_cells": len(arrs[0]),
        "n_evaluators": len(evs),
        "evaluators": evs,
    }


def per_domain_breakdown(pe: list, c2_field: str) -> dict:
    """Group by clinical domain inferred from CPG name. Compute FA per domain."""
    DOMAIN_MAP = {
        "aha_chest_pain": "chest_pain",
        "aha_st": "chest_pain",
        "aha_stroke": "stroke",
        "aha_asa_ich": "stroke",
        "ncs_aha_sah": "stroke",
        "aha_heart_failure": "heart_failure",
        "aha_he": "heart_failure",
        "aha_cardiogenic_shock": "shock",
        "sccm_pediatric_septic_shock": "shock",
        "aha_ttm": "post_arrest",
        "aha_acc_aortic_dissection": "vascular",
        "kdigo_aki": "aki",
        "kdigo_contrast": "aki",
        "ssc_sepsis": "sepsis",
        "smfm_maternal_sepsis": "sepsis",
        "cap_pneumonia": "respiratory",
        "asthma": "respiratory",
        "gina": "respiratory",
        "copd": "respiratory",
        "ats_esicm_sccm_ards": "respiratory",
        "ers_ats_niv": "respiratory",
        "bts_pleural_disease": "respiratory",
        "atrial_fibrillation": "rhythm",
        "hrs_vt_sd": "rhythm",
        "acls": "arrest",
        "anaph": "anaphylaxis",
        "anaphylaxis": "anaphylaxis",
        "aabb_t": "transfusion",
        "isth_ash_ttp": "hematology",
        "ash_sickle_cell_acs": "hematology",
        "asco_tls": "oncology",
        "ada_dka": "endocrine",
        "ispad_pediatric_dka": "endocrine",
        "ukka_hyperkalemia": "electrolyte",
        "tox": "toxicology",
        "toxicology": "toxicology",
        "asam": "toxicology",
        "gi_bleeding": "gi",
        "baveno_vii_varices": "gi",
        "idsa_cdi": "gi",
        "meningitis": "neuro_infection",
        "status_epilepticus": "neuro",
        "hypertensive_emergency": "hypertension",
        "pulmonary_embolism": "pe",
        "pals_pediatric_traumatic_arrest": "pediatric",
        "nrp_neonatal_resuscitation": "pediatric",
        "gina_pediatric_status_asthma": "pediatric",
        "sccm_rsi": "airway",
        "east_damage_control_mtp": "trauma",
        "wses_pelvic_trauma_reboa": "trauma",
        "esvs_aaa": "vascular",
        "esvs_acute_limb_ischemia": "vascular",
        "erc_drowning": "drowning",
        "erc_hypothermia": "hypothermia",
        "eau_obstructive_pyelonephritis": "urology",
        "who_severe_malaria": "infectious",
        "aba_burn_resuscitation": "burn",
        "acog_obstetric": "obstetric",
        "apa_agitation": "psychiatry",
        "smfm": "obstetric",
        "universal_clinical_safety": "universal",
    }
    by_domain: dict = defaultdict(list)
    unmatched: dict = defaultdict(int)
    for ep in pe:
        sid = ep["scenario_id"]
        domain = None
        for prefix, dom in sorted(DOMAIN_MAP.items(), key=lambda x: -len(x[0])):
            if sid.startswith(prefix):
                domain = dom
                break
        if domain is None:
            domain = "unmatched"
            unmatched[sid.split("_")[0]] += 1
        by_domain[domain].append(ep)

    out = {}
    for domain, eps in by_domain.items():
        n = len(eps)
        n_v4 = sum(1 for ep in eps if ep["v4_hard"])
        n_fa3 = sum(1 for ep in eps if ep["ac_proxy"] and ep["mab_proxy"] and ep[c2_field] and ep["v4_hard"])
        n_fa_consensus = sum(1 for ep in eps if ep["dxem"] and ep["ac_proxy"] and ep[c2_field] and ep["v4_hard"])
        out[domain] = {
            "n": n,
            "tcc_fail_pct": round(100 * n_v4 / n, 2),
            "fa_strict_3way_pct": round(100 * n_fa3 / n, 2),
            "fa_strict_3way_count": n_fa3,
            "fa_consensus_pct": round(100 * n_fa_consensus / n, 2),
            "fa_consensus_count": n_fa_consensus,
        }
    return {
        "by_domain": dict(sorted(out.items(), key=lambda kv: -kv[1]["fa_strict_3way_count"])),
        "n_domains": len(out),
        "unmatched_prefixes": dict(unmatched),
    }


def compute_all(pe: list, c2_field: str, label: str) -> dict:
    print(f"\n=== {label} (n={len(pe)}) ===")
    mat = build_mat(pe, c2_field)
    n, k = mat.shape

    # Effect size with bootstrap
    print("  Bootstrapping η², partial η², ω², Fleiss κ, VPC...")
    eta_pt, eta_lo, eta_hi = bootstrap_ci(mat, eta2_eval)
    peta_pt, peta_lo, peta_hi = bootstrap_ci(mat, partial_eta2_rm)
    om_pt, om_lo, om_hi = bootstrap_ci(mat, omega_squared)
    fk_pt, fk_lo, fk_hi = bootstrap_ci(mat, fleiss_kappa)
    vpc_pt, vpc_lo, vpc_hi = bootstrap_ci(mat, vpc)

    # Cohen's f² (derived from η²)
    f2_pt = cohens_f2(eta_pt)
    f2_lo = cohens_f2(eta_lo)
    f2_hi = cohens_f2(eta_hi)

    # Cliff's δ (CGA-Bench vs AC-Proxy)
    print("  Bootstrapping Cliff's δ...")
    cga = mat[:, 3]
    ac = mat[:, 0]
    pair = np.column_stack([cga, ac])
    rng = np.random.default_rng(SEED)
    boots = np.empty(N_BOOTSTRAP)
    for b in range(N_BOOTSTRAP):
        idx = rng.integers(0, n, size=n)
        boots[b] = cliffs_delta(pair[idx, 0], pair[idx, 1])
    cliff_pt = cliffs_delta(cga, ac)
    cliff_lo, cliff_hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))

    # Rank-biserial (TCC verdict vs coverage score)
    print("  Bootstrapping rank-biserial...")
    tcc_pass = (1 - mat[:, 3].astype(int)) ^ 1  # cga_pass: 1 if pass; verdict for rb is binary fail-pass
    coverage = np.array([ep.get("action_coverage", 0.0) for ep in pe])
    pair = np.column_stack([cga, coverage])
    boots = np.empty(N_BOOTSTRAP)
    for b in range(N_BOOTSTRAP):
        idx = rng.integers(0, n, size=n)
        boots[b] = rank_biserial(pair[idx, 0], pair[idx, 1])
    rb_pt = rank_biserial(cga, coverage)
    rb_lo, rb_hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))

    # Power analysis
    eta_run_pt = eta2_run(pe, mat)
    power_obs = posthoc_power(eta_pt, n, k)
    mde = mde_eta2(n, k)

    # Null-calibrated ratio (use small n_perm for speed)
    print("  Permutation null distribution...")
    null = null_ratio_test(mat, eta_pt, n_perm=200)

    print(f"  η²(eval) = {eta_pt:.4f}  [{eta_lo:.4f}, {eta_hi:.4f}]")
    print(f"  η²(run)  = {eta_run_pt:.4f}")
    print(f"  partial η² = {peta_pt:.4f} [{peta_lo:.4f}, {peta_hi:.4f}]")
    print(f"  ω²        = {om_pt:.4f} [{om_lo:.4f}, {om_hi:.4f}]")
    print(f"  Fleiss κ  = {fk_pt:.4f} [{fk_lo:.4f}, {fk_hi:.4f}]")
    print(f"  Cohen f²  = {f2_pt:.3f} [{f2_lo:.3f}, {f2_hi:.3f}]")
    print(f"  Cliff δ   = {cliff_pt:+.3f} [{cliff_lo:+.3f}, {cliff_hi:+.3f}]")
    print(f"  VPC       = {vpc_pt:.4f} [{vpc_lo:.4f}, {vpc_hi:.4f}]")
    print(f"  rank-biserial r = {rb_pt:+.3f} [{rb_lo:+.3f}, {rb_hi:+.3f}]")
    print(
        f"  null-calibrated ratio = {null['null_ratio']}× (perm CI [{null['null_ci_lo']:.4f}, {null['null_ci_hi']:.4f}])"
    )
    print(f"  post-hoc power = {power_obs:.4f}; MDE η² @ 80% = {mde:.5f}")

    # Friedman test
    fr = friedman_test(pe, c2_field)
    print(
        f"  Friedman χ² = {fr.get('chi2', 'NA'):.3f}, p={fr.get('p_value', 'NA'):.3e}, n_cells={fr.get('n_cells', 'NA')}"
    )

    return {
        "n_episodes": n,
        "n_evaluators": k,
        "eta2_eval": {"point": eta_pt, "ci_lo": eta_lo, "ci_hi": eta_hi},
        "eta2_run": {"point": eta_run_pt},
        "partial_eta2": {"point": peta_pt, "ci_lo": peta_lo, "ci_hi": peta_hi},
        "omega2": {"point": om_pt, "ci_lo": om_lo, "ci_hi": om_hi},
        "fleiss_kappa": {"point": fk_pt, "ci_lo": fk_lo, "ci_hi": fk_hi},
        "cohens_f2": {"point": f2_pt, "ci_lo": f2_lo, "ci_hi": f2_hi},
        "cliffs_delta": {"point": cliff_pt, "ci_lo": cliff_lo, "ci_hi": cliff_hi},
        "vpc": {"point": vpc_pt, "ci_lo": vpc_lo, "ci_hi": vpc_hi},
        "rank_biserial": {"point": rb_pt, "ci_lo": rb_lo, "ci_hi": rb_hi},
        "null_ratio": null,
        "post_hoc_power": power_obs,
        "mde_eta2_at_80pct_power": mde,
        "friedman": fr,
    }


def write_macros(
    out_path: Path, orig: dict, typed: dict, fa_pb: dict, fa_pb_typed: dict, dom_pb: dict, dom_pb_typed: dict
) -> None:
    """LaTeX macros with \\vSixFull prefix (Phase B canonical)."""

    def f3(x):
        return f"{x:.3f}"

    def f4(x):
        return f"{x:.4f}"

    def f2(x):
        return f"{x:.2f}"

    L = []
    L.append(r"% v6 Full (Phase B) extras — auto-generated; CIs use 1000-bootstrap.")
    L.append(r"% Use \\providecommand for safe re-import alongside legacy \\cresFive* macros.")
    L.append("")
    L.append(rf"\providecommand{{\vSixFullN}}{{{orig['n_episodes']}}}")
    L.append("")
    # Effect-size battery (Phase B original CwT)
    L.append(r"% --- Phase B original CwT ---")
    L.append(rf"\providecommand{{\vSixFullEtaSq}}{{{f3(orig['eta2_eval']['point'])}}}")
    L.append(
        rf"\providecommand{{\vSixFullEtaSqCI}}{{{f3(orig['eta2_eval']['ci_lo'])}--{f3(orig['eta2_eval']['ci_hi'])}}}"
    )
    L.append(rf"\providecommand{{\vSixFullEtaRun}}{{{f4(orig['eta2_run']['point'])}}}")
    L.append(rf"\providecommand{{\vSixFullPartialEtaSq}}{{{f3(orig['partial_eta2']['point'])}}}")
    L.append(
        rf"\providecommand{{\vSixFullPartialEtaSqCI}}{{{f3(orig['partial_eta2']['ci_lo'])}--{f3(orig['partial_eta2']['ci_hi'])}}}"
    )
    L.append(rf"\providecommand{{\vSixFullOmegaSq}}{{{f3(orig['omega2']['point'])}}}")
    L.append(rf"\providecommand{{\vSixFullOmegaSqCI}}{{{f3(orig['omega2']['ci_lo'])}--{f3(orig['omega2']['ci_hi'])}}}")
    L.append(rf"\providecommand{{\vSixFullFleissKappa}}{{{f3(orig['fleiss_kappa']['point'])}}}")
    L.append(
        rf"\providecommand{{\vSixFullFleissKappaCI}}{{{f3(orig['fleiss_kappa']['ci_lo'])}--{f3(orig['fleiss_kappa']['ci_hi'])}}}"
    )
    L.append(rf"\providecommand{{\vSixFullCohenF}}{{{f3(orig['cohens_f2']['point'])}}}")
    L.append(
        rf"\providecommand{{\vSixFullCohenFCI}}{{{f3(orig['cohens_f2']['ci_lo'])}--{f3(orig['cohens_f2']['ci_hi'])}}}"
    )
    L.append(rf"\providecommand{{\vSixFullCliffDelta}}{{{f3(orig['cliffs_delta']['point'])}}}")
    L.append(
        rf"\providecommand{{\vSixFullCliffDeltaCI}}{{{f3(orig['cliffs_delta']['ci_lo'])}--{f3(orig['cliffs_delta']['ci_hi'])}}}"
    )
    L.append(rf"\providecommand{{\vSixFullVPC}}{{{f3(orig['vpc']['point'])}}}")
    L.append(rf"\providecommand{{\vSixFullVPCCI}}{{{f3(orig['vpc']['ci_lo'])}--{f3(orig['vpc']['ci_hi'])}}}")
    L.append(rf"\providecommand{{\vSixFullRankBiserial}}{{{f3(orig['rank_biserial']['point'])}}}")
    L.append(
        rf"\providecommand{{\vSixFullRankBiserialCI}}{{{f3(orig['rank_biserial']['ci_lo'])}--{f3(orig['rank_biserial']['ci_hi'])}}}"
    )
    L.append(
        rf"\providecommand{{\vSixFullNullRatio}}{{{f2(orig['null_ratio']['null_ratio']) if orig['null_ratio']['null_ratio'] else 'NA'}}}"
    )
    L.append(rf"\providecommand{{\vSixFullPostHocPower}}{{{f4(orig['post_hoc_power'])}}}")
    L.append(rf"\providecommand{{\vSixFullMDE}}{{{orig['mde_eta2_at_80pct_power']:.5f}}}")
    fr = orig.get("friedman", {})
    if "chi2" in fr:
        L.append(rf"\providecommand{{\vSixFullFriedmanChi}}{{{fr['chi2']:.2f}}}")
        L.append(rf"\providecommand{{\vSixFullFriedmanP}}{{{fr['p_value']:.3e}}}")
        L.append(rf"\providecommand{{\vSixFullFriedmanN}}{{{fr['n_cells']}}}")
    L.append("")
    # Phase B typed
    L.append(r"% --- Phase B typed CwT (DEV-excluded) ---")
    L.append(rf"\providecommand{{\vSixFullTypedEtaSq}}{{{f3(typed['eta2_eval']['point'])}}}")
    L.append(
        rf"\providecommand{{\vSixFullTypedEtaSqCI}}{{{f3(typed['eta2_eval']['ci_lo'])}--{f3(typed['eta2_eval']['ci_hi'])}}}"
    )
    L.append(rf"\providecommand{{\vSixFullTypedEtaRun}}{{{f4(typed['eta2_run']['point'])}}}")
    L.append(rf"\providecommand{{\vSixFullTypedPartialEtaSq}}{{{f3(typed['partial_eta2']['point'])}}}")
    L.append(rf"\providecommand{{\vSixFullTypedOmegaSq}}{{{f3(typed['omega2']['point'])}}}")
    L.append(rf"\providecommand{{\vSixFullTypedFleissKappa}}{{{f3(typed['fleiss_kappa']['point'])}}}")
    L.append(rf"\providecommand{{\vSixFullTypedCohenF}}{{{f3(typed['cohens_f2']['point'])}}}")
    L.append(rf"\providecommand{{\vSixFullTypedVPC}}{{{f3(typed['vpc']['point'])}}}")
    L.append("")
    # Phase B FA macros
    fa = fa_pb["phase_b_original"] if "phase_b_original" in fa_pb else fa_pb
    L.append(r"% --- Phase B FA totals ---")
    L.append(rf"\providecommand{{\vSixFullStrictFAThree}}{{{f2(fa['fa_strict_3way_pct'])}}}")
    L.append(rf"\providecommand{{\vSixFullStrictFAThreeCount}}{{{fa['fa_strict_3way_asc_paf_cwt']}}}")
    L.append(rf"\providecommand{{\vSixFullConsensusFA}}{{{f2(fa['fa_consensus_tom_asc_cwt_pct'])}}}")
    L.append(rf"\providecommand{{\vSixFullConsensusFACount}}{{{fa['fa_consensus_tom_asc_cwt']}}}")
    fa_t = fa_pb_typed["phase_b_typed"] if "phase_b_typed" in fa_pb_typed else fa_pb_typed
    L.append(rf"\providecommand{{\vSixFullTypedStrictFAThree}}{{{f2(fa_t['fa_strict_3way_pct'])}}}")
    L.append(rf"\providecommand{{\vSixFullTypedConsensusFA}}{{{f2(fa_t['fa_consensus_tom_asc_cwt_pct'])}}}")
    L.append("")
    # Per-domain
    if dom_pb and "by_domain" in dom_pb and dom_pb["by_domain"]:
        top_dom = next(iter(dom_pb["by_domain"]))
        top_d = dom_pb["by_domain"][top_dom]
        L.append(r"% --- Top-FA domain (Phase B original) ---")
        L.append(rf"\providecommand{{\vSixFullDomainMaxName}}{{{top_dom.replace('_', '\\_')}}}")
        L.append(rf"\providecommand{{\vSixFullDomainMaxFA}}{{{top_d['fa_strict_3way_count']}}}")
        L.append(rf"\providecommand{{\vSixFullDomainMaxPct}}{{{f2(top_d['fa_strict_3way_pct'])}}}")
        L.append(rf"\providecommand{{\vSixFullNumDomains}}{{{dom_pb['n_domains']}}}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(L) + "\n")
    print(f"\nSaved → {out_path}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vmatrix", default="evidence_pack/analysis/verdict_matrix_v6_full.json")
    p.add_argument("--vmatrix-typed", default="evidence_pack/analysis/verdict_matrix_v6_full_typed.json")
    p.add_argument("--out-json", default="evidence_pack/analysis/v6_full_extras.json")
    p.add_argument("--out-tex", default="evidence_pack/tables/v6_full_extras.tex")
    args = p.parse_args()

    print(f"Loading {args.vmatrix} and {args.vmatrix_typed}...")
    pe = json.load(open(args.vmatrix))["per_episode"]
    pet = json.load(open(args.vmatrix_typed))["per_episode"]

    # Original (Phase B)
    out_orig = compute_all(pe, "c2_pass", "Phase B original")
    out_typed = compute_all(pet, "c2_pass_typed", "Phase B typed")

    # Per-domain
    print("\n=== Per-domain breakdown ===")
    dom_orig = per_domain_breakdown(pe, "c2_pass")
    dom_typed = per_domain_breakdown(pet, "c2_pass_typed")
    print(
        f"  Total domains (orig): {dom_orig['n_domains']}, unmatched prefix counts: {dict(list(dom_orig['unmatched_prefixes'].items())[:5])}"
    )
    print("  Top 5 by FA count (Phase B original):")
    for i, (dom, d) in enumerate(list(dom_orig["by_domain"].items())[:5]):
        print(
            f"    {dom}: n={d['n']}, FA3={d['fa_strict_3way_pct']}% ({d['fa_strict_3way_count']}), TCC fail={d['tcc_fail_pct']}%"
        )

    # Phase B FA from existing v6_full_macros.json
    fa_data = json.load(open("evidence_pack/analysis/v6_full_macros.json"))["fa"]

    # Save
    out = {
        "phase_b_original": out_orig,
        "phase_b_typed": out_typed,
        "per_domain": {"original": dom_orig, "typed": dom_typed},
        "fa_reference": {
            "phase_b_original": fa_data.get("phase_b_original"),
            "phase_b_typed": fa_data.get("phase_b_typed"),
        },
    }
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {args.out_json}")

    # LaTeX macros
    write_macros(
        Path(args.out_tex),
        out_orig,
        out_typed,
        fa_data["phase_b_original"],
        fa_data["phase_b_typed"],
        dom_orig,
        dom_typed,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
