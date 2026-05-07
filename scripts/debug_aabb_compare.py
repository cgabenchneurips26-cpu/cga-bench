"""Debug: compare oss120b vs qwen35b on same aabb_t scenario.
Traces every LLM call with raw response, parsed actions, rejection reasons.
"""

import logging
import sys
import time

sys.path.insert(0, "${CGA_BENCH_ROOT}")
sys.path.insert(0, "${CGA_BENCH_ROOT}/cga_bench")

logging.basicConfig(level=logging.WARNING)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("openai").setLevel(logging.ERROR)

import yaml

from cga_bench.agent_runner.llm_provider import (
    LLMMessage,
    safe_json_parse,
)
from cga_bench.agent_runner.rag_agent import RAGAgent, RAGConfig
from cga_bench.eval_harness.scenario_loader import ScenarioLoader

# Monkey-patch to capture raw LLM responses
_call_log = []

original_complete_json = None


def patch_provider(provider):
    """Wrap complete_json to log raw responses."""
    global original_complete_json
    original_complete_json = provider.complete_json.__func__ if hasattr(provider.complete_json, "__func__") else None

    original = provider.complete_json

    def logged_complete_json(messages, schema):
        # Call original complete (not complete_json) to get raw response
        import json as _json

        json_instruction = LLMMessage(
            role="system",
            content=f"Respond ONLY with valid JSON matching this schema. No markdown, no explanation, no thinking.\n\nSCHEMA:\n{_json.dumps(schema, indent=2)}\n\nOutput ONLY the JSON object.",
        )
        all_messages = [json_instruction] + messages
        response = provider.complete(all_messages)
        raw = response.content.strip()

        # Parse
        try:
            result = safe_json_parse(raw)
        except:
            result = {}

        _call_log.append(
            {
                "raw_len": len(raw),
                "raw_start": raw[:100],
                "raw_end": raw[-100:] if len(raw) > 100 else raw,
                "has_thinking": raw.startswith("Thinking") or "<think>" in raw[:50],
                "parsed_actions": len(result.get("actions", [])),
                "action_ids": [a.get("action_id", "?") for a in result.get("actions", [])],
            }
        )

        return result

    provider.complete_json = logged_complete_json


loader = ScenarioLoader()
SID = "aabb_t_basic_cardiac_liberal_threshold"

for model_key in ["oss120b", "qwen35b"]:
    _call_log.clear()

    config_path = f"configs/agents/clean_slate_{model_key}.yaml"
    agent_yaml = yaml.safe_load(open(config_path))["agent"]
    agent_config = RAGConfig(
        agent_id=f"debug_{model_key}",
        llm_backend=agent_yaml["llm_backend"],
        llm_model=agent_yaml["llm_model"],
        temperature=agent_yaml.get("temperature", 0.1),
        use_llm=True,
        base_url=agent_yaml["base_url"],
        api_key=agent_yaml.get("api_key", "sk-no-key-required"),
        top_k=5,
        use_bm25=True,
        max_actions_per_step=3,
        budget_limit_tokens=100000,
        budget_limit_tool_calls=50,
    )

    agent = RAGAgent(agent_config)
    patch_provider(agent.llm_provider)

    env = loader.create_environment(SID)
    t0 = time.time()
    episode_log = agent.run_episode(env, SID)
    elapsed = time.time() - t0

    print(f"\n{'=' * 70}")
    print(f"MODEL: {model_key} | {SID}")
    print(f"{'=' * 70}")
    print(f"Total actions: {len(episode_log.actions)} | Time: {elapsed:.0f}s")
    print(f"LLM calls: {len(_call_log)}")
    print()

    for i, call in enumerate(_call_log[:8]):
        thinking = "THINKING" if call["has_thinking"] else "NO-THINK"
        print(f"  Call {i}: raw={call['raw_len']}chars [{thinking}] parsed={call['parsed_actions']} actions")
        if call["action_ids"]:
            print(f"    IDs: {call['action_ids'][:4]}")
        else:
            print(f"    Start: {call['raw_start'][:80]}")
    if len(_call_log) > 8:
        empty = sum(1 for c in _call_log if c["parsed_actions"] == 0)
        print(f"  ... {len(_call_log) - 8} more calls ({empty} empty)")

    print("\n  Final actions:")
    for a in episode_log.actions[:10]:
        print(f"    {a.action_id} (t={a.timestamp_minutes:.0f}m)")
