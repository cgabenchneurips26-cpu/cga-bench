"""
Environment snapshot for full reproducibility tracking.

Captures git state, Python version, platform info, CUDA version,
and installed package versions at experiment runtime.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
import subprocess
import sys
import platform
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class EnvironmentSnapshot:
    """Complete environment metadata for reproducibility."""

    git_commit: str
    git_branch: str
    git_dirty: bool
    python_version: str
    platform_system: str
    platform_release: str
    platform_machine: str
    cuda_version: Optional[str]
    cga_bench_version: str
    dependencies: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def capture(cls) -> "EnvironmentSnapshot":
        """Capture current environment state."""
        return cls(
            git_commit=cls._get_git_commit(),
            git_branch=cls._get_git_branch(),
            git_dirty=cls._is_git_dirty(),
            python_version=sys.version,
            platform_system=platform.system(),
            platform_release=platform.release(),
            platform_machine=platform.machine(),
            cuda_version=cls._get_cuda_version(),
            cga_bench_version=cls._get_cga_bench_version(),
            dependencies=cls._get_dependencies(),
        )

    @staticmethod
    def _get_git_commit() -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "unknown"

    @staticmethod
    def _get_git_branch() -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "unknown"

    @staticmethod
    def _is_git_dirty() -> bool:
        try:
            output = subprocess.check_output(
                ["git", "status", "--porcelain"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            return bool(output)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def _get_cuda_version() -> Optional[str]:
        try:
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                stderr=subprocess.DEVNULL,
            ).decode().strip()
            return output.split("\n")[0] if output else None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    @staticmethod
    def _get_cga_bench_version() -> str:
        try:
            from cga_bench import __version__
            return __version__
        except ImportError:
            return "unknown"

    @staticmethod
    def _get_dependencies() -> Dict[str, str]:
        try:
            output = subprocess.check_output(
                [sys.executable, "-m", "pip", "freeze"],
                stderr=subprocess.DEVNULL,
            ).decode()
            deps: Dict[str, str] = {}
            for line in output.strip().split("\n"):
                if "==" in line:
                    pkg, ver = line.split("==", 1)
                    deps[pkg.strip()] = ver.strip()
            return deps
        except (subprocess.CalledProcessError, FileNotFoundError):
            return {}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
