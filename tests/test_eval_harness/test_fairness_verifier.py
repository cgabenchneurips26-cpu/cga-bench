"""Tests for FairnessVerifier (scoring-agent isolation enforcement)."""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cga_bench.eval_harness.fairness_verifier import (
    FairnessVerifier,
    ImportMonitor,
    IsolationConfig,
    StaticAnalyzer,
    ViolationRecord,
    verify_agent_source_files,
)


# ============================================================================
# IsolationConfig
# ============================================================================

class TestIsolationConfig:
    def test_default_forbidden_imports(self):
        cfg = IsolationConfig()
        assert "cga_bench.cpg_engine" in cfg.forbidden_imports
        assert "cga_bench.assessor_core" in cfg.forbidden_imports

    def test_default_allowed_imports(self):
        cfg = IsolationConfig()
        assert "cga_bench.agent_rules" in cfg.allowed_imports
        assert "cga_bench.tool_api" in cfg.allowed_imports

    def test_custom_config(self):
        cfg = IsolationConfig(
            forbidden_imports=["secret_module"],
            enforce_at_runtime=False,
        )
        assert cfg.forbidden_imports == ["secret_module"]
        assert cfg.enforce_at_runtime is False


# ============================================================================
# ImportMonitor
# ============================================================================

class TestImportMonitor:
    def test_start_stop_lifecycle(self):
        cfg = IsolationConfig(enforce_at_runtime=False)
        monitor = ImportMonitor(cfg)
        assert monitor._is_active is False
        monitor.start()
        assert monitor._is_active is True
        monitor.stop()
        assert monitor._is_active is False

    def test_double_start_safe(self):
        cfg = IsolationConfig(enforce_at_runtime=False)
        monitor = ImportMonitor(cfg)
        monitor.start()
        monitor.start()  # Should not crash
        assert monitor._is_active is True
        monitor.stop()

    def test_double_stop_safe(self):
        cfg = IsolationConfig(enforce_at_runtime=False)
        monitor = ImportMonitor(cfg)
        monitor.stop()  # Stop before start — safe
        monitor.start()
        monitor.stop()
        monitor.stop()  # Double stop — safe

    def test_violations_empty_initially(self):
        cfg = IsolationConfig()
        monitor = ImportMonitor(cfg)
        assert monitor.violations == []


# ============================================================================
# StaticAnalyzer
# ============================================================================

class TestStaticAnalyzer:
    def test_clean_file_no_violations(self, tmp_path):
        source = textwrap.dedent("""\
            import os
            from cga_bench.agent_rules.sepsis_rules import SepsisDecisionTable

            def decide():
                return []
        """)
        file = tmp_path / "clean_agent.py"
        file.write_text(source)

        analyzer = StaticAnalyzer(IsolationConfig())
        violations = analyzer.analyze_file(file)
        assert violations == []

    def test_forbidden_import_detected(self, tmp_path):
        source = textwrap.dedent("""\
            from cga_bench.cpg_engine.engine import CPGEngine

            def cheat():
                return CPGEngine()
        """)
        file = tmp_path / "cheating_agent.py"
        file.write_text(source)

        analyzer = StaticAnalyzer(IsolationConfig())
        violations = analyzer.analyze_file(file)
        assert len(violations) >= 1
        assert any(v.module_name == "cga_bench.cpg_engine.engine" for v in violations)

    def test_forbidden_direct_import_detected(self, tmp_path):
        source = textwrap.dedent("""\
            import cga_bench.assessor_core
        """)
        file = tmp_path / "direct_import.py"
        file.write_text(source)

        analyzer = StaticAnalyzer(IsolationConfig())
        violations = analyzer.analyze_file(file)
        assert len(violations) >= 1

    def test_allowed_import_not_flagged(self, tmp_path):
        source = textwrap.dedent("""\
            from cga_bench.agent_rules.decision_table import RuleBasedDecisionTable
            from cga_bench.tool_api.base import ToolAPI
        """)
        file = tmp_path / "allowed_agent.py"
        file.write_text(source)

        analyzer = StaticAnalyzer(IsolationConfig())
        violations = analyzer.analyze_file(file)
        assert violations == []

    def test_nonexistent_file_no_crash(self, tmp_path):
        analyzer = StaticAnalyzer(IsolationConfig())
        violations = analyzer.analyze_file(tmp_path / "nonexistent.py")
        assert violations == []

    def test_is_forbidden_import_exact_match(self):
        analyzer = StaticAnalyzer(IsolationConfig())
        assert analyzer._is_forbidden_import("cga_bench.cpg_engine") is True
        assert analyzer._is_forbidden_import("cga_bench.cpg_engine.engine") is True
        assert analyzer._is_forbidden_import("cga_bench.agent_rules") is False

    def test_is_forbidden_access(self):
        analyzer = StaticAnalyzer(IsolationConfig())
        assert analyzer._is_forbidden_access("cpg_engine.evaluate") is True
        assert analyzer._is_forbidden_access("assessor_core.violations") is True
        assert analyzer._is_forbidden_access("agent_rules.sepsis") is False


# ============================================================================
# FairnessVerifier
# ============================================================================

