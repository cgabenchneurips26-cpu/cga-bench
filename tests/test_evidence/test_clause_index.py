from __future__ import annotations
from pathlib import Path

from cga_bench.semantic_layer.evidence.clause_index import (
    CanonicalClause,
    ClauseIndex,
    build_clause_index_from_cpg,
)


class TestBuildClauseIndex:
    def test_build_from_cpg_graphs(self):
        idx = build_clause_index_from_cpg(str(Path(__file__).resolve().parent.parent.parent / "cpg_model" / "graphs"))
        assert len(idx) > 10

    def test_clause_id_format(self):
        idx = build_clause_index_from_cpg(str(Path(__file__).resolve().parent.parent.parent / "cpg_model" / "graphs"))
        for cid in list(idx.all_clause_ids())[:20]:
            assert cid == cid.upper() or "_" in cid

    def test_search_by_keyword_lactate(self):
        idx = build_clause_index_from_cpg(str(Path(__file__).resolve().parent.parent.parent / "cpg_model" / "graphs"))
        results = idx.search_by_keyword("lactate", top_k=5)
        assert len(results) >= 1
        assert any("LACTATE" in r.clause_id.upper() for r in results)

    def test_get_by_clause_id(self):
        idx = build_clause_index_from_cpg(str(Path(__file__).resolve().parent.parent.parent / "cpg_model" / "graphs"))
        ids = list(idx.all_clause_ids())
        assert len(ids) > 0
        clause = idx.get_by_clause_id(ids[0])
        assert clause is not None
        assert clause.clause_id == ids[0]

    def test_get_nonexistent_returns_none(self):
        idx = ClauseIndex()
        assert idx.get_by_clause_id("NONEXISTENT_ID") is None

    def test_canary_clause(self):
        idx = ClauseIndex()
        canary = CanonicalClause(
            clause_id="CANARY_TEST_12345",
            text="This is a unique canary clause for testing retrieval.",
            heading="Canary Test",
            keywords=["canary", "unique", "test"],
            guideline_id="test_guideline",
            section="test",
            evidence_level="1A",
            recommendation_class="I",
            source_quote="canary source",
            deadline_minutes=None,
        )
        idx.add_clause(canary)
        assert idx.get_by_clause_id("CANARY_TEST_12345") is not None
        results = idx.search_by_keyword("canary unique", top_k=5)
        assert any(r.clause_id == "CANARY_TEST_12345" for r in results)

    def test_all_clause_ids_returns_set(self):
        idx = build_clause_index_from_cpg(str(Path(__file__).resolve().parent.parent.parent / "cpg_model" / "graphs"))
        ids = idx.all_clause_ids()
        assert isinstance(ids, set)
        assert len(ids) == len(idx)
