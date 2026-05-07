"""Unit tests for the MedAgentBench adapter (CRES-3 scaffolding).

No external repo or API is touched here: tests use synthetic records and
an in-test stub scorer.
"""

from __future__ import annotations

import pytest

from cga_bench.external_scorers.medagentbench_adapter import (
    MEDAGENTBENCH_REQUIRED_FIELDS,
    MedAgentBenchAdapter,
    MedAgentBenchRecord,
    bind_native_scorer_from_clone,
)


@pytest.fixture
def synthetic_records() -> list[dict]:
    return [
        {
            "scenario_id": "sepsis_basic",
            "run_index": 0,
            "model": "oss120b",
            "performed_actions": ["order_lactate", "give_antibiotics"],
            "expected_actions": ["order_lactate", "give_antibiotics", "order_culture"],
            "ac_proxy": True,
            "n_actions": 2,
            "n_expected": 3,
        },
        {
            "scenario_id": "stemi_rv",
            "run_index": 1,
            "model": "gemma31b",
            "performed_actions": [],
            "expected_actions": ["ecg_12_lead", "aspirin"],
            "ac_proxy": False,
        },
        {
            # missing scenario_id — should be rejected
            "performed_actions": ["a"],
            "expected_actions": ["b"],
        },
    ]


def test_required_fields_constant_matches_record():
    for k in MEDAGENTBENCH_REQUIRED_FIELDS:
        assert k in (
            "scenario_id",
            "ground_truth_actions",
            "predicted_actions",
        )


def test_record_to_medagentbench_produces_mapped_record(synthetic_records: list[dict]):
    adapter = MedAgentBenchAdapter()
    mab = adapter.record_to_medagentbench(synthetic_records[0])
    assert mab.scenario_id == "sepsis_basic"
    assert mab.predicted_actions == ["order_lactate", "give_antibiotics"]
    assert mab.ground_truth_actions == [
        "order_lactate",
        "give_antibiotics",
        "order_culture",
    ]
    assert mab.trace_metadata["model"] == "oss120b"
    assert mab.trace_metadata["run_index"] == 0


def test_record_to_medagentbench_rejects_missing_scenario_id(
    synthetic_records: list[dict],
):
    adapter = MedAgentBenchAdapter()
    with pytest.raises(ValueError, match="scenario_id"):
        adapter.record_to_medagentbench(synthetic_records[2])


def test_record_to_medagentbench_rejects_non_list_actions():
    adapter = MedAgentBenchAdapter()
    bad = {
        "scenario_id": "x",
        "performed_actions": "not_a_list",
        "expected_actions": [],
    }
    with pytest.raises(ValueError, match="list"):
        adapter.record_to_medagentbench(bad)


def test_to_dict_roundtrip():
    rec = MedAgentBenchRecord(
        scenario_id="x",
        ground_truth_actions=["a"],
        predicted_actions=["b"],
        trace_metadata={"run_index": 1, "model": "m"},
    )
    d = rec.to_dict()
    assert d["scenario_id"] == "x"
    assert d["predicted_actions"] == ["b"]
    assert d["trace_metadata"]["model"] == "m"


def _stub_scorer(rec: MedAgentBenchRecord) -> tuple[bool, float]:
    """Jaccard over action sets, threshold 0.5."""
    p, e = set(rec.predicted_actions), set(rec.ground_truth_actions)
    if not (p | e):
        return (True, 1.0)
    jacc = len(p & e) / len(p | e)
    return (jacc >= 0.5, jacc)


def test_score_batch_with_stub_produces_rows_and_rejections(
    synthetic_records: list[dict],
):
    adapter = MedAgentBenchAdapter(_stub_scorer)
    rows, rejections = adapter.score_batch(synthetic_records)
    assert len(rows) == 2
    assert len(rejections) == 1
    assert "scenario_id" in rejections[0]["reason"].lower()
    # First record: 2/3 Jaccard -> 0.667 >= 0.5 -> pass
    sepsis = next(r for r in rows if r.scenario_id == "sepsis_basic")
    assert sepsis.native_pass is True
    assert 0.6 <= sepsis.native_score <= 0.7
    assert sepsis.proxy_pass is True
    # Second record: empty performed set -> jaccard 0 -> fail
    stemi = next(r for r in rows if r.scenario_id == "stemi_rv")
    assert stemi.native_pass is False
    assert stemi.native_score == 0.0
    assert stemi.proxy_pass is False


def test_default_scorer_raises_not_implemented(synthetic_records: list[dict]):
    """Unwired adapter must surface NotImplementedError via rejection."""
    adapter = MedAgentBenchAdapter()  # uses _unwired_scorer
    rows, rejections = adapter.score_batch(synthetic_records[:1])
    assert rows == []
    assert len(rejections) == 1
    assert "not wired" in rejections[0]["reason"].lower()


def test_score_batch_captures_scorer_exceptions():
    """Arbitrary scorer failures must end up in rejections, not crash the batch."""

    def boom(rec: MedAgentBenchRecord) -> tuple[bool, float]:
        raise RuntimeError("boom")

    adapter = MedAgentBenchAdapter(boom)
    rows, rejections = adapter.score_batch(
        [
            {
                "scenario_id": "x",
                "performed_actions": [],
                "expected_actions": [],
            }
        ]
    )
    assert rows == []
    assert len(rejections) == 1
    assert "RuntimeError" in rejections[0]["reason"]


def test_bind_native_scorer_missing_clone_raises(tmp_path):
    missing = tmp_path / "no_such_dir"
    with pytest.raises(FileNotFoundError):
        bind_native_scorer_from_clone(missing)


def test_bind_native_scorer_present_clone_raises_not_implemented(tmp_path):
    """Defensive: binding is intentionally stubbed for anonymity reasons."""
    clone = tmp_path / "clone"
    clone.mkdir()
    with pytest.raises(NotImplementedError, match="deferred to next session"):
        bind_native_scorer_from_clone(clone)
