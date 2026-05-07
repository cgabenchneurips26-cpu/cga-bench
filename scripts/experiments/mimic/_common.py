"""Shared utilities for the MIMIC-IV augmentation pipeline.

Implements the contract-required summary-JSON format, MIMIC data location
resolution (CSV.gz default; postgres optional via MIMIC_PG_DSN env-var),
git-sha + mimic-version stamping, and the two ActionNormalizer profiles
needed by Phase 2 (`current` vs `strict`).

All paths are anchored to the cga_bench repo root.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
MIMIC_LOCAL_ROOT = REPO_ROOT / "data" / "mimic_iv_local"
MIMIC_DEMO_ROOT = REPO_ROOT / "data" / "mimic-iv-demo"
EVIDENCE_ROOT = REPO_ROOT / "evidence_pack" / "mimic_iv"


def repo_root() -> Path:
    """Return the cga_bench repo root."""
    return REPO_ROOT


def git_sha() -> str:
    """Short HEAD sha; returns 'unknown' on detached / non-git checkouts."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT),
            stderr=subprocess.DEVNULL,
        )
        return out.decode("ascii").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def mimic_version(data_dir: Path | None = None) -> str:
    """Resolve MIMIC-IV version. Reads MIMIC_VERSION env-var first, then
    looks for a `VERSION` file under data_dir, then falls back to 'demo'
    if reading from data/mimic-iv-demo/, else 'unknown'.
    """
    env = os.environ.get("MIMIC_VERSION")
    if env:
        return env
    root = data_dir or _resolve_data_root()
    version_file = root / "VERSION"
    if version_file.is_file():
        return version_file.read_text().strip()
    if root == MIMIC_DEMO_ROOT:
        return "demo"
    return "unknown"


