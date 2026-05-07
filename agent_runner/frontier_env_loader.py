"""Frontier API key loader.

Reads ``secrets/frontier_api_keys.env`` and exports the values into
``os.environ`` so the existing :mod:`agent_runner.llm_provider` env-driven
auth path works unchanged for OpenAI / Anthropic / Google / xAI / DeepSeek.

Safety contract:
    1. The env file is gitignored at ``secrets/.gitignore`` (whitelist).
    2. The loader rejects the file if its mode bits leak to group/other
       (chmod 400 or 600 are the only acceptable states).
    3. The loader never writes back; it only reads.

Usage::

    from agent_runner.frontier_env_loader import load_frontier_env
    load_frontier_env()  # exports OPENAI_API_KEY etc. into os.environ
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo-relative path to the env file. Resolved against the repo root that
# contains the ``secrets/`` directory; the loader walks up from this file
# until it finds it, so the loader works regardless of CWD.
_ENV_BASENAME = Path("secrets") / "frontier_api_keys.env"


def _find_repo_root() -> Path:
    """Walk up from this file until a directory containing ``secrets/`` is found."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "secrets").is_dir():
            return candidate
    raise FileNotFoundError(
        "Could not locate repo root with secrets/ directory while walking up "
        f"from {here}. Run from inside the cga_bench checkout."
    )


def load_frontier_env(*, override: bool = False) -> dict[str, str]:
    """Load secrets/frontier_api_keys.env into os.environ.

    Args:
        override: If False (default), existing ``os.environ`` keys win and
            file values are skipped for those keys. If True, file values
            overwrite the environment unconditionally.

    Returns:
        A dict mapping every non-empty KEY=VALUE pair from the file to its
        raw string value (also exported to os.environ subject to override).

    Raises:
        FileNotFoundError: env file missing.
        PermissionError:  file is too permissive (any group/other bit set).
    """
    repo = _find_repo_root()
    env_path = repo / _ENV_BASENAME
    if not env_path.exists():
        raise FileNotFoundError(
            f"Frontier API key file missing: {env_path}\n"
            f"  cp {repo / 'secrets' / 'frontier_api_keys.env.example'} {env_path}\n"
            f"  $EDITOR {env_path}\n"
            f"  chmod 400 {env_path}"
        )

    mode = env_path.stat().st_mode & 0o777
    if mode & 0o077:
        raise PermissionError(
            f"{env_path} is too permissive (mode={oct(mode)}). "
            f"Run: chmod 400 {env_path}"
        )

    parsed: dict[str, str] = {}
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        parsed[key] = value
        if value and (override or key not in os.environ):
            os.environ[key] = value
    return parsed


__all__ = ["load_frontier_env"]
