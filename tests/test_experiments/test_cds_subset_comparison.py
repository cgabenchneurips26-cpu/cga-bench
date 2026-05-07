"""Tests for scripts/experiments/cds_subset_comparison.py (TG-V1 harness).

Covers the deterministic driver logic: scenario selection, job emission,
aggregation, and report rendering.  Does NOT spawn real episodes —
those are handled by the existing runner pool.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

# ------------------------------------------------------------------
# Lazy-load the script as a module
# ------------------------------------------------------------------


@pytest.fixture(scope="module")
def cds_module() -> Any:
    """Load the script as a module and register it in sys.modules.

    sys.modules registration is required for @dataclass to resolve forward
    references — otherwise dataclasses.py raises AttributeError on
    ``sys.modules.get(cls.__module__).__dict__``.
    """
    import sys

    name = "cds_subset_comparison"
    repo_root = Path(__file__).resolve().parent.parent.parent
    script_path = repo_root / "scripts" / "experiments" / "cds_subset_comparison.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------
# Selection
# ------------------------------------------------------------------


class TestSelectScenariosPerCpg:
    def test_caps_at_per_cpg(self, cds_module: Any) -> None:
        available = {
            "ssc_sepsis_hour1": [f"s{i}" for i in range(100)],
            "aha_chest_pain": [f"c{i}" for i in range(80)],
        }
        selected = cds_module.select_scenarios_per_cpg(available, per_cpg=50, seed=42)
        assert len(selected["ssc_sepsis_hour1"]) == 50
        assert len(selected["aha_chest_pain"]) == 50

    def test_caps_at_availability_when_smaller(self, cds_module: Any) -> None:
        available = {"small_cpg": ["s1", "s2", "s3"]}
        selected = cds_module.select_scenarios_per_cpg(available, per_cpg=50, seed=42)
        assert selected["small_cpg"] == ["s1", "s2", "s3"]

    def test_deterministic_with_same_seed(self, cds_module: Any) -> None:
        available = {"cpg1": [f"s{i}" for i in range(20)]}
        a = cds_module.select_scenarios_per_cpg(available, per_cpg=5, seed=99)
        b = cds_module.select_scenarios_per_cpg(available, per_cpg=5, seed=99)
        assert a == b

    def test_different_seeds_produce_different_samples(self, cds_module: Any) -> None:
        available = {"cpg1": [f"s{i}" for i in range(50)]}
        a = cds_module.select_scenarios_per_cpg(available, per_cpg=10, seed=1)
        b = cds_module.select_scenarios_per_cpg(available, per_cpg=10, seed=2)
        assert a != b


# ------------------------------------------------------------------
# Job emission
# ------------------------------------------------------------------


class TestEmitJobs:
    def test_cartesian_product_size(self, cds_module: Any, tmp_path: Path) -> None:
        """Job count = sum_{cpg} |scenarios| * |models| * runs * 2 arms."""
        selected = {"cpg1": ["s1", "s2"], "cpg2": ["t1"]}
        models = ["m1", "m2"]
        n_runs = 3
        jobs = cds_module.emit_jobs(selected, models, n_runs, tmp_path)
        # (2+1) scenarios * 2 models * 3 runs * 2 arms = 36
        assert len(jobs) == 36

    def test_both_arms_emitted_per_scenario(
        self, cds_module: Any, tmp_path: Path
    ) -> None:
        selected = {"cpg1": ["s1"]}
        jobs = cds_module.emit_jobs(selected, ["m1"], n_runs=1, output_root=tmp_path)
        arms = {j.arm for j in jobs}
        assert arms == {"cds_true", "cds_false"}

    def test_output_paths_are_arm_partitioned(
        self, cds_module: Any, tmp_path: Path
    ) -> None:
        selected = {"cpg1": ["s1"]}
        jobs = cds_module.emit_jobs(selected, ["m1"], n_runs=1, output_root=tmp_path)
        for job in jobs:
            assert f"/{job.arm}/" in job.output_path


# ------------------------------------------------------------------
# Aggregation + comparison
# ------------------------------------------------------------------


def _write_episode(path: Path, compliance: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "compliance_score": compliance,
                "peak_risk": 0.1,
                "aggregate_risk": 0.2,
            }
        )
    )


class TestAggregateAndCompare:
    def test_aggregate_groups_by_cpg_and_model(
        self, cds_module: Any, tmp_path: Path
    ) -> None:
        arm = tmp_path / "cds_true"
        _write_episode(arm / "ssc" / "sc_001_qwen35b_run0.json", 0.80)
        _write_episode(arm / "ssc" / "sc_002_qwen35b_run0.json", 0.90)
        _write_episode(arm / "ssc" / "sc_001_oss120b_run0.json", 0.70)

        aggregates = cds_module.aggregate_arm_episodes(arm)
        by_key = {(a.cpg_id, a.model): a for a in aggregates}
        assert (("ssc", "qwen35b")) in by_key
        assert by_key[("ssc", "qwen35b")].n_episodes == 2
        assert abs(by_key[("ssc", "qwen35b")].mean_compliance - 0.85) < 1e-9
        assert by_key[("ssc", "oss120b")].n_episodes == 1

    def test_comparison_delta_is_true_minus_false(
        self, cds_module: Any, tmp_path: Path
    ) -> None:
        true_dir = tmp_path / "cds_true"
        false_dir = tmp_path / "cds_false"
        # CDS=True boosts compliance from 0.70 to 0.85 (leakage hint = 0.15 lift)
        _write_episode(true_dir / "ssc" / "sc1_qwen35b_run0.json", 0.85)
        _write_episode(false_dir / "ssc" / "sc1_qwen35b_run0.json", 0.70)

        ts = cds_module.aggregate_arm_episodes(true_dir)
        fs = cds_module.aggregate_arm_episodes(false_dir)
        rows = cds_module.build_comparison_rows(ts, fs)
        assert len(rows) == 1
        assert abs(rows[0].delta_compliance - 0.15) < 1e-9

    def test_comparison_inner_joins_arms(
        self, cds_module: Any, tmp_path: Path
    ) -> None:
        """Models present in only one arm are dropped from the comparison."""
        true_dir = tmp_path / "cds_true"
        false_dir = tmp_path / "cds_false"
        _write_episode(true_dir / "ssc" / "sc1_only_in_true_run0.json", 0.5)
        _write_episode(false_dir / "ssc" / "sc1_qwen35b_run0.json", 0.5)

        ts = cds_module.aggregate_arm_episodes(true_dir)
        fs = cds_module.aggregate_arm_episodes(false_dir)
        rows = cds_module.build_comparison_rows(ts, fs)
        # Different "model" names parsed from filenames -> no inner-join match
        assert rows == []


class TestRenderComparisonMd:
    def test_empty_rows_renders_placeholder(self, cds_module: Any) -> None:
        out = cds_module.render_comparison_md([])
        assert "No matched episodes" in out

    def test_renders_overall_delta(self, cds_module: Any) -> None:
        Row = cds_module.ComparisonRow
        rows = [
            Row(
                cpg_id="ssc",
                model="qwen35b",
                n_episodes_per_arm=10,
                compliance_cds_true=0.80,
                compliance_cds_false=0.65,
                delta_compliance=0.15,
            ),
        ]
        out = cds_module.render_comparison_md(rows)
        assert "+0.1500" in out  # overall delta line
        assert "qwen35b" in out
        assert "ssc" in out