class TestFairnessVerifier:
    def test_default_init(self):
        v = FairnessVerifier()
        assert v.config is not None
        assert v.violations == []

    def test_custom_config(self):
        cfg = IsolationConfig(enforce_at_runtime=False)
        v = FairnessVerifier(config=cfg)
        assert v.config.enforce_at_runtime is False

    def test_verify_clean_module(self, tmp_path):
        source = "import os\n"
        f = tmp_path / "clean.py"
        f.write_text(source)
        v = FairnessVerifier()
        assert v.verify_agent_module(f) is True

    def test_verify_dirty_module(self, tmp_path):
        source = "from cga_bench.cpg_engine import engine\n"
        f = tmp_path / "dirty.py"
        f.write_text(source)
        v = FairnessVerifier()
        assert v.verify_agent_module(f) is False
        assert len(v.violations) >= 1

    def test_verify_agent_independence_clean(self):
        # Use spec=[] to prevent MagicMock from auto-creating forbidden attrs
        agent = MagicMock(spec=[
            "config", "get_independence_verification",
        ])
        agent.config.agent_id = "test_oracle"
        agent.get_independence_verification.return_value = {
            "uses_cpg_engine": False,
            "uses_assessor_core": False,
        }
        v = FairnessVerifier()
        result = v.verify_agent_independence(agent)
        assert result["is_independent"] is True
        assert "test_oracle" in v._verified_agents

    def test_verify_agent_independence_declares_cpg_engine(self):
        agent = MagicMock()
        agent.config.agent_id = "bad_agent"
        agent.get_independence_verification.return_value = {
            "uses_cpg_engine": True,
            "uses_assessor_core": False,
        }
        v = FairnessVerifier()
        result = v.verify_agent_independence(agent)
        assert result["is_independent"] is False
        assert any("cpg_engine" in viol for viol in result["violations"])

    def test_verify_agent_forbidden_attribute(self):
        agent = MagicMock(spec=[])
        agent.config = MagicMock()
        agent.config.agent_id = "attr_agent"
        agent.cpg_engine = "should_not_exist"
        # No get_independence_verification method
        v = FairnessVerifier()
        result = v.verify_agent_independence(agent)
        assert result["is_independent"] is False


# ============================================================================
# Experiment Fairness
# ============================================================================

class TestExperimentFairness:
    def test_fair_experiment(self):
        agent = MagicMock(spec=[
            "config", "get_independence_verification",
        ])
        agent.config.agent_id = "oracle"
        agent.config.budget_limit_tokens = 100000
        agent.config.budget_limit_tool_calls = 50
        agent.get_independence_verification.return_value = {
            "uses_cpg_engine": False,
            "uses_assessor_core": False,
        }
        v = FairnessVerifier()
        result = v.verify_experiment_fairness(
            agents={"oracle": agent},
            experiment_config={
                "experiment": {"experiment_id": "test_exp"},
                "budget": {
                    "enforce_budget_matching": True,
                    "budget_limit_tokens": 100000,
                },
            },
        )
        assert result["is_fair"] is True

    def test_unfair_budget_mismatch(self):
        agent = MagicMock()
        agent.config.agent_id = "rag"
        agent.config.budget_limit_tokens = 200000  # Different from experiment
        agent.config.budget_limit_tool_calls = None
        agent.get_independence_verification.return_value = {
            "uses_cpg_engine": False,
            "uses_assessor_core": False,
        }
        v = FairnessVerifier()
        result = v.verify_experiment_fairness(
            agents={"rag": agent},
            experiment_config={
                "experiment": {"experiment_id": "test_exp"},
                "budget": {
                    "enforce_budget_matching": True,
                    "budget_limit_tokens": 100000,
                },
            },
        )
        assert result["budget_matched"] is False
        assert result["is_fair"] is False


# ============================================================================
# get_summary
# ============================================================================

class TestGetSummary:
    def test_summary_empty(self):
        v = FairnessVerifier()
        summary = v.get_summary()
        assert summary["total_violations"] == 0
        assert summary["verified_agents"] == []
        assert summary["runtime_monitoring_active"] is False

    def test_summary_after_violations(self, tmp_path):
        source = "from cga_bench.cpg_engine import engine\n"
        f = tmp_path / "bad.py"
        f.write_text(source)
        v = FairnessVerifier()
        v.verify_agent_module(f)
        summary = v.get_summary()
        assert summary["total_violations"] >= 1
        assert "import" in summary["violations_by_type"]


# ============================================================================
# verify_agent_source_files (module-level function)
# ============================================================================

class TestVerifyAgentSourceFiles:
    def test_clean_directory(self, tmp_path):
        (tmp_path / "agent.py").write_text("import os\n")
        assert verify_agent_source_files(tmp_path) is True

    def test_dirty_directory(self, tmp_path):
        (tmp_path / "agent.py").write_text(
            "from cga_bench.cpg_engine.engine import CPGEngine\n"
        )
        assert verify_agent_source_files(tmp_path) is False

    def test_empty_directory(self, tmp_path):
        assert verify_agent_source_files(tmp_path) is True
