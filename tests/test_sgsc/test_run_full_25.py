"""Tests for scripts/sgsc/run_full_25.py batch runner.

The script lives outside any Python package, so we load it via importlib.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "sgsc" / "run_full_25.py"


def _load_module():
    """Load run_full_25 as a module without executing its __main__ block."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location("run_full_25", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules before exec so @dataclass can resolve cls.__module__
    # (Python 3.13 dataclasses calls sys.modules.get(cls.__module__).__dict__)
    sys.modules["run_full_25"] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop("run_full_25", None)
        raise
    return mod


# Cache the module so we only pay the import cost once per session.
_MOD = None


def _mod():
    global _MOD
    if _MOD is None:
        _MOD = _load_module()
    return _MOD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GUIDELINE_TEMPLATE = {
    "guideline_id": "ssc_sepsis",
    "guideline_name": "Surviving Sepsis Campaign 2021",
    "corpus_file": "agent_runner/rag_corpus/ssc_sepsis_hour1.txt",
    "graph_file": "cpg_model/graphs/auto/ssc_sepsis_hour1.yaml",
    "category": "infectious_disease",
    "conflict_pattern": None,
    "tier": "S",
    "held_out": False,
    "domain": "sepsis",
}


def _make_registry_json(n: int = 25, template: dict | None = None) -> dict:
    """Build a registry JSON dict with *n* unique guideline entries."""
    base = template or _GUIDELINE_TEMPLATE
    guidelines = []
    for i in range(n):
        entry = dict(base)
        entry["guideline_id"] = f"guideline_{i:02d}"
        entry["guideline_name"] = f"Guideline {i}"
        entry["corpus_file"] = f"agent_runner/rag_corpus/guideline_{i:02d}.txt"
        entry["graph_file"] = f"cpg_model/graphs/auto/guideline_{i:02d}.yaml"
        guidelines.append(entry)
    return {"version": "sgsc_full_v1", "guidelines": guidelines}


def _make_guideline_entry(mod, idx: int = 0):
    """Return a GuidelineEntry dataclass instance."""
    return mod.GuidelineEntry(
        guideline_id=f"guideline_{idx:02d}",
        guideline_name=f"Guideline {idx}",
        corpus_file=f"agent_runner/rag_corpus/guideline_{idx:02d}.txt",
        graph_file=f"cpg_model/graphs/auto/guideline_{idx:02d}.yaml",
        category="infectious_disease",
        conflict_pattern=None,
        tier="S",
        held_out=False,
        domain="sepsis",
    )


def _make_aggregate_report(mod, results=None):
    """Return an AggregateReport with optional list of RunResult objects."""
    report = mod.AggregateReport()
    if results:
        for r in results:
            report.per_guideline.append(r)
            if r.success:
                report.succeeded += 1
            else:
                report.failed += 1
    report.total_guidelines = len(report.per_guideline)
    report.leakage_all_passed = all(r.leakage_passed for r in report.per_guideline if r.success)
    return report


# ---------------------------------------------------------------------------
# TestLoadRegistry
# ---------------------------------------------------------------------------


class TestLoadRegistry:
    def test_load_registry_valid(self, tmp_path: Path) -> None:
        """load_registry() with 25 entries returns 25 GuidelineEntry objects."""
        mod = _mod()
        registry_file = tmp_path / "full_25_registry.json"
        registry_file.write_text(json.dumps(_make_registry_json(25)))

        with patch.object(mod, "REGISTRY_PATH", registry_file):
            entries = mod.load_registry()

        assert len(entries) == 25
        # All returned objects are GuidelineEntry instances
        for entry in entries:
            assert isinstance(entry, mod.GuidelineEntry)
        # Spot-check first entry
        assert entries[0].guideline_id == "guideline_00"
        assert entries[0].held_out is False
        assert entries[0].domain == "sepsis"

    def test_load_registry_wrong_count(self, tmp_path: Path) -> None:
        """load_registry() raises ValueError when entry count != 25."""
        mod = _mod()
        registry_file = tmp_path / "full_25_registry.json"
        registry_file.write_text(json.dumps(_make_registry_json(20)))

        with patch.object(mod, "REGISTRY_PATH", registry_file), pytest.raises(ValueError, match="20"):
            mod.load_registry()

    def test_load_registry_missing_file(self, tmp_path: Path) -> None:
        """load_registry() raises FileNotFoundError when registry is absent."""
        mod = _mod()
        nonexistent = tmp_path / "does_not_exist.json"

        with patch.object(mod, "REGISTRY_PATH", nonexistent), pytest.raises(FileNotFoundError):
            mod.load_registry()


# ---------------------------------------------------------------------------
# TestValidatePaths
# ---------------------------------------------------------------------------


