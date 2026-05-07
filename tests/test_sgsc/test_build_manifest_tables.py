"""Tests for scripts/sgsc/build_manifest_tables.py (P0-3)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.sgsc.build_manifest_tables import (
    collect_artifact_names,
    collect_atom_stats,
    collect_scenario_counts,
    generate_latex_macros,
    run_build,
)


def _make_sgsc_dir(tmp_path: Path, *, guidelines: int = 2) -> Path:
    """Create a minimal sgsc_output structure."""
    for i in range(guidelines):
        gid = f"guideline_{i}"
        gdir = tmp_path / gid
        gdir.mkdir()

        # Public scenarios
        public = {
            f"scenario_{i}_001": {
                "scenario_id": f"scenario_{i}_001",
                "description": f"Test scenario {i}",
            },
            f"scenario_{i}_002": {
                "scenario_id": f"scenario_{i}_002",
                "description": f"Another scenario {i}",
            },
        }
        (gdir / f"{gid}_scenarios_public.json").write_text(json.dumps(public))

        # Private scenarios
        private = {
            f"scenario_{i}_001": {
                "scenario_id": f"scenario_{i}_001",
                "expected_actions": ["action_a"],
            },
        }
        (gdir / f"{gid}_scenarios_private.json").write_text(json.dumps(private))

        # Atoms
        atoms = [
            {
                "atom_id": f"atom_{i}_001",
                "source": {
                    "guideline_id": gid,
                    "section": "Test",
                    "quote": "Test quote",
                },
                "population": {"inclusion": ["test"], "exclusion": []},
                "action": {"canonical_id": "test_action", "action_type": "medication"},
                "constraint": {
                    "type": "WITHIN",
                    "activation_event": "admission",
                    "deadline_minutes": 60,
                },
                "evidence": {
                    "system": "GRADE",
                    "recommendation_class": "I",
                    "level": "B",
                },
            },
            {
                "atom_id": f"atom_{i}_002",
                "source": {
                    "guideline_id": gid,
                    "section": "Test",
                    "quote": "Another quote",
                },
                "population": {"inclusion": ["test"], "exclusion": []},
                "action": {"canonical_id": "another_action", "action_type": "lab"},
                "constraint": {"type": "REQUIRED"},
                "evidence": {
                    "system": "GRADE",
                    "recommendation_class": "I",
                    "level": "A",
                },
            },
        ]
        (gdir / "atoms_smoke.json").write_text(json.dumps(atoms))

        # Graph
        graph = {"graph_id": gid, "nodes": {}}
        (gdir / f"{gid}_graph.json").write_text(json.dumps(graph))

    return tmp_path


@pytest.fixture()
def sgsc_dir(tmp_path: Path) -> Path:
    """Create sgsc_output with 2 guidelines."""
    return _make_sgsc_dir(tmp_path, guidelines=2)


class TestCollectScenarioCounts:
    """Tests for collect_scenario_counts."""

    def test_counts_public_scenarios(self, sgsc_dir: Path) -> None:
        counts = collect_scenario_counts(sgsc_dir)
        assert counts["public"] == 4  # 2 guidelines × 2 public scenarios

    def test_empty_dir(self, tmp_path: Path) -> None:
        counts = collect_scenario_counts(tmp_path)
        assert counts["public"] == 0
        assert counts["private"] == 0

    def test_single_guideline(self, tmp_path: Path) -> None:
        sgsc = _make_sgsc_dir(tmp_path, guidelines=1)
        counts = collect_scenario_counts(sgsc)
        assert counts["public"] == 2


class TestCollectAtomStats:
    """Tests for collect_atom_stats."""

    def test_counts_atoms(self, sgsc_dir: Path) -> None:
        stats = collect_atom_stats(sgsc_dir)
        assert stats["total_atoms"] == 4  # 2 guidelines × 2 atoms

    def test_constraint_types(self, sgsc_dir: Path) -> None:
        stats = collect_atom_stats(sgsc_dir)
        assert "WITHIN" in stats["constraint_types"]
        assert "REQUIRED" in stats["constraint_types"]
        assert stats["constraint_types"]["WITHIN"] == 2
        assert stats["constraint_types"]["REQUIRED"] == 2

    def test_empty_dir(self, tmp_path: Path) -> None:
        stats = collect_atom_stats(tmp_path)
        assert stats["total_atoms"] == 0
        assert stats["constraint_types"] == {}


class TestCollectArtifactNames:
    """Tests for collect_artifact_names."""

    def test_collects_json_files(self, sgsc_dir: Path) -> None:
        names = collect_artifact_names(sgsc_dir)
        assert len(names) > 0
        assert all(n.endswith(".json") for n in names)

    def test_empty_dir(self, tmp_path: Path) -> None:
        names = collect_artifact_names(tmp_path)
        assert names == []


class TestGenerateLatexMacros:
    """Tests for generate_latex_macros."""

    def test_contains_required_macros(self) -> None:
        latex = generate_latex_macros(
            scenario_counts={"public": 100, "private": 100, "manual": 0, "auto": 100},
            atom_stats={"total_atoms": 50, "constraint_types": {"WITHIN": 30, "REQUIRED": 20}},
            episode_formula={"models": 8, "scenarios": 100, "runs": 3, "expected_episodes": 2400},
            guidelines_count=14,
        )
        assert "\\sgscGuidelineCount" in latex
        assert "\\sgscScenarioCount" in latex
        assert "\\sgscAtomCount" in latex
        assert "\\sgscModelCount" in latex
        assert "\\sgscRunCount" in latex
        assert "\\sgscExpectedEpisodes" in latex

    def test_contains_constraint_macros(self) -> None:
        latex = generate_latex_macros(
            scenario_counts={"public": 10, "private": 10, "manual": 0, "auto": 10},
            atom_stats={"total_atoms": 5, "constraint_types": {"WITHIN": 3}},
            episode_formula={"models": 1, "scenarios": 10, "runs": 1, "expected_episodes": 10},
            guidelines_count=1,
        )
        assert "\\sgscConstraintWithin" in latex

    def test_uses_providecommand(self) -> None:
        latex = generate_latex_macros(
            scenario_counts={"public": 1, "private": 1, "manual": 0, "auto": 1},
            atom_stats={"total_atoms": 1, "constraint_types": {}},
            episode_formula={"models": 1, "scenarios": 1, "runs": 1, "expected_episodes": 1},
            guidelines_count=1,
        )
        assert "\\providecommand" in latex


class TestRunBuild:
    """Tests for run_build end-to-end."""

    def test_produces_manifest_and_report(self, sgsc_dir: Path) -> None:
        manifest_dict, report, latex = run_build(sgsc_dir, models=8, runs=3, previous_manifest=None)

        assert "benchmark_version" in manifest_dict
        assert report["check_name"] == "manifest_build"
        assert report["status"] in ("pass", "warn", "fail")
        assert len(latex) > 0

    def test_report_metrics(self, sgsc_dir: Path) -> None:
        _, report, _ = run_build(sgsc_dir, models=8, runs=3, previous_manifest=None)

        m = report["metrics"]
        assert m["guidelines_count"] == 2
        assert m["total_atoms"] == 4
        assert m["episode_formula"]["expected_episodes"] == 8 * 4 * 3  # 8 models × 4 scenarios × 3 runs

    def test_json_output_schema(self, sgsc_dir: Path) -> None:
        _, report, _ = run_build(sgsc_dir, models=1, runs=1, previous_manifest=None)

        required_keys = {"check_name", "status", "commit", "metrics", "failures"}
        assert required_keys.issubset(report.keys())
        assert "output_hash" in report
        assert len(report["output_hash"]) == 64

    def test_manifest_extended_fields(self, sgsc_dir: Path) -> None:
        manifest_dict, _, _ = run_build(sgsc_dir, models=1, runs=1, previous_manifest=None)

        assert "extended" in manifest_dict
        assert manifest_dict["extended"]["guidelines_count"] == 2
        assert manifest_dict["extended"]["atom_count"] == 4

    def test_empty_dir(self, tmp_path: Path) -> None:
        manifest_dict, report, latex = run_build(tmp_path, models=1, runs=1, previous_manifest=None)

        assert report["status"] == "pass"
        assert report["metrics"]["guidelines_count"] == 0
