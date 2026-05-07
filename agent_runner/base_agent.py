"""Base Agent: 에이전트 기본 인터페이스"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import logging
from typing import Any

logger = logging.getLogger(__name__)

from cga_bench.cpg_model.schemas.base import Action, EpisodeLog, PatientState
from cga_bench.scenario_engine.environment import ClinicalEnvironment, Observation
from cga_bench.tool_api.base import ToolRegistry, ToolResult


@dataclass
class AgentConfig:
    """에이전트 설정 - 예산 한도는 명시적으로 설정 필수"""

    agent_id: str
    agent_type: str = "base"
    max_actions_per_step: int = 3
    enable_justification: bool = True
    # 예산 한도는 None이면 무제한, 명시적 설정 시 해당 값으로 제한
    budget_limit_tokens: int | None = None
    budget_limit_tool_calls: int | None = None
    # LLM seed for reproducibility (propagated to LLMConfig.seed)
    llm_seed: int | None = None

    def __post_init__(self):
        """예산 설정 검증"""
        # 예산 한도가 설정된 경우 양수여야 함
        if self.budget_limit_tokens is not None and self.budget_limit_tokens <= 0:
            raise ValueError("budget_limit_tokens must be positive if set")
        if self.budget_limit_tool_calls is not None and self.budget_limit_tool_calls <= 0:
            raise ValueError("budget_limit_tool_calls must be positive if set")


@dataclass
class AgentMetrics:
    """에이전트 메트릭"""

    total_llm_calls: int = 0
    total_tokens: int = 0
    total_tool_calls: int = 0
    actions_taken: list[Action] = field(default_factory=list)


class BaseAgent(ABC):
    """에이전트 기본 클래스

    모든 에이전트는 이 클래스를 상속하여 구현:
    - RAG Agent: 검색 증강 생성 에이전트
    - Planner Agent: 계획 기반 에이전트
    - Reflection Agent: 자기 반성 에이전트
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.metrics = AgentMetrics()
        self.tool_registry = ToolRegistry()

    @abstractmethod
    def decide(self, observation: Observation) -> list[Action]:
        """관측을 받아 행동 결정

        Args:
            observation: 현재 환경 관측

        Returns:
            수행할 행동 목록
        """
        pass

    @abstractmethod
    def reset(self):
        """에이전트 상태 리셋"""
        pass

    def run_episode(self, environment: ClinicalEnvironment, scenario_id: str) -> EpisodeLog:
        """전체 에피소드 실행

        Args:
            environment: 임상 환경
            scenario_id: 시나리오 ID

        Returns:
            에피소드 로그
        """
        self.reset()
        environment.reset()

        states = [environment.current_state.model_copy(deep=True)]
        actions = []
        observations_list = []

        done = False
        max_steps = int(environment.config.max_duration_minutes / environment.config.time_step_minutes) + 10
        step_count = 0
        consecutive_empty = 0
        # Early termination threshold lowered 5 -> 3 (2026-04-22) for full_706_v6
        # re-sweep: Task-2 labelling split + alias-map fix made the great bulk of
        # "empty" returns into true scaffold-level exhaustion (not transient LLM
        # hiccups), so three consecutive empty decides is sufficient evidence to
        # stop and frees wall-clock for the next episode.
        max_consecutive_empty = 3

        while not done and step_count < max_steps:
            step_count += 1

            # 관측 획득
            obs = environment._get_observation()
            observations_list.append(obs.__dict__)

            # 행동 결정
            decided_actions = self.decide(obs)

            if not decided_actions:
                consecutive_empty += 1
                if consecutive_empty >= max_consecutive_empty:
                    # Agents may classify the empty-action cause — e.g. the RAG
                    # scaffold distinguishes "all-completed hallucination" from
                    # "genuine empty LLM response". When the hint is set, use it
                    # so downstream metric aggregation can separate the two
                    # distinct failure modes instead of collapsing both under
                    # ``consecutive_empty_actions``.
                    preferred = getattr(self, "_preferred_termination_reason", None)
                    termination_reason = preferred or "consecutive_empty_actions"
                    logger.warning(
                        f"[{scenario_id}] {max_consecutive_empty} consecutive empty actions, "
                        f"terminating episode early at step {step_count} "
                        f"(reason={termination_reason})"
                    )
                    environment.termination_reason = termination_reason
                    done = True
                    break
                # Empty decide → retry without advancing simulated clock.
                # Clock only advances on successful actions to prevent
                # spurious timing violations from LLM parse failures.
                continue
            else:
                consecutive_empty = 0  # Reset on successful action
                # 행동 수행
                for action in decided_actions:
                    obs, reward, done, info = environment.step(action)
                    actions.append(action)
                    # Deep copy state to preserve timestamp at action time
                    states.append(environment.current_state.model_copy(deep=True))
                    self.metrics.actions_taken.append(action)
                    self.metrics.total_tool_calls += 1

                    if done:
                        break

            # 예산 초과 체크
            if self._budget_exceeded():
                done = True

        return EpisodeLog(
            episode_id=f"{self.config.agent_id}_{scenario_id}",
            scenario_id=scenario_id,
            agent_id=self.config.agent_id,
            states=states,
            actions=actions,
            observations=observations_list,
            total_duration_minutes=environment.current_time,
            total_llm_calls=self.metrics.total_llm_calls,
            total_tokens=self.metrics.total_tokens,
            total_tool_calls=self.metrics.total_tool_calls,
            termination_reason=environment.termination_reason or "completed",
            final_disposition=environment.current_state.disposition_status,
        )

    def _budget_exceeded(self) -> bool:
        """예산 초과 여부 확인 - None은 무제한"""
        if self.config.budget_limit_tokens is not None:
            if self.metrics.total_tokens > self.config.budget_limit_tokens:
                return True
        if self.config.budget_limit_tool_calls is not None:
            if self.metrics.total_tool_calls > self.config.budget_limit_tool_calls:
                return True
        return False

    def execute_tool(self, tool_name: str, args: dict[str, Any], state: PatientState) -> ToolResult:
        """도구 실행"""
        tool = self.tool_registry.get(tool_name)
        if not tool:
            return ToolResult(success=False, message=f"Unknown tool: {tool_name}", error="Tool not found")
        return tool.execute(args, state)
