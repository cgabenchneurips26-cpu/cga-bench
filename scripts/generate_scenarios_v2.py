"""Scenario generator v2 — add patient-variation axes for richer coverage.

Extends generate_scenarios_from_cpg.py to produce ~15-30 scenarios per CPG
even when the underlying graph has sparse branches/conditional_rules.

Additional variation axes (on top of branch + severity):
  - Age: young (25), middle (55), elderly (80)
  - Sex: M, F
  - Comorbidity profile: none, common (HTN/DM), complex (CKD+CAD+DM)
  - Allergy profile: none, penicillin, sulfa, contrast

Output: configs/scenarios/auto_v2/<graph_id>_scenarios.yaml

Usage:
    PYTHONPATH=. python scripts/generate_scenarios_v2.py \
        --graphs-dir cpg_model/graphs/auto \
        --output-dir configs/scenarios/auto_v2 \
        --max-per-graph 24 --seed 42
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import random
import sys
from typing import Any

import yaml

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse v1 helpers
from scripts.generate_scenarios_from_cpg import (  # noqa: E402
    _chief_complaint_for_domain,
    _extract_domain,
    extract_branch_diagnoses,
    extract_conditional_triggers,
)

# Variation axes (kept small to control combinatorial explosion)
AGE_PROFILES = [
    ("young", 25),
    ("middle", 55),
    ("elderly", 80),
]

SEX_PROFILES = ["M", "F"]

COMORBIDITY_PROFILES = {
    "none": [],
    "common": ["hypertension", "diabetes"],
    "complex": ["chronic_kidney_disease", "coronary_artery_disease", "diabetes"],
    "immunocompromised": ["chemotherapy_ongoing", "hiv"],
}

ALLERGY_PROFILES = {
    "none": [],
    "penicillin": ["penicillin"],
    "sulfa": ["sulfonamides"],
    "contrast": ["iodinated_contrast"],
}

SEVERITY_VITALS = {
    "mild": {
        "heart_rate": 95,
        "blood_pressure_systolic": 135,
        "blood_pressure_diastolic": 85,
        "respiratory_rate": 20,
        "temperature": 38.0,
        "oxygen_saturation": 94,
        "map_mmhg": 102,
    },
    "moderate": {
        "heart_rate": 110,
        "blood_pressure_systolic": 100,
        "blood_pressure_diastolic": 60,
        "respiratory_rate": 24,
        "temperature": 38.8,
        "oxygen_saturation": 90,
        "map_mmhg": 73,
    },
    "severe": {
        "heart_rate": 130,
        "blood_pressure_systolic": 82,
        "blood_pressure_diastolic": 50,
        "respiratory_rate": 30,
        "temperature": 39.5,
        "oxygen_saturation": 85,
        "map_mmhg": 61,
    },
}


def make_scenario(
    graph_id: str,
    guideline_name: str,
    domain: str,
    diagnosis: str,
    age_label: str,
    age_val: int,
    sex: str,
    severity: str,
    comorb_label: str,
    comorbs: list[str],
    allergy_label: str,
    allergies: list[str],
    counter: int,
) -> dict[str, Any]:
    """Assemble one scenario dict."""
    scenario_id = (f"{graph_id}_{diagnosis}_{severity}_{age_label}_{sex}_{comorb_label}_{allergy_label}_{counter}")[
        :120
    ]
    vitals = dict(SEVERITY_VITALS[severity])
    return {
        "scenario_id": scenario_id,
        "description": (
            f"{guideline_name} — {diagnosis} ({severity}, {age_label}-{sex}, "
            f"comorbidities: {comorb_label}, allergies: {allergy_label})"
        ),
        "guideline_graph": graph_id,
        "patient": {
            "age": age_val,
            "sex": sex,
            "weight_kg": 70 if sex == "M" else 60,
            "chief_complaint": _chief_complaint_for_domain(domain),
            "working_diagnosis": diagnosis,
            "vitals": vitals,
            "allergies": allergies,
            "comorbidities": comorbs,
            "contraindications": [],
        },
        "expected_actions": [],
    }


def generate_rich_scenarios(
    graph: dict[str, Any],
    graph_path: Path,
    rng: random.Random,
    max_scenarios: int = 24,
) -> dict[str, dict[str, Any]]:
    """Generate up to max_scenarios with patient-variation axes."""
    graph_id = graph.get("graph_id", graph_path.stem)
    guideline_name = graph.get("guideline_name", graph_id)
    domain = _extract_domain(graph)

    diagnoses = extract_branch_diagnoses(graph) or [domain]
    triggers = extract_conditional_triggers(graph)

    scenarios: dict[str, dict[str, Any]] = {}
    counter = 0

    # Iterate all combinations in a stratified manner to hit max_scenarios
    for dx in diagnoses:
        for age_label, age_val in AGE_PROFILES:
            for sex in SEX_PROFILES:
                for severity in ("mild", "moderate", "severe"):
                    if len(scenarios) >= max_scenarios:
                        break
                    # Pick a comorbidity and allergy combination (rotating)
                    comorb_keys = list(COMORBIDITY_PROFILES.keys())
                    allergy_keys = list(ALLERGY_PROFILES.keys())
                    comorb_label = comorb_keys[counter % len(comorb_keys)]
                    allergy_label = allergy_keys[counter % len(allergy_keys)]
                    comorbs = COMORBIDITY_PROFILES[comorb_label]
                    allergies = ALLERGY_PROFILES[allergy_label]

                    sc = make_scenario(
                        graph_id,
                        guideline_name,
                        domain,
                        dx,
                        age_label,
                        age_val,
                        sex,
                        severity,
                        comorb_label,
                        comorbs,
                        allergy_label,
                        allergies,
                        counter,
                    )
                    scenarios[sc["scenario_id"]] = sc
                    counter += 1

    # Add trigger-based scenarios from conditional_rules
    for trg in triggers:
        if len(scenarios) >= max_scenarios:
            break
        dx = diagnoses[0]
        sc = make_scenario(
            graph_id,
            guideline_name,
            domain,
            dx,
            "trigger",
            55,
            "F",
            "moderate",
            "trigger",
            trg.get("comorbidities", []),
            "trigger",
            trg.get("allergies", []),
            counter,
        )
        sc["description"] = f"{guideline_name} — {dx} (conditional-trigger: {trg.get('description', '')[:60]})"
        scenarios[sc["scenario_id"]] = sc
        counter += 1

    return scenarios


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--graph", type=Path, help="Single CPG YAML")
    g.add_argument("--graphs-dir", type=Path, help="Directory of CPG YAMLs")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("configs/scenarios/auto_v2"),
        help="Output directory",
    )
    parser.add_argument("--max-per-graph", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    if args.graph:
        graph_files = [args.graph]
    else:
        graph_files = sorted(args.graphs_dir.glob("*.yaml"))
    if not graph_files:
        logger.error("no graph files found")
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    total = 0
    for gf in graph_files:
        try:
            graph = yaml.safe_load(gf.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("failed to parse %s: %s", gf, exc)
            continue
        if not graph:
            continue
        scenarios = generate_rich_scenarios(graph, gf, rng, args.max_per_graph)
        if not scenarios:
            logger.warning("no scenarios generated for %s", gf.name)
            continue
        graph_id = graph.get("graph_id", gf.stem)
        out_path = args.output_dir / f"{graph_id}_scenarios.yaml"
        if not args.dry_run:
            out_path.write_text(
                yaml.safe_dump({"scenarios": scenarios}, default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
        logger.info("  Generated %d for %s → %s", len(scenarios), graph_id, out_path.name)
        total += len(scenarios)

    print(f"\nTotal {total} scenarios across {len(graph_files)} graphs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
