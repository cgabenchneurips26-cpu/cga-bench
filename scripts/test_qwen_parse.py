"""Debug: why JSON parse fails even when response is complete."""

import json
import re

from openai import OpenAI

client = OpenAI(base_url="http://localhost:8013/v1", api_key="sk-no-key-required")

response = client.chat.completions.create(
    model="Qwen/Qwen3.5-35B-A3B-FP8",
    messages=[
        {"role": "system", "content": "Respond ONLY with valid JSON."},
        {
            "role": "user",
            "content": 'Recommend 3 actions for septic shock. JSON: {"actions": [{"action_id": "x", "action_type": "y", "justification": "z"}]}',
        },
    ],
    temperature=0.1,
    max_tokens=4096,
)

content = response.choices[0].message.content
print(f"Length: {len(content)}, finish: {response.choices[0].finish_reason}")
print(f"First 100: {content[:100]!r}")
print(f"Last 100: {content[-100:]!r}")

# Find ALL { positions
braces = [(i, content[i]) for i in range(len(content)) if content[i] in "{}"]
print(f"\nBrace positions (first 10): {braces[:10]}")
print(f"Brace positions (last 10): {braces[-10:]}")

# Try extract_last_json_block approach
last_close = content.rfind("}")
if last_close >= 0:
    depth = 0
    start = -1
    for i in range(last_close, -1, -1):
        if content[i] == "}":
            depth += 1
        elif content[i] == "{":
            depth -= 1
        if depth == 0:
            start = i
            break
    if start >= 0:
        candidate = content[start : last_close + 1]
        print(f"\nLast JSON block: pos {start}-{last_close} ({len(candidate)} chars)")
        print(f"First 200: {candidate[:200]!r}")
        try:
            parsed = json.loads(candidate)
            print(f"PARSE SUCCESS: {list(parsed.keys())}")
            if "actions" in parsed:
                print(f"Actions: {len(parsed['actions'])}")
        except json.JSONDecodeError as e:
            print(f"PARSE FAIL: {e}")
            # Try with markdown code block removal
            clean = re.sub(r"```json\s*", "", candidate)
            clean = re.sub(r"```\s*$", "", clean)
            try:
                parsed = json.loads(clean)
                print(f"After cleanup PARSE SUCCESS: {list(parsed.keys())}")
            except json.JSONDecodeError as e2:
                print(f"After cleanup still FAIL: {e2}")
                print(f"Problem area: {candidate[max(0, e.colno - 50) : e.colno + 50]!r}")
