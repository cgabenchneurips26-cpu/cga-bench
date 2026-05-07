"""Budget variance test.

Spec requirement: budget variance <= 1%
Tests that BudgetEnforcer tracks and limits resource usage within tolerance.
"""

from typing import cast

from cga_bench.eval_harness.budget_enforcer import (
    BudgetConfig,
    BudgetEnforcer,
    BudgetExceededAction,
)


class TestBudgetVariance:
    def test_token_tracking_accuracy(self) -> None:
        config = BudgetConfig(
            token_limit=10000,
            call_limit=50,
            on_exceeded=BudgetExceededAction.WARN,
        )
        enforcer = BudgetEnforcer(config)
        enforcer.reset()

        for _ in range(10):
            enforcer.record_llm_call(total_tokens=1000)

        actual_tokens = enforcer.usage.total_tokens
        expected_tokens = 10000

        variance = abs(actual_tokens - expected_tokens) / expected_tokens
        assert variance <= 0.01, f"Token variance {variance:.2%} > 1%"

    def test_tool_call_tracking_accuracy(self) -> None:
        config = BudgetConfig(
            token_limit=100000,
            call_limit=100,
            on_exceeded=BudgetExceededAction.WARN,
        )
        enforcer = BudgetEnforcer(config)
        enforcer.reset()

        for _ in range(50):
            enforcer.record_tool_call()

        actual_calls = enforcer.usage.tool_calls
        expected_calls = 50

        variance = abs(actual_calls - expected_calls) / expected_calls
        assert variance <= 0.01, f"Tool call variance {variance:.2%} > 1%"

    def test_budget_exceeded_detection(self) -> None:
        config = BudgetConfig(
            token_limit=1000,
            call_limit=5,
            on_exceeded=BudgetExceededAction.WARN,
        )
        enforcer = BudgetEnforcer(config)
        enforcer.reset()

        enforcer.record_llm_call(total_tokens=500)
        summary = cast(dict[str, object], enforcer.get_summary())
        assert bool(summary["exceeded"]) is False

        enforcer.record_llm_call(total_tokens=600)
        summary = cast(dict[str, object], enforcer.get_summary())
        assert bool(summary["exceeded"]) is True, "Budget exceeded not detected"

    def test_utilization_percentage(self) -> None:
        config = BudgetConfig(
            token_limit=10000,
            call_limit=100,
            on_exceeded=BudgetExceededAction.WARN,
        )
        enforcer = BudgetEnforcer(config)
        enforcer.reset()

        enforcer.record_llm_call(total_tokens=5000)
        token_utilization = enforcer.get_utilization()["token_utilization"]

        assert 0.49 <= token_utilization <= 0.51, (
            f"Token utilization {token_utilization:.2%} not ~50%"
        )

    def test_two_agents_same_budget(self) -> None:
        config = BudgetConfig(
            token_limit=10000,
            call_limit=50,
            on_exceeded=BudgetExceededAction.WARN,
        )

        enforcer_a = BudgetEnforcer(config)
        enforcer_b = BudgetEnforcer(config)
        enforcer_a.reset()
        enforcer_b.reset()

        for _ in range(8):
            enforcer_a.record_llm_call(total_tokens=1000)
            enforcer_b.record_llm_call(total_tokens=1000)

        tokens_a = enforcer_a.usage.total_tokens
        tokens_b = enforcer_b.usage.total_tokens

        if tokens_a > 0:
            variance = abs(tokens_a - tokens_b) / tokens_a
            assert variance <= 0.01, f"Inter-agent variance {variance:.2%} > 1%"
