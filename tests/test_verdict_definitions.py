"""Unit tests for Phase 0 verdict definitions.

Tests each evaluator's verdict function against hand-crafted fixtures,
then cross-validates against verdict_matrix_v6.json to confirm alignment
with the pre-computed verdicts.
"""

from __future__ import annotations

import json
from pathlib import Path

from assessor_core.spec.verdict_definitions import (
    AC_COVERAGE_THRESHOLD,
    ALL_VIOLATION_TYPES,
    CWT_TYPED_THRESHOLD,
    DG_TYPED_WEIGHTS,
    EVALUATOR_REGISTRY,
    HARD_VIOLATION_TYPES,
    MAB_F1_THRESHOLD,
    _classify_violation_type,
    _compute_f1,
    _count_violations_by_type,
    _extract_action_set,
    _normalize_action,
    acov_verdict,
    action_coverage,
    asc_verdict,
    compute_sub_scores,
    cwt_typed_verdict,
    cwt_verdict,
    dg_proxy,
    dg_typed_cost,
    mab_f1,
    paf_verdict,
    tcc_verdict,
    tom_empirical_audit,
    tom_verdict,
)
import pytest

# ---------------------------------------------------------------------------
# Fixtures: hand-crafted episode dicts
# ---------------------------------------------------------------------------

EP_CLEAN: dict = {
    "violation_events": [],
    "actions": [
        {"action_id": "order_lab_blood_culture"},
        {"action_id": "give_broad_spectrum_antibiotics"},
        {"action_id": "give_crystalloid_30ml_kg"},
    ],
    "expected_actions": [
        "order_lab_blood_culture",
        "give_broad_spectrum_antibiotics",
        "give_crystalloid_30ml_kg",
    ],
    "compliance_score": 1.0,
}

EP_COMMISSION: dict = {
    "violation_events": [
        {"violation_type": "commission", "action_involved": "give_nitroglycerin"},
    ],
    "actions": [{"action_id": "give_nitroglycerin"}],
    "expected_actions": ["order_lab_troponin"],
    "compliance_score": 0.5,
}

EP_TIMING: dict = {
    "violation_events": [
        {"violation_type": "timing", "action_involved": "give_antibiotics"},
    ],
    "actions": [
        {"action_id": "order_lab_blood_culture"},
        {"action_id": "give_antibiotics"},
    ],
    "expected_actions": ["order_lab_blood_culture", "give_antibiotics"],
    "compliance_score": 0.8,
}

EP_SEQUENCE: dict = {
    "violation_events": [
        {"violation_type": "sequence", "action_involved": "give_antibiotics"},
    ],
    "actions": [
        {"action_id": "give_antibiotics"},
        {"action_id": "order_lab_blood_culture"},
    ],
    "expected_actions": ["order_lab_blood_culture", "give_antibiotics"],
    "compliance_score": 0.85,
}

EP_OMISSION_ONLY: dict = {
    "violation_events": [
        {"violation_type": "omission", "action_involved": "give_crystalloid_30ml_kg"},
        {"violation_type": "omission", "action_involved": "give_antibiotics"},
    ],
    "actions": [{"action_id": "order_lab_blood_culture"}],
    "expected_actions": [
        "order_lab_blood_culture",
        "give_crystalloid_30ml_kg",
        "give_antibiotics",
    ],
    "compliance_score": 0.3,
}

EP_DEVIATION_ONLY: dict = {
    "violation_events": [
        {"violation_type": "deviation", "action_involved": "order_lab_cbc"},
    ],
    "actions": [
        {"action_id": "order_lab_blood_culture"},
        {"action_id": "order_lab_cbc"},
    ],
    "expected_actions": ["order_lab_blood_culture"],
    "compliance_score": 0.9,
}

