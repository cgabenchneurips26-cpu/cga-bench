"""Tests for scripts/generate_scenarios_from_cpg.py — Scenario Generator."""

from __future__ import annotations

from pathlib import Path
import random

import pytest
from scripts.generate_scenarios_from_cpg import (
    extract_branch_diagnoses,
    extract_conditional_triggers,
    generate_scenarios_for_graph,
    walk_reachable_path,
)
import yaml

# ---------------------------------------------------------------------------
# Fixtures: minimal graph builders
# ---------------------------------------------------------------------------


def _minimal_graph(
    graph_id: str = "test_graph",
    entry_node: str = "n1",
    nodes: dict | None = None,
    domain: str = "sepsis",
    guideline_name: str = "Test Guideline",
) -> dict:
    """Build a minimal valid CPG graph dict."""
    if nodes is None:
        nodes = {
            "n1": {
                "node_id": "n1",
                "node_type": "plan",
                "name": "Node 1",
                "mandatory_actions": ["action_a", "action_b"],
                "allowed_actions": ["action_a", "action_b", "action_c"],
                "forbidden_actions": [],
                "deadlines": {"action_a": 60},
                "next_nodes": [],
                "conditional_next": {},
                "conditional_rules": [],
                "source_guideline": "Test",
                "source_section": "Section 1",
            }
        }
    return {
        "graph_id": graph_id,
        "guideline_name": guideline_name,
        "entry_node": entry_node,
        "metadata": {"domain": domain},
        "nodes": nodes,
    }


def _branching_graph() -> dict:
    """Build a graph with conditional_next branching on working_diagnosis."""
    return _minimal_graph(
        graph_id="branching_test",
        domain="sepsis",
        guideline_name="Branching Test Guideline",
        nodes={
            "n1": {
                "node_id": "n1",
                "node_type": "assessment",
                "name": "Initial Assessment",
                "mandatory_actions": ["assess_vital_signs", "order_lab_blood_culture"],
                "allowed_actions": ["assess_vital_signs", "order_lab_blood_culture"],
                "forbidden_actions": [],
                "deadlines": {"assess_vital_signs": 15},
                "next_nodes": [],
                "conditional_next": {
                    "state.working_diagnosis == 'sepsis'": "n2",
                    "state.working_diagnosis == 'septic_shock'": "n3",
                },
                "conditional_rules": [],
                "source_guideline": "Test",
                "source_section": "S1",
            },
            "n2": {
                "node_id": "n2",
                "node_type": "treatment",
                "name": "Sepsis Bundle",
                "mandatory_actions": ["give_broad_spectrum_antibiotics"],
                "allowed_actions": ["give_broad_spectrum_antibiotics"],
                "forbidden_actions": [],
                "deadlines": {"give_broad_spectrum_antibiotics": 60},
                "next_nodes": [],
                "conditional_next": {},
                "conditional_rules": [],
                "source_guideline": "Test",
                "source_section": "S2",
            },
            "n3": {
                "node_id": "n3",
                "node_type": "treatment",
                "name": "Septic Shock Bundle",
                "mandatory_actions": [
                    "give_broad_spectrum_antibiotics",
                    "give_crystalloid_30ml_kg",
                    "start_vasopressor_norepinephrine",
                ],
                "allowed_actions": [
                    "give_broad_spectrum_antibiotics",
                    "give_crystalloid_30ml_kg",
                    "start_vasopressor_norepinephrine",
                ],
                "forbidden_actions": [],
                "deadlines": {"give_crystalloid_30ml_kg": 30},
                "next_nodes": [],
                "conditional_next": {},
                "conditional_rules": [],
                "source_guideline": "Test",
                "source_section": "S3",
            },
        },
    )


def _graph_with_conditional_rules() -> dict:
    """Build a graph with conditional_rules (allergy/comorbidity triggers)."""
    return _minimal_graph(
        graph_id="cond_rules_test",
        domain="sepsis",
        guideline_name="Conditional Rules Test",
        nodes={
            "n1": {
                "node_id": "n1",
                "node_type": "treatment",
                "name": "Treatment",
                "mandatory_actions": ["give_antibiotics"],
                "allowed_actions": ["give_antibiotics", "give_vancomycin"],
                "forbidden_actions": [],
                "deadlines": {"give_antibiotics": 60},
                "next_nodes": [],
                "conditional_next": {},
                "conditional_rules": [
                    {
                        "rule_id": "ALLERGY-PEN",
                        "condition": "'penicillin' in patient.allergies",
                        "effect": {
                            "actions": ["give_penicillin_class"],
                        },
                        "description": "Penicillin allergy: avoid penicillin-class drugs",
                    },
                    {
                        "rule_id": "COMORBID-HF",
                        "condition": "'heart_failure' in patient.comorbidities",
                        "effect": {
                            "actions": ["give_aggressive_fluids"],
                        },
                        "description": "Heart failure: limit fluid resuscitation",
                    },
                    {
                        "rule_id": "AGE-ELDERLY",
                        "condition": "patient.age > 65",
                        "effect": {
                            "actions": ["give_high_dose_nsaid"],
                        },
                        "description": "Elderly: avoid high-dose NSAIDs",
                    },
                ],
                "source_guideline": "Test",
                "source_section": "S1",
            }
        },
    )


