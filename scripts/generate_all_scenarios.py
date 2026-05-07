"""Generate all scenarios from CPG graphs using PatientGenerator.

Reads all graph YAMLs, derives constraints, generates trigger/normal/combo
scenarios, and saves them to configs/scenarios/.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
from cpg_model.patient_generator import GeneratedScenario, PatientGenerator

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"
SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"
OUTPUT_FILE = SCENARIOS_DIR / "auto_generated_scenarios.yaml"


def scenario_to_yaml_dict(s: GeneratedScenario) -> dict:
    """Convert GeneratedScenario to scenario YAML format."""
    result: dict = {
        "scenario_id": s.scenario_id,
        "description": s.trap_description if s.trap_scenario else f"Baseline scenario for {s.guideline_graph}",
        "guideline_graph": s.guideline_graph,
        "patient": s.patient,
        "trap_scenario": s.trap_scenario,
        "generation_method": s.generation_method,
        "triggered_rules": s.triggered_rules,
    }
    if s.trap_description:
        result["trap_description"] = s.trap_description

    # Prefer pre-computed fields; fall back to derived constraints extraction
    if s.expected_actions:
        expected_actions = list(s.expected_actions)
    else:
        derived = s.derived_constraints
        expected_actions = []
        for c in derived.get("required", []):
            expected_actions.extend(c.get("actions", []))
        for c in derived.get("expected", []):
            expected_actions.extend(c.get("actions", []))

    if s.forbidden_actions:
        forbidden_actions = list(s.forbidden_actions)
    else:
        derived = s.derived_constraints
        forbidden_actions = []
        for c in derived.get("forbidden", []):
            forbidden_actions.extend(c.get("actions", []))

    result["forbidden_actions"] = sorted(set(forbidden_actions))
    result["expected_actions"] = sorted(set(expected_actions))
    result["_derived_constraints"] = s.derived_constraints

    if s.pathway_id:
        result["pathway_id"] = s.pathway_id
    if s.pathway_description:
        result["pathway_description"] = s.pathway_description

    return result


def main() -> None:
    engine = ConstraintDerivationEngine()
    generator = PatientGenerator(engine, seed=42)

    all_generated: list[GeneratedScenario] = []

    print("Generating scenarios from CPG graphs...")
    print("=" * 60)

    for graph_path in sorted(GRAPHS_DIR.glob("*.yaml")):
        graph = load_graph(graph_path)
        graph_id = graph.get("graph_id", graph_path.stem)
        scenarios = generator.generate_from_graph(graph)
        all_generated.extend(scenarios)
        trap_count = sum(1 for s in scenarios if s.trap_scenario)
        print(f"  {graph_id}: {len(scenarios)} scenarios ({trap_count} traps)")

    # Load existing manual scenario IDs to avoid collision
    manual_ids: set[str] = set()
    for scenario_file in SCENARIOS_DIR.glob("*_scenarios.yaml"):
        if scenario_file.name == "auto_generated_scenarios.yaml":
            continue
        with open(scenario_file) as f:
            data = yaml.safe_load(f)
        if data and "scenarios" in data:
            manual_ids.update(data["scenarios"].keys())

    # Filter out collisions with manual scenarios
    new_auto = [s for s in all_generated if s.scenario_id not in manual_ids]

    # Save auto-generated scenarios
    scenarios_dict = {}
    for s in new_auto:
        scenarios_dict[s.scenario_id] = scenario_to_yaml_dict(s)

    output_data = {
        "defaults": {
            "time_step_minutes": 5,
            "lab_result_delay_minutes": 30,
            "imaging_result_delay_minutes": 15,
            "max_duration_minutes": 120,
            "enable_state_deterioration": True,
        },
        "scenarios": scenarios_dict,
    }

    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        yaml.dump(output_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)

    # Summary statistics
    total = len(new_auto)
    trap_count = sum(1 for s in new_auto if s.trap_scenario)
    graph_counter = Counter(s.guideline_graph for s in new_auto)

    print()
    print("=" * 60)
    print(f"TOTAL: {total} auto-generated scenarios")
    print(f"  Traps: {trap_count} ({trap_count / max(total, 1) * 100:.0f}%)")
    print(f"  Baselines: {total - trap_count}")
    print(f"  Graphs: {len(graph_counter)}")
    print(f"  Manual scenario IDs skipped: {len(manual_ids & {s.scenario_id for s in all_generated})}")
    print()
    print("Per-graph breakdown:")
    for graph_id, count in graph_counter.most_common():
        print(f"  {graph_id}: {count}")
    print()
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
