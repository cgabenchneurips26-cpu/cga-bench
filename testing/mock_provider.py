"""
Enhanced Mock LLM Provider for E2E Testing

Features:
- Pattern-based response matching with regex support
- Scenario-specific response libraries (Sepsis, STEMI, AKI, etc.)
- Golden Agent responses that follow guidelines perfectly
- Response delay simulation for timeout testing
- Error injection for error handling tests
- Call tracking and verification
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Pattern, Union
import re
import json
import time
import logging
from enum import Enum

from cga_bench.agent_runner.llm_provider import (
    BaseLLMProvider,
    LLMConfig,
    LLMMessage,
    LLMResponse,
    LLMBackend,
)

logger = logging.getLogger(__name__)


class ResponseMode(Enum):
    """응답 모드"""
    SEQUENTIAL = "sequential"  # 순차적으로 응답 반환
    PATTERN = "pattern"  # 패턴 매칭으로 응답 선택
    GOLDEN = "golden"  # Golden Agent 응답 (가이드라인 준수)
    RANDOM = "random"  # 랜덤 응답 (에러 케이스 테스트)


@dataclass
class ResponsePattern:
    """패턴 기반 응답 매칭"""
    pattern: Union[str, Pattern]  # 정규식 패턴
    response: Union[str, Dict[str, Any]]  # 응답 (문자열 또는 JSON)
    priority: int = 0  # 우선순위 (높을수록 먼저 매칭)
    match_field: str = "content"  # 매칭할 필드 (content, role)

    def __post_init__(self):
        if isinstance(self.pattern, str):
            self.pattern = re.compile(self.pattern, re.IGNORECASE)

    def matches(self, messages: List[LLMMessage]) -> bool:
        """메시지가 패턴과 매칭되는지 확인"""
        for msg in reversed(messages):  # 최근 메시지부터 확인
            text = getattr(msg, self.match_field, msg.content)
            if self.pattern.search(text):
                return True
        return False


@dataclass
class CallRecord:
    """LLM 호출 기록"""
    messages: List[LLMMessage]
    response: LLMResponse
    timestamp: float
    duration_ms: float
    error: Optional[Exception] = None


class ScenarioResponseLibrary:
    """
    시나리오별 응답 라이브러리

    각 임상 시나리오에 대한 표준 응답 세트 제공
    """

    @staticmethod
    def get_sepsis_responses() -> List[ResponsePattern]:
        """SSC 2021 Hour-1 Bundle 준수 응답"""
        return [
            ResponsePattern(
                pattern=r"(sepsis|septic|infection.*shock)",
                response=json.dumps({
                    "action": "order_lab",
                    "target": "lactate",
                    "reasoning": "SSC 2021: Measure lactate level within 1 hour of sepsis recognition"
                }),
                priority=100,
            ),
            ResponsePattern(
                pattern=r"lactate.*(ordered|pending|result)",
                response=json.dumps({
                    "action": "order_lab",
                    "target": "blood_culture",
                    "reasoning": "SSC 2021: Obtain blood cultures before antibiotics"
                }),
                priority=90,
            ),
            ResponsePattern(
                pattern=r"(culture|blood.*culture).*(ordered|pending)",
                response=json.dumps({
                    "action": "prescribe_medication",
                    "target": "ceftriaxone 2g IV",
                    "reasoning": "SSC 2021: Administer broad-spectrum antibiotics within 1 hour"
                }),
                priority=80,
            ),
            ResponsePattern(
                pattern=r"antibiotic.*(given|administered)",
                response=json.dumps({
                    "action": "administer_fluids",
                    "target": "crystalloid 30mL/kg",
                    "reasoning": "SSC 2021: 30mL/kg crystalloid for hypotension or lactate ≥4"
                }),
                priority=70,
            ),
        ]

    @staticmethod
    def get_stemi_responses() -> List[ResponsePattern]:
        """AHA STEMI 2013 가이드라인 준수 응답"""
        return [
            ResponsePattern(
                pattern=r"(chest.*pain|cardiac|stemi|inferior.*mi)",
                response=json.dumps({
                    "action": "order_imaging",
                    "target": "12-lead ECG",
                    "reasoning": "AHA: Obtain ECG within 10 minutes of arrival"
                }),
                priority=100,
            ),
            ResponsePattern(
                pattern=r"ecg.*(st.*elevation|inferior)",
                response=json.dumps({
                    "action": "order_imaging",
                    "target": "right-sided ECG (V4R)",
                    "reasoning": "AHA: Check V4R for RV involvement in inferior STEMI before nitrates"
                }),
                priority=95,
            ),
            ResponsePattern(
                pattern=r"v4r.*(no.*elevation|negative)",
                response=json.dumps({
                    "action": "prescribe_medication",
                    "target": "nitroglycerin 0.4mg SL",
                    "reasoning": "Safe to give nitrates - no RV involvement"
                }),
                priority=85,
            ),
            ResponsePattern(
                pattern=r"v4r.*(elevation|positive|rv)",
                response=json.dumps({
                    "action": "administer_fluids",
                    "target": "normal saline bolus",
                    "reasoning": "RV infarct: Preload-dependent, AVOID nitrates"
                }),
                priority=90,
            ),
        ]

    @staticmethod
    def get_aki_responses() -> List[ResponsePattern]:
        """KDIGO AKI 가이드라인 준수 응답"""
        return [
            ResponsePattern(
                pattern=r"(aki|acute.*kidney|creatinine.*elevated)",
                response=json.dumps({
                    "action": "discontinue_medication",
                    "target": "nephrotoxic agents",
                    "reasoning": "KDIGO: Discontinue nephrotoxic medications"
                }),
                priority=100,
            ),
            ResponsePattern(
                pattern=r"(contrast|ct.*with.*contrast)",
                response=json.dumps({
                    "action": "administer_fluids",
                    "target": "IV saline pre-hydration",
                    "reasoning": "KDIGO: Pre-hydrate before contrast in AKI patients"
                }),
                priority=90,
            ),
        ]

    @classmethod
    def get_all_patterns(cls) -> List[ResponsePattern]:
        """모든 시나리오의 패턴 반환"""
        patterns = []
        patterns.extend(cls.get_sepsis_responses())
        patterns.extend(cls.get_stemi_responses())
        patterns.extend(cls.get_aki_responses())
        return sorted(patterns, key=lambda p: -p.priority)


class GoldenAgentResponses:
    """
    Golden Agent 응답 세트

    각 시나리오에서 100% 점수를 받는 최적 응답 시퀀스
    """

    @staticmethod
    def sepsis_hour1_bundle() -> List[Dict[str, Any]]:
        """Sepsis Hour-1 Bundle 완전 준수 응답 시퀀스"""
        return [
            {
                "action": "order_lab",
                "target": "blood_culture",
                "reasoning": "SSC 2021: Blood cultures BEFORE antibiotics"
            },
            {
                "action": "order_lab",
                "target": "lactate",
                "reasoning": "SSC 2021: Measure lactate within 1 hour"
            },
            {
                "action": "prescribe_medication",
                "target": "ceftriaxone 2g IV",
                "reasoning": "SSC 2021: Broad-spectrum antibiotics within 1 hour"
            },
            {
                "action": "administer_fluids",
                "target": "crystalloid 30mL/kg IV",
                "reasoning": "SSC 2021: Fluid resuscitation for hypotension"
            },
        ]

    @staticmethod
    def stemi_with_rv_infarct() -> List[Dict[str, Any]]:
        """STEMI with RV Infarct - 니트로 함정 회피 응답"""
        return [
            {
                "action": "order_imaging",
                "target": "12-lead ECG",
                "reasoning": "AHA: ECG within 10 minutes"
            },
            {
                "action": "order_imaging",
                "target": "right-sided ECG V4R",
                "reasoning": "AHA: Check V4R in inferior STEMI"
            },
            {
                "action": "administer_fluids",
                "target": "normal saline 500mL bolus",
                "reasoning": "RV infarct is preload-dependent - fluids first, NO nitrates"
            },
            {
                "action": "consult",
                "target": "cardiology for emergent cath",
                "reasoning": "AHA: Door-to-balloon <90 minutes"
            },
        ]

    @staticmethod
    def aki_contrast_precautions() -> List[Dict[str, Any]]:
        """AKI with contrast exposure 응답"""
        return [
            {
                "action": "discontinue_medication",
                "target": "metformin",
                "reasoning": "KDIGO: Hold nephrotoxic agents"
            },
            {
                "action": "discontinue_medication",
                "target": "NSAIDs",
                "reasoning": "KDIGO: Avoid NSAIDs in AKI"
            },
            {
                "action": "administer_fluids",
                "target": "IV saline 1mL/kg/hr pre-hydration",
                "reasoning": "KDIGO: Pre-contrast hydration"
            },
        ]


class EnhancedMockLLMProvider(BaseLLMProvider):
    """
    향상된 Mock LLM Provider

    Features:
    - 패턴 기반 응답 매칭
    - 시나리오별 응답 라이브러리
    - Golden Agent 모드
    - 응답 지연 시뮬레이션
    - 에러 주입
    - 호출 추적 및 검증
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        mode: ResponseMode = ResponseMode.PATTERN,
        patterns: Optional[List[ResponsePattern]] = None,
        golden_responses: Optional[List[Dict[str, Any]]] = None,
        sequential_responses: Optional[List[Union[str, Dict]]] = None,
        response_delay_ms: float = 0,
        error_rate: float = 0.0,
        error_after_n_calls: Optional[int] = None,
    ):
        """
        Args:
            config: LLM 설정 (없으면 기본값 사용)
            mode: 응답 모드 (SEQUENTIAL, PATTERN, GOLDEN, RANDOM)
            patterns: 패턴 기반 응답 목록
            golden_responses: Golden Agent 응답 시퀀스
            sequential_responses: 순차적 응답 목록
            response_delay_ms: 응답 지연 시간 (밀리초)
            error_rate: 에러 발생 확률 (0.0 ~ 1.0)
            error_after_n_calls: N번 호출 후 에러 발생
        """
        if config is None:
            config = LLMConfig(backend=LLMBackend.MOCK, model="mock-model")
        super().__init__(config)

        self.mode = mode
        self.patterns = patterns or ScenarioResponseLibrary.get_all_patterns()
        self.golden_responses = golden_responses or []
        self.sequential_responses = sequential_responses or []
        self.response_delay_ms = response_delay_ms
        self.error_rate = error_rate
        self.error_after_n_calls = error_after_n_calls

        # 호출 추적
        self.call_count = 0
        self.call_history: List[CallRecord] = []
        self._golden_index = 0
        self._sequential_index = 0

    def complete(self, messages: List[LLMMessage]) -> LLMResponse:
        """Mock 응답 생성"""
        start_time = time.time()
        error: Optional[Exception] = None

        try:
            # 에러 주입 체크
            self._check_error_injection()

            # 응답 지연 시뮬레이션
            if self.response_delay_ms > 0:
                time.sleep(self.response_delay_ms / 1000)

            # 모드별 응답 생성
            if self.mode == ResponseMode.SEQUENTIAL:
                content = self._get_sequential_response()
            elif self.mode == ResponseMode.GOLDEN:
                content = self._get_golden_response()
            elif self.mode == ResponseMode.PATTERN:
                content = self._get_pattern_response(messages)
            else:
                content = self._get_default_response(messages)

            # JSON 응답이면 문자열로 변환
            if isinstance(content, dict):
                content = json.dumps(content)

            # 토큰 사용량 계산
            self._last_usage = self._calculate_usage(messages, content)

            response = LLMResponse(
                content=content,
                model="mock-model",
                usage=self._last_usage.copy()
            )

        except Exception as e:
            error = e
            raise

        finally:
            # 호출 기록
            duration_ms = (time.time() - start_time) * 1000
            self.call_count += 1

            record = CallRecord(
                messages=messages.copy(),
                response=response if error is None else LLMResponse(content="", model="mock"),
                timestamp=start_time,
                duration_ms=duration_ms,
                error=error,
            )
            self.call_history.append(record)

        return response

    def complete_json(self, messages: List[LLMMessage], schema: Dict[str, Any]) -> Dict[str, Any]:
        """Mock JSON 응답 생성"""
        response = self.complete(messages)
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            # 응답이 이미 dict면 그대로 반환
            return {"action": "assess_patient", "target": "general", "reasoning": "Default assessment"}

    def _check_error_injection(self):
        """에러 주입 체크"""
        import random

        if self.error_after_n_calls and self.call_count >= self.error_after_n_calls:
            raise RuntimeError(f"Injected error after {self.call_count} calls")

        if self.error_rate > 0 and random.random() < self.error_rate:
            raise RuntimeError("Random injected error")

    def _get_sequential_response(self) -> Union[str, Dict]:
        """순차적 응답 반환"""
        if self._sequential_index < len(self.sequential_responses):
            response = self.sequential_responses[self._sequential_index]
            self._sequential_index += 1
            return response
        return {"action": "wait", "target": "none", "reasoning": "No more responses"}

    def _get_golden_response(self) -> Dict[str, Any]:
        """Golden Agent 응답 반환"""
        if self._golden_index < len(self.golden_responses):
            response = self.golden_responses[self._golden_index]
            self._golden_index += 1
            return response
        return {"action": "complete", "target": "episode", "reasoning": "All required actions completed"}

    def _get_pattern_response(self, messages: List[LLMMessage]) -> Union[str, Dict]:
        """패턴 매칭 기반 응답"""
        for pattern in self.patterns:
            if pattern.matches(messages):
                logger.debug(f"Pattern matched: {pattern.pattern.pattern}")
                return pattern.response

        return self._get_default_response(messages)

    def _get_default_response(self, messages: List[LLMMessage]) -> Dict[str, Any]:
        """기본 응답"""
        return {
            "action": "assess_patient",
            "target": "clinical_status",
            "reasoning": "Continuing patient assessment"
        }

    def _calculate_usage(self, messages: List[LLMMessage], response: str) -> Dict[str, int]:
        """토큰 사용량 계산 (근사치)"""
        prompt_tokens = sum(len(m.content) // 4 for m in messages)
        completion_tokens = len(response) // 4
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    # ========== 검증 헬퍼 메서드 ==========

    def get_call_count(self) -> int:
        """총 호출 횟수"""
        return self.call_count

    def get_last_call(self) -> Optional[CallRecord]:
        """마지막 호출 기록"""
        return self.call_history[-1] if self.call_history else None

    def get_calls_with_pattern(self, pattern: str) -> List[CallRecord]:
        """특정 패턴이 포함된 호출 목록"""
        regex = re.compile(pattern, re.IGNORECASE)
        result = []
        for record in self.call_history:
            for msg in record.messages:
                if regex.search(msg.content):
                    result.append(record)
                    break
        return result

    def verify_action_sequence(self, expected_actions: List[str]) -> bool:
        """응답에서 예상 액션 시퀀스가 있는지 검증"""
        actual_actions = []
        for record in self.call_history:
            try:
                data = json.loads(record.response.content)
                if "action" in data:
                    actual_actions.append(data["action"])
            except (json.JSONDecodeError, KeyError):
                continue

        # 순서대로 포함되는지 확인
        expected_idx = 0
        for action in actual_actions:
            if expected_idx < len(expected_actions) and action == expected_actions[expected_idx]:
                expected_idx += 1
        return expected_idx == len(expected_actions)

    def reset(self):
        """상태 초기화"""
        self.call_count = 0
        self.call_history.clear()
        self._golden_index = 0
        self._sequential_index = 0
        self._last_usage = {}
