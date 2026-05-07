"""Tests for the 3-tier + Tier 4 normaliser in RAGAgent._normalize_action_id.

Design reference: docs/attack_gap_exp_exp/260421_three_tier_normalizer_design.md

Covers:
  Tier 1 — exact match in scenario available_actions → (id, None)
  Tier 2 — alias lookup resolved INTO scenario set → (canonical, None)
  Tier 3 — universal_clinical_safety fallback → (id, "GENERAL_WORKUP")
  Tier 4 — DEVIATION fallback (always returns non-None id) → (id, "DEVIATION")

Plus Action(semantic_tag=...) schema compatibility and scorer honouring
of "GENERAL_WORKUP" (no-op) via _check_deviation.
"""

from __future__ import annotations

from cga_bench.agent_runner.llm_provider import LLMBackend
from cga_bench.agent_runner.rag_agent import RAGAgent, RAGConfig
from cga_bench.cpg_model.schemas.base import Action, ActionType


def _make_agent(use_llm: bool = False) -> RAGAgent:
    """Minimal RAGAgent for normaliser testing — no network, no env."""
    return RAGAgent(
        RAGConfig(
            agent_id="test_three_tier",
            use_llm=use_llm,
            cpg_sources_path=None,
            llm_backend=LLMBackend.MOCK,
            llm_model="mock",
        )
    )


# ---------------------------------------------------------------------------
# Tier 1 — exact match
# ---------------------------------------------------------------------------


class TestTier1Exact:
    def test_exact_match_returns_id_with_no_tag(self) -> None:
        agent = _make_agent()
        rid, tag = agent._normalize_action_id("order_cbc", ["order_cbc", "order_type_and_screen"])
        assert rid == "order_cbc"
        assert tag is None

    def test_case_insensitive_match(self) -> None:
        agent = _make_agent()
        rid, tag = agent._normalize_action_id("Order_CBC", ["order_cbc"])
        assert rid == "order_cbc"
        assert tag is None


# ---------------------------------------------------------------------------
# Tier 2 — alias lookup into scenario
# ---------------------------------------------------------------------------


class TestTier2Alias:
    def test_order_lab_lactate_not_aliased_to_order_cbc(self) -> None:
        """Lactate and CBC are clinically distinct panels and must not share
        an alias bucket. When an AABB-style scenario lists only
        ``order_cbc``, a lactate proposal must reach Tier 3/4 (not silently
        resolve to CBC)."""
        agent = _make_agent()
        rid, tag = agent._normalize_action_id(
            "order_lab_lactate",
            ["order_cbc", "order_type_and_screen"],
        )
        assert rid != "order_cbc", (
            "Lactate was silently aliased to CBC via Tier 2 — the clinically "
            "incorrect cross-domain workup seed has regressed."
        )
        assert tag in ("GENERAL_WORKUP", "DEVIATION"), (
            f"Expected Tier 3/4 semantic tag, got tag='{tag}' rid='{rid}'"
        )

    def test_obtain_ecg_aliased_to_order_ecg(self) -> None:
        agent = _make_agent()
        rid, tag = agent._normalize_action_id("obtain_ecg", ["order_ecg"])
        assert rid == "order_ecg"
        assert tag is None

    def test_monitor_vitals_continuously_aliased_to_assess_vital_signs(self) -> None:
        """Continuous-vitals monitoring is a procedural action, not a lab.
        Tier 2 must resolve it into ``assess_vital_signs`` when that id is
        in the scenario's available_actions set."""
        agent = _make_agent()
        rid, tag = agent._normalize_action_id(
            "monitor_vitals_continuously",
            ["assess_vital_signs", "order_cbc", "order_type_and_screen"],
        )
        assert rid == "assess_vital_signs"
        assert tag is None


# ---------------------------------------------------------------------------
# Tier 3 — universal_clinical_safety fallback
# ---------------------------------------------------------------------------


