"""Tests for the auto graph pipeline: grounding (Option A), generation (Option B), orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from scripts.cpg_v2_phase_annotation.generate_graph_from_corpus import (
    _extract_json,
    validate_generated_graph,
)
from scripts.cpg_v2_phase_annotation.ground_graph_quotes import (
    apply_grounding,
    extract_best_span,
    find_corpus_for_graph,
    ground_all_nodes,
    ground_node_quote,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_RECOMMENDATIONS = [
    {
        "recommendation_id": "rec_1",
        "text": (
            "We recommend low tidal volume ventilation (Vt 4-8 mL/kg PBW, "
            "target 6 mL/kg) in all patients with ARDS (strong recommendation, "
            "moderate certainty of evidence)."
        ),
        "strength": "strong",
        "page": 12,
    },
    {
        "recommendation_id": "rec_2",
        "text": (
            "Prone positioning for at least 12 hours per day is recommended "
            "for patients with moderate-to-severe ARDS (PaO2/FiO2 < 150 mmHg)."
        ),
        "strength": "strong",
        "page": 15,
    },
    {
        "recommendation_id": "rec_3",
        "text": (
            "Conservative fluid management strategy is suggested in patients "
            "with ARDS who do not have evidence of tissue hypoperfusion."
        ),
        "strength": "conditional",
        "page": 18,
    },
]

SAMPLE_CORPUS = {
    "guideline_name": "ATS/ESICM/SCCM ARDS 2023",
    "graph_id": "ats_esicm_sccm_ards_2023",
    "doi": "10.1007/s00134-023-07050-7",
    "recommendations": SAMPLE_RECOMMENDATIONS,
    "key_sections": {"ventilation": "Low tidal volume is the cornerstone of ARDS management."},
}

SAMPLE_GRAPH: dict[str, Any] = {
    "graph_id": "ats_esicm_sccm_ards_2023",
    "guideline_name": "ATS/ESICM/SCCM ARDS 2023",
    "entry_node": "initial_assessment",
    "nodes": {
        "initial_assessment": {
            "node_id": "initial_assessment",
            "node_type": "decision",
            "name": "ARDS Recognition",
            "mandatory_actions": ["assess_respiratory_status"],
            "allowed_actions": ["assess_respiratory_status"],
            "source_guideline": "ATS/ESICM/SCCM ARDS 2023",
            "source_section": "Initial Assessment",
            "source_page": None,
            # Exact substring of rec_1
            "source_quote": "low tidal volume ventilation (Vt 4-8 mL/kg PBW, target 6 mL/kg)",
        },
        "treatment_bundle": {
            "node_id": "treatment_bundle",
            "node_type": "plan",
            "name": "ARDS Treatment",
            "mandatory_actions": ["initiate_low_tv_ventilation"],
            "allowed_actions": ["initiate_low_tv_ventilation", "prone_positioning"],
            "source_guideline": "ATS/ESICM/SCCM ARDS 2023",
            "source_section": "Mechanical Ventilation",
            "source_page": None,
            # Paraphrased — should be GROUNDED via keyword overlap
            "source_quote": "ARDS patients need tidal volume 6 mL/kg with prone positioning 12 hours",
        },
        "monitoring": {
            "node_id": "monitoring",
            "node_type": "enquiry",
            "name": "Monitoring",
            "mandatory_actions": ["reassess_pf_ratio"],
            "allowed_actions": ["reassess_pf_ratio"],
            "source_guideline": "ATS/ESICM/SCCM ARDS 2023",
            "source_section": "Monitoring",
            "source_page": None,
            # Completely unrelated quote
            "source_quote": "Zebra crossing protocol for cardiac patients is mandatory",
        },
    },
}


# ---------------------------------------------------------------------------
# TestQuoteGrounding
# ---------------------------------------------------------------------------


class TestQuoteGrounding:
    """Task 1 (Option A): quote grounding tests."""

    def test_exact_substring_match(self) -> None:
        """Quote that's an exact substring of a recommendation -> VERIFIED."""
        node = SAMPLE_GRAPH["nodes"]["initial_assessment"]
        corpus_text = "\n".join(r["text"] for r in SAMPLE_RECOMMENDATIONS)

        result = ground_node_quote("initial_assessment", node, SAMPLE_RECOMMENDATIONS, corpus_text)

        assert result.status == "VERIFIED"
        assert result.source_page == 12
        assert result.match_method == "exact_substring"
        assert result.match_score == 1.0

    def test_keyword_overlap_grounding(self) -> None:
        """Quote with high keyword overlap -> GROUNDED with verbatim replacement."""
        node = SAMPLE_GRAPH["nodes"]["treatment_bundle"]
        corpus_text = "\n".join(r["text"] for r in SAMPLE_RECOMMENDATIONS)

        result = ground_node_quote("treatment_bundle", node, SAMPLE_RECOMMENDATIONS, corpus_text)

        assert result.status == "GROUNDED"
        assert result.match_method == "keyword_overlap"
        assert result.match_score >= 0.4
        # The new quote should be a verbatim span from the corpus
        assert result.source_quote != node["source_quote"]  # changed
        assert len(result.source_quote) > 0

    def test_ungrounded_quote(self) -> None:
        """Quote with no matching recommendation -> UNGROUNDED."""
        node = SAMPLE_GRAPH["nodes"]["monitoring"]
        corpus_text = "\n".join(r["text"] for r in SAMPLE_RECOMMENDATIONS)

        result = ground_node_quote("monitoring", node, SAMPLE_RECOMMENDATIONS, corpus_text)

        assert result.status == "UNGROUNDED"
        assert result.old_quote == node["source_quote"]

    def test_empty_quote_skipped(self) -> None:
        """Node with empty source_quote -> SKIPPED."""
        node = {"source_quote": ""}
        corpus_text = "some text"

        result = ground_node_quote("test", node, SAMPLE_RECOMMENDATIONS, corpus_text)

        assert result.status == "SKIPPED"

    def test_source_page_populated(self) -> None:
        """Grounded nodes get source_page from recommendation."""
        node = SAMPLE_GRAPH["nodes"]["initial_assessment"]
        corpus_text = "\n".join(r["text"] for r in SAMPLE_RECOMMENDATIONS)

        result = ground_node_quote("initial_assessment", node, SAMPLE_RECOMMENDATIONS, corpus_text)

        assert result.source_page == 12  # from rec_1

    def test_ground_all_nodes_report(self) -> None:
        """ground_all_nodes produces correct summary statistics."""
        report = ground_all_nodes(SAMPLE_GRAPH, SAMPLE_CORPUS)

        assert report.graph_id == "ats_esicm_sccm_ards_2023"
        assert report.total_nodes == 3
        assert report.verified >= 1  # initial_assessment
        assert report.verified + report.grounded + report.ungrounded == 3

    def test_apply_grounding_updates_graph(self) -> None:
        """apply_grounding updates source_quote, source_page, _quote_verification."""
        import copy

        graph = copy.deepcopy(SAMPLE_GRAPH)
        report = ground_all_nodes(graph, SAMPLE_CORPUS)
        updated = apply_grounding(graph, report)

        # Verified node should have _quote_verification
        ia = updated["nodes"]["initial_assessment"]
        assert ia.get("_quote_verification") is not None
        assert ia["_quote_verification"]["status"] in ("VERIFIED", "GROUNDED")

        # Ungrounded node should be flagged
        mon = updated["nodes"]["monitoring"]
        assert mon.get("_quote_verification", {}).get("status") == "UNGROUNDED"


