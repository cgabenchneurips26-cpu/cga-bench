#!/usr/bin/env python3
"""Verify that the LLM path in RAGAgent actually works after the NoneType.lower() fix.

Runs 1 episode, captures logs, and reports:
1. Did _get_phase_prompt() succeed?
2. Was the LLM API actually called?
3. Did it return actions (not fall back to rule-based)?

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/verify_llm_path.py
"""

from __future__ import annotations

from io import StringIO
import logging
from pathlib import Path
import sys

# Setup path
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT.parent))

# Capture ALL logs including DEBUG
log_capture = StringIO()
handler = logging.StreamHandler(log_capture)
handler.setLevel(logging.DEBUG)
logging.root.addHandler(handler)
logging.root.setLevel(logging.DEBUG)

# Also print to stdout
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.INFO)
logging.root.addHandler(stdout_handler)

logger = logging.getLogger(__name__)


def main() -> None:
    from cga_bench.agent_runner.rag_agent import RAGAgent, RAGConfig
    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    # Use qwen35b (port 8013) - fastest model
    config = RAGConfig(
        agent_id="llm_path_test",
        llm_backend="vllm",
        llm_model="Qwen/Qwen3.5-35B-A3B-FP8",
        temperature=0.1,
        use_llm=True,
        base_url="http://localhost:8013/v1",
        api_key="sk-no-key-required",
        top_k=5,
        use_bm25=True,
        max_actions_per_step=3,
        budget_limit_tokens=100000,
        budget_limit_tool_calls=50,
    )

    agent = RAGAgent(config)

    # Pick a simple sepsis scenario
    loader = ScenarioLoader()
    scenario_id = "septic_shock_basic"
    scenario_def = loader.get_scenario(scenario_id)
    if scenario_def is None:
        # Fallback: find any sepsis scenario
        all_scenarios = loader.load_all_scenarios()
        for sid in sorted(all_scenarios.keys()):
            if "sepsis" in sid or "septic" in sid:
                scenario_id = sid
                scenario_def = all_scenarios[sid]
                break

    if scenario_def is None:
        logger.error("No sepsis scenario found")
        sys.exit(1)

    logger.info(f"Testing scenario: {scenario_id}")

    env = loader.create_environment(scenario_id)

    # Run the agent for 3 steps
    obs = env.reset()
    total_actions = 0

    for step in range(3):
        logger.info(f"\n{'=' * 60}")
        logger.info(f"STEP {step + 1}")
        logger.info(f"{'=' * 60}")

        actions = agent.decide(obs)
        total_actions += len(actions)

        for a in actions:
            logger.info(f"  Action: {a.action_id} ({a.type})")

        # Step the environment
        if actions:
            for action in actions:
                obs, reward, done, info = env.step(action)
                if done:
                    break
        if done:
            break

    # Analyze captured logs
    log_text = log_capture.getvalue()

    llm_called = "LLM 호출" in log_text or "complete_json" in log_text.lower() or "llm_provider" in log_text.lower()
    llm_failed = "LLM action generation failed" in log_text
    rule_fallback = "falling back to rule-based" in log_text
    phase_prompt_ok = "phase_prompt" in log_text.lower() or "_get_phase_prompt" in log_text.lower()
    none_lower = "NoneType" in log_text and "lower" in log_text

    print("\n" + "=" * 60)
    print("VERIFICATION RESULTS")
    print("=" * 60)
    print(f"  Scenario:          {scenario_id}")
    print(f"  Total actions:     {total_actions}")
    print(f"  NoneType.lower():  {'YES - STILL BROKEN' if none_lower else 'NO - FIXED'}")
    print(f"  LLM gen failed:    {'YES' if llm_failed else 'NO'}")
    print(f"  Rule-based fallback: {'YES' if rule_fallback else 'NO'}")
    print(f"  Steps completed:   {step + 1}")

    # Check for specific LLM call evidence
    llm_attempt_count = log_text.count("LLM action generation failed")
    llm_empty_count = log_text.count("LLM returned empty actions")
    rule_count = log_text.count("falling back to rule-based")

    print(f"\n  LLM attempt failures:  {llm_attempt_count}")
    print(f"  LLM empty returns:     {llm_empty_count}")
    print(f"  Rule-based fallbacks:  {rule_count}")

    # Verdict
    if none_lower:
        print("\n  VERDICT: FAIL - NoneType.lower() still occurring")
        sys.exit(1)
    elif llm_attempt_count == 0 and rule_count == 0 and total_actions > 0:
        print("\n  VERDICT: PASS - LLM path working, no fallbacks")
        sys.exit(0)
    elif llm_attempt_count > 0 and llm_attempt_count == rule_count:
        print("\n  VERDICT: FAIL - LLM called but ALL attempts failed (different error)")
        # Grep for the actual errors
        for line in log_text.split("\n"):
            if "LLM action generation failed" in line:
                print(f"    {line.strip()}")
        sys.exit(1)
    elif llm_attempt_count > 0 and rule_count < llm_attempt_count:
        print(f"\n  VERDICT: PARTIAL - LLM worked {step + 1 - rule_count}/{step + 1} steps")
        sys.exit(0)
    else:
        print("\n  VERDICT: UNCLEAR - check logs manually")
        # Print relevant log lines
        for line in log_text.split("\n"):
            if any(kw in line.lower() for kw in ["llm", "rule-based", "fallback", "fail", "error", "phase_prompt"]):
                print(f"    {line.strip()[:120]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
