from __future__ import annotations

import pytest

from cga_bench.eval_harness.budget_enforcer import (
    BudgetConfig,
    BudgetEnforcer,
    BudgetExceededAction,
    BudgetExceededException,
    BudgetUsage,
)


class TestBudgetUsage:
    def test_total_calls_property(self):
        u = BudgetUsage(llm_calls=3, tool_calls=5)
        assert u.total_calls == 8

    def test_start_end_round(self):
        u = BudgetUsage()
        u.start_round()
        assert u.current_round == 1
        assert len(u.rounds) == 1
        u.total_tokens = 100
        u.llm_calls = 2
        u.end_round()
        assert u.rounds[0]["tokens_used"] == 100
        assert u.rounds[0]["calls_used"] == 2

    def test_to_dict(self):
        u = BudgetUsage(total_tokens=500, llm_calls=3, tool_calls=2)
        d = u.to_dict()
        assert d["total_tokens"] == 500
        assert d["total_calls"] == 5
        assert d["llm_calls"] == 3


class TestBudgetEnforcer:
    def test_init(self):
        config = BudgetConfig(token_limit=1000, call_limit=10)
        enforcer = BudgetEnforcer(config)
        assert enforcer.usage.total_tokens == 0
        assert not enforcer._is_exceeded

    def test_record_llm_call(self):
        enforcer = BudgetEnforcer(BudgetConfig(token_limit=10000, call_limit=100))
        enforcer.record_llm_call(prompt_tokens=50, completion_tokens=30)
        assert enforcer.usage.total_tokens == 80
        assert enforcer.usage.prompt_tokens == 50
        assert enforcer.usage.completion_tokens == 30
        assert enforcer.usage.llm_calls == 1

    def test_record_tool_call(self):
        enforcer = BudgetEnforcer(BudgetConfig(token_limit=10000, call_limit=100))
        enforcer.record_tool_call()
        enforcer.record_tool_call()
        assert enforcer.usage.tool_calls == 2
        assert enforcer.usage.total_calls == 2

    def test_total_tokens_from_explicit(self):
        enforcer = BudgetEnforcer(BudgetConfig(token_limit=10000, call_limit=100))
        enforcer.record_llm_call(total_tokens=200)
        assert enforcer.usage.total_tokens == 200

    def test_reset(self):
        enforcer = BudgetEnforcer(BudgetConfig(token_limit=1000, call_limit=10))
        enforcer.record_llm_call(total_tokens=500)
        enforcer.reset()
        assert enforcer.usage.total_tokens == 0
        assert not enforcer._is_exceeded


class TestBudgetExceeded:
    def test_token_exceed_terminates(self):
        enforcer = BudgetEnforcer(
            BudgetConfig(token_limit=100, call_limit=100, on_exceeded=BudgetExceededAction.TERMINATE)
        )
        with pytest.raises(BudgetExceededException):
            enforcer.record_llm_call(total_tokens=150)

    def test_call_exceed_terminates(self):
        enforcer = BudgetEnforcer(
            BudgetConfig(token_limit=100000, call_limit=2, on_exceeded=BudgetExceededAction.TERMINATE)
        )
        enforcer.record_llm_call(total_tokens=10)
        enforcer.record_llm_call(total_tokens=10)
        with pytest.raises(BudgetExceededException):
            enforcer.record_tool_call()

    def test_warn_does_not_raise(self):
        enforcer = BudgetEnforcer(
            BudgetConfig(token_limit=100, call_limit=100, on_exceeded=BudgetExceededAction.WARN)
        )
        enforcer.record_llm_call(total_tokens=150)
        assert enforcer._is_exceeded

    def test_log_only_does_not_raise(self):
        enforcer = BudgetEnforcer(
            BudgetConfig(token_limit=100, call_limit=100, on_exceeded=BudgetExceededAction.LOG_ONLY)
        )
        enforcer.record_llm_call(total_tokens=150)
        assert enforcer._is_exceeded

    def test_exception_contains_usage_and_config(self):
        enforcer = BudgetEnforcer(
            BudgetConfig(token_limit=50, call_limit=100, on_exceeded=BudgetExceededAction.TERMINATE)
        )
        with pytest.raises(BudgetExceededException) as exc_info:
            enforcer.record_llm_call(total_tokens=100)
        assert exc_info.value.usage.total_tokens == 100
        assert exc_info.value.config.token_limit == 50


class TestRemainingBudget:
    def test_remaining_calculated(self):
        enforcer = BudgetEnforcer(BudgetConfig(token_limit=1000, call_limit=10))
        enforcer.record_llm_call(total_tokens=300)
        remaining = enforcer.get_remaining_budget()
        assert remaining["remaining_tokens"] == 700
        assert remaining["remaining_calls"] == 9

    def test_remaining_floors_at_zero(self):
        enforcer = BudgetEnforcer(
            BudgetConfig(token_limit=100, call_limit=100, on_exceeded=BudgetExceededAction.LOG_ONLY)
        )
        enforcer.record_llm_call(total_tokens=200)
        remaining = enforcer.get_remaining_budget()
        assert remaining["remaining_tokens"] == 0


class TestUtilization:
    def test_utilization_calculated(self):
        enforcer = BudgetEnforcer(BudgetConfig(token_limit=1000, call_limit=10))
        enforcer.record_llm_call(total_tokens=500)
        util = enforcer.get_utilization()
        assert util["token_utilization"] == pytest.approx(0.5)
        assert util["call_utilization"] == pytest.approx(0.1)


class TestRoundTracking:
    def test_multi_round_tracking(self):
        enforcer = BudgetEnforcer(BudgetConfig(token_limit=10000, call_limit=100))
        enforcer.reset()
        enforcer.start_round()
        enforcer.record_llm_call(total_tokens=100)
        enforcer.end_round()
        enforcer.start_round()
        enforcer.record_llm_call(total_tokens=200)
        enforcer.end_round()
        assert enforcer.usage.current_round == 2
        assert enforcer.usage.rounds[0]["tokens_used"] == 100
        assert enforcer.usage.rounds[1]["tokens_used"] == 200