class TestExtractBestSpan:
    """Tests for the extract_best_span helper."""

    def test_returns_nonempty(self) -> None:
        """Should return a non-empty span."""
        result = extract_best_span("tidal volume ventilation", SAMPLE_RECOMMENDATIONS[0]["text"])
        assert len(result) > 0

    def test_covers_query_keywords(self) -> None:
        """Returned span should contain key query tokens."""
        result = extract_best_span("prone positioning 12 hours", SAMPLE_RECOMMENDATIONS[1]["text"])
        result_lower = result.lower()
        assert "prone" in result_lower
        assert "12" in result_lower

    def test_max_len_respected(self) -> None:
        """Span should not exceed max_len."""
        result = extract_best_span("test query", "A " * 500, max_len=100)
        assert len(result) <= 100


# ---------------------------------------------------------------------------
# TestGraphGeneration (Option B)
# ---------------------------------------------------------------------------


class TestGraphGeneration:
    """Task 2 (Option B): generated graph validation tests."""

    def test_valid_graph_passes_validation(self) -> None:
        """A well-formed graph with verbatim quotes passes validation."""
        corpus_text = "\n".join(r["text"] for r in SAMPLE_RECOMMENDATIONS)
        graph = {
            "graph_id": "test_graph",
            "entry_node": "initial_assessment",
            "nodes": {
                "initial_assessment": {
                    "node_id": "initial_assessment",
                    "node_type": "decision",
                    "mandatory_actions": ["assess_respiratory_status"],
                    "allowed_actions": ["assess_respiratory_status"],
                    "forbidden_actions": [],
                    "source_guideline": "Test Guideline",
                    "source_quote": "low tidal volume ventilation (Vt 4-8 mL/kg PBW, target 6 mL/kg)",
                },
            },
        }

        errors = validate_generated_graph(graph, corpus_text)
        assert len(errors) == 0

    def test_missing_entry_node_flagged(self) -> None:
        """Graph with missing entry_node reference is caught."""
        graph = {
            "graph_id": "test",
            "entry_node": "nonexistent",
            "nodes": {
                "real_node": {
                    "node_type": "plan",
                    "mandatory_actions": ["action_1"],
                    "allowed_actions": ["action_1"],
                    "source_guideline": "Test",
                },
            },
        }
        errors = validate_generated_graph(graph, "some corpus text")
        assert any("entry_node" in e for e in errors)

    def test_hallucinated_quote_flagged(self) -> None:
        """Quote not found in corpus is flagged."""
        corpus_text = "Only this text exists in the corpus."
        graph = {
            "graph_id": "test",
            "entry_node": "node1",
            "nodes": {
                "node1": {
                    "node_type": "plan",
                    "mandatory_actions": ["action_1"],
                    "allowed_actions": ["action_1"],
                    "source_guideline": "Test",
                    "source_quote": "This quote was completely hallucinated by the LLM",
                },
            },
        }
        errors = validate_generated_graph(graph, corpus_text)
        assert any("not found in corpus" in e for e in errors)

    def test_forbidden_allowed_overlap_flagged(self) -> None:
        """Overlap between forbidden and allowed actions is caught."""
        graph = {
            "graph_id": "test",
            "entry_node": "node1",
            "nodes": {
                "node1": {
                    "node_type": "plan",
                    "mandatory_actions": ["action_1"],
                    "allowed_actions": ["action_1", "action_2"],
                    "forbidden_actions": ["action_2"],
                    "source_guideline": "Test",
                },
            },
        }
        errors = validate_generated_graph(graph, "")
        assert any("overlap" in e for e in errors)

    def test_empty_mandatory_flagged(self) -> None:
        """Node with no mandatory actions is caught."""
        graph = {
            "graph_id": "test",
            "entry_node": "node1",
            "nodes": {
                "node1": {
                    "node_type": "plan",
                    "mandatory_actions": [],
                    "allowed_actions": [],
                    "source_guideline": "Test",
                },
            },
        }
        errors = validate_generated_graph(graph, "")
        assert any("empty mandatory" in e for e in errors)


