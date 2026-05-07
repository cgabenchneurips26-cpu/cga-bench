"""Tests for the end-to-end traceability audit (T1-T5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.ci.audit_traceability import (
    _bfs_reachable_actions,
    _build_corpus_text,
    _get_recommendation_ids,
    check_t1_corpus_coverage,
    check_t2_quote_verification,
    check_t3_recommendation_linkage,
    check_t4_action_reachability,
    check_t5_provenance,
)
import yaml

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_corpus() -> dict[str, Any]:
    return {
        "recommendations": [
            {
                "recommendation_id": "rec_1",
                "text": "Administer epinephrine 0.01 mg/kg IM immediately for anaphylaxis",
                "page": 12,
            },
            {
                "recommendation_id": "rec_2",
                "text": "Obtain IV access and start crystalloid fluid resuscitation",
                "page": 14,
            },
        ],
        "key_sections": {
            "monitoring": "Monitor vital signs every 5 minutes including blood pressure and oxygen saturation",
            "disposition": "Observe patient for at least 4 hours for biphasic reaction",
        },
        "tables": [
            {"data": "Epinephrine dosing: 0.3mg for adults, 0.15mg for children under 30kg"},
        ],
    }


@pytest.fixture()
def sample_graph() -> dict[str, Any]:
    return {
        "graph_id": "test_anaphylaxis",
        "guideline_name": "Test Anaphylaxis Guideline",
        "entry_node": "initial_assessment",
        "nodes": {
            "initial_assessment": {
                "node_id": "initial_assessment",
                "node_type": "decision",
                "name": "Initial Assessment",
                "mandatory_actions": ["assess_airway", "give_epinephrine_im"],
                "allowed_actions": ["assess_airway", "give_epinephrine_im", "call_for_help"],
                "forbidden_actions": [],
                "source_guideline": "WAO Anaphylaxis 2020",
                "source_section": "Section 3.1",
                "source_quote": "Administer epinephrine 0.01 mg/kg IM immediately for anaphylaxis",
                "evidence_level": "1A",
                "recommendation_class": "I",
                "next_nodes": ["fluid_resuscitation"],
                "conditional_next": {},
            },
            "fluid_resuscitation": {
                "node_id": "fluid_resuscitation",
                "node_type": "action",
                "name": "Fluid Resuscitation",
                "mandatory_actions": ["start_iv_access", "give_crystalloid"],
                "allowed_actions": ["start_iv_access", "give_crystalloid"],
                "forbidden_actions": [],
                "source_guideline": "WAO Anaphylaxis 2020",
                "source_section": "Section 3.2",
                "source_quote": "Obtain IV access and start crystalloid fluid resuscitation",
                "evidence_level": "1B",
                "recommendation_class": "I",
                "next_nodes": ["monitoring"],
                "conditional_next": {},
            },
            "monitoring": {
                "node_id": "monitoring",
                "node_type": "enquiry",
                "name": "Monitoring",
                "mandatory_actions": ["monitor_vitals"],
                "allowed_actions": ["monitor_vitals", "repeat_epinephrine"],
                "forbidden_actions": [],
                "source_guideline": "WAO Anaphylaxis 2020",
                "source_section": "Section 4",
                "source_quote": "Monitor vital signs every 5 minutes including blood pressure and oxygen saturation",
                "evidence_level": "2C",
                "recommendation_class": "IIa",
                "next_nodes": [],
                "conditional_next": {},
            },
        },
    }


# ---------------------------------------------------------------------------
# T1: Corpus Coverage
# ---------------------------------------------------------------------------


class TestT1CorpusCoverage:
    def test_graph_with_corpus_match(self, tmp_path: Path) -> None:
        corpus_file = tmp_path / "Test-Corpus.parsed.json"
        corpus_file.write_text(json.dumps({"recommendations": []}))

        graphs = [("test_graph", {}, "core")]
        corpus_map = {
            "test_graph": {
                "corpus_file": corpus_file.name,
                "corpus_dir": str(tmp_path),
            }
        }
        # Monkey-patch REPO_ROOT for path resolution
        import scripts.ci.audit_traceability as mod

        orig_root = mod.REPO_ROOT
        mod.REPO_ROOT = Path("/")
        try:
            result = check_t1_corpus_coverage(graphs, corpus_map)
        finally:
            mod.REPO_ROOT = orig_root

        assert result["covered"] == 1
        assert result["missing"] == 0

    def test_graph_without_corpus(self) -> None:
        graphs = [("orphan_graph", {}, "auto")]
        result = check_t1_corpus_coverage(graphs, {})
        assert result["covered"] == 0
        assert result["missing"] == 1
        assert "orphan_graph" in result["missing_graphs"]

    def test_empty_graphs(self) -> None:
        result = check_t1_corpus_coverage([], {})
        assert result["total_graphs"] == 0
        assert result["coverage_rate"] == 0


# ---------------------------------------------------------------------------
# T2: Quote Verification
# ---------------------------------------------------------------------------


class TestT2QuoteVerification:
    def test_verified_exact_match(self, sample_graph: dict, sample_corpus: dict, tmp_path: Path) -> None:
        """Node with verbatim quote from recommendations → VERIFIED."""
        corpus_file = tmp_path / "corpus.parsed.json"
        corpus_file.write_text(json.dumps(sample_corpus))

        import scripts.ci.audit_traceability as mod

        orig_root = mod.REPO_ROOT
        mod.REPO_ROOT = Path("/")
        try:
            graphs = [("test_anaphylaxis", sample_graph, "core")]
            corpus_map = {
                "test_anaphylaxis": {
                    "corpus_file": corpus_file.name,
                    "corpus_dir": str(tmp_path),
                }
            }
            result = check_t2_quote_verification(graphs, corpus_map)
        finally:
            mod.REPO_ROOT = orig_root

        # All 3 nodes have quotes that exist in corpus text
        assert result["totals"]["verified"] >= 2
        assert result["quote_coverage_rate"] > 0.5

    def test_ungrounded_hallucinated_quote(self, sample_corpus: dict, tmp_path: Path) -> None:
        """Node with hallucinated quote → UNGROUNDED."""
        corpus_file = tmp_path / "corpus.parsed.json"
        corpus_file.write_text(json.dumps(sample_corpus))

        graph = {
            "graph_id": "test",
            "nodes": {
                "n1": {
                    "source_quote": "This text absolutely does not appear anywhere in the corpus whatsoever xyzzy",
                }
            },
        }

        import scripts.ci.audit_traceability as mod

        orig_root = mod.REPO_ROOT
        mod.REPO_ROOT = Path("/")
        try:
            graphs = [("test", graph, "core")]
            corpus_map = {
                "test": {
                    "corpus_file": corpus_file.name,
                    "corpus_dir": str(tmp_path),
                }
            }
            result = check_t2_quote_verification(graphs, corpus_map)
        finally:
            mod.REPO_ROOT = orig_root

        assert result["totals"]["ungrounded"] == 1

    def test_grounded_from_key_section(self, tmp_path: Path) -> None:
        """Quote matching key_section text → GROUNDED via keyword overlap."""
        corpus = {
            "recommendations": [],
            "key_sections": {
                "treatment": (
                    "Aggressive fluid resuscitation with crystalloid bolus"
                    " 30ml per kilogram body weight within first hour"
                ),
            },
        }
        corpus_file = tmp_path / "corpus.parsed.json"
        corpus_file.write_text(json.dumps(corpus))

        graph = {
            "graph_id": "test",
            "nodes": {
                "n1": {
                    "source_quote": "crystalloid bolus 30ml per kilogram body weight within first hour",
                }
            },
        }

        import scripts.ci.audit_traceability as mod

        orig_root = mod.REPO_ROOT
        mod.REPO_ROOT = Path("/")
        try:
            graphs = [("test", graph, "core")]
            corpus_map = {
                "test": {
                    "corpus_file": corpus_file.name,
                    "corpus_dir": str(tmp_path),
                }
            }
            result = check_t2_quote_verification(graphs, corpus_map)
        finally:
            mod.REPO_ROOT = orig_root

        # Should be VERIFIED (exact substring in key_section which is part of corpus_full_text)
        assert result["totals"]["verified"] == 1

    def test_no_corpus_counted(self) -> None:
        """Graph without corpus → nodes counted as no_corpus."""
        graph = {
            "graph_id": "orphan",
            "nodes": {"n1": {"source_quote": "some quote"}},
        }
        graphs = [("orphan", graph, "auto")]
        result = check_t2_quote_verification(graphs, {})
        assert result["totals"]["no_corpus"] == 1


# ---------------------------------------------------------------------------
# T3: Recommendation Linkage
# ---------------------------------------------------------------------------


class TestT3RecommendationLinkage:
    def test_valid_linkage(self, sample_corpus: dict, tmp_path: Path) -> None:
        corpus_file = tmp_path / "corpus.parsed.json"
        corpus_file.write_text(json.dumps(sample_corpus))

        graph = {
            "graph_id": "test",
            "nodes": {
                "n1": {"source_recommendation_ids": ["rec_1", "rec_2"]},
            },
        }

        import scripts.ci.audit_traceability as mod

        orig_root = mod.REPO_ROOT
        mod.REPO_ROOT = Path("/")
        try:
            graphs = [("test", graph, "core")]
            corpus_map = {
                "test": {
                    "corpus_file": corpus_file.name,
                    "corpus_dir": str(tmp_path),
                }
            }
            result = check_t3_recommendation_linkage(graphs, corpus_map)
        finally:
            mod.REPO_ROOT = orig_root

        assert result["totals"]["nodes_with_ids"] == 1
        assert result["totals"]["valid_links"] == 1
        assert result["totals"]["broken_links"] == 0

    def test_broken_linkage(self, sample_corpus: dict, tmp_path: Path) -> None:
        corpus_file = tmp_path / "corpus.parsed.json"
        corpus_file.write_text(json.dumps(sample_corpus))

        graph = {
            "graph_id": "test",
            "nodes": {
                "n1": {"source_recommendation_ids": ["rec_1", "rec_999"]},
            },
        }

        import scripts.ci.audit_traceability as mod

        orig_root = mod.REPO_ROOT
        mod.REPO_ROOT = Path("/")
        try:
            graphs = [("test", graph, "core")]
            corpus_map = {
                "test": {
                    "corpus_file": corpus_file.name,
                    "corpus_dir": str(tmp_path),
                }
            }
            result = check_t3_recommendation_linkage(graphs, corpus_map)
        finally:
            mod.REPO_ROOT = orig_root

        assert result["totals"]["broken_links"] == 1

    def test_no_recommendation_ids(self) -> None:
        graph = {"graph_id": "test", "nodes": {"n1": {"mandatory_actions": ["act1"]}}}
        graphs = [("test", graph, "core")]
        result = check_t3_recommendation_linkage(graphs, {})
        assert result["totals"]["nodes_without_ids"] == 1
        assert result["linkage_rate"] == 0.0


# ---------------------------------------------------------------------------
# T4: Action Reachability
# ---------------------------------------------------------------------------


class TestT4ActionReachability:
    def test_reachable_actions(self, sample_graph: dict) -> None:
        """Scenario with all expected_actions reachable → pass."""
        graphs = [("test_anaphylaxis", sample_graph, "core")]
        scenarios = [
            {
                "scenario_id": "test_1",
                "guideline_graph": "test_anaphylaxis",
                "expected_actions": ["assess_airway", "give_epinephrine_im", "give_crystalloid"],
            }
        ]
        result = check_t4_action_reachability(graphs, scenarios)
        assert result["pass"] == 1
        assert result["fail"] == 0

    def test_unreachable_actions(self, sample_graph: dict) -> None:
        """Scenario with actions not in graph → fail."""
        graphs = [("test_anaphylaxis", sample_graph, "core")]
        scenarios = [
            {
                "scenario_id": "test_2",
                "guideline_graph": "test_anaphylaxis",
                "expected_actions": ["give_epinephrine_im", "perform_intubation"],
            }
        ]
        result = check_t4_action_reachability(graphs, scenarios)
        assert result["fail"] == 1
        assert "perform_intubation" in result["failures"][0]["missing_actions"]

    def test_missing_graph_reference(self, sample_graph: dict) -> None:
        graphs = [("test_anaphylaxis", sample_graph, "core")]
        scenarios = [
            {
                "scenario_id": "test_3",
                "guideline_graph": "nonexistent_graph",
                "expected_actions": ["action_1"],
            }
        ]
        result = check_t4_action_reachability(graphs, scenarios)
        assert result["no_graph"] == 1

    def test_bfs_follows_conditional_next(self) -> None:
        graph = {
            "entry_node": "start",
            "nodes": {
                "start": {
                    "mandatory_actions": ["act_a"],
                    "allowed_actions": ["act_a"],
                    "next_nodes": [],
                    "conditional_next": {"state.severe": "severe_branch"},
                },
                "severe_branch": {
                    "mandatory_actions": ["act_b"],
                    "allowed_actions": ["act_b"],
                    "next_nodes": [],
                    "conditional_next": {},
                },
            },
        }
        actions = _bfs_reachable_actions(graph)
        assert "act_a" in actions
        assert "act_b" in actions

    def test_empty_expected_actions_skipped(self, sample_graph: dict) -> None:
        graphs = [("test_anaphylaxis", sample_graph, "core")]
        scenarios = [{"scenario_id": "empty", "guideline_graph": "test_anaphylaxis", "expected_actions": []}]
        result = check_t4_action_reachability(graphs, scenarios)
        assert result["total_scenarios"] == 0  # skipped


# ---------------------------------------------------------------------------
# T5: Provenance Completeness
# ---------------------------------------------------------------------------


class TestT5Provenance:
    def test_full_provenance(self, sample_graph: dict) -> None:
        graphs = [("test", sample_graph, "core")]
        result = check_t5_provenance(graphs)
        assert result["required_complete_rate"] == 1.0
        assert result["field_fill_rates"]["source_guideline"] == 1.0
        assert result["field_fill_rates"]["source_section"] == 1.0

    def test_missing_source_page(self, sample_graph: dict) -> None:
        """Nodes without source_page → low fill rate for that field."""
        graphs = [("test", sample_graph, "core")]
        result = check_t5_provenance(graphs)
        # sample_graph nodes don't have source_page
        assert result["field_fill_rates"]["source_page"] == 0.0

    def test_partial_provenance(self) -> None:
        graph = {
            "graph_id": "partial",
            "nodes": {
                "n1": {
                    "source_guideline": "Test",
                    "source_section": "S1",
                    "source_quote": "A quote",
                    "evidence_level": "1A",
                },
                "n2": {
                    "source_guideline": "Test",
                    # Missing source_section
                    "source_quote": "",
                    "evidence_level": "",
                },
            },
        }
        graphs = [("partial", graph, "core")]
        result = check_t5_provenance(graphs)
        assert result["required_complete_rate"] == 0.5
        assert result["field_fill_rates"]["source_quote"] == 0.5


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_build_corpus_text_includes_all_sources(self, sample_corpus: dict) -> None:
        text = _build_corpus_text(sample_corpus)
        assert "epinephrine" in text.lower()
        assert "vital signs" in text.lower()  # from key_sections
        assert "0.3mg" in text  # from tables

    def test_get_recommendation_ids(self, sample_corpus: dict) -> None:
        ids = _get_recommendation_ids(sample_corpus)
        assert ids == {"rec_1", "rec_2"}

    def test_bfs_empty_graph(self) -> None:
        assert _bfs_reachable_actions({"nodes": {}, "entry_node": "x"}) == set()

    def test_bfs_cycle_handling(self) -> None:
        graph = {
            "entry_node": "a",
            "nodes": {
                "a": {
                    "mandatory_actions": ["act1"],
                    "allowed_actions": ["act1"],
                    "next_nodes": ["b"],
                    "conditional_next": {},
                },
                "b": {
                    "mandatory_actions": ["act2"],
                    "allowed_actions": ["act2"],
                    "next_nodes": ["a"],  # cycle back to a
                    "conditional_next": {},
                },
            },
        }
        actions = _bfs_reachable_actions(graph)
        assert actions == {"act1", "act2"}


# ---------------------------------------------------------------------------
# Integration: run on real data (if available)
# ---------------------------------------------------------------------------


class TestIntegration:
    """Light integration tests against real project data."""

    @pytest.fixture()
    def real_graph_path(self) -> Path | None:
        p = Path(__file__).resolve().parent.parent.parent / "cpg_model" / "graphs" / "ssc_sepsis_hour1_bundle.yaml"
        if p.exists():
            return p
        return None

    @pytest.fixture()
    def real_corpus_map(self) -> dict[str, dict[str, str]]:
        p = Path(__file__).resolve().parent.parent.parent / "data" / "corpus_graph_map.json"
        if p.exists():
            with open(p) as f:
                return json.load(f)
        return {}

    def test_real_sepsis_graph_in_corpus_map(self, real_corpus_map: dict) -> None:
        if not real_corpus_map:
            pytest.skip("corpus_graph_map.json not found")
        assert "ssc_sepsis_hour1_bundle" in real_corpus_map

    def test_real_sepsis_provenance(self, real_graph_path: Path | None) -> None:
        if real_graph_path is None:
            pytest.skip("ssc_sepsis_hour1_bundle.yaml not found")
        data = yaml.safe_load(real_graph_path.read_text())
        graphs = [("ssc_sepsis_hour1_bundle", data, "core")]
        result = check_t5_provenance(graphs)
        assert result["required_complete_rate"] == 1.0
