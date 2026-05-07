"""Fix B: Balance sex distribution from M:F ~3:1 to ~55:45.

Domain-specific constraints (OB, peds) are handled by fix_domain_patient_constraints.py.
This script balances sex for remaining non-domain-specific scenarios.
"""

from collections import Counter
from pathlib import Path
import random

import yaml

SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"

SEX_SPECIFIC_F = [
    "pregnancy",
    "eclampsia",
    "pph",
    "postpartum",
    "ovarian",
    "cervical",
    "endometri",
    "obstetric",
]
SEX_SPECIFIC_M = ["prostate", "testicular"]

# Graphs where sex must be F
FEMALE_GRAPHS = {"acog_obstetric_hemorrhage"}

random.seed(42)


def should_keep_sex(sid: str, cfg: dict) -> bool:
    """Return True if this scenario has sex-specific clinical content."""
    patient = cfg.get("patient", {})
    graph = cfg.get("guideline_graph", "")

    if graph in FEMALE_GRAPHS:
        return True

    combined = " ".join(
        [
            str(patient.get("comorbidities", [])).lower(),
            str(patient.get("presentation", {})).lower(),
            str(cfg.get("description", "")).lower(),
            str(cfg.get("trap_description", "")).lower(),
        ]
    )

    if any(kw in combined for kw in SEX_SPECIFIC_F):
        return True
    if any(kw in combined for kw in SEX_SPECIFIC_M):
        return True

    return False


def process_file(path: Path) -> int:
    """Balance sex in a single YAML file. Returns count of changes."""
    with open(path) as f:
        data = yaml.safe_load(f)
    if not data:
        return 0

    scenarios = data.get("scenarios", {})
    if not isinstance(scenarios, dict):
        return 0

    changes = 0
    for sid, cfg in scenarios.items():
        patient = cfg.get("patient", {})
        if should_keep_sex(sid, cfg):
            continue

        # Flip M -> F with 50% probability to reach ~50:50
        if patient.get("sex") == "M" and random.random() < 0.5:
            patient["sex"] = "F"
            changes += 1

    if changes > 0:
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return changes


# First pass: count current distribution
before = Counter()
for yaml_path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    if not data or "scenarios" not in data:
        continue
    for sid, cfg in data["scenarios"].items():
        before[cfg.get("patient", {}).get("sex", "?")] += 1

print(f"Before: {dict(before)}")
total_before = sum(before.values())
print(f"F ratio before: {before.get('F', 0) / total_before * 100:.0f}%")

# Apply balancing
total_changes = 0
for yaml_path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
    changes = process_file(yaml_path)
    if changes > 0:
        print(f"  {yaml_path.name}: {changes} changes")
    total_changes += changes

# Verify after
after = Counter()
for yaml_path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    if not data or "scenarios" not in data:
        continue
    for sid, cfg in data["scenarios"].items():
        after[cfg.get("patient", {}).get("sex", "?")] += 1

print(f"\nAfter: {dict(after)}")
total_after = sum(after.values())
print(f"F ratio after: {after.get('F', 0) / total_after * 100:.0f}%")
print(f"Total changes: {total_changes}")
