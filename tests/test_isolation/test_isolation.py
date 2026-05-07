"""Scorer-agent isolation and canary leakage tests."""
import importlib
import tempfile
from pathlib import Path

import pytest

# Add scripts to path for import
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "ci"))
from leakage_scan import generate_canaries, scan_transcripts


class TestExtrasConceptualSeparation:
    """Verify scorer and agent modules have separate import paths."""

    def test_scorer_modules_importable(self):
        """cpg_engine and assessor_core are scorer-side modules."""
        mod1 = importlib.import_module("cga_bench.cpg_engine")
        mod2 = importlib.import_module("cga_bench.assessor_core")
        assert mod1 is not None
        assert mod2 is not None

    def test_agent_modules_importable(self):
        """agent_runner and agent_rules are agent-side modules."""
        mod1 = importlib.import_module("cga_bench.agent_runner")
        mod2 = importlib.import_module("cga_bench.agent_rules")
        assert mod1 is not None
        assert mod2 is not None

    def test_agent_does_not_import_cpg_engine_directly(self):
        """Oracle agent should use agent_rules, not cpg_engine."""
        import ast
        oracle_path = Path(__file__).parent.parent.parent / "agent_runner" / "oracle_agent.py"
        if not oracle_path.exists():
            pytest.skip("oracle_agent.py not found")
        source = oracle_path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                if "cpg_engine" in module:
                    pytest.fail(f"oracle_agent.py imports cpg_engine: {module}")


class TestCanaryScan:
    """Canary-based leakage detection tests."""

    def test_generate_canaries_unique(self):
        canaries = generate_canaries(10)
        assert len(canaries) == 10
        assert len(set(canaries)) == 10
        assert all(c.startswith("CGA_CANARY__") for c in canaries)

    def test_scan_no_hits_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write clean file
            (Path(tmpdir) / "clean.json").write_text('{"action": "order_lab"}')
            canaries = generate_canaries(3)
            result = scan_transcripts(tmpdir, canaries)
            assert result["passed"] is True
            assert result["total_hits"] == 0

    def test_scan_with_hit_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            canaries = generate_canaries(3)
            # Inject one canary into a file
            (Path(tmpdir) / "leaked.json").write_text(f'{{"data": "{canaries[0]}"}}')
            result = scan_transcripts(tmpdir, canaries)
            assert result["passed"] is False
            assert result["total_hits"] == 1
            assert result["hits"][canaries[0]] == 1

    def test_scan_nonexistent_dir_passes(self):
        result = scan_transcripts("/nonexistent/path", generate_canaries(2))
        assert result["passed"] is True


class TestRequirementsIsolation:
    """Verify requirements files don't overlap on forbidden modules."""

    REPO_ROOT = Path(__file__).parent.parent.parent

    def _read_requirements(self, filename: str) -> list[str]:
        path = self.REPO_ROOT / filename
        if not path.exists():
            pytest.skip(f"{filename} not found")
        lines = path.read_text().splitlines()
        # Strip comments and blank lines, lowercase package names
        return [
            line.strip().lower()
            for line in lines
            if line.strip() and not line.strip().startswith("#")
        ]

    def test_scorer_requirements_has_no_agent_packages(self):
        """requirements-scorer.txt must not contain agent-only packages."""
        scorer_reqs = self._read_requirements("requirements-scorer.txt")
        forbidden_in_scorer = ["httpx", "requests", "aiohttp"]
        for pkg in scorer_reqs:
            pkg_name = pkg.split(">=")[0].split("==")[0].split("<=")[0].strip()
            assert pkg_name not in forbidden_in_scorer, (
                f"requirements-scorer.txt contains agent-only package: {pkg_name}"
            )

    def test_agent_requirements_present(self):
        """requirements-agent.txt must exist and contain httpx."""
        agent_reqs = self._read_requirements("requirements-agent.txt")
        pkg_names = [
            r.split(">=")[0].split("==")[0].split("<=")[0].strip()
            for r in agent_reqs
        ]
        assert "httpx" in pkg_names, (
            "requirements-agent.txt must contain httpx for agent HTTP calls"
        )

    def test_scorer_requirements_has_pydantic_and_yaml(self):
        """requirements-scorer.txt must have pydantic and pyyaml."""
        scorer_reqs = self._read_requirements("requirements-scorer.txt")
        pkg_names = [
            r.split(">=")[0].split("==")[0].split("<=")[0].strip()
            for r in scorer_reqs
        ]
        assert "pydantic" in pkg_names, "requirements-scorer.txt missing pydantic"
        assert "pyyaml" in pkg_names, "requirements-scorer.txt missing pyyaml"


class TestDockerfileScorerIsolation:
    """Verify Dockerfile.scorer does not COPY agent-side code."""

    REPO_ROOT = Path(__file__).parent.parent.parent
    DOCKERFILE_SCORER = REPO_ROOT / "Dockerfile.scorer"

    def _read_dockerfile(self) -> str:
        if not self.DOCKERFILE_SCORER.exists():
            pytest.skip("Dockerfile.scorer not found")
        return self.DOCKERFILE_SCORER.read_text()

    def test_dockerfile_scorer_does_not_copy_agent_runner(self):
        content = self._read_dockerfile()
        # Ensure no COPY line includes agent_runner
        copy_lines = [
            line for line in content.splitlines()
            if line.strip().upper().startswith("COPY") and "agent_runner" in line
        ]
        assert copy_lines == [], (
            f"Dockerfile.scorer must not COPY agent_runner/: {copy_lines}"
        )

    def test_dockerfile_scorer_does_not_copy_agent_rules(self):
        content = self._read_dockerfile()
        copy_lines = [
            line for line in content.splitlines()
            if line.strip().upper().startswith("COPY") and "agent_rules" in line
        ]
        assert copy_lines == [], (
            f"Dockerfile.scorer must not COPY agent_rules/: {copy_lines}"
        )

    def test_dockerfile_scorer_does_not_copy_tool_api(self):
        content = self._read_dockerfile()
        copy_lines = [
            line for line in content.splitlines()
            if line.strip().upper().startswith("COPY") and "tool_api" in line
        ]
        assert copy_lines == [], (
            f"Dockerfile.scorer must not COPY tool_api/: {copy_lines}"
        )

    def test_dockerfile_scorer_copies_cpg_engine(self):
        content = self._read_dockerfile()
        copy_lines = [
            line for line in content.splitlines()
            if line.strip().upper().startswith("COPY") and "cpg_engine" in line
        ]
        assert copy_lines, "Dockerfile.scorer must COPY cpg_engine/"

    def test_dockerfile_scorer_copies_assessor_core(self):
        content = self._read_dockerfile()
        copy_lines = [
            line for line in content.splitlines()
            if line.strip().upper().startswith("COPY") and "assessor_core" in line
        ]
        assert copy_lines, "Dockerfile.scorer must COPY assessor_core/"
