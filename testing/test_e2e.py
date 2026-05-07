"""
E2E Tests for CGA-Bench using Mock LLM Provider

Tests validate:
- Mock provider functionality
- Golden agent response handling
- Pattern matching accuracy
- Error injection and handling
- Budget tracking
"""

import pytest
import json
from typing import List

from cga_bench.testing.mock_provider import (
    EnhancedMockLLMProvider,
    ScenarioResponseLibrary,
    ResponsePattern,
    ResponseMode,
    GoldenAgentResponses,
)
from cga_bench.testing.e2e_runner import E2ETestRunner, E2ETestSuite
from cga_bench.agent_runner.llm_provider import LLMMessage, LLMConfig, LLMBackend


class TestEnhancedMockLLMProvider:
    """EnhancedMockLLMProvider 테스트"""

    def test_sequential_responses(self):
        """순차적 응답 모드 테스트"""
        responses = [
            {"action": "action1", "target": "target1"},
            {"action": "action2", "target": "target2"},
            {"action": "action3", "target": "target3"},
        ]

        provider = EnhancedMockLLMProvider(
            mode=ResponseMode.SEQUENTIAL,
            sequential_responses=responses,
        )

        for i, expected in enumerate(responses):
            result = provider.complete([LLMMessage(role="user", content=f"Call {i}")])
            parsed = json.loads(result.content)
            assert parsed["action"] == expected["action"]

    def test_golden_agent_responses(self):
        """Golden Agent 응답 모드 테스트"""
        golden = GoldenAgentResponses.sepsis_hour1_bundle()

        provider = EnhancedMockLLMProvider(
            mode=ResponseMode.GOLDEN,
            golden_responses=golden,
        )

        for expected in golden:
            result = provider.complete([LLMMessage(role="user", content="Next action")])
            parsed = json.loads(result.content)
            assert parsed["action"] == expected["action"]

    def test_pattern_matching_sepsis(self):
        """Sepsis 시나리오 패턴 매칭 테스트"""
        provider = EnhancedMockLLMProvider(
            mode=ResponseMode.PATTERN,
            patterns=ScenarioResponseLibrary.get_sepsis_responses(),
        )

        # Sepsis 키워드로 요청
        result = provider.complete([
            LLMMessage(role="user", content="Patient presents with sepsis, fever 39C")
        ])

        parsed = json.loads(result.content)
        assert parsed["action"] == "order_lab"
        assert "lactate" in parsed["target"].lower()

    def test_pattern_matching_stemi(self):
        """STEMI 시나리오 패턴 매칭 테스트"""
        provider = EnhancedMockLLMProvider(
            mode=ResponseMode.PATTERN,
            patterns=ScenarioResponseLibrary.get_stemi_responses(),
        )

        result = provider.complete([
            LLMMessage(role="user", content="Patient with chest pain, suspected STEMI")
        ])

        parsed = json.loads(result.content)
        assert parsed["action"] == "order_imaging"
        assert "ecg" in parsed["target"].lower()

    def test_rv_infarct_pattern(self):
        """RV Infarct 패턴 - 니트로 회피 테스트"""
        provider = EnhancedMockLLMProvider(
            mode=ResponseMode.PATTERN,
            patterns=ScenarioResponseLibrary.get_stemi_responses(),
        )

        # V4R ST elevation (RV involvement) 메시지
        result = provider.complete([
            LLMMessage(role="user", content="V4R shows ST elevation, RV involvement confirmed")
        ])

        parsed = json.loads(result.content)
        # RV infarct에서는 nitrates 대신 fluids
        assert parsed["action"] == "administer_fluids"
        assert "nitrate" not in parsed["target"].lower()

    def test_call_tracking(self):
        """호출 추적 테스트"""
        provider = EnhancedMockLLMProvider(mode=ResponseMode.PATTERN)

        # 여러 번 호출
        for i in range(5):
            provider.complete([LLMMessage(role="user", content=f"Call {i}")])

        assert provider.get_call_count() == 5
        assert len(provider.call_history) == 5

        # 마지막 호출 확인
        last_call = provider.get_last_call()
        assert last_call is not None
        assert "Call 4" in last_call.messages[0].content

    def test_token_usage_tracking(self):
        """토큰 사용량 추적 테스트"""
        provider = EnhancedMockLLMProvider(mode=ResponseMode.PATTERN)

        # 긴 메시지로 호출
        long_message = "x" * 1000
        result = provider.complete([LLMMessage(role="user", content=long_message)])

        assert result.usage["prompt_tokens"] > 0
        assert result.usage["completion_tokens"] > 0
        assert result.usage["total_tokens"] == result.usage["prompt_tokens"] + result.usage["completion_tokens"]

    def test_error_injection(self):
        """에러 주입 테스트"""
        provider = EnhancedMockLLMProvider(
            mode=ResponseMode.SEQUENTIAL,
            sequential_responses=[{"action": "test"}],
            error_after_n_calls=2,
        )

        # 첫 두 번은 성공
        provider.complete([LLMMessage(role="user", content="Call 1")])
        provider.complete([LLMMessage(role="user", content="Call 2")])

        # 세 번째는 에러
        with pytest.raises(RuntimeError, match="Injected error"):
            provider.complete([LLMMessage(role="user", content="Call 3")])

    def test_response_delay(self):
        """응답 지연 테스트"""
        import time

        delay_ms = 100
        provider = EnhancedMockLLMProvider(
            mode=ResponseMode.PATTERN,
            response_delay_ms=delay_ms,
        )

        start = time.time()
        provider.complete([LLMMessage(role="user", content="test")])
        elapsed_ms = (time.time() - start) * 1000

        assert elapsed_ms >= delay_ms

    def test_reset(self):
        """상태 초기화 테스트"""
        provider = EnhancedMockLLMProvider(
            mode=ResponseMode.GOLDEN,
            golden_responses=[{"action": "test1"}, {"action": "test2"}],
        )

        # 몇 번 호출
        provider.complete([LLMMessage(role="user", content="1")])
        provider.complete([LLMMessage(role="user", content="2")])

        assert provider.get_call_count() == 2

        # 리셋
        provider.reset()

        assert provider.get_call_count() == 0
        assert len(provider.call_history) == 0
        assert provider._golden_index == 0


