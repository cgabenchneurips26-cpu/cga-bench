
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""Q3: Composite A 공식이 action 수에 과도하게 민감한가?"""

from collections import defaultdict
import glob
import json
import os
import statistics

import numpy as np

BASE = "results/clean_slate_20260331_210910"
MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]

# Load all episodes
all_eps = []
for model in MODELS:
    mpath = os.path.join(BASE, model)
    for f in sorted(glob.glob(os.path.join(mpath, "*.json"))):
        if f.endswith("model_summary.json"):
            continue
        with open(f) as fh:
            ep = json.load(fh)
        ep["_model"] = model
        all_eps.append(ep)


def get_metrics(ep):
    cga = ep.get("compliance_score", 0.0)
    n_acts = ep.get("actions_count", len(ep.get("actions", [])))
    n_exp = ep.get("n_expected_actions", len(ep.get("expected_actions", [])))
    if n_exp == 0:
        coverage = 1.0
    else:
        coverage = min(1.0, n_acts / (n_exp * 2))
    composite = cga * coverage
    return cga, n_acts, coverage, composite


# ============================================================
print("=" * 80)
print("Q3-1: Pearson 상관 분석 (180 episodes)")
print("=" * 80)

cga_all = []
acts_all = []
cov_all = []
comp_all = []

for ep in all_eps:
    cga, n_acts, cov, comp = get_metrics(ep)
    cga_all.append(cga)
    acts_all.append(n_acts)
    cov_all.append(cov)
    comp_all.append(comp)

cga_arr = np.array(cga_all)
acts_arr = np.array(acts_all)
cov_arr = np.array(cov_all)
comp_arr = np.array(comp_all)

r_comp_cga = np.corrcoef(comp_arr, cga_arr)[0, 1]
r_comp_acts = np.corrcoef(comp_arr, acts_arr)[0, 1]
r_cga_acts = np.corrcoef(cga_arr, acts_arr)[0, 1]
r_comp_cov = np.corrcoef(comp_arr, cov_arr)[0, 1]

print(f"\n  Composite A vs CGA:          r = {r_comp_cga:.4f}")
print(f"  Composite A vs action_count: r = {r_comp_acts:.4f}")
print(f"  Composite A vs coverage:     r = {r_comp_cov:.4f}")
print(f"  CGA vs action_count:         r = {r_cga_acts:.4f}")

print("\n  INTERPRETATION:")
if abs(r_comp_acts) > abs(r_comp_cga):
    print(f"  *** Composite A correlates MORE with action_count ({r_comp_acts:.4f})")
    print(f"      than with CGA ({r_comp_cga:.4f})")
    print("      -> Composite is dominated by activity volume, not guideline adherence")
else:
    print(f"  Composite A correlates MORE with CGA ({r_comp_cga:.4f})")
    print(f"  than with action_count ({r_comp_acts:.4f})")
    print("  -> CGA remains the dominant contributor")

# ============================================================
print("\n" + "=" * 80)
print("Q3-2: Coverage term 포화(saturation) 분석")
print("=" * 80)

for m in MODELS:
    m_eps = [e for e in all_eps if e["_model"] == m]
    covs = [get_metrics(e)[2] for e in m_eps]
    saturated = sum(1 for c in covs if abs(c - 1.0) < 1e-9)
    print(
        f"  {m:<12}: coverage mean={statistics.mean(covs):.4f}, "
        f"saturated(=1.0)={saturated}/{len(covs)} ({100 * saturated / len(covs):.0f}%)"
    )

print("\n  INTERPRETATION:")
# Check if oss120b is mostly saturated
oss_covs = [get_metrics(e)[2] for e in all_eps if e["_model"] == "oss120b"]
q4_covs = [get_metrics(e)[2] for e in all_eps if e["_model"] == "qwen4b"]
oss_sat = sum(1 for c in oss_covs if abs(c - 1.0) < 1e-9)
q4_sat = sum(1 for c in q4_covs if abs(c - 1.0) < 1e-9)
print(f"  oss120b saturated: {oss_sat}/45 ({100 * oss_sat / 45:.0f}%)")
print(f"  qwen4b saturated:  {q4_sat}/45 ({100 * q4_sat / 45:.0f}%)")

# ============================================================
print("\n" + "=" * 80)
print("Q3-3: Coverage term vs CGA — 모델간 분산 비교")
print("=" * 80)

model_means = {}
for m in MODELS:
    m_eps = [e for e in all_eps if e["_model"] == m]
    cgas = [get_metrics(e)[0] for e in m_eps]
    covs = [get_metrics(e)[2] for e in m_eps]
    comps = [get_metrics(e)[3] for e in m_eps]
    model_means[m] = {
        "cga": statistics.mean(cgas),
        "cov": statistics.mean(covs),
        "comp": statistics.mean(comps),
    }

print(f"\n  {'Model':<12} {'CGA mean':<12} {'Coverage mean':<15} {'Composite mean'}")
for m in MODELS:
    mm = model_means[m]
    print(f"  {m:<12} {mm['cga']:<12.4f} {mm['cov']:<15.4f} {mm['comp']:.4f}")

# Between-model variance
cga_means = [model_means[m]["cga"] for m in MODELS]
cov_means = [model_means[m]["cov"] for m in MODELS]
comp_means = [model_means[m]["comp"] for m in MODELS]

cga_var = statistics.variance(cga_means)
cov_var = statistics.variance(cov_means)
comp_var = statistics.variance(comp_means)

print("\n  Between-model variance:")
print(f"    CGA means variance:      {cga_var:.6f}")
print(f"    Coverage means variance: {cov_var:.6f}")
print(f"    Composite means variance:{comp_var:.6f}")

print(f"\n  Coverage/CGA variance ratio: {cov_var / cga_var:.2f}x")
if cov_var > cga_var:
    print("  *** Coverage term has MORE between-model variance than CGA")
    print("      -> Composite ranking is driven by coverage, not guideline adherence")
else:
    print("  CGA has more between-model variance than coverage term")
    print("  -> CGA drives the composite ranking")

# ============================================================
print("\n" + "=" * 80)
print("Q3-4: 대안 분석 — k값에 따른 Friedman p-value 변화")
print("=" * 80)

from scipy.stats import friedmanchisquare

all_scenarios = sorted(set(e.get("scenario_id") for e in all_eps))
episodes_by = defaultdict(list)
for e in all_eps:
    episodes_by[(e["_model"], e.get("scenario_id"))].append(e)

for k_val in [1.0, 1.5, 2.0, 3.0, 5.0, float("inf")]:
    mat = {m: [] for m in MODELS}
    for sc in all_scenarios:
        for m in MODELS:
            eps = episodes_by.get((m, sc), [])
            vals = []
            for ep in eps:
                cga = ep.get("compliance_score", 0.0)
                n_acts = ep.get("actions_count", 0)
                n_exp = ep.get("n_expected_actions", 0)
                if k_val == float("inf") or n_exp == 0:
                    cov = 1.0
                else:
                    cov = min(1.0, n_acts / (n_exp * k_val))
                vals.append(cga * cov)
            mat[m].append(statistics.mean(vals) if vals else 0.0)

    arrays = [np.array(mat[m]) for m in MODELS]
    stat, p = friedmanchisquare(*arrays)
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"
    k_str = "inf (CGA only)" if k_val == float("inf") else f"{k_val}"
    rankings = sorted([(m, np.mean(mat[m])) for m in MODELS], key=lambda x: -x[1])
    rank_str = " > ".join(f"{m}={v:.3f}" for m, v in rankings)
    print(f"  k={k_str:<15} p={p:.4f} ({sig})  {rank_str}")

print("\n  If ranking flips at different k -> composite is k-sensitive")
print("  If ranking stable across k -> composite reflects genuine model differences")
