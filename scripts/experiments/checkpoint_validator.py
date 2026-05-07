#!/usr/bin/env python3
"""Checkpoint validator for clean slate experiment.

Usage:
    python checkpoint_validator.py <outdir> cp1   # First episode check
    python checkpoint_validator.py <outdir> cp2   # First model complete
    python checkpoint_validator.py <outdir> cp3   # All models complete
"""

import json
from pathlib import Path
import sys

MODELS = ["oss120b", "qwen35b", "qwen27b", "qwen4b"]
SCENARIOS = [
    "septic_shock_basic", "septic_shock_penicillin_allergy", "stemi_inferior_rv_trap",
    "dka_moderate_basic", "dka_hypokalemia_trap", "stroke_tpa_eligible",
    "contrast_aki_prevention_basic", "aki_stage1_basic", "af_new_onset_basic",
    "gi_bleeding_upper_basic", "htn_emergency_basic", "pe_submassive_basic",
    "copd_moderate_exacerbation", "adhf_warm_wet", "hemorrhagic_stroke",
]


def load_episodes(outdir: Path) -> list[dict]:
    """Load all episode JSON files."""
    episodes = []
    for f in outdir.rglob("*.json"):
        if f.name.startswith("log_") or f.name == "model_summary.json" or f.name == "experiment_summary.json":
            continue
        try:
            data = json.loads(f.read_text())
            data["_file"] = str(f)
            episodes.append(data)
        except Exception:
            pass
    return episodes


def cp1(outdir: Path) -> None:
    """Checkpoint 1: First episode validation."""
    episodes = load_episodes(outdir)
    if not episodes:
        print("FAIL: No episodes found yet")
        return

    print(f"Found {len(episodes)} episode(s)")
    errors = []

    for ep in episodes[:4]:  # Check up to 4 (one per model)
        print(f"\n--- {ep.get('model_name', '?')} / {ep.get('scenario_id', '?')} ---")
        print(f"  file: {ep.get('_file', '?')}")

        # Check prompt_condition
        cond = ep.get("prompt_condition", "MISSING")
        if cond != "baseline":
            errors.append(f"CRITICAL: prompt_condition={cond}, expected baseline")
        print(f"  prompt_condition: {cond}")

        # Check required fields
        for field in ["model_name", "scenario_id", "run_index", "compliance_score"]:
            val = ep.get(field, "MISSING")
            print(f"  {field}: {val}")
            if val == "MISSING":
                errors.append(f"Missing field: {field}")

        # CGA range
        cga = ep.get("compliance_score", -1)
        if not (0 <= cga <= 1):
            errors.append(f"CGA out of range: {cga}")
        if cga in (0.0, 1.0):
            print(f"  WARNING: CGA is exactly {cga} (extreme value)")

        # Actions
        actions = ep.get("actions", [])
        print(f"  actions: {len(actions)}")
        if len(actions) == 0:
            errors.append("CRITICAL: 0 actions (agent failure)")
        elif len(actions) < 6:
            print(f"  WARNING: only {len(actions)} actions (low)")

        # C3 check
        vbt = ep.get("violations_by_type", {})
        sub = ep.get("sub_scores", {})
        if vbt.get("commission", 0) > 0:
            c3 = sub.get("C3_forbidden_avoidance", -1)
            print(f"  COMMISSION detected: C3={c3}")
            if c3 != 0.0:
                errors.append(f"C3 fix broken: commission>0 but C3={c3}")

        print(f"  tokens: {ep.get('total_tokens', '?')}")

    if errors:
        print(f"\n{'='*50}")
        print(f"CHECKPOINT 1: FAIL ({len(errors)} errors)")
        for e in errors:
            print(f"  - {e}")
        if any("CRITICAL" in e for e in errors):
            print("ABORT RECOMMENDED")
    else:
        print(f"\n{'='*50}")
        print("CHECKPOINT 1: PASS")


def cp2(outdir: Path) -> None:
    """Checkpoint 2: First model complete."""
    episodes = load_episodes(outdir)
    print(f"Total episodes so far: {len(episodes)}")

    # Group by model
    by_model: dict[str, list] = {}
    for ep in episodes:
        model = ep.get("_file", "").split("/")[-2] if "/" in ep.get("_file", "") else "unknown"
        by_model.setdefault(model, []).append(ep)

    errors = []
    for model, eps in sorted(by_model.items()):
        print(f"\n--- {model}: {len(eps)} episodes ---")
        if len(eps) < 45:
            print(f"  Not complete yet ({len(eps)}/45)")
            continue

        # Scenario coverage
        scenarios = {}
        for ep in eps:
            sc = ep.get("scenario_id", "?")
            scenarios[sc] = scenarios.get(sc, 0) + 1

        missing = set(SCENARIOS) - set(scenarios.keys())
        if missing:
            errors.append(f"{model}: missing scenarios: {missing}")

        for sc, count in sorted(scenarios.items()):
            flag = "" if count == 3 else " *** EXPECTED 3"
            print(f"  {sc}: {count}{flag}")

        # All baseline?
        non_baseline = [ep for ep in eps if ep.get("prompt_condition") != "baseline"]
        if non_baseline:
            errors.append(f"{model}: {len(non_baseline)} non-baseline episodes!")
        print(f"  All baseline: {len(non_baseline) == 0}")

        # Failures
        failures = [ep for ep in eps if ep.get("status") == "agent_failure"]
        print(f"  Agent failures: {len(failures)}")
        if len(failures) >= 5:
            errors.append(f"{model}: {len(failures)} failures (>10%)")

        # CGA stats
        cga_vals = [ep["compliance_score"] for ep in eps if "compliance_score" in ep]
        if cga_vals:
            import statistics
            print(f"  CGA: mean={statistics.mean(cga_vals):.3f} std={statistics.stdev(cga_vals):.3f} "
                  f"min={min(cga_vals):.3f} max={max(cga_vals):.3f}")
            print(f"  CGA=0.0: {sum(1 for v in cga_vals if v == 0.0)}, CGA=1.0: {sum(1 for v in cga_vals if v == 1.0)}")

        # Action stats
        act_vals = [ep["actions_count"] for ep in eps if "actions_count" in ep]
        if act_vals:
            print(f"  Actions: mean={statistics.mean(act_vals):.1f} min={min(act_vals)} max={max(act_vals)}")
            zero_acts = sum(1 for v in act_vals if v == 0)
            if zero_acts:
                errors.append(f"{model}: {zero_acts} episodes with 0 actions")

    if errors:
        print(f"\n{'='*50}")
        print(f"CHECKPOINT 2: FAIL ({len(errors)} errors)")
        for e in errors:
            print(f"  - {e}")
    else:
        print(f"\n{'='*50}")
        print("CHECKPOINT 2: PASS")