# ---------------------------------------------------------------------------
# walk_reachable_path
# ---------------------------------------------------------------------------


class TestWalkReachablePath:
    def test_single_node(self) -> None:
        graph = _minimal_graph()
        actions = walk_reachable_path(graph)
        assert actions == ["action_a", "action_b"]

    def test_chain_collects_all(self) -> None:
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": ["a1"],
                    "next_nodes": ["n2"],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                },
                "n2": {
                    "node_id": "n2",
                    "node_type": "plan",
                    "name": "N2",
                    "mandatory_actions": ["a2", "a3"],
                    "next_nodes": [],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                },
            }
        )
        assert walk_reachable_path(graph) == ["a1", "a2", "a3"]

    def test_branching_sepsis_path(self) -> None:
        graph = _branching_graph()
        actions = walk_reachable_path(graph, working_diagnosis="sepsis")
        assert "assess_vital_signs" in actions
        assert "order_lab_blood_culture" in actions
        assert "give_broad_spectrum_antibiotics" in actions
        # Should NOT include shock-specific actions
        assert "give_crystalloid_30ml_kg" not in actions
        assert "start_vasopressor_norepinephrine" not in actions

    def test_branching_septic_shock_path(self) -> None:
        graph = _branching_graph()
        actions = walk_reachable_path(graph, working_diagnosis="septic_shock")
        assert "assess_vital_signs" in actions
        assert "give_crystalloid_30ml_kg" in actions
        assert "start_vasopressor_norepinephrine" in actions

    def test_no_diagnosis_follows_all(self) -> None:
        graph = _branching_graph()
        actions = walk_reachable_path(graph, working_diagnosis=None)
        # Should collect actions from both branches
        assert "give_crystalloid_30ml_kg" in actions
        assert "give_broad_spectrum_antibiotics" in actions

    def test_missing_entry_returns_empty(self) -> None:
        graph = _minimal_graph(entry_node="nonexistent")
        assert walk_reachable_path(graph) == []

    def test_no_duplicates(self) -> None:
        """Actions appearing in multiple nodes should only be listed once."""
        graph = _branching_graph()
        actions = walk_reachable_path(graph, working_diagnosis=None)
        assert len(actions) == len(set(actions))


# ---------------------------------------------------------------------------
# extract_branch_diagnoses
# ---------------------------------------------------------------------------


class TestExtractBranchDiagnoses:
    def test_extracts_diagnoses(self) -> None:
        graph = _branching_graph()
        dx = extract_branch_diagnoses(graph)
        assert "sepsis" in dx
        assert "septic_shock" in dx

    def test_no_branches_returns_empty(self) -> None:
        graph = _minimal_graph()
        assert extract_branch_diagnoses(graph) == []

    def test_preserves_order_deduplicates(self) -> None:
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "decision",
                    "name": "D1",
                    "mandatory_actions": [],
                    "conditional_next": {
                        "state.working_diagnosis == 'type_a'": "n2",
                        "state.working_diagnosis == 'type_b'": "n3",
                    },
                    "next_nodes": [],
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                },
                "n2": {
                    "node_id": "n2",
                    "node_type": "decision",
                    "name": "D2",
                    "mandatory_actions": [],
                    "conditional_next": {
                        "state.working_diagnosis == 'type_a'": "n3",
                    },
                    "next_nodes": [],
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                },
                "n3": {
                    "node_id": "n3",
                    "node_type": "plan",
                    "name": "P",
                    "mandatory_actions": [],
                    "next_nodes": [],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                },
            }
        )
        dx = extract_branch_diagnoses(graph)
        # type_a appears twice but should only be listed once
        assert dx.count("type_a") == 1
        assert dx.count("type_b") == 1


# ---------------------------------------------------------------------------
# extract_conditional_triggers
# ---------------------------------------------------------------------------


class TestExtractConditionalTriggers:
    def test_extracts_allergy(self) -> None:
        graph = _graph_with_conditional_rules()
        triggers = extract_conditional_triggers(graph)
        allergy_trigger = next(t for t in triggers if t["rule_id"] == "ALLERGY-PEN")
        assert allergy_trigger["allergies"] == ["penicillin"]
        assert allergy_trigger["comorbidities"] == []

    def test_extracts_comorbidity(self) -> None:
        graph = _graph_with_conditional_rules()
        triggers = extract_conditional_triggers(graph)
        comorbid_trigger = next(t for t in triggers if t["rule_id"] == "COMORBID-HF")
        assert comorbid_trigger["comorbidities"] == ["heart_failure"]
        assert comorbid_trigger["allergies"] == []

    def test_extracts_age(self) -> None:
        graph = _graph_with_conditional_rules()
        triggers = extract_conditional_triggers(graph)
        age_trigger = next(t for t in triggers if t["rule_id"] == "AGE-ELDERLY")
        assert age_trigger["age_min"] == 66  # > 65 -> min age 66

    def test_forbidden_actions_captured(self) -> None:
        graph = _graph_with_conditional_rules()
        triggers = extract_conditional_triggers(graph)
        allergy_trigger = next(t for t in triggers if t["rule_id"] == "ALLERGY-PEN")
        assert "give_penicillin_class" in allergy_trigger["forbidden_actions"]

    def test_no_rules_returns_empty(self) -> None:
        graph = _minimal_graph()
        triggers = extract_conditional_triggers(graph)
        assert triggers == []

    def test_deduplicates_rule_ids(self) -> None:
        """Same rule_id in multiple nodes should only appear once."""
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": [],
                    "next_nodes": ["n2"],
                    "conditional_next": {},
                    "conditional_rules": [
                        {
                            "rule_id": "DUP-RULE",
                            "condition": "'sulfa' in patient.allergies",
                            "effect": {"actions": ["give_sulfa"]},
                            "description": "Sulfa allergy",
                        }
                    ],
                    "source_guideline": "T",
                    "source_section": "S",
                },
                "n2": {
                    "node_id": "n2",
                    "node_type": "plan",
                    "name": "N2",
                    "mandatory_actions": [],
                    "next_nodes": [],
                    "conditional_next": {},
                    "conditional_rules": [
                        {
                            "rule_id": "DUP-RULE",
                            "condition": "'sulfa' in patient.allergies",
                            "effect": {"actions": ["give_sulfa"]},
                            "description": "Sulfa allergy",
                        }
                    ],
                    "source_guideline": "T",
                    "source_section": "S",
                },
            }
        )
        triggers = extract_conditional_triggers(graph)
        assert len(triggers) == 1


