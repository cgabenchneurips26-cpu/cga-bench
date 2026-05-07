"""Tests for scripts/sgsc/run_validation_packet.py — Gate-7 packet runner."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003

# ---------------------------------------------------------------------------
# Synthetic fixture data (mirrors test_validation_packet.py shapes)
# ---------------------------------------------------------------------------

_ACCEPTED_ATOMS = [
    {
        "atom_id": f"atom_{i:03d}",
        "source": {
            "guideline_id": "ssc_test",
            "section": "Hour-1",
            "page": "e53",
            "quote": f"Guideline recommendation text {i}.",
            "quote_hash": "",
        },
        "population": {"inclusion": ["sepsis"], "exclusion": []},
        "action": {
            "canonical_id": f"action_{i}",
            "action_type": "medication",
            "terminology": {},
        },
        "constraint": {
            "type": "REQUIRED",
            "activation_event": None,
            "deadline_minutes": None,
        },
        "sequence": {"before": [], "required_prior": []},
        "evidence": {
            "system": "GRADE",
            "recommendation_class": "I",
            "level": "B",
        },
        "scenario_hooks": {"boundary_variables": [], "counterfactual_pairs": []},
        "proposed_by": "test_model",
        "agreement_score": 1.0,
        "entailment_status": "entailed",
        "verified_at": None,
    }
    for i in range(20)
]

_CONSTRAINTS = [
    {
        "constraint_type": "REQUIRED",
        "actions": [f"action_{i}"],
        "severity": "HIGH",
        "description": f"Constraint description {i}",
    }
    for i in range(15)
]

_PUBLIC_SCENARIOS = {
    f"scenario_{i:03d}": {
        "patient_state": {"diagnosis": "sepsis", "age": 65 + i},
        "observation": {"lactate": 2.5},
        "description": f"Sepsis patient scenario {i}",
        "mutations": [{"mutation_type": "omit", "target": "antibiotics"}],
    }
    for i in range(30)
}

_PRIVATE_SCENARIOS: dict[str, object] = {}


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_sgsc_output(base: Path, guideline_id: str) -> None:
    """Write the four required SGSC output files for *guideline_id*."""
    gdir = base / guideline_id
    _write_json(gdir / "atoms_accepted.json", _ACCEPTED_ATOMS)
    _write_json(gdir / f"{guideline_id}_constraints.json", _CONSTRAINTS)
    _write_json(gdir / f"{guideline_id}_scenarios_public.json", _PUBLIC_SCENARIOS)
    _write_json(gdir / f"{guideline_id}_scenarios_private.json", _PRIVATE_SCENARIOS)


def _make_registry(path: Path, guideline_ids: list[str]) -> None:
    """Write a minimal registry JSON with entries for each *guideline_id*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "guideline_id": gid,
            "guideline_name": gid.replace("_", " ").title(),
            "corpus_file": f"corpus/{gid}.txt",
            "graph_file": f"cpg_model/graphs/auto/{gid}.yaml",
            "category": "test",
            "domain": "test",
        }
        for gid in guideline_ids
    ]
    path.write_text(json.dumps({"guidelines": entries}), encoding="utf-8")


# ---------------------------------------------------------------------------
# Import the module under test (lazy, so PYTHONPATH issues surface clearly)
# ---------------------------------------------------------------------------


