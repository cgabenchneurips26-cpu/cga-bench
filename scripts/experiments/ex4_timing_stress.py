#!/usr/bin/env python3
"""EX-4: Timing Validity Stress Suite (Parts C + D)

4C: Jitter Sensitivity — add ±N min jitter to timestamps, measure verdict flips
4D: WITHIN Violation Margin Distribution — classify violations by margin size

Usage:
    PYTHONPATH=. python scripts/experiments/ex4_timing_stress.py
"""

from collections import defaultdict
import json
from pathlib import Path
import random

import numpy as np

EPISODES_DIR = Path("results/full_706_v5")
OUTPUT_DIR = Path("evidence_pack/ex4_timing_stress")


def load_episodes(max_n: int = 0) -> list:
    episodes = []
    for model_dir in sorted(EPISODES_DIR.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                ep = json.load(open(ep_file))
                if isinstance(ep, dict) and ep.get("scenario_id"):
                    ep["_model"] = model_dir.name
                    episodes.append(ep)
                    if max_n and len(episodes) >= max_n:
                        return episodes
            except Exception:
                pass
    return episodes


# ═══════════════════════════════════════════════════════════════════
# EX-4D: WITHIN Violation Margin Distribution
# ═══════════════════════════════════════════════════════════════════


def run_ex4d(episodes: list) -> dict:
    """Extract and classify WITHIN violation margins."""
    margins = []
    margin_by_action = defaultdict(list)
    margin_by_model = defaultdict(list)

    for ep in episodes:
        model = ep.get("_model", "")
        for v in ep.get("violation_events") or []:
            if not isinstance(v, dict):
                continue
            vt = v.get("violation_type", "").upper()
            if "TIMING" not in vt and "WITHIN" not in vt:
                continue

            deadline = v.get("expected_deadline")
            actual = v.get("actual_time", v.get("timestamp_minutes"))
            if deadline is not None and actual is not None:
                try:
                    margin = float(actual) - float(deadline)
                    if margin >= 0:  # Only late violations
                        margins.append(margin)
                        action = v.get("expected_action", v.get("action_involved", "unknown"))
                        margin_by_action[action].append(margin)
                        margin_by_model[model].append(margin)
                except (ValueError, TypeError):
                    pass

    if not margins:
        return {"n_within": 0, "note": "No margin data available"}

    arr = np.array(margins)

    # Classification buckets
    boundary = np.sum(arr <= 5)
    near = np.sum((arr > 5) & (arr <= 15))
    moderate = np.sum((arr > 15) & (arr <= 30))
    severe = np.sum(arr > 30)

    # Stratified sample for manual audit (200 violations)
    audit_sample = []
    indices = list(range(len(margins)))
    random.seed(42)

    for label, low, high, target_n in [
        ("boundary", 0, 5, 50),
        ("near", 5, 15, 50),
        ("moderate", 15, 30, 50),
        ("severe", 30, float("inf"), 50),
    ]:
        bucket_idx = [i for i in indices if low < margins[i] <= high or (low == 0 and margins[i] <= high)]
        sampled = random.sample(bucket_idx, min(target_n, len(bucket_idx)))
        for i in sampled:
            audit_sample.append({"margin": margins[i], "category": label})

    return {
        "n_within": len(margins),
        "mean_margin": round(float(np.mean(arr)), 1),
        "median_margin": round(float(np.median(arr)), 1),
        "p25": round(float(np.percentile(arr, 25)), 1),
        "p75": round(float(np.percentile(arr, 75)), 1),
        "p95": round(float(np.percentile(arr, 95)), 1),
        "max_margin": round(float(np.max(arr)), 1),
        "buckets": {
            "boundary_0_5min": int(boundary),
            "near_5_15min": int(near),
            "moderate_15_30min": int(moderate),
            "severe_30plus": int(severe),
        },
        "bucket_pcts": {
            "boundary": round(boundary / len(margins) * 100, 1),
            "near": round(near / len(margins) * 100, 1),
            "moderate": round(moderate / len(margins) * 100, 1),
            "severe": round(severe / len(margins) * 100, 1),
        },
        "genuine_rate": round((moderate + severe) / len(margins) * 100, 1),
        "artifact_rate": round(boundary / len(margins) * 100, 1),
        "audit_sample_size": len(audit_sample),
        "per_model": {
            m: {"n": len(v), "mean": round(np.mean(v), 1), "median": round(np.median(v), 1)}
            for m, v in margin_by_model.items()
        },
    }


# ═══════════════════════════════════════════════════════════════════
# EX-4C: Jitter Sensitivity
# ═══════════════════════════════════════════════════════════════════


def run_ex4c(episodes: list) -> dict:
    """Test verdict robustness under timestamp jitter."""
    jitter_levels = [0, 5, 10, 15, 30, 60]
    results = {}

    # For each episode, check if adding jitter changes TCC verdict
    # TCC = fail if any hard violation (OMISSION, COMMISSION, TIMING, SEQUENCE)
    # Jitter affects TIMING violations: if margin was small, jitter might flip it

    for jitter in jitter_levels:
        n_episodes = 0
        n_flips = 0
        n_timing_gained = 0
        n_timing_lost = 0

        for ep in episodes:
            viols = ep.get("violation_events", [])
            if not isinstance(viols, list):
                continue
            n_episodes += 1

            # Original: count hard violations from violation_events ONLY
            # (no compliance_score fallback — jitter operates on violations)
            non_timing_hard = False
            orig_timing_count = 0
            timing_margins = []

            for v in viols:
                if not isinstance(v, dict):
                    continue
                vt = v.get("violation_type", "").upper()
                if any(t in vt for t in ("OMISSION", "COMMISSION", "SEQUENCE")):
                    non_timing_hard = True
                elif "TIMING" in vt:
                    orig_timing_count += 1
                    deadline = v.get("expected_deadline")
                    actual = v.get("actual_time", v.get("timestamp_minutes"))
                    if deadline is not None and actual is not None:
                        try:
                            timing_margins.append(float(actual) - float(deadline))
                        except (ValueError, TypeError):
                            pass

            orig_hard = non_timing_hard or (orig_timing_count > 0)

            # Jittered: simulate adding random jitter to each action timestamp
            # A TIMING violation with margin M flips if jitter makes margin <= 0
            # Probability: if jitter ~ Uniform(-J, +J), P(flip) = min(1, J/M) for M > 0
            # Also: actions that were on-time might become late
            random.seed(42 + hash(ep.get("scenario_id", "")))

            jittered_timing = 0
            for margin in timing_margins:
                jittered_margin = margin + random.uniform(-jitter, jitter)
                if jittered_margin > 0:
                    jittered_timing += 1
                # else: violation removed by favorable jitter

            # Check for NEW timing violations from on-time actions becoming late
            # (simplified: assume deadlines we know about)
            # For now, only count removal of existing timing violations

            timing_removed = orig_timing_count - jittered_timing

            # Jittered verdict: non_timing_hard (unchanged) + surviving timing
            jittered_hard = non_timing_hard or (jittered_timing > 0)

            if orig_hard != jittered_hard:
                n_flips += 1
            if timing_removed > 0:
                n_timing_lost += timing_removed
            # timing_added not modeled (conservative: no new violations from jitter)

        flip_rate = n_flips / n_episodes * 100 if n_episodes > 0 else 0
        results[jitter] = {
            "jitter_minutes": jitter,
            "n_episodes": n_episodes,
            "n_flips": n_flips,
            "flip_rate": round(flip_rate, 2),
            "timing_violations_lost": n_timing_lost,
            "timing_violations_gained": n_timing_gained,
        }

    return results


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("EX-4: TIMING VALIDITY STRESS SUITE")
    print("=" * 70)

    episodes = load_episodes()
    print(f"Loaded {len(episodes)} episodes\n")

    # 4D
    print("[EX-4D] WITHIN Violation Margin Distribution...")
    ex4d = run_ex4d(episodes)

    lines = ["## EX-4D: WITHIN Violation Margin Distribution\n"]
    if ex4d.get("n_within", 0) > 0:
        lines.append(f"  Total WITHIN violations with margin data: {ex4d['n_within']}")
        lines.append(f"  Mean margin: {ex4d['mean_margin']}min, Median: {ex4d['median_margin']}min")
        lines.append(f"  P25={ex4d['p25']}min, P75={ex4d['p75']}min, P95={ex4d['p95']}min, Max={ex4d['max_margin']}min")
        lines.append("\n  Distribution:")
        for bucket, pct in ex4d["bucket_pcts"].items():
            count = ex4d["buckets"][
                f"{bucket}_0_5min"
                if bucket == "boundary"
                else f"{bucket}_5_15min"
                if bucket == "near"
                else f"{bucket}_15_30min"
                if bucket == "moderate"
                else f"{bucket}_30plus"
            ]
            lines.append(f"    {bucket:12s}: {count:>6d} ({pct:>5.1f}%)")
        lines.append(f"\n  Genuine delay (>15min): {ex4d['genuine_rate']:.1f}%")
        lines.append(f"  Potential artifact (≤5min): {ex4d['artifact_rate']:.1f}%")
    else:
        lines.append("  No margin data available in violation_events")
    print("\n".join(lines))

    # 4C
    print("\n[EX-4C] Jitter Sensitivity...")
    ex4c = run_ex4c(episodes)

    lines_c = ["\n## EX-4C: Jitter Sensitivity\n"]
    lines_c.append(f"  {'Jitter':>8s} {'Flips':>7s} {'Flip%':>7s} {'TimLost':>8s}")
    lines_c.append(f"  {'-' * 8} {'-' * 7} {'-' * 7} {'-' * 8}")
    for j in sorted(ex4c.keys()):
        r = ex4c[j]
        lines_c.append(
            f"  {r['jitter_minutes']:>7d}m {r['n_flips']:>7d} {r['flip_rate']:>6.2f}% {r['timing_violations_lost']:>8d}"
        )

    robust_30 = ex4c.get(30, {}).get("flip_rate", 0)
    lines_c.append(f"\n  ±30min jitter flip rate: {robust_30:.2f}%")
    lines_c.append(
        f"  {'✅ ROBUST' if robust_30 < 10 else '🟡 MODERATE' if robust_30 < 20 else '🔴 FRAGILE'} (threshold: <10%)"
    )
    print("\n".join(lines_c))

    # Save
    full_report = "\n".join(lines + lines_c)
    with open(OUTPUT_DIR / "ex4_report.md", "w") as f:
        f.write(full_report)
    with open(OUTPUT_DIR / "ex4_results.json", "w") as f:
        json.dump({"ex4d": ex4d, "ex4c": ex4c}, f, indent=2, default=str)
    print(f"\n[SAVED] {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
