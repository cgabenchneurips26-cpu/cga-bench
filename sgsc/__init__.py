"""Source-Grounded Scenario Compiler (SGSC).

Structured intermediate representation and coverage-optimized scenario
generation for CGA-Bench clinical guideline adherence benchmarking.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["SGSC_ROOT", "__version__"]

SGSC_ROOT = Path(__file__).resolve().parent

_version_file = SGSC_ROOT / "VERSION"
__version__: str = _version_file.read_text().strip() if _version_file.exists() else "0.0.0"