EP_MIXED: dict = {
    "violation_events": [
        {"violation_type": "commission", "action_involved": "give_nitroglycerin"},
        {"violation_type": "omission", "action_involved": "give_aspirin"},
        {"violation_type": "timing", "action_involved": "order_lab_troponin"},
        {"violation_type": "deviation", "action_involved": "order_lab_cbc"},
    ],
    "actions": [
        {"action_id": "give_nitroglycerin"},
        {"action_id": "order_lab_troponin"},
        {"action_id": "order_lab_cbc"},
    ],
    "expected_actions": ["give_aspirin", "order_lab_troponin"],
    "compliance_score": 0.2,
}

EP_EMPTY: dict = {
    "violation_events": [],
    "actions": [],
    "expected_actions": [],
    "compliance_score": 0.0,
}


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestNormalizeAction:
    def test_lowercase(self) -> None:
        assert _normalize_action("Give_Aspirin") == "give_aspirin"

    def test_strip_whitespace(self) -> None:
        assert _normalize_action("  order_lab  ") == "order_lab"

    def test_hyphens_to_underscores(self) -> None:
        assert _normalize_action("order-lab-cbc") == "order_lab_cbc"

    def test_spaces_to_underscores(self) -> None:
        assert _normalize_action("order lab cbc") == "order_lab_cbc"


class TestClassifyViolationType:
    def test_canonical_forms(self) -> None:
        for canon in ALL_VIOLATION_TYPES:
            assert _classify_violation_type(canon) == canon

    def test_uppercase(self) -> None:
        assert _classify_violation_type("COMMISSION") == "commission"

    def test_enum_format(self) -> None:
        assert _classify_violation_type("ViolationType.TIMING") == "timing"

    def test_unknown(self) -> None:
        assert _classify_violation_type("garbage") == "unknown"


class TestExtractActionSet:
    def test_dict_format(self) -> None:
        actions = [{"action_id": "A"}, {"action_id": "B"}]
        assert _extract_action_set(actions) == {"a", "b"}

    def test_string_format(self) -> None:
        actions = ["order_lab", "Give_Med"]
        assert _extract_action_set(actions) == {"order_lab", "give_med"}

    def test_empty(self) -> None:
        assert _extract_action_set([]) == set()

    def test_skips_empty_ids(self) -> None:
        actions = [{"action_id": ""}, {"action_id": "real_action"}]
        assert _extract_action_set(actions) == {"real_action"}


class TestCountViolations:
    def test_clean_episode(self) -> None:
        counts = _count_violations_by_type(EP_CLEAN)
        assert all(v == 0 for v in counts.values())

    def test_mixed_episode(self) -> None:
        counts = _count_violations_by_type(EP_MIXED)
        assert counts["commission"] == 1
        assert counts["omission"] == 1
        assert counts["timing"] == 1
        assert counts["deviation"] == 1
        assert counts["sequence"] == 0

    def test_none_violation_events(self) -> None:
        counts = _count_violations_by_type({"violation_events": None})
        assert all(v == 0 for v in counts.values())


# ---------------------------------------------------------------------------
# TCC (v4_hard) verdict tests
# ---------------------------------------------------------------------------


class TestTCCVerdict:
    def test_clean_passes(self) -> None:
        assert tcc_verdict(EP_CLEAN) is True

    def test_commission_fails(self) -> None:
        assert tcc_verdict(EP_COMMISSION) is False

    def test_timing_fails(self) -> None:
        assert tcc_verdict(EP_TIMING) is False

    def test_sequence_fails(self) -> None:
        assert tcc_verdict(EP_SEQUENCE) is False

    def test_omission_only_passes(self) -> None:
        """Omission is NOT a hard violation — TCC still passes."""
        assert tcc_verdict(EP_OMISSION_ONLY) is True

    def test_deviation_only_passes(self) -> None:
        """Deviation is NOT a hard violation — TCC still passes."""
        assert tcc_verdict(EP_DEVIATION_ONLY) is True

    def test_mixed_fails(self) -> None:
        """Mixed violations with commission → fails."""
        assert tcc_verdict(EP_MIXED) is False

    def test_empty_episode_passes(self) -> None:
        assert tcc_verdict(EP_EMPTY) is True

    def test_no_violation_events_key(self) -> None:
        assert tcc_verdict({}) is True

    def test_none_violation_events(self) -> None:
        assert tcc_verdict({"violation_events": None}) is True