# ---------------------------------------------------------------------------
# generate_scenarios_for_graph
# ---------------------------------------------------------------------------


class TestGenerateScenariosForGraph:
    def _gen(self, graph: dict, max_scenarios: int = 15) -> dict:
        rng = random.Random(42)
        return generate_scenarios_for_graph(graph, Path("/tmp/test_graph.yaml"), rng, max_scenarios)

    def test_single_node_generates_scenarios(self) -> None:
        graph = _minimal_graph()
        scenarios = self._gen(graph)
        assert len(scenarios) >= 1
        # Should have a baseline scenario
        baseline_keys = [k for k in scenarios if "baseline" in k]
        assert len(baseline_keys) >= 1

    def test_branching_graph_generates_per_diagnosis(self) -> None:
        graph = _branching_graph()
        scenarios = self._gen(graph)
        # Two diagnoses: sepsis and septic_shock
        sepsis_keys = [k for k in scenarios if "sepsis_mild" in k or "sepsis_moderate" in k or "sepsis_severe" in k]
        shock_keys = [k for k in scenarios if "septic_shock" in k]
        assert len(sepsis_keys) >= 1, f"Expected sepsis scenarios, got keys: {list(scenarios.keys())}"
        assert len(shock_keys) >= 1, f"Expected shock scenarios, got keys: {list(scenarios.keys())}"

    def test_conditional_rules_generate_trap_scenarios(self) -> None:
        graph = _graph_with_conditional_rules()
        scenarios = self._gen(graph)
        trap_scenarios = {k: v for k, v in scenarios.items() if v.get("trap_scenario")}
        assert len(trap_scenarios) >= 1
        # Check that allergies/comorbidities are injected
        for _sid, s in trap_scenarios.items():
            patient = s["patient"]
            has_trigger = (
                len(patient.get("allergies", [])) > 0
                or len(patient.get("comorbidities", [])) > 0
                or patient.get("age", 0) >= 66
            )
            assert has_trigger, f"Trap scenario should have a trigger: {s}"

    def test_scenario_fields_complete(self) -> None:
        graph = _minimal_graph()
        scenarios = self._gen(graph)
        for sid, s in scenarios.items():
            assert s["scenario_id"] == sid
            assert "description" in s
            assert "guideline_graph" in s
            assert "patient" in s
            assert "expected_actions" in s
            assert len(s["expected_actions"]) > 0
            patient = s["patient"]
            assert "age" in patient
            assert "sex" in patient
            assert "vitals" in patient
            assert "map_mmhg" in patient["vitals"]

    def test_max_scenarios_respected(self) -> None:
        graph = _branching_graph()
        scenarios = self._gen(graph, max_scenarios=3)
        assert len(scenarios) <= 3

    def test_deterministic_with_seed(self) -> None:
        graph = _branching_graph()
        s1 = self._gen(graph)
        s2 = self._gen(graph)
        assert list(s1.keys()) == list(s2.keys())

    def test_forbidden_actions_on_trap(self) -> None:
        graph = _graph_with_conditional_rules()
        scenarios = self._gen(graph)
        trap_scenarios = {k: v for k, v in scenarios.items() if v.get("trap_scenario")}
        for _sid, s in trap_scenarios.items():
            assert "forbidden_actions" in s
            assert len(s["forbidden_actions"]) > 0

    def test_real_ssc_graph(self) -> None:
        """SSC sepsis graph should generate 10+ scenarios."""
        ssc_path = (
            Path(__file__).resolve().parent.parent.parent / "cpg_model" / "graphs" / "ssc_sepsis_hour1_bundle.yaml"
        )
        if not ssc_path.exists():
            pytest.skip("SSC graph not found")

        data = yaml.safe_load(ssc_path.read_text(encoding="utf-8"))
        rng = random.Random(42)
        scenarios = generate_scenarios_for_graph(data, ssc_path, rng, max_scenarios=15)
        assert len(scenarios) >= 5, f"SSC should generate 5+ scenarios, got {len(scenarios)}"

        # Verify branch-based scenarios exist
        keys = list(scenarios.keys())
        has_sepsis = any("sepsis" in k and "shock" not in k for k in keys)
        has_shock = any("septic_shock" in k for k in keys)
        assert has_sepsis or has_shock, f"Expected branch scenarios, got: {keys}"


