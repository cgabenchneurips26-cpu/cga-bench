"""
Episode Runner
에피소드 시뮬레이션 실행 및 관리
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Protocol
from datetime import datetime
import logging

from cga_bench.env.core.state import (
    PatientState2,
    EpisodeState,
    TimeManager,
    DispositionStatus,
)
from cga_bench.env.core.actions import (
    Action2,
    ActionResult,
    ActionValidator,
    ActionStatus,
)

logger = logging.getLogger(__name__)


class AgentProtocol(Protocol):
    """에이전트 프로토콜"""

    def select_action(self, state: PatientState2) -> Action2:
        """현재 상태에서 행동 선택"""
        ...

    def receive_feedback(self, result: ActionResult) -> None:
        """행동 결과 피드백 수신"""
        ...


class EnvironmentProtocol(Protocol):
    """환경 프로토콜"""

    def step(self, action: Action2) -> tuple:
        """
        행동 수행 및 다음 상태 반환

        Returns:
            (next_state: PatientState2, reward: float, done: bool, info: dict)
        """
        ...

    def reset(self, scenario_id: str) -> PatientState2:
        """환경 리셋"""
        ...


@dataclass
class EpisodeConfig:
    """에피소드 설정"""
    scenario_id: str
    agent_id: str
    max_steps: int = 100
    max_time_minutes: float = 480.0  # 8시간
    budget_limit_tokens: int = 100000
    budget_limit_tool_calls: int = 50
    auto_terminate_on_disposition: bool = True
    record_detailed_logs: bool = True


@dataclass
class EpisodeResult:
    """에피소드 실행 결과"""
    episode_id: str
    scenario_id: str
    agent_id: str

    # 상태-행동 시퀀스
    states: List[PatientState2] = field(default_factory=list)
    actions: List[Action2] = field(default_factory=list)
    action_results: List[ActionResult] = field(default_factory=list)

    # 메타데이터
    total_steps: int = 0
    total_time_minutes: float = 0.0
    total_llm_calls: int = 0
    total_tokens: int = 0
    total_tool_calls: int = 0

    # 종료 정보
    termination_reason: str = ""
    final_disposition: Optional[str] = None
    success: bool = False

    # 타이밍
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    wall_time_seconds: float = 0.0


class EpisodeRunner:
    """
    에피소드 실행기
    에이전트와 환경 간의 상호작용 조율
    """

    def __init__(
        self,
        config: EpisodeConfig,
        environment: Optional[EnvironmentProtocol] = None,
        action_validator: Optional[ActionValidator] = None,
    ):
        self.config = config
        self.environment = environment
        self.action_validator = action_validator
        self.time_manager = TimeManager()

        # Episode state
        self.episode_state: Optional[EpisodeState] = None
        self.episode_result: Optional[EpisodeResult] = None

        # Callbacks
        self.on_step_start: Optional[Callable[[int, PatientState2], None]] = None
        self.on_step_end: Optional[Callable[[int, Action2, ActionResult], None]] = None
        self.on_episode_end: Optional[Callable[[EpisodeResult], None]] = None

    def initialize(self, initial_state: PatientState2) -> None:
        """에피소드 초기화"""
        import uuid

        episode_id = f"ep_{uuid.uuid4().hex[:8]}"

        self.episode_state = EpisodeState(
            episode_id=episode_id,
            scenario_id=self.config.scenario_id,
            agent_id=self.config.agent_id,
            current_state=initial_state,
            start_time=datetime.now(),
        )

        self.episode_result = EpisodeResult(
            episode_id=episode_id,
            scenario_id=self.config.scenario_id,
            agent_id=self.config.agent_id,
            start_time=datetime.now(),
        )

        self.time_manager = TimeManager(datetime.now())
        logger.info(f"Episode initialized: {episode_id}")

    def step(
        self,
        action: Action2,
        next_state: Optional[PatientState2] = None,
        time_elapsed: float = 5.0
    ) -> ActionResult:
        """
        단일 스텝 실행

        Args:
            action: 에이전트 행동
            next_state: 다음 상태 (None이면 환경에서 계산)
            time_elapsed: 경과 시간 (분)

        Returns:
            ActionResult
        """
        if not self.episode_state or self.episode_state.is_terminated:
            raise RuntimeError("Episode not initialized or already terminated")

        step_num = self.episode_state.current_step

        # Step start callback
        if self.on_step_start:
            self.on_step_start(step_num, self.episode_state.current_state)

        # Validate action
        if self.action_validator:
            is_valid, violation_type, message = self.action_validator.validate(action)
            if not is_valid:
                logger.warning(f"Invalid action: {message}")
                # 무효 행동도 기록은 함

        # 시간 진행
        self.time_manager.advance(time_elapsed)
        self.episode_state.advance_time(time_elapsed)

        # 환경 스텝 (있으면)
        if self.environment and next_state is None:
            next_state, reward, done, info = self.environment.step(action)
        elif next_state is None:
            # 환경 없이 외부에서 상태 제공
            next_state = self.episode_state.current_state
            done = False

        # Action result
        result = ActionResult(
            action_id=action.action_id,
            success=True,
            time_elapsed_minutes=time_elapsed,
        )

        action.status = ActionStatus.COMPLETED
        action.timestamp_minutes = self.episode_state.current_time_minutes

        # 상태 전이 기록
        self.episode_state.record_action(action.action_id, next_state)
        self.episode_state.tool_calls += 1

        # 결과 기록
        if self.episode_result:
            self.episode_result.states.append(next_state)
            self.episode_result.actions.append(action)
            self.episode_result.action_results.append(result)
            self.episode_result.total_steps = step_num + 1
            self.episode_result.total_time_minutes = self.episode_state.current_time_minutes
            self.episode_result.total_tool_calls = self.episode_state.tool_calls

        # Step end callback
        if self.on_step_end:
            self.on_step_end(step_num, action, result)

        # 종료 조건 체크
        self._check_termination_conditions(next_state)

        return result

    def _check_termination_conditions(self, state: PatientState2) -> None:
        """종료 조건 확인"""
        if not self.episode_state:
            return

        # 최대 스텝 초과
        if self.episode_state.current_step >= self.config.max_steps:
            self.terminate("max_steps_exceeded")
            return

        # 최대 시간 초과
        if self.episode_state.current_time_minutes >= self.config.max_time_minutes:
            self.terminate("max_time_exceeded")
            return

        # 예산 초과
        if self.episode_state.tokens_used >= self.config.budget_limit_tokens:
            self.terminate("budget_exhausted_tokens")
            return

        if self.episode_state.tool_calls >= self.config.budget_limit_tool_calls:
            self.terminate("budget_exhausted_tool_calls")
            return

        # 배치 완료
        if self.config.auto_terminate_on_disposition:
            if state.disposition_status in [
                DispositionStatus.ADMITTED,
                DispositionStatus.DISCHARGED,
                DispositionStatus.TRANSFERRED,
            ]:
                self.terminate("disposition_complete", success=True)
                return

    def terminate(self, reason: str, success: bool = False) -> None:
        """에피소드 종료"""
        if not self.episode_state:
            return

        self.episode_state.terminate(reason)

        if self.episode_result:
            self.episode_result.termination_reason = reason
            self.episode_result.success = success
            self.episode_result.end_time = datetime.now()
            self.episode_result.final_disposition = (
                self.episode_state.current_state.disposition_status.value
            )

            if self.episode_result.start_time:
                delta = self.episode_result.end_time - self.episode_result.start_time
                self.episode_result.wall_time_seconds = delta.total_seconds()

        logger.info(f"Episode terminated: {reason}")

        # Episode end callback
        if self.on_episode_end and self.episode_result:
            self.on_episode_end(self.episode_result)

    def run(
        self,
        agent: AgentProtocol,
        initial_state: PatientState2
    ) -> Optional[EpisodeResult]:
        """
        전체 에피소드 실행

        Args:
            agent: 에이전트
            initial_state: 초기 환자 상태

        Returns:
            EpisodeResult
        """
        self.initialize(initial_state)

        if self.episode_state is None:
            raise RuntimeError("Episode state not initialized")

        while not self.episode_state.is_terminated:
            current_state = self.episode_state.current_state

            # 에이전트 행동 선택
            action = agent.select_action(current_state)

            # 환경 스텝
            result = self.step(action)

            # 에이전트 피드백
            agent.receive_feedback(result)

        return self.episode_result

    def get_episode_log(self) -> Dict[str, Any]:
        """에피소드 로그 반환"""
        if not self.episode_result:
            return {}

        return {
            "episode_id": self.episode_result.episode_id,
            "scenario_id": self.episode_result.scenario_id,
            "agent_id": self.episode_result.agent_id,
            "total_steps": self.episode_result.total_steps,
            "total_time_minutes": self.episode_result.total_time_minutes,
            "termination_reason": self.episode_result.termination_reason,
            "success": self.episode_result.success,
            "states": [s.state_id for s in self.episode_result.states],
            "actions": [a.action_id for a in self.episode_result.actions],
        }