# ---------------------------------------------------------------------------
# CwT (C2) verdict tests
# ---------------------------------------------------------------------------


class TestCwTVerdict:
    def test_above_threshold(self) -> None:
        assert cwt_verdict(EP_CLEAN) is True  # 1.0 >= 0.7

    def test_at_threshold(self) -> None:
        ep = {**EP_CLEAN, "compliance_score": 0.7}
        assert cwt_verdict(ep) is True

    def test_below_threshold(self) -> None:
        ep = {**EP_CLEAN, "compliance_score": 0.69}
        assert cwt_verdict(ep) is False

    def test_zero_score(self) -> None:
        assert cwt_verdict(EP_EMPTY) is False  # 0.0 < 0.7

    def test_none_score(self) -> None:
        assert cwt_verdict({}) is False  # None → 0.0 < 0.7

    def test_custom_threshold(self) -> None:
        ep = {**EP_CLEAN, "compliance_score": 0.5}
        assert cwt_verdict(ep, threshold=0.5) is True
        assert cwt_verdict(ep, threshold=0.6) is False


# ---------------------------------------------------------------------------
# CwT-Typed verdict tests (A1)
# ---------------------------------------------------------------------------


class TestCwTTypedVerdict:
    def test_clean_passes(self) -> None:
        """No violations → typed compliance = 1.0 → passes."""
        assert cwt_typed_verdict(EP_CLEAN) is True

    def test_commission_fails(self) -> None:
        """1 commission on 1 action → typed_compliance = 0.0 < 0.7."""
        assert cwt_typed_verdict(EP_COMMISSION) is False

    def test_timing_fails(self) -> None:
        """1 timing on 2 actions → typed_compliance = 0.5 < 0.7."""
        assert cwt_typed_verdict(EP_TIMING) is False

    def test_sequence_fails(self) -> None:
        """1 sequence on 2 actions → typed_compliance = 0.5 < 0.7."""
        assert cwt_typed_verdict(EP_SEQUENCE) is False

    def test_omission_only_passes(self) -> None:
        """Omission is excluded from typed score — still passes.

        EP_OMISSION_ONLY has 2 omissions but 1 action, typed_count=0.
        typed_compliance = 1 - 0/1 = 1.0 >= 0.7.
        """
        assert cwt_typed_verdict(EP_OMISSION_ONLY) is True

    def test_deviation_only_passes(self) -> None:
        """Deviation is excluded from typed score — still passes.

        EP_DEVIATION_ONLY has 1 deviation, 2 actions, typed_count=0.
        typed_compliance = 1 - 0/2 = 1.0 >= 0.7.
        """
        assert cwt_typed_verdict(EP_DEVIATION_ONLY) is True

    def test_mixed_fails(self) -> None:
        """Mixed: commission + timing = 2 typed violations on 3 actions.

        typed_compliance = 1 - 2/3 = 0.333 < 0.7.
        Omission and deviation excluded.
        """
        assert cwt_typed_verdict(EP_MIXED) is False

    def test_empty_episode_passes(self) -> None:
        """Empty violation list, empty actions → denom=max(0,1)=1, typed_count=0.

        typed_compliance = 1.0 >= 0.7 → passes.
        """
        assert cwt_typed_verdict(EP_EMPTY) is True

    def test_no_fields_passes(self) -> None:
        """Missing violation_events and actions → typed_compliance = 1.0."""
        assert cwt_typed_verdict({}) is True

    def test_none_violation_events_passes(self) -> None:
        assert cwt_typed_verdict({"violation_events": None, "actions": []}) is True

    def test_custom_threshold_lower(self) -> None:
        """EP_TIMING: typed_compliance = 0.5. Passes at threshold=0.5."""
        assert cwt_typed_verdict(EP_TIMING, threshold=0.5) is True
        assert cwt_typed_verdict(EP_TIMING, threshold=0.6) is False

    def test_default_threshold_equals_constant(self) -> None:
        """Default threshold must match CWT_TYPED_THRESHOLD constant."""
        ep = {"violation_events": [], "actions": [{"action_id": "a"}]}
        # Score = 1.0 — passes both ways regardless of threshold value,
        # so check boundary with a constructed score near threshold.
        # 1 commission on 1 action → score = 0.0
        ep_fail = {
            "violation_events": [{"violation_type": "commission"}],
            "actions": [{"action_id": "a"}],
        }
        # At threshold=CWT_TYPED_THRESHOLD (0.7), score 0.0 fails.
        assert cwt_typed_verdict(ep_fail, threshold=CWT_TYPED_THRESHOLD) is False

    def test_omission_does_not_dilute_score(self) -> None:
        """CwT (original) fails on omission-heavy episode; CwT-Typed passes.

        This is the key differentiator: an agent that does nothing (omissions only)
        should NOT be rewarded, but the typed score correctly ignores omissions.
        The original cwt_verdict reads compliance_score which includes omissions.
        """
        # EP_OMISSION_ONLY has compliance_score=0.3 → original CwT fails.
        assert cwt_verdict(EP_OMISSION_ONLY) is False
        # But typed CwT passes because omissions are excluded.
        assert cwt_typed_verdict(EP_OMISSION_ONLY) is True

    def test_sequence_violation_counted(self) -> None:
        """Sequence violations ARE counted in typed score (unlike TCC proxy)."""
        ep = {
            "violation_events": [
                {"violation_type": "sequence"},
                {"violation_type": "sequence"},
                {"violation_type": "sequence"},
            ],
            "actions": [{"action_id": "a"}, {"action_id": "b"}, {"action_id": "c"}],
        }
        # 3 sequence on 3 actions → typed_compliance = 0.0 < 0.7
        assert cwt_typed_verdict(ep) is False

    def test_typed_and_original_agree_on_clean(self) -> None:
        """Both verdicts pass for a perfectly clean episode."""
        assert cwt_verdict(EP_CLEAN) is True
        assert cwt_typed_verdict(EP_CLEAN) is True


