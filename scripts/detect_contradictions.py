"""Test 2.2: Detect contradictions in generated scenarios.

Checks:
1. Same action in both expected AND forbidden
2. Empty scenarios (no expected and no forbidden)
3. Trap without description
4. Patient vitals out of physiological range
5. Lab values out of range
6. Trap vs normal differentiation per graph
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"


def main() -> None:
    issues: list[str] = []

    all_scenarios: list[dict] = []

    for sf in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
        with open(sf) as f:
            data = yaml.safe_load(f)
        if not data or "scenarios" not in data:
            continue
        for sid, sdata in data["scenarios"].items():
            sdata["_scenario_id"] = sid
            all_scenarios.append(sdata)

    for s in all_scenarios:
        sid = s["_scenario_id"]
        expected = set(s.get("expected_actions") or [])
        forbidden = set(s.get("forbidden_actions") or [])

        # 1. Expected & Forbidden overlap
        overlap = expected & forbidden
        if overlap:
            issues.append(f"CONTRADICTION: {sid} -- actions in both expected AND forbidden: {sorted(overlap)}")

        # 2. Both empty
        if len(expected) == 0 and len(forbidden) == 0:
            issues.append(f"EMPTY: {sid} -- no expected and no forbidden actions")

        # 3. Trap without description
        if s.get("trap_scenario") and not s.get("trap_description"):
            issues.append(f"TRAP-NO-DESC: {sid} -- trap=True but no description")

        # 4. Vitals range check
        patient = s.get("patient", {})
        vitals = patient.get("vitals", {})
        if vitals:
            hr = vitals.get("hr") or vitals.get("heart_rate")
            sbp = vitals.get("sbp") or vitals.get("blood_pressure_systolic")
            spo2 = vitals.get("spo2") or vitals.get("oxygen_saturation")
            temp = vitals.get("temp") or vitals.get("temperature")

            if hr is not None and (hr < 20 or hr > 250):
                issues.append(f"VITALS: {sid} -- HR={hr} out of physiological range")
            if sbp is not None and (sbp < 40 or sbp > 300):
                issues.append(f"VITALS: {sid} -- SBP={sbp} out of physiological range")
            if spo2 is not None and (spo2 < 30 or spo2 > 100):
                issues.append(f"VITALS: {sid} -- SpO2={spo2} out of range")
            if temp is not None and (temp < 30 or temp > 43):
                issues.append(f"VITALS: {sid} -- Temp={temp} out of range")

        # 5. Lab range check
        labs = patient.get("labs", {})
        if labs:
            k = labs.get("potassium")
            if k is not None and (k < 1.0 or k > 10.0):
                issues.append(f"LABS: {sid} -- K+={k} out of physiological range")
            glu = labs.get("glucose")
            if glu is not None and (glu < 10 or glu > 1500):
                issues.append(f"LABS: {sid} -- Glucose={glu} out of range")
            ph = labs.get("ph")
            if ph is not None and (ph < 6.5 or ph > 7.8):
                issues.append(f"LABS: {sid} -- pH={ph} out of range")

    # 6. Trap vs normal differentiation
    by_graph: dict[str, list[dict]] = defaultdict(list)
    for s in all_scenarios:
        by_graph[s.get("guideline_graph", "unknown")].append(s)

    for graph_id, graph_scenarios in by_graph.items():
        traps = [s for s in graph_scenarios if s.get("trap_scenario")]
        normals = [s for s in graph_scenarios if not s.get("trap_scenario")]

        if traps and normals:
            trap_forbidden: set[str] = set()
            for t in traps:
                trap_forbidden.update(t.get("forbidden_actions") or [])
            normal_forbidden: set[str] = set()
            for n in normals:
                normal_forbidden.update(n.get("forbidden_actions") or [])

            trap_only = trap_forbidden - normal_forbidden
            if not trap_only:
                issues.append(
                    f"NO-DIFF: {graph_id} -- trap and normal have identical forbidden "
                    f"(conditional rules not differentiating)"
                )

    # Report
    print(f"\n{'=' * 60}")
    print(f"Total scenarios checked: {len(all_scenarios)}")
    print(f"Total issues found: {len(issues)}")
    print(f"{'=' * 60}")

    by_type: dict[str, list[str]] = defaultdict(list)
    for issue in issues:
        issue_type = issue.split(":")[0]
        by_type[issue_type].append(issue)

    for itype, ilist in sorted(by_type.items()):
        print(f"\n{itype}: {len(ilist)}")
        for i in ilist[:5]:
            print(f"  {i}")
        if len(ilist) > 5:
            print(f"  ... and {len(ilist) - 5} more")

    if not issues:
        print("\nNo issues found.")

    # Save report
    evidence_dir = Path(__file__).parent.parent / "evidence_pack"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with open(evidence_dir / "scenario_contradiction_report.txt", "w") as f:
        f.write(f"Total scenarios: {len(all_scenarios)}\n")
        f.write(f"Total issues: {len(issues)}\n\n")
        f.write("\n".join(issues) if issues else "No issues found.")

    print("\nSaved to evidence_pack/scenario_contradiction_report.txt")


if __name__ == "__main__":
    main()