def cp3(outdir: Path) -> None:
    """Checkpoint 3: All models complete."""
    episodes = load_episodes(outdir)
    print(f"Total episodes: {len(episodes)}")

    errors = []
    if len(episodes) < 180:
        errors.append(f"Only {len(episodes)}/180 episodes")

    # Group by model
    by_model: dict[str, list] = {}
    for ep in episodes:
        model = ep.get("_file", "").split("/")[-2] if "/" in ep.get("_file", "") else "unknown"
        by_model.setdefault(model, []).append(ep)

    import statistics

    print(f"\n{'Model':<12} {'N':>4} {'Scenarios':>10} {'CGA mean':>10} {'CGA std':>9} {'min':>6} {'max':>6}")
    print("-" * 60)
    for model in MODELS:
        eps = by_model.get(model, [])
        scenarios = set(ep.get("scenario_id") for ep in eps)
        cga = [ep["compliance_score"] for ep in eps if "compliance_score" in ep]
        if cga:
            print(f"{model:<12} {len(eps):>4} {len(scenarios):>10} {statistics.mean(cga):>10.3f} "
                  f"{statistics.stdev(cga):>9.3f} {min(cga):>6.3f} {max(cga):>6.3f}")
        else:
            print(f"{model:<12} {len(eps):>4} {len(scenarios):>10} {'N/A':>10}")
        if len(eps) != 45:
            errors.append(f"{model}: {len(eps)}/45 episodes")
        if len(scenarios) != 15:
            errors.append(f"{model}: {len(scenarios)}/15 scenarios")

    # All baseline
    non_baseline = [ep for ep in episodes if ep.get("prompt_condition") != "baseline"]
    print(f"\nAll baseline: {len(episodes) - len(non_baseline)}/{len(episodes)}")
    if non_baseline:
        errors.append(f"{len(non_baseline)} non-baseline episodes")

    # DKA commission check
    dka_eps = [ep for ep in episodes if ep.get("scenario_id") == "dka_hypokalemia_trap"]
    dka_commissions = [ep for ep in dka_eps if ep.get("violations_by_type", {}).get("commission", 0) > 0]
    print(f"\nDKA hypokalemia commission: {len(dka_commissions)}/{len(dka_eps)} episodes")
    if len(dka_eps) > 0 and len(dka_commissions) == 0:
        print("  WARNING: No commission detected in DKA (C3 fix may not be working)")

    # STEMI commission check
    stemi_eps = [ep for ep in episodes if ep.get("scenario_id") == "stemi_inferior_rv_trap"]
    stemi_commissions = [ep for ep in stemi_eps if ep.get("violations_by_type", {}).get("commission", 0) > 0]
    print(f"STEMI RV commission: {len(stemi_commissions)}/{len(stemi_eps)} episodes")

    # Scenario difficulty
    print("\n--- Scenario difficulty (4-model mean CGA) ---")
    by_scenario: dict[str, list[float]] = {}
    for ep in episodes:
        sc = ep.get("scenario_id", "?")
        if "compliance_score" in ep:
            by_scenario.setdefault(sc, []).append(ep["compliance_score"])

    ranked = sorted(by_scenario.items(), key=lambda x: statistics.mean(x[1]))
    print("Hardest 3:")
    for sc, vals in ranked[:3]:
        print(f"  {sc}: {statistics.mean(vals):.3f}")
    print("Easiest 3:")
    for sc, vals in ranked[-3:]:
        print(f"  {sc}: {statistics.mean(vals):.3f}")

    if errors:
        print(f"\n{'='*50}")
        print(f"CHECKPOINT 3: FAIL ({len(errors)} errors)")
        for e in errors:
            print(f"  - {e}")
    else:
        print(f"\n{'='*50}")
        print("CHECKPOINT 3: PASS -- Analysis approved")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <outdir> <cp1|cp2|cp3>")
        sys.exit(1)

    outdir = Path(sys.argv[1])
    checkpoint = sys.argv[2]

    if checkpoint == "cp1":
        cp1(outdir)
    elif checkpoint == "cp2":
        cp2(outdir)
    elif checkpoint == "cp3":
        cp3(outdir)
    else:
        print(f"Unknown checkpoint: {checkpoint}")
        sys.exit(1)
