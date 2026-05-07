"""Gate 7 clinician validation packet generator.

Produces a structured review packet for 3-clinician annotation of SGSC
outputs.  SGSC scores and filenames are blinded; guideline source quotes
are NOT blinded (clinicians must see the evidence they are adjudicating).

Protocol constants:
    - 3 clinicians per item
    - 2-of-3 majority ruling; ties to senior reviewer with audit log
    - Agreement metric: Cohen's kappa + Gwet AC1 (binary, pairwise)

Default item counts (100/100/60/60) are aspirational ceilings; the unit
tests exercise smaller fixture sizes (20/15/30/30) and the build function
caps at the available bucket size.  Agreement values are computed in pure
Python — no scipy / numpy dependency.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
import random
from typing import Any

from sgsc.e2e_harness import E2EHarnessReport

# ------------------------------------------------------------------
# Review questions per item type
# ------------------------------------------------------------------

_ATOM_QUESTIONS: list[str] = [
    "Is this atom faithful to the source quote?",
    "Is action coding correct?",
    "Is constraint type (FORBIDDEN/REQUIRED/...) correct?",
    "Is the timing window correct?",
]

_CONSTRAINT_QUESTIONS: list[str] = [
    "Does this constraint match guideline intent?",
    "Is severity appropriate?",
]

_SCENARIO_QUESTIONS: list[str] = [
    "Is the patient profile clinically plausible?",
    "Are the activated constraints clinically appropriate for this patient?",
]

_TRACE_QUESTIONS: list[str] = [
    "Does the violation verdict match clinical judgment?",
]

_REVIEWER_PROTOCOL: dict[str, Any] = {
    "n_clinicians": 3,
    "guideline_source_blinded": False,
    "sgsc_output_blinded": True,
    "review_minutes_per_item": 5,
}

_ADJUDICATION_PROTOCOL: dict[str, Any] = {
    "rule": "2-of-3 majority; ties resolved by senior reviewer with audit log",
    "metric": "Cohen's kappa + Gwet AC1 + Krippendorff alpha (binary, pairwise)",
}

_ITEM_TYPE_QUESTIONS: dict[str, list[str]] = {
    "atom": _ATOM_QUESTIONS,
    "constraint": _CONSTRAINT_QUESTIONS,
    "scenario": _SCENARIO_QUESTIONS,
    "trace": _TRACE_QUESTIONS,
}


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------


@dataclass
class ClinicianReviewItem:
    """A single item presented to a clinician reviewer.

    Attributes:
        item_id: Unique identifier for this review item.
        item_type: One of 'atom', 'constraint', 'scenario', 'trace'.
        display_payload: Blinded content shown to the reviewer (no SGSC scores
            or file paths).
        source_excerpt: NOT blinded — verbatim guideline quote with section and
            page reference.
        review_questions: Ordered list of yes/no/free-text questions.
    """

    item_id: str
    item_type: str
    display_payload: dict[str, Any]
    source_excerpt: str
    review_questions: list[str]


@dataclass
class ClinicianValidationPacket:
    """Complete clinician validation packet for Gate 7.

    Attributes:
        items: All review items across all buckets.
        reviewer_protocol: Fixed protocol constants for reviewer onboarding.
        adjudication_protocol: Rules for resolving inter-rater disagreements.
    """

    items: list[ClinicianReviewItem] = field(default_factory=list)
    reviewer_protocol: dict[str, Any] = field(default_factory=dict)
    adjudication_protocol: dict[str, Any] = field(default_factory=dict)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _load_json_list(path: str) -> list[dict[str, Any]]:
    """Load a JSON file that contains a list of dicts."""
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    return data if isinstance(data, list) else []


def _sample(items: list[Any], n: int, rng: random.Random) -> list[Any]:
    """Return up to *n* items sampled without replacement."""
    return rng.sample(items, min(n, len(items)))


def _atom_to_review_item(atom: dict[str, Any], item_id: str) -> ClinicianReviewItem:
    """Build a blinded ClinicianReviewItem from an atom dict."""
    source = atom.get("source", {})
    display = {
        "action_canonical_id": atom.get("action", {}).get("canonical_id", ""),
        "action_type": atom.get("action", {}).get("action_type", ""),
        "constraint_type": atom.get("constraint", {}).get("type", ""),
        "deadline_minutes": atom.get("constraint", {}).get("deadline_minutes"),
        "population_inclusion": atom.get("population", {}).get("inclusion", []),
        "population_exclusion": atom.get("population", {}).get("exclusion", []),
    }
    excerpt = (
        f"[{source.get('guideline_id', '')} / {source.get('section', '')} "
        f"p.{source.get('page', 'N/A')}] {source.get('quote', '')}"
    )
    return ClinicianReviewItem(
        item_id=item_id,
        item_type="atom",
        display_payload=display,
        source_excerpt=excerpt,
        review_questions=_ATOM_QUESTIONS,
    )


def _constraint_to_review_item(
    constraint: dict[str, Any], item_id: str
) -> ClinicianReviewItem:
    """Build a blinded ClinicianReviewItem from a constraint dict."""
    display = {
        "constraint_type": constraint.get("constraint_type", ""),
        "actions": constraint.get("actions", []),
        "severity": constraint.get("severity", ""),
    }
    excerpt = constraint.get("description", "")
    return ClinicianReviewItem(
        item_id=item_id,
        item_type="constraint",
        display_payload=display,
        source_excerpt=excerpt,
        review_questions=_CONSTRAINT_QUESTIONS,
    )


def _scenario_to_review_item(
    scenario: dict[str, Any], scenario_id: str, item_id: str
) -> ClinicianReviewItem:
    """Build a blinded ClinicianReviewItem from a public scenario dict."""
    display = {
        "scenario_id": scenario_id,
        "patient_state": scenario.get("patient_state", {}),
        "observation": scenario.get("observation", {}),
    }
    excerpt = scenario.get("description", scenario.get("summary", ""))
    return ClinicianReviewItem(
        item_id=item_id,
        item_type="scenario",
        display_payload=display,
        source_excerpt=excerpt,
        review_questions=_SCENARIO_QUESTIONS,
    )


def _trace_to_review_item(
    scenario: dict[str, Any], scenario_id: str, item_id: str
) -> ClinicianReviewItem:
    """Build a ClinicianReviewItem for trace-verdict review from a scenario."""
    display = {
        "scenario_id": scenario_id,
        "trace_summary": scenario.get("trace_summary", scenario.get("mutations", [])),
    }
    excerpt = scenario.get("description", scenario.get("summary", ""))
    return ClinicianReviewItem(
        item_id=item_id,
        item_type="trace",
        display_payload=display,
        source_excerpt=excerpt,
        review_questions=_TRACE_QUESTIONS,
    )


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def build_validation_packet(
    harness_report: E2EHarnessReport,
    n_atoms: int = 100,
    n_constraints: int = 100,
    n_scenarios: int = 60,
    n_traces: int = 60,
    seed: int = 42,
) -> ClinicianValidationPacket:
    """Build a Gate-7 clinician validation packet from a harness report.

    Deterministically samples items from each bucket (atoms, constraints,
    scenarios, traces) and assembles a blinded review packet.

    Args:
        harness_report: Output from ``run_e2e_harness``.
        n_atoms: Target atom review items (capped at bucket size).
        n_constraints: Target constraint review items (capped at bucket size).
        n_scenarios: Target scenario review items (capped at bucket size).
        n_traces: Target trace review items (same scenarios, different lens).
        seed: Random seed for reproducible sampling.

    Returns:
        A ``ClinicianValidationPacket`` ready for serialisation.
    """
    rng = random.Random(seed)
    items: list[ClinicianReviewItem] = []

    # Atom items (from accepted bucket — these are the verified atoms)
    atom_dicts = _load_json_list(harness_report.accepted_atoms_path)
    for i, atom in enumerate(_sample(atom_dicts, n_atoms, rng)):
        items.append(_atom_to_review_item(atom, f"atom_{i:04d}"))

    # Constraint items
    constraint_dicts = _load_json_list(harness_report.constraints_path)
    for i, cst in enumerate(_sample(constraint_dicts, n_constraints, rng)):
        items.append(_constraint_to_review_item(cst, f"constraint_{i:04d}"))

    # Scenario + trace items (from public scenarios)
    public_scenarios = _load_public_scenarios(harness_report.scenarios_public_path)
    scenario_pairs = _sample(list(public_scenarios.items()), n_scenarios, rng)
    for i, (sid, scenario) in enumerate(scenario_pairs):
        items.append(_scenario_to_review_item(scenario, sid, f"scenario_{i:04d}"))

    trace_pairs = _sample(list(public_scenarios.items()), n_traces, rng)
    for i, (sid, scenario) in enumerate(trace_pairs):
        items.append(_trace_to_review_item(scenario, sid, f"trace_{i:04d}"))

    return ClinicianValidationPacket(
        items=items,
        reviewer_protocol=dict(_REVIEWER_PROTOCOL),
        adjudication_protocol=dict(_ADJUDICATION_PROTOCOL),
    )


def _load_public_scenarios(path: str) -> dict[str, dict[str, Any]]:
    """Load public scenarios JSON (dict of scenario_id -> scenario dict)."""
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


def serialize_packet(
    packet: ClinicianValidationPacket, output_dir: Path
) -> None:
    """Write packet.json and a flat clinician_review_form.csv to output_dir.

    Args:
        packet: The packet to serialise.
        output_dir: Directory in which to write the two output files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Full JSON
    packet_data = {
        "reviewer_protocol": packet.reviewer_protocol,
        "adjudication_protocol": packet.adjudication_protocol,
        "items": [
            {
                "item_id": it.item_id,
                "item_type": it.item_type,
                "display_payload": it.display_payload,
                "source_excerpt": it.source_excerpt,
                "review_questions": it.review_questions,
            }
            for it in packet.items
        ],
    }
    (output_dir / "packet.json").write_text(
        json.dumps(packet_data, indent=2), encoding="utf-8"
    )

    # Flat CSV for survey-tool upload
    csv_path = output_dir / "clinician_review_form.csv"
    _write_review_csv(packet, csv_path)


