"""Tests for X.3: MAB forward-direction TCC re-score."""

from __future__ import annotations

import pytest

from scripts.experiments.exp_crossbench_forward import (
    MAB_INSTANCES_PER_TASK,
    _action_token_hits,
    extract_performed_actions,
    task_id_to_type,
    tcc_verdict,
)


class TestTaskIdToType:
    @pytest.mark.parametrize(
        "tid, expected",
        [
            (0, "task1"),
            (29, "task1"),
            (30, "task2"),
            (59, "task2"),
            (60, "task3"),
            (299, "task10"),
        ],
    )
    def test_boundaries(self, tid: int, expected: str) -> None:
        assert task_id_to_type(tid) == expected

    def test_bucket_size(self) -> None:
        assert MAB_INSTANCES_PER_TASK == 30


class TestExtractPerformedActions:
    def test_patient_get(self) -> None:
        events = [
            {"tool_call": {"method": "GET", "url": "http://fhir/Patient/123"}},
        ]
        acts = extract_performed_actions(events)
        assert "get_patient" in acts
        assert "query_fhir" in acts

    def test_post_creates_marker(self) -> None:
        events = [
            {"tool_call": {"method": "POST", "url": "http://fhir/MedicationRequest"}}
        ]
        acts = extract_performed_actions(events)
        assert "create_resource" in acts
        assert "post_medicationrequest" in acts

    def test_empty_list(self) -> None:
        assert extract_performed_actions([]) == set()

    def test_missing_tool_call_field(self) -> None:
        assert extract_performed_actions([{"event_index": 0}]) == set()


class TestActionTokenHits:
    def test_substring_match(self) -> None:
        assert _action_token_hits("verify_patient_identity", {"post_patient", "query_fhir"}) is False
        # exact substring match after underscore removal
        assert _action_token_hits("get_patient", {"get_patient"}) is True
        # target contained in longer performed token
        assert _action_token_hits("patient", {"get_patient"}) is True
        # non-adjacent tokens do NOT match (no fuzzy word-order matching)
        assert _action_token_hits("order_cbc", {"orders_cbc_now"}) is False

    def test_empty_performed(self) -> None:
        assert _action_token_hits("anything", set()) is False

    def test_empty_target(self) -> None:
        assert _action_token_hits("", {"x"}) is False


class TestTccVerdict:
    def test_empty_mandatory_passes(self) -> None:
        assert tcc_verdict({"anything"}, []) is True

    def test_all_mandatory_hit(self) -> None:
        assert tcc_verdict({"get_patient", "post_observation"}, ["get_patient"]) is True

    def test_missing_one_fails(self) -> None:
        assert tcc_verdict({"get_patient"}, ["get_patient", "verify_identity"]) is False
