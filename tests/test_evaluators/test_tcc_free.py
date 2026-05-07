"""Unit tests for evaluators/tcc_free.py (CRES-1A).

All tests use the MockLLMProvider. No API calls happen here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cga_bench.agent_runner.llm_provider import LLMBackend, LLMConfig
from cga_bench.evaluators.tcc_free import (
    _FALLBACK_CORPUS,
    _PREFIX_TO_CORPUS,
    TCCFreeConfig,
    TCCFreeEvaluator,
    TCCFreeViolation,
    build_default_evaluator,
)


@pytest.fixture
def sample_record() -> dict:
    return {
        "scenario_id": "sepsis_basic_adult_hypotension",
        "run_index": 0,
        "model": "gemma31b",
        "cga_pass": False,
        "performed_actions": [
            "order_lactate",
            "give_broad_spectrum_antibiotics",
        ],
        "expected_actions": [
            "order_lactate",
            "give_broad_spectrum_antibiotics",
            "order_blood_culture",
            "give_crystalloid_30ml_kg",
        ],
        "n_violations": 2,
        "violation_types": ["omission", "omission"],
    }


@pytest.fixture
def mock_evaluator() -> TCCFreeEvaluator:
    return build_default_evaluator(use_mock=True)


def test_prefix_map_covers_common_prefixes():
    """Sanity: core scenario prefixes route to real corpus files."""
    for prefix in ("sepsis", "stemi", "stroke", "dka", "aabb"):
        assert prefix in _PREFIX_TO_CORPUS
        assert _PREFIX_TO_CORPUS[prefix].endswith(".parsed.json")


def test_fallback_corpus_is_universal_safety():
    assert _FALLBACK_CORPUS == "Universal-Clinical-Safety.parsed.json"


def test_config_rejects_missing_corpus_dir(tmp_path: Path):
    missing = tmp_path / "does_not_exist"
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("SYSTEM:\nhi\nUSER:\nbye")
    with pytest.raises(FileNotFoundError):
        TCCFreeConfig(
            corpus_dir=missing,
            prompt_template_path=prompt,
            llm_config=LLMConfig(backend=LLMBackend.MOCK, model="mock"),
        )


def test_config_rejects_missing_prompt(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    with pytest.raises(FileNotFoundError):
        TCCFreeConfig(
            corpus_dir=corpus,
            prompt_template_path=tmp_path / "missing.txt",
            llm_config=LLMConfig(backend=LLMBackend.MOCK, model="mock"),
        )


def test_resolve_corpus_filename_known_prefix(mock_evaluator: TCCFreeEvaluator):
    assert mock_evaluator._resolve_corpus_filename("sepsis_basic_adult") == "SSC-2021-Sepsis-Hour1-Bundle.parsed.json"


def test_resolve_corpus_filename_unknown_prefix_falls_back(
    mock_evaluator: TCCFreeEvaluator,
):
    assert mock_evaluator._resolve_corpus_filename("nonexistent_scenario") == _FALLBACK_CORPUS


def test_serialize_trace_includes_actions(mock_evaluator: TCCFreeEvaluator, sample_record: dict):
    text = mock_evaluator._serialize_trace(sample_record)
    assert "order_lactate" in text
    assert "order_blood_culture" in text
    assert "gemma31b" in text
    assert "sepsis_basic_adult_hypotension" in text


def test_build_query_combines_actions(mock_evaluator: TCCFreeEvaluator, sample_record: dict):
    q = mock_evaluator._build_query(sample_record)
    assert "lactate" in q
    assert "blood culture" in q or "blood_culture" in q or "blood" in q


def test_render_prompt_splits_into_two_messages(
    mock_evaluator: TCCFreeEvaluator,
):
    msgs = mock_evaluator._render_prompt("SSC-2021", "guideline text", "trace text")
    assert len(msgs) == 2
    assert msgs[0].role == "system"
    assert msgs[1].role == "user"
    assert "trace text" in msgs[1].content
    assert "guideline text" in msgs[1].content
    assert "SSC-2021" in msgs[1].content


def test_render_prompt_requires_both_markers(mock_evaluator: TCCFreeEvaluator, tmp_path: Path):
    """Malformed templates must raise clearly, not silently produce garbage."""
    bad = tmp_path / "bad.txt"
    bad.write_text("no markers here")
    mock_evaluator._prompt_template = bad.read_text()
    with pytest.raises(ValueError, match="SYSTEM:"):
        mock_evaluator._render_prompt("x", "y", "z")


def test_parse_verdict_handles_valid_json(mock_evaluator: TCCFreeEvaluator):
    record = {"scenario_id": "sepsis_x", "run_index": 0, "model": "m"}
    llm_text = json.dumps(
        {
            "violations": [
                {
                    "violation_type": "omission",
                    "action_involved": None,
                    "expected_action": "order_blood_culture",
                    "description": "Missing culture",
                    "source_recommendation": "SSC_R2",
                }
            ],
            "verdict_binary": "fail",
            "reasoning": "missing culture before antibiotics",
        }
    )
    verdict = mock_evaluator._parse_verdict(llm_text, record, tokens_used=42)
    assert verdict.verdict_binary == "fail"
    assert len(verdict.violations) == 1
    assert verdict.violations[0].violation_type == "omission"
    assert verdict.violations[0].source_recommendation == "SSC_R2"
    assert verdict.tokens_used == 42


def test_parse_verdict_handles_broken_json(mock_evaluator: TCCFreeEvaluator):
    record = {"scenario_id": "x", "run_index": 0, "model": "m"}
    verdict = mock_evaluator._parse_verdict("not json at all, really", record, tokens_used=5)
    assert verdict.verdict_binary == "fail"
    assert "not json" in verdict.reasoning.lower()
    assert verdict.tokens_used == 5


def test_parse_verdict_coerces_invalid_binary_to_fail(
    mock_evaluator: TCCFreeEvaluator,
):
    record = {"scenario_id": "x", "run_index": 0, "model": "m"}
    llm_text = json.dumps({"violations": [], "verdict_binary": "WATERMELON", "reasoning": "?"})
    verdict = mock_evaluator._parse_verdict(llm_text, record, tokens_used=1)
    assert verdict.verdict_binary == "fail"


def test_evaluate_end_to_end_with_mock(mock_evaluator: TCCFreeEvaluator, sample_record: dict):
    """Full evaluate() path with mock backend should return a well-formed verdict."""
    verdict = mock_evaluator.evaluate(sample_record)
    assert verdict.scenario_id == sample_record["scenario_id"]
    assert verdict.model == sample_record["model"]
    assert verdict.verdict_binary in ("pass", "fail")
    # Mock provider tracks call history
    assert mock_evaluator.llm.call_history, "mock LLM should have been called"
    # BM25 index must have been built for the corpus file
    assert "SSC-2021-Sepsis-Hour1-Bundle.parsed.json" in mock_evaluator._bm25_cache


def test_evaluate_missing_scenario_id_raises(mock_evaluator: TCCFreeEvaluator):
    with pytest.raises(ValueError, match="scenario_id"):
        mock_evaluator.evaluate({"run_index": 0, "model": "m"})


def test_render_prompt_tolerates_braces_in_excerpts(
    mock_evaluator: TCCFreeEvaluator,
):
    """Guideline excerpts containing literal '{' or '}' must not crash."""
    excerpts_with_braces = "Recommendation R1: dose {0.9 mg/kg} over 60 min"
    trace_with_braces = "action: give_{stuff}"
    msgs = mock_evaluator._render_prompt("domain-x", excerpts_with_braces, trace_with_braces)
    assert "{0.9 mg/kg}" in msgs[1].content
    assert "give_{stuff}" in msgs[1].content


def test_serialize_trace_does_not_leak_tcc_verdict_fields(
    mock_evaluator: TCCFreeEvaluator,
):
    """Catalogue-free evaluator must not see TCC-derived signals in the prompt."""
    record = {
        "scenario_id": "sepsis_x",
        "model": "m",
        "performed_actions": ["a", "b"],
        "expected_actions": ["a", "b", "c"],
        # Fields that MUST NOT leak:
        "cga_pass": False,
        "v4_hard": True,
        "n_violations": 9,
        "violation_types": ["omission", "timing", "commission"],
        "ao_fa": True,
        "coverage": 0.5,
        "f1": 0.3,
    }
    text = mock_evaluator._serialize_trace(record)
    for leak in (
        "violation_types",
        "omission",
        "commission",
        "timing",
        "v4_hard",
        "cga_pass",
        "n_violations",
        "ao_fa",
        "coverage",
    ):
        assert leak not in text, f"TCC-leaked field {leak!r} found in trace text"


def test_tcc_free_has_no_transitive_cpg_model_imports():
    """Defense-critical: loading the module must not pull in cpg_* modules."""
    import importlib
    import sys

    # Purge any pre-loaded cga_bench.* to simulate a fresh import.
    for mod_name in list(sys.modules):
        if mod_name.startswith(("cga_bench.cpg_", "cga_bench.assessor_core")):
            del sys.modules[mod_name]
    importlib.import_module("cga_bench.evaluators.tcc_free")
    for loaded in sys.modules:
        assert not loaded.startswith("cga_bench.cpg_engine"), f"tcc_free leaked cpg_engine import: {loaded}"
        assert not loaded.startswith("cga_bench.assessor_core"), f"tcc_free leaked assessor_core import: {loaded}"


def test_violation_to_dict_roundtrip():
    v = TCCFreeViolation(
        violation_type="commission",
        action_involved="give_nitroglycerin",
        expected_action=None,
        description="RV infarct + nitrates",
        source_recommendation="AHA_R15",
    )
    d = v.to_dict()
    assert d["violation_type"] == "commission"
    assert d["action_involved"] == "give_nitroglycerin"
    assert d["source_recommendation"] == "AHA_R15"
