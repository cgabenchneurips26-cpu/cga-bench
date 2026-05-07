"""Tests for Y.1: CDE vs LLM constraint extraction."""

from __future__ import annotations

import pytest

from scripts.experiments.exp_cde_vs_llm import (
    _build_user_prompt,
    _extract_constraint_list,
    _parse_parsed_json,
)


class TestBuildUserPrompt:
    def test_contains_name_and_text(self) -> None:
        p = _build_user_prompt("some guideline text here", "SEPSIS-TEST")
        assert "SEPSIS-TEST" in p
        assert "some guideline text here" in p
        assert "GUIDELINE TEXT START" in p
        assert "GUIDELINE TEXT END" in p

    def test_truncation(self) -> None:
        big = "x" * 40000
        p = _build_user_prompt(big, "LARGE")
        assert "[truncated]" in p
        # Kept max_chars is 28000
        assert "x" * 28000 in p


class TestExtractConstraintList:
    def test_well_formed_json_object(self) -> None:
        resp = {
            "choices": [
                {
                    "message": {
                        "content": '{"constraints": [{"type": "MUST", "action": "order_cbc"}]}'
                    }
                }
            ]
        }
        cs = _extract_constraint_list(resp)
        assert len(cs) == 1
        assert cs[0]["type"] == "MUST"

    def test_repair_stray_text(self) -> None:
        resp = {
            "choices": [
                {
                    "message": {
                        "content": 'Sure, here:\n{"constraints": [{"type": "WITHIN"}]}\nDone.'
                    }
                }
            ]
        }
        cs = _extract_constraint_list(resp)
        assert len(cs) == 1
        assert cs[0]["type"] == "WITHIN"

    def test_missing_constraints_key_returns_empty(self) -> None:
        resp = {"choices": [{"message": {"content": "{}"}}]}
        assert _extract_constraint_list(resp) == []


class TestParseParsedJson:
    def test_flattens_nested_strings(self, tmp_path) -> None:
        import json as _json

        p = tmp_path / "x.parsed.json"
        p.write_text(
            _json.dumps(
                {
                    "sections": [
                        {"heading": "Intro", "body": "Apples and pears."},
                        {"heading": "Method", "body": ["step one", "step two"]},
                    ],
                    "meta": {"author": "anon"},
                }
            )
        )
        text, raw = _parse_parsed_json(p)
        assert "Apples and pears." in text
        assert "step one" in text
        assert raw["meta"]["author"] == "anon"
