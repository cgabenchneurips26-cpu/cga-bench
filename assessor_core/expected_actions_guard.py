"""
ExpectedActionsGuard: expected_actions 무결성 보호 + 평가 누수 탐지.

SHA-256 hash로 원본 expected_actions 불변성 보장.
Sentinel 토큰으로 CPG 출력이 에이전트 컨텍스트에 누수되는지 탐지.
"""

import copy
import hashlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ExpectedActionsGuard:
    """expected_actions 무결성 보호 및 평가 누수 탐지."""

    _SENTINEL = "__CPG_SENTINEL_DO_NOT_LEAK__"

    @staticmethod
    def preserve_original(scenario: Any) -> None:
        """평가 전 호출: deepcopy + SHA-256 hash 저장.

        Args:
            scenario: ExternalScenario instance. expected_actions를 보존.
        """
        original = copy.deepcopy(scenario.expected_actions)
        scenario._expected_actions_original = original
        scenario.original_expected_hash = hashlib.sha256(
            str(original).encode("utf-8")
        ).hexdigest()
        logger.debug(
            f"ExpectedActionsGuard: preserved {len(original)} actions, "
            f"hash={scenario.original_expected_hash[:16]}..."
        )

    @staticmethod
    def verify_integrity(scenario: Any) -> bool:
        """평가 후 호출: hash 비교로 변조 확인.

        Returns:
            True if expected_actions are unchanged, False if tampered.
        """
        stored_hash = getattr(scenario, "original_expected_hash", None)
        if stored_hash is None:
            logger.warning("ExpectedActionsGuard: no hash stored, skipping")
            return True

        current_hash = hashlib.sha256(
            str(scenario.expected_actions).encode("utf-8")
        ).hexdigest()

        if current_hash != stored_hash:
            logger.error(
                f"ExpectedActionsGuard: INTEGRITY VIOLATION! "
                f"stored={stored_hash[:16]}... current={current_hash[:16]}..."
            )
            return False

        logger.debug("ExpectedActionsGuard: integrity verified")
        return True

    @classmethod
    def inject_sentinel(cls, cpg_actions: List[str]) -> List[str]:
        """테스트용: CPG 생성 액션에 sentinel 삽입.

        Args:
            cpg_actions: CPG에서 생성된 액션 목록.

        Returns:
            sentinel이 추가된 사본.
        """
        test_actions = cpg_actions.copy()
        test_actions.append(cls._SENTINEL)
        return test_actions

    @classmethod
    def detect_leakage(
        cls,
        prompt: str = "",
        action_space: Optional[List[str]] = None,
        context: str = "",
    ) -> Dict:
        """sentinel이 에이전트 컨텍스트에 노출되었는지 확인.

        Args:
            prompt: 에이전트에 전달된 프롬프트 텍스트.
            action_space: 에이전트에 노출된 가용 액션 목록.
            context: 기타 컨텍스트 문자열.

        Returns:
            dict with 'leaked' (bool), 'leakage_points' (list), 'sentinel_value'.
        """
        action_space = action_space or []
        leakage_points = []

        if cls._SENTINEL in prompt:
            leakage_points.append("prompt")
        if cls._SENTINEL in action_space:
            leakage_points.append("action_space")
        if cls._SENTINEL in context:
            leakage_points.append("context")

        return {
            "leaked": len(leakage_points) > 0,
            "leakage_points": leakage_points,
            "sentinel_value": cls._SENTINEL,
        }

    @staticmethod
    def prevent_overwrite(
        scenario: Any, new_actions: List[str], source: str
    ) -> None:
        """CPG 출력이 expected_actions를 덮어쓰지 못하도록 차단.

        Args:
            scenario: ExternalScenario instance.
            new_actions: 새로 생성된 액션 목록.
            source: 출처 ('cpg' or 'benchmark').

        Raises:
            ValueError: source가 'cpg'가 아닌 경우.
        """
        if source == "cpg":
            scenario.expected_actions_cpg = new_actions
            logger.debug(
                f"ExpectedActionsGuard: stored {len(new_actions)} CPG actions "
                f"in expected_actions_cpg (expected_actions untouched)"
            )
        else:
            raise ValueError(
                f"prevent_overwrite: unexpected source '{source}'. "
                f"Only 'cpg' source is allowed."
            )
