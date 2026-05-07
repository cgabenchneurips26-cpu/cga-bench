"""Tests for scripts/sgsc/check_field_entailment_acceptance.py (P0-2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.sgsc.check_field_entailment_acceptance import (
    compute_field_pass_rates,
    find_contradiction_candidates,
    load_pilot_atoms,
    run_check,
)
from sgsc.schemas.atom import RecommendationAtom


def _make_atom(
    atom_id: str = "test_001",
    canonical_id: str = "give_broad_spectrum_antibiotics",
    quote: str = "Administer broad-spectrum antibiotics within 1 hour of sepsis recognition.",
    constraint_type: str = "WITHIN",
    deadline_minutes: int | None = 60,
    exclusion: list[str] | None = None,
    rec_class: str = "I",
    level: str = "B",
) -> RecommendationAtom:
    return RecommendationAtom.model_validate(
        {
            "atom_id": atom_id,
            "source": {
                "guideline_id": "ssc_sepsis_hour1",
                "section": "Hour-1 Bundle",
                "quote": quote,
            },
            "population": {
                "inclusion": ["sepsis"],
                "exclusion": exclusion or [],
            },
            "action": {
                "canonical_id": canonical_id,
                "action_type": "medication",
            },
            "constraint": {
                "type": constraint_type,
                "activation_event": "sepsis_recognition",
                "deadline_minutes": deadline_minutes,
            },
            "evidence": {
                "system": "GRADE",
                "recommendation_class": rec_class,
                "level": level,
            },
        }
    )


@pytest.fixture()
def sgsc_dir_with_atoms(tmp_path: Path) -> Path:
    """Create sgsc_output with atoms_smoke.json."""
    gdir = tmp_path / "ssc_sepsis_hour1_bundle"
    gdir.mkdir()

    atoms = [
        {
            "atom_id": "ssc_2021_abx",
            "source": {
                "guideline_id": "ssc_sepsis_hour1",
                "section": "Hour-1 Bundle",
                "quote": "Administer broad-spectrum antibiotics within 1 hour.",
            },
            "population": {"inclusion": ["sepsis"], "exclusion": []},
            "action": {"canonical_id": "give_broad_spectrum_antibiotics", "action_type": "medication"},
            "constraint": {"type": "WITHIN", "activation_event": "sepsis_recognition", "deadline_minutes": 60},
            "evidence": {"system": "GRADE", "recommendation_class": "I", "level": "B"},
        },
        {
            "atom_id": "ssc_2021_lactate",
            "source": {
                "guideline_id": "ssc_sepsis_hour1",
                "section": "Hour-1 Bundle",
                "quote": "Measure lactate level. Remeasure lactate if initial lactate elevated.",
            },
            "population": {"inclusion": ["sepsis"], "exclusion": []},
            "action": {"canonical_id": "measure_lactate", "action_type": "lab"},
            "constraint": {"type": "REQUIRED"},
            "evidence": {"system": "GRADE", "recommendation_class": "I", "level": "B"},
        },
    ]
    (gdir / "atoms_smoke.json").write_text(json.dumps(atoms))

    return tmp_path


class TestLoadPilotAtoms:
    """Tests for load_pilot_atoms."""

    def test_loads_atoms_from_smoke_file(self, sgsc_dir_with_atoms: Path) -> None:
        atoms, files = load_pilot_atoms(sgsc_dir_with_atoms)
        assert len(atoms) == 2
        assert len(files) == 1

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        atoms, files = load_pilot_atoms(tmp_path)
        assert atoms == []
        assert files == []

    def test_invalid_atoms_skipped(self, tmp_path: Path) -> None:
        gdir = tmp_path / "test_guideline"
        gdir.mkdir()
        atoms = [{"atom_id": "invalid_missing_fields"}, {"not_an_atom": True}]
        (gdir / "atoms_smoke.json").write_text(json.dumps(atoms))

        loaded, files = load_pilot_atoms(tmp_path)
        assert loaded == []
        assert len(files) == 1


class TestComputeFieldPassRates:
    """Tests for compute_field_pass_rates."""

    def test_fully_entailed_atoms(self) -> None:
        atoms = [_make_atom()]
        rates = compute_field_pass_rates(atoms, threshold=0.3)
        # Action should pass (antibiotics keywords in quote)
        assert rates["action"] > 0.0

    def test_empty_atoms_returns_1(self) -> None:
        rates = compute_field_pass_rates([], threshold=0.5)
        for field, rate in rates.items():
            assert rate == 1.0

    def test_rates_are_between_0_and_1(self) -> None:
        atoms = [_make_atom(), _make_atom(atom_id="test_002")]
        rates = compute_field_pass_rates(atoms, threshold=0.5)
        for field, rate in rates.items():
            assert 0.0 <= rate <= 1.0


class TestFindContradictionCandidates:
    """Tests for find_contradiction_candidates."""

    def test_no_contradictions(self) -> None:
        atoms = [_make_atom()]
        candidates = find_contradiction_candidates(atoms, threshold=0.3)
        # With low threshold, should have few/no contradictions
        assert isinstance(candidates, list)

    def test_high_threshold_finds_more(self) -> None:
        atom = _make_atom(
            canonical_id="obscure_action_xyz",
            quote="Simple recommendation text.",
        )
        low = find_contradiction_candidates([atom], threshold=0.3)
        high = find_contradiction_candidates([atom], threshold=0.9)
        assert len(high) >= len(low)


class TestRunCheck:
    """Tests for run_check end-to-end."""

    def test_with_atoms_produces_report(self, sgsc_dir_with_atoms: Path) -> None:
        report = run_check(sgsc_dir_with_atoms, [0.4, 0.5, 0.6, 0.7])
        assert report["check_name"] == "field_entailment_acceptance"
        assert report["status"] in ("pass", "warn", "fail")
        assert report["metrics"]["total_atoms"] == 2

    def test_threshold_sensitivity_keys(self, sgsc_dir_with_atoms: Path) -> None:
        report = run_check(sgsc_dir_with_atoms, [0.4, 0.7])
        ts = report["metrics"]["threshold_sensitivity"]
        assert "0.4" in ts
        assert "0.7" in ts
        for t_data in ts.values():
            assert "strict" in t_data
            assert "lenient" in t_data
            assert "rejected" in t_data

    def test_monotonic_strict_counts(self, sgsc_dir_with_atoms: Path) -> None:
        report = run_check(sgsc_dir_with_atoms, [0.3, 0.5, 0.7, 0.9])
        ts = report["metrics"]["threshold_sensitivity"]
        strict_counts = [ts[str(t)]["strict"] for t in [0.3, 0.5, 0.7, 0.9]]
        # Strict counts should be monotonically non-increasing
        for i in range(len(strict_counts) - 1):
            assert strict_counts[i] >= strict_counts[i + 1]

    def test_empty_dir_warns(self, tmp_path: Path) -> None:
        report = run_check(tmp_path, [0.5])
        assert report["status"] == "warn"
        assert report["metrics"]["total_atoms"] == 0

    def test_json_output_schema(self, sgsc_dir_with_atoms: Path) -> None:
        report = run_check(sgsc_dir_with_atoms, [0.5])
        required_keys = {"check_name", "status", "commit", "metrics", "failures"}
        assert required_keys.issubset(report.keys())
        assert "field_pass_rates" in report["metrics"]
        assert "threshold_sensitivity" in report["metrics"]

    def test_output_hash_present(self, sgsc_dir_with_atoms: Path) -> None:
        report = run_check(sgsc_dir_with_atoms, [0.5])
        assert "output_hash" in report
        assert len(report["output_hash"]) == 64