def _import_runner() -> object:
    """Import run_validation_packet, inserting the repo root if needed."""
    import importlib
    import pathlib
    import sys

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return importlib.import_module("scripts.sgsc.run_validation_packet")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDryRun:
    """dry-run mode: path validation only, no packet built."""

    def test_dry_run_validates_paths(self, tmp_path: Path) -> None:
        """Dry run with all files present exits 0 and writes summary JSON."""
        gid = "ssc_test"
        sgsc_dir = tmp_path / "sgsc_output"
        _make_sgsc_output(sgsc_dir, gid)

        registry_path = tmp_path / "configs" / "sgsc" / "test_registry.json"
        _make_registry(registry_path, [gid])

        output_dir = tmp_path / "packets"
        summary_path = tmp_path / "evidence_pack" / "analysis" / "summary.json"

        runner = _import_runner()

        # Patch _SUMMARY_PATH to avoid writing into the real repo
        original = runner._SUMMARY_PATH
        runner._SUMMARY_PATH = summary_path
        try:
            rc = runner.main(
                [
                    "--all",
                    "--registry",
                    str(registry_path),
                    "--sgsc-dir",
                    str(sgsc_dir),
                    "--output-dir",
                    str(output_dir),
                    "--dry-run",
                ]
            )
        finally:
            runner._SUMMARY_PATH = original

        assert rc == 0
        assert summary_path.exists()

    def test_dry_run_reports_missing_files(self, tmp_path: Path) -> None:
        """Dry run with a missing atoms file skips the guideline (warn, not crash)."""
        gid = "ssc_test"
        sgsc_dir = tmp_path / "sgsc_output"
        # Intentionally omit atoms_accepted.json
        gdir = sgsc_dir / gid
        gdir.mkdir(parents=True)
        _write_json(gdir / f"{gid}_constraints.json", _CONSTRAINTS)
        _write_json(gdir / f"{gid}_scenarios_public.json", _PUBLIC_SCENARIOS)
        _write_json(gdir / f"{gid}_scenarios_private.json", _PRIVATE_SCENARIOS)

        registry_path = tmp_path / "configs" / "sgsc" / "test_registry.json"
        _make_registry(registry_path, [gid])

        summary_path = tmp_path / "summary.json"
        runner = _import_runner()
        original = runner._SUMMARY_PATH
        runner._SUMMARY_PATH = summary_path
        try:
            rc = runner.main(
                [
                    "--all",
                    "--registry",
                    str(registry_path),
                    "--sgsc-dir",
                    str(sgsc_dir),
                    "--output-dir",
                    str(tmp_path / "packets"),
                    "--dry-run",
                ]
            )
        finally:
            runner._SUMMARY_PATH = original

        # warn status → exit 0 (not fail)
        assert rc == 0
        contract = json.loads(summary_path.read_text())
        assert contract["status"] == "warn"
        skipped = contract["metrics"]["guidelines_skipped"]
        assert skipped == 1


