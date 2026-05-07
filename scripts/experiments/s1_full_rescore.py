#!/usr/bin/env python3
"""S1 Test C — full ViolationExtractor + HarmScorer re-extraction on 706 episodes.

Replays each S1 trace (preserved actions list) through the May-4
ViolationExtractor (with current ActionNormalizer) → new violations →
new HarmScorer.compute_score → new compliance_score. Compares against
S1 originals to quantify true end-to-end drift caused by code changes
between Apr 28 (S1 scoring) and May 4 (current HEAD).

Output: reports/path_d_day3/s1_full_rescore_drift.json
"""

from __future__ import annotations

from collections import Counter
import json
import logging
from pathlib import Path
import sys
import time
import warnings

logging.disable(logging.WARNING)
warnings.filterwarnings("ignore")

REPO = Path("/home/anonymous-org/anonymous-project/AnonProject")
sys.path.insert(0, str(REPO))

from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig
from cga_bench.assessor_core.violations import (
    HarmSeverityMapping,
    TimingSeverityThreshold,
    ViolationExtractor,
    ViolationExtractorConfig,
)
from cga_bench.cpg_engine.engine import CPGEngineConfig, CPGEngineFactory
from cga_bench.cpg_model.schemas.base import (
    Action,
    EpisodeLog,
    HarmSeverity,
    PatientState,
    RecommendationClass,
    ViolationType,
    VitalSigns,
)
from cga_bench.eval_harness.scenario_loader import ScenarioLoader


def build_ve_config() -> ViolationExtractorConfig:
    return ViolationExtractorConfig(
        harm_severity_mappings=[HarmSeverityMapping(action_pattern="", severity=HarmSeverity.MODERATE)],
        timing_severity_thresholds=[
            TimingSeverityThreshold(max_delay_minutes=15.0, severity=HarmSeverity.MINOR),
            TimingSeverityThreshold(max_delay_minutes=30.0, severity=HarmSeverity.MODERATE),
            TimingSeverityThreshold(max_delay_minutes=60.0, severity=HarmSeverity.MAJOR),
            TimingSeverityThreshold(max_delay_minutes=120.0, severity=HarmSeverity.SEVERE),
        ],
        default_deviation_severity=HarmSeverity.MODERATE,
        default_deviation_preventability=0.8,
    )


def build_hs_config() -> HarmScorerConfig:
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