class TestScenarioResponseLibrary:
    """ScenarioResponseLibrary 테스트"""

    def test_sepsis_patterns_priority(self):
        """Sepsis 패턴 우선순위 테스트"""
        patterns = ScenarioResponseLibrary.get_sepsis_responses()

        # 우선순위 내림차순 확인
        priorities = [p.priority for p in patterns]
        assert priorities == sorted(priorities, reverse=True)

    def test_all_patterns_have_response(self):
        """모든 패턴에 응답이 있는지 확인"""
        patterns = ScenarioResponseLibrary.get_all_patterns()

        for pattern in patterns:
            assert pattern.response is not None
            if isinstance(pattern.response, str):
                # JSON 파싱 가능한지 확인
                parsed = json.loads(pattern.response)
                assert "action" in parsed


class TestGoldenAgentResponses:
    """GoldenAgentResponses 테스트"""

    def test_sepsis_bundle_sequence(self):
        """Sepsis Hour-1 Bundle 시퀀스 테스트"""
        responses = GoldenAgentResponses.sepsis_hour1_bundle()

        assert len(responses) >= 4

        # 필수 액션 포함 확인
        actions = [r["action"] for r in responses]
        assert "order_lab" in actions
        assert "prescribe_medication" in actions

    def test_stemi_rv_sequence(self):
        """STEMI with RV Infarct 시퀀스 테스트"""
        responses = GoldenAgentResponses.stemi_with_rv_infarct()

        assert len(responses) >= 3

        # V4R ECG 확인
        targets = [r["target"].lower() for r in responses]
        v4r_found = any("v4r" in t for t in targets)
        assert v4r_found

        # Fluids 있고 Nitrates 없음 확인
        actions = [r["action"] for r in responses]
        assert "administer_fluids" in actions

        reasonings = " ".join(r.get("reasoning", "").lower() for r in responses)
        assert "nitrate" in reasonings  # "NO nitrates" 언급


