"""Cross-reference manual scenario forbidden actions vs derived constraints.

For each manual scenario, verifies that:
1. Manual forbidden_actions are a subset of derived forbidden actions
2. Reports any missing (manual not in derived) or extra (derived not in manual)
"""

from __future__ import annotations

from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"
SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"

# Mapping from guideline_graph to graph file
GRAPH_FILE_MAP: dict[str, str] = {
    "ssc_sepsis_hour1_bundle": "ssc_sepsis_hour1_bundle.yaml",
    "ssc_sepsis_hour1": "ssc_sepsis_hour1_bundle.yaml",
    "aha_chest_pain_evaluation": "aha_chest_pain_evaluation.yaml",
    "aha_chest_pain_stemi": "aha_chest_pain_evaluation.yaml",
    "aha_chest_pain": "aha_chest_pain_evaluation.yaml",
    "aha_stroke_2019": "aha_stroke_2019.yaml",
    "aha_stroke": "aha_stroke_2019.yaml",
    "aha_heart_failure_2022": "aha_heart_failure_2022.yaml",
    "aha_heart_failure": "aha_heart_failure_2022.yaml",
    "kdigo_contrast_aki": "kdigo_contrast_aki.yaml",
    "kdigo_aki_full": "kdigo_aki_full.yaml",
    "ada_dka_management": "ada_dka_management.yaml",
    "atrial_fibrillation": "atrial_fibrillation.yaml",
    "cap_pneumonia": "cap_pneumonia.yaml",
    "copd_exacerbation": "copd_exacerbation.yaml",
    "gi_bleeding": "gi_bleeding.yaml",
    "hypertensive_emergency": "hypertensive_emergency.yaml",
    "pulmonary_embolism": "pulmonary_embolism.yaml",
    "universal_clinical_safety": "universal_clinical_safety.yaml",
    "anaphylaxis_management": "anaphylaxis_management.yaml",
    "acls_cardiac_arrest": "acls_cardiac_arrest.yaml",
    "status_epilepticus": "status_epilepticus.yaml",
    "gina_asthma_exacerbation": "gina_asthma_exacerbation.yaml",
    "idsa_meningitis": "idsa_meningitis.yaml",
    "toxicology_management": "toxicology_management.yaml",
}


def _build_patient_dict(patient_data: dict) -> dict:
    """Convert scenario patient data to flat dict for engine."""
    result: dict = {}
    for key, value in patient_data.items():
        if key == "vitals" and isinstance(value, dict):
            result["vitals"] = value
        elif key in ("allergies", "comorbidities", "medications", "contraindications"):
            result[key] = value if isinstance(value, list) else []
        else:
            result[key] = value

    # Ensure required keys exist
    result.setdefault("allergies", [])
    result.setdefault("comorbidities", [])
    result.setdefault("medications", [])
    result.setdefault("labs", {})
    result.setdefault("vitals", {})
    result.setdefault("history", [])
    return result


def main() -> None:
    engine = ConstraintDerivationEngine()

    total_scenarios = 0
    total_missing = 0
    total_extra = 0
    scenarios_with_missing = 0

    print("Cross-referencing manual scenarios vs derived constraints...")
    print("=" * 70)

    for scenario_file in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
        if scenario_file.name == "auto_generated_scenarios.yaml":
            continue

        with open(scenario_file) as f:
            data = yaml.safe_load(f)

        if not data or "scenarios" not in data:
            continue

        for sid, sdata in data["scenarios"].items():
            total_scenarios += 1
            manual_forbidden = set(sdata.get("forbidden_actions", []))
            if not manual_forbidden:
                continue

            guideline = sdata.get("guideline_graph", "")
            graph_file = GRAPH_FILE_MAP.get(guideline)
            if not graph_file:
                continue

            graph_path = GRAPHS_DIR / graph_file
            if not graph_path.exists():
                continue

            graph = load_graph(graph_path)
            patient = _build_patient_dict(sdata.get("patient", {}))
            derived = engine.derive(graph, patient, sid)

            derived_forbidden = set(a for c in derived.forbidden for a in c.actions)

            missing = manual_forbidden - derived_forbidden
            extra = derived_forbidden - manual_forbidden

            if missing:
                total_missing += len(missing)
                scenarios_with_missing += 1
                print(f"\n  WARNING: {sid}")
                print(f"    Manual forbidden not in derived: {sorted(missing)}")
                print("    -> Graph may need additional conditional rules")

            if extra:
                total_extra += len(extra)

    print()
    print("=" * 70)
    print(f"Total scenarios checked: {total_scenarios}")
    print(f"Scenarios with missing coverage: {scenarios_with_missing}")
    print(f"Total missing forbidden actions: {total_missing}")
    print(f"Total extra derived actions: {total_extra}")

    if scenarios_with_missing == 0:
        print("\nAll manual forbidden actions are covered by derived constraints.")
    else:
        print(f"\n{scenarios_with_missing} scenarios need graph rule additions.")


if __name__ == "__main__":
    main()
