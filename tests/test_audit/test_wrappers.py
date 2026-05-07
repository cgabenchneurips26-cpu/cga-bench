"""Tests for Option C alternative evaluator wrappers.

Verifies that metric-threshold evaluators and the AlwaysTrue negative
control conform to the Evaluator ABC and produce correct verdicts.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims._verdict_cache import load_w8_episodes
from audit.wrappers import WRAPPER_REGISTRY
from audit.wrappers.metric_evaluators import (
    ActionCoverageEvaluator,
    AlwaysTrueEvaluator,
    C2ScoreEvaluator,
    MABF1Evaluator,
)
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

WRAPPER_CLASSES = [
    ActionCoverageEvaluator,
    C2ScoreEvaluator,
    MABF1Evaluator,
    AlwaysTrueEvaluator,
]

METRIC_WRAPPERS = [
    (ActionCoverageEvaluator, "action_coverage", 0.8),
    (C2ScoreEvaluator, "c2_score", 0.5),
    (MABF1Evaluator, "mab_f1", 0.5),
]


@pytest.fixture(scope="module")
def w8_episodes() -> dict[str, dict[str, Any]]:
    return load_w8_episodes()


@pytest.fixture(scope="module")
def sample_episode_ids(w8_episodes: dict) -> list[str]:
    """First 10 episode IDs for spot-checks."""
    return list(w8_episodes.keys())[:10]


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", WRAPPER_CLASSES, ids=lambda c: c.__name__)
def test_instantiation(cls: type) -> None:
    ev = cls()
    assert isinstance(ev, Evaluator)
    assert isinstance(ev.meta, EvaluatorMeta)
    assert ev.meta.name
    assert ev.meta.family


@pytest.mark.parametrize("cls", WRAPPER_CLASSES, ids=lambda c: c.__name__)
def test_verdict_returns_bool(cls: type, sample_episode_ids: list[str]) -> None:
    ev = cls()
    for ep_id in sample_episode_ids:
        result = ev.verdict({"episode_id": ep_id})
        assert isinstance(result, bool), f"{cls.__name__}.verdict returned {type(result)}"


# ---------------------------------------------------------------------------
# Metric threshold correctness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls,field,threshold",
    METRIC_WRAPPERS,
    ids=lambda x: x.__name__ if isinstance(x, type) else str(x),
)
def test_metric_threshold_correctness(
    cls: type,
    field: str,
    threshold: float,
    w8_episodes: dict,
    sample_episode_ids: list[str],
) -> None:
    """Verify wrapper.verdict(ep) == (raw_metric >= threshold)."""
    ev = cls()
    for ep_id in sample_episode_ids:
        ep_data = w8_episodes[ep_id]
        raw_val = ep_data.get(field)
        if raw_val is None:
            expected = False
        else:
            expected = float(raw_val) >= threshold
        actual = ev.verdict({"episode_id": ep_id})
        assert actual == expected, (
            f"{cls.__name__}: ep={ep_id}, {field}={raw_val}, threshold={threshold}, expected={expected}, got={actual}"
        )


def test_metric_threshold_full_corpus(w8_episodes: dict) -> None:
    """Every metric wrapper produces consistent verdicts on full corpus."""
    for cls, field, threshold in METRIC_WRAPPERS:
        ev = cls()
        mismatches = 0
        for ep_id, ep_data in w8_episodes.items():
            raw_val = ep_data.get(field)
            expected = False if raw_val is None else float(raw_val) >= threshold
            actual = ev.verdict({"episode_id": ep_id})
            if actual != expected:
                mismatches += 1
        assert mismatches == 0, f"{cls.__name__}: {mismatches} mismatches on {len(w8_episodes)} episodes"


# ---------------------------------------------------------------------------
# AlwaysTrue negative control
# ---------------------------------------------------------------------------


def test_always_true_all_episodes(w8_episodes: dict) -> None:
    ev = AlwaysTrueEvaluator()
    for ep_id in w8_episodes:
        assert ev.verdict({"episode_id": ep_id}) is True


def test_always_true_meta() -> None:
    ev = AlwaysTrueEvaluator()
    assert ev.meta.family == "trivial"
    assert ev.meta.name == "AlwaysTrue"


def test_always_true_observed_features() -> None:
    ev = AlwaysTrueEvaluator()
    assert ev.observed_features() == frozenset()


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------


def test_wrapper_registry_contains_all() -> None:
    core = {"action_coverage", "c2_score", "mab_f1", "always_true"}
    assert core.issubset(WRAPPER_REGISTRY.keys())
    # Any extra keys must be dynamically-registered external-benchmark shims
    extras = set(WRAPPER_REGISTRY.keys()) - core
    assert all(k.startswith("ext_") for k in extras), (
        f"Unexpected non-ext_ keys in WRAPPER_REGISTRY: {extras - {k for k in extras if k.startswith('ext_')}}"
    )


def test_shim_registry_includes_wrappers() -> None:
    """The unified SHIM_REGISTRY should include wrapper evaluators."""
    from audit.shims import SHIM_REGISTRY

    for key in WRAPPER_REGISTRY:
        assert key in SHIM_REGISTRY, f"Wrapper {key!r} missing from SHIM_REGISTRY"


# ---------------------------------------------------------------------------
# Isolation: no imports from assessor_core or cpg_engine
# ---------------------------------------------------------------------------

_FORBIDDEN_IMPORTS = {"assessor_core", "cpg_engine"}
_WRAPPER_FILES = [
    Path(__file__).resolve().parents[2] / "audit" / "wrappers" / "__init__.py",
    Path(__file__).resolve().parents[2] / "audit" / "wrappers" / "metric_evaluators.py",
]


def test_isolation_no_forbidden_imports() -> None:
    """Wrapper modules must not import from assessor_core or cpg_engine."""
    for fpath in _WRAPPER_FILES:
        if not fpath.exists():
            continue
        source = fpath.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in _FORBIDDEN_IMPORTS, f"{fpath.name} imports {alias.name} (forbidden)"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    assert top not in _FORBIDDEN_IMPORTS, f"{fpath.name} imports from {node.module} (forbidden)"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_determinism(sample_episode_ids: list[str]) -> None:
    """Two calls to the same wrapper return identical results."""
    for cls in WRAPPER_CLASSES:
        ev = cls()
        for ep_id in sample_episode_ids:
            v1 = ev.verdict({"episode_id": ep_id})
            v2 = ev.verdict({"episode_id": ep_id})
            assert v1 == v2, f"{cls.__name__} non-deterministic on {ep_id}"
