"""Test 1.2: Expected actions derivation accuracy."""

from __future__ import annotations

from pathlib import Path

from cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
import pytest

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"


@pytest.fixture()
def engine() -> ConstraintDerivationEngine:
    return ConstraintDerivationEngine()


def test_dka_hypokalemia_activates_k_replacement(engine: ConstraintDerivationEngine) -> None:
    """K+ 2.9 -> potassium replacement expected, insulin forbidden."""
    graph = load_graph(GRAPHS_DIR / "ada_dka_management.yaml")
    patient = {
        "age": 28,
        "sex": "M",
        "labs": {"potassium": 2.9, "glucose": 450, "ph": 7.15, "bicarbonate": 8},
        "comorbidities": ["type_1_diabetes"],
        "allergies": [],
        "medications": [],
    }
    result = engine.derive(graph, patient)

    expected = [a for c in result.expected for a in c.actions]
    expected += [a for c in result.required for a in c.actions]

    assert any("potassium" in a for a in expected), f"Expected potassium-related action, got: {expected}"

    forbidden = [a for c in result.forbidden for a in c.actions]
    assert "start_insulin_infusion" in forbidden or "give_insulin_bolus" in forbidden


def test_dka_normal_k_activates_insulin(engine: ConstraintDerivationEngine) -> None:
    """K+ 4.2 -> insulin expected, no conditional insulin forbidden."""
    graph = load_graph(GRAPHS_DIR / "ada_dka_management.yaml")
    patient = {
        "age": 28,
        "sex": "M",
        "labs": {"potassium": 4.2, "glucose": 450, "ph": 7.15, "bicarbonate": 8},
        "comorbidities": ["type_1_diabetes"],
        "allergies": [],
        "medications": [],
    }
    result = engine.derive(graph, patient)

    expected = [a for c in result.expected for a in c.actions]
    expected += [a for c in result.required for a in c.actions]

    assert any("insulin" in a for a in expected), f"Expected insulin-related action, got: {expected}"

    # The K+-gated insulin rules (DKA-HYPOK-INSULIN-GATE) should NOT fire with K+=4.2
    # Note: DKA-INSULIN-BEFORE-K-CHECK (condition=True) always fires but targets
    # "start_insulin_before_k_check" which is a different action than "start_insulin_infusion"
    k_gated_insulin = [
        c
        for c in result.forbidden
        if c.is_conditional and ("start_insulin_infusion" in c.actions or "give_insulin_bolus" in c.actions)
    ]
    assert len(k_gated_insulin) == 0, (
        "start_insulin_infusion/give_insulin_bolus should not be conditionally forbidden with K+=4.2"
    )


def test_sepsis_penicillin_allergy_no_cephalosporin(engine: ConstraintDerivationEngine) -> None:
    """Penicillin anaphylaxis -> cephalosporin forbidden."""
    graph = load_graph(GRAPHS_DIR / "ssc_sepsis_hour1_bundle.yaml")
    patient = {
        "age": 55,
        "sex": "F",
        "labs": {"lactate": 4.5},
        "comorbidities": [],
        "allergies": ["penicillin_anaphylaxis"],
        "medications": [],
        "vitals": {"sbp": 80, "hr": 120},
    }
    result = engine.derive(graph, patient)
    forbidden = [a for c in result.forbidden for a in c.actions]

    assert "give_cephalosporin" in forbidden or "give_ceftriaxone" in forbidden, (
        f"Cephalosporin should be forbidden with penicillin anaphylaxis. Got: {forbidden}"
    )


@pytest.mark.skipif(
    not (GRAPHS_DIR / "anaphylaxis_management.yaml").exists(),
    reason="Anaphylaxis graph not found",
)
def test_anaphylaxis_beta_blocker_needs_glucagon(engine: ConstraintDerivationEngine) -> None:
    """Beta-blocker patient with anaphylaxis -> glucagon required."""
    graph = load_graph(GRAPHS_DIR / "anaphylaxis_management.yaml")
    patient = {
        "age": 60,
        "sex": "M",
        "comorbidities": [],
        "allergies": ["peanut"],
        "medications": ["beta_blocker"],
        "vitals": {"sbp": 70, "hr": 50},
    }
    result = engine.derive(graph, patient)
    required = [a for c in result.required for a in c.actions]

    assert "give_glucagon" in required, (
        f"Glucagon should be required for beta-blocker patient. Got required: {required}"
    )


def test_expected_not_empty_for_any_graph(engine: ConstraintDerivationEngine) -> None:
    """Every graph should produce at least some expected actions for a basic patient."""
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
        result = engine.derive(graph, patient)
        assert len(result.expected) > 0, f"{graph_path.name}: 0 expected actions for basic patient"
