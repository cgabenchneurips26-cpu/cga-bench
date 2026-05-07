"""CI audit script: verify SGSC benchmark manifest artifact hashes.

Loads a manifest JSON file, recomputes SHA-256 hashes of all listed
artifacts, and reports any drift. Exits 0 when all hashes match, 1 on
drift, and (optionally) 0 when the manifest file itself is absent.

Usage::

    python scripts/ci/audit_manifest.py [manifest_path] [--allow-missing]

If ``manifest_path`` is omitted, defaults to ``sgsc/v1/manifest.json``
relative to the repository root (parent of this script's grandparent).

The ``--allow-missing`` flag (TG-V5) makes the missing-manifest case exit
0 with a warning to stderr.  This is the recommended posture during the
data-sweep window when ``manifest.json`` has not yet been generated:
without the flag, every CI run during that window would fail this step.
After the manifest lands, drop the flag to restore strict drift detection.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root without installing the package.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sgsc.manifest import load_manifest, verify_manifest  # noqa: E402

_DEFAULT_MANIFEST_PATH = _REPO_ROOT / "sgsc" / "v1" / "manifest.json"
_ALLOW_MISSING_FLAG = "--allow-missing"


def _parse_argv(argv: list[str]) -> tuple[Path, bool]:
    """Parse argv into (manifest_path, allow_missing).

    Args:
        argv: ``sys.argv`` (index 0 is script name).

    Returns:
        Tuple of resolved manifest Path and the allow_missing flag.
    """
    positional: list[str] = []
    allow_missing = False
    for tok in argv[1:]:
        if tok == _ALLOW_MISSING_FLAG:
            allow_missing = True
        else:
            positional.append(tok)

    if positional:
        manifest_path = Path(positional[0]).resolve()
    else:
        manifest_path = _DEFAULT_MANIFEST_PATH

    return manifest_path, allow_missing


def main(argv: list[str]) -> int:
    """Entry point for manifest audit.

    Args:
        argv: Command-line arguments (``sys.argv`` convention).

    Returns:
        0 if all hashes match (or manifest missing under ``--allow-missing``),
        1 on drift, load error, or missing-without-flag.
    """
    manifest_path, allow_missing = _parse_argv(argv)

    if not manifest_path.exists():
        if allow_missing:
            print(
                f"manifest audit SKIPPED — file not found: {manifest_path} "
                f"(--allow-missing in effect)",
                file=sys.stderr,
            )
            return 0
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    try:
        manifest = load_manifest(manifest_path)
    except Exception as exc:
        print(f"ERROR: failed to load manifest: {exc}", file=sys.stderr)
        return 1

    artifacts_dir = manifest_path.parent
    ok, mismatches = verify_manifest(manifest, artifacts_dir)

    if ok:
        n = len(manifest.artifact_hashes)
        print(f"manifest audit PASSED — {n} artifact(s) verified ({manifest_path})")
        return 0

    print(f"manifest audit FAILED — {len(mismatches)} issue(s) detected:", file=sys.stderr)
    for msg in mismatches:
        print(f"  {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
