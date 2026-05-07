"""Smoke test for the E9 High-Authority Core Robustness audit script.

Spec: docs/attack_gap_exp_exp/260430_e9_High-Authority_Core_Robustness.md
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def e9_module():
    """Import the experiment script as a module so we can hit its helpers."""
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    spec_path = repo_root / "scripts" / "experiments" / "exp_e39_high_authority_core.py"
    assert spec_path.exists()
    spec = importlib.util.spec_from_file_location("exp_e39", spec_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_node_authority_map_includes_real_graphs(e9_module) -> None:
    m = e9_module.build_node_authority_map()
    assert m, "expected non-empty node authority map"
    high = sum(1 for v in m.values() if v == "high")
    assert high > 0, "expected at least some high-authority nodes"


def test_build_scenario_to_graph_map_non_empty(e9_module) -> None:
    m = e9_module.build_scenario_to_graph_map()
    assert m, "expected non-empty scenario -> graph mapping"
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in m.items())


def test_compute_aggregate_metrics_minimum_keys(e9_module) -> None:
    enriched = [
        {
            "model_dir": "demo",
            "v4_hard": True,           # cached: True == FAIL (has hard violation)
            "v4_hard_high": False,     # recomputed: False == FAIL
            "ac_proxy": True,
            "c2_pass": True,
            "mab_proxy": True,
            "acov_pass": True,
            "viol_types_full": ["WITHIN"],
            "viol_types_high": ["WITHIN"],
            "kept_violation_events": 1,
            "total_violation_events": 1,
        },
        {
            "model_dir": "demo",
            "v4_hard": False,          # cached PASS
            "v4_hard_high": True,      # recomputed PASS
            "ac_proxy": True,
            "c2_pass": True,
            "mab_proxy": True,
            "acov_pass": True,
            "viol_types_full": [],
            "viol_types_high": [],
            "kept_violation_events": 0,
            "total_violation_events": 0,
        },
    ]
    metrics = e9_module.compute_aggregate_metrics(enriched)
    for key in (
        "n_episodes",
        "fa_strict",
        "tcc_fail_count",
        "replay_detection_loss",
        "ranking_reversal",
        "violation_type_breakdown",
        "violation_event_authority_split",
    ):
        assert key in metrics
    # First episode passes all proxies but TCC fails -> 1 strict false-accept,
    # both under full and high-authority because v4_hard_high is False too.
    assert metrics["fa_strict"]["full_catalogue"]["count"] == 1
    assert metrics["fa_strict"]["high_authority"]["count"] == 1


def test_full_audit_outputs_present_and_valid() -> None:
    """The full audit was already run; just verify outputs are well-formed."""
    repo_root = Path(__file__).resolve().parents[2]
    analysis_dir = repo_root / "evidence_pack" / "analysis"
    json_path = analysis_dir / "exp_e9_high_authority_core.json"
    md_path = analysis_dir / "exp_e9_high_authority_core.md"
    macros_path = analysis_dir / "exp_e9_macros.tex"
    cache_path = analysis_dir / "verdict_matrix_v6_high.json"
    if not json_path.exists():
        pytest.skip("E9 audit has not been run yet")

    with open(json_path) as f:
        m = json.load(f)
    assert m["fa_strict"]["high_authority"]["count"] >= 0
    assert "_meta" in m

    macros_text = macros_path.read_text()
    # Macros must be ASCII-safe for LaTeX compilation
    macros_text.encode("ascii")
    assert "\\Eninefastrict" in macros_text
    assert "\\Eninereplaylossmin" in macros_text
    assert "\\Eninerankreversal" in macros_text

    assert md_path.exists()
    md_text = md_path.read_text()
    assert "Pre-registered success criterion" in md_text

    with open(cache_path) as f:
        cache = json.load(f)
    assert "per_episode" in cache
    assert len(cache["per_episode"]) > 0
    first = cache["per_episode"][0]
    for key in ("episode_id", "scenario_id", "v4_hard_full", "v4_hard_high"):
        assert key in first
