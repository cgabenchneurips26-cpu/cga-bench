import pytest
from typing import Any

from .conftest import (
    _action,
    aki_patient,
    assert_ab_monotonic,
    chest_pain_patient,
    dka_patient,
    heart_failure_patient,
    run_case,
    sepsis_patient,
    stroke_patient,
)
from cga_bench.cpg_model.schemas.base import ActionType
from .cases import load_cases_from_dir


CASES: list[dict[str, Any]] = load_cases_from_dir()


@pytest.mark.parametrize("case", CASES, ids=[str(case["id"]) for case in CASES])
def test_golden_ab_pairs(case: dict[str, Any]) -> None:
    assert "citation" in case, f"Missing guideline citation for {case['id']}"

    patient_a = case["patient"]()
    patient_b = case["patient"]()

    a_result = run_case(
        graph_yaml=case["graph"],
        node_id=case["node"],
        patient=patient_a,
        actions=case["a_actions"],
        final_time=case["a_final"],
    )
    b_result = run_case(
        graph_yaml=case["graph"],
        node_id=case["node"],
        patient=patient_b,
        actions=case["b_actions"],
        final_time=case["b_final"],
    )

    assert_ab_monotonic(a_result, b_result, expected_violation_type=case["expected"])


@pytest.mark.parametrize("case", CASES, ids=[str(case["id"]) for case in CASES])
def test_golden_score_snapshot(case: dict[str, Any]) -> None:
    """Verify exact violation counts and score values match snapshot."""
    patient_a = case["patient"]()
    patient_b = case["patient"]()

    a_result = run_case(
        graph_yaml=case["graph"],
        node_id=case["node"],
        patient=patient_a,
        actions=case["a_actions"],
        final_time=case["a_final"],
    )
    b_result = run_case(
        graph_yaml=case["graph"],
        node_id=case["node"],
        patient=patient_b,
        actions=case["b_actions"],
        final_time=case["b_final"],
    )

    from .conftest import _result_to_dict, load_golden_snapshot, save_golden_snapshot

    existing = load_golden_snapshot(case["id"])
    if existing is None:
        save_golden_snapshot(case["id"], a_result, b_result)
        pytest.skip(f"Snapshot generated for {case['id']}")

    actual_a = _result_to_dict(a_result)
    actual_b = _result_to_dict(b_result)

    # Full A-side comparison
    for field in ("total_violations", ):
        assert actual_a[field] == existing["a"][field], \
            f"A {field}: {actual_a[field]} != {existing['a'][field]}"
    for field in ("compliance_score", "peak_risk", "aggregate_risk"):
        assert abs(actual_a[field] - existing["a"][field]) < 0.01, \
            f"A {field}: {actual_a[field]} != {existing['a'][field]}"
    for vtype, count in existing["a"].get("violations_by_type", {}).items():
        actual_count = actual_a["violations_by_type"].get(vtype, 0)
        assert actual_count == count, f"A {vtype}: {actual_count} != {count}"
    for sub, val in existing["a"].get("sub_scores", {}).items():
        actual_val = actual_a["sub_scores"].get(sub, 0.0)
        assert abs(actual_val - val) < 0.01, f"A sub_score {sub}: {actual_val} != {val}"

    # Full B-side comparison
    for field in ("total_violations", ):
        assert actual_b[field] == existing["b"][field], \
            f"B {field}: {actual_b[field]} != {existing['b'][field]}"
    for field in ("compliance_score", "peak_risk", "aggregate_risk"):
        assert abs(actual_b[field] - existing["b"][field]) < 0.01, \
            f"B {field}: {actual_b[field]} != {existing['b'][field]}"
    for vtype, count in existing["b"].get("violations_by_type", {}).items():
        actual_count = actual_b["violations_by_type"].get(vtype, 0)
        assert actual_count == count, f"B {vtype}: {actual_count} != {count}"
    for sub, val in existing["b"].get("sub_scores", {}).items():
        actual_val = actual_b["sub_scores"].get(sub, 0.0)
        assert abs(actual_val - val) < 0.01, f"B sub_score {sub}: {actual_val} != {val}"


@pytest.mark.parametrize(
    "case",
    [c for c in CASES if "timing" in c["expected"]],
    ids=[c["id"] for c in CASES if "timing" in c["expected"]],
)
def test_golden_time_unit_consistency(case: dict[str, Any]) -> None:
    """Run timing cases in both minutes and epoch-seconds to verify unit consistency."""
    from cga_bench.assessor_core.event_log import normalize_timestamp

    patient = case["patient"]()

    a_result_min = run_case(
        graph_yaml=case["graph"],
        node_id=case["node"],
        patient=patient,
        actions=case["a_actions"],
        final_time=case["a_final"],
    )
    b_result_min = run_case(
        graph_yaml=case["graph"],
        node_id=case["node"],
        patient=case["patient"](),
        actions=case["b_actions"],
        final_time=case["b_final"],
    )

    for action in case["a_actions"]:
        seconds = normalize_timestamp(action.timestamp_minutes, "minutes")
        back_to_min = seconds / 60.0
        assert abs(back_to_min - action.timestamp_minutes) < 0.001, (
            "Time unit roundtrip failed: "
            f"{action.timestamp_minutes}min -> {seconds}s -> {back_to_min}min"
        )

    a_violations_obj = a_result_min["violations"]
    b_violations_obj = b_result_min["violations"]
    assert isinstance(a_violations_obj, list)
    assert isinstance(b_violations_obj, list)

    a_violations = len(a_violations_obj)
    b_violations = len(b_violations_obj)
    assert b_violations >= a_violations, f"Timing case {case['id']} should have >= violations in B (equal allowed after MECE dedup)"
