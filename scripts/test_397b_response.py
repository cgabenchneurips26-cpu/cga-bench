"""Test 397B response: thinking length, truncation, parse."""

import json
import sys

sys.path.insert(0, "${CGA_BENCH_ROOT}/cga_bench")

from openai import OpenAI

client = OpenAI(base_url="http://localhost:8013/v1", api_key="sk-no-key-required")

for max_tok in [2048, 4096]:
    print(f"\n=== 397B max_tokens={max_tok} ===")
    resp = client.chat.completions.create(
        model="Qwen/Qwen3.5-397B-A17B-FP8",
        messages=[
            {"role": "system", "content": "Respond ONLY with valid JSON."},
            {
                "role": "user",
                "content": 'Recommend 3 actions for septic shock. JSON: {"actions": [{"action_id": "x", "action_type": "y", "justification": "z"}]}',
            },
        ],
        temperature=0.1,
        max_tokens=max_tok,
    )

    content = resp.choices[0].message.content
    print(f"  Tokens: {resp.usage.completion_tokens}, finish: {resp.choices[0].finish_reason}")
    print(f"  Length: {len(content)} chars")
    print(f"  First 60: {content[:60]!r}")

    idx = content.find("{")
    if idx >= 0:
        print(f"  Thinking: {idx} chars, JSON+rest: {len(content) - idx} chars")

    from agent_runner.llm_provider import safe_json_parse

    try:
        result = safe_json_parse(content)
        print(f"  Parse: SUCCESS, actions={len(result.get('actions', []))}")
    except json.JSONDecodeError:
        print("  Parse: FAILED")