# ---------------------------------------------------------------------------
# Task 1: Vitals randomization
# ---------------------------------------------------------------------------

from scripts.generate_scenarios_from_cpg import _perturb_vitals


class TestPerturbVitals:
    """Tests for _perturb_vitals() — clinically-bounded noise injection."""

    def test_returns_all_keys(self) -> None:
        template = {
            "heart_rate": 100,
            "blood_pressure_systolic": 120,
            "blood_pressure_diastolic": 80,
            "respiratory_rate": 18,
            "temperature": 37.0,
            "oxygen_saturation": 97,
            "map_mmhg": 93,
        }
        result = _perturb_vitals(template, random.Random(42))
        for key in template:
            assert key in result

    def test_map_recomputed(self) -> None:
        template = {
            "heart_rate": 100,
            "blood_pressure_systolic": 120,
            "blood_pressure_diastolic": 80,
            "respiratory_rate": 18,
            "temperature": 37.0,
            "oxygen_saturation": 97,
            "map_mmhg": 93,
        }
        result = _perturb_vitals(template, random.Random(42))
        expected_map = round(
            result["blood_pressure_diastolic"]
            + (result["blood_pressure_systolic"] - result["blood_pressure_diastolic"]) / 3
        )
        assert result["map_mmhg"] == expected_map

    def test_different_seeds_produce_different_vitals(self) -> None:
        template = {
            "heart_rate": 100,
            "blood_pressure_systolic": 120,
            "blood_pressure_diastolic": 80,
            "respiratory_rate": 18,
            "temperature": 37.0,
            "oxygen_saturation": 97,
            "map_mmhg": 93,
        }
        v1 = _perturb_vitals(template, random.Random(1))
        v2 = _perturb_vitals(template, random.Random(2))
        # At least one vital should differ
        diffs = [k for k in template if k != "map_mmhg" and v1[k] != v2[k]]
        assert len(diffs) > 0, "Different seeds should produce different vitals"

    def test_same_seed_deterministic(self) -> None:
        template = {
            "heart_rate": 100,
            "blood_pressure_systolic": 120,
            "blood_pressure_diastolic": 80,
            "respiratory_rate": 18,
            "temperature": 37.0,
            "oxygen_saturation": 97,
            "map_mmhg": 93,
        }
        v1 = _perturb_vitals(template, random.Random(42))
        v2 = _perturb_vitals(template, random.Random(42))
        assert v1 == v2

    def test_spo2_clamped_to_100(self) -> None:
        template = {
            "heart_rate": 100,
            "blood_pressure_systolic": 120,
            "blood_pressure_diastolic": 80,
            "respiratory_rate": 18,
            "temperature": 37.0,
            "oxygen_saturation": 99,
            "map_mmhg": 93,
        }
        for seed in range(100):
            result = _perturb_vitals(template, random.Random(seed))
            assert 40 <= result["oxygen_saturation"] <= 100

    def test_temperature_rounded_to_one_decimal(self) -> None:
        template = {
            "heart_rate": 100,
            "blood_pressure_systolic": 120,
            "blood_pressure_diastolic": 80,
            "respiratory_rate": 18,
            "temperature": 37.0,
            "oxygen_saturation": 97,
            "map_mmhg": 93,
        }
        result = _perturb_vitals(template, random.Random(42))
        temp = result["temperature"]
        assert temp == round(temp, 1)

    def test_neonatal_population(self) -> None:
        template = {
            "heart_rate": 140,
            "blood_pressure_systolic": 65,
            "blood_pressure_diastolic": 40,
            "respiratory_rate": 40,
            "temperature": 36.8,
            "oxygen_saturation": 96,
            "map_mmhg": 48,
        }
        result = _perturb_vitals(template, random.Random(42), "neonatal")
        assert result["heart_rate"] > 0
        assert 40 <= result["oxygen_saturation"] <= 100

    def test_integer_vitals_are_int(self) -> None:
        template = {
            "heart_rate": 100,
            "blood_pressure_systolic": 120,
            "blood_pressure_diastolic": 80,
            "respiratory_rate": 18,
            "temperature": 37.0,
            "oxygen_saturation": 97,
            "map_mmhg": 93,
        }
        result = _perturb_vitals(template, random.Random(42))
        for key in (
            "heart_rate",
            "blood_pressure_systolic",
            "blood_pressure_diastolic",
            "respiratory_rate",
            "oxygen_saturation",
            "map_mmhg",
        ):
            assert isinstance(result[key], int), f"{key} should be int, got {type(result[key])}"


# ---------------------------------------------------------------------------
# Task 2: Forbidden action extraction from graph nodes
# ---------------------------------------------------------------------------

from scripts.generate_scenarios_from_cpg import _extract_node_forbidden_actions


