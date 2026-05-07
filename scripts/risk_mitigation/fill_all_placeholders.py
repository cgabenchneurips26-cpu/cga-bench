#!/usr/bin/env python3
"""Fill all ?? placeholders in auto_numbers.tex.

Computes Tasks 2-8 from the 260405_fill_placeholder spec:
  Task 2: Variance Decomposition (η²) — 6 macros
  Task 3: Engine vs Manual — 8 macros
  Task 4: Held-out Generalizability — 2 macros
  Task 5: Difficulty Equivalence — 2 macros
  Task 6: Mixed-Effects GEE — 7 macros
  Task 7: Ranking Flip (Friedman/Kendall) — 5 macros
  Task 8: Timing Validity Audit — 7+ macros
  Task 9: E8 Replay (cross-benchmark) — 2 macros

Usage:
    PYTHONPATH=. python scripts/risk_mitigation/fill_all_placeholders.py
"""

from collections import defaultdict
from itertools import combinations
import json
import math
from pathlib import Path

import numpy as np
from scipy import stats

# ── Episode loading ──────────────────────────────────────────────────────────


COMPLETE_MODELS = frozenset(
    {
        "oss120b",
        "qwen27b",
        "qwen35b",
        "qwen4b",
        "qwen397b",
        "gemma31b",
        "nemotron30b",
    }
)


