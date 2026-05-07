"""Golden test case loader - reads per-domain subdirectories."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

CASES_DIR = Path(__file__).parent

# Map patient fixture names to domain-qualified keys used in conftest
_PATIENT_REGISTRY: dict[str, str] = {
    "sepsis_patient": "sepsis_patient",
    "chest_pain_patient": "chest_pain_patient",
    "dka_patient": "dka_patient",
    "aki_patient": "aki_patient",
    "stroke_patient": "stroke_patient",
    "heart_failure_patient": "heart_failure_patient",
}

_ACTION_TYPE_MAP: dict[str, str] = {
    "PROCEDURE": "PROCEDURE",
    "DISPOSITION": "DISPOSITION",
    "MEDICATION": "MEDICATION",
    "LAB": "LAB",
    "IMAGING": "IMAGING",
}


def _load_actions(episode_path: Path) -> list[dict[str, Any]]:
    with open(episode_path, encoding="utf-8") as f:
        data = json.load(f)
    return data["actions"]


def load_cases_from_dir() -> list[dict[str, Any]]:
    """Discover and load all golden cases from the cases/ directory tree.

    Each case directory must contain:
        scenario.yaml  - metadata (id, graph_file, node, patient, finals, citation, expected_violation_type)
        episode_A.json - A-side actions
        episode_B.json - B-side actions

    Returns a list of case dicts compatible with the existing CASES format.
    """
    from tests.test_golden.conftest import (  # imported lazily to avoid circular deps
        _action,
        aki_patient,
        chest_pain_patient,
        dka_patient,
        heart_failure_patient,
        sepsis_patient,
        stroke_patient,
    )
    from cga_bench.cpg_model.schemas.base import ActionType

    patient_map = {
        "sepsis_patient": sepsis_patient,
        "chest_pain_patient": chest_pain_patient,
        "dka_patient": dka_patient,
        "aki_patient": aki_patient,
        "stroke_patient": stroke_patient,
        "heart_failure_patient": heart_failure_patient,
    }

    cases: list[dict[str, Any]] = []

    for scenario_file in sorted(CASES_DIR.rglob("scenario.yaml")):
        case_dir = scenario_file.parent
        with open(scenario_file, encoding="utf-8") as f:
            meta = yaml.safe_load(f)

        a_actions_raw = _load_actions(case_dir / "episode_A.json")
        b_actions_raw = _load_actions(case_dir / "episode_B.json")

        def _build_actions(raw: list[dict[str, Any]]) -> list[Any]:
            result = []
            for entry in raw:
                atype_str = entry.get("action_type", "PROCEDURE")
                atype = ActionType[atype_str]
                result.append(
                    _action(
                        entry["action_id"],
                        float(entry["timestamp_minutes"]),
                        atype,
                    )
                )
            return result

        cases.append(
            {
                "id": meta["id"],
                "citation": meta["citation"],
                "graph": meta["graph_file"],
                "node": meta["node"],
                "patient": patient_map[meta["patient"]],
                "a_actions": _build_actions(a_actions_raw),
                "b_actions": _build_actions(b_actions_raw),
                "a_final": float(meta["a_final"]),
                "b_final": float(meta["b_final"]),
                "expected": meta["expected_violation_type"],
            }
        )

    return cases