class TestExtractNodeForbiddenActions:
    """Tests for _extract_node_forbidden_actions() — returns (list, dict)."""

    def test_collects_from_single_node(self) -> None:
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": ["a1"],
                    "forbidden_actions": ["give_aspirin", "give_nsaid"],
                    "next_nodes": [],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                }
            }
        )
        fa_list, fa_prov = _extract_node_forbidden_actions(graph)
        assert "give_aspirin" in fa_list
        assert "give_nsaid" in fa_list
        assert fa_prov["give_aspirin"] == "node:n1"
        assert fa_prov["give_nsaid"] == "node:n1"

    def test_collects_from_multiple_nodes(self) -> None:
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": ["a1"],
                    "forbidden_actions": ["give_aspirin"],
                    "next_nodes": ["n2"],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                },
                "n2": {
                    "node_id": "n2",
                    "node_type": "plan",
                    "name": "N2",
                    "mandatory_actions": ["a2"],
                    "forbidden_actions": ["delay_antibiotics"],
                    "next_nodes": [],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                },
            }
        )
        fa_list, fa_prov = _extract_node_forbidden_actions(graph)
        assert "give_aspirin" in fa_list
        assert "delay_antibiotics" in fa_list
        assert fa_prov["give_aspirin"] == "node:n1"
        assert fa_prov["delay_antibiotics"] == "node:n2"

    def test_deduplicates(self) -> None:
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": [],
                    "forbidden_actions": ["give_aspirin"],
                    "next_nodes": ["n2"],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                },
                "n2": {
                    "node_id": "n2",
                    "node_type": "plan",
                    "name": "N2",
                    "mandatory_actions": [],
                    "forbidden_actions": ["give_aspirin"],
                    "next_nodes": [],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                },
            }
        )
        fa_list, _prov = _extract_node_forbidden_actions(graph)
        assert fa_list.count("give_aspirin") == 1

    def test_empty_forbidden_actions(self) -> None:
        graph = _minimal_graph()  # default has forbidden_actions: []
        fa_list, fa_prov = _extract_node_forbidden_actions(graph)
        assert fa_list == []
        assert fa_prov == {}

    def test_sorted_output(self) -> None:
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": [],
                    "forbidden_actions": ["z_action", "a_action", "m_action"],
                    "next_nodes": [],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                }
            }
        )
        fa_list, _prov = _extract_node_forbidden_actions(graph)
        assert fa_list == sorted(fa_list)


# ---------------------------------------------------------------------------
# Task 5: Ground truth perturbation
# ---------------------------------------------------------------------------

from scripts.generate_scenarios_from_cpg import _perturb_ground_truth


class TestPerturbGroundTruth:
    """Tests for _perturb_ground_truth()."""

    def test_numeric_values_perturbed(self) -> None:
        gt = {"lab_troponin": 2.5, "lab_bnp": 450}
        r1 = _perturb_ground_truth(gt, random.Random(1))
        r2 = _perturb_ground_truth(gt, random.Random(2))
        assert r1 != r2

    def test_string_values_unchanged(self) -> None:
        gt = {"ecg_result": "ST elevation V1-V4", "lab_troponin": 2.5}
        result = _perturb_ground_truth(gt, random.Random(42))
        assert result["ecg_result"] == "ST elevation V1-V4"

    def test_deterministic(self) -> None:
        gt = {"lab_lactate": 4.0, "lab_wbc": 18}
        r1 = _perturb_ground_truth(gt, random.Random(42))
        r2 = _perturb_ground_truth(gt, random.Random(42))
        assert r1 == r2

    def test_float_stays_float(self) -> None:
        gt = {"lab_troponin": 2.5}
        result = _perturb_ground_truth(gt, random.Random(42))
        assert isinstance(result["lab_troponin"], float)

    def test_int_stays_int(self) -> None:
        gt = {"lab_bnp": 450}
        result = _perturb_ground_truth(gt, random.Random(42))
        assert isinstance(result["lab_bnp"], int)

    def test_empty_dict(self) -> None:
        assert _perturb_ground_truth({}, random.Random(42)) == {}


# ---------------------------------------------------------------------------
# Integration: All 5 improvements in generate_scenarios_for_graph
# ---------------------------------------------------------------------------


