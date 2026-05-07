"""Tests for evaluator shims backed by verdict_matrix_v6.json.

Validates:
1. All 6 shims instantiate without error
2. W8 filter yields exactly 14,826 episodes
3. Each shim's verdict matches the raw JSON
4. No imports from assessor_core or cpg_engine (isolation check)
"""

from __future__ import annotations

import json
from pathlib import Path

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims import (
    SHIM_REGISTRY,
    ACovShim,
    ACProxyShim,
    C2Shim,
    DxEMShim,
    MABProxyShim,
    V4HardShim,
)
from audit.shims._verdict_cache import (
    COLUMN_MAP,
    W8_EXCLUDED_MODEL,
    get_all_episode_ids,
    get_episode_count,
    get_verdict,
    load_w8_episodes,
)
import pytest

VERDICT_MATRIX_PATH = Path(__file__).resolve().parents[2] / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"

# (shim_registry_key, shim_class, column_key_for_COLUMN_MAP)
SHIM_COLUMN_MAP: list[tuple[str, type, str]] = [
    ("dxem", DxEMShim, "dxem"),
    ("ac_proxy", ACProxyShim, "ac_proxy"),
    ("mab_proxy", MABProxyShim, "mab_proxy"),
    ("c2_shim", C2Shim, "c2"),
    ("acov_shim", ACovShim, "acov"),
    ("v4_hard", V4HardShim, "v4_hard"),
]


@pytest.fixture(scope="module")
def raw_per_episode() -> list[dict]:
    """Load raw per_episode list for cross-checking."""
    with open(VERDICT_MATRIX_PATH) as f:
        data = json.load(f)
    return data["per_episode"]


@pytest.fixture(scope="module")
def raw_per_episode_by_id(raw_per_episode: list[dict]) -> dict[str, dict]:
    """Build {episode_id: entry} from the raw list, W8-filtered."""
    return {ep["episode_id"]: ep for ep in raw_per_episode if ep.get("model") != W8_EXCLUDED_MODEL}


class TestVerdictCache:
    """Test the verdict cache loader and W8 filter."""

    def test_w8_episode_count(self) -> None:
        assert get_episode_count() == 14826, f"W8 filter should yield 14,826 episodes, got {get_episode_count()}"

    def test_w8_excludes_deepseek(self) -> None:
        episodes = load_w8_episodes()
        for ep in episodes.values():
            assert ep.get("model") != W8_EXCLUDED_MODEL

    def test_all_episode_ids_returns_list(self) -> None:
        ids = get_all_episode_ids()
        assert isinstance(ids, list)
        assert len(ids) == 14826

    def test_get_verdict_raises_on_missing_episode(self) -> None:
        with pytest.raises(KeyError, match="not found"):
            get_verdict("nonexistent_episode_id_xyz", "dxem")

    def test_get_verdict_raises_on_missing_column(self) -> None:
        ids = get_all_episode_ids()
        with pytest.raises(KeyError, match="not found"):
            get_verdict(ids[0], "NonexistentColumn")


class TestShimInstantiation:
    """Test that all 6 shims instantiate and have correct metadata."""

    @pytest.mark.parametrize("name,cls", list(SHIM_REGISTRY.items()))
    def test_instantiate(self, name: str, cls: type) -> None:
        shim = cls()
        assert isinstance(shim, Evaluator)
        assert isinstance(shim.meta, EvaluatorMeta)
        assert shim.meta.name
        assert shim.meta.family

    def test_registry_has_expected_entries(self) -> None:
        # 6 Option-B shims + 4 Option-C wrappers = 10
        assert len(SHIM_REGISTRY) >= 6
        for name in ("dxem", "ac_proxy", "mab_proxy", "c2_shim", "acov_shim", "v4_hard"):
            assert name in SHIM_REGISTRY, f"Missing core shim: {name}"

    @pytest.mark.parametrize(
        "name,expected_family",
        [
            ("dxem", "TOM"),
            ("ac_proxy", "ASC"),
            ("mab_proxy", "PAF"),
            ("c2_shim", "CwT"),
            ("acov_shim", "ACov"),
            ("v4_hard", "TCC"),
        ],
    )
    def test_family_labels(self, name: str, expected_family: str) -> None:
        shim = SHIM_REGISTRY[name]()
        assert shim.meta.family == expected_family


class TestShimVerdicts:
    """Test that each shim's verdict matches the raw JSON data."""

    @pytest.mark.parametrize("shim_name,cls,col_key", SHIM_COLUMN_MAP, ids=[s[0] for s in SHIM_COLUMN_MAP])
    def test_spot_check_first_20(
        self,
        shim_name: str,
        cls: type,
        col_key: str,
        raw_per_episode_by_id: dict[str, dict],
    ) -> None:
        shim = cls()
        json_field = COLUMN_MAP[col_key]
        w8_episodes = load_w8_episodes()
        checked = 0
        for ep_id, ep_data in w8_episodes.items():
            if checked >= 20:
                break
            raw_val = raw_per_episode_by_id[ep_id][json_field]
            expected = bool(raw_val)
            actual = shim.verdict({"episode_id": ep_id})
            assert actual == expected, f"Shim {shim_name} mismatch on {ep_id}: expected {expected}, got {actual}"
            checked += 1

    @pytest.mark.parametrize("shim_name,cls,col_key", SHIM_COLUMN_MAP, ids=[s[0] for s in SHIM_COLUMN_MAP])
    def test_full_corpus_consistency(
        self,
        shim_name: str,
        cls: type,
        col_key: str,
        raw_per_episode_by_id: dict[str, dict],
    ) -> None:
        """Verify all 14,826 episodes match for each shim."""
        shim = cls()
        json_field = COLUMN_MAP[col_key]
        w8_episodes = load_w8_episodes()
        mismatches = 0
        for ep_id in w8_episodes:
            raw_val = raw_per_episode_by_id[ep_id][json_field]
            expected = bool(raw_val)
            actual = shim.verdict({"episode_id": ep_id})
            if actual != expected:
                mismatches += 1
        assert mismatches == 0, f"Shim {shim_name}: {mismatches}/{len(w8_episodes)} mismatches"


class TestIsolation:
    """Verify audit shims do not import from scorer-side modules."""

    @staticmethod
    def _has_forbidden_import(source: str, module_name: str) -> bool:
        """Check for actual import statements, ignoring comments and docstrings."""
        for line in source.splitlines():
            stripped = line.strip()
            # Skip comments and docstring lines
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
                continue
            if f"from {module_name}" in stripped or f"import {module_name}" in stripped:
                return True
        return False

    def test_no_assessor_core_imports(self) -> None:
        import audit.evaluator_base
        import audit.shims._verdict_cache
        import audit.shims.dxem
        import audit.shims.v4_hard

        modules = [
            audit.evaluator_base,
            audit.shims._verdict_cache,
            audit.shims.dxem,
            audit.shims.v4_hard,
        ]
        for mod in modules:
            src = Path(mod.__file__).read_text()
            assert not self._has_forbidden_import(src, "assessor_core"), f"{mod.__name__} imports assessor_core"
            assert not self._has_forbidden_import(src, "cpg_engine"), f"{mod.__name__} imports cpg_engine"