def _write_review_csv(packet: ClinicianValidationPacket, csv_path: Path) -> None:
    """Write flat CSV with one row per (item, question) pair."""
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["item_id", "item_type", "question_index", "question", "source_excerpt"]
        )
        for item in packet.items:
            for q_idx, question in enumerate(item.review_questions):
                writer.writerow(
                    [
                        item.item_id,
                        item.item_type,
                        q_idx,
                        question,
                        item.source_excerpt[:200],
                    ]
                )


def compute_packet_metrics(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute per-bucket precision and inter-rater agreement from filled reviews.

    Each review dict must contain keys: ``item_id``, ``item_type``,
    ``question_index``, ``clinician_id``, ``answer`` (1=yes, 0=no).

    Args:
        reviews: List of filled-in review dicts from all clinicians.

    Returns:
        Dict with ``per_bucket_precision`` and ``inter_rater_agreement`` keys.
        ``inter_rater_agreement`` contains both ``cohen_kappa`` and
        ``gwet_ac1`` values for the first two raters paired item-wise.

    The implementation is pure-Python (no numpy / scipy required).
    """
    buckets: dict[str, list[int]] = {}
    for r in reviews:
        bucket = r.get("item_type", "unknown")
        answer = r.get("answer", 0)
        buckets.setdefault(bucket, []).append(int(answer))

    precision: dict[str, float] = {
        bkt: sum(answers) / len(answers) if answers else 0.0
        for bkt, answers in buckets.items()
    }

    agreement = _compute_agreement(reviews)

    return {"per_bucket_precision": precision, "inter_rater_agreement": agreement}


def _pair_first_two_raters(
    reviews: list[dict[str, Any]],
) -> tuple[list[int], list[int]]:
    """Group answers by item_id and return aligned (rater_1, rater_2) lists.

    Items with only one rater are skipped — agreement on a single observation
    is undefined.  The order of raters within an item is the insertion order
    in *reviews*, which makes the result deterministic for a given input.
    """
    item_answers: dict[str, list[int]] = {}
    for r in reviews:
        item_answers.setdefault(r["item_id"], []).append(int(r.get("answer", 0)))

    r1: list[int] = []
    r2: list[int] = []
    for answers in item_answers.values():
        if len(answers) < 2:
            continue
        r1.append(answers[0])
        r2.append(answers[1])
    return r1, r2


def _cohen_kappa(r1: list[int], r2: list[int]) -> float:
    """Cohen's kappa for two raters with binary (0/1) labels.

    Formula:
        po = observed agreement
        pe = sum_k P(rater_1 == k) * P(rater_2 == k)
        kappa = (po - pe) / (1 - pe)

    Returns 1.0 for perfect agreement, 0.0 for chance-level, and 0.0 when
    pe == 1 (degenerate case where one or both raters are constant).
    """
    n = len(r1)
    if n == 0:
        return 0.0
    po = sum(1 for a, b in zip(r1, r2) if a == b) / n
    p1_yes = sum(r1) / n
    p2_yes = sum(r2) / n
    pe = p1_yes * p2_yes + (1 - p1_yes) * (1 - p2_yes)
    if abs(1 - pe) < 1e-12:
        return 1.0 if abs(po - 1.0) < 1e-12 else 0.0
    return (po - pe) / (1 - pe)


def _gwet_ac1(r1: list[int], r2: list[int]) -> float:
    """Gwet's AC1 for two raters with binary (0/1) labels.

    Formula (binary case):
        po = observed agreement
        p_bar = mean of P(yes) across raters
        pa = 2 * p_bar * (1 - p_bar)            # chance agreement
        ac1 = (po - pa) / (1 - pa)

    AC1 is more stable than kappa under high-prevalence categories
    (the "kappa paradox") because chance agreement is computed from the
    pooled marginal rather than the product of per-rater marginals.
    """
    n = len(r1)
    if n == 0:
        return 0.0
    po = sum(1 for a, b in zip(r1, r2) if a == b) / n
    p1_yes = sum(r1) / n
    p2_yes = sum(r2) / n
    p_bar = (p1_yes + p2_yes) / 2
    pa = 2 * p_bar * (1 - p_bar)
    if abs(1 - pa) < 1e-12:
        return 1.0 if abs(po - 1.0) < 1e-12 else 0.0
    return (po - pa) / (1 - pa)


def _krippendorff_alpha_binary(r1: list[int], r2: list[int]) -> float:
    """Krippendorff's alpha for binary nominal data with two raters per unit.

    For binary nominal data with exactly two raters per unit, alpha reduces to:

        D_o = (number of disagreeing units) / n_units
        p_1 = pooled prevalence of category 1 across all 2*n ratings
        D_e = 2 * p_1 * (1 - p_1)               # uncorrected expected disagreement
        D_e_c = D_e * total_ratings / (total_ratings - 1)   # small-sample correction
        alpha = 1 - D_o / D_e_c

    Krippendorff's alpha differs from Cohen's kappa in that it computes the
    expected-disagreement baseline from the *pooled* marginal across all raters
    (Scott's-pi-like) rather than the product of per-rater marginals. This makes
    alpha more conservative when raters have asymmetric biases.

    Returns 1.0 for perfect agreement, 0.0 when chance disagreement is zero
    (all-same constant labels) and observed disagreement is also zero, and may
    be negative for systematic disagreement.
    """
    n = len(r1)
    if n == 0:
        return 0.0
    n_disagree = sum(1 for a, b in zip(r1, r2) if a != b)
    d_o = n_disagree / n
    total_ratings = 2 * n
    p1 = (sum(r1) + sum(r2)) / total_ratings
    d_e = 2 * p1 * (1 - p1)
    if abs(d_e) < 1e-12:
        return 1.0 if d_o == 0 else 0.0
    # Small-sample correction (Krippendorff 2018, eq. 4.3)
    d_e_corrected = d_e * total_ratings / (total_ratings - 1)
    return 1 - d_o / d_e_corrected


def _compute_agreement(reviews: list[dict[str, Any]]) -> dict[str, float]:
    """Compute pairwise inter-rater agreement on the first two raters per item.

    Three chance-corrected agreement metrics are returned:

        - cohen_kappa         expected disagreement = product of per-rater marginals
        - gwet_ac1            expected disagreement = pooled prevalence (kappa-paradox-free)
        - krippendorff_alpha  expected disagreement = pooled prevalence with small-sample
                              correction (Scott's-pi-style)

    Returns ``{"cohen_kappa": k, "gwet_ac1": ac1, "krippendorff_alpha": a,
    "n_paired_items": n}``. When fewer than two paired items exist all three
    metrics are 0.0 with ``n_paired_items=0`` and the caller should treat the
    result as insufficient-data rather than a meaningful agreement value.
    """
    r1, r2 = _pair_first_two_raters(reviews)
    n = len(r1)
    if n == 0:
        return {
            "cohen_kappa": 0.0,
            "gwet_ac1": 0.0,
            "krippendorff_alpha": 0.0,
            "n_paired_items": 0,
        }
    return {
        "cohen_kappa": _cohen_kappa(r1, r2),
        "gwet_ac1": _gwet_ac1(r1, r2),
        "krippendorff_alpha": _krippendorff_alpha_binary(r1, r2),
        "n_paired_items": float(n),
    }
