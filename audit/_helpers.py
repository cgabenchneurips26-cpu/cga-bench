"""Shared helpers for audit scripts.

Provides raw YAML scenario loading that preserves fields not captured
by ScenarioDefinition (generation_method, triggered_rules, raw patient dict).
"""

from pathlib import Path
from typing import Any

import yaml

SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"
GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"


def load_raw_scenarios() -> list[dict[str, Any]]:
    """Load all scenarios as raw dicts from YAML files.

    Returns list of dicts, each with at minimum:
      scenario_id, guideline_graph, patient (raw dict), expected_actions,
      forbidden_actions, trap_scenario, generation_method, triggered_rules,
      _source_file
    """
    results: list[dict[str, Any]] = []
    for path in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        if not data or "scenarios" not in data:
            continue
        for sid, cfg in data["scenarios"].items():
            cfg["scenario_id"] = sid
            cfg["_source_file"] = path.name
            cfg.setdefault("trap_scenario", False)
            cfg.setdefault("generation_method", "manual")
            cfg.setdefault("triggered_rules", [])
            cfg.setdefault("expected_actions", [])
            cfg.setdefault("forbidden_actions", [])
            cfg.setdefault("guideline_graph", "")
            results.append(cfg)
    return results


def load_graph(graph_id: str) -> dict[str, Any] | None:
    """Load a graph YAML by graph_id, searching all files."""
    for path in GRAPHS_DIR.glob("*.yaml"):
        with open(path) as f:
            g = yaml.safe_load(f)
        if g and g.get("graph_id") == graph_id:
            return g
    return None


def graph_id_to_path(graph_id: str) -> Path | None:
    """Find the file path for a graph_id."""
    for path in GRAPHS_DIR.glob("*.yaml"):
        with open(path) as f:
            g = yaml.safe_load(f)
        if g and g.get("graph_id") == graph_id:
            return path
    return None


def patient_to_eval_dict(raw_patient: dict[str, Any]) -> dict[str, Any]:
    """Convert raw YAML patient dict to format expected by _evaluate_condition.

    The condition evaluator expects dot-notation access like
    patient.labs.potassium, patient.comorbidities, etc.
    """
    return dict(raw_patient)