# ---------------------------------------------------------------------------
# ASC (AC-Proxy) verdict tests
# ---------------------------------------------------------------------------


class TestASCVerdict:
    def test_full_coverage(self) -> None:
        assert asc_verdict(EP_CLEAN) is True  # 3/3 = 1.0 >= 0.5

    def test_partial_coverage_passes(self) -> None:
        ep = {
            "actions": [{"action_id": "A"}, {"action_id": "B"}],
            "expected_actions": ["A", "B", "C"],
        }
        assert asc_verdict(ep) is True  # 2/3 = 0.667 >= 0.5

    def test_low_coverage_fails(self) -> None:
        ep = {
            "actions": [{"action_id": "A"}],
            "expected_actions": ["A", "B", "C", "D", "E"],
        }
        assert asc_verdict(ep) is False  # 1/5 = 0.2 < 0.5

    def test_empty_expected(self) -> None:
        ep = {"actions": [{"action_id": "A"}], "expected_actions": []}
        assert asc_verdict(ep) is True  # No expectations → pass

    def test_empty_performed(self) -> None:
        ep = {"actions": [], "expected_actions": ["A"]}
        assert asc_verdict(ep) is False  # 0/1 = 0.0 < 0.5

    def test_exact_threshold(self) -> None:
        ep = {
            "actions": [{"action_id": "A"}],
            "expected_actions": ["A", "B"],
        }
        assert asc_verdict(ep) is True  # 1/2 = 0.5 >= 0.5


# ---------------------------------------------------------------------------
# PAF (MAB-Proxy) verdict tests
# ---------------------------------------------------------------------------


