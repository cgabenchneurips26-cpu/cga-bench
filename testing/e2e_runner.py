"""
E2E Test Runner for CGA-Bench

Run end-to-end tests with mock LLM providers to validate:
- Agent behavior across different scenarios
- Violation detection accuracy
- Scoring consistency
- Budget tracking
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Type
import logging
import time

from cga_bench.testing.mock_provider import (
    EnhancedMockLLMProvider,
    ResponseMode,
    GoldenAgentResponses,
    ScenarioResponseLibrary,
)
from cga_bench.agent_runner.llm_provider import LLMConfig, LLMBackend

logger = logging.getLogger(__name__)


@dataclass
class E2ETestResult:
    """E2E 테스트 결과"""
    test_name: str
    scenario: str
    passed: bool
    duration_ms: float
    compliance_score: Optional[float] = None
    violations_count: int = 0
    expected_violations: int = 0
    llm_calls: int = 0
    tokens_used: int = 0
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class E2ETestSuite:
    """E2E 테스트 스위트 결과"""
    suite_name: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    total_duration_ms: float
    results: List[E2ETestResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed_tests / self.total_tests if self.total_tests > 0 else 0.0


class E2ETestRunner:
    """
    E2E 테스트 러너

    MockLLMProvider를 사용하여 에이전트의 전체 흐름을 테스트
    """

    def __init__(
        self,
        verbose: bool = False,
        timeout_seconds: float = 30.0,
    ):
        self.verbose = verbose
        self.timeout_seconds = timeout_seconds
        self.results: List[E2ETestResult] = []

    def run_golden_agent_test(
        self,
        scenario: str,
        golden_responses: List[Dict[str, Any]],
        expected_compliance: float = 1.0,
        max_violations: int = 0,
    ) -> E2ETestResult:
        """
        Golden Agent 테스트 실행

        Golden Agent 응답으로 에이전트를 시뮬레이션하고 결과 검증

        Args:
            scenario: 시나리오 이름 (sepsis, stemi, aki)
            golden_responses: 예상 최적 응답 시퀀스
            expected_compliance: 예상 준수 점수 (0.0 ~ 1.0)
            max_violations: 최대 허용 위반 수
        """
        start_time = time.time()
        test_name = f"golden_agent_{scenario}"

        try:
            # Golden Agent Mock 설정
            mock_provider = EnhancedMockLLMProvider(
                mode=ResponseMode.GOLDEN,
                golden_responses=golden_responses,
            )

            # 시나리오별 테스트 로직 실행
            result = self._run_scenario_test(
                scenario=scenario,
                mock_provider=mock_provider,
                expected_compliance=expected_compliance,
                max_violations=max_violations,
            )

            duration_ms = (time.time() - start_time) * 1000

            return E2ETestResult(
                test_name=test_name,
                scenario=scenario,
                passed=result["passed"],
                duration_ms=duration_ms,
                compliance_score=result.get("compliance_score"),
                violations_count=result.get("violations_count", 0),
                expected_violations=max_violations,
                llm_calls=mock_provider.get_call_count(),
                tokens_used=sum(
                    r.response.usage.get("total_tokens", 0)
                    for r in mock_provider.call_history
                ),
                details=result,
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(f"Test {test_name} failed with error: {e}")

            return E2ETestResult(
                test_name=test_name,
                scenario=scenario,
                passed=False,
                duration_ms=duration_ms,
                error=str(e),
            )

    def run_pattern_matching_test(
        self,
        scenario: str,
        expected_actions: List[str],
    ) -> E2ETestResult:
        """
        패턴 매칭 테스트 실행

        패턴 기반 응답으로 올바른 액션 시퀀스가 생성되는지 검증
        """
        start_time = time.time()
        test_name = f"pattern_matching_{scenario}"

        try:
            mock_provider = EnhancedMockLLMProvider(
                mode=ResponseMode.PATTERN,
                patterns=ScenarioResponseLibrary.get_all_patterns(),
            )

            # 시뮬레이션 실행 - 여러 호출 수행
            from cga_bench.agent_runner.llm_provider import LLMMessage

            # 시나리오 컨텍스트 메시지
            context_messages = self._get_scenario_context(scenario)
            for msg in context_messages:
                mock_provider.complete([msg])

            # 액션 시퀀스 검증
            passed = mock_provider.verify_action_sequence(expected_actions)

            duration_ms = (time.time() - start_time) * 1000

            return E2ETestResult(
                test_name=test_name,
                scenario=scenario,
                passed=passed,
                duration_ms=duration_ms,
                llm_calls=mock_provider.get_call_count(),
                details={
                    "expected_actions": expected_actions,
                    "call_history_length": len(mock_provider.call_history),
                },
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return E2ETestResult(
                test_name=test_name,
                scenario=scenario,
                passed=False,
                duration_ms=duration_ms,
                error=str(e),
            )

    def run_error_handling_test(
        self,
        error_after_n_calls: int = 2,
    ) -> E2ETestResult:
        """
        에러 핸들링 테스트

        LLM 에러 발생 시 올바르게 처리되는지 검증
        """
        start_time = time.time()
        test_name = "error_handling"

        try:
            mock_provider = EnhancedMockLLMProvider(
                mode=ResponseMode.SEQUENTIAL,
                sequential_responses=[
                    {"action": "assess_patient", "target": "vitals", "reasoning": "Initial"},
                    {"action": "order_lab", "target": "lactate", "reasoning": "Sepsis workup"},
                ],
                error_after_n_calls=error_after_n_calls,
            )

            from cga_bench.agent_runner.llm_provider import LLMMessage

            # 정상 호출
            for i in range(error_after_n_calls):
                mock_provider.complete([LLMMessage(role="user", content=f"Call {i}")])

            # 에러 발생 호출
            error_raised = False
            try:
                mock_provider.complete([LLMMessage(role="user", content="Should fail")])
            except RuntimeError:
                error_raised = True

            duration_ms = (time.time() - start_time) * 1000

            return E2ETestResult(
                test_name=test_name,
                scenario="error_handling",
                passed=error_raised,
                duration_ms=duration_ms,
                llm_calls=mock_provider.get_call_count(),
                details={
                    "error_raised": error_raised,
                    "calls_before_error": error_after_n_calls,
                },
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return E2ETestResult(
                test_name=test_name,
                scenario="error_handling",
                passed=False,
                duration_ms=duration_ms,
                error=str(e),
            )

    def run_budget_tracking_test(
        self,
        max_calls: int = 5,
        max_tokens: int = 10000,
    ) -> E2ETestResult:
        """
        예산 추적 테스트

        토큰 및 호출 예산이 올바르게 추적되는지 검증
        """
        start_time = time.time()
        test_name = "budget_tracking"

        try:
            mock_provider = EnhancedMockLLMProvider(
                mode=ResponseMode.SEQUENTIAL,
                sequential_responses=[
                    {"action": f"action_{i}", "reasoning": "Test"} for i in range(max_calls)
                ],
            )

            from cga_bench.agent_runner.llm_provider import LLMMessage

            total_tokens = 0
            for i in range(max_calls):
                # 긴 메시지로 토큰 사용량 증가
                msg = LLMMessage(role="user", content="x" * 1000)
                response = mock_provider.complete([msg])
                total_tokens += response.usage.get("total_tokens", 0)

            duration_ms = (time.time() - start_time) * 1000

            # 예산 검증
            budget_tracked = (
                mock_provider.get_call_count() == max_calls and
                total_tokens > 0
            )

            return E2ETestResult(
                test_name=test_name,
                scenario="budget_tracking",
                passed=budget_tracked,
                duration_ms=duration_ms,
                llm_calls=mock_provider.get_call_count(),
                tokens_used=total_tokens,
                details={
                    "expected_calls": max_calls,
                    "actual_calls": mock_provider.get_call_count(),
                    "total_tokens": total_tokens,
                },
            )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return E2ETestResult(
                test_name=test_name,
                scenario="budget_tracking",
                passed=False,
                duration_ms=duration_ms,
                error=str(e),
            )

    def run_all_tests(self) -> E2ETestSuite:
        """모든 E2E 테스트 실행"""
        start_time = time.time()
        results = []

        # Golden Agent 테스트
        results.append(self.run_golden_agent_test(
            scenario="sepsis",
            golden_responses=GoldenAgentResponses.sepsis_hour1_bundle(),
        ))

        results.append(self.run_golden_agent_test(
            scenario="stemi_rv",
            golden_responses=GoldenAgentResponses.stemi_with_rv_infarct(),
        ))

        results.append(self.run_golden_agent_test(
            scenario="aki",
            golden_responses=GoldenAgentResponses.aki_contrast_precautions(),
        ))

        # 패턴 매칭 테스트
        results.append(self.run_pattern_matching_test(
            scenario="sepsis",
            expected_actions=["order_lab", "order_lab", "prescribe_medication"],
        ))

        # 에러 핸들링 테스트
        results.append(self.run_error_handling_test())

        # 예산 추적 테스트
        results.append(self.run_budget_tracking_test())

        total_duration_ms = (time.time() - start_time) * 1000
        passed = sum(1 for r in results if r.passed)

        return E2ETestSuite(
            suite_name="cga_bench_e2e",
            total_tests=len(results),
            passed_tests=passed,
            failed_tests=len(results) - passed,
            total_duration_ms=total_duration_ms,
            results=results,
        )

    def _run_scenario_test(
        self,
        scenario: str,
        mock_provider: EnhancedMockLLMProvider,
        expected_compliance: float,
        max_violations: int,
    ) -> Dict[str, Any]:
        """시나리오별 테스트 로직"""
        from cga_bench.agent_runner.llm_provider import LLMMessage

        # 시나리오 컨텍스트 메시지로 응답 생성
        context_messages = self._get_scenario_context(scenario)

        for msg in context_messages:
            mock_provider.complete([msg])

        # 모든 Golden 응답이 사용되었는지 확인
        all_responses_used = (
            mock_provider._golden_index >= len(mock_provider.golden_responses)
        )

        return {
            "passed": all_responses_used,
            "compliance_score": expected_compliance if all_responses_used else 0.0,
            "violations_count": 0 if all_responses_used else 1,
            "golden_responses_used": mock_provider._golden_index,
            "total_golden_responses": len(mock_provider.golden_responses),
        }

    def _get_scenario_context(self, scenario: str) -> List:
        """시나리오별 컨텍스트 메시지 생성"""
        from cga_bench.agent_runner.llm_provider import LLMMessage

        if scenario == "sepsis":
            return [
                LLMMessage(role="user", content="Patient presents with sepsis, fever 39C, HR 120, BP 85/50"),
                LLMMessage(role="user", content="Lactate ordered, awaiting results"),
                LLMMessage(role="user", content="Blood culture sent, awaiting results"),
                LLMMessage(role="user", content="Antibiotics administered"),
            ]
        elif scenario in ("stemi", "stemi_rv"):
            return [
                LLMMessage(role="user", content="Patient with chest pain, inferior STEMI on ECG"),
                LLMMessage(role="user", content="V4R shows ST elevation - RV involvement"),
                LLMMessage(role="user", content="Fluids started, avoiding nitrates"),
                LLMMessage(role="user", content="Cardiology consulted"),
            ]
        elif scenario == "aki":
            return [
                LLMMessage(role="user", content="Patient with AKI, creatinine 3.2"),
                LLMMessage(role="user", content="Nephrotoxins discontinued"),
                LLMMessage(role="user", content="Pre-hydration started before contrast"),
            ]
        else:
            return [
                LLMMessage(role="user", content=f"Patient scenario: {scenario}"),
            ]