def build_episode_log(ep: dict, stub_state: PatientState) -> EpisodeLog:
    actions = [Action.model_validate(a) for a in ep["actions"]]
    return EpisodeLog(
        episode_id=f"rescore_{ep['scenario_id']}",
        scenario_id=ep["scenario_id"],
        agent_id="rescore",
        states=[stub_state],
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
    out_path = REPO / "cga_bench/reports/path_d_day3/s1_full_rescore_drift.json"

    print(f"Loading S1: {s1_path}")
    with open(s1_path) as f:
        s1 = json.load(f)
    episodes = s1["episodes"]
    print(f"  {len(episodes)} episodes")

    loader = ScenarioLoader()
    ve_cfg = build_ve_config()
    hs_cfg = build_hs_config()

    # Cache CPGEngine + extractor per scenario_id (engine load is the bottleneck)
    engine_cache: dict[str, ViolationExtractor] = {}
    stub_state = PatientState(
        state_id="stub",
        age=60,
        sex="M",
        chief_complaint="unspecified",
        vitals=VitalSigns(timestamp_minutes=0.0),
    )

    deltas: list[dict] = []
    failures: list[dict] = []
    viol_count_changes: Counter[int] = Counter()
    viol_type_orig: Counter[str] = Counter()
    viol_type_new: Counter[str] = Counter()

    t0 = time.monotonic()
    for i, ep in enumerate(episodes):
        sid = ep["scenario_id"]
        try:
            if sid not in engine_cache:
                graph_path = str(loader.get_cpg_graph_path(sid))
                engine = CPGEngineFactory.load_from_file(graph_path, CPGEngineConfig())
                engine_cache[sid] = ViolationExtractor(engine=engine, config=ve_cfg)
            extractor = engine_cache[sid]
            el = build_episode_log(ep, stub_state)
            expected = ep.get("expected_actions") or None
            new_viols = extractor.extract_violations(el, scenario_expected_actions=expected)
            new_n = len(new_viols)
            orig_n = ep.get("total_violations", 0)
            viol_count_changes[new_n - orig_n] += 1
            for v in ep.get("violation_events", []):
                viol_type_orig[v["violation_type"]] += 1
            for v in new_viols:
                viol_type_new[v.violation_type.value] += 1
            total_mandatory = len(expected) if expected else 5
            scorer = HarmScorer(total_mandatory_count=total_mandatory, config=hs_cfg)
            new_score = scorer.compute_score(new_viols, el)
            orig = float(ep["compliance_score"])
            new = float(new_score.compliance_score)
            deltas.append(
                {
                    "scenario_id": sid,
                    "orig_compliance": orig,
                    "new_compliance": new,
                    "delta": new - orig,
                    "orig_n_violations": orig_n,
                    "new_n_violations": new_n,
                    "n_violations_diff": new_n - orig_n,
                    "orig_subs": ep.get("sub_scores", {}),
                    "new_subs": dict(new_score.sub_scores),
                }
            )
        except Exception as e:
            failures.append({"scenario_id": sid, "error": f"{type(e).__name__}: {str(e)[:200]}"})
        if (i + 1) % 100 == 0:
            elapsed = time.monotonic() - t0
            print(
                f"  [{i + 1}/{len(episodes)}] elapsed={elapsed:.1f}s ok={len(deltas)} failed={len(failures)} cache_size={len(engine_cache)}"
            )

    elapsed = time.monotonic() - t0
    print(f"\nDone in {elapsed:.1f}s — {len(deltas)} ok, {len(failures)} failed")
    if not deltas:
        print("All failed.")
        if failures:
            print("First 3:", failures[:3])
        return 1

    abs_d = [abs(d["delta"]) for d in deltas]
    raw_d = [d["delta"] for d in deltas]
    n = len(deltas)
    summary = {
        "test": "S1 706-episode full ViolationExtractor + HarmScorer rescore (Test C)",
        "purpose": "End-to-end drift between Apr 28 scoring and May 4 scoring (covers commits 3817bed6 + 2fbb3da0)",
        "n_episodes": n,
        "n_failures": len(failures),
        "n_unique_scenarios": len(engine_cache),
        "elapsed_seconds": round(elapsed, 2),
        "compliance_drift": {
            "mean_abs_delta": round(sum(abs_d) / n, 6),
            "max_abs_delta": round(max(abs_d), 6),
            "mean_delta": round(sum(raw_d) / n, 6),
            "n_changed_any": sum(1 for d in raw_d if abs(d) > 1e-6),
            "n_changed_gt_0.01": sum(1 for d in raw_d if abs(d) > 0.01),
            "n_changed_gt_0.05": sum(1 for d in raw_d if abs(d) > 0.05),
            "n_changed_gt_0.10": sum(1 for d in raw_d if abs(d) > 0.10),
            "n_higher": sum(1 for d in raw_d if d > 1e-6),
            "n_lower": sum(1 for d in raw_d if d < -1e-6),
            "n_equal": sum(1 for d in raw_d if abs(d) <= 1e-6),
        },
        "violation_count_drift": {
            "distribution": dict(sorted(viol_count_changes.items())),
            "viol_type_orig_total": dict(viol_type_orig),
            "viol_type_new_total": dict(viol_type_new),
        },
        "interpretation": (
            "DRIFT DETECTED"
            if sum(1 for d in raw_d if abs(d) > 0.01) > 0
            else "NO MEANINGFUL DRIFT (<0.01 across all 706)"
        ),
        "top_20_largest_deltas": sorted(deltas, key=lambda d: abs(d["delta"]), reverse=True)[:20],
        "first_5_records": deltas[:5],
        "failures_summary": Counter(f["error"].split(":")[0] for f in failures).most_common(5),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nReport: {out_path}")

    print("\n=== TEST C — FULL RESCORE DRIFT ===")
    cd = summary["compliance_drift"]
    print(f"  mean |Δ|: {cd['mean_abs_delta']:.6f}")
    print(f"  max  |Δ|: {cd['max_abs_delta']:.6f}")
    print(f"  mean  Δ: {cd['mean_delta']:+.6f}")
    print(f"  changed >0.01: {cd['n_changed_gt_0.01']:4d} / {n} ({100 * cd['n_changed_gt_0.01'] / n:.2f}%)")
    print(f"  changed >0.05: {cd['n_changed_gt_0.05']:4d} / {n} ({100 * cd['n_changed_gt_0.05'] / n:.2f}%)")
    print(f"  changed >0.10: {cd['n_changed_gt_0.10']:4d} / {n} ({100 * cd['n_changed_gt_0.10'] / n:.2f}%)")
    print(f"  higher={cd['n_higher']}, lower={cd['n_lower']}, unchanged={cd['n_equal']}")
    print(f"  verdict: {summary['interpretation']}")
    print(f"\n  violation count diff distribution: {summary['violation_count_drift']['distribution']}")
    print(f"  orig violation types: {summary['violation_count_drift']['viol_type_orig_total']}")
    print(f"  new  violation types: {summary['violation_count_drift']['viol_type_new_total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
