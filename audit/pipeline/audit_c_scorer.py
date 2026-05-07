"""Section C: Scoring이 새 시나리오에서 작동하는가."""

from __future__ import annotations

import inspect
from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parents[2]

HELD_OUT_GRAPHS: list[str] = [
    "anaphylaxis_management",
    "acls_cardiac_arrest",
    "status_epilepticus",
    "gina_asthma_exacerbation",
    "idsa_meningitis",
    "toxicology_management",
    "aba_burn_resuscitation",
    "aabb_transfusion",
    "acog_obstetric_hemorrhage",
    "pals_pediatric_emergency",
    "apa_agitation_management",
]

GRAPHS_DIR = ROOT / "cpg_model" / "graphs"


def _make_minimal_patient() -> object:
    """Build a minimal PatientState for engine evaluation when no scenario exists."""
    from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns

    vitals = VitalSigns(
        heart_rate=80,
        blood_pressure_systolic=130,
        blood_pressure_diastolic=80,
        respiratory_rate=16,
        temperature=37.0,
        oxygen_saturation=98,
    )
    return PatientState(
        state_id="audit",
        age=55,
        sex="M",
        vitals=vitals,
        lab_results=[],
        imaging_results=[],
        medications_given=[],
        procedures_done=[],
        pending_orders=[],
        contraindications=[],
        allergies=[],
        comorbidities=[],
        chief_complaint="audit test",
        working_diagnosis=None,
        disposition_status=None,
    )


def run_c1_scorer_api_discovery() -> None:
    """C.1: Scorer API discovery — print available classes and init signatures."""
    print("=" * 60)
    print("C.1  Scorer API Discovery")
    print("=" * 60)

    try:
        from cga_bench.assessor_core import harm_scorer as hs_mod
        from cga_bench.assessor_core import violations as viol_mod

        print("\n--- assessor_core.violations ---")
        for name, _obj in inspect.getmembers(viol_mod, inspect.isclass):
            print(f"  class {name}")
        for name, _obj in inspect.getmembers(viol_mod, inspect.isfunction):
            print(f"  func  {name}")

        print(
            f"\n  ViolationExtractor.__init__ sig: "
            f"{inspect.signature(viol_mod.ViolationExtractor.__init__)}"
        )

        print("\n--- assessor_core.harm_scorer ---")
        for name, _obj in inspect.getmembers(hs_mod, inspect.isclass):
            print(f"  class {name}")
        for name, _obj in inspect.getmembers(hs_mod, inspect.isfunction):
            print(f"  func  {name}")

        print(
            f"\n  HarmScorer.__init__ sig: "
            f"{inspect.signature(hs_mod.HarmScorer.__init__)}"
        )

    except Exception:
        traceback.print_exc()


def _find_graph_yaml(graph_name: str) -> Path | None:
    """Locate the YAML file for a graph name."""
    exact = GRAPHS_DIR / f"{graph_name}.yaml"
    if exact.exists():
        return exact
    for p in GRAPHS_DIR.glob("*.yaml"):
        if graph_name in p.stem:
            return p
    return None


def run_c2_e2e_init() -> None:
    """C.2: E2E initialization for each held-out graph."""
    print("\n" + "=" * 60)
    print("C.2  E2E Initialization for Held-Out Graphs")
    print("=" * 60)

    from cga_bench.cpg_engine.engine import CPGEngineFactory
    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    loader = ScenarioLoader()
    all_scenarios = loader.load_all_scenarios()

    for graph_name in HELD_OUT_GRAPHS:
        print(f"\n--- {graph_name} ---")
        try:
            matched = {
                sid: s
                for sid, s in all_scenarios.items()
                if graph_name in s.guideline_graph or s.guideline_graph == graph_name
            }

            if matched:
                best_id = min(matched, key=lambda sid: len(matched[sid].expected_actions))
                scenario = matched[best_id]
                print(f"  Scenario: {best_id}  (expected_actions={len(scenario.expected_actions)})")

                graph_path = loader.get_cpg_graph_path(best_id)
                if graph_path is None:
                    graph_path = _find_graph_yaml(graph_name)

                if graph_path is None:
                    print(f"  FAIL: graph YAML not found for {graph_name}")
                    continue

                print(f"  Graph path: {graph_path}")
                engine = CPGEngineFactory.load_from_file(str(graph_path))
                engine.set_scenario_forbidden_actions(scenario.forbidden_actions or [])
                output = engine.evaluate(scenario.patient)

                print(f"  Allowed:   {len(output.allowed_actions)}")
                print(f"  Mandatory: {len(output.mandatory_actions)}")
                print(f"  Forbidden: {len(output.forbidden_actions)}")
                print(f"  Deadlines: {len(output.deadlines)}")
            else:
                print("  No scenarios found; loading engine directly")
                graph_path = _find_graph_yaml(graph_name)
                if graph_path is None:
                    print(f"  FAIL: graph YAML not found for {graph_name}")
                    continue

                print(f"  Graph path: {graph_path}")
                engine = CPGEngineFactory.load_from_file(str(graph_path))
                patient = _make_minimal_patient()
                output = engine.evaluate(patient)

                print(f"  Allowed:   {len(output.allowed_actions)}")
                print(f"  Mandatory: {len(output.mandatory_actions)}")
                print(f"  Forbidden: {len(output.forbidden_actions)}")
                print(f"  Deadlines: {len(output.deadlines)}")

        except Exception:
            traceback.print_exc()

    CPGEngineFactory.clear_cache()


def main() -> None:
    """Run all Section C audits."""
    print("Section C: Scoring + E2E Init Audit")
    print("=" * 60)
    run_c1_scorer_api_discovery()
    run_c2_e2e_init()
    print("\n" + "=" * 60)
    print("Section C complete.")


if __name__ == "__main__":
    main()
