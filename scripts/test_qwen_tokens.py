"""Test Qwen3 response: thinking length vs JSON, truncation analysis."""

import json

from openai import OpenAI

client = OpenAI(base_url="http://localhost:8013/v1", api_key="sk-no-key-required")

for max_tok in [2048, 4096]:
    print(f"\n=== max_tokens={max_tok} ===")
    response = client.chat.completions.create(
        model="Qwen/Qwen3.5-35B-A3B-FP8",
        messages=[
            {"role": "system", "content": "Respond ONLY with valid JSON. No thinking."},
            {
                "role": "user",
                "content": 'Recommend 3 actions for septic shock. JSON: {"actions": [{"action_id": "...", "action_type": "...", "justification": "..."}]}',
            },
        ],
        temperature=0.1,
        max_tokens=max_tok,
    )

    content = response.choices[0].message.content
    finish = response.choices[0].finish_reason
    tokens = response.usage.completion_tokens

    print(f"  Completion tokens: {tokens}")
    print(f"  Finish reason: {finish}")
    print(f"  Content length: {len(content)} chars")
    print(f"  Starts with: {content[:40]!r}")

    # Find first {
    idx = content.find("{")
    if idx >= 0:
        thinking = content[:idx]
        json_part = content[idx:]
        print(f"  Thinking: {len(thinking)} chars ({len(thinking.split())} words)")
        print(f"  JSON part: {len(json_part)} chars")
        print(f"  Truncated: {finish == 'length'}")

        # Try parse last JSON block
        last_close = json_part.rfind("}")
        if last_close >= 0:
            candidate = json_part[: last_close + 1]
            try:
                parsed = json.loads(candidate)
                acts = parsed.get("actions", [])
                print(f"  Parse: SUCCESS, {len(acts)} actions")
                for a in acts[:3]:
                    print(f"    {a.get('action_id', '?')}")
            except json.JSONDecodeError:
                print("  Parse: FAILED")
        else:
            print("  No closing brace")
    else:
        print("  No JSON found!")

# Test with /no_think
print("\n=== /no_think in system prompt ===")
response = client.chat.completions.create(
    model="Qwen/Qwen3.5-35B-A3B-FP8",
    messages=[
        {"role": "system", "content": "/no_think\nRespond ONLY with valid JSON."},
        {
            "role": "user",
            "content": 'Recommend 3 actions for septic shock. JSON: {"actions": [{"action_id": "...", "action_type": "...", "justification": "..."}]}',
        },
    ],
    temperature=0.1,
    max_tokens=2048,
)
content = response.choices[0].message.content
print(f"  Starts with: {content[:60]!r}")
print(f"  Tokens: {response.usage.completion_tokens}")
print(f"  Has thinking: {'Thinking' in content[:50]}")
