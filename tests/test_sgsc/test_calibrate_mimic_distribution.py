"""Tests for scripts/sgsc/calibrate_mimic_distribution.py.

Covers KL divergence math, each calibration metric, graceful degradation
when MIMIC artifacts are missing, JSON contract schema, LaTeX macro
generation, and the --domain filter.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from scripts.sgsc.calibrate_mimic_distribution import (
    MIMIC_DOMAINS,
    MIMIC_HOUR1_ACTIONS,
    _append_macros,
    _build_macros,
    _metric_action_alphabet,
    _metric_constraint_activation,
    _metric_domain_coverage,
    kl_divergence,
    run_calibration,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_TOP_KEYS = {
    "check_name",
    "status",
    "commit",
    "input_hash",
    "output_hash",
    "metrics",
    "failures",
}

_REQUIRED_METRICS_KEYS = {
    "data_available",
    "action_frequency_kl",
    "constraint_activation_rate",
    "violation_type_distribution",
    "domain_coverage",
    "action_alphabet_overlap",
    "deadline_presence_rate",
}


def _make_registry(tmp_path: Path, guidelines: list[dict] | None = None) -> Path:
    """Write a minimal registry JSON and return its path."""
    if guidelines is None:
        guidelines = [
            {"guideline_id": "ssc_sepsis", "domain": "sepsis"},
            {"guideline_id": "aha_stroke", "domain": "stroke"},
            {"guideline_id": "ada_dka", "domain": "endocrine"},
            {"guideline_id": "kdigo_aki", "domain": "nephrology"},
        ]
    reg = {"version": "test", "guidelines": guidelines}
    p = tmp_path / "registry.json"
    p.write_text(json.dumps(reg), encoding="utf-8")
    return p


def _make_sgsc_dir(
    tmp_path: Path,
    guideline_id: str,
    constraints: list[dict] | None = None,
    scenarios: list[dict] | None = None,
) -> Path:
    """Create a minimal SGSC output directory for one guideline."""
    gdir = tmp_path / "sgsc_output" / guideline_id
    gdir.mkdir(parents=True, exist_ok=True)
    if constraints is not None:
        (gdir / f"{guideline_id}_constraints.json").write_text(json.dumps(constraints), encoding="utf-8")
    if scenarios is not None:
        (gdir / f"{guideline_id}_scenarios.json").write_text(json.dumps(scenarios), encoding="utf-8")
    return tmp_path / "sgsc_output"


def _make_mimic_phase0(tmp_path: Path, matched: dict[str, int] | None = None) -> Path:
    """Write a minimal phase0 mapping_coverage.json."""
    if matched is None:
        matched = {
            "administer_antibiotics": 11050,
            "obtain_blood_culture": 9066,
            "measure_lactate": 9731,
            "iv_crystalloid_bolus": 10586,
        }
    phase0_dir = tmp_path / "mimic_iv" / "phase0"
    phase0_dir.mkdir(parents=True, exist_ok=True)
    data = {"metadata": {}, "n_mimic_events_matched": matched}
    (phase0_dir / "mapping_coverage.json").write_text(json.dumps(data), encoding="utf-8")
    return tmp_path / "mimic_iv"


# ---------------------------------------------------------------------------
# 1. kl_divergence — identical distributions → KL ≈ 0
# ---------------------------------------------------------------------------


class TestKLDivergenceIdentical:
    def test_identical_returns_near_zero(self) -> None:
        p = {"a": 10.0, "b": 20.0, "c": 30.0}
        result = kl_divergence(p, p.copy())
        assert result == pytest.approx(0.0, abs=1e-8)


# ---------------------------------------------------------------------------
# 2. kl_divergence — different distributions → KL > 0
# ---------------------------------------------------------------------------


class TestKLDivergenceDifferent:
    def test_different_returns_positive(self) -> None:
        p = {"a": 10.0, "b": 1.0}
        q = {"a": 1.0, "b": 10.0}
        result = kl_divergence(p, q)
        assert result > 0.0

    def test_asymmetric(self) -> None:
        """KL(P||Q) != KL(Q||P) when one distribution is strictly broader.

        Choose P concentrated (spike on "a") and Q uniform across 4 keys.
        KL(P||Q) measures surprise of Q under P, KL(Q||P) the reverse — they
        differ whenever P and Q have genuinely different shapes.
        """
        p = {"a": 97.0, "b": 1.0, "c": 1.0, "d": 1.0}
        q = {"a": 25.0, "b": 25.0, "c": 25.0, "d": 25.0}
        kl_pq = kl_divergence(p, q)
        kl_qp = kl_divergence(q, p)
        assert abs(kl_pq - kl_qp) > 1e-6


# ---------------------------------------------------------------------------
# 3. kl_divergence — disjoint distributions → KL large but finite
# ---------------------------------------------------------------------------


class TestKLDivergenceDisjoint:
    def test_disjoint_is_finite(self) -> None:
        """Smoothing prevents infinity for zero-probability keys."""
        p = {"a": 100.0}
        q = {"b": 100.0}
        result = kl_divergence(p, q)
        assert math.isfinite(result)
        assert result > 0.0

    def test_disjoint_larger_than_overlapping(self) -> None:
        p_disjoint = {"a": 100.0}
        q_disjoint = {"b": 100.0}
        p_overlap = {"a": 90.0, "b": 10.0}
        q_overlap = {"a": 10.0, "b": 90.0}
        kl_dis = kl_divergence(p_disjoint, q_disjoint)
        kl_ovl = kl_divergence(p_overlap, q_overlap)
        assert kl_dis > kl_ovl


# ---------------------------------------------------------------------------
# 4. constraint_activation_rate — full overlap → 1.0
# ---------------------------------------------------------------------------


class TestConstraintActivationFull:
    def test_full_overlap_returns_one(self) -> None:
        # All SGSC constraint types present in MIMIC-covered types
        constraints: dict[str, list[dict]] = {
            "guide_a": [
                {"constraint_type": "REQUIRED"},
                {"constraint_type": "WITHIN"},
                {"constraint_type": "BEFORE"},
            ]
        }
        phase0 = {
            "n_mimic_events_matched": {
                "administer_antibiotics": 100,
                "obtain_blood_culture": 100,
            }
        }
        result = _metric_constraint_activation(constraints, phase0)
        assert result == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# 5. constraint_activation_rate — partial overlap → 0.6
# ---------------------------------------------------------------------------


class TestConstraintActivationPartial:
    def test_partial_overlap(self) -> None:
        # REQUIRED, WITHIN, BEFORE are MIMIC-covered; FORBIDDEN, SEQUENCE are not
        constraints: dict[str, list[dict]] = {
            "guide_a": [
                {"constraint_type": "REQUIRED"},
                {"constraint_type": "WITHIN"},
                {"constraint_type": "BEFORE"},
                {"constraint_type": "FORBIDDEN"},
                {"constraint_type": "SEQUENCE"},
            ]
        }
        phase0 = {
            "n_mimic_events_matched": {
                "administer_antibiotics": 100,
                "obtain_blood_culture": 100,
            }
        }
        result = _metric_constraint_activation(constraints, phase0)
        # 3 of 5 types are covered → 0.6
        assert result == pytest.approx(0.6, abs=1e-4)


# ---------------------------------------------------------------------------
# 6. domain_coverage — SGSC 13 domains, MIMIC 4
# ---------------------------------------------------------------------------


class TestDomainCoverage:
    def test_coverage_rate(self) -> None:
        # 13 distinct SGSC domains, 4 overlap with MIMIC_DOMAINS
        sgsc_domain_names = [
            "sepsis",
            "stroke",
            "chest_pain",
            "aki",  # these 4 are in MIMIC_DOMAINS
            "endocrine",
            "pulmonary",
            "hematology",
            "cardiac_arrest",
            "infectious_disease",
            "pediatric",
            "neurology",
            "nephrology",
            "allergy",
        ]
        guidelines = [{"guideline_id": f"g{i}", "domain": d} for i, d in enumerate(sgsc_domain_names)]
        result = _metric_domain_coverage(guidelines, domain_filter=None)
        assert result["sgsc_domains"] == 13
        assert result["mimic_domains"] == len(MIMIC_DOMAINS)
        # 4 domains overlap
        assert len(result["overlap"]) == 4
        # overlap_rate = 4/13 ≈ 0.307
        assert result["overlap_rate"] == pytest.approx(4 / 13, abs=1e-3)


# ---------------------------------------------------------------------------
# 7. action_alphabet_overlap — SGSC 50 actions, MIMIC 5
# ---------------------------------------------------------------------------


class TestActionAlphabetOverlap:
    def test_overlap_bounded_by_mimic(self) -> None:
        # Create 50 SGSC actions; a few match MIMIC_HOUR1_ACTIONS
        sgsc_actions = [f"action_{i}" for i in range(45)]
        # Add 3 from MIMIC Hour-1
        mimic_sample = list(MIMIC_HOUR1_ACTIONS)[:3]
        sgsc_actions.extend(mimic_sample)
        # Put them all into scenarios
        scenarios: dict[str, list[dict]] = {"guide_a": [{"actions": sgsc_actions}]}
        result = _metric_action_alphabet({}, scenarios)
        assert result["sgsc_actions"] == 48  # 45 + 3 (no duplicates in set)
        assert result["mimic_actions"] == len(MIMIC_HOUR1_ACTIONS)
        assert result["overlap"] == 3
        assert result["overlap"] <= len(MIMIC_HOUR1_ACTIONS)

    def test_zero_overlap_when_no_match(self) -> None:
        scenarios: dict[str, list[dict]] = {"guide_a": [{"actions": ["totally_unknown_action_xyz"]}]}
        result = _metric_action_alphabet({}, scenarios)
        assert result["overlap"] == 0
        assert result["overlap_rate"] == 0.0


# ---------------------------------------------------------------------------
# 8. graceful_no_mimic_artifacts → status=warn, metrics=None for kl/activation
# ---------------------------------------------------------------------------


class TestGracefulNoMimicArtifacts:
    def test_missing_mimic_dir_produces_warn(self, tmp_path: Path) -> None:
        reg = _make_registry(tmp_path)
        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        mimic_dir = tmp_path / "nonexistent_mimic"
        out_dir = tmp_path / "out"

        report = run_calibration(
            registry_path=reg,
            sgsc_dir=sgsc_dir,
            mimic_dir=mimic_dir,
            output_dir=out_dir,
        )

        assert report["status"] == "warn"
        assert report["metrics"]["data_available"]["mimic_phase0"] is False
        assert report["metrics"]["data_available"]["mimic_phase1"] is False
        assert report["metrics"]["data_available"]["mimic_phase2"] is False
        assert report["metrics"]["action_frequency_kl"] is None
        assert report["metrics"]["constraint_activation_rate"] is None

    def test_no_mimic_failure_message_present(self, tmp_path: Path) -> None:
        reg = _make_registry(tmp_path)
        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        mimic_dir = tmp_path / "nonexistent_mimic"
        out_dir = tmp_path / "out"

        report = run_calibration(
            registry_path=reg,
            sgsc_dir=sgsc_dir,
            mimic_dir=mimic_dir,
            output_dir=out_dir,
        )

        failure_details = [f.get("detail", "") for f in report["failures"]]
        assert any("MIMIC" in d or "mimic" in d for d in failure_details)


# ---------------------------------------------------------------------------
# 9. graceful_partial_mimic — only phase0 exists → partial metrics computed
# ---------------------------------------------------------------------------


class TestGracefulPartialMimic:
    def test_phase0_only_computes_kl(self, tmp_path: Path) -> None:
        reg = _make_registry(tmp_path)
        sgsc_dir = _make_sgsc_dir(
            tmp_path,
            "ssc_sepsis",
            scenarios=[{"actions": ["administer_antibiotics", "obtain_blood_culture"]}],
        )
        mimic_dir = _make_mimic_phase0(tmp_path)
        out_dir = tmp_path / "out"

        report = run_calibration(
            registry_path=reg,
            sgsc_dir=sgsc_dir,
            mimic_dir=mimic_dir,
            output_dir=out_dir,
        )

        da = report["metrics"]["data_available"]
        assert da["mimic_phase0"] is True
        assert da["mimic_phase1"] is False
        assert da["mimic_phase2"] is False
        # KL should be computable when phase0 and scenarios are present
        assert report["metrics"]["action_frequency_kl"] is not None

    def test_phase0_only_does_not_fail(self, tmp_path: Path) -> None:
        reg = _make_registry(tmp_path)
        sgsc_dir = _make_sgsc_dir(
            tmp_path,
            "ssc_sepsis",
            scenarios=[{"actions": ["administer_antibiotics"]}],
        )
        mimic_dir = _make_mimic_phase0(tmp_path)
        out_dir = tmp_path / "out"

        report = run_calibration(
            registry_path=reg,
            sgsc_dir=sgsc_dir,
            mimic_dir=mimic_dir,
            output_dir=out_dir,
        )

        assert report["status"] != "fail"


# ---------------------------------------------------------------------------
# 10. json_contract_schema — output has all required keys
# ---------------------------------------------------------------------------


class TestJsonContractSchema:
    def test_all_top_level_keys_present(self, tmp_path: Path) -> None:
        reg = _make_registry(tmp_path)
        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        mimic_dir = tmp_path / "no_mimic"
        out_dir = tmp_path / "out"

        report = run_calibration(
            registry_path=reg,
            sgsc_dir=sgsc_dir,
            mimic_dir=mimic_dir,
            output_dir=out_dir,
        )

        assert _REQUIRED_TOP_KEYS.issubset(set(report.keys()))

    def test_all_metrics_keys_present(self, tmp_path: Path) -> None:
        reg = _make_registry(tmp_path)
        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        mimic_dir = tmp_path / "no_mimic"
        out_dir = tmp_path / "out"

        report = run_calibration(
            registry_path=reg,
            sgsc_dir=sgsc_dir,
            mimic_dir=mimic_dir,
            output_dir=out_dir,
        )

        assert _REQUIRED_METRICS_KEYS.issubset(set(report["metrics"].keys()))

    def test_output_file_written(self, tmp_path: Path) -> None:
        reg = _make_registry(tmp_path)
        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        mimic_dir = tmp_path / "no_mimic"
        out_dir = tmp_path / "out"

        run_calibration(
            registry_path=reg,
            sgsc_dir=sgsc_dir,
            mimic_dir=mimic_dir,
            output_dir=out_dir,
        )

        out_file = out_dir / "mimic_calibration.json"
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert data["check_name"] == "mimic_calibration"

    def test_output_hash_populated(self, tmp_path: Path) -> None:
        reg = _make_registry(tmp_path)
        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        mimic_dir = tmp_path / "no_mimic"
        out_dir = tmp_path / "out"

        report = run_calibration(
            registry_path=reg,
            sgsc_dir=sgsc_dir,
            mimic_dir=mimic_dir,
            output_dir=out_dir,
        )

        assert isinstance(report["output_hash"], str)
        assert len(report["output_hash"]) == 64  # SHA-256 hex digest length

    def test_status_values_are_valid(self, tmp_path: Path) -> None:
        reg = _make_registry(tmp_path)
        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        mimic_dir = tmp_path / "no_mimic"
        out_dir = tmp_path / "out"

        report = run_calibration(
            registry_path=reg,
            sgsc_dir=sgsc_dir,
            mimic_dir=mimic_dir,
            output_dir=out_dir,
        )

        assert report["status"] in {"pass", "warn", "fail"}


# ---------------------------------------------------------------------------
# 11. latex_macros_generated — macros written to auto_numbers_sgsc.tex
# ---------------------------------------------------------------------------


class TestLatexMacrosGenerated:
    def test_macros_appended_to_tex_file(self, tmp_path: Path) -> None:
        tex_path = tmp_path / "auto_numbers_sgsc.tex"
        tex_path.write_text("% existing content\n", encoding="utf-8")

        metrics = {
            "action_frequency_kl": 0.1234,
            "constraint_activation_rate": 0.75,
            "domain_coverage": {"overlap": ["sepsis", "aki"], "overlap_rate": 0.3},
            "action_alphabet_overlap": {"overlap_rate": 0.05},
            "deadline_presence_rate": 0.8,
        }
        macros = _build_macros(metrics)
        _append_macros(tex_path, macros)

        content = tex_path.read_text(encoding="utf-8")
        assert "sgscMimicActionKL" in content
        assert "sgscMimicConstraintActivation" in content
        assert "sgscMimicDomainsCovered" in content
        assert "sgscMimicActionOverlap" in content
        assert "sgscMimicDeadlinePresence" in content

    def test_macros_idempotent(self, tmp_path: Path) -> None:
        """Calling _append_macros twice should not duplicate the block."""
        tex_path = tmp_path / "auto_numbers_sgsc.tex"
        tex_path.write_text("", encoding="utf-8")

        metrics = {
            "action_frequency_kl": 0.5,
            "constraint_activation_rate": 0.5,
            "domain_coverage": {"overlap": [], "overlap_rate": 0.0},
            "action_alphabet_overlap": {"overlap_rate": 0.0},
            "deadline_presence_rate": 0.5,
        }
        macros = _build_macros(metrics)
        _append_macros(tex_path, macros)
        _append_macros(tex_path, macros)

        content = tex_path.read_text(encoding="utf-8")
        # Should appear exactly once
        assert content.count("sgscMimicActionKL") == 1

    def test_build_macros_na_when_none(self) -> None:
        metrics: dict = {
            "action_frequency_kl": None,
            "constraint_activation_rate": None,
            "domain_coverage": {"overlap": [], "overlap_rate": 0.0},
            "action_alphabet_overlap": {"overlap_rate": 0.0},
            "deadline_presence_rate": None,
        }
        macros = _build_macros(metrics)
        kl_macro = next(m for m in macros if "sgscMimicActionKL" in m)
        assert "{N/A}" in kl_macro


# ---------------------------------------------------------------------------
# 12. domain_filter — --domain sepsis → only sepsis constraints counted
# ---------------------------------------------------------------------------


class TestDomainFilter:
    def test_domain_filter_restricts_guidelines(self, tmp_path: Path) -> None:
        guidelines = [
            {"guideline_id": "ssc_sepsis", "domain": "sepsis"},
            {"guideline_id": "aha_stroke", "domain": "stroke"},
            {"guideline_id": "aha_hf", "domain": "heart_failure"},
        ]
        reg = _make_registry(tmp_path, guidelines)

        # Create SGSC output for both sepsis and stroke
        sgsc_dir = tmp_path / "sgsc_output"
        sepsis_dir = sgsc_dir / "ssc_sepsis"
        sepsis_dir.mkdir(parents=True)
        (sepsis_dir / "ssc_sepsis_constraints.json").write_text(
            json.dumps([{"constraint_type": "WITHIN", "action_id": "administer_antibiotics"}]),
            encoding="utf-8",
        )
        (sepsis_dir / "ssc_sepsis_scenarios.json").write_text(
            json.dumps([{"actions": ["administer_antibiotics"]}]),
            encoding="utf-8",
        )
        stroke_dir = sgsc_dir / "aha_stroke"
        stroke_dir.mkdir(parents=True)
        (stroke_dir / "aha_stroke_constraints.json").write_text(
            json.dumps([{"constraint_type": "BEFORE", "action_id": "give_alteplase"}]),
            encoding="utf-8",
        )

        mimic_dir = _make_mimic_phase0(tmp_path)
        out_dir = tmp_path / "out"

        report = run_calibration(
            registry_path=reg,
            sgsc_dir=sgsc_dir,
            mimic_dir=mimic_dir,
            output_dir=out_dir,
            domain_filter="sepsis",
        )

        # Domain coverage: only sepsis → 1 SGSC domain
        dc = report["metrics"]["domain_coverage"]
        assert dc["sgsc_domains"] == 1
        # sepsis is in MIMIC_DOMAINS → overlap_rate = 1.0
        assert dc["overlap_rate"] == pytest.approx(1.0, abs=1e-6)

    def test_domain_filter_produces_pass_with_real_artifacts(self, tmp_path: Path) -> None:
        guidelines = [
            {"guideline_id": "ssc_sepsis", "domain": "sepsis"},
        ]
        reg = _make_registry(tmp_path, guidelines)
        sgsc_dir = _make_sgsc_dir(
            tmp_path,
            "ssc_sepsis",
            constraints=[{"constraint_type": "WITHIN", "action_id": "administer_antibiotics", "deadline_minutes": 60}],
            scenarios=[{"actions": ["administer_antibiotics", "obtain_blood_culture"]}],
        )
        mimic_dir = _make_mimic_phase0(tmp_path)
        out_dir = tmp_path / "out"

        report = run_calibration(
            registry_path=reg,
            sgsc_dir=sgsc_dir,
            mimic_dir=mimic_dir,
            output_dir=out_dir,
            domain_filter="sepsis",
        )

        assert report["status"] == "pass"
        assert report["metrics"]["action_frequency_kl"] is not None
        assert report["metrics"]["deadline_presence_rate"] is not None
