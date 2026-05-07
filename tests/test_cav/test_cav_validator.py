"""Tests for scripts.cav.cav_validator.

These tests build a tiny CAV fixture under tmp_path, point CAV_PATH at it
via monkeypatch, and verify the filter / membership API.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))

from cga_bench.scripts.cav import cav_validator  # noqa: E402


@pytest.fixture
def fixture_cav(tmp_path: Path) -> Path:
    """Write a tiny CAV artifact for tests."""
    cav = {
        "version": "0.5",
        "policy": "strict",
        "build_date": "2026-05-01T00:00:00+00:00",
        "summary": {
            "total_entries": 3,
            "by_tier": {"explicit": 2, "implicit": 1},
            "by_kind": {"medication": 1, "lab": 1, "assessment": 1},
            "rxnorm_mapped": 1,
        },
        "metadata": {},
        "entries": {
            "give_aspirin": {
                "tier": "explicit",
                "action_kind": "medication",
                "raw_forms": ["give_aspirin", "aspirin"],
                "rxnorm": {"rxcui": "1191", "tty": "IN", "rxnorm_name": "Aspirin"},
                "occurrences": [],
            },
            "order_lab_lactate": {
                "tier": "explicit",
                "action_kind": "lab",
                "raw_forms": ["order_lab_lactate"],
                "rxnorm": None,
                "occurrences": [],
            },
            "assess_vital_signs": {
                "tier": "implicit",
                "action_kind": "assessment",
                "raw_forms": ["assess_vital_signs", "check_vitals"],
                "rxnorm": None,
                "occurrences": [],
            },
        },
    }
    p = tmp_path / "fixture_cav.json"
    p.write_text(json.dumps(cav), encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def _clear_cache_each_test():
    cav_validator.clear_cache()
    yield
    cav_validator.clear_cache()


def test_load_cav_explicit_path(fixture_cav: Path):
    cav = cav_validator.load_cav(fixture_cav)
    assert cav["version"] == "0.5"
    assert "give_aspirin" in cav["entries"]


def test_load_cav_via_env_var(monkeypatch: pytest.MonkeyPatch, fixture_cav: Path):
    monkeypatch.setenv("CAV_PATH", str(fixture_cav))
    cav = cav_validator.load_cav()
    assert cav["entries"]["give_aspirin"]["rxnorm"]["rxcui"] == "1191"


def test_load_cav_default_path_real_artifact():
    """The real cav_v0_5.json may or may not exist depending on whether
    Phase 4 has run. If it exists, load it; otherwise this test skips.
    """
    if not cav_validator._DEFAULT_CAV_PATH.is_file():
        pytest.skip("Real CAV artifact not built yet")
    cav = cav_validator.load_cav()
    assert cav["version"] == "0.5"
    assert cav["summary"]["total_entries"] > 0


def test_known_explicit_id_passes(fixture_cav: Path):
    cav = cav_validator.load_cav(fixture_cav)
    assert cav_validator.is_in_cav("give_aspirin", cav) is True
    assert cav_validator.is_in_cav("order_lab_lactate", cav) is True


def test_known_extension_id_dropped(fixture_cav: Path):
    cav = cav_validator.load_cav(fixture_cav)
    # "give_cefazolin" is in extension-tier per the real harvest, so the
    # Strict-policy CAV artifact does NOT have it as an entry.
    assert cav_validator.is_in_cav("give_cefazolin", cav) is False


def test_unknown_id_dropped(fixture_cav: Path):
    cav = cav_validator.load_cav(fixture_cav)
    assert cav_validator.is_in_cav("totally_made_up_action_xyz", cav) is False


def test_filter_preserves_order(fixture_cav: Path):
    cav = cav_validator.load_cav(fixture_cav)
    actions = ["assess_vital_signs", "unknown_one", "give_aspirin", "unknown_two", "order_lab_lactate"]
    kept, _dropped = cav_validator.filter_action_list(actions, cav=cav)
    assert kept == ["assess_vital_signs", "give_aspirin", "order_lab_lactate"]


def test_filter_returns_dropped_with_reason(fixture_cav: Path):
    cav = cav_validator.load_cav(fixture_cav)
    actions = ["give_aspirin", "give_cefazolin", "totally_made_up"]
    kept, dropped = cav_validator.filter_action_list(actions, context="expected", cav=cav)
    assert kept == ["give_aspirin"]
    assert len(dropped) == 2
    for d in dropped:
        assert d["reason"] == "not_in_cav"
        assert d["context"] == "expected"
        assert d["action_id"] in {"give_cefazolin", "totally_made_up"}
