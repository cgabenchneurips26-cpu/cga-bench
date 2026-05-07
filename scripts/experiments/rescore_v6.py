"""Re-score Phase A + B episodes with the v6 normalizer (post-hoc).

Following the rescore_clean_slate.py template. Re-runs ViolationExtractor
+ HarmScorer over each existing episode JSON, using the *current*
action_normalizer alias table (which now has the v6 deepseek-r1 mitigation
mappings). Writes back into the same JSON, preserving the original
fields under ``_v1_*`` keys for transparency.

WHY: Phase A + early Phase B episodes were scored with an older normalizer
that didn't recognise oxygen / consultation / reassessment aliases. Some
DEVIATION classifications were string-level mistakes — the LLM emitted a
synonym but the scorer counted it as out-of-protocol. After the v6
normalizer patch (commit cc02ed76), we re-score everything for
consistency.

Usage:
    PYTHONPATH=. python scripts/experiments/rescore_v6.py \\
        --in results/full_v6a_706 results/full_v6b \\
        [--dry-run] [--limit 100]

Per-episode wall-clock: ~50ms (loading + scoring; no agent reruns).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig  # noqa: E402
from cga_bench.assessor_core.violations import (  # noqa: E402
    HarmSeverityMapping,
    TimingSeverityThreshold,
    ViolationExtractor,
    ViolationExtractorConfig,
)
from cga_bench.cpg_engine.engine import CPGEngineFactory  # noqa: E402
from cga_bench.cpg_model.schemas.base import (  # noqa: E402
    Action,
    ActionType,
    EpisodeLog,
    HarmSeverity,
    RecommendationClass,
    ViolationType,
)
from cga_bench.eval_harness.scenario_loader import ScenarioLoader  # noqa: E402

os.environ.setdefault("CGA_BENCH_EXCLUDE_AUTO", "1")
os.environ.setdefault("CGA_BENCH_INCLUDE_AUTO_V2", "1")

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def build_ve_config() -> ViolationExtractorConfig:
    """Match runner.py production config."""
    return ViolationExtractorConfig(
        harm_severity_mappings=[
            HarmSeverityMapping(action_pattern="", severity=HarmSeverity.MODERATE),
        ],
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


def _action_type_from_str(s: str) -> ActionType:
    """Map string action_type into ActionType enum (best-effort)."""
    try:
        return ActionType(s)
    except (ValueError, KeyError):
        return ActionType.PROCEDURE


def rescore_episode(
    ep_data: dict,
    ve_config: ViolationExtractorConfig,
    hs_config: HarmScorerConfig,
    loader: ScenarioLoader,
) -> dict | None:
    """Re-score one episode dict; returns updated dict or None on error."""
    scenario_id = ep_data["scenario_id"]
    scenario = loader.get_scenario(scenario_id)
    if scenario is None:
        return None
    graph_path = str(loader.get_cpg_graph_path(scenario_id))
    if not graph_path:
        return None

    engine = CPGEngineFactory.load_from_file(graph_path)
    ve = ViolationExtractor(engine, ve_config)

    expected_actions = ep_data.get("expected_actions") or scenario.expected_actions or []
    forbidden_actions = ep_data.get("forbidden_actions") or scenario.forbidden_actions or []
    n_expected = len(expected_actions) if expected_actions else ep_data.get("n_expected_actions", 5)
    hs = HarmScorer(n_expected, hs_config)

    actions = []
    for a in ep_data.get("actions") or []:
        actions.append(
            Action(
                type=_action_type_from_str(a.get("type", "procedure")),
                action_id=a["action_id"],
                args=a.get("args") or {},
                timestamp_minutes=a.get("timestamp_minutes", a.get("timestamp", 0.0)),
            )
        )

    # PROPER STATE REPLAY: build the actual environment + step through actions
    # so state_history evolves (lab results arrive, vitals change, CPG node
    # transitions). Without this, all actions are evaluated against the entry
    # node only → systematic worsening of compliance scores.
    env = loader.create_environment(scenario_id)
    env._cpg_engine = engine  # ensure same engine instance for consistency
    env.reset()
    for a in actions:
        try:
            env.step(a)
        except Exception:
            break  # truncated step is OK — episode just ends earlier here
        if getattr(env, "terminated", False):
            break

    states = list(env.state_history) if env.state_history else [env.current_state]
    # Pad to len(actions) if state evolution stopped early
    while len(states) < max(len(actions), 1):
        states.append(states[-1])

    episode = EpisodeLog(
        episode_id=f"rescore_{scenario_id}_{ep_data.get('run_index', 0)}",
        scenario_id=scenario_id,
        agent_id=ep_data.get("agent_id", "unknown"),
        actions=actions,
        states=states,
        observations=[],
        total_duration_minutes=ep_data.get("total_duration_minutes", 60.0),
        total_llm_calls=ep_data.get("total_llm_calls", 0),
        total_tokens=ep_data.get("total_tokens", 0),
        total_tool_calls=0,
        termination_reason=ep_data.get("termination_reason", "max_time"),
    )

    violations = ve.extract_violations(
        episode,
        scenario_expected_actions=expected_actions if expected_actions else None,
    )
    score = hs.compute_score(violations, episode)

    # Preserve original v1 scores
    v1_keys = [
        "compliance_score",
        "peak_risk",
        "aggregate_risk",
        "total_violations",
        "violations_by_type",
        "violation_events",
        "sub_scores",
    ]
    v1 = {f"_v1_{k}": ep_data.get(k) for k in v1_keys}

    out = dict(ep_data)
    out.update(v1)
    out["compliance_score"] = score.compliance_score
    out["peak_risk"] = score.peak_risk
    out["aggregate_risk"] = score.aggregate_risk
    out["total_violations"] = score.total_violations
    out["violations_by_type"] = score.violations_by_type
    out["sub_scores"] = score.sub_scores
    out["violation_events"] = [e.model_dump() if hasattr(e, "model_dump") else str(e) for e in score.violation_events]
    out["_rescore_marker"] = "v6_normalizer_patch_cc02ed76"
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="dirs", nargs="+", required=True, help="Result directories to walk")
    p.add_argument("--dry-run", action="store_true", help="Compute deltas, don't overwrite")
    p.add_argument("--limit", type=int, default=0, help="Process at most N eps (0 = all)")
    args = p.parse_args()

    ve_config = build_ve_config()
    hs_config = build_hs_config()
    loader = ScenarioLoader()

    total = ok = unchanged = improved = worsened = err = 0
    delta_sum = 0.0
    t0 = time.time()

    for d in args.dirs:
        D = Path(d)
        for model_dir in sorted(D.iterdir()):
            if not model_dir.is_dir() or model_dir.name.startswith("_"):
                continue
            for f in sorted(model_dir.glob("*.json")):
                if f.name.startswith(("checkpoint", "model_summary", ".claim")):
                    continue
                if args.limit and total >= args.limit:
                    break
                total += 1
                try:
                    ep = json.load(open(f))
                except Exception:
                    err += 1
                    continue
                if ep.get("_rescore_marker") == "v6_normalizer_patch_cc02ed76":
                    continue  # already rescored
                old_comp = ep.get("compliance_score", 0)
                try:
                    new_ep = rescore_episode(ep, ve_config, hs_config, loader)
                except Exception as exc:
                    err += 1
                    if err <= 3:
                        logger.warning(f"  err {f.name}: {exc}")
                    continue
                if new_ep is None:
                    err += 1
                    continue
                new_comp = new_ep["compliance_score"]
                delta = new_comp - old_comp
                delta_sum += delta
                if abs(delta) < 0.001:
                    unchanged += 1
                elif delta > 0:
                    improved += 1
                else:
                    worsened += 1
                ok += 1
                if not args.dry_run:
                    f.write_text(json.dumps(new_ep, indent=2, default=str))
            if args.limit and total >= args.limit:
                break

    dt = time.time() - t0
    print("\n=== RESCORE SUMMARY ===")
    print(f"  Processed: {ok}/{total}  errors: {err}  ({dt:.1f}s, {dt / max(ok, 1) * 1000:.0f}ms/ep)")
    print(f"  Unchanged: {unchanged}  Improved: {improved}  Worsened: {worsened}")
    print(f"  Mean Δ compliance: {delta_sum / max(ok, 1):+.4f}")
    print(f"  Mode: {'DRY-RUN (no writes)' if args.dry_run else 'WROTE BACK'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
