#!/usr/bin/env python3
"""Friedman + η² Raw Verification
================================
auto_numbers의 수치를 raw episode data에서 재계산하고,
중간 과정을 전부 보여준다.

확인할 것:
1. Friedman χ²=0.1, p=0.996 — 왜 비유의인가?
   → model ranking 행렬을 직접 출력해서 눈으로 확인
   → reversal rate 76.2%와 양립 가능한지

2. η²(evaluator)=0.312, η²(run)=0.036, ratio=8.7x
   → 이전 830x와 왜 다른지
   → ANOVA 중간 계산 전부 출력

Usage:
    python verify_friedman_eta.py --episodes-dir results/full_706_final
"""

import argparse
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path

import numpy as np

# 9 complete models — matches verdict_matrix_v5.py / _episode_cache.py
COMPLETE_MODELS = frozenset(
    {
        "oss120b",
        "qwen27b",
        "qwen35b",
        "qwen4b",
        "qwen397b",
        "gemma31b",
        "nemotron30b",
        "deepseek_r1_7b",
        "llama4scout",
    }
)


def load_episodes(episodes_dir):
    episodes = []
    seen_keys: set[str] = set()
    for model_dir in sorted(Path(episodes_dir).iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        if model_dir.name not in COMPLETE_MODELS:
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                key = f"{model_dir.name}_{ep.get('scenario_id', '')}_{ep.get('run_index', 0)}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                ep["_model"] = model_dir.name
                episodes.append(ep)
            except Exception:
                pass
    return episodes


def extract_action_name(a):
    if isinstance(a, str):
        return a.lower().strip()
    if isinstance(a, dict):
        return a.get("action_id", a.get("action", a.get("name", str(a)))).lower().strip()
    return str(a).lower().strip()


def compute_evaluator_verdicts(ep):
    """각 evaluator의 pass/fail을 직접 계산"""
    # Extract action sets
    performed = set()
    for a in ep.get("actions", []):
        name = extract_action_name(a)
        if name:
            performed.add(name)

    expected = set()
    for a in ep.get("expected_actions", ep.get("mandatory_actions", [])):
        name = extract_action_name(a)
        if name:
            expected.add(name)

    # Violations
    violations = ep.get("violation_events", [])
    has_hard = bool(violations) if isinstance(violations, list) else False
    if not has_hard:
        cs = ep.get("compliance_score", 1.0)
        if cs < 1.0:
            has_hard = True

    n_violations = len(violations) if isinstance(violations, list) else 0

    # Coverage
    if len(expected) > 0:
        coverage = len(performed & expected) / len(expected)
    else:
        coverage = 1.0

    verdicts = {
        "TOM": True,  # always pass
        "ASC": coverage >= 0.5,
        "CwT": coverage >= 0.7,
        "PAF": coverage >= 0.5,  # simplified
        "TCC": not has_hard,
    }

    return verdicts


# ═══════════════════════════════════════════════════════════════════
# PART 1: FRIEDMAN TEST VERIFICATION
# ═══════════════════════════════════════════════════════════════════


def verify_friedman(episodes):
    """Friedman test를 처음부터 다시 계산하고 중간 과정을 전부 보여준다."""
    print("=" * 70)
    print("PART 1: FRIEDMAN TEST RAW VERIFICATION")
    print("=" * 70)

    # Step 1: 각 (model, evaluator)의 pass rate 계산
    model_eval_pass = defaultdict(lambda: defaultdict(lambda: {"pass": 0, "total": 0}))

    for ep in episodes:
        model = ep.get("_model", "unknown")
        verdicts = compute_evaluator_verdicts(ep)
        for ev, passed in verdicts.items():
            model_eval_pass[model][ev]["total"] += 1
            if passed:
                model_eval_pass[model][ev]["pass"] += 1

    models = sorted(model_eval_pass.keys())
    evaluators = ["ASC", "CwT", "PAF", "TCC"]  # Exclude TOM (degenerate)

    print(f"\n  Models: {models}")
    print(f"  Evaluators: {evaluators}")
    print("  Episodes per model:")
    for m in models:
        n = model_eval_pass[m][evaluators[0]]["total"]
        print(f"    {m}: {n}")

    # Step 2: Pass rate matrix
    print("\n  PASS RATE MATRIX (%):")
    print(f"  {'Model':20s}", end="")
    for ev in evaluators:
        print(f" {ev:>8s}", end="")
    print()
    print("  " + "-" * (20 + 9 * len(evaluators)))

    pass_rate_matrix = []
    for m in models:
        rates = []
        print(f"  {m:20s}", end="")
        for ev in evaluators:
            d = model_eval_pass[m][ev]
            rate = d["pass"] / d["total"] * 100 if d["total"] > 0 else 0
            rates.append(rate)
            print(f" {rate:7.1f}%", end="")
        print()
        pass_rate_matrix.append(rates)

    pass_rate_matrix = np.array(pass_rate_matrix)

    # Step 3: RANK matrix (per evaluator, rank the models)
    print("\n  RANK MATRIX (per evaluator, 1=best):")
    print(f"  {'Model':20s}", end="")
    for ev in evaluators:
        print(f" {ev:>8s}", end="")
    print()
    print("  " + "-" * (20 + 9 * len(evaluators)))

    # Rank: higher pass rate = better = rank 1
    rank_matrix = np.zeros_like(pass_rate_matrix)
    for j in range(len(evaluators)):
        col = pass_rate_matrix[:, j]
        # rankdata: higher value → lower rank (1=best)
        # Use scipy-style ranking manually
        order = np.argsort(-col)  # descending
        ranks = np.empty_like(order, dtype=float)
        for rank_val, idx in enumerate(order):
            ranks[idx] = rank_val + 1
        rank_matrix[:, j] = ranks

    for i, m in enumerate(models):
        print(f"  {m:20s}", end="")
        for j in range(len(evaluators)):
            print(f" {rank_matrix[i, j]:8.0f}", end="")
        print()

    # Step 4: Friedman statistic
    n = len(models)  # number of "subjects" (models)
    k = len(evaluators)  # number of "treatments" (evaluators)

    # Friedman: rows = subjects, cols = treatments
    # χ² = (12 / (n*k*(k+1))) * Σ(R_j² for j=1..k) - 3*n*(k+1)
    # where R_j = sum of ranks in column j

    R_j = rank_matrix.sum(axis=0)  # sum of ranks per evaluator
    print(f"\n  Column rank sums R_j: {R_j}")
    print(f"  n (models) = {n}, k (evaluators) = {k}")

    chi2 = (12 / (n * k * (k + 1))) * np.sum(R_j**2) - 3 * n * (k + 1)
    df = k - 1

    print(f"\n  Friedman χ² = (12 / ({n}×{k}×{k + 1})) × Σ(R_j²) - 3×{n}×{k + 1}")
    print(f"             = (12 / {n * k * (k + 1)}) × {np.sum(R_j**2):.1f} - {3 * n * (k + 1)}")
    print(f"             = {chi2:.4f}")
    print(f"  df = {df}")

    # p-value from chi-squared distribution
    try:
        from scipy.stats import chi2 as chi2_dist
        from scipy.stats import friedmanchisquare

        p_value = 1 - chi2_dist.cdf(chi2, df)
        print(f"  p-value = {p_value:.6f}")

        # Also compute using scipy directly
        # Friedman needs at least 3 groups
        if k >= 3:
            # scipy.stats.friedmanchisquare wants columns of data
            # But it expects repeated measures data, not ranks
            # Let's use it on pass rates directly
            result = friedmanchisquare(*[pass_rate_matrix[:, j] for j in range(k)])
            print("\n  scipy friedmanchisquare on pass rates:")
            print(f"    χ² = {result.statistic:.4f}, p = {result.pvalue:.6f}")
    except ImportError:
        print("  (scipy not available for p-value computation)")
        p_value = None

    # Step 5: Reversal rate
    print("\n  PAIRWISE MODEL RANKING REVERSALS:")
    n_pairs = 0
    n_reversals = 0
    reversal_details = []

    for i, j in combinations(range(n), 2):
        m1, m2 = models[i], models[j]
        n_pairs += 1

        # Check if ranking order flips across any evaluator pair
        has_reversal = False
        for e1, e2 in combinations(range(k), 2):
            r1_e1 = rank_matrix[i, e1]
            r1_e2 = rank_matrix[i, e2]
            r2_e1 = rank_matrix[j, e1]
            r2_e2 = rank_matrix[j, e2]

            # Reversal: m1 ranked higher in e1 but lower in e2
            if (r1_e1 < r2_e1 and r1_e2 > r2_e2) or (r1_e1 > r2_e1 and r1_e2 < r2_e2):
                has_reversal = True
                break

        if has_reversal:
            n_reversals += 1
            reversal_details.append(f"    {m1} vs {m2}: REVERSED")
        else:
            reversal_details.append(f"    {m1} vs {m2}: consistent")

    for d in reversal_details:
        print(d)

    reversal_rate = n_reversals / n_pairs * 100 if n_pairs > 0 else 0
    print(f"\n  Reversal rate: {n_reversals}/{n_pairs} = {reversal_rate:.1f}%")

    # Step 6: Top-1 flip
    print("\n  TOP-1 MODEL PER EVALUATOR:")
    top1_models = []
    for j, ev in enumerate(evaluators):
        best_idx = np.argmin(rank_matrix[:, j])
        best_model = models[best_idx]
        best_rate = pass_rate_matrix[best_idx, j]
        top1_models.append(best_model)
        print(f"    {ev}: {best_model} ({best_rate:.1f}%)")

    top1_flip = len(set(top1_models)) > 1
    print(f"  Top-1 flips: {'YES' if top1_flip else 'NO'} ({len(set(top1_models))} unique top-1 models)")

    # Step 7: Kendall's W
    # W = (12 × Σ(R_j - R̄)² ) / (k² × n × (n² - 1))
    R_bar = R_j.mean()
    W = (12 * np.sum((R_j - R_bar) ** 2)) / (k**2 * n * (n**2 - 1))
    print(f"\n  Kendall's W = {W:.4f}")

    # Diagnosis
    print(f"\n  {'─' * 60}")
    print("  FRIEDMAN 진단:")
    if chi2 < 1.0 and reversal_rate > 50:
        print(f"  ⚠️ χ²={chi2:.2f}이 매우 낮은데 reversal={reversal_rate:.0f}%가 높음")
        print("  가능한 원인:")
        print(f"    1. n={n} 모델이 너무 적어서 Friedman 검정력 부족")
        print("    2. Reversal이 있지만 rank sum이 균형을 이뤄서 R_j가 비슷")
        print("    3. 계산에 TOM(degenerate)이 포함되었을 수 있음 — 모든 모델 동률")
        print("  → 논문에서 Friedman p를 주장 근거로 쓰면 안 됨")
        print(f"  → 대신 reversal rate {reversal_rate:.0f}%와 top-1 flip을 서술적으로 보고")
    print(f"  {'─' * 60}")

    return {
        "pass_rate_matrix": pass_rate_matrix.tolist(),
        "rank_matrix": rank_matrix.tolist(),
        "models": models,
        "evaluators": evaluators,
        "friedman_chi2": float(chi2),
        "friedman_p": float(p_value) if p_value is not None else None,
        "kendall_w": float(W),
        "reversal_rate": reversal_rate,
        "top1_flip": top1_flip,
    }


# ═══════════════════════════════════════════════════════════════════
# PART 2: η² VERIFICATION
# ═══════════════════════════════════════════════════════════════════


def verify_eta_squared(episodes):
    """η²(evaluator)와 η²(run)을 처음부터 계산하고 중간 과정을 보여준다."""
    print("\n" + "=" * 70)
    print("PART 2: η² (ETA-SQUARED) RAW VERIFICATION")
    print("=" * 70)

    evaluators = ["ASC", "CwT", "PAF", "TCC"]  # Exclude TOM

    # Build data: each row = (episode, evaluator, verdict, model, scenario, run)
    data_rows = []
    for ep in episodes:
        model = ep.get("_model", "unknown")
        scenario = ep.get("scenario_id", "unknown")
        run = ep.get("run_index", ep.get("run", ep.get("run_id", 0)))

        verdicts = compute_evaluator_verdicts(ep)
        for ev in evaluators:
            data_rows.append(
                {
                    "evaluator": ev,
                    "verdict": 1 if verdicts[ev] else 0,
                    "model": model,
                    "scenario": scenario,
                    "run": run,
                }
            )

    n_obs = len(data_rows)
    verdicts_array = np.array([r["verdict"] for r in data_rows])
    grand_mean = verdicts_array.mean()

    print(f"\n  Total observations: {n_obs}")
    print(f"  (= {len(episodes)} episodes × {len(evaluators)} evaluators)")
    print(f"  Grand mean (overall pass rate): {grand_mean:.4f}")

    # SS_total
    ss_total = np.sum((verdicts_array - grand_mean) ** 2)
    print(f"  SS_total = {ss_total:.2f}")

    # SS_evaluator
    eval_means = {}
    for ev in evaluators:
        ev_verdicts = [r["verdict"] for r in data_rows if r["evaluator"] == ev]
        eval_means[ev] = np.mean(ev_verdicts)

    ss_evaluator = sum(
        sum(1 for r in data_rows if r["evaluator"] == ev) * (eval_means[ev] - grand_mean) ** 2 for ev in evaluators
    )

    print("\n  Evaluator means:")
    for ev in evaluators:
        n_ev = sum(1 for r in data_rows if r["evaluator"] == ev)
        print(f"    {ev}: mean={eval_means[ev]:.4f}, n={n_ev}")
    print(f"  SS_evaluator = {ss_evaluator:.2f}")

    # SS_run: group by run within each (scenario, model) group
    # This measures run-to-run variance
    group_runs = defaultdict(lambda: defaultdict(list))
    for r in data_rows:
        key = (r["scenario"], r["model"], r["evaluator"])
        group_runs[key][r["run"]].append(r["verdict"])

    # Count unique runs
    all_runs = set(r["run"] for r in data_rows)
    print(f"\n  Unique runs: {sorted(all_runs)}")

    # For η²(run), we need run-level means
    run_means = {}
    for run_val in all_runs:
        run_verdicts = [r["verdict"] for r in data_rows if r["run"] == run_val]
        run_means[run_val] = np.mean(run_verdicts) if run_verdicts else 0

    ss_run = sum(
        sum(1 for r in data_rows if r["run"] == run_val) * (run_means[run_val] - grand_mean) ** 2
        for run_val in all_runs
    )

    print("  Run means:")
    for run_val in sorted(all_runs):
        n_run = sum(1 for r in data_rows if r["run"] == run_val)
        print(f"    run={run_val}: mean={run_means[run_val]:.4f}, n={n_run}")
    print(f"  SS_run = {ss_run:.2f}")

    # η²
    eta_evaluator = ss_evaluator / ss_total if ss_total > 0 else 0
    eta_run = ss_run / ss_total if ss_total > 0 else 0
    eta_ratio = eta_evaluator / eta_run if eta_run > 0 else float("inf")

    print(f"\n  η²(evaluator) = {ss_evaluator:.2f} / {ss_total:.2f} = {eta_evaluator:.4f} ({eta_evaluator * 100:.1f}%)")
    print(f"  η²(run) = {ss_run:.2f} / {ss_total:.2f} = {eta_run:.4f} ({eta_run * 100:.1f}%)")
    print(f"  η² ratio = {eta_ratio:.1f}x")

    # Compare with auto_numbers
    print(f"\n  {'─' * 60}")
    print("  auto_numbers 대비:")
    print(f"    η²(evaluator): auto_numbers={0.312}, computed={eta_evaluator:.3f}")
    print(f"    η²(run):       auto_numbers={0.036}, computed={eta_run:.3f}")
    print(f"    ratio:         auto_numbers={8.7},   computed={eta_ratio:.1f}")

    # Check for issues
    if abs(eta_evaluator - 0.312) > 0.05:
        print(f"  ⚠️ η²(evaluator) 불일치: |{eta_evaluator:.3f} - 0.312| > 0.05")
    if abs(eta_run - 0.036) > 0.01:
        print(f"  ⚠️ η²(run) 불일치: |{eta_run:.3f} - 0.036| > 0.01")

    # Check: what if TOM was included?
    print(f"\n  {'─' * 60}")
    print("  TOM 포함 시 (degenerate evaluator):")
    evaluators_with_tom = ["TOM", "ASC", "CwT", "PAF", "TCC"]
    data_with_tom = []
    for ep in episodes:
        verdicts = compute_evaluator_verdicts(ep)
        for ev in evaluators_with_tom:
            data_with_tom.append(
                {
                    "evaluator": ev,
                    "verdict": 1 if verdicts[ev] else 0,
                }
            )

    tom_verdicts = np.array([r["verdict"] for r in data_with_tom])
    tom_grand = tom_verdicts.mean()
    tom_ss_total = np.sum((tom_verdicts - tom_grand) ** 2)

    tom_eval_means = {}
    for ev in evaluators_with_tom:
        ev_v = [r["verdict"] for r in data_with_tom if r["evaluator"] == ev]
        tom_eval_means[ev] = np.mean(ev_v)

    tom_ss_eval = sum(
        sum(1 for r in data_with_tom if r["evaluator"] == ev) * (tom_eval_means[ev] - tom_grand) ** 2
        for ev in evaluators_with_tom
    )

    tom_eta_eval = tom_ss_eval / tom_ss_total if tom_ss_total > 0 else 0
    print(f"    With TOM: η²(evaluator) = {tom_eta_eval:.3f}")
    print(f"    Without TOM: η²(evaluator) = {eta_evaluator:.3f}")
    if abs(tom_eta_eval - eta_evaluator) > 0.05:
        print("    → TOM 포함 여부가 결과를 바꿈!")

    print(f"  {'─' * 60}")

    return {
        "eta_evaluator": float(eta_evaluator),
        "eta_run": float(eta_run),
        "eta_ratio": float(eta_ratio),
        "ss_total": float(ss_total),
        "ss_evaluator": float(ss_evaluator),
        "ss_run": float(ss_run),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes-dir", default="results/full_706_v5")
    parser.add_argument("--output-dir", default="evidence_pack/verify_stats")
    args = parser.parse_args()

    episodes = load_episodes(args.episodes_dir)
    print(f"Loaded {len(episodes)} episodes\n")

    if not episodes:
        print("[ERROR] No episodes")
        return

    # Part 1: Friedman
    friedman_results = verify_friedman(episodes)

    # Part 2: η²
    eta_results = verify_eta_squared(episodes)

    # Save
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {
        "friedman": friedman_results,
        "eta_squared": eta_results,
    }
    with open(output_dir / "verify_stats_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n[SAVED] {output_dir / 'verify_stats_results.json'}")


if __name__ == "__main__":
    main()
