
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""CP4: Friedman analysis on clean slate 180-episode experiment."""

from collections import defaultdict
import glob
import json
import os
import statistics

import numpy as np
from scipy.stats import friedmanchisquare

BASE = "results/clean_slate_20260331_210910"
MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]
MODEL_LABELS = {
    "oss120b": "DeepSeek-R1-671B (oss-120b)",
    "qwen27b": "Qwen3.5-27B",
    "qwen35b": "Qwen3.5-35B",
    "qwen4b": "Qwen3-4B",
}

print("=" * 80)
print("CP4: FRIEDMAN ANALYSIS — Clean Slate Experiment")
print("=" * 80)

# Load all episodes
episodes = defaultdict(list)  # (model, scenario) -> [episode_dicts]

for model in MODELS:
    mpath = os.path.join(BASE, model)
    for f in sorted(glob.glob(os.path.join(mpath, "*.json"))):
        if f.endswith("model_summary.json"):
            continue
        with open(f) as fh:
            ep = json.load(fh)
        sid = ep.get("scenario_id", "unknown")
        episodes[(model, sid)].append(ep)

# Get scenario list
all_scenarios = sorted(set(sid for _, sid in episodes.keys()))
print(f"\nScenarios: {len(all_scenarios)}")
print(f"Models: {MODELS}")

# --- Helper functions ---


def get_cga(ep):
    return ep.get("compliance_score", 0.0)


def get_sub(ep, key):
    sub = ep.get("sub_scores", {})
    return sub.get(key, 0.0)


def get_composite_a(ep):
    """Composite A = CGA * min(1, actions / (expected * 2))"""
    cga = get_cga(ep)
    n_acts = ep.get("actions_count", len(ep.get("actions", [])))
    n_exp = ep.get("n_expected_actions", len(ep.get("expected_actions", [])))
    if n_exp == 0:
        coverage = 1.0
    else:
        coverage = min(1.0, n_acts / (n_exp * 2))
    return cga * coverage


def build_matrix(metric_fn, use_mean=True):
    """Build scenario x model matrix for Friedman test.

    If use_mean: average across runs per (model, scenario) -> 1 value each
    If not use_mean: use individual runs (expand scenarios by run_index)
    """
    matrix = {m: [] for m in MODELS}

    if use_mean:
        for sc in all_scenarios:
            for m in MODELS:
                eps = episodes.get((m, sc), [])
                if eps:
                    vals = [metric_fn(e) for e in eps]
                    matrix[m].append(statistics.mean(vals))
                else:
                    matrix[m].append(0.0)
    else:
        # Single-run: each (scenario, run_index) is a separate observation
        max_runs = 3
        for sc in all_scenarios:
            for r in range(max_runs):
                for m in MODELS:
                    eps = episodes.get((m, sc), [])
                    matching = [e for e in eps if e.get("run_index", -1) == r]
                    if matching:
                        matrix[m].append(metric_fn(matching[0]))
                    else:
                        matrix[m].append(0.0)

    return matrix


def run_friedman(matrix, label):
    """Run Friedman test and print results."""
    arrays = [np.array(matrix[m]) for m in MODELS]
    n = len(arrays[0])

    try:
        stat, p = friedmanchisquare(*arrays)
        k = len(MODELS)
        epsilon_sq = stat / (n * (k - 1))
    except Exception as e:
        print(f"  {label}: FAILED - {e}")
        return None

    sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"

    print(f"\n  {label}:")
    print(f"    N={n}, chi2={stat:.4f}, p={p:.6f} ({sig}), epsilon2={epsilon_sq:.4f}")

    # Model means
    means = {m: np.mean(matrix[m]) for m in MODELS}
    ranked = sorted(means.items(), key=lambda x: -x[1])
    print("    Rankings: ", end="")
    for i, (m, v) in enumerate(ranked):
        print(f"{MODEL_LABELS.get(m, m)}={v:.4f}", end="")
        if i < len(ranked) - 1:
            print(" > ", end="")
    print()

    return {"chi2": stat, "p": p, "epsilon2": epsilon_sq, "sig": sig, "n": n}


# --- Run all 5 Friedman tests ---

print("\n" + "=" * 80)
print("FRIEDMAN TEST RESULTS")
print("=" * 80)

# 1. Composite A (multi-run means)
mat = build_matrix(get_composite_a, use_mean=True)
r1 = run_friedman(mat, "1. Composite A (multi-run means, N=15)")

# 2. Composite A (single-run)
mat = build_matrix(get_composite_a, use_mean=False)
r2 = run_friedman(mat, "2. Composite A (single-run, N=45)")

# 3. CGA alone (multi-run means)
mat = build_matrix(get_cga, use_mean=True)
r3 = run_friedman(mat, "3. CGA alone (multi-run means, N=15)")

# 4. CGA alone (single-run)
mat = build_matrix(get_cga, use_mean=False)
r4 = run_friedman(mat, "4. CGA alone (single-run, N=45)")

# 5. C4 Timing (multi-run means)
mat = build_matrix(lambda ep: get_sub(ep, "C4_timing_compliance"), use_mean=True)
r5 = run_friedman(mat, "5. C4 Timing (multi-run means, N=15)")

# --- Additional sub-scores ---
print("\n" + "-" * 40)
print("ADDITIONAL SUB-SCORE FRIEDMAN TESTS")
print("-" * 40)

for sub_key in ["C1_path_selection", "C2_mandatory_completion", "C3_forbidden_avoidance", "C5_sequence_integrity"]:
    mat = build_matrix(lambda ep, k=sub_key: get_sub(ep, k), use_mean=True)
    run_friedman(mat, f"{sub_key} (multi-run means)")

# --- Per-scenario breakdown ---
print("\n" + "=" * 80)
print("PER-SCENARIO CGA BREAKDOWN")
print("=" * 80)
print(f"\n  {'Scenario':<40} ", end="")
for m in MODELS:
    print(f"{m:<10}", end="")
print()

for sc in all_scenarios:
    print(f"  {sc:<40} ", end="")
    for m in MODELS:
        eps = episodes.get((m, sc), [])
        if eps:
            mean_cga = statistics.mean([get_cga(e) for e in eps])
            print(f"{mean_cga:<10.4f}", end="")
        else:
            print(f"{'N/A':<10}", end="")
    print()

# --- Summary for paper narrative ---
print("\n" + "=" * 80)
print("CP4 SUMMARY FOR PAPER NARRATIVE")
print("=" * 80)

results = [r1, r2, r3, r4, r5]
labels = [
    "Composite A (multi-run)",
    "Composite A (single-run)",
    "CGA (multi-run)",
    "CGA (single-run)",
    "C4 Timing (multi-run)",
]

any_sig = False
for label, r in zip(labels, results):
    if r and r["p"] < 0.05:
        any_sig = True
        print(f"  SIGNIFICANT: {label} — p={r['p']:.6f} ({r['sig']})")
    elif r:
        print(f"  not sig:     {label} — p={r['p']:.6f} ({r['sig']})")

if any_sig:
    print("\n  => At least one significant result. Model size effect detected.")
else:
    print("\n  => No significant differences. Clean slate removes RAG advantage?")
    print("     This is itself a notable finding for the paper.")
