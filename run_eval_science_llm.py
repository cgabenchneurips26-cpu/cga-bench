#!/usr/bin/env python3
"""
Run real LLM experiments for Evaluation Science.

Executes 8 scenarios × 4 conditions (baseline + 3 prompt patches)
using the actual CGA-Bench pipeline with Qwen3.5-35B on vLLM.

Usage:
    # From parent directory (AnonProject/):
    cd ${CGA_BENCH_ROOT}
    PYTHONPATH=. python cga_bench/run_eval_science_llm.py

    # Run single condition:
    PYTHONPATH=. python cga_bench/run_eval_science_llm.py --condition baseline
    PYTHONPATH=. python cga_bench/run_eval_science_llm.py --condition patch_T
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Setup paths
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eval_science_llm")

# Prompt patches from Experiment D
PROMPT_PATCHES: Dict[str, str] = {
    "baseline": "",
    "patch_T": (
        "\n\nCRITICAL TIMING REQUIREMENT:\n"
        "All mandatory actions must be completed within the guideline-specified "
        "time window. For sepsis, this means completing the Hour-1 Bundle "
        "(blood cultures, antibiotics, lactate, fluid resuscitation) within "
        "60 minutes of presentation. For DKA, IV fluids must start within "
        "15 minutes. For STEMI, cath lab activation within 10 minutes of "
        "ECG diagnosis. Delays in time-critical interventions are associated "
        "with increased mortality. Prioritize mandatory actions by deadline urgency."
    ),
    "patch_S": (
        "\n\nCRITICAL SEQUENCE REQUIREMENT:\n"
        "Actions must be performed in the correct clinical order. "
        "Always obtain blood cultures BEFORE administering antibiotics. "
        "In DKA, always check and correct potassium BEFORE starting insulin. "
        "In stroke, always obtain CT head BEFORE administering tPA. "
        "In chest pain, always obtain 12-lead ECG BEFORE giving aspirin. "
        "Violating these sequences can cause direct patient harm or mask "
        "important diagnostic information."
    ),
    "patch_O": (
        "\n\nACTION SCOPE REQUIREMENT:\n"
        "Only perform actions that are explicitly recommended in the "
        "clinical guideline for this specific condition. Do not order "
        "additional tests or treatments that are not part of the "
        "standard protocol, even if they seem clinically reasonable. "
        "Off-protocol actions waste resources, delay critical "
        "interventions, and may cause unnecessary harm. Stick strictly "
        "to the guideline-recommended action set."
    ),
}

SCENARIOS = [
    "septic_shock_basic",
    "septic_shock_penicillin_allergy",
    "stemi_inferior_rv_trap",
    "dka_moderate_basic",
    "dka_hypokalemia_trap",
    "stroke_tpa_eligible",
    "contrast_aki_prevention_basic",
    "aki_stage1_basic",
]

AGENT_NAME = "rag_qwen35"  # default, overridable via --agent


def run_episode_with_patch(
    scenario_id: str,
    condition: str,
    patch_text: str,
    output_dir: Path,
    seed: int = 42,
    agent_name: str = AGENT_NAME,
) -> Optional[Dict]:
    """Run a single episode with an optional system prompt patch."""
    from cga_bench.eval_harness.scenario_loader import ScenarioLoader, AgentConfigLoader
    from cga_bench.agent_runner import RAGAgent, RAGConfig, LLMBackend
    from cga_bench.cpg_engine.engine import CPGEngineFactory
    from cga_bench.cpg_model.schemas.base import EpisodeLog, HarmSeverity, ViolationType, RecommendationClass

    # Import scoring — use the same defaults as run_benchmark.py
    from cga_bench.assessor_core.violations import (
        ViolationExtractor, ViolationExtractorConfig,
        HarmSeverityMapping, TimingSeverityThreshold,
    )
    from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig

    # Monkey-patch the system prompt if needed
    if patch_text:
        import cga_bench.agent_runner.llm_provider as llm_mod
        original_prompt = llm_mod.CLINICAL_SYSTEM_PROMPT
        llm_mod.CLINICAL_SYSTEM_PROMPT = original_prompt + patch_text
        logger.info(f"Patched system prompt (+{len(patch_text)} chars)")

    try:
        # Load scenario
        scenario_loader = ScenarioLoader()
        agent_loader = AgentConfigLoader()

        scenario = scenario_loader.get_scenario(scenario_id)
        if not scenario:
            logger.error(f"Scenario not found: {scenario_id}")
            return None

        # Load agent config
        agent_config = agent_loader.load_agent_config(agent_name)
        agent_settings = agent_config.get("agent", {})

        # Create agent
        rag_config = RAGConfig(
            agent_id=f"{agent_name}_{condition}",
            llm_backend=LLMBackend(agent_settings.get("llm_backend", "vllm")),
            llm_model=agent_settings.get("llm_model", "Qwen/Qwen3.5-35B-A3B-FP8"),
            temperature=agent_settings.get("temperature", 0.1),
            use_llm=True,
            base_url=agent_settings.get("base_url", "http://localhost:8013/v1"),
            api_key=agent_settings.get("api_key", "sk-no-key-required"),
            top_k=agent_settings.get("top_k", 5),
            use_bm25=True,
            max_actions_per_step=agent_settings.get("max_actions_per_step", 3),
            budget_limit_tokens=100000,
            budget_limit_tool_calls=50,
            llm_seed=seed,
        )
        agent = RAGAgent(rag_config)

        # Create environment
        environment = scenario_loader.create_environment(scenario_id)
        cpg_graph_path = scenario_loader.get_cpg_graph_path(scenario_id)

        # Run episode
        agent.reset()
        states = [scenario.patient]
        actions = []
        obs = environment.reset()
        done = False
        step = 0
        consecutive_empty = 0

        while not done and step < 100:
            step += 1
            agent_actions = agent.decide(obs)

            if agent_actions:
                consecutive_empty = 0
                for action in agent_actions:
                    obs, reward, done, info = environment.step(action)
                    actions.append(action)
                    if done:
                        break
            else:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break

            if not done:
                states.append(environment.current_state)

        # Build episode log
        termination = "success" if done else ("no_more_actions" if consecutive_empty >= 3 else "timeout")
        observations = [{"vitals": s.vitals.model_dump() if s.vitals else {}} for s in states]

        episode_log = EpisodeLog(
            episode_id=f"{scenario_id}_{condition}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            scenario_id=scenario_id,
            agent_id=f"{agent_name}_{condition}",
            states=states,
            actions=actions,
            observations=observations,
            total_duration_minutes=environment.current_time,
            total_llm_calls=agent.metrics.total_llm_calls,
            total_tokens=agent.metrics.total_tokens,
            total_tool_calls=agent.metrics.total_tool_calls,
            termination_reason=termination,
        )

        # Score with real pipeline
        score_data = {"scenario_id": scenario_id, "condition": condition, "agent_id": f"{agent_name}_{condition}"}

        if cpg_graph_path and cpg_graph_path.exists():
            engine = CPGEngineFactory.load_from_file(str(cpg_graph_path))

            # Same configs as run_benchmark.py get_default_*()
            ve_config = ViolationExtractorConfig(
                harm_severity_mappings=[
                    HarmSeverityMapping(action_pattern="antibiotic", severity=HarmSeverity.MAJOR),
                    HarmSeverityMapping(action_pattern="lactate", severity=HarmSeverity.MODERATE),
                    HarmSeverityMapping(action_pattern="blood_culture", severity=HarmSeverity.MODERATE),
                    HarmSeverityMapping(action_pattern="vasopressor", severity=HarmSeverity.MAJOR),
                    HarmSeverityMapping(action_pattern="crystalloid", severity=HarmSeverity.MODERATE),
                    HarmSeverityMapping(action_pattern="ecg", severity=HarmSeverity.MAJOR),
                    HarmSeverityMapping(action_pattern="troponin", severity=HarmSeverity.MODERATE),
                    HarmSeverityMapping(action_pattern="cath_lab", severity=HarmSeverity.SEVERE),
                    HarmSeverityMapping(action_pattern="nitro", severity=HarmSeverity.SEVERE),
                    HarmSeverityMapping(action_pattern="aspirin", severity=HarmSeverity.MODERATE),
                    HarmSeverityMapping(action_pattern="", severity=HarmSeverity.MINOR),
                ],
                timing_severity_thresholds=[
                    TimingSeverityThreshold(max_delay_minutes=15, severity=HarmSeverity.MINOR),
                    TimingSeverityThreshold(max_delay_minutes=30, severity=HarmSeverity.MODERATE),
                    TimingSeverityThreshold(max_delay_minutes=60, severity=HarmSeverity.MAJOR),
                    TimingSeverityThreshold(max_delay_minutes=120, severity=HarmSeverity.SEVERE),
                ],
                default_deviation_severity=HarmSeverity.MINOR,
                default_deviation_preventability=0.8,
            )
            extractor = ViolationExtractor(engine, ve_config)
            violations = extractor.extract_violations(episode_log)

            hs_config = HarmScorerConfig(
                severity_weights={
                    HarmSeverity.CATASTROPHIC: 1.0, HarmSeverity.SEVERE: 0.85,
                    HarmSeverity.MAJOR: 0.7, HarmSeverity.MODERATE: 0.4,
                    HarmSeverity.MINOR: 0.1,
                },
                guideline_strength_weights={
                    RecommendationClass.CLASS_I: 1.0, RecommendationClass.CLASS_IIA: 0.8,
                    RecommendationClass.CLASS_IIB: 0.5, RecommendationClass.CLASS_III: 0.3,
                    None: 0.5,
                },
                violation_type_weights={
                    ViolationType.OMISSION: 1.0, ViolationType.COMMISSION: 1.2,
                    ViolationType.TIMING: 0.8, ViolationType.SEQUENCE: 0.9,
                    ViolationType.DEVIATION: 0.5,
                },
            )
            scorer = HarmScorer(
                total_mandatory_count=max(len(scenario.expected_actions), 1),
                config=hs_config,
            )
            score = scorer.compute_score(violations, episode_log)

            score_data.update({
                "compliance_score": score.compliance_score,
                "peak_risk": score.peak_risk,
                "aggregate_risk": score.aggregate_risk,
                "total_violations": score.total_violations,
                "sub_scores": score.sub_scores,
                "violations_by_type": score.violations_by_type,
                "llm_calls": episode_log.total_llm_calls,
                "total_tokens": episode_log.total_tokens,
                "actions_count": len(actions),
                "actions": [
                    {"action_id": a.action_id, "timestamp": a.timestamp_minutes, "type": a.type}
                    for a in actions
                ],
            })

            logger.info(
                f"  [{condition}] {scenario_id}: CGA={score.compliance_score:.1%} "
                f"actions={len(actions)} tokens={episode_log.total_tokens}"
            )
        else:
            logger.warning(f"No CPG graph for {scenario_id}")
            score_data["error"] = "no_cpg_graph"

        # Save result
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = output_dir / f"{scenario_id}_{agent_name}_{condition}_{ts}.json"
        with open(result_file, "w") as f:
            json.dump(score_data, f, indent=2, ensure_ascii=False, default=str)

        return score_data

    finally:
        # Restore original prompt
        if patch_text:
            import cga_bench.agent_runner.llm_provider as llm_mod
            llm_mod.CLINICAL_SYSTEM_PROMPT = original_prompt  # noqa: F821


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real LLM eval science experiments")
    parser.add_argument("--condition", type=str, default="all",
                        help="Condition: baseline, patch_T, patch_S, patch_O, or all")
    parser.add_argument("--scenario", type=str, default=None,
                        help="Single scenario to run (default: all 8)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--agent", type=str, default=AGENT_NAME,
                        help="Agent config name (default: rag_qwen35)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (default: results/eval_science_{agent})")
    args = parser.parse_args()

    agent_name = args.agent
    conditions = list(PROMPT_PATCHES.keys()) if args.condition == "all" else [args.condition]
    scenarios = [args.scenario] if args.scenario else SCENARIOS
    output_base = Path(args.output_dir) if args.output_dir else (SCRIPT_DIR / "results" / f"eval_science_{agent_name}")

    total = len(conditions) * len(scenarios)
    logger.info(f"Running {total} episodes: {len(conditions)} conditions × {len(scenarios)} scenarios")
    logger.info(f"Agent: {agent_name}")
    logger.info(f"Output: {output_base}")

    all_results: List[Dict] = []

    for condition in conditions:
        patch = PROMPT_PATCHES[condition]
        cond_dir = output_base / condition
        logger.info(f"\n{'='*60}")
        logger.info(f"Condition: {condition}" + (f" (+{len(patch)} chars patch)" if patch else ""))
        logger.info(f"{'='*60}")

        for scenario_id in scenarios:
            try:
                result = run_episode_with_patch(
                    scenario_id=scenario_id,
                    condition=condition,
                    patch_text=patch,
                    output_dir=cond_dir,
                    seed=args.seed,
                    agent_name=agent_name,
                )
                if result:
                    all_results.append(result)
            except Exception as exc:
                logger.error(f"FAILED {scenario_id}/{condition}: {exc}")
                all_results.append({
                    "scenario_id": scenario_id,
                    "condition": condition,
                    "error": str(exc),
                })

    # Save combined summary
    summary_path = output_base / "eval_science_summary.json"
    with open(summary_path, "w") as f:
        json.dump({
            "experiment": "eval_science_real_llm",
            "agent": agent_name,
            "timestamp": datetime.now().isoformat(),
            "total_episodes": len(all_results),
            "conditions": conditions,
            "scenarios": scenarios,
            "results": all_results,
        }, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"\nSummary saved: {summary_path}")
    logger.info(f"Total episodes: {len(all_results)}")

    # Print summary table
    print(f"\n{'='*80}")
    print(f"{'Scenario':<40} {'baseline':>8} {'patch_T':>8} {'patch_S':>8} {'patch_O':>8}")
    print(f"{'='*80}")
    for scenario_id in scenarios:
        row = f"{scenario_id:<40}"
        for cond in ["baseline", "patch_T", "patch_S", "patch_O"]:
            r = next((r for r in all_results if r.get("scenario_id") == scenario_id and r.get("condition") == cond), None)
            if r and "compliance_score" in r:
                row += f" {r['compliance_score']:>7.1%}"
            elif r and "error" in r:
                row += f" {'ERR':>7}"
            else:
                row += f" {'—':>7}"
        print(row)


if __name__ == "__main__":
    main()
