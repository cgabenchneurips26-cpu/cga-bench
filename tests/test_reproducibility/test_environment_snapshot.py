"""Tests for EnvironmentSnapshot reproducibility metadata capture."""

import sys
import platform

import pytest

from cga_bench.eval_harness.environment_snapshot import EnvironmentSnapshot


class TestEnvironmentSnapshot:
    """Test EnvironmentSnapshot.capture() and serialization."""

    def test_capture_returns_snapshot(self):
        snap = EnvironmentSnapshot.capture()
        assert isinstance(snap, EnvironmentSnapshot)

    def test_python_version_present(self):
        snap = EnvironmentSnapshot.capture()
        assert sys.version in snap.python_version

    def test_platform_fields(self):
        snap = EnvironmentSnapshot.capture()
        assert snap.platform_system == platform.system()
        assert snap.platform_machine == platform.machine()
        assert snap.platform_release == platform.release()

    def test_git_commit_is_string(self):
        snap = EnvironmentSnapshot.capture()
        assert isinstance(snap.git_commit, str)
        # Either a 40-char hex hash or "unknown"
        assert len(snap.git_commit) == 40 or snap.git_commit == "unknown"

    def test_git_branch_is_string(self):
        snap = EnvironmentSnapshot.capture()
        assert isinstance(snap.git_branch, str)
        assert len(snap.git_branch) > 0

    def test_git_dirty_is_bool(self):
        snap = EnvironmentSnapshot.capture()
        assert isinstance(snap.git_dirty, bool)

    def test_dependencies_dict(self):
        snap = EnvironmentSnapshot.capture()
        assert isinstance(snap.dependencies, dict)
        # Should have at least a few packages installed
        assert len(snap.dependencies) > 0

    def test_to_dict(self):
        snap = EnvironmentSnapshot.capture()
        d = snap.to_dict()
        assert isinstance(d, dict)
        assert "git_commit" in d
        assert "python_version" in d
        assert "dependencies" in d
        assert "platform_system" in d

    def test_to_json(self):
        snap = EnvironmentSnapshot.capture()
        j = snap.to_json()
        assert isinstance(j, str)
        import json
        parsed = json.loads(j)
        assert parsed["platform_system"] == platform.system()

    def test_cuda_version_optional(self):
        snap = EnvironmentSnapshot.capture()
        # CUDA may or may not be available
        assert snap.cuda_version is None or isinstance(snap.cuda_version, str)

    def test_cga_bench_version(self):
        snap = EnvironmentSnapshot.capture()
        assert isinstance(snap.cga_bench_version, str)
