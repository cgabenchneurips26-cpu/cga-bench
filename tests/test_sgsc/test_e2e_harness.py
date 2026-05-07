"""Tests for sgsc.e2e_harness — Gate 1 end-to-end harness.

Uses precomputed atoms from conftest.py fixtures (no real LLM calls).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sgsc.e2e_harness import E2EHarnessConfig, E2EHarnessReport, run_e2e_harness
from sgsc.schemas.atom import RecommendationAtom

# ------------------------------------------------------------------
# Shared corpus / recommendations matching conftest atoms
# ------------------------------------------------------------------

_CORPUS_TEXT = (
    "Administer broad-spectrum antibiotics within 1 hour of sepsis recognition. "
    "Measure serum lactate level; remeasure if initial lactate is elevated (>2 mmol/L). "
    "Avoid iodinated contrast agents in patients with AKI stage 2 or higher."
)

_RECOMMENDATIONS = [
    {
        "text": "Administer broad-spectrum antibiotics within 1 hour of sepsis recognition.",
        "section": "Hour-1 Bundle",
    },
    {
        "text": "Measure serum lactate level; remeasure if initial lactate is elevated (>2 mmol/L).",
        "section": "Hour-1 Bundle",
    },
    {
        "text": "Avoid iodinated contrast agents in patients with AKI stage 2 or higher.",
        "section": "Contrast-Induced AKI Prevention",
    },
]


# ------------------------------------------------------------------
# Fixture helpers
# ------------------------------------------------------------------


def _write_corpus(tmp_path: Path, text: str = _CORPUS_TEXT) -> Path:
    """Write corpus text file and return its path."""
    p = tmp_path / "corpus.txt"
    p.write_text(text, encoding="utf-8")
    return p


def _write_recommendations(tmp_path: Path) -> Path:
    """Write recommendations JSON file and return its path."""
    p = tmp_path / "recommendations.json"
    p.write_text(json.dumps(_RECOMMENDATIONS), encoding="utf-8")
    return p


def _write_atoms(tmp_path: Path, atoms: list[RecommendationAtom]) -> Path:
    """Serialise atoms to JSON and return path."""
    p = tmp_path / "atoms.json"
    p.write_text(json.dumps([a.model_dump() for a in atoms]), encoding="utf-8")
    return p


@pytest.fixture()
def harness_config(tmp_path: Path, sample_atoms: list[RecommendationAtom]) -> E2EHarnessConfig:
    """E2EHarnessConfig wired to tmp_path fixtures (no LLM)."""
    corpus_p = _write_corpus(tmp_path)
    recs_p = _write_recommendations(tmp_path)
    atoms_p = _write_atoms(tmp_path, sample_atoms)
    out_dir = tmp_path / "harness_out"
    return E2EHarnessConfig(
        corpus_path=str(corpus_p),
        recommendations_path=str(recs_p),
        output_dir=str(out_dir),
        precomputed_atoms_path=str(atoms_p),
        guideline_id="ssc_test",
        guideline_name="SSC Test",
    )


# ------------------------------------------------------------------
# Config validation tests
# ------------------------------------------------------------------


class TestE2EHarnessConfig:
    """Unit tests for E2EHarnessConfig."""

    def test_defaults(self) -> None:
        cfg = E2EHarnessConfig(
            corpus_path="/tmp/c.txt",
            recommendations_path="/tmp/r.json",
            output_dir="/tmp/out",
        )
        assert cfg.max_atoms == 0
        assert cfg.grounding_threshold == 0.4
        assert cfg.entailment_mode == "rule_based"
        assert cfg.guideline_id == "sgsc_harness"

    def test_raises_without_llm_or_precomputed(self, tmp_path: Path) -> None:
        corpus_p = _write_corpus(tmp_path)
        recs_p = _write_recommendations(tmp_path)
        cfg = E2EHarnessConfig(
            corpus_path=str(corpus_p),
            recommendations_path=str(recs_p),
            output_dir=str(tmp_path / "out"),
            llm_config=None,
            precomputed_atoms_path=None,
        )
        with pytest.raises(ValueError, match="llm_config or precomputed_atoms_path"):
            run_e2e_harness(cfg)


# ------------------------------------------------------------------
# E2EHarnessReport defaults
# ------------------------------------------------------------------


class TestE2EHarnessReport:
    """Unit tests for E2EHarnessReport dataclass."""

    def test_all_fields_empty_string_by_default(self) -> None:
        r = E2EHarnessReport()
        for f in (
            "proposed_atoms_path",
            "accepted_atoms_path",
            "rejected_atoms_path",
            "review_required_atoms_path",
            "constraints_path",
            "seeds_path",
            "scenarios_public_path",
            "scenarios_private_path",
            "coverage_report_path",
            "leakage_report_path",
        ):
            assert getattr(r, f) == ""


# ------------------------------------------------------------------
# Full harness run tests (precomputed atoms, no LLM)
# ------------------------------------------------------------------


class TestRunE2EHarness:
    """Integration tests for run_e2e_harness with precomputed atoms."""

    def test_all_ten_output_paths_exist(
        self, harness_config: E2EHarnessConfig
    ) -> None:
        report = run_e2e_harness(harness_config)
        paths = [
            report.proposed_atoms_path,
            report.accepted_atoms_path,
            report.rejected_atoms_path,
            report.review_required_atoms_path,
            report.constraints_path,
            report.seeds_path,
            report.scenarios_public_path,
            report.scenarios_private_path,
            report.coverage_report_path,
            report.leakage_report_path,
        ]
        for p in paths:
            assert p, f"Path field is empty: {p!r}"
            assert Path(p).exists(), f"File missing: {p}"

    def test_all_output_files_are_valid_json(
        self, harness_config: E2EHarnessConfig
    ) -> None:
        report = run_e2e_harness(harness_config)
        for p in (
            report.proposed_atoms_path,
            report.accepted_atoms_path,
            report.rejected_atoms_path,
            report.review_required_atoms_path,
            report.constraints_path,
            report.seeds_path,
            report.scenarios_public_path,
            report.scenarios_private_path,
            report.coverage_report_path,
            report.leakage_report_path,
        ):
            assert p, f"Path empty: {p!r}"
            content = Path(p).read_text(encoding="utf-8")
            json.loads(content)  # raises on invalid JSON

    def test_proposed_is_superset_of_accepted_and_review(
        self, harness_config: E2EHarnessConfig
    ) -> None:
        report = run_e2e_harness(harness_config)
        proposed = {a["atom_id"] for a in json.loads(Path(report.proposed_atoms_path).read_text())}
        accepted = {a["atom_id"] for a in json.loads(Path(report.accepted_atoms_path).read_text())}
        review = {a["atom_id"] for a in json.loads(Path(report.review_required_atoms_path).read_text())}
        assert accepted.issubset(proposed), "Accepted must be subset of proposed"
        assert review.issubset(proposed), "Review-required must be subset of proposed"
        assert accepted.isdisjoint(review), "Accepted and review-required must not overlap"

    def test_rejected_bucket_disjoint_from_accepted(
        self, harness_config: E2EHarnessConfig
    ) -> None:
        """Rejected (NOT_ENTAILED) and accepted atoms must be disjoint sets."""
        report = run_e2e_harness(harness_config)
        accepted = {a["atom_id"] for a in json.loads(Path(report.accepted_atoms_path).read_text())}
        rejected = {a["atom_id"] for a in json.loads(Path(report.rejected_atoms_path).read_text())}
        assert accepted.isdisjoint(rejected), (
            "Accepted and rejected buckets must be disjoint"
        )

    def test_rejected_atoms_have_rejected_status(
        self, harness_config: E2EHarnessConfig
    ) -> None:
        """Each rejected atom must carry entailment_status='rejected'."""
        report = run_e2e_harness(harness_config)
        rejected = json.loads(Path(report.rejected_atoms_path).read_text())
        for atom in rejected:
            assert atom.get("entailment_status") == "rejected", (
                f"Rejected atom {atom.get('atom_id')} missing rejected status"
            )

    def test_leakage_report_has_required_keys(
        self, harness_config: E2EHarnessConfig
    ) -> None:
        report = run_e2e_harness(harness_config)
        leakage = json.loads(Path(report.leakage_report_path).read_text())
        assert "passed" in leakage
        assert "scenarios_scanned" in leakage
        assert "leaks" in leakage

    def test_seeds_summary_has_required_keys(
        self, harness_config: E2EHarnessConfig
    ) -> None:
        report = run_e2e_harness(harness_config)
        seeds = json.loads(Path(report.seeds_path).read_text())
        assert "total_seeds" in seeds
        assert "total_families" in seeds
        assert "total_mutations" in seeds

    def test_max_atoms_cap_applied(
        self, tmp_path: Path, sample_atoms: list[RecommendationAtom]
    ) -> None:
        corpus_p = _write_corpus(tmp_path)
        recs_p = _write_recommendations(tmp_path)
        atoms_p = _write_atoms(tmp_path, sample_atoms)
        cfg = E2EHarnessConfig(
            corpus_path=str(corpus_p),
            recommendations_path=str(recs_p),
            output_dir=str(tmp_path / "out_cap"),
            precomputed_atoms_path=str(atoms_p),
            max_atoms=1,
            guideline_id="ssc_test",
            guideline_name="SSC Test",
        )
        report = run_e2e_harness(cfg)
        proposed = json.loads(Path(report.proposed_atoms_path).read_text())
        assert len(proposed) == 1, "max_atoms cap must be respected"