class TestE2ETestRunner:
    """E2ETestRunner 테스트"""

    def test_golden_agent_test(self):
        """Golden Agent 테스트 실행"""
        runner = E2ETestRunner()

        result = runner.run_golden_agent_test(
            scenario="sepsis",
            golden_responses=GoldenAgentResponses.sepsis_hour1_bundle(),
        )

        assert result.test_name == "golden_agent_sepsis"
        assert result.scenario == "sepsis"
        assert result.duration_ms > 0
        assert result.llm_calls > 0

    def test_pattern_matching_test(self):
        """패턴 매칭 테스트 실행"""
        runner = E2ETestRunner()

        result = runner.run_pattern_matching_test(
            scenario="sepsis",
            expected_actions=["order_lab"],  # 첫 번째 액션만 검증
        )

        assert result.test_name == "pattern_matching_sepsis"
        assert result.llm_calls > 0

    def test_error_handling_test(self):
        """에러 핸들링 테스트 실행"""
        runner = E2ETestRunner()

        result = runner.run_error_handling_test(error_after_n_calls=2)

        assert result.test_name == "error_handling"
        assert result.passed  # 에러가 올바르게 발생해야 함
        assert result.details["error_raised"]

    def test_budget_tracking_test(self):
        """예산 추적 테스트 실행"""
        runner = E2ETestRunner()

        result = runner.run_budget_tracking_test(max_calls=3)

        assert result.test_name == "budget_tracking"
        assert result.llm_calls == 3
        assert result.tokens_used > 0

    def test_run_all_tests(self):
        """전체 테스트 스위트 실행"""
        runner = E2ETestRunner()

        suite = runner.run_all_tests()

        assert suite.total_tests > 0
        assert suite.passed_tests + suite.failed_tests == suite.total_tests
        assert suite.total_duration_ms > 0
        assert len(suite.results) == suite.total_tests


class TestResponsePattern:
    """ResponsePattern 테스트"""

    def test_pattern_matching(self):
        """패턴 매칭 테스트"""
        pattern = ResponsePattern(
            pattern=r"sepsis|septic",
            response={"action": "order_lab"},
        )

        # 매칭되는 메시지
        messages = [LLMMessage(role="user", content="Patient has sepsis")]
        assert pattern.matches(messages)

        # 매칭되지 않는 메시지
        messages = [LLMMessage(role="user", content="Patient has headache")]
        assert not pattern.matches(messages)

    def test_case_insensitive_matching(self):
        """대소문자 구분 없는 매칭 테스트"""
        pattern = ResponsePattern(
            pattern=r"stemi",
            response={"action": "order_ecg"},
        )

        messages = [LLMMessage(role="user", content="STEMI confirmed")]
        assert pattern.matches(messages)

        messages = [LLMMessage(role="user", content="stemi suspected")]
        assert pattern.matches(messages)


class TestIntegration:
    """통합 테스트"""

    def test_full_sepsis_workflow(self):
        """Sepsis 전체 워크플로우 테스트"""
        provider = EnhancedMockLLMProvider(
            mode=ResponseMode.GOLDEN,
            golden_responses=GoldenAgentResponses.sepsis_hour1_bundle(),
        )

        workflow_messages = [
            "Patient presents with suspected sepsis",
            "What should we do first?",
            "Lactate ordered, what next?",
            "Cultures sent, proceed with antibiotics?",
            "Any other interventions needed?",
        ]

        actions_taken = []
        for msg in workflow_messages:
            result = provider.complete([LLMMessage(role="user", content=msg)])
            try:
                parsed = json.loads(result.content)
                actions_taken.append(parsed.get("action"))
            except json.JSONDecodeError:
                pass

        # SSC Hour-1 Bundle 필수 액션 확인
        assert "order_lab" in actions_taken
        assert "prescribe_medication" in actions_taken

    def test_stemi_rv_trap_avoidance(self):
        """STEMI RV Trap 회피 테스트"""
        provider = EnhancedMockLLMProvider(
            mode=ResponseMode.GOLDEN,
            golden_responses=GoldenAgentResponses.stemi_with_rv_infarct(),
        )

        workflow_messages = [
            "Inferior STEMI on ECG",
            "Should we check V4R?",
            "V4R positive, RV involvement",
            "Patient hypotensive, what to give?",
        ]

        responses = []
        for msg in workflow_messages:
            result = provider.complete([LLMMessage(role="user", content=msg)])
            try:
                responses.append(json.loads(result.content))
            except json.JSONDecodeError:
                pass

        # Nitrates가 처방되지 않았는지 확인
        for resp in responses:
            target = resp.get("target", "").lower()
            action = resp.get("action", "").lower()
            assert "nitroglycerin" not in target
            assert "nitrate" not in target or "no" in resp.get("reasoning", "").lower()