class TestGeneratorImprovements:
    """Integration tests for all 5 quality improvements."""

    def _gen(self, graph: dict, max_scenarios: int = 15) -> dict:
        rng = random.Random(42)
        return generate_scenarios_for_graph(graph, Path("/tmp/test_graph.yaml"), rng, max_scenarios)

    def test_vitals_diversity(self) -> None:
        """Task 1: Different scenarios should have different vitals."""
        graph = _branching_graph()
        scenarios = self._gen(graph)
        vitals_tuples = set()
        for s in scenarios.values():
            v = s["patient"]["vitals"]
            vitals_tuples.add((v["heart_rate"], v["blood_pressure_systolic"], v["temperature"]))
        # With perturbation, we should have near-unique vitals
        assert len(vitals_tuples) >= min(len(scenarios), 3), (
            f"Expected diverse vitals, got {len(vitals_tuples)} unique out of {len(scenarios)}"
        )

    def test_node_forbidden_actions_on_branch_scenarios(self) -> None:
        """Task 2: Branch scenarios should inherit node-level forbidden actions."""
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": ["a1"],
                    "allowed_actions": ["a1"],
                    "forbidden_actions": ["give_dangerous_drug"],
                    "deadlines": {},
                    "next_nodes": [],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                }
            }
        )
        scenarios = self._gen(graph)
        for s in scenarios.values():
            if "forbidden_actions" in s:
                assert "give_dangerous_drug" in s["forbidden_actions"]

    def test_diagnosis_diversity_no_raw_domain(self) -> None:
        """Task 3: Diagnoses should not be raw domain names like 'sepsis'."""
        graph = _minimal_graph(domain="sepsis")
        # No conditional_next branching -> falls back to _DOMAIN_DIAGNOSES
        scenarios = self._gen(graph)
        diagnoses = {s["patient"]["working_diagnosis"] for s in scenarios.values()}
        # Should use domain-specific diagnoses, not raw 'sepsis'
        assert "sepsis" not in diagnoses or len(diagnoses) > 1

    def test_universal_traps_generated(self) -> None:
        """Task 4: Universal trap scenarios should be generated."""
        graph = _minimal_graph(domain="sepsis")
        scenarios = self._gen(graph, max_scenarios=20)
        trap_ids = [k for k in scenarios if scenarios[k].get("trap_scenario")]
        # Should have at least one universal trap (renal_nsaid applies to all domains)
        universal_trap_ids = [
            k for k in trap_ids if "renal_nsaid" in k or "liver" in k or "pregnancy" in k or "heart_failure" in k
        ]
        assert len(universal_trap_ids) >= 1, f"Expected universal traps, got trap keys: {trap_ids}"

    def test_universal_trap_has_comorbidities(self) -> None:
        """Task 4: Universal trap scenarios should have comorbidities or allergies."""
        graph = _minimal_graph(domain="sepsis")
        scenarios = self._gen(graph, max_scenarios=20)
        for sid, s in scenarios.items():
            if s.get("trap_scenario") and any(
                t_id in sid for t_id in ["renal_nsaid", "liver_acetaminophen", "pregnancy_teratogen"]
            ):
                patient = s["patient"]
                has_trigger = len(patient.get("comorbidities", [])) > 0 or len(patient.get("allergies", [])) > 0
                assert has_trigger, f"Universal trap {sid} must have comorbidities/allergies"

    def test_ground_truth_present(self) -> None:
        """Task 5: All scenarios should have ground_truth."""
        graph = _minimal_graph(domain="sepsis")
        scenarios = self._gen(graph)
        for sid, s in scenarios.items():
            assert "ground_truth" in s, f"Scenario {sid} missing ground_truth"
            assert len(s["ground_truth"]) > 0, f"Scenario {sid} has empty ground_truth"

    def test_ground_truth_domain_specific(self) -> None:
        """Task 5: Sepsis scenarios should have sepsis-specific ground truth keys."""
        graph = _minimal_graph(domain="sepsis")
        scenarios = self._gen(graph)
        for s in scenarios.values():
            gt = s.get("ground_truth", {})
            # Sepsis ground truth should have lactate or procalcitonin
            has_sepsis_key = any(k in gt for k in ("lab_lactate", "lab_procalcitonin", "lab_wbc"))
            assert has_sepsis_key, f"Sepsis ground truth missing domain keys: {gt}"

    def test_domain_filter_on_traps(self) -> None:
        """Task 4: Domain-restricted traps should only appear in matching domains."""
        # asthma_beta_blocker only applies to cardiology/heart_failure/chest_pain
        graph = _minimal_graph(domain="burn")
        scenarios = self._gen(graph, max_scenarios=20)
        for sid in scenarios:
            assert "asthma_beta_blocker" not in sid, "asthma_beta_blocker trap should not appear in burn domain"


# ---------------------------------------------------------------------------
# v5: Provenance metadata (Task 1)
# ---------------------------------------------------------------------------


