#!/usr/bin/env python3
"""S1 Sonnet 706-episode rescore drift analysis.

Test A: HarmScorer-only — reuses preserved violation_events from S1
episode JSON. Directly tests commit 3817bed6 (CDE-rescoring) drift on
the score computation pipeline.

Output: reports/path_d_day3/s1_rescore_drift.json + console summary.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
import time

REPO = Path("/home/anonymous-org/anonymous-project/AnonProject")
sys.path.insert(0, str(REPO))

from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig
from cga_bench.cpg_model.schemas.base import (
    Action,
    EpisodeLog,
    HarmSeverity,
    RecommendationClass,
    ViolationEvent,
    ViolationType,
)


def build_harm_scorer_config() -> HarmScorerConfig:
    """Same builder as frontier_spot_check.py:_build_harm_scorer_config."""
    return HarmScorerConfig(
        severity_weights={
            HarmSeverity.MINOR: 0.1,
            HarmSeverity.MODERATE: 0.3,
            HarmSeverity.MAJOR: 0.6,
            HarmSeverity.SEVERE: 0.85,
            HarmSeverity.CATASTROPHIC: 1.0,
        },
        guideline_strength_weights={
            RecommendationClass.CLASS_I: 1.0,
            RecommendationClass.CLASS_IIA: 0.75,
            RecommendationClass.CLASS_IIB: 0.5,
            RecommendationClass.CLASS_III: 0.25,
            None: 0.5,
        },
        violation_type_weights={
            ViolationType.OMISSION: 0.8,
            ViolationType.COMMISSION: 1.0,
            ViolationType.TIMING: 0.7,
            ViolationType.SEQUENCE: 0.6,
            ViolationType.DEVIATION: 0.4,
        },
    )


def reconstruct_episode_log(ep: dict) -> EpisodeLog:
    """Rebuild EpisodeLog from preserved JSON dict.

    HarmScorer.compute_score does not consume states; pass empty list to
    skip PatientState reconstruction (which has many required fields not
    preserved in episode JSON).
    """
    actions = [Action.model_validate(a) for a in ep["actions"]]
    return EpisodeLog(
        episode_id=f"rescore_{ep['scenario_id']}_r{ep.get('run_idx', 0)}",
        scenario_id=ep["scenario_id"],
        agent_id="rag_claude_sonnet46_rescore",
        states=[],
        actions=actions,
        observations=[],
        total_duration_minutes=float(ep.get("total_duration_minutes") or 0.0),
        total_llm_calls=int(ep.get("total_llm_calls") or 0),
        total_tokens=int(ep.get("total_tokens") or 0),
        total_tool_calls=int(ep.get("total_tool_calls") or 0),
        termination_reason=ep.get("termination_reason") or "completed",
    )


def main() -> int:
    s1_path = REPO / "cga_bench/evidence_pack/frontier/s1_sonnet.json"
    out_path = REPO / "cga_bench/reports/path_d_day3/s1_rescore_drift.json"

    print(f"Loading S1: {s1_path}")
    with open(s1_path) as f:
        s1 = json.load(f)
    episodes = s1["episodes"]
    print(f"  episodes: {len(episodes)}")

    config = build_harm_scorer_config()

    deltas: list[dict] = []
    failures: list[dict] = []
    t_start = time.monotonic()
    first_err = None

    for i, ep in enumerate(episodes):
        try:
            episode_log = reconstruct_episode_log(ep)
            violations = [ViolationEvent.model_validate(v) for v in ep.get("violation_events", [])]
            expected_actions = ep.get("expected_actions") or []
            total_mandatory = len(expected_actions) if expected_actions else 5

            scorer = HarmScorer(total_mandatory_count=total_mandatory, config=config)
            new_score = scorer.compute_score(violations, episode_log)

            orig = float(ep["compliance_score"])
            new = float(new_score.compliance_score)
            delta = new - orig

            deltas.append(
                {
                    "scenario_id": ep["scenario_id"],
                    "run_idx": ep.get("run_idx", 0),
                    "orig_compliance": orig,
                    "new_compliance": new,
                    "delta": delta,
                    "orig_subs": ep["sub_scores"],
                    "new_subs": dict(new_score.sub_scores),
                    "n_violations": len(violations),
                }
            )
        except Exception as e:
            if first_err is None:
                import traceback as tb

                first_err = f"{type(e).__name__}: {e}\n{tb.format_exc(limit=4)}"
            failures.append(
                {
                    "scenario_id": ep["scenario_id"],
                    "run_idx": ep.get("run_idx", 0),
                    "error": f"{type(e).__name__}: {str(e)[:200]}",
                }
            )
        if (i + 1) % 100 == 0:
            elapsed = time.monotonic() - t_start
            print(f"  [{i + 1}/{len(episodes)}] elapsed={elapsed:.1f}s ok={len(deltas)} failed={len(failures)}")

    elapsed = time.monotonic() - t_start
    print(f"\nDone in {elapsed:.1f}s — {len(deltas)} rescored, {len(failures)} failed")
    if first_err and not deltas:
        print(f"\nFIRST ERROR:\n{first_err}")

    if not deltas:
        print("No successful rescores — abort.")
        return 1

    abs_deltas = [abs(d["delta"]) for d in deltas]
    raw_deltas = [d["delta"] for d in deltas]
    n = len(deltas)
    mean_abs = sum(abs_deltas) / n
    max_abs = max(abs_deltas)
    n_changed = sum(1 for d in raw_deltas if abs(d) > 1e-6)
    n_changed_001 = sum(1 for d in raw_deltas if abs(d) > 0.01)
    n_changed_005 = sum(1 for d in raw_deltas if abs(d) > 0.05)
    mean_delta = sum(raw_deltas) / n
    n_higher = sum(1 for d in raw_deltas if d > 1e-6)
    n_lower = sum(1 for d in raw_deltas if d < -1e-6)
    n_equal = n - n_higher - n_lower

    summary = {
        "test": "S1 706-episode HarmScorer-only rescore drift (Test A)",
        "purpose": "Detect 3817bed6 (CDE-rescoring) drift in compliance_score",
        "n_episodes": n,
        "n_failures": len(failures),
        "elapsed_seconds": round(elapsed, 2),
        "drift_stats": {
            "mean_abs_delta": round(mean_abs, 6),
            "max_abs_delta": round(max_abs, 6),
            "mean_delta": round(mean_delta, 6),
            "n_changed_any": n_changed,
            "n_changed_gt_0.01": n_changed_001,
            "n_changed_gt_0.05": n_changed_005,
            "n_higher": n_higher,
            "n_lower": n_lower,
            "n_equal": n_equal,
        },
        "interpretation": ("DRIFT DETECTED" if n_changed_001 > 0 else "NO DRIFT (HarmScorer math unchanged)"),
        "top_10_largest_deltas": sorted(deltas, key=lambda d: abs(d["delta"]), reverse=True)[:10],
        "first_5_records": deltas[:5],
        "failure_categories": Counter(f["error"].split(":")[0] for f in failures).most_common(5),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nReport: {out_path}")

    print("\n=== DRIFT SUMMARY (HarmScorer-only) ===")
    print(f"  mean |Δ|: {mean_abs:.6f}")
    print(f"  max  |Δ|: {max_abs:.6f}")
    print(f"  mean  Δ: {mean_delta:+.6f}")
    print(f"  changed (any):     {n_changed:4d} / {n} ({100 * n_changed / n:.1f}%)")
    print(f"  changed >0.01:     {n_changed_001:4d} / {n} ({100 * n_changed_001 / n:.1f}%)")
    print(f"  changed >0.05:     {n_changed_005:4d} / {n} ({100 * n_changed_005 / n:.1f}%)")
    print(f"  direction: higher={n_higher}, lower={n_lower}, unchanged={n_equal}")
    print(f"  verdict: {summary['interpretation']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