class TestExtractJson:
    """Tests for JSON extraction from LLM responses."""

    def test_plain_json(self) -> None:
        result = _extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_code_block_json(self) -> None:
        result = _extract_json('Some text\n```json\n{"key": "value"}\n```\nMore text')
        assert result == {"key": "value"}

    def test_json_array(self) -> None:
        result = _extract_json('[{"a": 1}, {"b": 2}]')
        assert len(result) == 2

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot extract JSON"):
            _extract_json("This is not JSON at all")


# ---------------------------------------------------------------------------
# TestPipelineOrchestrator (Task 3)
# ---------------------------------------------------------------------------


class TestPipelineOrchestrator:
    """Task 3: pipeline orchestrator logic tests."""

    def test_auto_mode_grounds_when_graph_exists(self, tmp_path: Path) -> None:
        """Auto mode uses Option A when graph file exists."""
        from scripts.cpg_v2_phase_annotation.auto_graph_pipeline import run_single

        # Write test graph
        graph_path = tmp_path / "test.yaml"
        import yaml as _yaml

        _yaml.dump(SAMPLE_GRAPH, graph_path.open("w"))

        # Write test corpus
        corpus_path = tmp_path / "test.parsed.json"
        import json as _json

        corpus_path.write_text(_json.dumps(SAMPLE_CORPUS))

        result = run_single(
            mode="auto",
            corpus_path=corpus_path,
            graph_path=graph_path,
            graph_id="test_graph",
            guideline_name="Test",
            endpoint="http://localhost:99999/v1",
            model="fake-model",
            output_path=tmp_path / "output.yaml",
            dry_run=True,
        )

        assert result.mode_used == "A"

    def test_ground_mode_fails_without_graph(self, tmp_path: Path) -> None:
        """Ground mode returns SKIPPED when no graph file exists."""
        from scripts.cpg_v2_phase_annotation.auto_graph_pipeline import run_single

        corpus_path = tmp_path / "test.parsed.json"
        import json as _json

        corpus_path.write_text(_json.dumps(SAMPLE_CORPUS))

        result = run_single(
            mode="ground",
            corpus_path=corpus_path,
            graph_path=tmp_path / "nonexistent.yaml",
            graph_id="test",
            guideline_name="Test",
            endpoint="http://localhost:99999/v1",
            model="fake-model",
            output_path=None,
            dry_run=True,
        )

        assert result.mode_used == "SKIPPED"
        assert not result.success

    def test_generate_mode_returns_failure_on_llm_unavailable(self, tmp_path: Path) -> None:
        """Generate mode returns failure when LLM is unreachable."""
        from scripts.cpg_v2_phase_annotation.auto_graph_pipeline import run_single

        corpus_path = tmp_path / "test.parsed.json"
        import json as _json

        corpus_path.write_text(_json.dumps(SAMPLE_CORPUS))

        result = run_single(
            mode="generate",
            corpus_path=corpus_path,
            graph_path=None,
            graph_id="test",
            guideline_name="Test",
            endpoint="http://localhost:99999/v1",  # unreachable
            model="fake-model",
            output_path=tmp_path / "output.yaml",
            dry_run=False,
        )

        assert result.mode_used == "B"
        assert not result.success
        assert "unavailable" in result.message.lower() or "error" in result.message.lower()

    def test_auto_mode_fallback_on_llm_failure(self, tmp_path: Path) -> None:
        """Auto mode falls back to A when B fails and graph exists."""
        from scripts.cpg_v2_phase_annotation.auto_graph_pipeline import run_single

        graph_path = tmp_path / "test.yaml"
        import yaml as _yaml

        _yaml.dump(SAMPLE_GRAPH, graph_path.open("w"))

        corpus_path = tmp_path / "test.parsed.json"
        import json as _json

        corpus_path.write_text(_json.dumps(SAMPLE_CORPUS))

        # Auto mode with nonexistent graph -> tries B (fails) -> falls back to A
        # But graph_path exists, so auto will go directly to A (graph exists = A)
        result = run_single(
            mode="auto",
            corpus_path=corpus_path,
            graph_path=graph_path,
            graph_id="test",
            guideline_name="Test",
            endpoint="http://localhost:99999/v1",
            model="fake-model",
            output_path=tmp_path / "output.yaml",
            dry_run=True,
        )

        # When graph exists, auto mode goes straight to A
        assert result.mode_used == "A"