class TestValidatePaths:
    def _setup_entries(self, mod, tmp_path: Path, n: int = 3):
        """Create GuidelineEntry objects and the corresponding corpus+graph files."""
        entries = []
        for i in range(n):
            gid = f"guideline_{i:02d}"
            corpus_rel = f"corpus/{gid}.txt"
            graph_rel = f"graphs/{gid}.yaml"

            # Create physical files
            corpus_path = tmp_path / corpus_rel
            corpus_path.parent.mkdir(parents=True, exist_ok=True)
            corpus_path.write_text("corpus text")

            graph_path = tmp_path / graph_rel
            graph_path.parent.mkdir(parents=True, exist_ok=True)
            graph_path.write_text("graph: yaml")

            entries.append(
                mod.GuidelineEntry(
                    guideline_id=gid,
                    guideline_name=f"G{i}",
                    corpus_file=corpus_rel,
                    graph_file=graph_rel,
                    category="test",
                    conflict_pattern=None,
                    tier="A",
                    held_out=False,
                    domain="sepsis",
                )
            )
        return entries

    def test_validate_all_exist(self, tmp_path: Path) -> None:
        """validate_paths() returns 0 errors when all corpus and graph files exist."""
        mod = _mod()
        entries = self._setup_entries(mod, tmp_path, 3)

        with (
            patch.object(mod, "REPO_ROOT", tmp_path),
            patch.object(mod, "OUTPUT_BASE", tmp_path / "sgsc_output"),
        ):
            errors = mod.validate_paths(entries, None)

        assert errors == []

    def test_validate_missing_corpus(self, tmp_path: Path) -> None:
        """validate_paths() reports an error for a missing corpus file."""
        mod = _mod()
        entries = self._setup_entries(mod, tmp_path, 3)

        # Remove the first corpus file
        corpus_path = tmp_path / entries[0].corpus_file
        corpus_path.unlink()

        with (
            patch.object(mod, "REPO_ROOT", tmp_path),
            patch.object(mod, "OUTPUT_BASE", tmp_path / "sgsc_output"),
        ):
            errors = mod.validate_paths(entries, None)

        assert len(errors) >= 1
        corpus_errors = [e for e in errors if "CORPUS" in e]
        assert len(corpus_errors) == 1
        assert entries[0].corpus_file in corpus_errors[0]

    def test_validate_missing_graph(self, tmp_path: Path) -> None:
        """validate_paths() reports an error for a missing graph file."""
        mod = _mod()
        entries = self._setup_entries(mod, tmp_path, 3)

        # Remove the last graph file
        graph_path = tmp_path / entries[-1].graph_file
        graph_path.unlink()

        with (
            patch.object(mod, "REPO_ROOT", tmp_path),
            patch.object(mod, "OUTPUT_BASE", tmp_path / "sgsc_output"),
        ):
            errors = mod.validate_paths(entries, None)

        assert len(errors) >= 1
        graph_errors = [e for e in errors if "GRAPH" in e]
        assert len(graph_errors) == 1
        assert entries[-1].graph_file in graph_errors[0]


# ---------------------------------------------------------------------------
# TestSkipExisting
# ---------------------------------------------------------------------------


class TestSkipExisting:
    def test_skip_existing_detects_completed(self, tmp_path: Path) -> None:
        """is_already_done() returns True when {id}_scenarios.json exists."""
        mod = _mod()
        gid = "ssc_sepsis"

        # Simulate existing output
        scenarios_path = tmp_path / gid / f"{gid}_scenarios.json"
        scenarios_path.parent.mkdir(parents=True, exist_ok=True)
        scenarios_path.write_text(json.dumps([{"id": "s1"}]))

        with patch.object(mod, "OUTPUT_BASE", tmp_path):
            result = mod.is_already_done(gid)

        assert result is True

    def test_skip_existing_no_output(self, tmp_path: Path) -> None:
        """is_already_done() returns False when the scenarios file is absent."""
        mod = _mod()
        gid = "ssc_sepsis"

        # Output dir exists but scenarios file does not
        (tmp_path / gid).mkdir(parents=True, exist_ok=True)

        with patch.object(mod, "OUTPUT_BASE", tmp_path):
            result = mod.is_already_done(gid)

        assert result is False


# ---------------------------------------------------------------------------
# TestNoGoCriteria
# ---------------------------------------------------------------------------


