"""Tests for sgsc.extraction.atom_proposer — LLM-as-proposer with mock LLM."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from sgsc.extraction.atom_proposer import (
    PASS_SEEDS,
    AtomProposerConfig,
    _build_corpus_context,
    _extract_json,
    propose_atoms,
)
from sgsc.schemas.atom import VALID_ACTION_TYPES, AtomAction

# ------------------------------------------------------------------
# _extract_json tests
# ------------------------------------------------------------------


class TestExtractJson:
    """Tests for _extract_json helper."""

    def test_plain_json_array(self) -> None:
        text = '[{"key": "value"}, {"key2": "value2"}]'
        result = _extract_json(text)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_plain_json_object(self) -> None:
        text = '{"atom_id": "test_001", "action": "give_abx"}'
        result = _extract_json(text)
        assert isinstance(result, dict)
        assert result["atom_id"] == "test_001"

    def test_markdown_code_block(self) -> None:
        text = 'Here are the results:\n```json\n[{"id": 1}]\n```\nDone.'
        result = _extract_json(text)
        assert result == [{"id": 1}]

    def test_markdown_code_block_no_lang(self) -> None:
        text = 'Output:\n```\n{"id": 2}\n```'
        result = _extract_json(text)
        assert result == {"id": 2}

    def test_think_tags_stripped(self) -> None:
        text = '<think>reasoning here</think>\n[{"atom": "test"}]'
        result = _extract_json(text)
        assert result == [{"atom": "test"}]

    def test_embedded_json_in_text(self) -> None:
        text = 'I found these atoms: [{"a": 1}, {"b": 2}] and that is all.'
        result = _extract_json(text)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_invalid_json_raises(self) -> None:
        text = "This is just plain text with no JSON at all."
        with pytest.raises(ValueError, match="Could not extract JSON"):
            _extract_json(text)

    def test_nested_braces(self) -> None:
        text = '{"outer": {"inner": [1, 2, 3]}}'
        result = _extract_json(text)
        assert result["outer"]["inner"] == [1, 2, 3]


# ------------------------------------------------------------------
# AtomProposerConfig tests
# ------------------------------------------------------------------


class TestAtomProposerConfig:
    """Tests for AtomProposerConfig dataclass."""

    def test_defaults(self) -> None:
        config = AtomProposerConfig(endpoint="http://localhost:8000/v1")
        assert config.model == "default"
        assert config.temperature == 0.2
        assert config.max_tokens == 8192
        assert config.api_key == "sk-no-key-required"
        assert config.timeout_seconds == 300.0
        assert config.enable_multi_pass is False
        assert config.corpus_context_chars == 0

    def test_custom_values(self) -> None:
        config = AtomProposerConfig(
            endpoint="http://example.com/v1",
            model="qwen-35b",
            temperature=0.5,
            max_tokens=2048,
            api_key="sk-test",
        )
        assert config.model == "qwen-35b"
        assert config.temperature == 0.5

    def test_frozen(self) -> None:
        config = AtomProposerConfig(endpoint="http://localhost:8000/v1")
        with pytest.raises(AttributeError):
            config.model = "changed"  # type: ignore[misc]


# ------------------------------------------------------------------
# propose_atoms with mock LLM
# ------------------------------------------------------------------

_MOCK_LLM_RESPONSE = json.dumps(
    [
        {
            "atom_id": "ssc_2021_mock_abx",
            "source": {
                "guideline_id": "ssc_sepsis_hour1",
                "section": "Hour-1 Bundle",
                "quote": "Administer broad-spectrum antibiotics within 1 hour of sepsis recognition.",
            },
            "population": {
                "inclusion": ["sepsis"],
                "exclusion": [],
            },
            "action": {
                "canonical_id": "give_broad_spectrum_antibiotics",
                "action_type": "medication",
            },
            "constraint": {
                "type": "WITHIN",
                "activation_event": "sepsis_recognition",
                "deadline_minutes": 60,
            },
            "evidence": {
                "system": "GRADE",
                "recommendation_class": "I",
                "level": "B",
            },
        }
    ]
)


class TestProposeAtoms:
    """Tests for propose_atoms with mocked LLM calls."""

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_basic_proposal(self, mock_call: MagicMock) -> None:
        mock_call.return_value = _MOCK_LLM_RESPONSE
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        recs = [{"text": "Give antibiotics within 1 hour.", "section": "Hour-1"}]
        atoms = propose_atoms(config, "ssc_sepsis_hour1", recs)
        assert len(atoms) == 1
        assert atoms[0].atom_id == "ssc_2021_mock_abx"
        assert atoms[0].constraint.type == "WITHIN"
        assert atoms[0].constraint.deadline_minutes == 60

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_proposed_by_set(self, mock_call: MagicMock) -> None:
        mock_call.return_value = _MOCK_LLM_RESPONSE
        config = AtomProposerConfig(endpoint="http://mock:8000/v1", model="test-model")
        atoms = propose_atoms(config, "ssc_sepsis_hour1", [{"text": "Give abx."}])
        assert atoms[0].proposed_by == "test-model"

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_empty_response(self, mock_call: MagicMock) -> None:
        mock_call.return_value = "[]"
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "test", [{"text": "rec"}])
        assert atoms == []

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_invalid_json_returns_empty(self, mock_call: MagicMock) -> None:
        mock_call.return_value = "I cannot parse this guideline."
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "test", [{"text": "rec"}])
        assert atoms == []

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_partial_valid_atoms(self, mock_call: MagicMock) -> None:
        """One valid atom + one invalid → only valid returned."""
        response = json.dumps(
            [
                {
                    "atom_id": "valid_001",
                    "source": {
                        "guideline_id": "test",
                        "section": "A",
                        "quote": "Valid recommendation text here.",
                    },
                    "population": {"inclusion": ["all"], "exclusion": []},
                    "action": {"canonical_id": "do_something", "action_type": "lab"},
                    "constraint": {"type": "REQUIRED"},
                    "evidence": {"system": "GRADE", "recommendation_class": "I", "level": "A"},
                },
                {"atom_id": "invalid_missing_fields"},
            ]
        )
        mock_call.return_value = response
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "test", [{"text": "rec"}])
        assert len(atoms) == 1
        assert atoms[0].atom_id == "valid_001"

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_single_object_wrapped_in_list(self, mock_call: MagicMock) -> None:
        """LLM returns a single object instead of array."""
        response = json.dumps(
            {
                "atom_id": "single_001",
                "source": {
                    "guideline_id": "test",
                    "section": "A",
                    "quote": "Single recommendation quote text.",
                },
                "population": {"inclusion": ["all"], "exclusion": []},
                "action": {"canonical_id": "single_action", "action_type": "procedure"},
                "constraint": {"type": "REQUIRED"},
                "evidence": {"system": "AHA", "recommendation_class": "I", "level": "A"},
            }
        )
        mock_call.return_value = response
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "test", [{"text": "rec"}])
        assert len(atoms) == 1

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_markdown_wrapped_response(self, mock_call: MagicMock) -> None:
        """LLM wraps JSON in markdown code block."""
        mock_call.return_value = f"Here are the atoms:\n```json\n{_MOCK_LLM_RESPONSE}\n```"
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "ssc", [{"text": "Give abx within 1 hour."}])
        assert len(atoms) == 1

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_chunking_large_corpus(self, mock_call: MagicMock) -> None:
        """8 recommendations -> 2 chunks (5 + 3), atoms merged."""
        mock_call.return_value = _MOCK_LLM_RESPONSE  # 1 atom per call
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        recs = [{"text": f"Recommendation {i}."} for i in range(8)]
        atoms = propose_atoms(config, "test", recs)
        # 2 chunks, each returns 1 atom, but same atom_id so deduped to 1
        assert mock_call.call_count == 2
        assert len(atoms) >= 1

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_chunking_distinct_atoms(self, mock_call: MagicMock) -> None:
        """Chunks returning distinct atom_ids are all kept."""
        atom_a = json.dumps(
            [
                {
                    "atom_id": "chunk_a_001",
                    "source": {"guideline_id": "test", "section": "A", "quote": "Quote A."},
                    "population": {"inclusion": ["all"], "exclusion": []},
                    "action": {"canonical_id": "action_a", "action_type": "lab"},
                    "constraint": {"type": "REQUIRED"},
                    "evidence": {"system": "GRADE", "recommendation_class": "I", "level": "A"},
                }
            ]
        )
        atom_b = json.dumps(
            [
                {
                    "atom_id": "chunk_b_001",
                    "source": {"guideline_id": "test", "section": "B", "quote": "Quote B."},
                    "population": {"inclusion": ["all"], "exclusion": []},
                    "action": {"canonical_id": "action_b", "action_type": "medication"},
                    "constraint": {"type": "REQUIRED"},
                    "evidence": {"system": "GRADE", "recommendation_class": "I", "level": "B"},
                }
            ]
        )
        mock_call.side_effect = [atom_a, atom_b]
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        recs = [{"text": f"Recommendation {i}."} for i in range(7)]
        atoms = propose_atoms(config, "test", recs)
        assert mock_call.call_count == 2
        assert len(atoms) == 2
        ids = {a.atom_id for a in atoms}
        assert ids == {"chunk_a_001", "chunk_b_001"}

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_no_chunking_at_boundary(self, mock_call: MagicMock) -> None:
        """Exactly 5 recommendations -> single call, no chunking."""
        mock_call.return_value = _MOCK_LLM_RESPONSE
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        recs = [{"text": f"Rec {i}."} for i in range(5)]
        atoms = propose_atoms(config, "test", recs)
        assert mock_call.call_count == 1


# ------------------------------------------------------------------
# Action type taxonomy validation (E3-a: 7 -> 14 types)
# ------------------------------------------------------------------


def _make_atom_response(atom_id: str, canonical_id: str, action_type: str, constraint_type: str = "REQUIRED") -> str:
    """Build a minimal valid LLM JSON response for a single atom."""
    return json.dumps(
        [
            {
                "atom_id": atom_id,
                "source": {
                    "guideline_id": "test",
                    "section": "Test Section",
                    "quote": "A verbatim quote from the guideline text.",
                },
                "population": {"inclusion": ["adults"], "exclusion": []},
                "action": {"canonical_id": canonical_id, "action_type": action_type},
                "constraint": {"type": constraint_type},
                "evidence": {"system": "GRADE", "recommendation_class": "I", "level": "B"},
            }
        ]
    )


class TestActionTypeTaxonomy:
    """Validate the 14-type action taxonomy (E3-a expansion)."""

    def test_valid_action_types_has_14_values(self) -> None:
        assert len(VALID_ACTION_TYPES) == 14

    def test_original_7_types_present(self) -> None:
        original = {"medication", "lab", "imaging", "procedure", "consult", "reassess", "disposition"}
        assert original.issubset(VALID_ACTION_TYPES)

    def test_new_7_types_present(self) -> None:
        new_types = {
            "medication_hold",
            "medication_avoid",
            "monitoring",
            "dose_adjustment",
            "followup",
            "prevention",
            "discharge",
        }
        assert new_types.issubset(VALID_ACTION_TYPES)

    def test_invalid_action_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="action_type must be one of"):
            AtomAction(canonical_id="invalid_action", action_type="documentation")

    def test_unknown_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="action_type must be one of"):
            AtomAction(canonical_id="unknown_action", action_type="clinical_decision")


class TestNewActionTypeAcceptance:
    """Each new action_type is accepted by propose_atoms via mock LLM."""

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_accepts_medication_hold(self, mock_call: MagicMock) -> None:
        mock_call.return_value = _make_atom_response(
            "aki_hold_ace",
            "hold_ace_inhibitor",
            "medication_hold",
            "FORBIDDEN",
        )
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "kdigo_aki", [{"text": "Hold ACE inhibitors in AKI."}])
        assert len(atoms) == 1
        assert atoms[0].action.action_type == "medication_hold"

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_accepts_medication_avoid(self, mock_call: MagicMock) -> None:
        mock_call.return_value = _make_atom_response(
            "aki_avoid_nsaid",
            "avoid_nsaid",
            "medication_avoid",
            "FORBIDDEN",
        )
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "kdigo_aki", [{"text": "Avoid NSAIDs in AKI patients."}])
        assert len(atoms) == 1
        assert atoms[0].action.action_type == "medication_avoid"

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_accepts_monitoring(self, mock_call: MagicMock) -> None:
        mock_call.return_value = _make_atom_response(
            "aki_monitor_uo",
            "monitor_urine_output",
            "monitoring",
        )
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "kdigo_aki", [{"text": "Monitor urine output hourly."}])
        assert len(atoms) == 1
        assert atoms[0].action.action_type == "monitoring"

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_accepts_dose_adjustment(self, mock_call: MagicMock) -> None:
        mock_call.return_value = _make_atom_response(
            "aki_dose_adj",
            "dose_adjust_renal",
            "dose_adjustment",
        )
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "kdigo_aki", [{"text": "Adjust dose for renal function."}])
        assert len(atoms) == 1
        assert atoms[0].action.action_type == "dose_adjustment"

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_accepts_followup(self, mock_call: MagicMock) -> None:
        mock_call.return_value = _make_atom_response(
            "aki_followup",
            "schedule_nephrology_followup",
            "followup",
        )
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "kdigo_aki", [{"text": "Schedule nephrology follow-up."}])
        assert len(atoms) == 1
        assert atoms[0].action.action_type == "followup"

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_accepts_prevention(self, mock_call: MagicMock) -> None:
        mock_call.return_value = _make_atom_response(
            "aki_prevention",
            "pre_hydration",
            "prevention",
        )
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "kdigo_contrast_aki", [{"text": "Pre-hydrate before contrast."}])
        assert len(atoms) == 1
        assert atoms[0].action.action_type == "prevention"

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_accepts_discharge(self, mock_call: MagicMock) -> None:
        mock_call.return_value = _make_atom_response(
            "aki_discharge",
            "discharge_with_renal_plan",
            "discharge",
        )
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "kdigo_aki", [{"text": "Discharge with renal follow-up plan."}])
        assert len(atoms) == 1
        assert atoms[0].action.action_type == "discharge"

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_invalid_type_from_llm_is_rejected(self, mock_call: MagicMock) -> None:
        """LLM returns an unknown action_type -> atom is rejected silently."""
        mock_call.return_value = _make_atom_response(
            "bad_type_001",
            "some_action",
            "documentation",
        )
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "test", [{"text": "Document findings."}])
        assert len(atoms) == 0


# ------------------------------------------------------------------
# E3-c: Corpus context injection tests
# ------------------------------------------------------------------


class TestBuildCorpusContext:
    """Tests for _build_corpus_context helper (E3-c head+tail truncation)."""

    def test_empty_corpus_returns_empty(self) -> None:
        assert _build_corpus_context("", 8000) == ""

    def test_zero_max_chars_returns_empty(self) -> None:
        assert _build_corpus_context("Some text", 0) == ""

    def test_negative_max_chars_returns_empty(self) -> None:
        assert _build_corpus_context("Some text", -1) == ""

    def test_short_corpus_included_fully(self) -> None:
        corpus = "Short guideline text."
        result = _build_corpus_context(corpus, 8000)
        assert "=== GUIDELINE CONTEXT ===" in result
        assert "=== END CONTEXT ===" in result
        assert "Short guideline text." in result
        assert "omitted" not in result

    def test_long_corpus_head_tail_truncated(self) -> None:
        corpus = "A" * 5000 + "MIDDLE" + "Z" * 5000
        result = _build_corpus_context(corpus, 100)
        assert "=== GUIDELINE CONTEXT ===" in result
        assert "=== END CONTEXT ===" in result
        # Head (70% of 100 = 70 chars of 'A')
        assert "AAAAAAA" in result
        # Tail (30% of 100 = 30 chars of 'Z')
        assert "ZZZZZZZ" in result
        # Omission notice
        assert "chars omitted" in result
        # Middle is not present
        assert "MIDDLE" not in result

    def test_exact_boundary_no_truncation(self) -> None:
        corpus = "X" * 100
        result = _build_corpus_context(corpus, 100)
        assert "omitted" not in result
        assert corpus in result

    def test_one_char_over_triggers_truncation(self) -> None:
        corpus = "X" * 101
        result = _build_corpus_context(corpus, 100)
        assert "chars omitted" in result


class TestCorpusInjectionInProposeAtoms:
    """Tests for corpus_text parameter in propose_atoms (E3-c)."""

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_no_corpus_backward_compatible(self, mock_call: MagicMock) -> None:
        """propose_atoms without corpus_text works as before."""
        mock_call.return_value = _MOCK_LLM_RESPONSE
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "test", [{"text": "Give abx."}])
        assert len(atoms) == 1
        # user_prompt should NOT contain GUIDELINE CONTEXT
        call_args = mock_call.call_args
        user_prompt = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("user_prompt", "")
        assert "GUIDELINE CONTEXT" not in user_prompt

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_corpus_injected_when_configured(self, mock_call: MagicMock) -> None:
        """corpus_text appears in user_prompt when corpus_context_chars > 0."""
        mock_call.return_value = _MOCK_LLM_RESPONSE
        config = AtomProposerConfig(
            endpoint="http://mock:8000/v1",
            corpus_context_chars=8000,
        )
        corpus = "This is the full clinical practice guideline for sepsis management."
        atoms = propose_atoms(config, "ssc", [{"text": "Give abx."}], corpus_text=corpus)
        assert len(atoms) == 1
        call_args = mock_call.call_args
        user_prompt = call_args[0][2]
        assert "GUIDELINE CONTEXT" in user_prompt
        assert "full clinical practice guideline" in user_prompt

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_corpus_disabled_when_chars_zero(self, mock_call: MagicMock) -> None:
        """corpus_text provided but corpus_context_chars=0 → no injection."""
        mock_call.return_value = _MOCK_LLM_RESPONSE
        config = AtomProposerConfig(endpoint="http://mock:8000/v1", corpus_context_chars=0)
        corpus = "Full guideline text here."
        atoms = propose_atoms(config, "test", [{"text": "rec"}], corpus_text=corpus)
        assert len(atoms) == 1
        call_args = mock_call.call_args
        user_prompt = call_args[0][2]
        assert "GUIDELINE CONTEXT" not in user_prompt


class TestMultiPassExtraction:
    """Tests for multi-pass extraction (E3-b)."""

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_single_pass_default(self, mock_call: MagicMock) -> None:
        """Default config runs single pass."""
        mock_call.return_value = _MOCK_LLM_RESPONSE
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        atoms = propose_atoms(config, "test", [{"text": "rec"}])
        assert mock_call.call_count == 1
        assert len(atoms) == 1

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_multi_pass_three_calls(self, mock_call: MagicMock) -> None:
        """enable_multi_pass=True runs 3 passes (positive, negative, process)."""
        mock_call.return_value = _MOCK_LLM_RESPONSE
        config = AtomProposerConfig(
            endpoint="http://mock:8000/v1",
            enable_multi_pass=True,
        )
        atoms = propose_atoms(config, "test", [{"text": "rec"}])
        assert mock_call.call_count == 3
        # Same atom_id returned 3 times → deduped to 1
        assert len(atoms) == 1

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_multi_pass_distinct_atoms_kept(self, mock_call: MagicMock) -> None:
        """Different atoms from different passes are all retained."""
        positive_resp = _make_atom_response("pos_001", "give_abx", "medication")
        negative_resp = _make_atom_response("neg_001", "avoid_nsaid", "medication_avoid", "FORBIDDEN")
        process_resp = _make_atom_response("proc_001", "monitor_output", "monitoring")
        mock_call.side_effect = [positive_resp, negative_resp, process_resp]
        config = AtomProposerConfig(
            endpoint="http://mock:8000/v1",
            enable_multi_pass=True,
        )
        atoms = propose_atoms(config, "test", [{"text": "rec"}])
        assert mock_call.call_count == 3
        assert len(atoms) == 3
        ids = {a.atom_id for a in atoms}
        assert ids == {"pos_001", "neg_001", "proc_001"}

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_multi_pass_system_prompt_differs(self, mock_call: MagicMock) -> None:
        """Each pass uses a different system prompt with FOCUS directive."""
        mock_call.return_value = "[]"
        config = AtomProposerConfig(
            endpoint="http://mock:8000/v1",
            enable_multi_pass=True,
        )
        propose_atoms(config, "test", [{"text": "rec"}])
        assert mock_call.call_count == 3
        system_prompts = [call[0][1] for call in mock_call.call_args_list]
        assert "POSITIVE/PERFORMATIVE" in system_prompts[0]
        assert "NEGATIVE/PROHIBITIVE" in system_prompts[1]
        assert "MONITORING" in system_prompts[2]


# ------------------------------------------------------------------
# Deterministic mode tests (seed / top_p)
# ------------------------------------------------------------------


class TestDeterministicMode:
    """Tests for deterministic extraction mode (per-request seed + top_p)."""

    def test_pass_seeds_constant_has_four_entries(self) -> None:
        """PASS_SEEDS must have positive, negative, process, and default keys."""
        assert set(PASS_SEEDS.keys()) == {"positive", "negative", "process", "default"}
        # Each value must be an int
        for v in PASS_SEEDS.values():
            assert isinstance(v, int)

    def test_top_p_default_is_one(self) -> None:
        config = AtomProposerConfig(endpoint="http://mock:8000/v1")
        assert config.top_p == 1.0

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_top_p_in_config(self, mock_call: MagicMock) -> None:
        """top_p is stored in config and forwarded to _llm_call."""
        mock_call.return_value = "[]"
        config = AtomProposerConfig(
            endpoint="http://mock:8000/v1",
            top_p=0.95,
        )
        assert config.top_p == 0.95
        propose_atoms(config, "test", [{"text": "rec"}])
        # _llm_call receives the config with top_p set
        passed_config = mock_call.call_args[0][0]
        assert passed_config.top_p == 0.95

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_deterministic_mode_passes_seed_to_llm_call(self, mock_call: MagicMock) -> None:
        """When deterministic=True + multi_pass, each pass gets its PASS_SEEDS value."""
        mock_call.return_value = "[]"
        config = AtomProposerConfig(
            endpoint="http://mock:8000/v1",
            enable_multi_pass=True,
            deterministic=True,
        )
        propose_atoms(config, "test", [{"text": "rec"}])
        assert mock_call.call_count == 3
        # Extract seed kwarg from each call
        seeds = [call.kwargs.get("seed") for call in mock_call.call_args_list]
        assert seeds == [
            PASS_SEEDS["positive"],
            PASS_SEEDS["negative"],
            PASS_SEEDS["process"],
        ]

    @patch("sgsc.extraction.atom_proposer._llm_call")
    def test_non_deterministic_mode_no_seed(self, mock_call: MagicMock) -> None:
        """When deterministic=False (default), seed is None for all passes."""
        mock_call.return_value = "[]"
        config = AtomProposerConfig(
            endpoint="http://mock:8000/v1",
            enable_multi_pass=True,
            deterministic=False,
        )
        propose_atoms(config, "test", [{"text": "rec"}])
        assert mock_call.call_count == 3
        seeds = [call.kwargs.get("seed") for call in mock_call.call_args_list]
        assert seeds == [None, None, None]