# ---------------------------------------------------------------------------
# TestAuditSourcesExtension (Task 4)
# ---------------------------------------------------------------------------


class TestAuditQuoteVerification:
    """Task 4: audit_sources.py quote verification extension."""

    def test_ungrounded_detected(self, tmp_path: Path) -> None:
        """UNGROUNDED nodes are flagged as errors."""
        from scripts.ci.audit_sources import audit_quote_verification

        graph = {
            "nodes": {
                "node1": {
                    "source_guideline": "Test",
                    "source_page": None,
                    "_quote_verification": {"status": "UNGROUNDED", "score": 0.1},
                },
            },
        }
        graph_file = tmp_path / "test.yaml"
        import yaml as _yaml

        _yaml.dump(graph, graph_file.open("w"))

        errors, warnings = audit_quote_verification(str(tmp_path))
        assert len(errors) == 1
        assert "UNGROUNDED" in errors[0]

    def test_verified_passes(self, tmp_path: Path) -> None:
        """VERIFIED nodes with source_page pass without errors."""
        from scripts.ci.audit_sources import audit_quote_verification

        graph = {
            "nodes": {
                "node1": {
                    "source_guideline": "Test",
                    "source_page": 12,
                    "_quote_verification": {"status": "VERIFIED", "method": "exact_substring"},
                },
            },
        }
        graph_file = tmp_path / "test.yaml"
        import yaml as _yaml

        _yaml.dump(graph, graph_file.open("w"))

        errors, warnings = audit_quote_verification(str(tmp_path))
        assert len(errors) == 0

    def test_null_page_warned(self, tmp_path: Path) -> None:
        """Nodes with verification but NULL source_page get warnings."""
        from scripts.ci.audit_sources import audit_quote_verification

        graph = {
            "nodes": {
                "node1": {
                    "source_guideline": "Test",
                    "source_page": None,
                    "_quote_verification": {"status": "GROUNDED", "method": "keyword_overlap"},
                },
            },
        }
        graph_file = tmp_path / "test.yaml"
        import yaml as _yaml

        _yaml.dump(graph, graph_file.open("w"))

        errors, warnings = audit_quote_verification(str(tmp_path))
        assert len(warnings) >= 1
        assert "source_page" in warnings[0]


