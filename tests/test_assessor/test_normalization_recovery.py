"""Normalization recovery rate test.

Spec requirement: normalization recovery >= 99.5%
Tests that the ActionNormalizer can map known action IDs to canonical forms.
"""

import pytest

from cga_bench.assessor_core.action_normalizer import ActionNormalizer


KNOWN_ACTIONS = [
    ("blood_culture_before_antibiotics", "order_lab_blood_culture"),
    ("broad_spectrum_antibiotics", "give_broad_spectrum_antibiotics"),
    ("crystalloid_30ml_kg", "give_crystalloid_30ml_kg"),
    ("start_norepinephrine", "start_vasopressor_norepinephrine"),
    ("order_lactate", "order_lab_lactate"),
    ("give_iv_fluids", "give_crystalloid_fluid"),
    ("aspirin_loading", "give_aspirin_loading"),
    ("p2y12", "give_p2y12_inhibitor"),
    ("activate_cath_lab", "activate_cath_lab"),
    ("12_lead_ecg", "obtain_12_lead_ecg"),
    ("heparin_bolus", "give_anticoagulation"),
    ("give_entresto", "initiate_ace_or_arb_or_arni"),
    ("start_carvedilol", "initiate_beta_blocker"),
    ("start_spironolactone", "initiate_mra"),
    ("tpa", "give_alteplase_0.9mg_kg"),
    ("calculate_nihss", "perform_nihss"),
    ("ct_head", "order_stat_ct_head"),
    ("start_insulin_infusion", "start_insulin_infusion"),
    ("give_potassium_iv", "give_potassium_iv"),
    ("start_iv_fluid_ns", "start_iv_fluid_normal_saline"),
    ("discontinue_nephrotoxins", "hold_nephrotoxic_medications"),
    ("check_creatinine", "check_baseline_egfr"),
    ("order_cbc", "order_lab_cbc"),
    ("order_bmp", "order_lab_bmp"),
    ("give_morphine_if_needed", "give_morphine_if_needed"),
    ("consult_cardiology", "request_consultation"),
]


class TestNormalizationRecovery:
    """Verify that ActionNormalizer achieves >=99.5% recovery on known action IDs."""

    @pytest.fixture
    def normalizer(self) -> ActionNormalizer:
        return ActionNormalizer()

    def test_recovery_rate(self, normalizer: ActionNormalizer) -> None:
        """Overall recovery rate must be >= 99.5%."""
        total = len(KNOWN_ACTIONS)
        recovered = 0
        failures: list[str] = []

        for input_id, expected in KNOWN_ACTIONS:
            result = normalizer.normalize(input_id)
            if result == expected:
                recovered += 1
            else:
                failures.append(f"  {input_id} -> {result} (expected {expected})")

        rate = recovered / total
        if failures:
            shown = "\n".join(failures[:10])
            pytest.fail(
                f"Normalization recovery {recovered}/{total} ({rate:.3%}) < 99.5%\n"
                + f"Failures ({len(failures)}):\n{shown}"
            )

        assert rate >= 0.995

    def test_direct_mappings_complete(self, normalizer: ActionNormalizer) -> None:
        """All default direct mappings should roundtrip at >=99%."""
        direct_mappings = normalizer.config.direct_mappings
        total = len(direct_mappings)
        recovered = 0

        for input_id, expected in direct_mappings.items():
            result = normalizer.normalize(input_id)
            if result == expected:
                recovered += 1

        rate = recovered / max(total, 1)
        assert rate >= 0.99, f"Direct mapping recovery {rate:.1%} < 99%"

    def test_identity_normalization(self, normalizer: ActionNormalizer) -> None:
        """Already-canonical action IDs should pass through unchanged."""
        canonical_ids = [
            "order_lab_lactate",
            "give_broad_spectrum_antibiotics",
            "obtain_12_lead_ecg",
            "give_alteplase_0.9mg_kg",
            "start_vasopressor_norepinephrine",
        ]
        for action_id in canonical_ids:
            assert normalizer.normalize(action_id) == action_id

    def test_no_severe_miss(self, normalizer: ActionNormalizer) -> None:
        """Critical actions must never pass through unchanged as aliases."""
        critical_actions = [
            "broad_spectrum_antibiotics",
            "tpa",
            "aspirin_loading",
            "blood_culture_before_antibiotics",
            "start_norepinephrine",
        ]
        for action_id in critical_actions:
            result = normalizer.normalize(action_id)
            assert result != action_id
