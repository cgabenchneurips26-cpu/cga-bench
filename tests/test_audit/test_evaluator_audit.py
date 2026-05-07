"""Tests for the evaluator audit runbook CLI.

Validates:
1. V4HardShim self-consistency (BSR ~0, pi-class = nctx)
2. DxEMShim audit (pi-class = term, BSR ~ 0.44, Bayes floor = 0.436)
3. All 6 shim reports generate without error
"""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from audit.shims import SHIM_REGISTRY
import pytest
from scripts.audit.evaluator_audit import (
    run_audit,
    step1_pi_class,
    step2_bsr,
    step3_bayes_floor,
    step4_false_accept_witnesses,
)


@pytest.fixture(scope="module")
def tmp_reports_dir() -> Path:
    """Create a temporary reports directory for audit outputs."""
    d = Path(tempfile.mkdtemp(prefix="audit_test_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


class TestV4HardSelfConsistency:
    """V4Hard is the reference evaluator — it should pass self-checks."""

    def test_bsr_is_zero(self) -> None:
        shim = SHIM_REGISTRY["v4_hard"]()
        result = step2_bsr(shim)
        assert result["bsr"] == 0.0, f"V4Hard BSR should be 0, got {result['bsr']}"

    def test_no_false_accepts(self) -> None:
        shim = SHIM_REGISTRY["v4_hard"]()
        result = step4_false_accept_witnesses(shim)
        assert result["total_false_accepts"] == 0

    def test_pi_class_is_nctx(self) -> None:
        shim = SHIM_REGISTRY["v4_hard"]()
        result = step1_pi_class(shim)
        assert result["pi_class"] == "nctx", f"V4Hard should be nctx, got {result['pi_class']}"


class TestDxEMAudit:
    """DxEM is the coarsest evaluator — always passes everything."""

    def test_pi_class_is_term(self) -> None:
        shim = SHIM_REGISTRY["dxem"]()
        result = step1_pi_class(shim)
        assert result["pi_class"] == "term", f"DxEM should be term, got {result['pi_class']}"

    def test_bsr_approximately_044(self) -> None:
        shim = SHIM_REGISTRY["dxem"]()
        result = step2_bsr(shim)
        # DxEM passes everything, so BSR = fraction of v4_hard FAIL episodes
        assert 0.3 <= result["bsr"] <= 0.6, f"DxEM BSR expected ~0.44, got {result['bsr']}"

    def test_bayes_floor_is_0436(self) -> None:
        result = step3_bayes_floor("term")
        assert result["epsilon_star"] == 0.436


class TestFullAuditRun:
    """Test full audit pipeline on two shims."""

    def test_v4_hard_full_audit(self, tmp_reports_dir: Path) -> None:
        shim = SHIM_REGISTRY["v4_hard"]()
        report = run_audit(shim, tmp_reports_dir)
        assert report["step1_pi_class"]["pi_class"] == "nctx"
        assert report["step2_bsr"]["bsr"] == 0.0

        # Check files written
        eval_dir = tmp_reports_dir / "cga_bench"
        assert (eval_dir / "report.json").exists()
        assert (eval_dir / "report.md").exists()

    def test_dxem_full_audit(self, tmp_reports_dir: Path) -> None:
        shim = SHIM_REGISTRY["dxem"]()
        report = run_audit(shim, tmp_reports_dir)
        assert report["step1_pi_class"]["pi_class"] == "term"
        assert report["step3_bayes_floor"]["epsilon_star"] == 0.436

    @pytest.mark.parametrize("shim_name", list(SHIM_REGISTRY.keys()))
    def test_all_shims_generate_reports(self, shim_name: str, tmp_reports_dir: Path) -> None:
        shim = SHIM_REGISTRY[shim_name]()
        report = run_audit(shim, tmp_reports_dir)
        assert "step1_pi_class" in report
        assert "step2_bsr" in report
        assert "step3_bayes_floor" in report
        assert "step4_witnesses" in report
        assert report["corpus_size"] == 14826


class TestBuildIndex:
    """Test the INDEX.md generation."""

    def test_build_index(self, tmp_reports_dir: Path) -> None:
        from scripts.audit.build_index import build_index

        # Run all 6 shim audits
        for name, cls in SHIM_REGISTRY.items():
            run_audit(cls(), tmp_reports_dir)

        content = build_index(tmp_reports_dir)
        assert "Evaluator Audit Index" in content
        assert "CGA-Bench" in content  # v4_hard evaluator name
        assert "DxEM" in content
        assert "14,826" in content