class TestNoGoCriteria:
    def test_no_go_all_pass(self, tmp_path: Path) -> None:
        """check_no_go_criteria() returns (True, []) when all results are clean."""
        mod = _mod()
        results = [
            mod.RunResult(
                guideline_id=f"guideline_{i:02d}",
                success=True,
                leakage_passed=True,
            )
            for i in range(3)
        ]
        report = _make_aggregate_report(mod, results)

        # Output dirs exist but have no files that trigger no-go conditions
        with patch.object(mod, "OUTPUT_BASE", tmp_path):
            passed, failures = mod.check_no_go_criteria(report)

        assert passed is True
        assert failures == []

    def test_no_go_leakage_fail(self, tmp_path: Path) -> None:
        """check_no_go_criteria() reports NO-GO-4 when leakage_passed=False."""
        mod = _mod()
        results = [
            mod.RunResult(
                guideline_id="guideline_00",
                success=True,
                leakage_passed=False,
            )
        ]
        report = _make_aggregate_report(mod, results)

        with patch.object(mod, "OUTPUT_BASE", tmp_path):
            passed, failures = mod.check_no_go_criteria(report)

        assert passed is False
        leakage_failures = [f for f in failures if "NO-GO-4" in f]
        assert len(leakage_failures) >= 1
        assert "guideline_00" in leakage_failures[0]

    def test_no_go_public_private_mismatch(self, tmp_path: Path) -> None:
        """check_no_go_criteria() reports NO-GO-2 when public/private counts differ."""
        mod = _mod()
        gid = "guideline_00"
        outdir = tmp_path / gid
        outdir.mkdir(parents=True, exist_ok=True)

        # Write mismatched public/private scenario files
        pub_file = outdir / f"{gid}_scenarios_public.json"
        priv_file = outdir / f"{gid}_scenarios_private.json"
        pub_file.write_text(json.dumps([{"id": "s1"}, {"id": "s2"}]))  # 2 entries
        priv_file.write_text(json.dumps([{"id": "s1"}]))  # 1 entry

        results = [mod.RunResult(guideline_id=gid, success=True, leakage_passed=True)]
        report = _make_aggregate_report(mod, results)

        with patch.object(mod, "OUTPUT_BASE", tmp_path):
            passed, failures = mod.check_no_go_criteria(report)

        assert passed is False
        mismatch_failures = [f for f in failures if "NO-GO-2" in f]
        assert len(mismatch_failures) == 1
        assert gid in mismatch_failures[0]


# ---------------------------------------------------------------------------
# TestOutputContract
# ---------------------------------------------------------------------------


class TestOutputContract:
    def _clean_report(self, mod):
        """Return a minimal clean AggregateReport with 3 successful guidelines."""
        results = [
            mod.RunResult(
                guideline_id=f"guideline_{i:02d}",
                success=True,
                scenario_count=10,
                atom_count=5,
                hallucination_rate=0.05,
                leakage_passed=True,
                duration_seconds=12.3,
            )
            for i in range(3)
        ]
        report = _make_aggregate_report(mod, results)
        report.total_scenarios = 30
        report.total_atoms = 15
        report.avg_hallucination_rate = 0.05
        report.leakage_all_passed = True
        return report

    def test_contract_has_required_keys(self, tmp_path: Path) -> None:
        """build_output_contract() output contains all required top-level keys."""
        mod = _mod()
        report = self._clean_report(mod)
        registry_file = tmp_path / "full_25_registry.json"
        registry_file.write_text(json.dumps(_make_registry_json(25)))

        with patch.object(mod, "REGISTRY_PATH", registry_file):
            contract = mod.build_output_contract(report, True, [])

        required_keys = {
            "check_name",
            "status",
            "commit",
            "input_hash",
            "output_hash",
            "metrics",
            "failures",
        }
        assert required_keys.issubset(contract.keys())

    def test_contract_hash_is_sha256(self, tmp_path: Path) -> None:
        """output_hash in contract is a 64-char lowercase hex string (SHA-256)."""
        mod = _mod()
        report = self._clean_report(mod)
        registry_file = tmp_path / "full_25_registry.json"
        registry_file.write_text(json.dumps(_make_registry_json(25)))

        with patch.object(mod, "REGISTRY_PATH", registry_file):
            contract = mod.build_output_contract(report, True, [])

        output_hash = contract["output_hash"]
        assert len(output_hash) == 64
        assert output_hash == output_hash.lower()
        # Must be valid hex
        int(output_hash, 16)

    def test_contract_status_pass(self, tmp_path: Path) -> None:
        """build_output_contract() sets status='pass' for a clean report."""
        mod = _mod()
        report = self._clean_report(mod)
        registry_file = tmp_path / "full_25_registry.json"
        registry_file.write_text(json.dumps(_make_registry_json(25)))

        with patch.object(mod, "REGISTRY_PATH", registry_file):
            contract = mod.build_output_contract(report, True, [])

        assert contract["status"] == "pass"