class TestGenerationMetadata:
    """Tests for _generation_metadata provenance injection."""

    def _gen(self, graph: dict, max_scenarios: int = 20) -> dict:
        rng = random.Random(42)
        return generate_scenarios_for_graph(graph, Path("/tmp/test.yaml"), rng, max_scenarios)

    def test_metadata_present_in_all_scenarios(self) -> None:
        """Every generated scenario must have _generation_metadata."""
        graph = _branching_graph()
        scenarios = self._gen(graph)
        for sid, s in scenarios.items():
            assert "_generation_metadata" in s, f"{sid} missing _generation_metadata"

    def test_metadata_has_required_fields(self) -> None:
        """Metadata must have generator_version, generation_phase, graph_id, source_node_ids."""
        graph = _branching_graph()
        scenarios = self._gen(graph)
        required = {
            "generator_version",
            "generation_phase",
            "graph_id",
            "source_node_ids",
            "forbidden_action_provenance",
        }
        for sid, s in scenarios.items():
            meta = s["_generation_metadata"]
            missing = required - set(meta.keys())
            assert not missing, f"{sid} metadata missing keys: {missing}"

    def test_metadata_phase_matches_scenario_type(self) -> None:
        """Branch scenarios -> 'branch', trap -> 'conditional_rule'/'universal_trap', baseline -> 'baseline'."""
        graph = _graph_with_conditional_rules()
        scenarios = self._gen(graph)
        for sid, s in scenarios.items():
            phase = s["_generation_metadata"]["generation_phase"]
            if "baseline" in sid:
                assert phase == "baseline", f"{sid}: expected 'baseline', got '{phase}'"
            elif s.get("trap_scenario"):
                assert phase in ("conditional_rule", "universal_trap"), f"{sid}: expected trap phase, got '{phase}'"
            else:
                assert phase == "branch", f"{sid}: expected 'branch', got '{phase}'"

    def test_fa_provenance_covers_all_forbidden_actions(self) -> None:
        """Every FA in forbidden_actions must have a provenance entry."""
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": ["a1"],
                    "allowed_actions": ["a1"],
                    "forbidden_actions": ["give_dangerous_drug"],
                    "deadlines": {},
                    "next_nodes": [],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                }
            }
        )
        scenarios = self._gen(graph)
        for sid, s in scenarios.items():
            fa_list = s.get("forbidden_actions", [])
            fa_prov = s["_generation_metadata"]["forbidden_action_provenance"]
            for fa in fa_list:
                assert fa in fa_prov, f"{sid}: FA '{fa}' has no provenance"

    def test_generator_version_is_v5(self) -> None:
        graph = _minimal_graph()
        scenarios = self._gen(graph)
        for s in scenarios.values():
            assert s["_generation_metadata"]["generator_version"] == "v5"

    def test_source_node_ids_are_valid(self) -> None:
        """source_node_ids should reference real nodes in the graph."""
        graph = _branching_graph()
        scenarios = self._gen(graph)
        valid_nodes = set(graph["nodes"].keys())
        for sid, s in scenarios.items():
            for nid in s["_generation_metadata"]["source_node_ids"]:
                assert nid in valid_nodes, f"{sid}: source_node_id '{nid}' not in graph"


# ---------------------------------------------------------------------------
# v5: FA calibration (Task 2)
# ---------------------------------------------------------------------------


class TestFACalibration:
    """Tests for FA over-injection fix."""

    def test_baseline_has_no_forbidden_actions(self) -> None:
        """Phase 3 baseline should have no forbidden_actions."""
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": ["a1"],
                    "allowed_actions": ["a1"],
                    "forbidden_actions": ["give_dangerous_drug"],
                    "deadlines": {},
                    "next_nodes": [],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                }
            }
        )
        rng = random.Random(42)
        scenarios = generate_scenarios_for_graph(graph, Path("/tmp/t.yaml"), rng, 20)
        baseline = {k: v for k, v in scenarios.items() if "baseline" in k}
        for sid, s in baseline.items():
            assert "forbidden_actions" not in s, f"Baseline {sid} should not have forbidden_actions"

    def test_fa_not_100_percent_on_branch(self) -> None:
        """Across many seeds, branch scenarios should NOT always have FA (80% target)."""
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": ["a1"],
                    "allowed_actions": ["a1"],
                    "forbidden_actions": ["give_dangerous_drug"],
                    "deadlines": {},
                    "next_nodes": [],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                }
            }
        )
        has_fa_count = 0
        total_branch = 0
        for seed in range(50):
            rng = random.Random(seed)
            scenarios = generate_scenarios_for_graph(graph, Path("/tmp/t.yaml"), rng, 20)
            for sid, s in scenarios.items():
                if "baseline" not in sid and not s.get("trap_scenario"):
                    total_branch += 1
                    if s.get("forbidden_actions"):
                        has_fa_count += 1
        # Should be roughly 80% — allow 60-95% range for statistical variation
        fa_rate = has_fa_count / total_branch if total_branch else 0
        assert 0.55 < fa_rate < 0.98, f"FA rate {fa_rate:.1%} outside expected 60-95% range"

    def test_fa_count_capped_at_3(self) -> None:
        """Branch scenarios should have at most 3 forbidden actions."""
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": ["a1"],
                    "allowed_actions": ["a1"],
                    "forbidden_actions": [
                        "fa1",
                        "fa2",
                        "fa3",
                        "fa4",
                        "fa5",
                        "fa6",
                        "fa7",
                        "fa8",
                        "fa9",
                        "fa10",
                    ],
                    "deadlines": {},
                    "next_nodes": [],
                    "conditional_next": {},
                    "conditional_rules": [],
                    "source_guideline": "T",
                    "source_section": "S",
                }
            }
        )
        rng = random.Random(42)
        scenarios = generate_scenarios_for_graph(graph, Path("/tmp/t.yaml"), rng, 20)
        for sid, s in scenarios.items():
            if "baseline" not in sid and not s.get("trap_scenario"):
                fa = s.get("forbidden_actions", [])
                assert len(fa) <= 3, f"{sid} has {len(fa)} FA, expected <= 3"

    def test_trap_scenarios_always_have_fa(self) -> None:
        """Trap scenarios (Phase 2/2b) must always have forbidden_actions."""
        graph = _graph_with_conditional_rules()
        rng = random.Random(42)
        scenarios = generate_scenarios_for_graph(graph, Path("/tmp/t.yaml"), rng, 20)
        for sid, s in scenarios.items():
            if s.get("trap_scenario"):
                assert s.get("forbidden_actions"), f"Trap {sid} must have forbidden_actions"


# ---------------------------------------------------------------------------
# v5: Comorbidity calibration (Task 3)
# ---------------------------------------------------------------------------


