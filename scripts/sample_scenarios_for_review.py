"""Test 2.1: Sample scenarios for human review.

Extracts 1 trap + 1 normal from each graph for clinical validity inspection.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import random
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"
EVIDENCE_DIR = Path(__file__).parent.parent / "evidence_pack"


def main() -> None:
    random.seed(42)

    auto_path = SCENARIOS_DIR / "auto_generated_scenarios.yaml"
    with open(auto_path) as f:
        data = yaml.safe_load(f)

    scenarios = data.get("scenarios", {})

    by_graph: dict[str, list[dict]] = defaultdict(list)
    for sid, sdata in scenarios.items():
        sdata["_scenario_id"] = sid
        by_graph[sdata.get("guideline_graph", "unknown")].append(sdata)

    output: list[str] = []

    for graph_id in sorted(by_graph.keys()):
        graph_scenarios = by_graph[graph_id]
        traps = [s for s in graph_scenarios if s.get("trap_scenario")]
        normals = [s for s in graph_scenarios if not s.get("trap_scenario")]

        sample_trap = random.choice(traps) if traps else None
        sample_normal = random.choice(normals) if normals else None

        for label, s in [("TRAP", sample_trap), ("NORMAL", sample_normal)]:
            if s is None:
                continue

            patient = s.get("patient", {})
            expected = s.get("expected_actions", [])
            forbidden = s.get("forbidden_actions", [])

            expected_str = "\n".join(f"  - {a}" for a in expected[:15])
            if len(expected) > 15:
                expected_str += f"\n  ... ({len(expected) - 15} more)"

            forbidden_str = "\n".join(f"  - {a}" for a in forbidden[:15])
            if len(forbidden) > 15:
                forbidden_str += f"\n  ... ({len(forbidden) - 15} more)"

            output.append(
                f"{'=' * 80}\n"
                f"GRAPH: {graph_id} | TYPE: {label} | ID: {s['_scenario_id']}\n"
                f"{'=' * 80}\n"
                f"\n"
                f"PATIENT:\n"
                f"  Age: {patient.get('age', '?')}, Sex: {patient.get('sex', '?')}\n"
                f"  Chief complaint: {patient.get('chief_complaint', '?')}\n"
                f"\n"
                f"  Labs: {patient.get('labs', {})}\n"
                f"  Vitals: {patient.get('vitals', {})}\n"
                f"  Comorbidities: {patient.get('comorbidities', [])}\n"
                f"  Allergies: {patient.get('allergies', [])}\n"
                f"  Medications: {patient.get('medications', [])}\n"
                f"\n"
                f"EXPECTED ACTIONS ({len(expected)}):\n"
                f"{expected_str}\n"
                f"\n"
                f"FORBIDDEN ACTIONS ({len(forbidden)}):\n"
                f"{forbidden_str}\n"
                f"\n"
                f"TRAP: {s.get('trap_scenario', False)}\n"
                f"TRAP DESCRIPTION: {s.get('trap_description', 'N/A')}\n"
                f"TRIGGERED RULES: {s.get('triggered_rules', [])}\n"
            )

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    with open(EVIDENCE_DIR / "scenario_sample_review.txt", "w") as f:
        f.write("\n\n".join(output))

    print(f"Wrote {len(output)} scenario reviews to evidence_pack/scenario_sample_review.txt")


if __name__ == "__main__":
    main()
