from __future__ import annotations

from cga_bench.assessor_core.action_normalizer import (
    ActionNormalizer,
    ActionNormalizerConfig,
    NormalizationRule,
    normalize_action_id,
)
from cga_bench.cpg_model.schemas.base import Action, ActionType


def _normalizer(**kwargs) -> ActionNormalizer:
    config = ActionNormalizerConfig(**kwargs)
    return ActionNormalizer(config)


class TestNormalizerInit:
    def test_default_config_creates_normalizer(self):
        n = ActionNormalizer()
        assert n.config is not None

    def test_custom_config_accepted(self):
        config = ActionNormalizerConfig(
            direct_mappings={"foo": "bar"},
        )
        n = ActionNormalizer(config)
        assert n.normalize("foo") == "bar"

    def test_cache_starts_empty(self):
        n = ActionNormalizer()
        assert n._cache_hits == 0
        assert n._cache_misses == 0


class TestDirectMapping:
    def test_exact_match(self):
        n = _normalizer(direct_mappings={"blood_culture": "order_lab_blood_culture"})
        assert n.normalize("blood_culture") == "order_lab_blood_culture"

    def test_case_insensitive(self):
        n = _normalizer(direct_mappings={"blood_culture": "order_lab_blood_culture"})
        assert n.normalize("Blood_Culture") == "order_lab_blood_culture"

    def test_empty_string_passthrough(self):
        n = ActionNormalizer()
        assert n.normalize("") == ""

    def test_unmapped_returns_lowered(self):
        n = _normalizer(direct_mappings={})
        result = n.normalize("Some_Unknown_Action")
        assert result == "some_unknown_action"


class TestDomainSpecificMapping:
    def test_domain_mapping_takes_priority(self):
        n = _normalizer(
            direct_mappings={"vasopressor": "start_vasopressor_generic"},
            domain_specific_mappings={
                "ssc_sepsis": {"vasopressor": "start_vasopressor_norepinephrine"},
            },
        )
        assert n.normalize("vasopressor", cpg_id="ssc_sepsis") == "start_vasopressor_norepinephrine"
        assert n.normalize("vasopressor") == "start_vasopressor_generic"

    def test_unknown_domain_falls_through(self):
        n = _normalizer(
            direct_mappings={"aspirin": "give_aspirin_loading"},
            domain_specific_mappings={
                "chest_pain": {"aspirin": "give_aspirin_325"},
            },
        )
        assert n.normalize("aspirin", cpg_id="stroke") == "give_aspirin_loading"


class TestAbbreviationExpansion:
    def test_cbc_expanded(self):
        n = ActionNormalizer()
        result = n._expand_abbreviations("order_lab_cbc")
        assert "complete_blood_count" in result

    def test_ecg_expanded(self):
        n = ActionNormalizer()
        result = n._expand_abbreviations("order_ecg")
        assert "electrocardiogram" in result

    def test_unknown_abbreviation_passthrough(self):
        n = ActionNormalizer()
        assert n._expand_abbreviations("xyz_test") == "xyz_test"

    def test_multiple_abbreviations(self):
        n = ActionNormalizer()
        result = n._expand_abbreviations("order_cbc_and_bmp")
        assert "complete_blood_count" in result
        assert "basic_metabolic_panel" in result


class TestSynonymGroups:
    def test_synonym_resolves_to_canonical(self):
        n = _normalizer(
            synonym_groups={"order_lab_lactate": ["lactate", "check_lactate", "serum_lactate"]},
        )
        assert n.normalize("check_lactate") == "order_lab_lactate"
        assert n.normalize("serum_lactate") == "order_lab_lactate"

    def test_canonical_form_not_in_synonyms_still_works(self):
        n = _normalizer(
            synonym_groups={"order_lab_lactate": ["lactate_level"]},
        )
        assert n.normalize("lactate_level") == "order_lab_lactate"


class TestPatternRules:
    def test_pattern_rule_applied(self):
        n = _normalizer(
            pattern_rules=[
                NormalizationRule(
                    pattern=r"^order_(\w+)$",
                    replacement=r"order_lab_\1",
                    priority=10,
                ),
            ],
        )
        assert n.normalize("order_potassium") == "order_lab_potassium"

    def test_higher_priority_wins(self):
        n = _normalizer(
            pattern_rules=[
                NormalizationRule(pattern=r"^give_(.*)$", replacement=r"give_med_\1", priority=1),
                NormalizationRule(pattern=r"^give_(.*)$", replacement=r"give_drug_\1", priority=10),
            ],
        )
        result = n.normalize("give_aspirin")
        assert result == "give_drug_aspirin"