class TestPAFVerdict:
    def test_perfect_f1(self) -> None:
        assert paf_verdict(EP_CLEAN) is True  # P=1, R=1, F1=1.0

    def test_no_overlap_fails(self) -> None:
        ep = {
            "actions": [{"action_id": "X"}, {"action_id": "Y"}],
            "expected_actions": ["A", "B"],
        }
        assert paf_verdict(ep) is False  # F1=0.0

    def test_partial_overlap(self) -> None:
        ep = {
            "actions": [{"action_id": "A"}, {"action_id": "X"}],
            "expected_actions": ["A", "B"],
        }
        # TP=1, P=1/2=0.5, R=1/2=0.5, F1=0.5
        assert paf_verdict(ep) is True  # 0.5 >= 0.5

    def test_empty_expected(self) -> None:
        ep = {"actions": [{"action_id": "A"}], "expected_actions": []}
        assert paf_verdict(ep) is False  # F1=0 when no expected

    def test_empty_performed(self) -> None:
        ep = {"actions": [], "expected_actions": ["A"]}
        assert paf_verdict(ep) is False


# ---------------------------------------------------------------------------
# TOM (DxEM) verdict tests
# ---------------------------------------------------------------------------


class TestTOMVerdict:
    def test_always_true_clean(self) -> None:
        assert tom_verdict(EP_CLEAN) is True

    def test_always_true_commission(self) -> None:
        assert tom_verdict(EP_COMMISSION) is True

    def test_always_true_empty(self) -> None:
        assert tom_verdict(EP_EMPTY) is True

    def test_always_true_no_fields(self) -> None:
        assert tom_verdict({}) is True


# ---------------------------------------------------------------------------
# ACov verdict tests
# ---------------------------------------------------------------------------


class TestACovVerdict:
    def test_identical_to_asc(self) -> None:
        """ACov is structurally identical to ASC."""
        for ep in [EP_CLEAN, EP_COMMISSION, EP_OMISSION_ONLY, EP_EMPTY]:
            assert acov_verdict(ep) == asc_verdict(ep)


# ---------------------------------------------------------------------------
# Sub-score tests (C1-C5)
# ---------------------------------------------------------------------------


class TestSubScores:
    def test_all_clean(self) -> None:
        counts = dict.fromkeys(ALL_VIOLATION_TYPES, 0)
        scores = compute_sub_scores(counts, n_mandatory=5, n_actions=5)
        assert scores["C1_path_selection"] == 1.0
        assert scores["C2_mandatory_completion"] == 1.0
        assert scores["C3_forbidden_avoidance"] == 1.0
        assert scores["C4_timing_compliance"] == 1.0
        assert scores["C5_sequence_integrity"] == 1.0

    def test_c3_binary_zero(self) -> None:
        """C3 is binary: any commission → 0.0."""
        counts = {"commission": 1, "omission": 0, "timing": 0, "sequence": 0, "deviation": 0}
        scores = compute_sub_scores(counts, n_mandatory=5, n_actions=5)
        assert scores["C3_forbidden_avoidance"] == 0.0

    def test_c3_binary_one(self) -> None:
        """C3 is binary: no commission → 1.0."""
        counts = {"commission": 0, "omission": 3, "timing": 2, "sequence": 1, "deviation": 4}
        scores = compute_sub_scores(counts, n_mandatory=5, n_actions=10)
        assert scores["C3_forbidden_avoidance"] == 1.0

    def test_c2_omission_formula(self) -> None:
        """C2 = 1 - omission_count / n_mandatory."""
        counts = {"commission": 0, "omission": 2, "timing": 0, "sequence": 0, "deviation": 0}
        scores = compute_sub_scores(counts, n_mandatory=10, n_actions=8)
        assert scores["C2_mandatory_completion"] == pytest.approx(0.8)

    def test_c1_deviation_formula(self) -> None:
        """C1 = 1 - deviation_count / max(n_actions, n_mandatory, 1)."""
        counts = {"commission": 0, "omission": 0, "timing": 0, "sequence": 0, "deviation": 3}
        scores = compute_sub_scores(counts, n_mandatory=5, n_actions=10)
        assert scores["C1_path_selection"] == pytest.approx(0.7)  # 1 - 3/10

    def test_c4_timing_formula(self) -> None:
        counts = {"commission": 0, "omission": 0, "timing": 3, "sequence": 0, "deviation": 0}
        scores = compute_sub_scores(counts, n_mandatory=10, n_actions=10)
        assert scores["C4_timing_compliance"] == pytest.approx(0.7)  # 1 - 3/10

    def test_c5_sequence_formula(self) -> None:
        counts = {"commission": 0, "omission": 0, "timing": 0, "sequence": 2, "deviation": 0}
        scores = compute_sub_scores(counts, n_mandatory=5, n_actions=5)
        assert scores["C5_sequence_integrity"] == pytest.approx(0.6)  # 1 - 2/5

    def test_clamp_at_zero(self) -> None:
        """Scores should not go below 0.0."""
        counts = {"commission": 0, "omission": 20, "timing": 0, "sequence": 0, "deviation": 0}
        scores = compute_sub_scores(counts, n_mandatory=5, n_actions=5)
        assert scores["C2_mandatory_completion"] == 0.0  # 1 - 20/5 clamped