def load_episodes(episodes_dir: str) -> list:
    episodes = []
    seen_keys: set[str] = set()
    for model_dir in sorted(Path(episodes_dir).iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        if model_dir.name not in COMPLETE_MODELS:
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            if ep_file.name.startswith(("checkpoint", ".claim", "log_", "model_summary")):
                continue
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                if not isinstance(ep, dict):
                    continue
                sid = ep.get("scenario_id", "")
                if not sid:
                    continue
                key = f"{model_dir.name}_{sid}_{ep.get('run_index', 0)}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                ep["_model"] = model_dir.name
                episodes.append(ep)
            except Exception:
                pass
    return episodes


# ── Normalizer-aware action matching ─────────────────────────────────────────

_NORMALIZER = None


def _get_normalizer():
    global _NORMALIZER
    if _NORMALIZER is None:
        try:
            from cga_bench.assessor_core.action_normalizer import ActionNormalizer

            _NORMALIZER = ActionNormalizer()
        except ImportError:
            _NORMALIZER = False
    return _NORMALIZER if _NORMALIZER is not False else None


def _norm(name: str) -> str:
    n = name.lower().strip()
    normalizer = _get_normalizer()
    return normalizer.normalize(n) if normalizer else n


def get_verdicts(ep: dict) -> dict:
    """Compute 5 evaluator verdicts for an episode (normalizer-aware)."""
    normalizer = _get_normalizer()

    # Performed (normalized)
    performed = set()
    for a in ep.get("actions") or []:
        if isinstance(a, dict):
            name = a.get("action_id", a.get("action", ""))
            if name:
                performed.add(_norm(name))

    # Expected (normalized)
    expected = set()
    for a in ep.get("expected_actions") or []:
        if isinstance(a, str):
            expected.add(_norm(a))

    # Violations (recount OMISSION with normalizer)
    has_hard = False
    n_timing = 0
    n_forbidden_performed = 0
    for v in ep.get("violation_events") or []:
        if not isinstance(v, dict):
            continue
        vtype = v.get("violation_type", "").upper()

        if "OMISSION" in vtype:
            exp_action = v.get("expected_action", v.get("action_involved", ""))
            if exp_action and normalizer:
                if _norm(exp_action) in performed:
                    continue  # Resolved by normalizer
            has_hard = True
        elif "COMMISSION" in vtype or "FORBID" in vtype:
            has_hard = True
            n_forbidden_performed += 1
        elif "TIMING" in vtype:
            has_hard = True
            n_timing += 1
        elif "SEQUENCE" in vtype:
            has_hard = True

    # Also check compliance_score fallback
    if not has_hard and not (ep.get("violation_events") or []):
        cs = ep.get("compliance_score", 1.0)
        if cs < 1.0:
            has_hard = True

    # Coverage
    coverage = len(performed & expected) / len(expected) if expected else 1.0

    # TOM
    tom = True

    # ASC
    asc = coverage >= 0.5

    # CwT
    cwt_score = coverage - n_timing * 0.05
    cwt = cwt_score >= 0.7

    # PAF
    if performed and expected:
        tp = len(performed & expected)
        precision = tp / len(performed)
        recall = tp / len(expected)
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        paf_score = max(0, f1 - n_forbidden_performed * 0.1)
    elif not expected:
        paf_score = 1.0 if n_forbidden_performed == 0 else 0.5
    else:
        paf_score = 0.0
    paf = paf_score >= 0.5

    # TCC
    tcc = not has_hard

    return {"TOM": tom, "ASC": asc, "CwT": cwt, "PAF": paf, "TCC": tcc}


# ── Auto scenario detection ─────────────────────────────────────────────────

AUTO_MARKERS = {"_combo_", "_pathway_", "_trap_", "_single_trigger_", "_value_", "_time_sin_"}
HELDOUT_PREFIXES = {"aba_bu", "aabb_t", "acog", "apa", "ards", "dic", "hyperkalemia", "thyroid"}


def is_auto(sid: str) -> bool:
    return any(m in sid for m in AUTO_MARKERS)


def is_heldout(sid: str) -> bool:
    parts = sid.split("_")
    if len(parts) >= 2 and f"{parts[0]}_{parts[1]}" in HELDOUT_PREFIXES:
        return True
    return parts[0] in HELDOUT_PREFIXES


# ── Task 2: Variance Decomposition ──────────────────────────────────────────


def task2_variance_decomposition(episodes: list, all_verdicts: list) -> dict:
    """η² for evaluator vs run effect on verdict."""
    evaluators = ["TOM", "ASC", "CwT", "PAF", "TCC"]

    # Build long-form data: each row = (episode_idx, evaluator, verdict_01)
    n = len(all_verdicts)
    grand_mean_vals = []
    eval_means = {}
    for ev in evaluators:
        vals = [1 if v[ev] else 0 for v in all_verdicts]
        eval_means[ev] = np.mean(vals)
        grand_mean_vals.extend(vals)
    grand_mean = np.mean(grand_mean_vals)

    # SS_evaluator
    ss_eval = n * sum((eval_means[ev] - grand_mean) ** 2 for ev in evaluators)

    # SS_total
    ss_total = sum((v - grand_mean) ** 2 for v in grand_mean_vals)

    eta_evaluator = ss_eval / ss_total if ss_total > 0 else 0

    # Run effect: group by (scenario, model), compare across runs
    run_groups = defaultdict(list)
    for ep, v in zip(episodes, all_verdicts):
        sid = ep.get("scenario_id", "")
        model = ep.get("_model", "")
        run_idx = ep.get("run_index", 0)
        # TCC verdict as the outcome
        run_groups[(sid, model)].append(1 if v["TCC"] else 0)

    # Run instability: fraction of (scenario, model) groups with non-identical TCC across runs
    n_groups = 0
    n_unstable = 0
    for key, vals in run_groups.items():
        if len(vals) >= 2:
            n_groups += 1
            if len(set(vals)) > 1:
                n_unstable += 1

    run_instability = n_unstable / n_groups if n_groups > 0 else 0

    # η²(run) approximation: variance explained by run within (scenario, model) groups
    ss_run = 0
    for key, vals in run_groups.items():
        if len(vals) >= 2:
            group_mean = np.mean(vals)
            ss_run += sum((v - group_mean) ** 2 for v in vals)
    eta_run = ss_run / ss_total if ss_total > 0 else 0

    eta_ratio = eta_evaluator / eta_run if eta_run > 0 else float("inf")

    # Evaluator entropy: H = -Σ p_i log2(p_i) for evaluator pass rates
    pass_rates = [eval_means[ev] for ev in evaluators]
    entropy = 0
    for p in pass_rates:
        if 0 < p < 1:
            entropy -= p * math.log2(p) + (1 - p) * math.log2(1 - p)
    entropy /= len(evaluators)

    # Wilcoxon: ASC vs TCC verdicts
    asc_vals = [1 if v["ASC"] else 0 for v in all_verdicts]
    tcc_vals = [1 if v["TCC"] else 0 for v in all_verdicts]
    try:
        wilcoxon_stat, wilcoxon_p = stats.wilcoxon(asc_vals, tcc_vals)
    except ValueError:
        wilcoxon_p = 1.0

    return {
        "etaEvaluator": round(eta_evaluator, 3),
        "etaRun": round(eta_run, 4),
        "etaRatio": round(eta_ratio, 1) if eta_ratio != float("inf") else 999,
        "evalEntropy": round(entropy, 2),
        "runInstability": round(run_instability * 100, 1),
        "wilcoxonP": f"{wilcoxon_p:.2e}" if wilcoxon_p < 0.001 else f"{wilcoxon_p:.4f}",
    }


# ── Task 3: Engine vs Manual ────────────────────────────────────────────────


def task3_engine_vs_manual(episodes: list, all_verdicts: list) -> dict:
    manual_v = []
    auto_v = []
    manual_viols = []
    auto_viols = []
    manual_ctypes = set()
    auto_ctypes = set()

    for ep, v in zip(episodes, all_verdicts):
        sid = ep.get("scenario_id", "")
        n_viols = len(ep.get("violation_events") or [])

        # Collect violation types
        vtypes = set()
        for viol in ep.get("violation_events") or []:
            if isinstance(viol, dict):
                vt = viol.get("violation_type", "").upper()
                if "OMISSION" in vt:
                    vtypes.add("REQUIRED")
                elif "COMMISSION" in vt:
                    vtypes.add("FORBIDDEN")
                elif "TIMING" in vt:
                    vtypes.add("WITHIN")
                elif "SEQUENCE" in vt:
                    vtypes.add("BEFORE")

        if is_auto(sid):
            auto_v.append(v)
            auto_viols.append(n_viols)
            auto_ctypes.update(vtypes)
        else:
            manual_v.append(v)
            manual_viols.append(n_viols)
            manual_ctypes.update(vtypes)

    def vf_rate(verdicts):
        evaluators = ["TOM", "ASC", "CwT", "PAF", "TCC"]
        n_flip = sum(1 for v in verdicts if any(v[a] != v[b] for a, b in combinations(evaluators, 2)))
        return n_flip / len(verdicts) * 100 if verdicts else 0

    def bsr_asc(verdicts):
        n_fa = sum(1 for v in verdicts if v["ASC"] and not v["TCC"])
        return n_fa / len(verdicts) * 100 if verdicts else 0

    return {
        "vfManual": round(vf_rate(manual_v), 1),
        "vfAuto": round(vf_rate(auto_v), 1),
        "bsrManualAC": round(bsr_asc(manual_v), 1),
        "bsrAutoAC": round(bsr_asc(auto_v), 1),
        "violManual": round(np.mean(manual_viols), 1) if manual_viols else 0,
        "violAuto": round(np.mean(auto_viols), 1) if auto_viols else 0,
        "ctypeManual": len(manual_ctypes),
        "ctypeAuto": len(auto_ctypes),
    }


# ── Task 4: Held-out Generalizability ───────────────────────────────────────


def task4_heldout(episodes: list, all_verdicts: list) -> dict:
    heldout_v = [v for ep, v in zip(episodes, all_verdicts) if is_heldout(ep.get("scenario_id", ""))]

    evaluators = ["TOM", "ASC", "CwT", "PAF", "TCC"]
    n_flip = sum(1 for v in heldout_v if any(v[a] != v[b] for a, b in combinations(evaluators, 2)))
    vf = n_flip / len(heldout_v) * 100 if heldout_v else 0

    n_fa = sum(1 for v in heldout_v if v["ASC"] and not v["TCC"])
    bsr = n_fa / len(heldout_v) * 100 if heldout_v else 0

    return {
        "vfHeldout": round(vf, 1),
        "bsrHeldoutAC": round(bsr, 1),
        "_n_heldout": len(heldout_v),
    }


# ── Task 5: Difficulty Equivalence ──────────────────────────────────────────


def task5_difficulty(episodes: list) -> dict:
    manual_scores = []
    auto_scores = []

    for ep in episodes:
        cs = ep.get("compliance_score")
        if cs is None:
            continue
        sid = ep.get("scenario_id", "")
        if is_auto(sid):
            auto_scores.append(cs)
        else:
            manual_scores.append(cs)

    if manual_scores and auto_scores:
        mean_m = np.mean(manual_scores)
        mean_a = np.mean(auto_scores)
        sd_m = np.std(manual_scores, ddof=1)
        sd_a = np.std(auto_scores, ddof=1)
        n_m = len(manual_scores)
        n_a = len(auto_scores)
        pooled_sd = math.sqrt(((n_m - 1) * sd_m**2 + (n_a - 1) * sd_a**2) / (n_m + n_a - 2))
        cohen_d = (mean_a - mean_m) / pooled_sd if pooled_sd > 0 else 0

        # Spearman: model ordering consistency
        model_ranks_manual = defaultdict(list)
        model_ranks_auto = defaultdict(list)
        for ep in episodes:
            cs = ep.get("compliance_score")
            if cs is None:
                continue
            model = ep.get("_model", "")
            sid = ep.get("scenario_id", "")
            if is_auto(sid):
                model_ranks_auto[model].append(cs)
            else:
                model_ranks_manual[model].append(cs)

        models = sorted(set(model_ranks_manual.keys()) & set(model_ranks_auto.keys()))
        if len(models) >= 3:
            manual_means = [np.mean(model_ranks_manual[m]) for m in models]
            auto_means = [np.mean(model_ranks_auto[m]) for m in models]
            rho, _ = stats.spearmanr(manual_means, auto_means)
        else:
            rho = 0

        return {
            "cohenDDifficulty": round(cohen_d, 3),
            "spearmanManualAuto": round(rho, 2),
        }

    return {"cohenDDifficulty": 0, "spearmanManualAuto": 0}


# ── Task 6: GEE ─────────────────────────────────────────────────────────────


def task6_gee(episodes: list, all_verdicts: list) -> dict:
    """Mixed-effects GEE: verdict ~ evaluator with scenario clustering."""
    try:
        import pandas as pd
        import statsmodels.api as sm
        from statsmodels.genmod.families import Binomial
        from statsmodels.genmod.generalized_estimating_equations import GEE
    except ImportError:
        return {
            "geeMethod": "GEE (statsmodels unavailable)",
            "geeCoeffASC": 0,
            "geeCoeffCwT": 0,
            "geeCoeffPAF": 0,
            "geeORASC": 0,
            "geeORCwT": 0,
            "geeORPAF": 0,
        }

    rows = []
    for ep, v in zip(episodes, all_verdicts):
        sid = ep.get("scenario_id", "")
        for ev_name in ["ASC", "CwT", "PAF", "TCC"]:
            rows.append(
                {
                    "scenario_id": sid,
                    "evaluator": ev_name,
                    "verdict": 1 if v[ev_name] else 0,
                }
            )

    df = pd.DataFrame(rows)
    df["evaluator"] = pd.Categorical(df["evaluator"], categories=["TCC", "ASC", "CwT", "PAF"])

    try:
        model = GEE.from_formula(
            "verdict ~ C(evaluator, Treatment(reference='TCC'))",
            groups="scenario_id",
            data=df,
            family=Binomial(),
            cov_struct=sm.cov_struct.Exchangeable(),
        )
        result = model.fit(maxiter=100)

        params = result.params
        coeff_asc = params.get("C(evaluator, Treatment(reference='TCC'))[T.ASC]", 0)
        coeff_cwt = params.get("C(evaluator, Treatment(reference='TCC'))[T.CwT]", 0)
        coeff_paf = params.get("C(evaluator, Treatment(reference='TCC'))[T.PAF]", 0)

        return {
            "geeMethod": "GEE logistic (exchangeable)",
            "geeCoeffASC": round(coeff_asc, 2),
            "geeCoeffCwT": round(coeff_cwt, 2),
            "geeCoeffPAF": round(coeff_paf, 2),
            "geeORASC": round(math.exp(coeff_asc), 2),
            "geeORCwT": round(math.exp(coeff_cwt), 2),
            "geeORPAF": round(math.exp(coeff_paf), 2),
        }
    except Exception as e:
        print(f"  [WARN] GEE failed: {e}")
        # Fallback: simple OR from 2x2 tables
        ev_pass = {ev: sum(1 for v in all_verdicts if v[ev]) for ev in ["ASC", "CwT", "PAF", "TCC"]}
        ev_fail = {ev: len(all_verdicts) - ev_pass[ev] for ev in ev_pass}
        n = len(all_verdicts)
        tcc_odds = ev_pass["TCC"] / ev_fail["TCC"] if ev_fail["TCC"] > 0 else 1

        result = {"geeMethod": "Odds ratio (GEE failed)"}
        for ev in ["ASC", "CwT", "PAF"]:
            ev_odds = ev_pass[ev] / ev_fail[ev] if ev_fail[ev] > 0 else 1
            or_val = ev_odds / tcc_odds if tcc_odds > 0 else 1
            result[f"geeCoeff{ev}"] = round(math.log(or_val), 2) if or_val > 0 else 0
            result[f"geeOR{ev}"] = round(or_val, 2)
        return result


# ── Task 7: Ranking Flip ────────────────────────────────────────────────────


def task7_ranking_flip(episodes: list, all_verdicts: list) -> dict:
    evaluators = ["ASC", "CwT", "PAF", "TCC"]

    # Model pass rates per evaluator
    model_pass = defaultdict(lambda: defaultdict(list))
    for ep, v in zip(episodes, all_verdicts):
        model = ep.get("_model", "")
        for ev in evaluators:
            model_pass[ev][model].append(1 if v[ev] else 0)

    models = sorted(set.intersection(*[set(model_pass[ev].keys()) for ev in evaluators]))
    if len(models) < 3:
        return {"friedmanChi": 0, "friedmanP": 1, "kendallW": 0, "reversalRate": 0, "topOneFlip": "N/A"}

    # Build pass-rate matrix (models × evaluators) for Friedman test
    # and rank matrix for Kendall's W / reversal rate
    pass_rate_matrix = []  # rows = models
    rank_matrix = []  # rows = evaluators (transposed later)
    for ev in evaluators:
        means = [np.mean(model_pass[ev][m]) for m in models]
        pass_rate_matrix.append(means)
        ranks = stats.rankdata([-x for x in means])  # Higher pass rate = rank 1
        rank_matrix.append(ranks)

    pass_rate_matrix = np.array(pass_rate_matrix).T  # models × evaluators
    rank_matrix = np.array(rank_matrix).T  # models × evaluators

    # Kendall's W: inter-rater agreement (evaluators rank models)
    k = len(evaluators)
    n_m = len(models)
    rank_sums = rank_matrix.sum(axis=1)
    mean_rank_sum = np.mean(rank_sums)
    ss = np.sum((rank_sums - mean_rank_sum) ** 2)
    kendall_w = 12 * ss / (k**2 * (n_m**3 - n_m)) if (n_m**3 - n_m) > 0 else 0

    # Friedman test derived from Kendall W (same hypothesis: model ranking agreement)
    # χ² = k*(n-1)*W, df = n-1
    friedman_stat = k * (n_m - 1) * kendall_w
    friedman_p = 1 - stats.chi2.cdf(friedman_stat, df=n_m - 1) if friedman_stat > 0 else 1.0

    # Reversal rate: for each model pair, check if ranking flips across evaluators
    n_pairs = 0
    n_reversals = 0
    for i, j in combinations(range(n_m), 2):
        n_pairs += 1
        orders = set()
        for ev_idx in range(k):
            if rank_matrix[i, ev_idx] < rank_matrix[j, ev_idx]:
                orders.add("i<j")
            elif rank_matrix[i, ev_idx] > rank_matrix[j, ev_idx]:
                orders.add("i>j")
        if len(orders) > 1:
            n_reversals += 1
    reversal_rate = n_reversals / n_pairs * 100 if n_pairs > 0 else 0

    # Top-1 flip: does the best model change across evaluators?
    top1_models = set()
    for ev_idx, ev in enumerate(evaluators):
        best_idx = np.argmin(rank_matrix[:, ev_idx])
        top1_models.add(models[best_idx])
    top_one_flip = "yes" if len(top1_models) > 1 else "no"

    return {
        "friedmanChi": round(friedman_stat, 1),
        "friedmanP": f"{friedman_p:.2e}" if friedman_p < 0.001 else f"{friedman_p:.4f}",
        "kendallW": round(kendall_w, 3),
        "reversalRate": round(reversal_rate, 1),
        "topOneFlip": top_one_flip,
    }


# ── Task 8: Timing Validity Audit ───────────────────────────────────────────


def task8_timing(episodes: list) -> dict:
    margins = []
    timing_by_scenario_model = defaultdict(lambda: defaultdict(set))

    for ep in episodes:
        sid = ep.get("scenario_id", "")
        model = ep.get("_model", "")
        for v in ep.get("violation_events") or []:
            if not isinstance(v, dict):
                continue
            vtype = v.get("violation_type", "").upper()
            if "TIMING" not in vtype and "WITHIN" not in vtype:
                continue

            deadline = v.get("expected_deadline")
            actual = v.get("actual_time", v.get("timestamp_minutes"))
            if deadline is not None and actual is not None:
                try:
                    margin = float(actual) - float(deadline)
                    margins.append(margin)
                    action = v.get("action_involved", v.get("expected_action", "unknown"))
                    timing_by_scenario_model[sid][model].add(action)
                except (ValueError, TypeError):
                    pass

    n_within = len(margins)
    if n_within == 0:
        return {
            "timingNWithinViols": 0,
            "timingMeanMargin": 0,
            "timingMedianMargin": 0,
            "timingPctBoundary": 0,
            "timingPctOver60": 0,
            "timingIsBoundary": "no",
            "timingJaccard": 0,
            "timingNScenariosAgree": 0,
        }

    margins_arr = np.array(margins)
    mean_margin = np.mean(margins_arr)
    median_margin = np.median(margins_arr)
    pct_boundary = np.mean(margins_arr <= 5) * 100
    pct_over_60 = np.mean(margins_arr > 60) * 100

    # Cross-model Jaccard
    jaccards = []
    n_agree = 0
    for sid, model_sets in timing_by_scenario_model.items():
        models_here = list(model_sets.values())
        if len(models_here) < 2:
            continue
        all_same = True
        for a, b in combinations(models_here, 2):
            union = len(a | b)
            inter = len(a & b)
            if union > 0:
                jaccards.append(inter / union)
            if a != b:
                all_same = False
        if all_same:
            n_agree += 1

    return {
        "timingNWithinViols": n_within,
        "timingMeanMargin": round(mean_margin, 1),
        "timingMedianMargin": round(median_margin, 1),
        "timingPctBoundary": round(pct_boundary, 1),
        "timingPctOver60": round(pct_over_60, 1),
        "timingIsBoundary": "yes" if pct_boundary > 50 else "no",
        "timingJaccard": round(np.mean(jaccards), 3) if jaccards else 0,
        "timingNScenariosAgree": n_agree,
    }


# ── Task 9: E8 Replay ───────────────────────────────────────────────────────


def task9_e8_replay(episodes: list, all_verdicts: list) -> dict:
    """Cross-benchmark replay: apply MAB-F1 and AC-Diag scorers."""
    # MAB-F1: action-set F1 >= 0.5
    # AC-Diag: coverage >= 0.5 (same as ASC for our purposes)
    # Blind spot: native scorer pass AND TCC fail

    n = len(all_verdicts)
    # MAB-like: F1 >= 0.5 (same as PAF without forbidden penalty)
    mab_pass_and_tcc_fail = sum(1 for v in all_verdicts if v["PAF"] and not v["TCC"])
    mab_blind_pct = mab_pass_and_tcc_fail / n * 100 if n > 0 else 0

    # AC-like: coverage >= 0.5 (same as ASC)
    ac_pass_and_tcc_fail = sum(1 for v in all_verdicts if v["ASC"] and not v["TCC"])
    ac_blind_pct = ac_pass_and_tcc_fail / n * 100 if n > 0 else 0

    return {
        "crossReplayMABBlindPct": round(mab_blind_pct, 1),
        "crossReplayACBlindPct": round(ac_blind_pct, 1),
    }


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    episodes_dir = "results/full_706_v5"
    output_dir = Path("evidence_pack/fill_placeholders")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("FILL ALL ?? PLACEHOLDERS")
    print("=" * 70)

    episodes = load_episodes(episodes_dir)
    print(f"[INFO] {len(episodes)} episodes loaded\n")

    # Compute all verdicts once
    print("[STEP 1] Computing verdicts for all episodes...")
    all_verdicts = [get_verdicts(ep) for ep in episodes]

    # Run all tasks
    print("[STEP 2] Task 2: Variance Decomposition...")
    t2 = task2_variance_decomposition(episodes, all_verdicts)

    print("[STEP 3] Task 3: Engine vs Manual...")
    t3 = task3_engine_vs_manual(episodes, all_verdicts)

    print("[STEP 4] Task 4: Held-out Generalizability...")
    t4 = task4_heldout(episodes, all_verdicts)

    print("[STEP 5] Task 5: Difficulty Equivalence...")
    t5 = task5_difficulty(episodes)

    print("[STEP 6] Task 6: GEE...")
    t6 = task6_gee(episodes, all_verdicts)

    print("[STEP 7] Task 7: Ranking Flip...")
    t7 = task7_ranking_flip(episodes, all_verdicts)

    print("[STEP 8] Task 8: Timing Validity...")
    t8 = task8_timing(episodes)

    print("[STEP 9] Task 9: E8 Replay...")
    t9 = task9_e8_replay(episodes, all_verdicts)

    # Merge all results
    all_results = {}
    for label, result in [
        ("task2", t2),
        ("task3", t3),
        ("task4", t4),
        ("task5", t5),
        ("task6", t6),
        ("task7", t7),
        ("task8", t8),
        ("task9", t9),
    ]:
        all_results[label] = result

    # Print summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    # Flatten for auto_numbers
    macros = {}
    for task_result in [t2, t3, t4, t5, t6, t7, t8, t9]:
        for k, v in task_result.items():
            if not k.startswith("_"):
                macros[k] = v

    for k, v in sorted(macros.items()):
        print(f"  \\{k} = {v}")

    # Save
    with open(output_dir / "all_placeholder_results.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n[SAVED] {output_dir / 'all_placeholder_results.json'}")

    # Generate tex update snippet
    tex_lines = [
        "% Generated by fill_all_placeholders.py",
        f"% Based on {len(episodes)} episodes",
    ]
    for k, v in sorted(macros.items()):
        tex_lines.append(f"% \\renewcommand{{\\{k}}}{{{v}}}")
    tex_text = "\n".join(tex_lines)
    with open(output_dir / "placeholder_update.tex", "w") as f:
        f.write(tex_text)
    print(f"[SAVED] {output_dir / 'placeholder_update.tex'}")


if __name__ == "__main__":
    main()
