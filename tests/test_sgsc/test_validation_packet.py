"""Tests for sgsc.validation_packet — Gate 7 clinician review packet generator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sgsc.e2e_harness import E2EHarnessReport
from sgsc.validation_packet import (
    ClinicianReviewItem,
    ClinicianValidationPacket,
    build_validation_packet,
    compute_packet_metrics,
    serialize_packet,
)

# ------------------------------------------------------------------
# Minimal synthetic harness report fixture
# ------------------------------------------------------------------

_ACCEPTED_ATOMS = [
    {
        "atom_id": f"atom_{i:03d}",
        "source": {
            "guideline_id": "ssc_test",
            "section": "Hour-1",
            "page": "e53",
            "quote": f"Guideline recommendation text {i}.",
            "quote_hash": "",
        },
        "population": {"inclusion": ["sepsis"], "exclusion": []},
        "action": {"canonical_id": f"action_{i}", "action_type": "medication", "terminology": {}},
        "constraint": {"type": "REQUIRED", "activation_event": None, "deadline_minutes": None},
        "sequence": {"before": [], "required_prior": []},
        "evidence": {"system": "GRADE", "recommendation_class": "I", "level": "B"},
        "scenario_hooks": {"boundary_variables": [], "counterfactual_pairs": []},
        "proposed_by": "test_model",
        "agreement_score": 1.0,
        "entailment_status": "entailed",
        "verified_at": None,
    }
    for i in range(20)
]

_CONSTRAINTS = [
    {
        "constraint_type": "REQUIRED",
        "actions": [f"action_{i}"],
        "severity": "HIGH",
        "description": f"Constraint description {i}",
    }
    for i in range(15)
]

_PUBLIC_SCENARIOS = {
    f"scenario_{i:03d}": {
        "patient_state": {"diagnosis": "sepsis", "age": 65 + i},
        "observation": {"lactate": 2.5},
        "description": f"Sepsis patient scenario {i}",
        "mutations": [{"mutation_type": "omit", "target": "antibiotics"}],
    }
    for i in range(30)
}


def _write_json(path: Path, data: object) -> str:
    """Write data as JSON and return path string."""
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


@pytest.fixture()
def synthetic_report(tmp_path: Path) -> E2EHarnessReport:
    """E2EHarnessReport pointing to synthetic fixture files."""
    accepted_p = _write_json(tmp_path / "atoms_accepted.json", _ACCEPTED_ATOMS)
    constraints_p = _write_json(tmp_path / "constraints.json", _CONSTRAINTS)
    public_p = _write_json(tmp_path / "scenarios_public.json", _PUBLIC_SCENARIOS)

    return E2EHarnessReport(
        proposed_atoms_path=_write_json(tmp_path / "atoms_proposed.json", _ACCEPTED_ATOMS),
        accepted_atoms_path=accepted_p,
        rejected_atoms_path=_write_json(tmp_path / "atoms_rejected.json", []),
        review_required_atoms_path=_write_json(tmp_path / "atoms_review.json", []),
        constraints_path=constraints_p,
        seeds_path=_write_json(tmp_path / "seeds.json", {"total_seeds": 5}),
        scenarios_public_path=public_p,
        scenarios_private_path=_write_json(tmp_path / "scenarios_private.json", {}),
        coverage_report_path=_write_json(tmp_path / "coverage.json", {"total_items": 5}),
        leakage_report_path=_write_json(
            tmp_path / "leakage.json", {"passed": True, "leaks": [], "scenarios_scanned": 30}
        ),
    )


# ------------------------------------------------------------------
# ClinicianReviewItem
# ------------------------------------------------------------------


class TestClinicianReviewItem:
    """Unit tests for ClinicianReviewItem dataclass."""

    def test_required_fields_present(self) -> None:
        item = ClinicianReviewItem(
            item_id="atom_0001",
            item_type="atom",
            display_payload={"action_canonical_id": "give_abx"},
            source_excerpt="[ssc_test / Hour-1 p.e53] Administer antibiotics.",
            review_questions=["Is this faithful?"],
        )
        assert item.item_id == "atom_0001"
        assert item.item_type == "atom"
        assert "action_canonical_id" in item.display_payload
        assert item.source_excerpt != ""
        assert len(item.review_questions) == 1


# ------------------------------------------------------------------
# ClinicianValidationPacket
# ------------------------------------------------------------------


class TestClinicianValidationPacket:
    """Unit tests for ClinicianValidationPacket dataclass."""

    def test_defaults(self) -> None:
        pkt = ClinicianValidationPacket()
        assert pkt.items == []
        assert pkt.reviewer_protocol == {}
        assert pkt.adjudication_protocol == {}


# ------------------------------------------------------------------
# build_validation_packet
# ------------------------------------------------------------------


class TestBuildValidationPacket:
    """Tests for build_validation_packet."""

    def test_sample_sizes_within_bucket_bounds(
        self, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt = build_validation_packet(
            synthetic_report, n_atoms=10, n_constraints=10, n_scenarios=10, n_traces=10
        )
        atom_items = [it for it in pkt.items if it.item_type == "atom"]
        constraint_items = [it for it in pkt.items if it.item_type == "constraint"]
        scenario_items = [it for it in pkt.items if it.item_type == "scenario"]
        trace_items = [it for it in pkt.items if it.item_type == "trace"]

        assert len(atom_items) == 10
        assert len(constraint_items) == 10
        assert len(scenario_items) == 10
        assert len(trace_items) == 10

    def test_capped_when_bucket_smaller_than_requested(
        self, synthetic_report: E2EHarnessReport
    ) -> None:
        # Only 20 atoms but request 100 — should be capped at 20
        pkt = build_validation_packet(
            synthetic_report, n_atoms=100, n_constraints=100, n_scenarios=100, n_traces=100
        )
        atom_items = [it for it in pkt.items if it.item_type == "atom"]
        constraint_items = [it for it in pkt.items if it.item_type == "constraint"]
        scenario_items = [it for it in pkt.items if it.item_type == "scenario"]
        trace_items = [it for it in pkt.items if it.item_type == "trace"]

        assert len(atom_items) == 20, "atoms capped at 20 (bucket size)"
        assert len(constraint_items) == 15, "constraints capped at 15 (bucket size)"
        assert len(scenario_items) == 30, "scenarios capped at 30 (bucket size)"
        assert len(trace_items) == 30, "traces capped at 30 (bucket size)"

    def test_all_items_have_required_fields(
        self, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt = build_validation_packet(synthetic_report, n_atoms=5, n_constraints=5, n_scenarios=5, n_traces=5)
        for item in pkt.items:
            assert item.item_id, "item_id must not be empty"
            assert item.item_type in ("atom", "constraint", "scenario", "trace")
            assert isinstance(item.display_payload, dict)
            assert isinstance(item.source_excerpt, str)
            assert isinstance(item.review_questions, list)
            assert len(item.review_questions) >= 1

    def test_reviewer_protocol_fields_present(
        self, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt = build_validation_packet(synthetic_report)
        assert pkt.reviewer_protocol["n_clinicians"] == 3
        assert pkt.reviewer_protocol["guideline_source_blinded"] is False
        assert pkt.reviewer_protocol["sgsc_output_blinded"] is True
        assert "review_minutes_per_item" in pkt.reviewer_protocol

    def test_adjudication_protocol_fields_present(
        self, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt = build_validation_packet(synthetic_report)
        assert "rule" in pkt.adjudication_protocol
        assert "metric" in pkt.adjudication_protocol
        assert "Gwet AC1" in pkt.adjudication_protocol["metric"]

    def test_deterministic_with_same_seed(
        self, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt1 = build_validation_packet(
            synthetic_report, n_atoms=5, n_constraints=5, n_scenarios=5, n_traces=5, seed=99
        )
        pkt2 = build_validation_packet(
            synthetic_report, n_atoms=5, n_constraints=5, n_scenarios=5, n_traces=5, seed=99
        )
        ids1 = [it.item_id for it in pkt1.items]
        ids2 = [it.item_id for it in pkt2.items]
        assert ids1 == ids2, "Same seed must produce identical item order"

    def test_atom_display_payload_is_blinded(
        self, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt = build_validation_packet(synthetic_report, n_atoms=5, n_constraints=0, n_scenarios=0, n_traces=0)
        for item in pkt.items:
            if item.item_type == "atom":
                # No SGSC scores or internal identifiers in payload
                payload_str = json.dumps(item.display_payload)
                assert "entailment_status" not in payload_str
                assert "agreement_score" not in payload_str
                assert "proposed_by" not in payload_str

    def test_atom_review_questions_correct(
        self, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt = build_validation_packet(synthetic_report, n_atoms=1, n_constraints=0, n_scenarios=0, n_traces=0)
        atom_items = [it for it in pkt.items if it.item_type == "atom"]
        assert len(atom_items) == 1
        assert "Is this atom faithful to the source quote?" in atom_items[0].review_questions

    def test_constraint_review_questions_correct(
        self, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt = build_validation_packet(synthetic_report, n_atoms=0, n_constraints=1, n_scenarios=0, n_traces=0)
        cst_items = [it for it in pkt.items if it.item_type == "constraint"]
        assert len(cst_items) == 1
        assert "Does this constraint match guideline intent?" in cst_items[0].review_questions


# ------------------------------------------------------------------
# serialize_packet
# ------------------------------------------------------------------


class TestSerializePacket:
    """Tests for serialize_packet."""

    def test_packet_json_written(
        self, tmp_path: Path, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt = build_validation_packet(synthetic_report, n_atoms=3, n_constraints=3, n_scenarios=3, n_traces=3)
        serialize_packet(pkt, tmp_path / "output")
        assert (tmp_path / "output" / "packet.json").exists()

    def test_csv_written(
        self, tmp_path: Path, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt = build_validation_packet(synthetic_report, n_atoms=3, n_constraints=3, n_scenarios=3, n_traces=3)
        serialize_packet(pkt, tmp_path / "output")
        assert (tmp_path / "output" / "clinician_review_form.csv").exists()

    def test_packet_json_round_trip(
        self, tmp_path: Path, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt = build_validation_packet(synthetic_report, n_atoms=3, n_constraints=3, n_scenarios=3, n_traces=3)
        out_dir = tmp_path / "output"
        serialize_packet(pkt, out_dir)
        loaded = json.loads((out_dir / "packet.json").read_text(encoding="utf-8"))
        assert "items" in loaded
        assert "reviewer_protocol" in loaded
        assert "adjudication_protocol" in loaded
        assert len(loaded["items"]) == len(pkt.items)

    def test_each_item_has_required_json_keys(
        self, tmp_path: Path, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt = build_validation_packet(synthetic_report, n_atoms=2, n_constraints=2, n_scenarios=2, n_traces=2)
        serialize_packet(pkt, tmp_path / "output")
        loaded = json.loads((tmp_path / "output" / "packet.json").read_text(encoding="utf-8"))
        for item in loaded["items"]:
            for key in ("item_id", "item_type", "display_payload", "source_excerpt", "review_questions"):
                assert key in item, f"Missing key '{key}' in serialised item"

    def test_csv_has_header_row(
        self, tmp_path: Path, synthetic_report: E2EHarnessReport
    ) -> None:
        pkt = build_validation_packet(synthetic_report, n_atoms=2, n_constraints=0, n_scenarios=0, n_traces=0)
        serialize_packet(pkt, tmp_path / "output")
        csv_text = (tmp_path / "output" / "clinician_review_form.csv").read_text(encoding="utf-8")
        header = csv_text.splitlines()[0]
        assert "item_id" in header
        assert "question" in header


# ------------------------------------------------------------------
# compute_packet_metrics
# ------------------------------------------------------------------


class TestComputePacketMetrics:
    """Tests for compute_packet_metrics."""

    def test_per_bucket_precision_computed(self) -> None:
        reviews = [
            {"item_id": "atom_0001", "item_type": "atom", "question_index": 0, "clinician_id": "C1", "answer": 1},
            {"item_id": "atom_0001", "item_type": "atom", "question_index": 0, "clinician_id": "C2", "answer": 1},
            {"item_id": "atom_0002", "item_type": "atom", "question_index": 0, "clinician_id": "C1", "answer": 0},
            {"item_id": "cst_0001", "item_type": "constraint", "question_index": 0, "clinician_id": "C1", "answer": 1},
        ]
        metrics = compute_packet_metrics(reviews)
        assert "per_bucket_precision" in metrics
        assert "atom" in metrics["per_bucket_precision"]
        assert "constraint" in metrics["per_bucket_precision"]
        # 2 out of 3 atom answers are 1 -> 0.667
        atom_prec = metrics["per_bucket_precision"]["atom"]
        assert abs(atom_prec - 2 / 3) < 1e-6

    def test_empty_reviews_returns_empty_buckets(self) -> None:
        metrics = compute_packet_metrics([])
        assert metrics["per_bucket_precision"] == {}
        assert metrics["inter_rater_agreement"]["n_paired_items"] == 0

    def test_agreement_keys_present(self) -> None:
        """Agreement reports must include both Cohen's kappa and Gwet AC1."""
        reviews = [
            {"item_id": "a1", "item_type": "atom", "question_index": 0, "clinician_id": "C1", "answer": 1},
            {"item_id": "a1", "item_type": "atom", "question_index": 0, "clinician_id": "C2", "answer": 1},
            {"item_id": "a2", "item_type": "atom", "question_index": 0, "clinician_id": "C1", "answer": 0},
            {"item_id": "a2", "item_type": "atom", "question_index": 0, "clinician_id": "C2", "answer": 0},
        ]
        metrics = compute_packet_metrics(reviews)
        agreement = metrics["inter_rater_agreement"]
        assert "cohen_kappa" in agreement
        assert "gwet_ac1" in agreement
        assert "n_paired_items" in agreement

    def test_perfect_agreement_kappa_one(self) -> None:
        """Two raters agreeing on every item must yield kappa = 1.0."""
        reviews = [
            {"item_id": f"a{i}", "item_type": "atom", "question_index": 0,
             "clinician_id": cid, "answer": ans}
            for i, ans in enumerate([1, 0, 1, 0, 1])
            for cid in ("C1", "C2")
        ]
        metrics = compute_packet_metrics(reviews)
        assert abs(metrics["inter_rater_agreement"]["cohen_kappa"] - 1.0) < 1e-9
        assert abs(metrics["inter_rater_agreement"]["gwet_ac1"] - 1.0) < 1e-9

    def test_chance_agreement_kappa_zero(self) -> None:
        """Anti-correlated raters with balanced marginals yield kappa <= 0."""
        # Rater 1: 1,0,1,0  Rater 2: 0,1,0,1  => 0/4 agreement, p_yes=.5 each
        # po=0, pe=0.5, kappa = (0-.5)/(1-.5) = -1
        pairs = [(1, 0), (0, 1), (1, 0), (0, 1)]
        reviews: list[dict[str, object]] = []
        for i, (a1, a2) in enumerate(pairs):
            reviews.append({"item_id": f"a{i}", "item_type": "atom",
                            "question_index": 0, "clinician_id": "C1", "answer": a1})
            reviews.append({"item_id": f"a{i}", "item_type": "atom",
                            "question_index": 0, "clinician_id": "C2", "answer": a2})
        metrics = compute_packet_metrics(reviews)
        assert metrics["inter_rater_agreement"]["cohen_kappa"] < 0.0

    def test_pure_python_no_scipy_dependency(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Agreement computation must NOT require scipy (pure-Python regression)."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("scipy"):
                raise ImportError("scipy intentionally unavailable")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        reviews = [
            {"item_id": "a1", "item_type": "atom", "question_index": 0,
             "clinician_id": "C1", "answer": 1},
            {"item_id": "a1", "item_type": "atom", "question_index": 0,
             "clinician_id": "C2", "answer": 0},
        ]
        # Must succeed without scipy.
        metrics = compute_packet_metrics(reviews)
        assert "cohen_kappa" in metrics["inter_rater_agreement"]

    def test_krippendorff_alpha_present_and_perfect(self) -> None:
        """Krippendorff alpha must be 1.0 on perfect-agreement input."""
        reviews = [
            {"item_id": f"a{i}", "item_type": "atom", "question_index": 0,
             "clinician_id": cid, "answer": ans}
            for i, ans in enumerate([1, 0, 1, 0, 1, 0])
            for cid in ("C1", "C2")
        ]
        metrics = compute_packet_metrics(reviews)
        agreement = metrics["inter_rater_agreement"]
        assert "krippendorff_alpha" in agreement
        assert abs(agreement["krippendorff_alpha"] - 1.0) < 1e-9

    def test_krippendorff_alpha_negative_on_anticorrelation(self) -> None:
        """Anti-correlated raters with balanced marginals yield alpha < 0."""
        # r1=[1,0,1,0]  r2=[0,1,0,1]  -> all units disagree, p1_pooled = 0.5
        pairs = [(1, 0), (0, 1), (1, 0), (0, 1)]
        reviews: list[dict[str, object]] = []
        for i, (a1, a2) in enumerate(pairs):
            reviews.append({"item_id": f"a{i}", "item_type": "atom",
                            "question_index": 0, "clinician_id": "C1", "answer": a1})
            reviews.append({"item_id": f"a{i}", "item_type": "atom",
                            "question_index": 0, "clinician_id": "C2", "answer": a2})
        metrics = compute_packet_metrics(reviews)
        assert metrics["inter_rater_agreement"]["krippendorff_alpha"] < 0.0

    def test_three_metrics_consistent_on_perfect_agreement(self) -> None:
        """All three agreement metrics must equal 1.0 on perfect agreement."""
        reviews = [
            {"item_id": f"a{i}", "item_type": "atom", "question_index": 0,
             "clinician_id": cid, "answer": ans}
            for i, ans in enumerate([1, 1, 0, 0, 1, 0, 1, 0])
            for cid in ("C1", "C2")
        ]
        a = compute_packet_metrics(reviews)["inter_rater_agreement"]
        for key in ("cohen_kappa", "gwet_ac1", "krippendorff_alpha"):
            assert abs(a[key] - 1.0) < 1e-9, f"{key} = {a[key]} (expected 1.0)"

    def test_metric_label_advertises_all_three(
        self, synthetic_report: E2EHarnessReport
    ) -> None:
        """Adjudication-protocol label must mention all three computed metrics."""
        pkt = build_validation_packet(synthetic_report)
        metric_label = pkt.adjudication_protocol["metric"]
        for token in ("Cohen", "Gwet AC1", "Krippendorff"):
            assert token in metric_label, f"Missing {token!r} in metric label"
