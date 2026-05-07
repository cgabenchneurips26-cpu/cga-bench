"""Fix remaining realism issues: pregnancy sex, extreme ages, impossible combos.

Issues addressed:
1. Male + pregnancy: scenarios with pregnancy in comorbidities must be Female
2. Extreme ages (>100): cap age_extreme_hi scenarios at 99
3. Impossible combo: se_combo_pregnancy_no_valproate_elderly_dose_reduce (age 82 + pregnancy)
"""

from pathlib import Path
import random

import yaml

SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"

PREGNANCY_KEYWORDS = [
    "pregnancy",
    "eclampsia",
    "preeclampsia",
    "postpartum",
    "perimortem",
    "teratogen",
]

# Impossible combos: scenarios that combine mutually exclusive clinical conditions
IMPOSSIBLE_COMBOS = {
    "se_combo_pregnancy_no_valproate_elderly_dose_reduce",
}

random.seed(42)


def has_pregnancy(cfg: dict) -> bool:
    """Check if scenario involves pregnancy via comorbidities or keywords."""
    patient = cfg.get("patient", {})
    comorbidities = patient.get("comorbidities", [])
    if isinstance(comorbidities, list):
        if any("pregnancy" in str(c).lower() for c in comorbidities):
            return True

    # Also check description and trap_description for pregnancy keywords
    combined = " ".join(
        [
            str(cfg.get("description", "")).lower(),
            str(cfg.get("trap_description", "")).lower(),
        ]
    )
    return any(kw in combined for kw in PREGNANCY_KEYWORDS)


def fix_scenario(sid: str, cfg: dict) -> list[str]:
    """Fix a single scenario. Returns list of fix descriptions."""
    fixes: list[str] = []
    patient = cfg.get("patient", {})

    # Fix 1: Delete impossible combo scenarios
    if sid in IMPOSSIBLE_COMBOS:
        return ["DELETE"]

    # Fix 2: Pregnancy scenarios must be Female with realistic age
    if has_pregnancy(cfg):
        if patient.get("sex") == "M":
            patient["sex"] = "F"
            fixes.append("sex M->F (pregnancy)")

        age = patient.get("age")
        if age is not None and (age > 50 or age < 16):
            random.seed(hash(sid) & 0xFFFFFFFF)
            new_age = random.randint(22, 40)
            patient["age"] = new_age
            fixes.append(f"age {age}->{new_age} (pregnancy range)")

    # Fix 3: Cap extreme ages at 99
    age = patient.get("age")
    if age is not None and age > 100:
        patient["age"] = 99
        fixes.append(f"age {age}->99 (cap extreme)")

    return fixes


def process_file(path: Path) -> tuple[int, int]:
    """Process a single YAML file. Returns (fixes, deletions)."""
    with open(path) as f:
        data = yaml.safe_load(f)
    if not data:
        return 0, 0

    scenarios = data.get("scenarios", {})
    if not isinstance(scenarios, dict):
        return 0, 0

    fix_count = 0
    delete_count = 0
    to_delete: list[str] = []

    for sid, cfg in list(scenarios.items()):
        fixes = fix_scenario(sid, cfg)
        if "DELETE" in fixes:
            to_delete.append(sid)
            delete_count += 1
            print(f"  DELETE: {sid} (impossible clinical combo)")
        elif fixes:
            fix_count += len(fixes)
            for desc in fixes:
                print(f"  FIX: {sid} -- {desc}")

    for sid in to_delete:
        del scenarios[sid]

    if fix_count > 0 or delete_count > 0:
        with open(path, "w") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        print(f"  Wrote {path.name}")

    return fix_count, delete_count


# Count before
before_issues: list[str] = []
for yaml_path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    if not data or "scenarios" not in data:
        continue
    for sid, cfg in data["scenarios"].items():
        patient = cfg.get("patient", {})
        if has_pregnancy(cfg) and patient.get("sex") == "M":
            before_issues.append(f"{sid}: male + pregnancy")
        age = patient.get("age")
        if age is not None and age > 100:
            before_issues.append(f"{sid}: age={age} (extreme)")

print(f"Issues before fix: {len(before_issues)}")
for issue in before_issues:
    print(f"  - {issue}")

# Apply fixes
print("\nApplying fixes...")
total_fixes = 0
total_deletes = 0
for yaml_path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
    fixes, deletes = process_file(yaml_path)
    total_fixes += fixes
    total_deletes += deletes

# Verify after
after_issues: list[str] = []
total_scenarios = 0
for yaml_path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    if not data or "scenarios" not in data:
        continue
    for sid, cfg in data["scenarios"].items():
        total_scenarios += 1
        patient = cfg.get("patient", {})
        if has_pregnancy(cfg) and patient.get("sex") == "M":
            after_issues.append(f"{sid}: male + pregnancy")
        age = patient.get("age")
        if age is not None and age > 100:
            after_issues.append(f"{sid}: age={age} (extreme)")

print(f"\nTotal fixes: {total_fixes}, deletions: {total_deletes}")
print(f"Total scenarios after: {total_scenarios}")
print(f"Issues after fix: {len(after_issues)}")
if after_issues:
    for issue in after_issues:
        print(f"  - {issue}")
else:
    print("  None -- all pregnancy/age issues resolved")