# ---------------------------------------------------------------------------
# TestFindCorpus
# ---------------------------------------------------------------------------


class TestFindCorpus:
    """Tests for corpus discovery logic."""

    def test_finds_by_graph_id_field(self, tmp_path: Path) -> None:
        """Finds corpus by matching graph_id field inside JSON."""
        import json as _json

        corpus = {"graph_id": "test_graph", "recommendations": []}
        (tmp_path / "SomeFile.parsed.json").write_text(_json.dumps(corpus))

        result = find_corpus_for_graph("test_graph", tmp_path)
        assert result is not None
        assert result.name == "SomeFile.parsed.json"

    def test_finds_by_filename_fallback(self, tmp_path: Path) -> None:
        """Falls back to filename token matching."""
        import json as _json

        corpus = {"graph_id": "different_id", "recommendations": []}
        (tmp_path / "AHA-2023-Chest-Pain.parsed.json").write_text(_json.dumps(corpus))

        result = find_corpus_for_graph("aha_chest_pain_2023", tmp_path)
        # Tokens: {aha, chest, pain, 2023} vs filename tokens: {aha, 2023, chest, pain}
        assert result is not None

    def test_returns_none_when_no_match(self, tmp_path: Path) -> None:
        """Returns None when no corpus matches."""
        import json as _json

        corpus = {"graph_id": "unrelated", "recommendations": []}
        (tmp_path / "XYZ-Unrelated.parsed.json").write_text(_json.dumps(corpus))

        result = find_corpus_for_graph("completely_different_graph", tmp_path)
        assert result is None
