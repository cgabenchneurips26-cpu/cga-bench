
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""CP3 Validation: Full 180-episode clean slate experiment check."""

from collections import defaultdict
import glob
import json
import os
import statistics

BASE = "results/clean_slate_20260331_210910"
MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]

print("=" * 80)
print("CP3: FULL EPISODE VALIDATION")
print("=" * 80)

model_stats = {}

for model in MODELS:
    path = os.path.join(BASE, model)
    files = sorted(glob.glob(os.path.join(path, "*.json")))
    # Skip model_summary.json
    files = [f for f in files if not f.endswith("model_summary.json")]

    scenarios = defaultdict(int)
    conditions = set()
    failures = 0
    cga_scores = []
    action_counts = []
    commission_eps = []

    for f in files:
        with open(f) as fh:
            ep = json.load(fh)

        sid = ep.get("scenario_id", "unknown")
        scenarios[sid] += 1

        # Schema: top-level "condition" and "prompt_condition"
        cond = ep.get("prompt_condition", ep.get("condition", "missing"))
        conditions.add(cond)

        # Schema: top-level "compliance_score" (not nested cga_score)
        cga = ep.get("compliance_score", -1)
        cga_scores.append(cga)

        acts = ep.get("actions", [])
        action_counts.append(len(acts))

        if ep.get("agent_failure"):
            failures += 1

        # Schema: "violation_events" (not "violations")
        violations = ep.get("violation_events", ep.get("violations", []))
        if isinstance(violations, list):
            for v in violations:
                vtype = str(v.get("type", v.get("violation_type", "")))
                if "COMMISSION" in vtype.upper():
                    commission_eps.append(sid)
                    break

    model_stats[model] = {
        "count": len(files),
        "scenarios": dict(scenarios),
        "conditions": conditions,
        "failures": failures,
        "cga_mean": statistics.mean(cga_scores) if cga_scores else 0,
        "cga_std": statistics.stdev(cga_scores) if len(cga_scores) > 1 else 0,
        "cga_min": min(cga_scores) if cga_scores else 0,
        "cga_max": max(cga_scores) if cga_scores else 0,
        "act_mean": statistics.mean(action_counts) if action_counts else 0,
        "act_min": min(action_counts) if action_counts else 0,
        "act_max": max(action_counts) if action_counts else 0,
        "zero_actions": sum(1 for a in action_counts if a == 0),
        "cga_zero": sum(1 for c in cga_scores if abs(c) < 1e-9),
        "cga_one": sum(1 for c in cga_scores if abs(c - 1.0) < 1e-9),
        "commission_eps": commission_eps,
    }

# --- Reports ---

# 1. Total
total = sum(s["count"] for s in model_stats.values())
print(f"\n1. Total episodes: {total} (expected: 180)")
if total != 180:
    print(f"   *** MISMATCH: got {total}, expected 180 ***")

# 2. Per-model
print("\n2. Per-model breakdown:")
print(f"  {'Model':<12} {'Eps':<6} {'Scenarios':<10} Conditions")
for m in MODELS:
    s = model_stats[m]
    print(f"  {m:<12} {s['count']:<6} {len(s['scenarios']):<10} {s['conditions']}")

# 3. All baseline?
all_bl = all(s["conditions"] == {"baseline"} for s in model_stats.values())
print(f"\n3. All prompt_condition=baseline: {all_bl}")
for m in MODELS:
    conds = model_stats[m]["conditions"]
    if conds != {"baseline"}:
        print(f"   WARN: {m} -> {conds}")

# 4. CGA distribution
print("\n4. CGA Score Distribution:")
hdr = f"  {'Model':<12} {'Mean':<8} {'Std':<8} {'Min':<8} {'Max':<8} {'=0.0':<6} {'=1.0':<6}"
print(hdr)
for m in MODELS:
    s = model_stats[m]
    print(
        f"  {m:<12} {s['cga_mean']:<8.4f} {s['cga_std']:<8.4f} "
        f"{s['cga_min']:<8.4f} {s['cga_max']:<8.4f} {s['cga_zero']:<6} {s['cga_one']:<6}"
    )

# 5. Actions
print("\n5. Action Count Distribution:")
print(f"  {'Model':<12} {'Mean':<8} {'Min':<6} {'Max':<6} {'Zero':<6} {'Fail':<6}")
for m in MODELS:
    s = model_stats[m]
    print(
        f"  {m:<12} {s['act_mean']:<8.1f} {s['act_min']:<6} {s['act_max']:<6} {s['zero_actions']:<6} {s['failures']:<6}"
    )

# 6. Scenario coverage
print("\n6. Scenario Coverage:")
all_sc = set()
for m in MODELS:
    all_sc |= set(model_stats[m]["scenarios"].keys())
print(f"  Total unique scenarios: {len(all_sc)}")
for s in sorted(all_sc):
    counts = [model_stats[m]["scenarios"].get(s, 0) for m in MODELS]
    marker = "" if all(c == 3 for c in counts) else " ***"
    print(f"    {s:<40} {counts}{marker}")
for m in MODELS:
    missing = all_sc - set(model_stats[m]["scenarios"].keys())
    if missing:
        print(f"  WARN {m} missing: {missing}")

# 7. COMMISSION check
print("\n7. COMMISSION Detection (C3 fix validation):")
for m in MODELS:
    ce = model_stats[m]["commission_eps"]
    if ce:
        unique = set(ce)
        print(f"  {m}: {len(ce)} episodes ({len(unique)} scenarios): {unique}")
    else:
        print(f"  {m}: NONE detected")

# 8. Key trap scenarios
print("\n8. Key Trap Scenario Counts:")
for m in MODELS:
    sc = model_stats[m]["scenarios"]
    dka = sc.get("dka_hypokalemia_trap", 0)
    stemi = sc.get("stemi_inferior_rv_trap", 0)
    print(f"  {m}: dka_hypokalemia_trap={dka}, stemi_inferior_rv_trap={stemi}")

# 9. Hardest/easiest
print("\n9. Scenario Difficulty (4-model avg CGA):")
sc_cga = defaultdict(list)
for m in MODELS:
    mpath = os.path.join(BASE, m)
    for f in glob.glob(os.path.join(mpath, "*.json")):
        if f.endswith("model_summary.json"):
            continue
        with open(f) as fh:
            ep = json.load(fh)
        cga = ep.get("compliance_score", 0)
        sc_cga[ep.get("scenario_id", "?")].append(cga)

sc_avg = {s: statistics.mean(v) for s, v in sc_cga.items()}
sorted_sc = sorted(sc_avg.items(), key=lambda x: x[1])
print("  HARDEST:")
for s, v in sorted_sc[:5]:
    print(f"    {s}: {v:.4f}")
print("  EASIEST:")
for s, v in sorted_sc[-5:]:
    print(f"    {s}: {v:.4f}")

# 10. C3 deep check on trap scenarios
print("\n10. C3 Fix Deep Check (DKA + STEMI traps):")
trap_found = 0
for m in MODELS:
    mpath = os.path.join(BASE, m)
    for f in sorted(glob.glob(os.path.join(mpath, "*.json"))):
        if f.endswith("model_summary.json"):
            continue
        with open(f) as fh:
            ep = json.load(fh)
        sid = ep.get("scenario_id", "")
        if sid not in ("dka_hypokalemia_trap", "stemi_inferior_rv_trap"):
            continue
        violations = ep.get("violation_events", [])
        has_comm = False
        comm_action = ""
        for v in violations:
            vtype = str(v.get("type", v.get("violation_type", "")))
            if "COMMISSION" in vtype.upper():
                has_comm = True
                comm_action = v.get("action_id", v.get("action", "?"))
                break
        sub = ep.get("sub_scores", {})
        c3 = sub.get("C3_forbidden_avoidance", "N/A")
        run = ep.get("run_index", "?")
        cga = ep.get("compliance_score", 0)
        status = "COMMISSION" if has_comm else "clean"
        trap_found += 1
        print(f"  {m}/{sid} r{run}: {status}, C3={c3}, CGA={cga:.4f}" + (f", action={comm_action}" if has_comm else ""))

if trap_found == 0:
    print("  WARNING: No trap scenario episodes found!")

# Summary verdict
print("\n" + "=" * 80)
issues = []
if total != 180:
    issues.append(f"Episode count: {total} (expected 180)")
if not all_bl:
    issues.append("Not all baseline condition")
for m in MODELS:
    if model_stats[m]["zero_actions"] > 0:
        issues.append(f"{m} has {model_stats[m]['zero_actions']} zero-action episodes")
    if model_stats[m]["failures"] > 4:
        issues.append(f"{m} has {model_stats[m]['failures']} failures (>10%)")
    if model_stats[m]["cga_min"] < 0:
        issues.append(f"{m} has negative CGA score ({model_stats[m]['cga_min']})")

# Check all CGA=1.0 for any model (scoring broken)
for m in MODELS:
    if model_stats[m]["cga_one"] == model_stats[m]["count"]:
        issues.append(f"{m} ALL episodes CGA=1.0 (scoring not applied?)")

if issues:
    print("VERDICT: ISSUES FOUND")
    for i in issues:
        print(f"  - {i}")
else:
    print("VERDICT: ALL CHECKS PASSED - READY FOR ANALYSIS")
print("=" * 80)
