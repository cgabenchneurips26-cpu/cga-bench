"""Regression tests for Issue #5: Oracle domain detection.

Verifies that unknown domains raise ValueError instead of silently
defaulting to SepsisDecisionTable.
"""
from __future__ import annotations

from typing import Optional
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

import pytest


@dataclass
class MockOracleConfig:
    agent_id: str = "test_oracle"
    agent_type: str = "oracle"
    guideline_domain: str = "sepsis"
    budget_limit_tokens: Optional[int] = 100000
    budget_limit_tool_calls: Optional[int] = 50
    max_actions_per_step: int = 3
    enable_justification: bool = True
    use_llm: bool = False


class TestOracleDomainDetection:
    """Tests for Oracle agent domain validation."""

    def test_unknown_domain_raises_valueerror(self):
        """P6 재현: unknown domain → ValueError (was silent fallback)."""
        from cga_bench.agent_runner.oracle_agent import OracleAgent

        with pytest.raises(ValueError, match="Unknown domain"):
            OracleAgent(MockOracleConfig(guideline_domain="nonexistent_domain"))

    def test_unknown_domain_error_message_includes_valid_list(self):
        """ValueError message contains valid domain list for debugging."""
        from cga_bench.agent_runner.oracle_agent import OracleAgent

        with pytest.raises(ValueError, match="Valid domains"):
            OracleAgent(MockOracleConfig(guideline_domain="invalid"))

    def test_known_domain_sepsis(self):
        """Known domain 'sepsis' initializes without error."""
        from cga_bench.agent_runner.oracle_agent import OracleAgent

        agent = OracleAgent(MockOracleConfig(guideline_domain="sepsis"))
        assert agent.decision_table is not None

    def test_known_domain_chest_pain(self):
        """Known domain 'chest_pain' initializes without error."""
        from cga_bench.agent_runner.oracle_agent import OracleAgent

        agent = OracleAgent(MockOracleConfig(guideline_domain="chest_pain"))
        assert agent.decision_table is not None

    def test_known_domain_aha_stroke(self):
        """Known domain 'aha_stroke' initializes without error."""
        from cga_bench.agent_runner.oracle_agent import OracleAgent

        agent = OracleAgent(MockOracleConfig(guideline_domain="aha_stroke"))
        assert agent.decision_table is not None

    def test_known_domain_dka(self):
        """Known domain 'dka' initializes without error."""
        from cga_bench.agent_runner.oracle_agent import OracleAgent

        agent = OracleAgent(MockOracleConfig(guideline_domain="dka"))
        assert agent.decision_table is not None

    def test_known_domain_aki(self):
        """Known domain 'aki' initializes without error."""
        from cga_bench.agent_runner.oracle_agent import OracleAgent

        agent = OracleAgent(MockOracleConfig(guideline_domain="aki"))
        assert agent.decision_table is not None

    def test_case_insensitive_domain(self):
        """Domain lookup is case-insensitive."""
        from cga_bench.agent_runner.oracle_agent import OracleAgent

        agent = OracleAgent(MockOracleConfig(guideline_domain="SEPSIS"))
        assert agent.decision_table is not None

    def test_whitespace_stripped(self):
        """Domain lookup strips whitespace."""
        from cga_bench.agent_runner.oracle_agent import OracleAgent

        agent = OracleAgent(MockOracleConfig(guideline_domain="  sepsis  "))
        assert agent.decision_table is not None

    def test_impact_wrong_domain_no_longer_silent(self):
        """P6 영향도: 잘못된 도메인이 Sepsis로 silent fallback하지 않음.

        Before fix: OracleAgent("aha") → SepsisDecisionTable (wrong upper bound)
        After fix: OracleAgent("aha") → ValueError (immediate error)
        """
        from cga_bench.agent_runner.oracle_agent import OracleAgent

        # "aha" alone is not a valid key (chest_pain and stroke both use aha_*)
        with pytest.raises(ValueError):
            OracleAgent(MockOracleConfig(guideline_domain="aha"))
