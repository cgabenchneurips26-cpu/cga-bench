#!/usr/bin/env python3
"""Run P2-1 frontier model experiments (GPT-4o, Claude 3.5 Sonnet).

Executes 15-scenario x 3-run episodes for frontier models using the
existing eval_harness runner infrastructure and RAG agent pipeline.

Produces per-episode JSON results in:
    results/eval_science_rag_{model}/baseline/

Usage:
    PYTHONPATH=. python scripts/experiments/run_frontier_models.py --model gpt4o --dry-run
    PYTHONPATH=. python scripts/experiments/run_frontier_models.py --model claude35 --runs 3
    PYTHONPATH=. python scripts/experiments/run_frontier_models.py --model gpt4o --scenarios septic_shock_basic,dka_moderate_basic
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import sys
import time

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]  # cga_bench/
CONFIGS_DIR = BASE_DIR / "configs"
RESULTS_DIR = BASE_DIR / "results"
BUDGET_PATH = BASE_DIR / "evidence_pack" / "analysis" / "budget_estimate_frontier.json"

ALL_15_SCENARIOS: list[str] = [
    "septic_shock_basic",
    "septic_shock_penicillin_allergy",
    "stemi_inferior_rv_trap",
    "dka_moderate_basic",
    "dka_hypokalemia_trap",
    "stroke_tpa_eligible",
    "contrast_aki_prevention_basic",
    "aki_stage1_basic",
    "af_new_onset_basic",
    "gi_bleeding_upper_basic",
    "htn_emergency_basic",
    "pe_submassive_basic",
    "copd_moderate_exacerbation",
    "adhf_warm_wet",
    "hemorrhagic_stroke",
]

MODEL_CONFIGS: dict[str, dict[str, str]] = {
    "gpt4o": {
        "config_file": "configs/agents/rag_gpt4o.yaml",
        "agent_id": "rag_gpt4o",
        "result_dir": "eval_science_rag_gpt4o",
        "display_name": "GPT-4o",
        "input_price_per_m": "2.50",
        "output_price_per_m": "10.00",
    },
    "claude35": {
        "config_file": "configs/agents/rag_claude35.yaml",
        "agent_id": "rag_claude35",
        "result_dir": "eval_science_rag_claude35",
        "display_name": "Claude 3.5 Sonnet",
        "input_price_per_m": "3.00",
        "output_price_per_m": "15.00",
    },
}

# Token estimates from existing oss-120b runs (22 episodes)
AVG_TOKENS_PER_EPISODE = 41104
INPUT_TOKEN_RATIO = 0.85
OUTPUT_TOKEN_RATIO = 0.15


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="Run P2-1 frontier model experiments for CGA-Bench",
    )
    parser.add_argument(
        "--model",
        required=True,
        choices=list(MODEL_CONFIGS.keys()),
        help="Frontier model to evaluate",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Budget calculation only, no API calls",
    )
    parser.add_argument(
        "--scenarios",
        type=str,
        default=None,
        help="Comma-separated scenario IDs (default: all 15)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of runs per scenario (default: 3)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Override output directory",
    )
    return parser.parse_args()


def load_agent_config(config_path: Path) -> dict:
    """Load agent configuration from YAML.

    Args:
        config_path: Path to agent YAML config.

    Returns:
        Parsed agent config dict.
    """
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def compute_budget_estimate(
    scenarios: list[str],
    runs: int,
    model_key: str,
) -> dict:
    """Compute cost estimate for the experiment.

    Args:
        scenarios: List of scenario IDs.
        runs: Number of runs per scenario.
        model_key: Model identifier key.

    Returns:
        Budget estimation dict.
    """
    mc = MODEL_CONFIGS[model_key]
    total_episodes = len(scenarios) * runs

    input_price = float(mc["input_price_per_m"])
    output_price = float(mc["output_price_per_m"])

    avg_input = AVG_TOKENS_PER_EPISODE * INPUT_TOKEN_RATIO
    avg_output = AVG_TOKENS_PER_EPISODE * OUTPUT_TOKEN_RATIO

    input_cost = (avg_input * total_episodes / 1_000_000) * input_price
    output_cost = (avg_output * total_episodes / 1_000_000) * output_price
    total_cost = input_cost + output_cost

    return {
        "model": mc["display_name"],
        "num_scenarios": len(scenarios),
        "runs_per_scenario": runs,
        "total_episodes": total_episodes,
        "avg_tokens_per_episode": AVG_TOKENS_PER_EPISODE,
        "estimated_input_tokens": int(avg_input * total_episodes),
        "estimated_output_tokens": int(avg_output * total_episodes),
        "input_cost_usd": round(input_cost, 2),
        "output_cost_usd": round(output_cost, 2),
        "total_cost_usd": round(total_cost, 2),
        "with_buffer_usd": round(total_cost * 1.2, 2),
    }


def run_dry_mode(
    scenarios: list[str],
    runs: int,
    model_key: str,
) -> None:
    """Print budget estimate without making API calls.

    Args:
        scenarios: List of scenario IDs.
        runs: Number of runs per scenario.
        model_key: Model identifier key.
    """
    mc = MODEL_CONFIGS[model_key]
    budget = compute_budget_estimate(scenarios, runs, model_key)

    print("=" * 70)
    print("  P2-1 Frontier Model Experiment — DRY RUN")
    print(f"  Model: {mc['display_name']}")
    print("=" * 70)
    print(f"  Scenarios:       {budget['num_scenarios']}")
    print(f"  Runs/scenario:   {budget['runs_per_scenario']}")
    print(f"  Total episodes:  {budget['total_episodes']}")
    print(f"  Avg tokens/ep:   {budget['avg_tokens_per_episode']:,}")
    print("-" * 70)
    print(f"  Est. input tokens:  {budget['estimated_input_tokens']:,}")
    print(f"  Est. output tokens: {budget['estimated_output_tokens']:,}")
    print(f"  Input cost:         ${budget['input_cost_usd']:.2f}")
    print(f"  Output cost:        ${budget['output_cost_usd']:.2f}")
    print(f"  Total cost:         ${budget['total_cost_usd']:.2f}")
    print(f"  With 20% buffer:    ${budget['with_buffer_usd']:.2f}")
    print("=" * 70)
    print("\nScenarios:")
    for i, sid in enumerate(scenarios, 1):
        print(f"  {i:2d}. {sid}")

    # Write budget estimate to file
    budget["generated_at"] = datetime.now().isoformat()
    budget["scenarios"] = scenarios
    BUDGET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(BUDGET_PATH, "w", encoding="utf-8") as f:
        json.dump(budget, f, indent=2)
    print(f"\nBudget estimate saved: {BUDGET_PATH}")


def run_experiment(
    scenarios: list[str],
    runs: int,
    model_key: str,
    seed: int,
    output_dir: str | None,
) -> None:
    """Execute the frontier model experiment.

    Args:
        scenarios: List of scenario IDs.
        runs: Number of runs per scenario.
        model_key: Model identifier key.
        seed: Random seed.
        output_dir: Override output directory, or None for default.
    """
    # Late imports to avoid import overhead for --dry-run
    from cga_bench.eval_harness.runner import EvaluationRunner, ExperimentConfig
    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    mc = MODEL_CONFIGS[model_key]
    agent_config = load_agent_config(BASE_DIR / mc["config_file"])

    result_dir_name = output_dir or mc["result_dir"]
    result_path = RESULTS_DIR / result_dir_name / "baseline"
    result_path.mkdir(parents=True, exist_ok=True)

    # Set up experiment config
    exp_config = ExperimentConfig(
        experiment_id=f"eval_science_{mc['agent_id']}",
        scenarios=scenarios,
        agents=[mc["agent_id"]],
        num_runs_per_scenario=runs,
        output_dir=str(RESULTS_DIR / result_dir_name),
        save_logs=True,
        save_scores=True,
        budget_limit_tokens=100_000,
        budget_limit_tool_calls=50,
        enforce_budget_matching=True,
        random_seed=seed,
    )

    runner = EvaluationRunner(exp_config)
    loader = ScenarioLoader()

    total_episodes = len(scenarios) * runs
    completed = 0
    failed: list[str] = []
    results_summary: list[dict] = []

    print(f"\nStarting {mc['display_name']} experiment")
    print(f"Episodes: {total_episodes} ({len(scenarios)} scenarios x {runs} runs)")
    print(f"Output: {result_path}\n")

    for sid in scenarios:
        for run_idx in range(runs):
            episode_tag = f"{sid} run={run_idx}"
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = result_path / f"{sid}_{mc['agent_id']}_baseline_{timestamp_str}.json"

            try:
                logger.info("Starting %s", episode_tag)
                print(f"  [{completed + 1}/{total_episodes}] {episode_tag} ...", end=" ", flush=True)

                t0 = time.monotonic()

                # Load scenario
                scenario_config = loader.load_scenario(sid)
                if scenario_config is None:
                    raise ValueError(f"Scenario '{sid}' not found")

                # Create patient and environment
                patient = runner.create_patient_from_config(scenario_config["patient"])
                env = runner.create_environment(patient, scenario_config)

                # Create agent
                from cga_bench.agent_runner.rag_agent import RAGAgent, RAGAgentConfig

                rag_config = RAGAgentConfig(
                    agent_id=mc["agent_id"],
                    llm_backend=agent_config["agent"]["llm_backend"],
                    llm_model=agent_config["agent"]["llm_model"],
                    temperature=agent_config["agent"].get("temperature", 0.1),
                    top_k=agent_config["agent"].get("top_k", 5),
                    use_bm25=agent_config["agent"].get("use_bm25", True),
                    max_actions_per_step=agent_config["agent"].get("max_actions_per_step", 3),
                    budget_limit_tokens=agent_config["agent"].get("budget_limit_tokens", 100_000),
                )
                agent = RAGAgent(rag_config)

                # Run episode
                obs = env.reset()
                episode_actions = []
                total_tokens = 0
                llm_calls = 0

                while not env.done:
                    action = agent.decide(obs)
                    if action is None:
                        break
                    obs, reward, done, info = env.step(action)
                    episode_actions.append({
                        "action_id": action.action_id,
                        "timestamp": action.timestamp_minutes,
                        "type": action.type.value if hasattr(action.type, "value") else str(action.type),
                    })
                    if hasattr(agent, "_llm_provider") and agent._llm_provider:
                        usage = agent._llm_provider.last_usage
                        total_tokens += usage.get("total_tokens", 0)
                        llm_calls += 1

                # Score episode
                episode_log = env.get_episode_log()
                cpg_outputs = runner._get_cpg_outputs(scenario_config, patient)
                violations = runner._extract_violations(episode_log, cpg_outputs, scenario_config)
                score = runner._compute_score(violations, scenario_config)

                elapsed = time.monotonic() - t0

                result = {
                    "scenario_id": sid,
                    "condition": "baseline",
                    "agent_id": f"{mc['agent_id']}_baseline",
                    "compliance_score": score.compliance_score,
                    "peak_risk": score.peak_risk,
                    "aggregate_risk": score.aggregate_risk,
                    "total_violations": score.total_violations,
                    "sub_scores": score.sub_scores,
                    "violations_by_type": score.violations_by_type,
                    "llm_calls": llm_calls,
                    "total_tokens": total_tokens,
                    "actions_count": len(episode_actions),
                    "actions": episode_actions,
                    "run_index": run_idx,
                    "elapsed_seconds": round(elapsed, 1),
                }

                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2)

                results_summary.append(result)
                completed += 1
                print(f"CGA={score.compliance_score:.3f} tokens={total_tokens} ({elapsed:.1f}s)")

            except Exception as exc:
                failed.append(episode_tag)
                logger.exception("Failed: %s", episode_tag)
                print(f"FAILED: {exc}")

    # Write summary
    summary = {
        "experiment": f"eval_science_{mc['agent_id']}",
        "agent": mc["agent_id"],
        "model": mc["display_name"],
        "timestamp": datetime.now().isoformat(),
        "total_episodes": total_episodes,
        "completed": completed,
        "failed": len(failed),
        "failed_episodes": failed,
        "scenarios": scenarios,
        "results": results_summary,
    }
    summary_path = RESULTS_DIR / result_dir_name / "eval_science_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nCompleted: {completed}/{total_episodes}")
    if failed:
        print(f"Failed: {len(failed)}")
        for ep in failed:
            print(f"  - {ep}")
    print(f"Summary: {summary_path}")


def main() -> None:
    """Entry point for the frontier model experiment runner."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    args = parse_args()

    # Resolve scenarios
    if args.scenarios:
        scenarios = [s.strip() for s in args.scenarios.split(",")]
        unknown = [s for s in scenarios if s not in ALL_15_SCENARIOS]
        if unknown:
            print(f"ERROR: Unknown scenarios: {unknown}")
            print(f"Available: {ALL_15_SCENARIOS}")
            sys.exit(1)
    else:
        scenarios = list(ALL_15_SCENARIOS)

    if args.dry_run:
        run_dry_mode(scenarios, args.runs, args.model)
    else:
        # Verify API key availability
        mc = MODEL_CONFIGS[args.model]
        if args.model == "gpt4o" and not os.environ.get("OPENAI_API_KEY"):
            print("ERROR: OPENAI_API_KEY not set")
            sys.exit(1)
        if args.model == "claude35" and not os.environ.get("ANTHROPIC_API_KEY"):
            print("ERROR: ANTHROPIC_API_KEY not set")
            sys.exit(1)

        run_experiment(scenarios, args.runs, args.model, args.seed, args.output_dir)


if __name__ == "__main__":
    main()
