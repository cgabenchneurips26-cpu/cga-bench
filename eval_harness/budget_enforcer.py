"""
Budget Enforcer: NeurIPS 비판 3 대응 - Budget-Matched 평가

모든 베이스라인에 동일 예산을 부여하여 공정한 비교를 보장합니다.

예산 유형:
1. B_tok: 에피소드당 총 생성 토큰 상한
2. B_call: LLM 호출 수 + tool call 수 상한

설계 원칙:
- Reflection은 재시도할수록 예산 소모
- Planner/RAG도 동일 예산 내에서 best-of-N 샘플링 허용
- 예산 초과 시 명시적 처리 (terminate/warn/log)
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
import logging
import time

from cga_bench.agent_runner.llm_provider import BaseLLMProvider, LLMConfig, LLMMessage, LLMResponse

logger = logging.getLogger(__name__)


class BudgetExceededAction(Enum):
    """예산 초과 시 동작"""
    TERMINATE = "terminate"  # 즉시 종료
    WARN = "warn"           # 경고 후 계속
    LOG_ONLY = "log_only"   # 로그만 남기고 계속


@dataclass
class BudgetConfig:
    """예산 설정"""
    # 토큰 예산
    token_limit: int = 50000

    # 호출 예산 (LLM + tool)
    call_limit: int = 100

    # 예산 초과 시 동작
    on_exceeded: BudgetExceededAction = BudgetExceededAction.TERMINATE

    # 샘플링 허용 여부
    allow_sampling: bool = True
    max_samples_per_decision: int = 3

    # 라운드별 예산 추적
    track_per_round: bool = True


@dataclass
class BudgetUsage:
    """예산 사용량 추적"""
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    llm_calls: int = 0
    tool_calls: int = 0

    # 라운드별 추적
    rounds: List[Dict[str, int]] = field(default_factory=list)
    current_round: int = 0

    # 타임스탬프
    start_time: float = 0.0
    timestamps: List[float] = field(default_factory=list)

    @property
    def total_calls(self) -> int:
        return self.llm_calls + self.tool_calls

    def start_round(self):
        """새 라운드 시작"""
        self.current_round += 1
        self.rounds.append({
            "round": self.current_round,
            "tokens_at_start": self.total_tokens,
            "calls_at_start": self.total_calls,
        })
        self.timestamps.append(time.time())

    def end_round(self):
        """라운드 종료"""
        if self.rounds:
            self.rounds[-1].update({
                "tokens_used": self.total_tokens - self.rounds[-1]["tokens_at_start"],
                "calls_used": self.total_calls - self.rounds[-1]["calls_at_start"],
                "duration": time.time() - self.timestamps[-1] if self.timestamps else 0,
            })

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "total_calls": self.total_calls,
            "rounds": self.rounds,
            "total_rounds": self.current_round,
        }


class BudgetExceededException(Exception):
    """예산 초과 예외"""
    def __init__(self, message: str, usage: BudgetUsage, config: BudgetConfig):
        super().__init__(message)
        self.usage = usage
        self.config = config


class BudgetEnforcer:
    """
    예산 강제 실행기

    에이전트의 LLM 호출과 tool 호출을 모니터링하고
    예산 제한을 강제합니다.
    """

    def __init__(self, config: BudgetConfig):
        self.config = config
        self.usage = BudgetUsage()
        self._callbacks: List[Callable] = []
        self._is_exceeded = False

    def reset(self):
        """예산 사용량 초기화"""
        self.usage = BudgetUsage()
        self.usage.start_time = time.time()
        self._is_exceeded = False

    def start_round(self):
        """새 라운드 시작 (Reflection용)"""
        self.usage.start_round()

    def end_round(self):
        """라운드 종료"""
        self.usage.end_round()

    def record_llm_call(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: Optional[int] = None
    ):
        """LLM 호출 기록"""
        if total_tokens is None:
            total_tokens = prompt_tokens + completion_tokens

        self.usage.prompt_tokens += prompt_tokens
        self.usage.completion_tokens += completion_tokens
        self.usage.total_tokens += total_tokens
        self.usage.llm_calls += 1

        self._check_budget("llm_call")

    def record_tool_call(self):
        """Tool 호출 기록"""
        self.usage.tool_calls += 1
        self._check_budget("tool_call")

    def _check_budget(self, trigger: str):
        """예산 초과 확인"""
        token_exceeded = self.usage.total_tokens > self.config.token_limit
        call_exceeded = self.usage.total_calls > self.config.call_limit

        if token_exceeded or call_exceeded:
            self._is_exceeded = True
            message = self._format_exceeded_message(token_exceeded, call_exceeded, trigger)

            if self.config.on_exceeded == BudgetExceededAction.TERMINATE:
                raise BudgetExceededException(message, self.usage, self.config)
            elif self.config.on_exceeded == BudgetExceededAction.WARN:
                logger.warning(message)
            else:  # LOG_ONLY
                logger.info(message)

            # 콜백 실행
            for callback in self._callbacks:
                callback(self.usage, self.config, trigger)

    def _format_exceeded_message(
        self,
        token_exceeded: bool,
        call_exceeded: bool,
        trigger: str
    ) -> str:
        parts = [f"Budget exceeded (trigger: {trigger})"]

        if token_exceeded:
            parts.append(
                f"Tokens: {self.usage.total_tokens}/{self.config.token_limit} "
                f"({self.usage.total_tokens / self.config.token_limit * 100:.1f}%)"
            )
        if call_exceeded:
            parts.append(
                f"Calls: {self.usage.total_calls}/{self.config.call_limit} "
                f"({self.usage.total_calls / self.config.call_limit * 100:.1f}%)"
            )

        return " | ".join(parts)

    def get_remaining_budget(self) -> Dict[str, int]:
        """남은 예산 반환"""
        return {
            "remaining_tokens": max(0, self.config.token_limit - self.usage.total_tokens),
            "remaining_calls": max(0, self.config.call_limit - self.usage.total_calls),
        }

    def get_utilization(self) -> Dict[str, float]:
        """예산 사용률 반환"""
        return {
            "token_utilization": self.usage.total_tokens / self.config.token_limit,
            "call_utilization": self.usage.total_calls / self.config.call_limit,
        }

    def is_budget_available(self, estimated_tokens: int = 0, estimated_calls: int = 1) -> bool:
        """예산 여유 확인"""
        token_ok = (self.usage.total_tokens + estimated_tokens) <= self.config.token_limit
        call_ok = (self.usage.total_calls + estimated_calls) <= self.config.call_limit
        return token_ok and call_ok

    def add_callback(self, callback: Callable):
        """예산 초과 시 호출될 콜백 등록"""
        self._callbacks.append(callback)

    def get_summary(self) -> Dict[str, Any]:
        """예산 사용 요약"""
        return {
            "config": {
                "token_limit": self.config.token_limit,
                "call_limit": self.config.call_limit,
                "on_exceeded": self.config.on_exceeded.value,
            },
            "usage": self.usage.to_dict(),
            "utilization": self.get_utilization(),
            "remaining": self.get_remaining_budget(),
            "exceeded": self._is_exceeded,
        }


class BudgetAwareLLMWrapper(BaseLLMProvider):
    """
    예산 인식 LLM 래퍼

    기존 LLM Provider를 래핑하여 자동으로 예산을 추적합니다.
    BaseLLMProvider를 상속하여 type-safe하게 사용할 수 있습니다.
    """

    def __init__(self, llm_provider: BaseLLMProvider, budget_enforcer: BudgetEnforcer):
        # BaseLLMProvider의 __init__ 호출 (wrapped provider의 config 사용)
        super().__init__(llm_provider.config)
        self._llm = llm_provider
        self._enforcer = budget_enforcer

    @property
    def last_usage(self) -> Dict[str, int]:
        """마지막 LLM 호출의 토큰 사용량 반환 (wrapped provider에서 가져옴)"""
        return self._llm.last_usage

    def get_total_tokens_from_last_call(self) -> int:
        """마지막 호출에서 사용된 총 토큰 수 반환"""
        return self._llm.get_total_tokens_from_last_call()

    def complete(self, messages: List[LLMMessage]) -> LLMResponse:
        """LLM 호출 (예산 추적 포함)"""
        # 예산 확인
        if not self._enforcer.is_budget_available(estimated_calls=1):
            raise BudgetExceededException(
                "Not enough budget for LLM call",
                self._enforcer.usage,
                self._enforcer.config
            )

        # LLM 호출
        response = self._llm.complete(messages)

        # 토큰 사용량 기록
        usage = getattr(response, 'usage', None)
        if usage:
            self._enforcer.record_llm_call(
                prompt_tokens=getattr(usage, 'prompt_tokens', 0),
                completion_tokens=getattr(usage, 'completion_tokens', 0),
                total_tokens=getattr(usage, 'total_tokens', None)
            )
        else:
            # 토큰 정보 없으면 추정
            self._enforcer.record_llm_call(total_tokens=1000)

        return response

    def complete_json(self, messages: List[LLMMessage], schema: Dict[str, Any]) -> Dict[str, Any]:
        """JSON 형식 응답 생성 (예산 추적 포함)"""
        # 예산 확인
        if not self._enforcer.is_budget_available(estimated_calls=1):
            raise BudgetExceededException(
                "Not enough budget for LLM call",
                self._enforcer.usage,
                self._enforcer.config
            )

        # LLM 호출
        response = self._llm.complete_json(messages, schema)

        # complete_json은 토큰 사용량을 직접 추적하기 어려우므로
        # wrapped provider의 last_usage 사용
        last_usage = self._llm.last_usage
        if last_usage:
            self._enforcer.record_llm_call(
                prompt_tokens=last_usage.get('prompt_tokens', 0),
                completion_tokens=last_usage.get('completion_tokens', 0),
                total_tokens=last_usage.get('total_tokens')
            )
        else:
            self._enforcer.record_llm_call(total_tokens=1000)

        return response

    @property
    def budget_enforcer(self) -> BudgetEnforcer:
        """예산 추적기 반환"""
        return self._enforcer

    @property
    def wrapped_provider(self) -> BaseLLMProvider:
        """래핑된 원본 LLM Provider 반환"""
        return self._llm


def create_budget_matched_agents(
    experiment_config: Dict[str, Any],
    llm_providers: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Budget-matched 에이전트 생성

    모든 에이전트에 동일한 예산 설정을 적용합니다.
    """
    budget_config = experiment_config.get("budget", {})

    config = BudgetConfig(
        token_limit=budget_config.get("budget_limit_tokens", 50000),
        call_limit=budget_config.get("budget_limit_calls", 100),
        on_exceeded=BudgetExceededAction(budget_config.get("on_budget_exceeded", "terminate")),
        allow_sampling=budget_config.get("allow_sampling", True),
        max_samples_per_decision=budget_config.get("max_samples_per_decision", 3),
    )

    wrapped_providers = {}
    enforcers = {}

    for agent_name, provider in llm_providers.items():
        enforcer = BudgetEnforcer(config)
        wrapped_providers[agent_name] = BudgetAwareLLMWrapper(provider, enforcer)
        enforcers[agent_name] = enforcer

    return {
        "providers": wrapped_providers,
        "enforcers": enforcers,
        "config": config,
    }
