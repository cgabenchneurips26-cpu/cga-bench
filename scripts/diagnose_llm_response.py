#!/usr/bin/env python3
"""Diagnose why qwen35b produces fewer actions than oss120b on aabb_t.

Patches VLLMProvider.complete to log raw LLM responses, then runs
one episode via the same code path as clean_slate_runner.
"""

import json
import logging
from pathlib import Path
import sys

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("diag")
logger.setLevel(logging.INFO)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

SCENARIO_ID = "aabb_t_basic_cardiac_liberal_threshold"

MODELS = {
    "oss120b": {
        "base_url": "http://localhost:28000/v1",
        "model": "openai/gpt-oss-120b",
        "port": 28000,
    },
    "qwen35b": {
        "base_url": "http://localhost:8013/v1",
        "model": "Qwen/Qwen3.5-35B-A3B-FP8",
        "port": 8013,
    },
    "qwen27b": {
        "base_url": "http://localhost:28010/v1",
        "model": "Qwen/Qwen3.5-27B-FP8",
        "port": 28010,
    },
    "qwen4b": {
        "base_url": "http://localhost:8101/v1",
        "model": "Qwen/Qwen3-4B-Instruct-2507",
        "port": 8101,
    },
}


def run_diagnosis(model_key: str) -> None:
    from cga_bench.agent_runner.llm_provider import VLLMProvider
    from cga_bench.agent_runner.rag_agent import RAGAgent, RAGConfig
    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    model_info = MODELS[model_key]
    print(f"\n{'=' * 70}")
    print(f"=== {model_key} ({model_info['model']}) on {SCENARIO_ID} ===")
    print(f"{'=' * 70}")

    # Patch VLLMProvider.complete to capture raw responses
    raw_responses: list[dict] = []
    original_complete = VLLMProvider.complete

    def logging_complete(self, messages):
        resp = original_complete(self, messages)
        content = resp.content or ""
        raw_responses.append(
            {
                "call_index": len(raw_responses),
                "content_len": len(content),
                "starts_with_brace": content.strip().startswith("{") if content else False,
                "content_first_500": content[:500],
                "content_last_200": content[-200:] if len(content) > 200 else content,
                "usage": resp.usage,
            }
        )
        logger.info(
            f"LLM call #{len(raw_responses)}: "
            f"len={len(content)}, starts_brace={content.strip()[:1] == '{'}, "
            f"tokens={resp.usage}"
        )
        return resp

    VLLMProvider.complete = logging_complete

    try:
        # Create agent (same pattern as clean_slate_runner)
        agent_config = RAGConfig(
            agent_id=f"diag_{model_key}",
            llm_backend="vllm",
            llm_model=model_info["model"],
            temperature=0.1,
            use_llm=True,
            base_url=model_info["base_url"],
            api_key="sk-no-key-required",
            max_actions_per_step=3,
            budget_limit_tokens=100000,
            budget_limit_tool_calls=50,
        )
        agent = RAGAgent(agent_config)

        # Load scenario
        loader = ScenarioLoader()
        scenario_def = loader.get_scenario(SCENARIO_ID)
        if scenario_def is None:
            avail = [s for s in loader.load_all_scenarios() if "aabb_t" in s][:5]
            print(f"ERROR: {SCENARIO_ID} not found. Available: {avail}")
            return

        # Create environment via ScenarioLoader (same as clean_slate_runner)
        env = loader.create_environment(SCENARIO_ID)

        # Run episode via agent.run_episode (same code path as runner)
        episode_log = agent.run_episode(env, SCENARIO_ID)
        all_actions = episode_log.actions

        print("\n--- SUMMARY ---")
        print(f"Total actions: {len(all_actions)}")
        print(f"Action IDs: {[a.action_id for a in all_actions]}")
        print(f"Total LLM calls: {len(raw_responses)}")

        # Analyze raw responses
        print("\n--- RAW LLM RESPONSES ---")
        for r in raw_responses:
            print(f"\nCall #{r['call_index']}:")
            print(f"  Length: {r['content_len']}, Starts '{{': {r['starts_with_brace']}")
            print(f"  Tokens: {r['usage']}")
            print(f"  First 300: {r['content_first_500'][:300]}")
            if r["content_len"] > 300:
                print(f"  Last 200: {r['content_last_200']}")

        # Save
        out = Path(f"evidence_pack/diag_{model_key}.json")
        with open(out, "w") as f:
            json.dump(
                {"actions": [a.action_id for a in all_actions], "raw_responses": raw_responses},
                f,
                indent=2,
                default=str,
            )
        print(f"\nSaved to {out}")

    finally:
        VLLMProvider.complete = original_complete


if __name__ == "__main__":
    models_to_test = sys.argv[1:] if len(sys.argv) > 1 else ["oss120b", "qwen35b"]
    for mk in models_to_test:
        if mk in MODELS:
            try:
                run_diagnosis(mk)
            except Exception as e:
                print(f"ERROR {mk}: {e}")
                import traceback

                traceback.print_exc()
