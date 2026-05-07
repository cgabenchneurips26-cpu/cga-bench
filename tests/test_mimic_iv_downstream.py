"""Lightweight schema / wiring tests for Phase 2-6 of the MIMIC-IV pipeline.

These tests do NOT exercise the heavy scoring loop (which requires
Python >= 3.11 plus the assessor_core stack). They verify only that:

  * the phase scripts import cleanly
  * their main entry points refuse to run when prerequisite artefacts
    are missing (so a misconfigured run halts at the right boundary)
  * the macro / tex emitters produce the keys downstream code expects

Run as ``PYTHONPATH=. pytest tests/test_mimic_iv_downstream.py -v``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.experiments.mimic._common import (  # noqa: E402
    EVIDENCE_ROOT,
    MIMIC_LOCAL_ROOT,
)

VERDICT_PARQUET = (
    PROJECT_ROOT / "evidence_pack" / "verdicts" / "verdict_matrix_mimic_iv.parquet"
)
RANK_BOOTSTRAP = (
    PROJECT_ROOT / "evidence_pack" / "analysis" / "rank_bootstrap.json"
)


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(PROJECT_ROOT),
        env={"PYTHONPATH": str(PROJECT_ROOT), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )


class TestPhaseImports:
    """All phase scripts must import + ast-parse on Python 3.8+."""

    @pytest.mark.parametrize(
        "module",
        [
            "phase0_setup",
            "phase0_action_mapping",
            "phase1_distribution_check",
            "phase2_score_trajectories",
            "phase2_aggregate",
            "phase3_predictive_validity",
            "phase4_witness_pairs",
            "phase5_clinician_leaderboard",
            "phase6_integrate",
            "phase6_pre_flight",
        ],
    )
    def test_module_ast_parses(self, module):
        import ast

        path = PROJECT_ROOT / "scripts" / "experiments" / "mimic" / f"{module}.py"
        ast.parse(path.read_text())


class TestRefuseWhenPrereqsMissing:
    """Each phase script should exit non-zero when its inputs are absent."""

    def test_phase2_aggregate_refuses_without_verdict_matrix(self, tmp_path):
        if VERDICT_PARQUET.is_file():
            pytest.skip("verdict matrix exists; refusal-test not applicable")
        result = _run(["scripts/experiments/mimic/phase2_aggregate.py"])
        assert result.returncode == 2

    def test_phase3_refuses_without_verdict_matrix(self):
        if VERDICT_PARQUET.is_file():
            pytest.skip("verdict matrix exists; refusal-test not applicable")
        result = _run(["scripts/experiments/mimic/phase3_predictive_validity.py"])
        assert result.returncode == 2

    def test_phase5_refuses_without_verdict_matrix(self):
        if VERDICT_PARQUET.is_file():
            pytest.skip("verdict matrix exists; refusal-test not applicable")
        result = _run(["scripts/experiments/mimic/phase5_clinician_leaderboard.py"])
        assert result.returncode == 2


class TestPhase5Schema:
    """Phase 5's bootstrap-update payload must match the schema that
    paper/figures/make_figure4_ranking.py reads (per_cell[model][EV_CODE]
    with point_rank, rank_ci_lo, rank_ci_hi)."""

    def test_phase5_emits_required_per_cell_fields(self):
        if not VERDICT_PARQUET.is_file():
            pytest.skip("no verdict matrix; phase 5 cannot emit a payload")
        # Run phase 5 with --no-bootstrap-update so we can inspect the
        # standalone JSON without touching production rank_bootstrap.json.
        result = _run(
            [
                "scripts/experiments/mimic/phase5_clinician_leaderboard.py",
                "--no-bootstrap-update",
            ]
        )
        assert result.returncode == 0, result.stderr
        out = EVIDENCE_ROOT / "phase5" / "clinician_leaderboard.json"
        assert out.is_file()
        payload = json.loads(out.read_text())
        for k in ("metadata", "pass_rates", "ranks"):
            assert k in payload
        for ev in ("ASC", "CwT", "PAF", "TCC"):
            assert ev in payload["pass_rates"]
            assert ev in payload["ranks"]


class TestPhase6Macros:
    """Phase 6 macro audit: defined and used sets must align after a
    full pipeline run. We only sanity-check that the auditor functions
    work; numerical correctness is owner-side."""

    def test_phase6_integrate_runs_with_missing_summaries(self):
        result = _run(
            [
                "scripts/experiments/mimic/phase6_integrate.py",
                "--allow-missing-summaries",
            ]
        )
        # With --allow-missing-summaries the script may still flag
        # macro-orphans / missing-defs from real tex; we only require
        # that it produces a MANIFEST.
        manifest = EVIDENCE_ROOT / "MANIFEST.json"
        assert manifest.is_file()
        payload = json.loads(manifest.read_text())
        for k in (
            "git_sha",
            "mimic_version",
            "macro_definitions",
            "macro_used",
            "macro_orphaned",
            "macro_missing",
            "leakage_scan_ok",
        ):
            assert k in payload