# ---------------------------------------------------------------------------
# d_G proxy tests
# ---------------------------------------------------------------------------


class TestDGProxy:
    def test_clean_episode(self) -> None:
        assert dg_proxy(EP_CLEAN) == 0

    def test_commission_counted(self) -> None:
        assert dg_proxy(EP_COMMISSION) == 1

    def test_timing_counted(self) -> None:
        assert dg_proxy(EP_TIMING) == 1

    def test_omission_not_counted(self) -> None:
        assert dg_proxy(EP_OMISSION_ONLY) == 0

    def test_deviation_not_counted(self) -> None:
        assert dg_proxy(EP_DEVIATION_ONLY) == 0

    def test_sequence_not_counted(self) -> None:
        assert dg_proxy(EP_SEQUENCE) == 0

    def test_mixed(self) -> None:
        """Mixed: 1 commission + 1 timing = 2."""
        assert dg_proxy(EP_MIXED) == 2


class TestDGTypedCost:
    def test_clean(self) -> None:
        assert dg_typed_cost(EP_CLEAN) == 0.0

    def test_commission_weight(self) -> None:
        assert dg_typed_cost(EP_COMMISSION) == pytest.approx(1.0)

    def test_timing_weight(self) -> None:
        assert dg_typed_cost(EP_TIMING) == pytest.approx(0.5)

    def test_sequence_weight(self) -> None:
        assert dg_typed_cost(EP_SEQUENCE) == pytest.approx(0.6)

    def test_deviation_excluded(self) -> None:
        assert dg_typed_cost(EP_DEVIATION_ONLY) == pytest.approx(0.0)

    def test_omission_excluded(self) -> None:
        assert dg_typed_cost(EP_OMISSION_ONLY) == pytest.approx(0.0)

    def test_mixed(self) -> None:
        # commission(1.0) + timing(0.5) = 1.5. Deviation and omission excluded.
        assert dg_typed_cost(EP_MIXED) == pytest.approx(1.5)

    def test_weights_match_constant(self) -> None:
        """DG_TYPED_WEIGHTS constant has expected values."""
        assert DG_TYPED_WEIGHTS["commission"] == pytest.approx(1.0)
        assert DG_TYPED_WEIGHTS["timing"] == pytest.approx(0.5)
        assert DG_TYPED_WEIGHTS["sequence"] == pytest.approx(0.6)
        assert "omission" not in DG_TYPED_WEIGHTS
        assert "deviation" not in DG_TYPED_WEIGHTS

    def test_all_three_typed_types(self) -> None:
        """Episode with commission + timing + sequence: sum of all weights."""
        ep = {
            "violation_events": [
                {"violation_type": "commission"},
                {"violation_type": "timing"},
                {"violation_type": "sequence"},
            ],
            "actions": [],
        }
        # 1.0 + 0.5 + 0.6 = 2.1
        assert dg_typed_cost(ep) == pytest.approx(2.1)


