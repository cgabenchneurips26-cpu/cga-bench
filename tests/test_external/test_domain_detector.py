from __future__ import annotations

from pathlib import Path

from cga_bench.semantic_layer.external.domain_detector import (
    DOMAIN_REGISTRY,
    DomainDetectorConfig,
    DomainMatch,
    _load_domain_registry,
    detect_domain,
    extract_actions_from_text,
    list_supported_domains,
)


class TestDomainRegistryYamlLoading:
    def test_registry_loaded_from_yaml(self):
        assert len(DOMAIN_REGISTRY) == 12

    def test_all_expected_domains_present(self):
        expected = {
            "sepsis", "chest_pain", "stroke", "heart_failure", "aki", "dka",
            "pneumonia", "hypertensive_emergency", "copd_exacerbation",
            "gi_bleeding", "pulmonary_embolism", "atrial_fibrillation",
        }
        assert set(DOMAIN_REGISTRY.keys()) == expected

    def test_each_domain_has_required_keys(self):
        for domain, info in DOMAIN_REGISTRY.items():
            assert "guideline_id" in info, f"{domain} missing guideline_id"
            assert "en_keywords" in info, f"{domain} missing en_keywords"
            assert "cn_keywords" in info, f"{domain} missing cn_keywords"
            assert len(info["en_keywords"]) > 0, f"{domain} has empty en_keywords"

    def test_guideline_ids_are_yaml_paths(self):
        for domain, info in DOMAIN_REGISTRY.items():
            gid = info["guideline_id"]
            assert gid.endswith(".yaml"), f"{domain} guideline_id {gid} not a YAML path"

    def test_load_from_explicit_path(self):
        yaml_path = Path(__file__).resolve().parents[2] / "configs" / "domain_registry.yaml"
        registry = _load_domain_registry(yaml_path)
        assert len(registry) == 12

    def test_load_from_missing_path_returns_empty(self):
        registry = _load_domain_registry(Path("/tmp/nonexistent_domain_registry.yaml"))
        assert registry == {}


class TestDetectDomainFromYaml:
    def test_sepsis_detected(self):
        result = detect_domain("Patient with sepsis and bacteremia")
        assert result is not None
        assert result.domain == "sepsis"

    def test_chest_pain_detected(self):
        result = detect_domain("Acute coronary syndrome with STEMI")
        assert result is not None
        assert result.domain == "chest_pain"

    def test_stroke_detected(self):
        result = detect_domain("Cerebrovascular accident, needs alteplase")
        assert result is not None
        assert result.domain == "stroke"

    def test_chinese_keywords_detected(self):
        result = detect_domain("患者诊断为脓毒症")
        assert result is not None
        assert result.domain == "sepsis"

    def test_no_match_returns_none(self):
        result = detect_domain("Routine physical examination, healthy adult")
        assert result is None

    def test_empty_text_returns_none(self):
        assert detect_domain("") is None

    def test_confidence_filtering(self):
        config = DomainDetectorConfig(min_confidence=0.99)
        result = detect_domain("sepsis", config)
        assert result is None or result.confidence >= 0.99


class TestExtractActionsFromText:
    def test_sepsis_chinese_actions(self):
        actions = extract_actions_from_text("需要血培养和乳酸检查", "sepsis")
        assert "order_lab_blood_culture" in actions
        assert "order_lab_lactate" in actions

    def test_unknown_domain_returns_base_actions(self):
        actions = extract_actions_from_text("some text", "unknown_domain_xyz")
        assert "take_history" in actions
        assert "assess_vital_signs" in actions


class TestListSupportedDomains:
    def test_returns_sorted_list(self):
        domains = list_supported_domains()
        assert domains == sorted(domains)
        assert len(domains) == 12
