"""Test 1.3: PatientGenerator accuracy - trigger patients trigger, normal patients don't."""

from __future__ import annotations

from pathlib import Path

from cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
from cpg_model.patient_generator import PatientGenerator, _collect_all_rules
import pytest

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"


@pytest.fixture()
def engine() -> ConstraintDerivationEngine:
    return ConstraintDerivationEngine()


@pytest.fixture()
def generator(engine: ConstraintDerivationEngine) -> PatientGenerator:
    return PatientGenerator(engine, seed=42)


def test_generated_trigger_patient_actually_triggers(
    engine: ConstraintDerivationEngine,
    generator: PatientGenerator,
) -> None:
    """Every trigger patient must actually fire its corresponding rule."""
    failures: list[str] = []

    for graph_path in sorted(GRAPHS_DIR.glob("*.yaml")):
        graph = load_graph(graph_path)
        rules = _collect_all_rules(graph)

        for rule in rules:
            trigger_patient = generator._make_trigger_scenario(rule, graph)
            if trigger_patient is None:
                continue

            result = engine.derive(graph, trigger_patient.patient)
            triggered_rule_ids = set()
            for c in result.all_constraints():
                if c.is_conditional and rule["rule_id"] in c.provenance:
                    triggered_rule_ids.add(rule["rule_id"])

            if rule["rule_id"] not in triggered_rule_ids:
                failures.append(
                    f"Rule {rule['rule_id']} NOT triggered by its trigger patient "
                    f"(graph: {graph.get('graph_id')}, "
                    f"condition: {rule['condition']})"
                )

    if failures:
        msg = f"{len(failures)} trigger patients failed to trigger their rule:\n"
        msg += "\n".join(f"  - {f}" for f in failures[:20])
        if len(failures) > 20:
            msg += f"\n  ... and {len(failures) - 20} more"
        pytest.fail(msg)


def test_generated_normal_patient_does_not_trigger(
    engine: ConstraintDerivationEngine,
    generator: PatientGenerator,
) -> None:
    """Normal patients must NOT fire their corresponding rule."""
    failures: list[str] = []

    for graph_path in sorted(GRAPHS_DIR.glob("*.yaml")):
        graph = load_graph(graph_path)
        rules = _collect_all_rules(graph)

        for rule in rules:
            normal_patient = generator._make_normal_scenario(rule, graph)
            if normal_patient is None:
                continue

            result = engine.derive(graph, normal_patient.patient)
            triggered = False
            for c in result.all_constraints():
                if c.is_conditional and rule["rule_id"] in c.provenance:
                    triggered = True
                    break

            if triggered:
                failures.append(
                    f"Rule {rule['rule_id']} triggered by NORMAL patient "
                    f"(graph: {graph.get('graph_id')}, "
                    f"condition: {rule['condition']})"
                )

    if failures:
        msg = f"{len(failures)} normal patients incorrectly triggered their rule:\n"
        msg += "\n".join(f"  - {f}" for f in failures[:20])
        if len(failures) > 20:
            msg += f"\n  ... and {len(failures) - 20} more"
        pytest.fail(msg)
