"""Tests for LLMJudgeEvaluator — EVP-2 extensibility proof."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from audit.evaluator_base import Evaluator
from audit.shims.llm_judge_shim import LLMJudgeEvaluator


class TestLLMJudgeEvaluator:
    """Unit tests for the cached LLM-as-judge evaluator."""

    def test_is_evaluator_subclass(self) -> None:
        evaluator = LLMJudgeEvaluator()
        assert isinstance(evaluator, Evaluator)

    def test_meta_fields(self) -> None:
        evaluator = LLMJudgeEvaluator()
        assert evaluator.meta.name == "LLMJudge"
        assert evaluator.meta.family == "LLM-judge"
        assert evaluator.meta.source == "llm_judge_cache.json"

    def test_observed_features(self) -> None:
        evaluator = LLMJudgeEvaluator()
        features = evaluator.observed_features()
        assert "actions" in features
        assert "expected_actions" in features

    def test_verdict_with_cache(self) -> None:
        cache = {"ep_safe": True, "ep_unsafe": False}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(cache, f)
            cache_path = Path(f.name)

        try:
            with patch("audit.shims.llm_judge_shim._CACHE_PATH", cache_path):
                evaluator = LLMJudgeEvaluator()
                assert evaluator.verdict({"episode_id": "ep_safe"}) is True
                assert evaluator.verdict({"episode_id": "ep_unsafe"}) is False
        finally:
            cache_path.unlink()

    def test_unknown_episode_returns_false(self) -> None:
        cache = {"ep_known": True}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(cache, f)
            cache_path = Path(f.name)

        try:
            with patch("audit.shims.llm_judge_shim._CACHE_PATH", cache_path):
                evaluator = LLMJudgeEvaluator()
                assert evaluator.verdict({"episode_id": "ep_unknown"}) is False
        finally:
            cache_path.unlink()

    def test_missing_cache_file_empty(self) -> None:
        with patch(
            "audit.shims.llm_judge_shim._CACHE_PATH",
            Path("/nonexistent/path/cache.json"),
        ):
            evaluator = LLMJudgeEvaluator()
            assert len(evaluator._cache) == 0
            assert evaluator.verdict({"episode_id": "any"}) is False

    def test_registry_contains_llm_judge(self) -> None:
        from audit.shims import SHIM_REGISTRY

        assert "llm_judge" in SHIM_REGISTRY
        assert SHIM_REGISTRY["llm_judge"] is LLMJudgeEvaluator
