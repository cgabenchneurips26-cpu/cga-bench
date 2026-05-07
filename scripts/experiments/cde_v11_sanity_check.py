"""T2+U6 sanity check: CDE v1.1 derive() on all 25 CPG graphs.

Validates that ConstraintDerivationEngine.derive() runs without crash
on every graph in the catalogue.  Uses a generic patient context
(comorbidities + allergies that maximise conditional-rule activation).

Mode:
  --conflict-only   Original T2 behaviour: only conflict-bearing graphs (9)
  (default)         All 25 graphs in cpg_model/graphs/

Exit code 0 = all OK; exit code 1 = at least one failure.

Usage:
    PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject:/home/anonymous-org/anonymous-project/AnonProject/cga_bench \
        python scripts/experiments/cde_v11_sanity_check.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cga_bench.cpg_model.constraint_derivation import (
    ConstraintDerivationEngine,
    load_graph,
)

REPO = Path(__file__).resolve().parents[2]
AUDIT_PATH = REPO / "evidence_pack" / "cde_conflict_audit_v1.json"
GRAPH_DIR = REPO / "cpg_model" / "graphs"


def _generic_patient() -> dict:
    """Broad patient context that triggers many conditional rules."""
    return {
        "vitals": {
            "sbp": 80,
            "map_mmhg": 55,
            "temperature": 36.0,
            "heart_rate": 120,
            "respiratory_rate": 28,
            "oxygen_saturation": 88,
        },
        "labs": {
            "potassium": 6.0,
            "creatinine": 3.5,
            "ph": 7.28,
            "lactate": 4.5,
            "hemoglobin": 6.5,
            "platelets": 45,
            "inr": 2.8,
        },
        "comorbidities": [
            "esrd",
            "hemodialysis",
            "active_bleeding",
            "recent_surgery",
            "aortic_dissection_suspected",
            "congenital_heart_disease",
            "hyperkalemia",
            "renal_failure",
        ],
        "allergies": ["penicillin", "cephalosporin"],
        "history": ["recent_surgery_3_weeks"],
        "contraindications": ["active_bleeding", "recent_surgery"],
        "age": 70,
        "weight_kg": 65,
        "medications": [],
    }


def _get_conflict_graph_ids() -> set[str]:
    """Load conflict-bearing graph IDs from CDE audit JSON."""
    audit = json.load(open(AUDIT_PATH))
    ids: set[str] = set()
    for c in audit.get("conflicts", []):
        g = c.get("graph", "")
        if g:
            ids.add(g)
    return ids


def _get_all_graph_ids() -> list[str]:
    """Discover all graph YAML files (excluding auto/ subdirectory)."""
    return sorted(f.stem for f in GRAPH_DIR.glob("*.yaml") if f.is_file())


def main() -> int:
    """Run CDE derive() on all 25 graphs (or --conflict-only for 9)."""
    conflict_only = "--conflict-only" in sys.argv

    if conflict_only:
        graph_ids = sorted(_get_conflict_graph_ids())
        label = f"{len(graph_ids)} conflict-bearing graphs"
    else:
        graph_ids = _get_all_graph_ids()
        label = f"{len(graph_ids)} total graphs (all)"

    conflict_set = _get_conflict_graph_ids()

    print(f"CDE v1.1 Sanity Check — {label}")
    print("=" * 60)

    engine = ConstraintDerivationEngine()
    patient = _generic_patient()
    ok = 0
    fail = 0
    results: list[dict] = []

    for graph_id in graph_ids:
        graph_file = GRAPH_DIR / f"{graph_id}.yaml"
        if not graph_file.exists():
            print(f"  SKIP  {graph_id} — file not found")
            continue

        try:
            graph = load_graph(graph_file)
            derived = engine.derive(graph, patient, scenario_id=f"sanity_{graph_id}")

            n_forbidden = len(derived.forbidden)
            n_required = len(derived.required)
            n_conflicts = len(derived.conflicts)
            n_total = len(derived.all_constraints())

            status = "OK" if n_total > 0 else "WARN (0 constraints)"
            is_conflict = graph_id in conflict_set
            tag = " [C]" if is_conflict else ""
            print(
                f"  {status:6s} {graph_id}{tag}: F={n_forbidden} R={n_required} CONFLICT={n_conflicts} total={n_total}"
            )
            ok += 1
            results.append(
                {
                    "graph_id": graph_id,
                    "status": "ok",
                    "forbidden": n_forbidden,
                    "required": n_required,
                    "conflicts": n_conflicts,
                    "total": n_total,
                    "is_conflict_graph": is_conflict,
                }
            )
        except Exception as e:
            print(f"  FAIL  {graph_id}: {e}")
            traceback.print_exc()
            fail += 1
            results.append({"graph_id": graph_id, "status": "fail", "error": str(e)})

    print("=" * 60)
    print(f"Result: {ok} OK, {fail} FAIL out of {len(graph_ids)} graphs")

    # Write JSON report
    out_path = REPO / "evidence_pack" / "analysis" / "cde_v11_sanity_check.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "total_graphs": len(graph_ids),
        "ok": ok,
        "fail": fail,
        "mode": "conflict_only" if conflict_only else "all_25",
        "patient_context": "generic (maximise conditional-rule activation)",
        "note": "Real episodes lack stored states; CDE derive() tested on production graph YAMLs",
        "results": results,
    }
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report: {out_path}")

    return 1 if fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
