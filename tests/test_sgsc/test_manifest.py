"""Tests for sgsc/manifest.py — BenchmarkManifest schema, hashing, verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from sgsc.manifest import (
    BenchmarkManifest,
    build_manifest,
    compute_artifact_hash,
    manifest_from_dict,
    manifest_to_dict,
    verify_manifest,
)

# ------------------------------------------------------------------
# Shared fixtures
# ------------------------------------------------------------------

VALID_SCENARIO_COUNT: dict[str, int] = {
    "public": 706,
    "private": 706,
    "manual": 105,
    "auto": 601,
}

VALID_EPISODE_FORMULA: dict[str, int] = {
    "models": 9,
    "scenarios": 706,
    "runs": 3,
    "expected_episodes": 19062,
}


def _make_manifest(**overrides: object) -> BenchmarkManifest:
    """Create a minimal valid manifest, optionally overriding fields."""
    kwargs: dict = dict(
        benchmark_version="sgsc_v1",
        scenario_count=VALID_SCENARIO_COUNT.copy(),
        episode_formula=VALID_EPISODE_FORMULA.copy(),
        artifact_hashes={},
    )
    kwargs.update(overrides)
    return BenchmarkManifest(**kwargs)


# ------------------------------------------------------------------
# Self-consistency validation
# ------------------------------------------------------------------


class TestManifestSelfConsistency:
    def test_valid_formula_passes(self) -> None:
        """9 * 706 * 3 == 19062 should construct without error."""
        manifest = _make_manifest()
        assert manifest.episode_formula["expected_episodes"] == 19062

    def test_mismatch_raises_value_error(self) -> None:
        """Wrong expected_episodes must raise ValueError."""
        bad_formula = {
            "models": 9,
            "scenarios": 706,
            "runs": 3,
            "expected_episodes": 99999,
        }
        with pytest.raises(ValueError, match="inconsistency"):
            _make_manifest(episode_formula=bad_formula)

    def test_missing_formula_key_raises_value_error(self) -> None:
        """Omitting a required key in episode_formula raises ValueError."""
        incomplete_formula = {"models": 9, "scenarios": 706, "runs": 3}
        with pytest.raises(ValueError, match="missing keys"):
            _make_manifest(episode_formula=incomplete_formula)

    def test_manifest_is_frozen(self) -> None:
        """Frozen model must reject attribute mutation."""
        manifest = _make_manifest()
        with pytest.raises(Exception):
            manifest.benchmark_version = "tampered"  # type: ignore[misc]


# ------------------------------------------------------------------
# Artifact hash
# ------------------------------------------------------------------


class TestComputeArtifactHash:
    def test_matches_hashlib_sha256(self, tmp_path: Path) -> None:
        """compute_artifact_hash must equal hashlib.sha256 on same bytes."""
        content = b"sgsc_v1 canonical scenario bytes"
        artifact = tmp_path / "artifact.jsonl"
        artifact.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        actual = compute_artifact_hash(artifact)

        assert actual == expected

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        """Two files with different content must produce different hashes."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"alpha")
        f2.write_bytes(b"beta")
        assert compute_artifact_hash(f1) != compute_artifact_hash(f2)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        """Missing file must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            compute_artifact_hash(tmp_path / "nonexistent.bin")


# ------------------------------------------------------------------
# verify_manifest drift detection
# ------------------------------------------------------------------


class TestVerifyManifestDetectsDrift:
    def _setup_artifacts(self, tmp_path: Path) -> tuple[BenchmarkManifest, Path]:
        """Write two artifact files and build a manifest over them."""
        f1 = tmp_path / "recommendation_atoms.jsonl"
        f2 = tmp_path / "scenarios_public.jsonl"
        f1.write_bytes(b"atom data v1")
        f2.write_bytes(b"scenario data v1")

        manifest = build_manifest(
            benchmark_version="sgsc_v1",
            scenario_count=VALID_SCENARIO_COUNT,
            episode_formula=VALID_EPISODE_FORMULA,
            artifacts_dir=tmp_path,
            artifact_names=["recommendation_atoms.jsonl", "scenarios_public.jsonl"],
        )
        return manifest, tmp_path

    def test_clean_dir_returns_ok(self, tmp_path: Path) -> None:
        """verify_manifest returns (True, []) when files are unchanged."""
        manifest, artifacts_dir = self._setup_artifacts(tmp_path)
        ok, mismatches = verify_manifest(manifest, artifacts_dir)
        assert ok is True
        assert mismatches == []

    def test_mutated_file_returns_false_with_path(self, tmp_path: Path) -> None:
        """Mutating one artifact file must trigger a DRIFT mismatch entry."""
        manifest, artifacts_dir = self._setup_artifacts(tmp_path)

        # Mutate one artifact after the manifest was built
        mutated = artifacts_dir / "recommendation_atoms.jsonl"
        mutated.write_bytes(b"atom data TAMPERED")

        ok, mismatches = verify_manifest(manifest, artifacts_dir)
        assert ok is False
        assert len(mismatches) == 1
        assert "recommendation_atoms.jsonl" in mismatches[0]
        assert "DRIFT" in mismatches[0]

    def test_missing_artifact_returns_false(self, tmp_path: Path) -> None:
        """A deleted artifact file must produce a MISSING mismatch entry."""
        manifest, artifacts_dir = self._setup_artifacts(tmp_path)

        (artifacts_dir / "scenarios_public.jsonl").unlink()

        ok, mismatches = verify_manifest(manifest, artifacts_dir)
        assert ok is False
        assert any("MISSING" in m for m in mismatches)


# ------------------------------------------------------------------
# Round-trip serialisation
# ------------------------------------------------------------------


class TestRoundTripSerialize:
    def test_dict_round_trip(self) -> None:
        """manifest_to_dict then manifest_from_dict must reproduce the manifest."""
        original = _make_manifest(
            artifact_hashes={"scenarios_public.jsonl": "abc123def456"},
        )
        data = manifest_to_dict(original)
        restored = manifest_from_dict(data)
        assert restored == original

    def test_json_round_trip(self) -> None:
        """JSON serialise and deserialise must preserve all fields."""
        original = _make_manifest()
        json_str = json.dumps(manifest_to_dict(original))
        data = json.loads(json_str)
        restored = manifest_from_dict(data)
        assert restored.benchmark_version == original.benchmark_version
        assert restored.scenario_count == original.scenario_count
        assert restored.episode_formula == original.episode_formula

    def test_serialised_dict_is_json_safe(self) -> None:
        """manifest_to_dict output must serialise with json.dumps without error."""
        manifest = _make_manifest()
        # Should not raise
        serialised = json.dumps(manifest_to_dict(manifest))
        assert "sgsc_v1" in serialised


# ------------------------------------------------------------------
# CLI audit script (TG-V5: --allow-missing posture)
# ------------------------------------------------------------------


class TestAuditManifestCLI:
    """Tests for scripts/ci/audit_manifest.py argv parsing and exit codes."""

    def _import_audit_main(self):
        """Lazy-import the CLI script's main() function."""
        import importlib.util

        repo_root = Path(__file__).resolve().parent.parent.parent
        script_path = repo_root / "scripts" / "ci" / "audit_manifest.py"
        spec = importlib.util.spec_from_file_location("audit_manifest_cli", script_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.main, module._parse_argv  # type: ignore[attr-defined]

    def test_missing_manifest_exits_1_by_default(self, tmp_path: Path) -> None:
        """Without --allow-missing, missing manifest exits 1 (strict CI)."""
        main, _ = self._import_audit_main()
        nonexistent = tmp_path / "absent.json"
        rc = main(["audit_manifest.py", str(nonexistent)])
        assert rc == 1

    def test_missing_manifest_exits_0_with_allow_missing(self, tmp_path: Path) -> None:
        """With --allow-missing, missing manifest exits 0 (data-sweep window)."""
        main, _ = self._import_audit_main()
        nonexistent = tmp_path / "absent.json"
        rc = main(["audit_manifest.py", str(nonexistent), "--allow-missing"])
        assert rc == 0

    def test_present_manifest_with_allow_missing_still_runs_audit(
        self, tmp_path: Path
    ) -> None:
        """--allow-missing only affects the missing case; present manifests are still audited."""
        main, _ = self._import_audit_main()

        # Build a tiny artifact + manifest
        artifact = tmp_path / "scenarios_public.jsonl"
        artifact.write_text("payload\n")
        artifact_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest = _make_manifest(artifact_hashes={"scenarios_public.jsonl": artifact_hash})

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_to_dict(manifest)))

        rc = main(["audit_manifest.py", str(manifest_path), "--allow-missing"])
        assert rc == 0  # passes audit; flag does not override drift detection

    def test_drifted_artifact_still_fails_with_allow_missing(self, tmp_path: Path) -> None:
        """--allow-missing must NOT suppress real drift — only the missing-file case."""
        main, _ = self._import_audit_main()

        artifact = tmp_path / "scenarios_public.jsonl"
        artifact.write_text("original-bytes\n")

        manifest = _make_manifest(artifact_hashes={"scenarios_public.jsonl": "deadbeef"})
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_to_dict(manifest)))

        rc = main(["audit_manifest.py", str(manifest_path), "--allow-missing"])
        assert rc == 1  # drift still fails

    def test_argv_parser_extracts_flag_from_any_position(self) -> None:
        """--allow-missing must be recognised before or after the path argument."""
        _, parse_argv = self._import_audit_main()
        path_a, ok_a = parse_argv(["script", "/tmp/a.json", "--allow-missing"])
        path_b, ok_b = parse_argv(["script", "--allow-missing", "/tmp/a.json"])
        assert ok_a is True and ok_b is True
        assert path_a == path_b == Path("/tmp/a.json").resolve()