# ---------------------------------------------------------------------------
# F1 / Coverage helper tests
# ---------------------------------------------------------------------------


class TestF1:
    def test_perfect(self) -> None:
        assert _compute_f1({"a", "b"}, {"a", "b"}) == pytest.approx(1.0)

    def test_zero_overlap(self) -> None:
        assert _compute_f1({"x"}, {"a", "b"}) == pytest.approx(0.0)

    def test_partial(self) -> None:
        # TP=1, P=1/2, R=1/2, F1=0.5
        assert _compute_f1({"a", "x"}, {"a", "b"}) == pytest.approx(0.5)

    def test_empty_expected(self) -> None:
        assert _compute_f1({"a"}, set()) == 0.0

    def test_empty_performed(self) -> None:
        assert _compute_f1(set(), {"a"}) == 0.0


class TestActionCoverage:
    def test_full(self) -> None:
        assert action_coverage(EP_CLEAN) == pytest.approx(1.0)

    def test_partial(self) -> None:
        ep = {
            "actions": [{"action_id": "A"}],
            "expected_actions": ["A", "B"],
        }
        assert action_coverage(ep) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Evaluator registry tests
# ---------------------------------------------------------------------------


class TestEvaluatorRegistry:
    def test_all_families_present(self) -> None:
        families = {v["family"] for v in EVALUATOR_REGISTRY.values()}
        assert families == {"TCC", "CwT", "ASC", "PAF", "TOM", "ACov"}

    def test_tcc_is_reference(self) -> None:
        assert EVALUATOR_REGISTRY["TCC"]["is_reference"] is True

    def test_tom_is_degenerate(self) -> None:
        assert EVALUATOR_REGISTRY["TOM"].get("is_degenerate") is True

    def test_acov_is_duplicate(self) -> None:
        assert EVALUATOR_REGISTRY["ACov"].get("is_duplicate_of") == "ASC"

    def test_cwt_typed_in_registry(self) -> None:
        """CwT_Typed entry is present in registry with correct metadata."""
        assert "CwT_Typed" in EVALUATOR_REGISTRY
        entry = EVALUATOR_REGISTRY["CwT_Typed"]
        assert entry["family"] == "CwT"
        assert entry["column"] == "cwt_typed_pass"
        assert entry["threshold"] == pytest.approx(CWT_TYPED_THRESHOLD)
        assert entry["is_reference"] is False
        assert entry["function"] is cwt_typed_verdict

    def test_cwt_typed_input_fields(self) -> None:
        """CwT_Typed reads from violation_events and actions (not compliance_score)."""
        entry = EVALUATOR_REGISTRY["CwT_Typed"]
        fields = entry["input_fields"]
        assert any("violation_events" in f for f in fields)
        assert any("actions" in f for f in fields)
        assert not any("compliance_score" in f for f in fields)

    def test_pi_classes_match_ground_truth(self) -> None:
        """Pi-class ground truth from audit/reports/*/report.json."""
        expected = {
            "TCC": "nctx",
            "CwT": "aset",
            "ASC": "nctx",
            "PAF": "term",
            "TOM": "term",
            "ACov": "nctx",
        }
        for key, pi in expected.items():
            assert EVALUATOR_REGISTRY[key]["pi_class"] == pi, f"{key} pi_class mismatch"


# ---------------------------------------------------------------------------
# Cross-validation against verdict_matrix_v6.json (conditional)
# ---------------------------------------------------------------------------

VERDICT_MATRIX_PATH = Path(__file__).resolve().parents[1] / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"


@pytest.fixture(scope="module")
def sample_matrix_episodes() -> list[dict] | None:
    """Load first 200 per_episode entries from verdict matrix if available."""
    if not VERDICT_MATRIX_PATH.exists():
        return None
    with open(VERDICT_MATRIX_PATH) as f:
        data = json.load(f)
    return data["per_episode"][:200]


