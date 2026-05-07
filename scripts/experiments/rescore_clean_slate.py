#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""R6: Re-score 180 clean slate episodes with fixed pipeline.

Reads original episode JSONs, replays actions through the fixed
ViolationExtractor + HarmScorer, and saves comparison results.
"""

from collections import defaultdict
from datetime import datetime
import json
import logging
from pathlib import Path
import statistics

from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig
from cga_bench.assessor_core.violations import (
    HarmSeverityMapping,
    TimingSeverityThreshold,
    ViolationExtractor,
    ViolationExtractorConfig,
)
from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    EpisodeLog,
    HarmSeverity,
    PatientState,
    RecommendationClass,
    ViolationType,
    VitalSigns,
)
from cga_bench.eval_harness.scenario_loader import ScenarioLoader

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INPUT_DIR = Path("results/clean_slate_20260331_210910")
OUTPUT_DIR = Path("results/clean_slate_rescored")

SCENARIO_GRAPH_MAP = {
    "septic_shock_basic": "ssc_sepsis_hour1_bundle.yaml",
    "septic_shock_penicillin_allergy": "ssc_sepsis_hour1_bundle.yaml",
    "stemi_inferior_rv_trap": "aha_chest_pain_evaluation.yaml",
    "dka_moderate_basic": "ada_dka_management.yaml",
    "dka_hypokalemia_trap": "ada_dka_management.yaml",
    "stroke_tpa_eligible": "aha_stroke_2019.yaml",
    "contrast_aki_prevention_basic": "kdigo_contrast_aki.yaml",
    "aki_stage1_basic": "kdigo_aki_full.yaml",
    "af_new_onset_basic": "atrial_fibrillation.yaml",
    "gi_bleeding_upper_basic": "gi_bleeding.yaml",
    "htn_emergency_basic": "hypertensive_emergency.yaml",
    "pe_submassive_basic": "pulmonary_embolism.yaml",
    "copd_moderate_exacerbation": "copd_exacerbation.yaml",
    "adhf_warm_wet": "aha_heart_failure_2022.yaml",
    "hemorrhagic_stroke": "aha_stroke_2019.yaml",
}

GRAPHS_DIR = Path("cpg_model/graphs")


def build_ve_config() -> ViolationExtractorConfig:
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
    mapping = {
        "order_lab": ActionType.ORDER_LAB,
        "order_imaging": ActionType.ORDER_IMAGING,
        "give_medication": ActionType.GIVE_MEDICATION,
        "procedure": ActionType.PROCEDURE,
        "consult": ActionType.CONSULT,
        "reassess": ActionType.REASSESS,
        "disposition": ActionType.DISPOSITION,
    }
    return mapping.get(s, ActionType.PROCEDURE)


def rescore_episode(ep_data: dict, ve_config: ViolationExtractorConfig, hs_config: HarmScorerConfig) -> dict:
    """Re-score a single episode using the fixed pipeline."""
    scenario_id = ep_data["scenario_id"]
    graph_file = SCENARIO_GRAPH_MAP.get(scenario_id)
    if not graph_file:
        return {"error": f"No graph mapping for {scenario_id}"}

    graph_path = str(GRAPHS_DIR / graph_file)
    engine = CPGEngineFactory.load_from_file(graph_path)
    ve = ViolationExtractor(engine, ve_config)

    # Get expected/forbidden from episode data (need n_expected for HarmScorer)
    expected_actions = ep_data.get("expected_actions") or []
    forbidden_actions = ep_data.get("forbidden_actions") or []
    n_expected = len(expected_actions) if expected_actions else ep_data.get("n_expected_actions", 5)
    hs = HarmScorer(n_expected, hs_config)

    # Rebuild actions
    actions = []
    for a in ep_data["actions"]:
        actions.append(
            Action(
                type=_action_type_from_str(a.get("type", "procedure")),
                action_id=a["action_id"],
                args={},
                timestamp_minutes=a.get("timestamp", 0.0),
            )
        )

    # Build minimal patient state
    state = PatientState(
        state_id="rescore_s0",
        time_since_arrival_minutes=0.0,
        age=65,
        sex="M",
        weight_kg=70,
        vitals=VitalSigns(
            heart_rate=100,
            blood_pressure_systolic=90,
            blood_pressure_diastolic=60,
            respiratory_rate=20,
            temperature=37.0,
            oxygen_saturation=95,
            map_mmhg=70,
        ),
        chief_complaint="clinical scenario",
        working_diagnosis=scenario_id,
    )

    # Build episode log
    states = [state] * max(len(actions), 1)
    episode = EpisodeLog(
        episode_id=f"rescore_{scenario_id}",
        scenario_id=scenario_id,
        agent_id=ep_data.get("agent_id", "unknown"),
        actions=actions,
        states=states,
        observations=[],
        total_duration_minutes=60.0,
        total_llm_calls=ep_data.get("llm_calls", 0),
        total_tokens=ep_data.get("total_tokens", 0),
        total_tool_calls=0,
        termination_reason="max_time",
    )

    # Extract violations with fixed pipeline
    violations = ve.extract_violations(
        episode,
        scenario_expected_actions=expected_actions if expected_actions else None,
    )

    # Score
    score = hs.compute_score(violations, episode)

    return {
        "scenario_id": scenario_id,
        "agent_id": ep_data.get("agent_id", "unknown"),
        "model_name": ep_data.get("model_name", "unknown"),
        "run_index": ep_data.get("run_index", 0),
        "actions_count": len(actions),
        "n_expected_actions": n_expected,
        # Old scores
        "old_compliance_score": ep_data["compliance_score"],
        "old_sub_scores": ep_data.get("sub_scores", {}),
        "old_total_violations": ep_data.get("total_violations", 0),
        "old_violations_by_type": ep_data.get("violations_by_type", {}),
        # New scores
        "new_compliance_score": score.compliance_score,
        "new_sub_scores": score.sub_scores,
        "new_total_violations": score.total_violations,
        "new_violations_by_type": score.violations_by_type,
        "new_peak_risk": score.peak_risk,
        "new_aggregate_risk": score.aggregate_risk,
        "new_violation_events": [
            e.model_dump() if hasattr(e, "model_dump") else str(e) for e in score.violation_events
        ],
        # Delta
        "cga_delta": score.compliance_score - ep_data["compliance_score"],
        "c2_old": ep_data.get("sub_scores", {}).get("C2_mandatory_completion", None),
        "c2_new": score.sub_scores.get("C2_mandatory_completion", None),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ve_config = build_ve_config()
    hs_config = build_hs_config()

    loader = ScenarioLoader()
    all_results = []
    model_stats: dict[str, list[dict]] = defaultdict(list)
    failures = 0

    # Iterate over model directories
    for model_dir in sorted(INPUT_DIR.iterdir()):
        if not model_dir.is_dir():
            continue
        model_key = model_dir.name
        logger.info(f"Re-scoring {model_key}...")

        for ep_file in sorted(model_dir.glob("*.json")):
            if ep_file.name == "model_summary.json":
                continue

            ep_data = json.loads(ep_file.read_text())
            if "actions" not in ep_data:
                continue

            try:
                result = rescore_episode(ep_data, ve_config, hs_config)
                result["source_file"] = str(ep_file.name)
                all_results.append(result)
                model_stats[model_key].append(result)

                # Save individual result
                out_path = OUTPUT_DIR / model_key / ep_file.name
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, "w") as f:
                    json.dump(result, f, indent=2, default=str)

            except Exception as e:
                logger.error(f"Failed to re-score {ep_file.name}: {e}")
                failures += 1

    # ---------------------------------------------------------------------------
    # Sanity checks
    # ---------------------------------------------------------------------------
    logger.info(f"\n{'=' * 60}")
    logger.info(f"RE-SCORING COMPLETE: {len(all_results)} episodes, {failures} failures")
    logger.info(f"{'=' * 60}")

    # C2 distribution check
    c2_old_vals = [r["c2_old"] for r in all_results if r.get("c2_old") is not None]
    c2_new_vals = [r["c2_new"] for r in all_results if r.get("c2_new") is not None]

    if c2_old_vals:
        c2_old_1 = sum(1 for v in c2_old_vals if v >= 0.99)
        c2_new_1 = sum(1 for v in c2_new_vals if v >= 0.99)
        logger.info("\nC2 distribution:")
        logger.info(f"  Old C2=1.0 count: {c2_old_1}/{len(c2_old_vals)}")
        logger.info(f"  New C2=1.0 count: {c2_new_1}/{len(c2_new_vals)}")
        logger.info(f"  Old C2 mean: {statistics.mean(c2_old_vals):.4f}")
        logger.info(f"  New C2 mean: {statistics.mean(c2_new_vals):.4f}")

    # CGA=1.0 count
    cga_old_1 = sum(1 for r in all_results if r["old_compliance_score"] >= 0.99)
    cga_new_1 = sum(1 for r in all_results if r["new_compliance_score"] >= 0.99)
    logger.info("\nCGA=1.0 episodes:")
    logger.info(f"  Old: {cga_old_1}")
    logger.info(f"  New: {cga_new_1}")

    # Per-model summary
    logger.info("\nPer-model CGA comparison:")
    summary_data = {}
    for model_key, results in sorted(model_stats.items()):
        old_scores = [r["old_compliance_score"] for r in results]
        new_scores = [r["new_compliance_score"] for r in results]
        old_mean = statistics.mean(old_scores)
        new_mean = statistics.mean(new_scores)
        logger.info(
            f"  {model_key:12s}: old_CGA={old_mean:.4f} -> new_CGA={new_mean:.4f} "
            f"(delta={new_mean - old_mean:+.4f}, n={len(results)})"
        )
        summary_data[model_key] = {
            "n_episodes": len(results),
            "old_cga_mean": round(old_mean, 4),
            "new_cga_mean": round(new_mean, 4),
            "cga_delta": round(new_mean - old_mean, 4),
            "old_cga_std": round(statistics.stdev(old_scores), 4) if len(old_scores) > 1 else 0,
            "new_cga_std": round(statistics.stdev(new_scores), 4) if len(new_scores) > 1 else 0,
        }

    # DKA hypokalemia check
    dka_episodes = [r for r in all_results if r["scenario_id"] == "dka_hypokalemia_trap"]
    if dka_episodes:
        logger.info(f"\nDKA hypokalemia_trap check ({len(dka_episodes)} episodes):")
        for r in dka_episodes:
            vbt = r["new_violations_by_type"]
            logger.info(
                f"  {r['model_name']:15s} r{r['run_index']}: "
                f"CGA {r['old_compliance_score']:.3f}->{r['new_compliance_score']:.3f}, "
                f"C2 {r['c2_old']:.2f}->{r['c2_new']:.2f}, "
                f"OM={vbt.get('OMISSION', 0)} CO={vbt.get('COMMISSION', 0)}"
            )

    # Save summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_episodes": len(all_results),
        "failures": failures,
        "models": summary_data,
        "c2_old_mean": round(statistics.mean(c2_old_vals), 4) if c2_old_vals else None,
        "c2_new_mean": round(statistics.mean(c2_new_vals), 4) if c2_new_vals else None,
        "cga_perfect_old": cga_old_1,
        "cga_perfect_new": cga_new_1,
    }
    with open(OUTPUT_DIR / "rescore_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"\nResults saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
