
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""CP4 Friedman validity check: is N=45 single-run inflated?"""

from collections import defaultdict
import glob
import json
import os
import statistics

import numpy as np
from scipy.stats import friedmanchisquare

BASE = "results/clean_slate_20260331_210910"
MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]

# Load all episodes
episodes = defaultdict(list)
for model in MODELS:
    mpath = os.path.join(BASE, model)
    for f in sorted(glob.glob(os.path.join(mpath, "*.json"))):
        if f.endswith("model_summary.json"):
            continue
        with open(f) as fh:
            ep = json.load(fh)
        sid = ep.get("scenario_id", "unknown")
        episodes[(model, sid)].append(ep)

all_scenarios = sorted(set(sid for _, sid in episodes.keys()))


def get_cga(ep):
    return ep.get("compliance_score", 0.0)


def get_composite_a(ep):
    cga = get_cga(ep)
    n_acts = ep.get("actions_count", len(ep.get("actions", [])))
    n_exp = ep.get("n_expected_actions", len(ep.get("expected_actions", [])))
    if n_exp == 0:
        coverage = 1.0
    else:
        coverage = min(1.0, n_acts / (n_exp * 2))
    return cga * coverage


def run_friedman_safe(arrays, label):
    n = len(arrays[0])
    try:
        stat, p = friedmanchisquare(*arrays)
        k = len(arrays)
        eps2 = stat / (n * (k - 1))
    except Exception as e:
        print(f"  {label}: FAILED - {e}")
        return None
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"
    print(f"  {label}: N={n}, chi2={stat:.4f}, p={p:.6f} ({sig}), eps2={eps2:.4f}")
    return {"chi2": stat, "p": p, "sig": sig, "n": n}


# ============================================================
print("=" * 80)
print("STEP 1: N=45 single-run 행렬 구조 확인")
print("=" * 80)

# Reproduce the N=45 matrix from cp4_friedman.py
matrix_45 = {m: [] for m in MODELS}
block_labels = []
for sc in all_scenarios:
    for r in range(3):
        block_labels.append(f"{sc}_r{r}")
        for m in MODELS:
            eps = episodes.get((m, sc), [])
            matching = [e for e in eps if e.get("run_index", -1) == r]
            if matching:
                matrix_45[m].append(get_composite_a(matching[0]))
            else:
                matrix_45[m].append(0.0)

print(f"\nMatrix shape: 4 models x {len(matrix_45['oss120b'])} blocks")
print("Block construction: 15 scenarios x 3 runs = 45 blocks")
print(f"First 6 blocks: {block_labels[:6]}")
print("\nPROBLEM: septic_shock_basic_r0, r1, r2 are 3 separate blocks")
print("  but they share the same scenario -> intra-block correlation HIGH")
print("  -> effective N << 45, p-value is INFLATED")

# ============================================================
print("\n" + "=" * 80)
print("STEP 2: 올바른 분석 — run_index별 독립 Friedman (N=15)")
print("=" * 80)

for metric_name, metric_fn in [("Composite A", get_composite_a), ("CGA alone", get_cga)]:
    print(f"\n--- {metric_name} ---")

    for r in range(3):
        mat = {m: [] for m in MODELS}
        for sc in all_scenarios:
            for m in MODELS:
                eps = episodes.get((m, sc), [])
                matching = [e for e in eps if e.get("run_index", -1) == r]
                if matching:
                    mat[m].append(metric_fn(matching[0]))
                else:
                    mat[m].append(0.0)
        arrays = [np.array(mat[m]) for m in MODELS]
        run_friedman_safe(arrays, f"run_index={r} (N=15)")

    # Multi-run mean (canonical)
    mat = {m: [] for m in MODELS}
    for sc in all_scenarios:
        for m in MODELS:
            eps = episodes.get((m, sc), [])
            vals = [metric_fn(e) for e in eps]
            mat[m].append(statistics.mean(vals) if vals else 0.0)
    arrays = [np.array(mat[m]) for m in MODELS]
    run_friedman_safe(arrays, "multi-run mean (N=15, canonical)")

# ============================================================
print("\n" + "=" * 80)
print("STEP 3: 잘못된 N=45 vs 올바른 N=15 비교")
print("=" * 80)

for metric_name, metric_fn in [("Composite A", get_composite_a), ("CGA alone", get_cga)]:
    print(f"\n--- {metric_name} ---")

    # Wrong: N=45
    mat45 = {m: [] for m in MODELS}
    for sc in all_scenarios:
        for r in range(3):
            for m in MODELS:
                eps = episodes.get((m, sc), [])
                matching = [e for e in eps if e.get("run_index", -1) == r]
                if matching:
                    mat45[m].append(metric_fn(matching[0]))
                else:
                    mat45[m].append(0.0)
    arrays45 = [np.array(mat45[m]) for m in MODELS]
    run_friedman_safe(arrays45, "WRONG N=45 (runs as blocks)")

    # Right: N=15 multi-run mean
    mat15 = {m: [] for m in MODELS}
    for sc in all_scenarios:
        for m in MODELS:
            eps = episodes.get((m, sc), [])
            vals = [metric_fn(e) for e in eps]
            mat15[m].append(statistics.mean(vals) if vals else 0.0)
    arrays15 = [np.array(mat15[m]) for m in MODELS]
    run_friedman_safe(arrays15, "CORRECT N=15 (scenario means)")

# ============================================================
print("\n" + "=" * 80)
print("STEP 4: 판정")
print("=" * 80)

# Recompute for summary
for metric_name, metric_fn in [("Composite A", get_composite_a), ("CGA alone", get_cga)]:
    # N=15 canonical
    mat15 = {m: [] for m in MODELS}
    for sc in all_scenarios:
        for m in MODELS:
            eps = episodes.get((m, sc), [])
            vals = [metric_fn(e) for e in eps]
            mat15[m].append(statistics.mean(vals) if vals else 0.0)
    arrays15 = [np.array(mat15[m]) for m in MODELS]
    stat, p = friedmanchisquare(*arrays15)
    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"

    # N=45 inflated
    mat45 = {m: [] for m in MODELS}
    for sc in all_scenarios:
        for r in range(3):
            for m in MODELS:
                eps = episodes.get((m, sc), [])
                matching = [e for e in eps if e.get("run_index", -1) == r]
                if matching:
                    mat45[m].append(metric_fn(matching[0]))
                else:
                    mat45[m].append(0.0)
    arrays45 = [np.array(mat45[m]) for m in MODELS]
    stat45, p45 = friedmanchisquare(*arrays45)

    inflation = p / p45 if p45 > 0 else float("inf")
    print(f"\n{metric_name}:")
    print(f"  N=15 (correct):  p={p:.6f} ({sig})")
    print(f"  N=45 (inflated): p={p45:.6f}")
    print(f"  Inflation ratio: {inflation:.1f}x")

print("\n" + "-" * 40)
print("CONCLUSION:")
print("  N=45 single-run Friedman은 부적절함.")
print("  같은 시나리오의 3 runs는 독립 블록이 아님.")
print("  논문에는 N=15 (multi-run mean) 결과만 사용해야 함.")
print("  N=45 p-values는 CP4 보고에서 제거/주석 처리 필요.")
