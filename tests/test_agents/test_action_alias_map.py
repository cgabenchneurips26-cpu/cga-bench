"""Tests for canonical action-ID alias map and RAGAgent alias lookup.

Covers:
- build_canonical_action_map produces valid YAML with expected structure
- AABB transfusion scenario: model-emitted synonyms accepted via alias map
- Clinically distinct actions stay distinct (different canonicals)
- Exact match still takes priority over alias lookup
- RAGAgent.__init__ loads the alias map attributes
- Reverse map completeness: every canonical is in its own variant list
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CGA_BENCH_ROOT = Path(__file__).resolve().parents[2]
ALIAS_MAP_PATH = CGA_BENCH_ROOT / "cpg_model" / "action_alias_map.yaml"
GRAPHS_DIR = CGA_BENCH_ROOT / "cpg_model" / "graphs"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def alias_data() -> dict[str, Any]:
    """Load the generated action_alias_map.yaml once for the module."""
    assert ALIAS_MAP_PATH.is_file(), (
        f"alias map not found at {ALIAS_MAP_PATH} — "
        "run: PYTHONPATH=. python scripts/tools/build_canonical_action_map.py"
    )
    with open(ALIAS_MAP_PATH) as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def canonical_map(alias_data: dict[str, Any]) -> dict[str, list[str]]:
    """Return the canonical_map section."""
    return alias_data["canonical_map"]


@pytest.fixture(scope="module")
def reverse_map(alias_data: dict[str, Any]) -> dict[str, str]:
    """Return the reverse_map section."""
    return alias_data["reverse_map"]


# ---------------------------------------------------------------------------
# 1. Build-script output structure tests
# ---------------------------------------------------------------------------


def test_alias_map_file_exists() -> None:
    """action_alias_map.yaml must exist after running the build script."""
    assert ALIAS_MAP_PATH.is_file(), (
        f"Missing {ALIAS_MAP_PATH}. Run: PYTHONPATH=. python scripts/tools/build_canonical_action_map.py"
    )


def test_alias_map_has_required_keys(alias_data: dict[str, Any]) -> None:
    """YAML must contain canonical_map and reverse_map keys."""
    assert "canonical_map" in alias_data
    assert "reverse_map" in alias_data


def test_canonical_map_nonempty(canonical_map: dict[str, list[str]]) -> None:
    """canonical_map must have at least 20 groups (root-cause doc seeds alone = 25)."""
    assert len(canonical_map) >= 20, f"Expected >=20 groups, got {len(canonical_map)}"


def test_reverse_map_nonempty(reverse_map: dict[str, str]) -> None:
    """reverse_map must have at least as many entries as canonical groups."""
    assert len(reverse_map) >= len({v for v in reverse_map.values()}), "reverse_map should cover all canonical ids"


def test_canonical_map_values_are_lists(canonical_map: dict[str, list[str]]) -> None:
    """Every canonical_map value must be a non-empty list of strings."""
    for canonical, variants in canonical_map.items():
        assert isinstance(variants, list), f"Expected list for {canonical}, got {type(variants)}"
        assert len(variants) >= 1, f"Empty variant list for canonical '{canonical}'"
        for v in variants:
            assert isinstance(v, str), f"Non-string variant '{v}' in group '{canonical}'"


def test_reverse_map_values_are_strings(reverse_map: dict[str, str]) -> None:
    """Every reverse_map value must be a string canonical id."""
    for variant, canonical in reverse_map.items():
        assert isinstance(canonical, str), f"Expected str canonical for '{variant}', got {type(canonical)}"


# ---------------------------------------------------------------------------
# 2. Completeness: canonical in its own variant list
# ---------------------------------------------------------------------------


def test_reverse_map_completeness(
    canonical_map: dict[str, list[str]],
    reverse_map: dict[str, str],
) -> None:
    """Every variant in canonical_map must appear in reverse_map pointing back to a canonical."""
    for canonical, variants in canonical_map.items():
        for v in variants:
            assert v in reverse_map, f"Variant '{v}' of group '{canonical}' missing from reverse_map"
            # The canonical it points to must itself be a key in canonical_map
            c = reverse_map[v]
            assert c in canonical_map, f"Variant '{v}' -> canonical '{c}', but '{c}' is not a key in canonical_map"


# ---------------------------------------------------------------------------
# 3. AABB transfusion: cross-domain synonym acceptance
# ---------------------------------------------------------------------------


def test_aabb_order_lab_lactate_in_reverse_map(reverse_map: dict[str, str]) -> None:
    """order_lab_lactate must be in the reverse map (seed group: initial workup labs)."""
    assert "order_lab_lactate" in reverse_map, (
        "order_lab_lactate not found in reverse_map — check SEED_SYNONYM_GROUPS in build_canonical_action_map.py"
    )


def test_aabb_order_basic_metabolic_panel_in_reverse_map(reverse_map: dict[str, str]) -> None:
    """order_basic_metabolic_panel must be in the reverse map."""
    assert "order_basic_metabolic_panel" in reverse_map, "order_basic_metabolic_panel not found in reverse_map"


def test_cbc_bmp_lactate_do_not_share_canonical(reverse_map: dict[str, str]) -> None:
    """CBC, BMP, and lactate are three clinically distinct tests and MUST each
    own a distinct canonical.

    Regression against a prior seed that collapsed all three (plus CMP and
    continuous-vitals monitoring) into a single
    ``order_lab_basic_metabolic_panel`` canonical — a clinically incorrect
    merge that silently replaced LLM-emitted lactate / CBC orders with BMP
    in episode logs and broke mandatory-action scoring for every panel-
    specific benchmark.
    """
    c_cbc = reverse_map.get("order_cbc")
    c_bmp = reverse_map.get("order_basic_metabolic_panel")
    c_lactate = reverse_map.get("order_lab_lactate")

    assert c_cbc is not None, "order_cbc missing from reverse_map"
    assert c_bmp is not None, "order_basic_metabolic_panel missing from reverse_map"
    assert c_lactate is not None, "order_lab_lactate missing from reverse_map"

    assert c_cbc != c_bmp, f"CBC and BMP must have distinct canonicals (both are '{c_cbc}')"
    assert c_cbc != c_lactate, f"CBC and lactate must have distinct canonicals (both are '{c_cbc}')"
    assert c_bmp != c_lactate, f"BMP and lactate must have distinct canonicals (both are '{c_bmp}')"


def test_order_cbc_alias_resolves_to_order_lab_cbc(
    canonical_map: dict[str, list[str]],
    reverse_map: dict[str, str],
) -> None:
    """``order_cbc`` (short form) must resolve to ``order_lab_cbc`` (canonical),
    not to BMP. This is the true-synonym case."""
    assert reverse_map.get("order_cbc") == "order_lab_cbc"
    assert "order_cbc" in canonical_map["order_lab_cbc"]


def test_order_basic_metabolic_panel_alias_resolves_to_own_canonical(
    canonical_map: dict[str, list[str]],
    reverse_map: dict[str, str],
) -> None:
    """``order_basic_metabolic_panel`` must resolve to
    ``order_lab_basic_metabolic_panel`` (its own canonical), not to CBC."""
    assert reverse_map.get("order_basic_metabolic_panel") == "order_lab_basic_metabolic_panel"
    variants = canonical_map.get("order_lab_basic_metabolic_panel", [])
    assert "order_basic_metabolic_panel" in variants
    # Must not contain clinically distinct tests
    assert "order_cbc" not in variants
    assert "order_lab_cbc" not in variants
    assert "order_lab_lactate" not in variants


# ---------------------------------------------------------------------------
# 4. Clinically distinct actions remain distinct
# ---------------------------------------------------------------------------


def test_give_epinephrine_and_give_aspirin_different_canonicals(
    reverse_map: dict[str, str],
) -> None:
    """give_epinephrine and give_aspirin must NOT share a canonical."""
    # These IDs may or may not be in the reverse map; if not, they have no
    # canonical (which is also fine — distinct by default).
    c_epi = reverse_map.get("give_epinephrine")
    c_asp = reverse_map.get("give_aspirin")
    # If both have a canonical they must differ
    if c_epi is not None and c_asp is not None:
        assert c_epi != c_asp, f"give_epinephrine and give_aspirin incorrectly share canonical '{c_epi}'"


def test_order_cbc_and_order_type_and_screen_different_canonicals(
    reverse_map: dict[str, str],
) -> None:
    """order_cbc and order_type_and_screen must NOT share a canonical."""
    c_cbc = reverse_map.get("order_cbc")
    c_ts = reverse_map.get("order_type_and_screen")
    assert c_cbc is not None, "order_cbc missing from reverse_map"
    assert c_ts is not None, "order_type_and_screen missing from reverse_map"
    assert c_cbc != c_ts, f"order_cbc and order_type_and_screen incorrectly share canonical '{c_cbc}'"


# ---------------------------------------------------------------------------
# 5. RAGAgent loads alias map on __init__
# ---------------------------------------------------------------------------


def _make_minimal_rag_config() -> Any:
    """Return a minimal RAGConfig-like mock."""
    from cga_bench.agent_runner.rag_agent import RAGConfig

    return RAGConfig(
        agent_id="test_alias",
        use_llm=False,
        use_dense=False,
        use_hybrid=False,
    )


def test_rag_agent_has_alias_map_attributes() -> None:
    """RAGAgent.__init__ must populate _alias_reverse_map and _alias_canonical_map."""
    from cga_bench.agent_runner.rag_agent import RAGAgent

    config = _make_minimal_rag_config()
    agent = RAGAgent(config)
    assert hasattr(agent, "_alias_reverse_map"), "RAGAgent missing _alias_reverse_map"
    assert hasattr(agent, "_alias_canonical_map"), "RAGAgent missing _alias_canonical_map"
    assert isinstance(agent._alias_reverse_map, dict)
    assert isinstance(agent._alias_canonical_map, dict)


def test_rag_agent_alias_map_nonempty() -> None:
    """RAGAgent must load a non-empty alias map when the YAML exists."""
    from cga_bench.agent_runner.rag_agent import RAGAgent

    config = _make_minimal_rag_config()
    agent = RAGAgent(config)
    assert len(agent._alias_reverse_map) > 0, (
        "_alias_reverse_map is empty — alias map file may not exist or failed to load"
    )


def test_rag_agent_normalize_lactate_not_forced_into_cbc_scenario() -> None:
    """When an AABB scenario lists only ``order_cbc`` and the LLM emits
    ``order_lab_lactate``, the normalizer must NOT silently remap lactate to
    CBC (they are clinically distinct tests). Instead, Tier 3/4 should tag
    the proposal so the scorer can count it independently.

    Regression against the pre-fix seed where lactate, CBC, BMP, CMP and
    continuous-vitals monitoring all shared the same canonical and any of
    them would alias-resolve to whichever was in ``available_actions``.
    """
    from cga_bench.agent_runner.rag_agent import RAGAgent

    config = _make_minimal_rag_config()
    agent = RAGAgent(config)

    available = [
        "order_cbc",
        "order_type_and_screen",
        "assess_hemodynamic_status",
        "assess_active_bleeding",
        "review_transfusion_history",
    ]
    rid, tag = agent._normalize_action_id("order_lab_lactate", available)
    # Lactate is not a CBC/type-and-screen/etc synonym. It should either
    # reach Tier 3 (universal_clinical_safety → GENERAL_WORKUP) or Tier 4
    # (DEVIATION) — never silently rewrite to order_cbc.
    assert rid != "order_cbc", (
        "order_lab_lactate was silently aliased to order_cbc — the pre-fix "
        "cross-domain workup seed has regressed."
    )
    assert tag in ("GENERAL_WORKUP", "DEVIATION"), (
        f"Expected Tier 3/4 tag for an off-graph clinically-distinct order, got tag='{tag}' rid='{rid}'"
    )


def test_rag_agent_normalize_monitor_vitals_resolves_to_assess_vital_signs() -> None:
    """``monitor_vitals_continuously`` / ``monitor_vitals_q15min`` / similar
    monitoring verbs must resolve into the ``assess_vital_signs`` canonical
    group, NOT into any lab-order canonical. When the scenario's
    available_actions includes ``assess_vital_signs`` (standard across most
    CPG graphs), the Tier 2 alias lookup returns that id with tag=None.
    """
    from cga_bench.agent_runner.rag_agent import RAGAgent

    config = _make_minimal_rag_config()
    agent = RAGAgent(config)

    available = [
        "assess_vital_signs",
        "order_cbc",
        "order_type_and_screen",
        "assess_hemodynamic_status",
    ]
    rid, tag = agent._normalize_action_id("monitor_vitals_continuously", available)
    assert rid == "assess_vital_signs", (
        f"Expected monitor_vitals_continuously → assess_vital_signs via Tier 2 alias, got '{rid}'"
    )
    assert tag is None


def test_rag_agent_normalize_exact_match_takes_priority() -> None:
    """Exact match must be returned immediately, before alias lookup fires."""
    from cga_bench.agent_runner.rag_agent import RAGAgent

    config = _make_minimal_rag_config()
    agent = RAGAgent(config)

    available = ["order_cbc", "order_type_and_screen"]
    # order_cbc IS in available — Tier 1 match
    rid, tag = agent._normalize_action_id("order_cbc", available)
    assert rid == "order_cbc"
    assert tag is None


def test_rag_agent_normalize_distinct_action_not_aliased() -> None:
    """An action with no synonym in the available list must NOT be silently aliased.

    Under the 3-tier design (260421_three_tier_normalizer_design.md), an
    unresolved id is returned with ``tag='DEVIATION'`` instead of being silently
    dropped. The scorer (not the normaliser) is responsible for penalising
    DEVIATIONs. The critical guarantee this test enforces: the id is NOT
    merged into one of the scenario's available ids via an unsafe alias.
    """
    from cga_bench.agent_runner.rag_agent import RAGAgent

    config = _make_minimal_rag_config()
    agent = RAGAgent(config)

    # give_epinephrine_intramuscular has no alias in available set
    available = ["order_cbc", "order_type_and_screen"]
    rid, tag = agent._normalize_action_id("give_epinephrine_intramuscular", available)
    # Safety: must NOT be coerced to order_cbc or order_type_and_screen
    assert rid not in available, (
        f"Unsafe alias: resolved to '{rid}' in available set. Distinct clinical actions must not be merged."
    )
    # New contract: Tier 4 returns DEVIATION tag instead of None.
    assert tag == "DEVIATION", f"Expected Tier 4 DEVIATION tag, got tag={tag!r} with rid={rid!r}"
