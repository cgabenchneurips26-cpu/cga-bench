
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""Q2: CGA=1.0 에피소드 — 진짜 완벽인가, 채점 빈틈인가?"""

from collections import defaultdict
import glob
import json
import os

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
        ep["_file"] = f
        all_eps.append(ep)

# ============================================================
print("=" * 80)
print("Q2-1: CGA=1.0 에피소드 전수 분석")
print("=" * 80)

perfect = [e for e in all_eps if abs(e.get("compliance_score", 0) - 1.0) < 1e-9]
print(f"\nTotal CGA=1.0 episodes: {len(perfect)} / {len(all_eps)}")

# Model distribution
model_counts = defaultdict(int)
for e in perfect:
    model_counts[e["_model"]] += 1
print("\nBy model:")
for m in MODELS:
    print(f"  {m}: {model_counts[m]}")

# Scenario distribution
sc_counts = defaultdict(list)
for e in perfect:
    sc_counts[e.get("scenario_id", "?")].append(e["_model"])
print("\nBy scenario:")
for sc in sorted(sc_counts.keys()):
    models_list = sc_counts[sc]
    model_set = sorted(set(models_list))
    print(f"  {sc}: {len(models_list)} episodes ({model_set})")

# ============================================================
print("\n" + "=" * 80)
print("Q2-2: CGA=1.0 에피소드 상세")
print("=" * 80)

print(f"\n{'Model':<10} {'Scenario':<35} {'Run':<4} {'Acts':<5} {'Exp':<5} {'Done':<5} {'Viol':<5} {'TrackA':<8}")
for e in perfect:
    m = e["_model"]
    sc = e.get("scenario_id", "?")
    r = e.get("run_index", "?")
    n_acts = e.get("actions_count", len(e.get("actions", [])))
    exp = e.get("expected_actions", [])
    n_exp = len(exp)
    n_viol = e.get("total_violations", 0)

    # Track A: how many expected actions were actually performed?
    performed_actions = set()
    for a in e.get("actions", []):
        if isinstance(a, dict):
            performed_actions.add(a.get("action_id", ""))
        else:
            performed_actions.add(str(a))

    matched = sum(1 for ea in exp if ea in performed_actions)
    track_a = matched / n_exp if n_exp > 0 else 1.0

    print(f"  {m:<10} {sc:<35} r{r:<3} {n_acts:<5} {n_exp:<5} {matched:<5} {n_viol:<5} {track_a:<8.2f}")

# ============================================================
print("\n" + "=" * 80)
print("Q2-3: CGA=1.0 + Track A < 0.5 (적게 해서 만점 함정)")
print("=" * 80)

trap_cases = []
for e in perfect:
    exp = e.get("expected_actions", [])
    n_exp = len(exp)
    performed_actions = set()
    for a in e.get("actions", []):
        if isinstance(a, dict):
            performed_actions.add(a.get("action_id", ""))
        else:
            performed_actions.add(str(a))

    matched = sum(1 for ea in exp if ea in performed_actions)
    track_a = matched / n_exp if n_exp > 0 else 1.0

    if track_a < 0.5:
        trap_cases.append(
            {
                "model": e["_model"],
                "scenario": e.get("scenario_id", "?"),
                "run": e.get("run_index", "?"),
                "n_acts": e.get("actions_count", 0),
                "n_exp": n_exp,
                "matched": matched,
                "track_a": track_a,
            }
        )

if trap_cases:
    print(f"\nFOUND {len(trap_cases)} trap cases (CGA=1.0 but Track A < 0.5):")
    for t in trap_cases:
        print(
            f"  {t['model']}/{t['scenario']} r{t['run']}: "
            f"{t['matched']}/{t['n_exp']} expected done, "
            f"Track A={t['track_a']:.2f}, total actions={t['n_acts']}"
        )
else:
    print("\nNo trap cases found (all CGA=1.0 episodes have Track A >= 0.5)")

# Also check CGA=1.0 with Track A < 0.8
mild_trap = []
for e in perfect:
    exp = e.get("expected_actions", [])
    n_exp = len(exp)
    performed_actions = set()
    for a in e.get("actions", []):
        if isinstance(a, dict):
            performed_actions.add(a.get("action_id", ""))
        else:
            performed_actions.add(str(a))
    matched = sum(1 for ea in exp if ea in performed_actions)
    track_a = matched / n_exp if n_exp > 0 else 1.0
    if track_a < 0.8:
        mild_trap.append(
            {
                "model": e["_model"],
                "scenario": e.get("scenario_id", "?"),
                "run": e.get("run_index", "?"),
                "track_a": track_a,
                "matched": matched,
                "n_exp": n_exp,
                "n_acts": e.get("actions_count", 0),
            }
        )

if mild_trap:
    print(f"\nMild concern: {len(mild_trap)} episodes with CGA=1.0 but Track A < 0.8:")
    for t in mild_trap:
        print(
            f"  {t['model']}/{t['scenario']} r{t['run']}: "
            f"{t['matched']}/{t['n_exp']} expected, Track A={t['track_a']:.2f}"
        )

# ============================================================
print("\n" + "=" * 80)
print("Q2-4: CGA=1.0 시나리오의 CPG 복잡도")
print("=" * 80)

# Gather expected/forbidden counts per scenario from all episodes
sc_complexity = {}
for e in all_eps:
    sc = e.get("scenario_id", "?")
    if sc not in sc_complexity:
        sc_complexity[sc] = {
            "n_expected": len(e.get("expected_actions", [])),
            "n_forbidden": len(e.get("forbidden_actions", [])),
            "expected": e.get("expected_actions", []),
            "forbidden": e.get("forbidden_actions", []),
        }

perfect_scenarios = set(e.get("scenario_id") for e in perfect)
all_scenario_list = sorted(set(e.get("scenario_id") for e in all_eps))

print(f"\n{'Scenario':<40} {'Expected':<10} {'Forbidden':<10} {'Has 1.0?'}")
for sc in all_scenario_list:
    c = sc_complexity.get(sc, {})
    has_perfect = "YES" if sc in perfect_scenarios else "no"
    print(f"  {sc:<40} {c.get('n_expected', 0):<10} {c.get('n_forbidden', 0):<10} {has_perfect}")