def _resolve_data_root() -> Path:
    """Pick a MIMIC data root to read from.

    Priority:
      1. ``MIMIC_DATA_DIR`` env-var (absolute path).
      2. ``data/mimic_iv_local/`` if it contains hosp/.
      3. ``data/mimic-iv-demo/`` (always available; used for smoke tests).
    """
    env = os.environ.get("MIMIC_DATA_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    if (MIMIC_LOCAL_ROOT / "hosp").is_dir():
        return MIMIC_LOCAL_ROOT
    return MIMIC_DEMO_ROOT


def resolve_mimic_root(prefer_full: bool = True) -> Path:
    """Return the MIMIC-IV data root that scripts should read from.

    Args:
        prefer_full: If True, prefer ``data/mimic_iv_local/`` (full v3.1)
            over ``data/mimic-iv-demo/``. If the full path is absent, fall
            back to the demo dataset and print a warning to stderr.
    """
    root = _resolve_data_root()
    if not prefer_full:
        return MIMIC_DEMO_ROOT
    if root == MIMIC_DEMO_ROOT and prefer_full:
        import sys

        print(
            f"[mimic._common] WARNING: full MIMIC-IV not found at {MIMIC_LOCAL_ROOT}; "
            f"falling back to demo dataset. Sanity gates will fail by design.",
            file=sys.stderr,
        )
    return root


def read_mimic_csv(
    table: str, subdir: str = "hosp", root: Path | None = None, **read_kwargs: Any
) -> pd.DataFrame:
    """Read a MIMIC-IV table by name, transparently handling gzipped vs plain CSV.

    Tries ``<root>/<subdir>/<table>.csv.gz`` first, then ``.csv``. Errors out if
    neither is present.

    Args:
        table: Table name without extension, e.g. ``patients``.
        subdir: Either ``hosp`` or ``icu``.
        root: MIMIC root; defaults to ``resolve_mimic_root()``.
        **read_kwargs: Extra kwargs forwarded to ``pandas.read_csv``.
    """
    if root is None:
        root = resolve_mimic_root()
    base = root / subdir / table
    gz = base.with_suffix(".csv.gz")
    plain = base.with_suffix(".csv")
    if gz.is_file():
        return pd.read_csv(gz, compression="gzip", **read_kwargs)
    if plain.is_file():
        return pd.read_csv(plain, **read_kwargs)
    raise FileNotFoundError(
        f"MIMIC table not found: looked for {gz} and {plain}. "
        f"Drop the full v3.1 download into {MIMIC_LOCAL_ROOT}/ or set "
        f"MIMIC_DATA_DIR to a path containing hosp/ and icu/ subdirs."
    )


def cohort_hash(parquet_path: Path) -> str:
    """SHA-256 of a parquet file, used in MANIFEST.json for reproducibility."""
    h = hashlib.sha256()
    with open(parquet_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class PhaseSummary:
    """Required shape of every phase script's summary JSON."""

    script_name: str
    phase: str
    n_episodes: int = 0
    n_excluded: int = 0
    exclusion_breakdown: dict[str, int] = field(default_factory=dict)
    seed: int = 0
    git_sha: str = ""
    mimic_version: str = ""
    wall_time_s: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def write(self, out_dir: Path) -> Path:
        """Write the summary JSON. Returns the written path."""
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.script_name}.summary.json"
        payload: dict[str, Any] = {
            "script_name": self.script_name,
            "phase": self.phase,
            "n_episodes": self.n_episodes,
            "n_excluded": self.n_excluded,
            "exclusion_breakdown": self.exclusion_breakdown,
            "seed": self.seed,
            "git_sha": self.git_sha,
            "mimic_version": self.mimic_version,
            "wall_time_s": round(self.wall_time_s, 3),
            **self.extra,
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")
        return path


class GateFailure(Exception):
    """Raised when a Phase sanity gate fails. Caller must HALT and append
    a diagnosis to KNOWN_ISSUES.md per the source contract.
    """


def assert_gate(condition: bool, gate_name: str, detail: str) -> None:
    """Raise GateFailure if the condition is False.

    Use ``halt_and_log`` when you also want the reason persisted to
    KNOWN_ISSUES.md from a script's main(). This helper is a pure-Python
    fail-fast gate intended for tests and phase-script sanity blocks.
    """
    if not condition:
        raise GateFailure(f"[GATE-FAIL] {gate_name}: {detail}")


def halt_and_log(gate_name: str, detail: str, known_issues_section: str = "6") -> None:
    """Append a HALT entry to KNOWN_ISSUES.md and re-raise as GateFailure.

    The caller is expected to have already written its summary JSON with
    enough breakdown info that a reader can reconstruct the failure.
    """
    ki_path = REPO_ROOT / "KNOWN_ISSUES.md"
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    block = (
        f"\n### {known_issues_section}-HALT.{stamp} — {gate_name}\n"
        f"- **Detail**: {detail}\n"
        f"- **Action required**: investigate root cause; do NOT tune the gate.\n"
    )
    if ki_path.is_file():
        with open(ki_path, "a") as fh:
            fh.write(block)
    raise GateFailure(f"[HALT] {gate_name}: {detail}")


# ---- ActionNormalizer profiles for Phase 2 ----------------------------------


def build_normalizer(mode: str) -> Any:
    """Construct an ActionNormalizer in either `current` or `strict` mode.

    `current` = full mappings (direct + abbreviation + pattern + fuzzy).
    `strict`  = direct + abbreviation only (no pattern rules, no fuzzy).

    Implements Risk 6-3 from KNOWN_ISSUES.md.
    """
    from cga_bench.assessor_core.action_normalizer import ActionNormalizer

    if mode not in {"current", "strict"}:
        raise ValueError(f"normalizer mode must be 'current' or 'strict', got {mode!r}")

    nm = ActionNormalizer()
    if mode == "strict":
        # Disable pattern rules and fuzzy matching by replacing them with
        # empty stand-ins. We don't mutate the underlying class; we mutate
        # the instance attributes only.
        for attr in ("pattern_rules", "_pattern_rules"):
            if hasattr(nm, attr):
                setattr(nm, attr, [])
        for attr in ("fuzzy_threshold",):
            if hasattr(nm, attr):
                setattr(nm, attr, 1.0)  # require exact match
    return nm


# ---- Postgres path (unverified; opt-in via MIMIC_PG_DSN) --------------------


def maybe_pg_engine() -> Any | None:
    """Return a SQLAlchemy engine if MIMIC_PG_DSN is set, else None.

    The CSV.gz path is the default and verified. The postgres path is
    provided for owner convenience but is unverified end-to-end.
    """
    dsn = os.environ.get("MIMIC_PG_DSN")
    if not dsn:
        return None
    try:
        from sqlalchemy import create_engine

        return create_engine(dsn)
    except ImportError:
        return None
