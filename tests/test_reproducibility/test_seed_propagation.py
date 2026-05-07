"""Tests for seed propagation in LLMConfig and ExperimentConfig."""

import pytest


class TestLLMConfigSeed:
    """Test that LLMConfig accepts and propagates seed parameter."""

    def test_seed_default_none(self):
        from cga_bench.agent_runner.llm_provider import LLMConfig, LLMBackend

        config = LLMConfig(backend=LLMBackend.MOCK, model="test-model")
        assert config.seed is None

    def test_seed_explicit(self):
        from cga_bench.agent_runner.llm_provider import LLMConfig, LLMBackend

        config = LLMConfig(backend=LLMBackend.MOCK, model="test-model", seed=42)
        assert config.seed == 42

    def test_seed_zero(self):
        from cga_bench.agent_runner.llm_provider import LLMConfig, LLMBackend

        config = LLMConfig(backend=LLMBackend.MOCK, model="test-model", seed=0)
        assert config.seed == 0


class TestExperimentConfigSeed:
    """Test that ExperimentConfig propagates random_seed."""

    def test_random_seed_default_none(self):
        from cga_bench.eval_harness.runner import ExperimentConfig

        config = ExperimentConfig(
            experiment_id="test",
            scenarios=["septic_shock_basic"],
            agents=["oracle"],
        )
        assert config.random_seed is None

    def test_random_seed_set(self):
        from cga_bench.eval_harness.runner import ExperimentConfig

        config = ExperimentConfig(
            experiment_id="test",
            scenarios=["septic_shock_basic"],
            agents=["oracle"],
            random_seed=42,
        )
        assert config.random_seed == 42

    def test_random_seed_sets_random_module(self):
        """When random_seed is set, random module should be seeded."""
        import random

        from cga_bench.eval_harness.runner import ExperimentConfig

        # Create config with seed → __post_init__ seeds random
        ExperimentConfig(
            experiment_id="test",
            scenarios=["s"],
            agents=["a"],
            random_seed=123,
        )
        val1 = random.random()

        # Re-seed with same seed
        ExperimentConfig(
            experiment_id="test",
            scenarios=["s"],
            agents=["a"],
            random_seed=123,
        )
        val2 = random.random()

        assert val1 == val2
