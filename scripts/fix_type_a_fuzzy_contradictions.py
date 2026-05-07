"""Fix Type A fuzzy contradictions: forbidden action is prefix of expected action.

Type A pairs identified:
1. give_aspirin (forbidden) vs give_aspirin_loading (expected) -- 5 scenarios
   Clinical: aspirin allergy -> ALL aspirin forms forbidden
2. give_epinephrine_1mg_iv (forbidden) vs give_epinephrine_1mg_iv_immediately (expected) -- 5 scenarios
   Clinical: hypothermia -> ALL epinephrine forms withheld
3. give_ceftriaxone (forbidden) vs give_ceftriaxone_iv (expected) -- 4 scenarios
   Clinical: penicillin allergy -> ALL ceftriaxone forms forbidden

Fix: move the expected action from expected_actions to forbidden_actions.
"""

from pathlib import Path

import yaml

SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"

# Type A patterns: (forbidden_prefix, expected_specific)
TYPE_A_PATTERNS: list[tuple[str, str]] = [
    ("give_aspirin", "give_aspirin_loading"),
    ("give_epinephrine_1mg_iv", "give_epinephrine_1mg_iv_immediately"),
    ("give_ceftriaxone", "give_ceftriaxone_iv"),
]


def find_type_a_conflicts(
    expected: list[str],
    forbidden: list[str],
) -> list[tuple[str, str]]:
    """Find Type A conflicts: forbidden is prefix of expected."""
    conflicts: list[tuple[str, str]] = []
    for f_action in forbidden:
        for e_action in expected:
            if e_action != f_action and e_action.startswith(f_action):
                conflicts.append((f_action, e_action))
    return conflicts


def fix_scenario(
    sid: str,
    cfg: dict,
) -> int:
    """Fix Type A fuzzy contradictions in a scenario. Returns fix count."""
    expected = cfg.get("expected_actions", [])
    forbidden = cfg.get("forbidden_actions", [])
    if not expected or not forbidden:
        return 0

    conflicts = find_type_a_conflicts(expected, forbidden)
    if not conflicts:
        return 0

    fixes = 0
    for f_prefix, e_specific in conflicts:
        # Move expected action to forbidden
        if e_specific in expected:
            expected.remove(e_specific)
            if e_specific not in forbidden:
                forbidden.append(e_specific)
            fixes += 1
            print(f"  FIX: {sid}")
            print(f"    forbidden '{f_prefix}' was prefix of expected '{e_specific}'")
            print(f"    -> moved '{e_specific}' from expected to forbidden")

    cfg["expected_actions"] = expected
    cfg["forbidden_actions"] = forbidden
    return fixes


def process_file(path: Path) -> int:
    """Process a single YAML file. Returns fix count."""
    with open(path) as f:
        data = yaml.safe_load(f)
    if not data:
        return 0

    scenarios = data.get("scenarios", {})
    if not isinstance(scenarios, dict):
        return 0

    total_fixes = 0
    for sid, cfg in scenarios.items():
        total_fixes += fix_scenario(sid, cfg)

    if total_fixes > 0:
        with open(path, "w") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        print(f"  Wrote {path.name}")

    return total_fixes


# Pre-scan: count all fuzzy pairs
print("=== Pre-fix scan ===")
type_a_total = 0
type_b_total = 0
for yaml_path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    if not data or "scenarios" not in data:
        continue
    for sid, cfg in data["scenarios"].items():
        expected = cfg.get("expected_actions", [])
        forbidden = cfg.get("forbidden_actions", [])
        if not expected or not forbidden:
            continue
        for f_action in forbidden:
            for e_action in expected:
                if e_action != f_action:
                    if e_action.startswith(f_action):
                        type_a_total += 1
                    elif f_action.startswith(e_action):
                        type_b_total += 1

print(f"Type A (PROBLEMATIC): {type_a_total}")
print(f"Type B (safe, expected is prefix of forbidden): {type_b_total}")
print(f"Total fuzzy pairs: {type_a_total + type_b_total}")

# Apply fixes
print("\n=== Applying Type A fixes ===")
total_fixes = 0
for yaml_path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
    total_fixes += process_file(yaml_path)

# Post-scan
print("\n=== Post-fix scan ===")
type_a_after = 0
type_b_after = 0
for yaml_path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    if not data or "scenarios" not in data:
        continue
    for sid, cfg in data["scenarios"].items():
        expected = cfg.get("expected_actions", [])
        forbidden = cfg.get("forbidden_actions", [])
        if not expected or not forbidden:
            continue
        for f_action in forbidden:
            for e_action in expected:
                if e_action != f_action:
                    if e_action.startswith(f_action):
                        type_a_after += 1
                    elif f_action.startswith(e_action):
                        type_b_after += 1

print(f"Type A (PROBLEMATIC): {type_a_after}")
print(f"Type B (safe): {type_b_after}")
print(f"Total fuzzy pairs: {type_a_after + type_b_after}")
print(f"\nTotal fixes applied: {total_fixes}")

if type_a_after > 0:
    print("\nWARNING: Some Type A contradictions remain!")
else:
    print("\nAll Type A contradictions resolved.")
