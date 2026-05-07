"""Tests for scripts/sgsc/analyze_representativeness.py.

Covers all 8 stratification axes plus the run_analysis contract.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "sgsc" / "analyze_representativeness.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("analyze_representativeness", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(tmp_path: Path, guidelines: list[dict]) -> Path:
    data = {"version": "sgsc_pilot_v1", "guidelines": guidelines}
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(data))
    return p


def _guideline_entry(
    gid: str,
    domain: str = "sepsis",
    held_out: bool = False,
) -> dict:
    return {
        "guideline_id": gid,
        "guideline_name": gid,
        "corpus_file": "x.json",
        "graph_file": "x.yaml",
        "category": "breadth",
        "conflict_pattern": None,
        "tier": None,
        "held_out": held_out,
        "domain": domain,
    }


# ---------------------------------------------------------------------------
# TestDomainDistribution (Axis 1)
# ---------------------------------------------------------------------------


class TestDomainDistribution:
    def test_domain_counts(self, mod) -> None:
        entries = [
            _guideline_entry("g1", domain="sepsis"),
            _guideline_entry("g2", domain="stroke"),
            _guideline_entry("g3", domain="sepsis"),
        ]
        result = mod._axis_domain(entries)
        assert result["domain_distribution"] == {"sepsis": 2, "stroke": 1}

    def test_domain_count_metric(self, mod) -> None:
        entries = [
            _guideline_entry("g1", domain="sepsis"),
            _guideline_entry("g2", domain="stroke"),
            _guideline_entry("g3", domain="sepsis"),
        ]
        result = mod._axis_domain(entries)
        assert result["domain_count"] == 2


# ---------------------------------------------------------------------------
# TestConstraintTypeDistribution (Axis 2)
# ---------------------------------------------------------------------------


class TestConstraintTypeDistribution:
    def test_with_constraints_json(self, mod, tmp_path: Path) -> None:
        gid = "test_sepsis"
        gdir = tmp_path / gid
        gdir.mkdir()
        constraints = [
            {"constraint_type": "REQUIRED", "actions": ["a1"]},
            {"constraint_type": "FORBIDDEN", "actions": ["a2"]},
            {"constraint_type": "REQUIRED", "actions": ["a3"]},
        ]
        (gdir / f"{gid}_constraints.json").write_text(json.dumps(constraints))

        entries = [_guideline_entry(gid)]
        result = mod._axis_constraint_type(entries, tmp_path)

        assert result["constraint_type_distribution"]["REQUIRED"] == 2
        assert result["constraint_type_distribution"]["FORBIDDEN"] == 1
        assert result["total_constraints_loaded"] == 3
        assert result["guidelines_missing_constraints"] == 0

    def test_missing_constraints_file(self, mod, tmp_path: Path) -> None:
        # No file written — directory doesn't even exist
        entries = [_guideline_entry("no_such_guideline")]
        result = mod._axis_constraint_type(entries, tmp_path)

        assert result["total_constraints_loaded"] == 0
        assert result["guidelines_missing_constraints"] == 1
        assert result["constraint_type_distribution"] == {}


# ---------------------------------------------------------------------------
# TestConditionality (Axis 3)
# ---------------------------------------------------------------------------


class TestConditionality:
    def test_guarded_atoms(self, mod, tmp_path: Path) -> None:
        gid = "test_aki"
        gdir = tmp_path / gid
        gdir.mkdir()
        atoms = [
            {
                "atom_id": "a1",
                "action": {"action_id": "x"},
                "guard": {"field": "lactate", "operator": ">", "value": 2.0},
            },
            {
                "atom_id": "a2",
                "action": {"action_id": "y"},
                "guard": {"field": "map_mmhg", "operator": "<", "value": 65},
            },
            {
                "atom_id": "a3",
                "action": {"action_id": "z"},
                "guard": None,
            },
        ]
        (gdir / "atoms_smoke.json").write_text(json.dumps(atoms))

        entries = [_guideline_entry(gid)]
        result = mod._axis_conditionality(entries, tmp_path)

        assert result["total_atoms"] == 3
        assert result["guarded_atom_count"] == 2
        assert result["guarded_atom_pct"] == pytest.approx(66.7, abs=0.1)

    def test_no_atoms_file(self, mod, tmp_path: Path) -> None:
        entries = [_guideline_entry("missing_atoms_guideline")]
        result = mod._axis_conditionality(entries, tmp_path)

        assert result["total_atoms"] == 0
        assert result["guarded_atom_count"] == 0
        assert result["guarded_atom_pct"] == 0.0


# ---------------------------------------------------------------------------
# TestScenarioYield (Axis 7)
# ---------------------------------------------------------------------------


class TestScenarioYield:
    def test_yield_calculation(self, mod, tmp_path: Path) -> None:
        gid = "test_hf"
        gdir = tmp_path / gid
        gdir.mkdir()

        atoms = [{"atom_id": f"a{i}", "action": {"action_id": f"act_{i}"}} for i in range(5)]
        (gdir / "atoms_smoke.json").write_text(json.dumps(atoms))

        scenarios = {f"seed_{i:03d}": {"scenario_id": f"seed_{i:03d}"} for i in range(10)}
        (gdir / f"{gid}_scenarios.json").write_text(json.dumps(scenarios))

        entries = [_guideline_entry(gid)]
        result = mod._axis_scenario_yield(entries, tmp_path)

        per = result["per_guideline_yield"]
        assert len(per) == 1
        assert per[0]["scenarios"] == 10
        assert per[0]["atoms"] == 5
        assert per[0]["yield"] == pytest.approx(2.0)
        assert result["avg_yield"] == pytest.approx(2.0)

    def test_yield_no_atoms(self, mod, tmp_path: Path) -> None:
        gid = "test_zero_atoms"
        gdir = tmp_path / gid
        gdir.mkdir()

        # No atoms file written at all
        scenarios = {f"seed_{i:03d}": {"scenario_id": f"seed_{i:03d}"} for i in range(10)}
        (gdir / f"{gid}_scenarios.json").write_text(json.dumps(scenarios))

        entries = [_guideline_entry(gid)]
        result = mod._axis_scenario_yield(entries, tmp_path)

        per = result["per_guideline_yield"]
        assert per[0]["atoms"] == 0
        assert per[0]["yield"] == 0.0
        assert result["avg_yield"] == 0.0


# ---------------------------------------------------------------------------
# TestRunAnalysis — contract shape
# ---------------------------------------------------------------------------


def _build_minimal_sgsc(tmp_path: Path, gid: str) -> None:
    """Populate tmp_path/{gid}/ with all expected SGSC artifacts."""
    gdir = tmp_path / gid
    gdir.mkdir(parents=True, exist_ok=True)

    constraints = [
        {"constraint_type": "REQUIRED", "actions": ["a1"]},
        {"constraint_type": "FORBIDDEN", "actions": ["a2"]},
    ]
    (gdir / f"{gid}_constraints.json").write_text(json.dumps(constraints))

    atoms = [
        {
            "atom_id": "a1",
            "action": {"action_id": "x"},
            "guard": {"field": "lactate", "operator": ">", "value": 2.0},
        },
        {
            "atom_id": "a2",
            "action": {"action_id": "y"},
            "guard": None,
        },
    ]
    (gdir / "atoms_smoke.json").write_text(json.dumps(atoms))

    scenarios = {"seed_001": {"scenario_id": "seed_001"}, "seed_002": {"scenario_id": "seed_002"}}
    (gdir / f"{gid}_scenarios.json").write_text(json.dumps(scenarios))

    graph = {"nodes": [{"node_id": "n1", "auto_transition_conditions": []}]}
    (gdir / f"{gid}_graph.json").write_text(json.dumps(graph))


class TestRunAnalysis:
    def test_full_run_produces_contract(self, mod, tmp_path: Path) -> None:
        gid = "test_sepsis"
        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        _build_minimal_sgsc(sgsc_dir, gid)

        registry_path = _make_registry(tmp_path, [_guideline_entry(gid)])
        output_dir = tmp_path / "out"

        report = mod.run_analysis(registry_path, output_dir, sgsc_dir)

        required_keys = {"check_name", "status", "commit", "input_hash", "output_hash", "metrics", "failures"}
        assert required_keys.issubset(report.keys())
        assert report["check_name"] == "representativeness_analysis"
        assert report["status"] in ("pass", "warn", "fail")

        metrics = report["metrics"]
        assert "domain" in metrics
        assert "constraint_type" in metrics
        assert "conditionality" in metrics
        assert "timing" in metrics
        assert "alternatives" in metrics
        assert "source_quality" in metrics
        assert "scenario_yield" in metrics
        assert "transition_complexity" in metrics
        assert "held_out" in metrics

    def test_output_hash_is_sha256(self, mod, tmp_path: Path) -> None:
        gid = "test_stroke"
        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        _build_minimal_sgsc(sgsc_dir, gid)

        registry_path = _make_registry(tmp_path, [_guideline_entry(gid, domain="stroke")])
        output_dir = tmp_path / "out"

        report = mod.run_analysis(registry_path, output_dir, sgsc_dir)

        output_hash = report["output_hash"]
        assert len(output_hash) == 64
        assert all(c in "0123456789abcdef" for c in output_hash)


# ---------------------------------------------------------------------------
# TestLatexMacros
# ---------------------------------------------------------------------------


class TestLatexMacros:
    def test_macros_generated(self, mod, tmp_path: Path) -> None:
        gid = "test_aki"
        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        _build_minimal_sgsc(sgsc_dir, gid)

        registry_path = _make_registry(tmp_path, [_guideline_entry(gid)])
        output_dir = tmp_path / "out"

        report = mod.run_analysis(registry_path, output_dir, sgsc_dir)

        # Verify macro generation via _build_macros on the produced metrics
        macros = mod._build_macros(report["metrics"])
        macro_text = "\n".join(macros)

        assert "\\sgscDomainCount" in macro_text
        assert "\\sgscGuardedAtomPct" in macro_text
        assert "\\sgscTimedConstraintPct" in macro_text
        assert "\\sgscCounterfactualPct" in macro_text
        assert "\\sgscAvgScenarioYield" in macro_text
        assert "\\sgscHeldOutCount" in macro_text
        assert "\\sgscTransitionPct" in macro_text
        assert "\\providecommand" in macro_text

    def test_empty_data(self, mod, tmp_path: Path) -> None:
        # Registry with one guideline but no sgsc artifacts at all
        gid = "empty_guideline"
        sgsc_dir = tmp_path / "empty_sgsc"
        sgsc_dir.mkdir()
        # Guideline sub-dir exists but is empty
        (sgsc_dir / gid).mkdir()

        registry_path = _make_registry(tmp_path, [_guideline_entry(gid)])
        output_dir = tmp_path / "out"

        report = mod.run_analysis(registry_path, output_dir, sgsc_dir)

        # Should still produce a valid JSON structure with zero metrics
        assert report["check_name"] == "representativeness_analysis"
        assert report["status"] in ("pass", "warn", "fail")
        metrics = report["metrics"]
        assert metrics["guideline_count"] == 1
        assert metrics["conditionality"]["total_atoms"] == 0
        assert metrics["constraint_type"]["total_constraints_loaded"] == 0
        assert metrics["scenario_yield"]["avg_yield"] == 0.0