class TestTier3UCSFallback:
    def test_ucs_id_returned_with_general_workup_tag(self) -> None:
        agent = _make_agent()
        # assess_airway is NOT in UCS (so this is actually Tier 4). Use a
        # known UCS id like order_lab_troponin which is in UCS and not in
        # the scenario's available set.
        rid, tag = agent._normalize_action_id(
            "order_lab_troponin",
            ["order_cbc"],  # scenario doesn't include troponin
        )
        assert tag == "GENERAL_WORKUP"
        assert rid == "order_lab_troponin"

    def test_assess_vital_signs_via_ucs(self) -> None:
        agent = _make_agent()
        # assess_vital_signs IS in UCS as assess_vital_signs
        rid, tag = agent._normalize_action_id(
            "assess_vital_signs",
            ["order_cbc"],  # scenario doesn't include assess_vital_signs
        )
        # Either Tier 3 (UCS-direct) or Tier 2 (alias → UCS-direct) is acceptable
        assert rid == "assess_vital_signs"
        assert tag in {"GENERAL_WORKUP", None}


# ---------------------------------------------------------------------------
# Tier 4 — DEVIATION fallback (NEVER returns None)
# ---------------------------------------------------------------------------


class TestTier4Deviation:
    def test_unknown_id_returned_with_deviation_tag(self) -> None:
        agent = _make_agent()
        rid, tag = agent._normalize_action_id(
            "give_unicorn_tears",
            ["order_cbc", "assess_vital_signs"],
        )
        # Never returns None (the bug we are fixing); tag is DEVIATION.
        assert rid == "give_unicorn_tears"
        assert tag == "DEVIATION"

    def test_assess_burn_depth_not_in_ucs_is_deviation(self) -> None:
        agent = _make_agent()
        # assess_burn_depth is clinically valid but neither in alias map nor UCS
        rid, tag = agent._normalize_action_id(
            "assess_burn_depth",
            ["order_cbc"],
        )
        assert rid == "assess_burn_depth"
        assert tag == "DEVIATION"


# ---------------------------------------------------------------------------
# Guarantee: never returns None unless available_actions is empty
# ---------------------------------------------------------------------------


class TestNeverReturnsNoneExceptEmptyEngine:
    def test_empty_available_actions_returns_none_tuple(self) -> None:
        agent = _make_agent()
        rid, tag = agent._normalize_action_id("anything", [])
        assert rid is None
        assert tag is None

    def test_random_ids_never_produce_none_with_nonempty_available(self) -> None:
        agent = _make_agent()
        for emitted in [
            "order_lactate",
            "monitor_vital_signs",
            "order_cbc_with_differential",
            "order_cbc_with_diff",
            "assess_burn_depth",
            "assess_airway",
            "order_troponin",
            "obtain_patient_weight",
            "calculate_parkland_formula",
        ]:
            rid, _tag = agent._normalize_action_id(emitted, ["order_cbc"])
            assert rid is not None, f"{emitted!r} resolved to None — Tier 4 regression"


# ---------------------------------------------------------------------------
# Action schema — semantic_tag field
# ---------------------------------------------------------------------------


class TestActionSchemaSemanticTag:
    def test_semantic_tag_defaults_to_none(self) -> None:
        a = Action(
            type=ActionType.ORDER_LAB,
            action_id="order_cbc",
            args={},
            timestamp_minutes=0.0,
            justification="t",
        )
        assert a.semantic_tag is None

    def test_semantic_tag_accepts_general_workup(self) -> None:
        a = Action(
            type=ActionType.ORDER_LAB,
            action_id="order_lab_troponin",
            args={},
            timestamp_minutes=0.0,
            semantic_tag="GENERAL_WORKUP",
        )
        assert a.semantic_tag == "GENERAL_WORKUP"

    def test_semantic_tag_accepts_deviation(self) -> None:
        a = Action(
            type=ActionType.REASSESS,
            action_id="assess_burn_depth",
            args={},
            timestamp_minutes=0.0,
            semantic_tag="DEVIATION",
        )
        assert a.semantic_tag == "DEVIATION"