class TestFuzzyMatching:
    def test_fuzzy_match_from_cpg_allowed(self):
        n = _normalizer(
            cpg_allowed_actions={
                "sepsis": {"order_lab_blood_culture", "give_broad_spectrum_antibiotics"},
            },
        )
        result = n.normalize("order_blood_culture", cpg_id="sepsis")
        assert result in {"order_lab_blood_culture", "order_blood_culture"}

    def test_no_cpg_returns_normalized(self):
        n = _normalizer()
        result = n.normalize("random_unknown_action")
        assert result == "random_unknown_action"


class TestCaching:
    def test_cache_hit_on_second_call(self):
        n = _normalizer(direct_mappings={"a": "b"})
        n.normalize("a")
        n.normalize("a")
        assert n._cache_hits == 1
        assert n._cache_misses == 1

    def test_different_cpg_id_creates_different_cache_key(self):
        n = _normalizer(
            domain_specific_mappings={
                "sepsis": {"x": "y"},
                "stroke": {"x": "z"},
            },
        )
        r1 = n.normalize("x", cpg_id="sepsis")
        r2 = n.normalize("x", cpg_id="stroke")
        assert r1 == "y"
        assert r2 == "z"


class TestDeterminism:
    def test_same_input_same_output_100_times(self):
        n = ActionNormalizer()
        results = {n.normalize("blood_culture_before_antibiotics") for _ in range(100)}
        assert len(results) == 1

    def test_order_independent(self):
        n1 = ActionNormalizer()
        n2 = ActionNormalizer()
        inputs = ["order_lab_lactate", "give_aspirin", "start_norepinephrine"]
        results1 = [n1.normalize(a) for a in inputs]
        results2 = [n2.normalize(a) for a in reversed(inputs)]
        assert results1 == list(reversed(results2))


class TestNormalizeAction:
    def test_normalize_action_object(self):
        n = _normalizer(direct_mappings={"old_id": "new_id"})
        action = Action(
            type=ActionType.ORDER_LAB,
            action_id="old_id",
            args={},
            timestamp_minutes=5.0,
        )
        result = n.normalize_action(action)
        assert result.action_id == "new_id"
        assert result.type == ActionType.ORDER_LAB


class TestModuleLevelFunction:
    def test_normalize_action_id_function(self):
        result = normalize_action_id("blood_culture_before_antibiotics")
        assert isinstance(result, str)
        assert len(result) > 0


class TestN1N2CircularAliasFix:
    def test_n1_assess_urine_output_maps_to_monitor(self):
        n = ActionNormalizer()
        assert n.normalize("assess_urine_output") == "monitor_urine_output"

    def test_n1_monitor_urine_output_passthrough(self):
        n = ActionNormalizer()
        assert n.normalize("monitor_urine_output") == "monitor_urine_output"

    def test_n1_urine_output_idempotent(self):
        n = ActionNormalizer()
        assert n.normalize(n.normalize("assess_urine_output")) == "monitor_urine_output"

    def test_n2_monitor_neuro_status_maps_to_assess(self):
        n = ActionNormalizer()
        assert n.normalize("monitor_neurological_status") == "assess_neurological_status"

    def test_n2_assess_neuro_status_passthrough(self):
        n = ActionNormalizer()
        assert n.normalize("assess_neurological_status") == "assess_neurological_status"

    def test_n2_neuro_status_idempotent(self):
        n = ActionNormalizer()
        assert n.normalize(n.normalize("monitor_neurological_status")) == "assess_neurological_status"


class TestN3N4N5ResidualNormalizerFixes:
    def test_n3_endocrinology_consult_word_order(self):
        n = ActionNormalizer()
        assert n.normalize("endocrinology_consult") == "consult_endocrinology"
        assert n.normalize("consult_endocrinology") == "consult_endocrinology"

    def test_n4_order_lab_creatinine_canonical_passthrough(self):
        n = ActionNormalizer()
        # AKI graphs reference order_lab_creatinine directly (19 occurrences).
        # Prior bug: line 1768 mapped it to order_lab_bmp, breaking AKI matching.
        assert n.normalize("order_lab_creatinine") == "order_lab_creatinine"

    def test_n5_order_imaging_ecg_resolves_to_ecg_family(self):
        n = ActionNormalizer()
        # order_imaging_ecg (5 graph occurrences) should resolve into the ECG family.
        result = n.normalize("order_imaging_ecg")
        assert result in {"order_ecg", "obtain_12_lead_ecg"}
        # idempotent: re-normalizing produces a stable canonical
        assert n.normalize(result) == result or n.normalize(result) == "obtain_12_lead_ecg"