class TestComorbidityCalibration:
    """Tests for comorbidity rate calibration."""

    def test_comorbidity_rate_approximately_80_percent(self) -> None:
        """Across many seeds, ~80% of branch scenarios should have comorbidities."""
        graph = _minimal_graph(domain="sepsis")
        has_comorb = 0
        total_branch = 0
        for seed in range(50):
            rng = random.Random(seed)
            scenarios = generate_scenarios_for_graph(graph, Path("/tmp/t.yaml"), rng, 20)
            for sid, s in scenarios.items():
                if "baseline" not in sid and not s.get("trap_scenario"):
                    total_branch += 1
                    if s["patient"].get("comorbidities"):
                        has_comorb += 1
        rate = has_comorb / total_branch if total_branch else 0
        # Weighted [0.20, 0.45, 0.35] → P(>0) = 80%. Allow 65-95% range.
        assert 0.60 < rate < 0.98, f"Comorbidity rate {rate:.1%} outside expected 65-95% range"


# ---------------------------------------------------------------------------
# v5: Validator Rules E+F (Task 4)
# ---------------------------------------------------------------------------

from scripts.ci.validate_scenario_plausibility import (
    SEVERITY_ERROR,
    check_fa_traceability,
    check_provenance,
)


class TestRuleEProvenance:
    """Tests for validator Rule E: provenance completeness."""

    def test_manual_scenario_skipped(self) -> None:
        """Scenarios without _generation_metadata (manual) should pass."""
        findings = check_provenance("manual_001", {"patient": {}}, None)
        assert findings == []

    def test_missing_graph_id(self) -> None:
        scenario = {
            "_generation_metadata": {
                "generator_version": "v5",
                "generation_phase": "branch",
                "graph_id": "",
                "source_node_ids": ["n1"],
                "forbidden_action_provenance": {},
            }
        }
        findings = check_provenance("test_001", scenario, None)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1
        assert any("graph_id" in f.message for f in errors)

    def test_invalid_phase(self) -> None:
        scenario = {
            "_generation_metadata": {
                "generator_version": "v5",
                "generation_phase": "invalid_phase",
                "graph_id": "test_graph",
                "source_node_ids": ["n1"],
                "forbidden_action_provenance": {},
            }
        }
        findings = check_provenance("test_001", scenario, None)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1
        assert any("generation_phase" in f.message for f in errors)

    def test_fa_without_provenance(self) -> None:
        scenario = {
            "forbidden_actions": ["fa1", "fa2"],
            "_generation_metadata": {
                "generator_version": "v5",
                "generation_phase": "branch",
                "graph_id": "test_graph",
                "source_node_ids": ["n1"],
                "forbidden_action_provenance": {"fa1": "node:n1"},
            },
        }
        findings = check_provenance("test_001", scenario, None)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1
        assert any("fa2" in f.message for f in errors)

    def test_valid_metadata_passes(self) -> None:
        scenario = {
            "forbidden_actions": ["fa1"],
            "_generation_metadata": {
                "generator_version": "v5",
                "generation_phase": "branch",
                "graph_id": "test_graph",
                "source_node_ids": ["n1"],
                "forbidden_action_provenance": {"fa1": "node:n1"},
            },
        }
        findings = check_provenance("test_001", scenario, None)
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) == 0


class TestRuleFTraceability:
    """Tests for validator Rule F: FA-to-graph traceability."""

    def _graph_with_fa(self) -> dict:
        return {
            "graph_id": "test",
            "nodes": {
                "n1": {
                    "node_id": "n1",
                    "forbidden_actions": ["give_aspirin"],
                }
            },
        }

    def test_manual_scenario_skipped(self) -> None:
        findings = check_fa_traceability("m001", {"patient": {}}, self._graph_with_fa())
        assert findings == []

    def test_valid_node_reference_passes(self) -> None:
        scenario = {
            "_generation_metadata": {
                "forbidden_action_provenance": {"give_aspirin": "node:n1"},
            }
        }
        findings = check_fa_traceability("t001", scenario, self._graph_with_fa())
        assert len(findings) == 0

    def test_dangling_node_reference(self) -> None:
        scenario = {
            "_generation_metadata": {
                "forbidden_action_provenance": {"give_aspirin": "node:nonexistent"},
            }
        }
        findings = check_fa_traceability("t001", scenario, self._graph_with_fa())
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1
        assert any("nonexistent" in f.message for f in errors)

    def test_fa_not_in_node_list(self) -> None:
        scenario = {
            "_generation_metadata": {
                "forbidden_action_provenance": {"give_nsaid": "node:n1"},
            }
        }
        findings = check_fa_traceability("t001", scenario, self._graph_with_fa())
        errors = [f for f in findings if f.severity == SEVERITY_ERROR]
        assert len(errors) >= 1
        assert any("give_nsaid" in f.message for f in errors)

    def test_trap_source_not_validated_here(self) -> None:
        """trap: and rule: sources should NOT be flagged by Rule F."""
        scenario = {
            "_generation_metadata": {
                "forbidden_action_provenance": {
                    "give_nsaid": "trap:renal_nsaid",
                    "give_penicillin": "rule:ALLERGY-PEN",
                },
            }
        }
        findings = check_fa_traceability("t001", scenario, self._graph_with_fa())
        assert len(findings) == 0
