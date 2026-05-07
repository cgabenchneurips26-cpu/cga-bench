
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""Q1: Run간 분산 원인 추적 — r2가 왜 다른가?"""

from collections import defaultdict
import glob
import json
import os
import statistics

BASE = "results/clean_slate_20260331_210910"
MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]


def get_cga(ep):
    return ep.get("compliance_score", 0.0)


def get_composite_a(ep):
    cga = get_cga(ep)
    n_acts = ep.get("actions_count", len(ep.get("actions", [])))
    n_exp = ep.get("n_expected_actions", len(ep.get("expected_actions", [])))
    if n_exp == 0:
        return cga
    coverage = min(1.0, n_acts / (n_exp * 2))
    return cga * coverage


# Load episodes
episodes = defaultdict(dict)  # (model, scenario) -> {run_index: ep}
for model in MODELS:
    mpath = os.path.join(BASE, model)
    for f in sorted(glob.glob(os.path.join(mpath, "*.json"))):
        if f.endswith("model_summary.json"):
            continue
        with open(f) as fh:
            ep = json.load(fh)
        sid = ep.get("scenario_id", "unknown")
        r = ep.get("run_index", 0)
        episodes[(model, sid)][r] = ep

all_scenarios = sorted(set(sid for _, sid in episodes.keys()))

# ============================================================
print("=" * 80)
print("Q1-1: 전체 Composite A 테이블 (180 values)")
print("=" * 80)

header = f"{'Scenario':<40} {'Run':<4}"
for m in MODELS:
    header += f" {m:<10}"
print(header)
print("-" * len(header))

for sc in all_scenarios:
    for r in range(3):
        line = f"{sc:<40} r{r:<3}"
        for m in MODELS:
            ep = episodes.get((m, sc), {}).get(r)
            if ep:
                ca = get_composite_a(ep)
                line += f" {ca:<10.4f}"
            else:
                line += f" {'N/A':<10}"
        print(line)
    print()

# ============================================================
print("=" * 80)
print("Q1-2: r2에서 모델 순위 역전 시나리오")
print("=" * 80)

reversals = []
for sc in all_scenarios:
    # Get per-run rankings
    run_rankings = {}
    for r in range(3):
        vals = {}
        for m in MODELS:
            ep = episodes.get((m, sc), {}).get(r)
            if ep:
                vals[m] = get_composite_a(ep)
        run_rankings[r] = sorted(vals.items(), key=lambda x: -x[1])

    # Check if r2 reverses any pairwise order from r0/r1 consensus
    r0_order = [m for m, _ in run_rankings.get(0, [])]
    r1_order = [m for m, _ in run_rankings.get(1, [])]
    r2_order = [m for m, _ in run_rankings.get(2, [])]

    for i in range(len(MODELS)):
        for j in range(i + 1, len(MODELS)):
            if len(r0_order) <= j or len(r1_order) <= j or len(r2_order) <= j:
                continue
            # r0 and r1 agree on order of model pair
            r0_pair = r0_order.index(MODELS[i]) < r0_order.index(MODELS[j])
            r1_pair = r1_order.index(MODELS[i]) < r1_order.index(MODELS[j])
            r2_pair = r2_order.index(MODELS[i]) < r2_order.index(MODELS[j])

            if r0_pair == r1_pair and r0_pair != r2_pair:
                reversals.append(
                    {
                        "scenario": sc,
                        "pair": f"{MODELS[i]} vs {MODELS[j]}",
                        "r0r1_winner": MODELS[i] if r0_pair else MODELS[j],
                        "r2_winner": MODELS[j] if r0_pair else MODELS[i],
                    }
                )

print(f"Total r0/r1 consensus reversals in r2: {len(reversals)}")
for rev in reversals:
    print(f"  {rev['scenario']}: {rev['pair']} — r0/r1: {rev['r0r1_winner']} > , r2: {rev['r2_winner']} >")

# ============================================================
print("\n" + "=" * 80)
print("Q1-3: Run간 분산이 가장 큰 모델-시나리오 top 10")
print("=" * 80)

variances = []
for m in MODELS:
    for sc in all_scenarios:
        runs = episodes.get((m, sc), {})
        vals = [get_composite_a(runs[r]) for r in range(3) if r in runs]
        if len(vals) >= 2:
            v = statistics.variance(vals)
            variances.append(
                {
                    "model": m,
                    "scenario": sc,
                    "variance": v,
                    "values": vals,
                    "actions": [runs[r].get("actions_count", 0) for r in range(3) if r in runs],
                }
            )

variances.sort(key=lambda x: -x["variance"])
print(f"{'Model':<12} {'Scenario':<35} {'Var':<8} {'CompA values':<30} {'Action counts'}")
for v in variances[:10]:
    vals_str = ", ".join(f"{x:.4f}" for x in v["values"])
    acts_str = ", ".join(str(x) for x in v["actions"])
    print(f"  {v['model']:<12} {v['scenario']:<35} {v['variance']:<8.4f} [{vals_str}]  [{acts_str}]")

# High-variance episode action comparison
print("\n--- Top 1 high-variance case: action list comparison ---")
top = variances[0]
m, sc = top["model"], top["scenario"]
for r in range(3):
    ep = episodes.get((m, sc), {}).get(r)
    if ep:
        acts = [a.get("action_id", a) if isinstance(a, dict) else a for a in ep.get("actions", [])]
        print(f"\n  {m}/{sc} r{r}: CompA={get_composite_a(ep):.4f}, {len(acts)} actions")
        for a in acts[:15]:
            print(f"    - {a}")
        if len(acts) > 15:
            print(f"    ... ({len(acts) - 15} more)")

# ============================================================
print("\n" + "=" * 80)
print("Q1-4: LLM Temperature/Sampling 설정 확인")
print("=" * 80)

# Check agent configs
config_dir = "configs/agents"
for cfile in sorted(glob.glob(os.path.join(config_dir, "clean_slate_*.yaml"))):
    print(f"\n--- {os.path.basename(cfile)} ---")
    with open(cfile) as fh:
        content = fh.read()
    # Extract temperature/sampling related lines
    for line in content.split("\n"):
        low = line.lower()
        if any(k in low for k in ["temperature", "top_p", "top_k", "sampling", "seed", "random"]):
            print(f"  {line.strip()}")
    if "temperature" not in content.lower():
        print("  WARNING: No temperature setting found")

# Check runner script
print("\n--- clean_slate runner temperature check ---")
runner_files = glob.glob("scripts/experiments/run_clean_slate*.py") + glob.glob("scripts/run_clean_slate*.py")
for rf in runner_files:
    with open(rf) as fh:
        content = fh.read()
    for i, line in enumerate(content.split("\n")):
        low = line.lower()
        if any(k in low for k in ["temperature", "top_p", "top_k"]):
            print(f"  {os.path.basename(rf)}:{i + 1}: {line.strip()}")