class TestFullRun:
    """Full (non-dry) run tests."""

    def test_build_packet_from_synthetic_output(self, tmp_path: Path) -> None:
        """Full run produces packet.json in output_dir/{guideline_id}/."""
        gid = "ssc_test"
        sgsc_dir = tmp_path / "sgsc_output"
        _make_sgsc_output(sgsc_dir, gid)

        registry_path = tmp_path / "reg.json"
        _make_registry(registry_path, [gid])

        output_dir = tmp_path / "packets"
        summary_path = tmp_path / "summary.json"

        runner = _import_runner()
        original = runner._SUMMARY_PATH
        runner._SUMMARY_PATH = summary_path
        try:
            rc = runner.main(
                [
                    "--all",
                    "--registry",
                    str(registry_path),
                    "--sgsc-dir",
                    str(sgsc_dir),
                    "--output-dir",
                    str(output_dir),
                ]
            )
        finally:
            runner._SUMMARY_PATH = original

        assert rc == 0
        assert (output_dir / gid / "packet.json").exists()

    def test_csv_output_created(self, tmp_path: Path) -> None:
        """Full run produces clinician_review_form.csv alongside packet.json."""
        gid = "ssc_test"
        sgsc_dir = tmp_path / "sgsc_output"
        _make_sgsc_output(sgsc_dir, gid)

        registry_path = tmp_path / "reg.json"
        _make_registry(registry_path, [gid])

        output_dir = tmp_path / "packets"
        summary_path = tmp_path / "summary.json"

        runner = _import_runner()
        original = runner._SUMMARY_PATH
        runner._SUMMARY_PATH = summary_path
        try:
            runner.main(
                [
                    "--all",
                    "--registry",
                    str(registry_path),
                    "--sgsc-dir",
                    str(sgsc_dir),
                    "--output-dir",
                    str(output_dir),
                ]
            )
        finally:
            runner._SUMMARY_PATH = original

        assert (output_dir / gid / "clinician_review_form.csv").exists()

    def test_json_contract_schema(self, tmp_path: Path) -> None:
        """Output JSON has all required top-level keys."""
        gid = "ssc_test"
        sgsc_dir = tmp_path / "sgsc_output"
        _make_sgsc_output(sgsc_dir, gid)

        registry_path = tmp_path / "reg.json"
        _make_registry(registry_path, [gid])

        summary_path = tmp_path / "summary.json"
        runner = _import_runner()
        original = runner._SUMMARY_PATH
        runner._SUMMARY_PATH = summary_path
        try:
            runner.main(
                [
                    "--all",
                    "--registry",
                    str(registry_path),
                    "--sgsc-dir",
                    str(sgsc_dir),
                    "--output-dir",
                    str(tmp_path / "packets"),
                ]
            )
        finally:
            runner._SUMMARY_PATH = original

        contract = json.loads(summary_path.read_text())
        for key in ("check_name", "status", "commit", "input_hash", "output_hash", "metrics", "failures"):
            assert key in contract, f"Missing key '{key}' in contract"
        assert contract["check_name"] == "validation_packet_runner"

        metrics = contract["metrics"]
        for mk in ("guidelines_processed", "guidelines_skipped", "total_items", "per_bucket", "per_guideline"):
            assert mk in metrics, f"Missing metrics key '{mk}'"

    def test_per_bucket_counts(self, tmp_path: Path) -> None:
        """per_bucket counts reflect items built (capped at bucket sizes)."""
        gid = "ssc_test"
        sgsc_dir = tmp_path / "sgsc_output"
        _make_sgsc_output(sgsc_dir, gid)

        registry_path = tmp_path / "reg.json"
        _make_registry(registry_path, [gid])

        summary_path = tmp_path / "summary.json"
        runner = _import_runner()
        original = runner._SUMMARY_PATH
        runner._SUMMARY_PATH = summary_path
        try:
            runner.main(
                [
                    "--all",
                    "--registry",
                    str(registry_path),
                    "--sgsc-dir",
                    str(sgsc_dir),
                    "--output-dir",
                    str(tmp_path / "packets"),
                    "--n-atoms",
                    "10",
                    "--n-constraints",
                    "10",
                    "--n-scenarios",
                    "10",
                    "--n-traces",
                    "10",
                ]
            )
        finally:
            runner._SUMMARY_PATH = original

        contract = json.loads(summary_path.read_text())
        pb = contract["metrics"]["per_bucket"]
        assert pb["atom"] == 10
        assert pb["constraint"] == 10
        assert pb["scenario"] == 10
        assert pb["trace"] == 10

    def test_per_guideline_breakdown(self, tmp_path: Path) -> None:
        """per_guideline list contains the expected guideline_id."""
        gid = "ssc_test"
        sgsc_dir = tmp_path / "sgsc_output"
        _make_sgsc_output(sgsc_dir, gid)

        registry_path = tmp_path / "reg.json"
        _make_registry(registry_path, [gid])

        summary_path = tmp_path / "summary.json"
        runner = _import_runner()
        original = runner._SUMMARY_PATH
        runner._SUMMARY_PATH = summary_path
        try:
            runner.main(
                [
                    "--all",
                    "--registry",
                    str(registry_path),
                    "--sgsc-dir",
                    str(sgsc_dir),
                    "--output-dir",
                    str(tmp_path / "packets"),
                ]
            )
        finally:
            runner._SUMMARY_PATH = original

        contract = json.loads(summary_path.read_text())
        ids = [g["guideline_id"] for g in contract["metrics"]["per_guideline"]]
        assert gid in ids

    def test_empty_sgsc_dir_graceful(self, tmp_path: Path) -> None:
        """No SGSC output files → warn status with 0 items, no crash."""
        gid = "ssc_test"
        sgsc_dir = tmp_path / "sgsc_output"
        # directory exists but is empty
        sgsc_dir.mkdir(parents=True)

        registry_path = tmp_path / "reg.json"
        _make_registry(registry_path, [gid])

        summary_path = tmp_path / "summary.json"
        runner = _import_runner()
        original = runner._SUMMARY_PATH
        runner._SUMMARY_PATH = summary_path
        try:
            rc = runner.main(
                [
                    "--all",
                    "--registry",
                    str(registry_path),
                    "--sgsc-dir",
                    str(sgsc_dir),
                    "--output-dir",
                    str(tmp_path / "packets"),
                ]
            )
        finally:
            runner._SUMMARY_PATH = original

        assert rc == 0, "empty dir should warn not fail"
        contract = json.loads(summary_path.read_text())
        assert contract["status"] == "warn"
        assert contract["metrics"]["total_items"] == 0

    def test_custom_item_counts(self, tmp_path: Path) -> None:
        """--n-atoms=5 limits atom bucket to 5 items."""
        gid = "ssc_test"
        sgsc_dir = tmp_path / "sgsc_output"
        _make_sgsc_output(sgsc_dir, gid)

        registry_path = tmp_path / "reg.json"
        _make_registry(registry_path, [gid])

        output_dir = tmp_path / "packets"
        summary_path = tmp_path / "summary.json"
        runner = _import_runner()
        original = runner._SUMMARY_PATH
        runner._SUMMARY_PATH = summary_path
        try:
            runner.main(
                [
                    "--all",
                    "--registry",
                    str(registry_path),
                    "--sgsc-dir",
                    str(sgsc_dir),
                    "--output-dir",
                    str(output_dir),
                    "--n-atoms",
                    "5",
                    "--n-constraints",
                    "5",
                    "--n-scenarios",
                    "5",
                    "--n-traces",
                    "5",
                ]
            )
        finally:
            runner._SUMMARY_PATH = original

        packet = json.loads((output_dir / gid / "packet.json").read_text())
        atom_items = [it for it in packet["items"] if it["item_type"] == "atom"]
        assert len(atom_items) == 5

    def test_multiple_guidelines(self, tmp_path: Path) -> None:
        """Two guidelines produce aggregated per_bucket counts."""
        gid1 = "ssc_test"
        gid2 = "aha_test"
        sgsc_dir = tmp_path / "sgsc_output"
        _make_sgsc_output(sgsc_dir, gid1)
        _make_sgsc_output(sgsc_dir, gid2)

        registry_path = tmp_path / "reg.json"
        _make_registry(registry_path, [gid1, gid2])

        output_dir = tmp_path / "packets"
        summary_path = tmp_path / "summary.json"
        runner = _import_runner()
        original = runner._SUMMARY_PATH
        runner._SUMMARY_PATH = summary_path
        try:
            runner.main(
                [
                    "--all",
                    "--registry",
                    str(registry_path),
                    "--sgsc-dir",
                    str(sgsc_dir),
                    "--output-dir",
                    str(output_dir),
                    "--n-atoms",
                    "5",
                    "--n-constraints",
                    "5",
                    "--n-scenarios",
                    "5",
                    "--n-traces",
                    "5",
                ]
            )
        finally:
            runner._SUMMARY_PATH = original

        contract = json.loads(summary_path.read_text())
        assert contract["metrics"]["guidelines_processed"] == 2
        # Each guideline contributes 5 of each bucket type
        pb = contract["metrics"]["per_bucket"]
        assert pb["atom"] == 10
        assert pb["constraint"] == 10
        assert pb["scenario"] == 10
        assert pb["trace"] == 10
