"""Test 2.3: Derivation determinism - same input always produces same output."""

from __future__ import annotations

from pathlib import Path

from cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"


def test_derivation_is_deterministic() -> None:
    engine = ConstraintDerivationEngine()
    graph = load_graph(GRAPHS_DIR / "ada_dka_management.yaml")
    patient = {
        "age": 28,
        "labs": {"potassium": 2.9, "glucose": 450, "ph": 7.15},
        "comorbidities": ["type_1_diabetes"],
        "allergies": [],
        "medications": [],
    }

    result1 = engine.derive(graph, patient, "test1")
    result2 = engine.derive(graph, patient, "test2")

    forbidden1 = sorted([a for c in result1.forbidden for a in c.actions])
    forbidden2 = sorted([a for c in result2.forbidden for a in c.actions])
    assert forbidden1 == forbidden2, "Forbidden derivation is non-deterministic!"

    expected1 = sorted([a for c in result1.expected for a in c.actions])
    expected2 = sorted([a for c in result2.expected for a in c.actions])
    assert expected1 == expected2, "Expected derivation is non-deterministic!"

    before1 = sorted([str(c.actions) for c in result1.before])
    before2 = sorted([str(c.actions) for c in result2.before])
    assert before1 == before2, "Before derivation is non-deterministic!"


def test_deterministic_across_all_graphs() -> None:
    """Verify determinism for every graph with a basic patient."""
    engine = ConstraintDerivationEngine()
    patient = {
        "age": 50,
        "sex": "M",
        "labs": {},
        "comorbidities": [],
        "allergies": [],
        "medications": [],
        "vitals": {},
        "history": [],
        "presentation": {},
    }

    for graph_path in GRAPHS_DIR.glob("*.yaml"):
        graph = load_graph(graph_path)
        r1 = engine.derive(graph, patient, "run1")
        r2 = engine.derive(graph, patient, "run2")

        f1 = sorted([a for c in r1.forbidden for a in c.actions])
        f2 = sorted([a for c in r2.forbidden for a in c.actions])
        assert f1 == f2, f"{graph_path.name}: forbidden non-deterministic"

        e1 = sorted([a for c in r1.expected for a in c.actions])
        e2 = sorted([a for c in r2.expected for a in c.actions])
        assert e1 == e2, f"{graph_path.name}: expected non-deterministic"
