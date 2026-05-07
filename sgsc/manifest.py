"""Dataset manifest for SGSC benchmark — single source of truth for scenario counts.

Provides a frozen ``BenchmarkManifest`` with self-consistency validation,
hash-based artifact drift detection, and a round-trip-serialisable schema.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ------------------------------------------------------------------
# Core model
# ------------------------------------------------------------------


class BenchmarkManifest(BaseModel):
    """Frozen manifest for one release of the SGSC benchmark.

    Attributes:
        benchmark_version: Version tag, e.g. ``"sgsc_v1"``.
        scenario_count: Counts keyed by ``public``, ``private``, ``manual``, ``auto``.
        episode_formula: Keys ``models``, ``scenarios``, ``runs``, ``expected_episodes``.
        artifact_hashes: Mapping of artifact name to SHA-256 hex digest.
    """

    model_config = ConfigDict(frozen=True)

    benchmark_version: str = Field(..., description="Version tag, e.g. 'sgsc_v1'")
    scenario_count: dict[str, int] = Field(
        ...,
        description="Scenario counts: public, private, manual, auto",
    )
    episode_formula: dict[str, int] = Field(
        ...,
        description="Episode formula: models, scenarios, runs, expected_episodes",
    )
    artifact_hashes: dict[str, str] = Field(
        default_factory=dict,
        description="Artifact name -> SHA-256 hex digest",
    )

    @model_validator(mode="after")
    def _check_episode_consistency(self) -> BenchmarkManifest:
        """Validate that expected_episodes == models * scenarios * runs."""
        formula = self.episode_formula
        required = {"models", "scenarios", "runs", "expected_episodes"}
        missing = required - formula.keys()
        if missing:
            raise ValueError(f"episode_formula missing keys: {missing}")
        computed = formula["models"] * formula["scenarios"] * formula["runs"]
        if computed != formula["expected_episodes"]:
            raise ValueError(
                f"episode_formula inconsistency: "
                f"{formula['models']}*{formula['scenarios']}*{formula['runs']}"
                f"={computed} != expected_episodes={formula['expected_episodes']}"
            )
        return self


# ------------------------------------------------------------------
# Hash utilities
# ------------------------------------------------------------------


def compute_artifact_hash(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file's binary content.

    Args:
        path: Absolute or relative path to the artifact file.

    Returns:
        Lowercase SHA-256 hex string.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


# ------------------------------------------------------------------
# Builder
# ------------------------------------------------------------------


def build_manifest(
    benchmark_version: str,
    scenario_count: dict[str, int],
    episode_formula: dict[str, int],
    artifacts_dir: Path,
    artifact_names: list[str],
) -> BenchmarkManifest:
    """Construct a BenchmarkManifest by hashing artifacts in a directory.

    Args:
        benchmark_version: Version tag string.
        scenario_count: Dict with keys public, private, manual, auto.
        episode_formula: Dict with keys models, scenarios, runs, expected_episodes.
        artifacts_dir: Directory containing artifact files.
        artifact_names: List of filenames (relative to ``artifacts_dir``) to hash.

    Returns:
        A frozen BenchmarkManifest with computed artifact hashes.
    """
    hashes: dict[str, str] = {}
    for name in artifact_names:
        artifact_path = artifacts_dir / name
        if artifact_path.exists():
            hashes[name] = compute_artifact_hash(artifact_path)
    return BenchmarkManifest(
        benchmark_version=benchmark_version,
        scenario_count=scenario_count,
        episode_formula=episode_formula,
        artifact_hashes=hashes,
    )


# ------------------------------------------------------------------
# Verifier
# ------------------------------------------------------------------


def verify_manifest(
    manifest: BenchmarkManifest,
    artifacts_dir: Path,
) -> tuple[bool, list[str]]:
    """Recompute artifact hashes and compare against the manifest.

    Args:
        manifest: The manifest whose hashes will be verified.
        artifacts_dir: Directory where artifact files are stored.

    Returns:
        A tuple ``(ok, mismatches)`` where ``ok`` is ``True`` when all hashes
        match and ``mismatches`` is a list of human-readable mismatch messages.
    """
    mismatches: list[str] = []
    for name, expected_hash in manifest.artifact_hashes.items():
        artifact_path = artifacts_dir / name
        if not artifact_path.exists():
            mismatches.append(f"MISSING  {artifact_path}")
            continue
        actual_hash = compute_artifact_hash(artifact_path)
        if actual_hash != expected_hash:
            mismatches.append(
                f"DRIFT    {artifact_path}\n"
                f"  expected: {expected_hash}\n"
                f"  actual:   {actual_hash}"
            )
    return (len(mismatches) == 0, mismatches)


# ------------------------------------------------------------------
# JSON round-trip helpers
# ------------------------------------------------------------------


def manifest_to_dict(manifest: BenchmarkManifest) -> dict:
    """Serialise a manifest to a plain dict (JSON-safe).

    Args:
        manifest: Manifest to serialise.

    Returns:
        Dict representation suitable for ``json.dumps``.
    """
    return manifest.model_dump()


def manifest_from_dict(data: dict) -> BenchmarkManifest:
    """Deserialise a manifest from a plain dict.

    Args:
        data: Dict previously produced by ``manifest_to_dict`` or loaded from JSON.

    Returns:
        Validated BenchmarkManifest instance.
    """
    return BenchmarkManifest.model_validate(data)


def load_manifest(path: Path) -> BenchmarkManifest:
    """Load a manifest from a JSON file.

    Args:
        path: Path to ``manifest.json``.

    Returns:
        Validated BenchmarkManifest instance.
    """
    data = json.loads(path.read_text())
    return manifest_from_dict(data)
