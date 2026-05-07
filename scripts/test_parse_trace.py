"""Trace safe_json_parse behavior for Qwen3 responses."""

import json
import sys

sys.path.insert(0, "${CGA_BENCH_ROOT}")
sys.path.insert(0, "${CGA_BENCH_ROOT}/cga_bench")

from agent_runner.llm_provider import repair_json, safe_json_parse

# Test 1: Good response
test1 = 'Thinking Process:\n\n1. Analyze\n\n{"actions": [{"action_id": "1", "action_type": "lab", "justification": "test"}]}'
print("=== Test 1: Good ===")
r1 = safe_json_parse(test1)
print(f"  actions: {len(r1.get('actions', []))}")

# Test 2: Truncated
test2 = 'Thinking Process:\n\n1. Long thinking...\n\n{"actions": [{"action_id": "order_lab_lactate", "justific'
print("\n=== Test 2: Truncated ===")
try:
    r2 = safe_json_parse(test2)
    print(f"  result: {r2}")
except json.JSONDecodeError:
    print("  JSONDecodeError (expected)")

# Test 3: Inline JSON in thinking
test3 = 'Thinking Process:\n\n1. Need {"immediate": "care"}\n\n{"actions": [{"action_id": "x", "action_type": "y", "justification": "z"}]}'
print("\n=== Test 3: Inline JSON ===")
r3 = safe_json_parse(test3)
print(f"  keys: {list(r3.keys())}")
print(f"  got 'actions': {'actions' in r3}")
print(f"  got 'immediate': {'immediate' in r3}")

# Test 4: repair_json analysis
print("\n=== repair_json results ===")
for i, t in enumerate([test1, test2, test3], 1):
    rep = repair_json(t)
    print(f"  Test {i}: {rep[:80]!r}")
