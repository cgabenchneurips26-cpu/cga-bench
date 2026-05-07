"""Debug: trace exactly why Qwen produces fewer actions than oss120b.

Runs 1 episode of septic_shock_basic with qwen35b, logging every
LLM response, parsed JSON, action rejection reason.
"""

import logging
import sys

sys.path.insert(0, "${CGA_BENCH_ROOT}")
sys.path.insert(0, "${CGA_BENCH_ROOT}/cga_bench")

# Enable DEBUG logging for rag_agent
logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
# But suppress noisy HTTP logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

from cga_bench.agent_runner.rag_agent import RAGAgent, RAGConfig
from cga_bench.eval_harness.scenario_loader import ScenarioLoader

# Monkey-patch _generate_actions_with_llm to log details
original_generate = RAGAgent._generate_actions_with_llm


def debug_generate(self, observation, retrieved_docs, state, current_time, completed_action_ids):
    """Wrapped version that logs LLM response details."""
    available_actions = observation.available_actions

    # Call original
    if self.llm_provider is None:
        raise RuntimeError("LLM provider not initialized")

    # Build same prompt as original
    context_parts = ["## Retrieved Clinical Guidelines\n"]
    for i, doc in enumerate(retrieved_docs, 1):
        context_parts.append(f"### [{i}] {doc.source} (Score: {doc.score:.2f})")
        if doc.strength:
            context_parts.append(f"**Strength**: {doc.strength}")
        context_parts.append(doc.content[:500])
        context_parts.append("")
    context = "\n".join(context_parts)

    patient_summary = self._format_patient_state(state)
    completed_str = ", ".join(completed_action_ids) if completed_action_ids else "None"
    available_actions_str = self._format_available_actions(
        available_actions, completed_action_ids, getattr(observation, "mandatory_actions", [])
    )
    phase_prompt = self._get_phase_prompt(state, available_actions, current_time)

    # Count prompt tokens roughly
    full_prompt = f"{patient_summary}\n{completed_str}\n{phase_prompt}\n{available_actions_str}\n{context}"
    prompt_chars = len(full_prompt)
    prompt_words = len(full_prompt.split())

    from cga_bench.agent_runner.llm_provider import ACTION_RECOMMENDATION_SCHEMA, CLINICAL_SYSTEM_PROMPT, LLMMessage

    messages = [
        LLMMessage(role="system", content=CLINICAL_SYSTEM_PROMPT),
        LLMMessage(role="user", content=full_prompt[:8000]),  # truncate for safety
    ]

    result = self.llm_provider.complete_json(messages, ACTION_RECOMMENDATION_SCHEMA)

    # Log raw result
    actions_data = result.get("actions", []) if isinstance(result, dict) else result if isinstance(result, list) else []

    print(f"\n  [DEBUG] Step t={current_time:.0f}m")
    print(f"    Prompt: {prompt_chars} chars, {prompt_words} words")
    print(f"    Completed: {len(completed_action_ids)} actions")
    print(f"    Available: {len(available_actions)} actions")
    print(f"    LLM returned: {len(actions_data)} raw actions")

    # Check each action
    accepted = []
    for ad in actions_data:
        aid = str(ad.get("action_id", ""))
        normalized = self._normalize_action_id(aid, available_actions)
        in_completed = aid in completed_action_ids or (normalized and normalized in completed_action_ids)
        in_available = bool(normalized) or not available_actions

        reason = ""
        if in_completed:
            reason = "SKIP:completed"
        elif not in_available:
            reason = f"REJECT:not_in_available (raw='{aid}')"
        else:
            reason = "ACCEPT"
            accepted.append(normalized or aid)

        print(f"    action '{aid}' → normalized='{normalized}' → {reason}")

    print(f"    Final accepted: {len(accepted)}")

    # Return via original method
    return original_generate(self, observation, retrieved_docs, state, current_time, completed_action_ids)


RAGAgent._generate_actions_with_llm = debug_generate

# Run 1 episode
loader = ScenarioLoader()
import yaml

config_path = "configs/agents/clean_slate_qwen35b.yaml"
agent_yaml = yaml.safe_load(open(config_path))["agent"]
agent_config = RAGConfig(
    agent_id="debug_qwen35b",
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
env = loader.create_environment("septic_shock_basic")

print("=== DEBUG: septic_shock_basic with qwen35b ===")
print(f"Available actions: {len(env.reset().available_actions)}")

episode_log = agent.run_episode(env, "septic_shock_basic")
print(f"\n=== RESULT: {len(episode_log.actions)} actions ===")
for a in episode_log.actions:
    print(f"  {a.action_id} (t={a.timestamp_minutes:.0f}m)")