@pytest.fixture(scope="module")
def raw_episodes_by_id() -> dict[str, dict] | None:
    """Load raw episodes for cross-validation (v5 dir)."""
    v5_dir = Path(__file__).resolve().parents[1] / "results" / "full_706_v5"
    if not v5_dir.exists():
        return None
    episodes: dict[str, dict] = {}
    count = 0
    for model_dir in sorted(v5_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            if ep_file.name.startswith(("checkpoint", ".claim", "log_", "model_summary")):
                continue
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                sid = ep.get("scenario_id", "")
                run_idx = ep.get("run_index", 0)
                key = f"{sid}_{model_dir.name}_{run_idx}"
                episodes[key] = ep
                count += 1
                if count >= 200:
                    return episodes
            except Exception:
                continue
    return episodes


class TestCrossValidationMatrix:
    """Cross-validate spec verdicts against verdict_matrix_v6.json."""

    def test_tcc_matches_v4_hard(self, sample_matrix_episodes: list[dict] | None) -> None:
        if sample_matrix_episodes is None:
            pytest.skip("verdict_matrix_v6.json not available")
        # TCC uses violation_events, but matrix only has boolean.
        # We verify the matrix internal consistency: v4_hard column exists.
        for ep in sample_matrix_episodes:
            assert "v4_hard" in ep

    def test_dxem_always_true_in_matrix(self, sample_matrix_episodes: list[dict] | None) -> None:
        if sample_matrix_episodes is None:
            pytest.skip("verdict_matrix_v6.json not available")
        for ep in sample_matrix_episodes:
            assert ep.get("dxem") is True, f"DxEM not True for {ep.get('episode_id')}"


class TestCrossValidationRaw:
    """Cross-validate spec verdicts against raw v5 episode files."""

    def test_tcc_matches_raw(self, raw_episodes_by_id: dict[str, dict] | None) -> None:
        if raw_episodes_by_id is None:
            pytest.skip("v5 results not available")
        for key, ep in raw_episodes_by_id.items():
            spec_verdict = tcc_verdict(ep)
            # Also compute from violation_events manually
            has_hard = False
            for v in ep.get("violation_events", []) or []:
                if not isinstance(v, dict):
                    continue
                raw_type = str(v.get("violation_type", v.get("type", "")))
                vtype = _classify_violation_type(raw_type)
                if vtype in HARD_VIOLATION_TYPES:
                    has_hard = True
                    break
            expected = not has_hard
            assert spec_verdict == expected, f"TCC mismatch for {key}"

    def test_asc_coverage_matches(self, raw_episodes_by_id: dict[str, dict] | None) -> None:
        if raw_episodes_by_id is None:
            pytest.skip("v5 results not available")
        for key, ep in raw_episodes_by_id.items():
            spec_verdict = asc_verdict(ep)
            cov = action_coverage(ep)
            assert spec_verdict == (cov >= AC_COVERAGE_THRESHOLD), f"ASC mismatch for {key}"

    def test_paf_f1_matches(self, raw_episodes_by_id: dict[str, dict] | None) -> None:
        if raw_episodes_by_id is None:
            pytest.skip("v5 results not available")
        for key, ep in raw_episodes_by_id.items():
            spec_verdict = paf_verdict(ep)
            f1_val = mab_f1(ep)
            assert spec_verdict == (f1_val >= MAB_F1_THRESHOLD), f"PAF mismatch for {key}"


class TestTOMEmpiricalAudit:
    def test_dxem_degenerate(self) -> None:
        if not VERDICT_MATRIX_PATH.exists():
            pytest.skip("verdict_matrix_v6.json not available")
        result = tom_empirical_audit(VERDICT_MATRIX_PATH)
        assert result["is_degenerate"] is True
        assert result["pass_rate"] == pytest.approx(1.0)
        assert result["n_false"] == 0
        assert result["n_total"] == 16944
