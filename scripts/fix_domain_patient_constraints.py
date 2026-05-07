"""Fix A: Domain-specific patient constraints.

OB scenarios must be Female age 18-45.
Peds scenarios must be age <= 17.
"""

from pathlib import Path
import random

import yaml

SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"

DOMAIN_CONSTRAINTS: dict[str, dict] = {
    "acog_obstetric_hemorrhage": {
        "sex": "F",
        "age_range": (18, 45),
    },
    "pals_pediatric_emergency": {
        "age_range": (0, 17),
    },
}


def fix_scenario(sid: str, cfg: dict, constraints: dict) -> int:
    """Apply domain constraints to a single scenario. Returns count of fixes."""
    patient = cfg.get("patient", {})
    fixes = 0

    # Sex constraint
    if "sex" in constraints and patient.get("sex") != constraints["sex"]:
        print(f"  FIX sex: {sid} {patient.get('sex')} -> {constraints['sex']}")
        patient["sex"] = constraints["sex"]
        fixes += 1

    # Age range constraint
    if "age_range" in constraints:
        lo, hi = constraints["age_range"]
        age = patient.get("age", 50)
        if age < lo or age > hi:
            random.seed(hash(sid) & 0xFFFFFFFF)
            new_age = random.randint(lo, hi)
            print(f"  FIX age: {sid} {age} -> {new_age} (range {lo}-{hi})")
            patient["age"] = new_age
            fixes += 1

    return fixes


def process_file(path: Path) -> int:
    """Process a single YAML scenario file. Returns count of fixes."""
    with open(path) as f:
        data = yaml.safe_load(f)
    if not data:
        return 0

    fixes = 0
    scenarios = data.get("scenarios", {})
    if not isinstance(scenarios, dict):
        return 0

    for sid, cfg in scenarios.items():
        graph = cfg.get("guideline_graph", "")
        constraints = DOMAIN_CONSTRAINTS.get(graph)
        if constraints:
            fixes += fix_scenario(sid, cfg, constraints)

    if fixes > 0:
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print(f"  Wrote {path.name} ({fixes} fixes)")

    return fixes


total = 0
for yaml_path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
    total += process_file(yaml_path)

print(f"\nTotal domain constraint fixes: {total}")
