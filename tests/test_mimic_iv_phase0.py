"""Phase 0 schema and halt-on-gate-fail tests for the MIMIC-IV pipeline.

Run as ``PYTHONPATH=. pytest tests/test_mimic_iv_phase0.py -v``.

These tests use the demo MIMIC-IV dataset (``data/mimic-iv-demo/``); they
intentionally exercise the gate-failure path because the demo cohort is
6 episodes (far below the contract minimum of 5,000). The point is to
verify that the scaffolding **halts correctly** when gates fail, not
that the demo data passes the gates (it cannot).
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
    GateFailure,
    PhaseSummary,
    assert_gate,
    git_sha,
    mimic_version,
    resolve_mimic_root,
)

PHASE0_DIR = EVIDENCE_ROOT / "phase0"
COHORT_SUMMARY = PHASE0_DIR / "cohort_summary.json"
MAPPING_COVERAGE = PHASE0_DIR / "mapping_coverage.json"
COHORT_PARQUET = MIMIC_LOCAL_ROOT / "cohort_sepsis3.parquet"
MAPPING_YAML = MIMIC_LOCAL_ROOT / "action_mapping.yaml"


def _run(args: list[str]) -> subprocess.CompletedProcess:
    """Run a phase script as a subprocess from the repo root."""
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(PROJECT_ROOT),
        env={"PYTHONPATH": str(PROJECT_ROOT), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module", autouse=True)
def _ensure_phase0_outputs():
    """Run phase0_setup + phase0_action_mapping in --skip-gates mode so the
    artefacts exist for downstream schema checks. Demo data → gates fail
    by design; we still emit outputs.

    **Important**: if a real-data cohort already exists (N > 100), the
    fixture skips the demo overwrite so production runs stay intact.
    The schema tests only care that the JSONs exist with the required
    shape; they don't require the demo numbers specifically.
    """
    if COHORT_PARQUET.is_file():
        try:
            import pandas as pd

            existing = pd.read_parquet(COHORT_PARQUET)
            if len(existing) > 100:
                # Real-data run is already on disk; just verify outputs exist.
                if COHORT_SUMMARY.is_file() and MAPPING_COVERAGE.is_file():
                    return
        except Exception:
            pass
    _run(
        [
            "scripts/experiments/mimic/phase0_setup.py",
            "--allow-demo-fallback",
            "--skip-gates",
        ]
    )
    _run(
        [
            "scripts/experiments/mimic/phase0_action_mapping.py",
            "--skip-gates",
        ]
    )


class TestCommonHelpers:
    def test_git_sha_short(self):
        sha = git_sha()
        assert sha == "unknown" or len(sha) == 7 or len(sha) == 8

    def test_mimic_root_resolves(self):
        root = resolve_mimic_root(prefer_full=True)
        assert root.is_dir()

    def test_mimic_version_demo_default(self):
        # Without MIMIC_VERSION env, demo path returns "demo".
        root = resolve_mimic_root(prefer_full=True)
        v = mimic_version(root)
        # Either falls back to demo (if no full data) or is set explicitly.
        assert isinstance(v, str) and v

    def test_assert_gate_raises_on_false(self):
        with pytest.raises(GateFailure):
            assert_gate(False, "test_gate", "intentional failure")

    def test_phase_summary_writes_required_keys(self, tmp_path):
        s = PhaseSummary(
            script_name="unit_test",
            phase="phase0",
            n_episodes=10,
            n_excluded=2,
            exclusion_breakdown={"too_young": 2},
            seed=7,
            git_sha="abcdef0",
            mimic_version="demo",
            wall_time_s=0.5,
            extra={"note": "smoke"},
        )
        out = s.write(tmp_path)
        assert out.exists()
        payload = json.loads(out.read_text())
        for key in (
            "script_name",
            "phase",
            "n_episodes",
            "n_excluded",
            "exclusion_breakdown",
            "seed",
            "git_sha",
            "mimic_version",
            "wall_time_s",
        ):
            assert key in payload, f"missing required summary key: {key}"
        assert payload.get("note") == "smoke", "extra fields should be merged at top level"


class TestPhase0SetupOutputs:
    def test_cohort_summary_exists(self):
        assert COHORT_SUMMARY.is_file(), f"missing {COHORT_SUMMARY}"

    def test_cohort_summary_schema(self):
        payload = json.loads(COHORT_SUMMARY.read_text())
        for key in (
            "metadata",
            "n_total_after_exclusions",
            "exclusion_breakdown",
            "demographics",
            "gates",
        ):
            assert key in payload, f"missing key: {key}"
        for gate in (
            "gate_a_size",
            "gate_b_age_median",
            "gate_b_female_fraction",
            "gate_b_mortality",
        ):
            assert gate in payload["gates"], f"missing gate: {gate}"
            keys = set(payload["gates"][gate].keys())
            assert {"pass", "observed"} <= keys
            # gate_a_size has the two-tier band (expected_range_hard +
            # expected_range_soft); other gates have a single expected_range.
            assert (
                "expected_range" in keys
                or {"expected_range_hard", "expected_range_soft"} <= keys
            )

    def test_cohort_parquet_exists(self):
        assert COHORT_PARQUET.is_file()
        import pandas as pd

        df = pd.read_parquet(COHORT_PARQUET)
        for col in (
            "subject_id",
            "hadm_id",
            "anchor_age",
            "gender",
            "female",
            "mortality_in_hospital",
        ):
            assert col in df.columns, f"missing column: {col}"

    def test_phase0_setup_summary_schema(self):
        path = PHASE0_DIR / "phase0_setup.summary.json"
        assert path.is_file()
        payload = json.loads(path.read_text())
        for key in (
            "n_episodes",
            "n_excluded",
            "exclusion_breakdown",
            "seed",
            "git_sha",
            "mimic_version",
            "wall_time_s",
        ):
            assert key in payload


class TestPhase0ActionMappingOutputs:
    def test_coverage_json_exists(self):
        assert MAPPING_COVERAGE.is_file()

    def test_coverage_json_schema(self):
        payload = json.loads(MAPPING_COVERAGE.read_text())
        for key in (
            "metadata",
            "n_mimic_events_matched",
            "all_four_hour1_coverage",
            "unmatched_string_buckets",
        ):
            assert key in payload, f"missing key: {key}"
        for action in (
            "administer_antibiotics",
            "obtain_blood_culture",
            "measure_lactate",
            "iv_crystalloid_bolus",
        ):
            assert action in payload["n_mimic_events_matched"], action

    def test_mapping_yaml_has_all_actions(self):
        import yaml

        assert MAPPING_YAML.is_file()
        data = yaml.safe_load(MAPPING_YAML.read_text())
        actions = {a["canonical_action"] for a in data["canonical_actions"]}
        required = {
            "administer_antibiotics",
            "obtain_blood_culture",
            "measure_lactate",
            "iv_crystalloid_bolus",
            "start_vasopressor_if_hypotensive",
        }
        assert required <= actions, f"missing canonical actions: {required - actions}"


class TestHaltOnGateFail:
    """Subprocess halt-on-gate-fail tests.

    These tests deliberately overwrite ``data/mimic_iv_local/cohort_sepsis3.parquet``
    with demo-cohort data, which corrupts a real-data run. They are skipped
    automatically when a real-data cohort (N > 100) is present so the
    pre-flight pipeline stays intact.
    """

    @pytest.fixture(autouse=True)
    def _skip_if_real_cohort(self):
        if COHORT_PARQUET.is_file():
            try:
                import pandas as pd

                if len(pd.read_parquet(COHORT_PARQUET)) > 100:
                    pytest.skip(
                        "real-data cohort present; halt tests would overwrite "
                        "it with demo data. Run on a fresh checkout to exercise."
                    )
            except Exception:
                pass

    def test_phase0_setup_halts_without_skip_flag(self):
        """On demo data, gates A and B fail → script must exit nonzero."""
        result = _run(
            [
                "scripts/experiments/mimic/phase0_setup.py",
                "--allow-demo-fallback",
            ]
        )
        assert result.returncode != 0, (
            f"phase0_setup should HALT on gate failure on demo data, "
            f"but exited 0. stderr:\n{result.stderr}"
        )
        assert "HALT" in result.stderr or "GATE-FAIL" in result.stderr

    def test_phase0_action_mapping_halts_without_skip_flag(self):
        """On demo data, gate C fails (no prescriptions) → script must exit nonzero."""
        result = _run(
            ["scripts/experiments/mimic/phase0_action_mapping.py"]
        )
        assert result.returncode != 0, (
            f"phase0_action_mapping should HALT on gate failure on demo data, "
            f"but exited 0. stderr:\n{result.stderr}"
        )
