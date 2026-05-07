"""
Base Adapter
외부 벤치마크 어댑터의 기본 인터페이스
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from cga_bench.env.core.state import PatientState2
from cga_bench.env.core.actions import Action2


@dataclass
class AdaptedAction:
    """어댑터가 변환한 행동"""
    original_action: Dict[str, Any]  # 원본 형식
    cga_action: Action2  # CGA-Bench 형식
    mapping_confidence: float = 1.0  # 매핑 신뢰도
    notes: str = ""


@dataclass
class AdaptedEpisode:
    """어댑터가 변환한 에피소드"""
    episode_id: str
    source_benchmark: str
    original_task_id: str

    # 변환된 데이터
    initial_state: PatientState2
    actions: List[AdaptedAction]
    final_state: Optional[PatientState2] = None

    # 메타데이터
    guideline_id: Optional[str] = None
    task_success: bool = False
    original_metrics: Dict[str, Any] = field(default_factory=dict)

    # 변환 품질
    adaptation_warnings: List[str] = field(default_factory=list)


class BaseAdapter(ABC):
    """
    외부 벤치마크 어댑터 기본 클래스

    각 벤치마크(MedAgentBench, AgentClinic 등)에 대한
    변환 로직을 구현
    """

    def __init__(self, benchmark_name: str):
        self.benchmark_name = benchmark_name
        self.guideline_mappings: Dict[str, str] = {}

    @abstractmethod
    def load_patient(self, source_data: Dict) -> PatientState2:
        """
        소스 데이터에서 환자 상태 로드

        Args:
            source_data: 원본 벤치마크의 환자 데이터

        Returns:
            PatientState2 객체
        """
        pass

    @abstractmethod
    def convert_action(self, source_action: Dict) -> AdaptedAction:
        """
        소스 행동을 CGA-Bench Action2로 변환

        Args:
            source_action: 원본 벤치마크의 행동 데이터

        Returns:
            AdaptedAction 객체
        """
        pass

    @abstractmethod
    def convert_action_log(self, action_log: List[Dict]) -> List[AdaptedAction]:
        """
        행동 로그 전체 변환

        Args:
            action_log: 원본 벤치마크의 행동 로그

        Returns:
            AdaptedAction 리스트
        """
        pass

    @abstractmethod
    def adapt_episode(self, source_episode: Dict) -> AdaptedEpisode:
        """
        에피소드 전체 변환

        Args:
            source_episode: 원본 벤치마크의 에피소드 데이터

        Returns:
            AdaptedEpisode 객체
        """
        pass

    def map_task_to_guideline(self, task_id: str) -> Optional[str]:
        """
        Task ID를 Runtime DSL 파일 경로로 매핑

        Args:
            task_id: 원본 벤치마크의 task ID

        Returns:
            Runtime DSL 파일 경로 또는 None
        """
        return self.guideline_mappings.get(task_id)

    def register_guideline_mapping(self, task_id: str, dsl_path: str):
        """가이드라인 매핑 등록"""
        self.guideline_mappings[task_id] = dsl_path

    def load_guideline_mappings(self, filepath: Path):
        """매핑 파일 로드"""
        import yaml

        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        mappings = data.get('task_guideline_mappings', {})
        self.guideline_mappings.update(mappings)

    def validate_adaptation(self, episode: AdaptedEpisode) -> List[str]:
        """
        변환 결과 검증

        Returns:
            경고 메시지 리스트
        """
        warnings = []

        # 기본 검증
        if not episode.initial_state:
            warnings.append("Missing initial state")

        if not episode.actions:
            warnings.append("No actions in episode")

        if not episode.guideline_id:
            warnings.append("No guideline mapping found")

        return warnings
