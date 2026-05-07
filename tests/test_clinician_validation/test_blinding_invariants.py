"""Blinding invariants for generated clinician-validation scenario data.

These tests guard the IRB-critical separation between the public
``scenario_data.js`` file (served to clinicians in the browser) and the
research-side ``scenario_data_full.json`` file (kept off the web server and
used by ``analyze_validation.py`` for de-blinding).

Run locally:
    PYTHONPATH=. pytest tests/test_clinician_validation/test_blinding_invariants.py -v

If this file fails after editing ``generate_scenario_data.py``, the generator
has regressed on one of the blinding invariants. Do NOT relax the test —
either fix the generator, or if a field genuinely needs to be surfaced to
clinicians, add it to the Korean dictionary / domain map first.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import pytest

VALIDATION_DIR = Path(__file__).resolve().parent.parent.parent / "clinician_validation"
PUBLIC_JS = VALIDATION_DIR / "scenario_data.js"
FULL_JSON = VALIDATION_DIR / "scenario_data_full.json"

# Enum-style scenario_id patterns that must never appear in clinician-visible
# fields. These are the naming conventions used by configs/scenarios/*.yaml.
SCENARIO_ID_PATTERNS = [
    re.compile(r"\b[a-z]+_\d{3}\b"),  # e.g. sepsis_001, rv_trap_004
    re.compile(r"\b[a-z]+_[a-z]+_\d{3}\b"),  # e.g. chest_pain_002
    re.compile(r"\b[a-z]+_trap_\d{3}\b"),  # e.g. rv_trap_001
]


def _parse_public_scenarios() -> list[dict[str, Any]]:
    """Load ``scenario_data.js`` by stripping the ``export const`` wrapper."""
    text = PUBLIC_JS.read_text()
    # Strip leading comments and the export declaration; the remainder is a
    # trailing-semicolon JSON array.
    match = re.search(r"export\s+const\s+SCENARIOS\s*=\s*(\[.*?\]);?\s*$", text, re.DOTALL)
    assert match, f"Could not locate SCENARIOS array in {PUBLIC_JS}"
    return json.loads(match.group(1))


def _load_full_scenarios() -> list[dict[str, Any]]:
    """Load the research-side full data file."""
    with FULL_JSON.open() as handle:
        data = json.load(handle)
    scenarios = data.get("scenarios", [])
    assert scenarios, f"No scenarios found in {FULL_JSON}"
    return scenarios


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def public_scenarios() -> list[dict[str, Any]]:
    return _parse_public_scenarios()


@pytest.fixture(scope="module")
def full_scenarios() -> list[dict[str, Any]]:
    return _load_full_scenarios()


# ---------------------------------------------------------------------------
# Public-side blinding invariants
# ---------------------------------------------------------------------------


def test_public_has_no_scenario_id_key(public_scenarios: list[dict[str, Any]]) -> None:
    """scenario_data.js must never expose the research scenario_id or any
    underscored private variant of it.
    """
    offenders: list[str] = []
    for scenario in public_scenarios:
        if "scenario_id" in scenario:
            offenders.append(f"{scenario.get('id')}: scenario_id leaked")
        if "_scenario_id" in scenario:
            offenders.append(f"{scenario.get('id')}: _scenario_id leaked")
    assert not offenders, "Public scenario_data.js leaks research id: " + ", ".join(offenders)


def test_public_titles_do_not_expose_scenario_id(public_scenarios: list[dict[str, Any]]) -> None:
    """Blinded titles must not match scenario_id enum patterns (e.g. sepsis_001)."""
    offenders: list[tuple[str, str]] = []
    for scenario in public_scenarios:
        title = scenario.get("title", "") or ""
        for pattern in SCENARIO_ID_PATTERNS:
            if pattern.search(title):
                offenders.append((scenario.get("id", "?"), title))
                break
    assert not offenders, "Public titles expose scenario_id enum patterns: " + ", ".join(
        f"{i}={t!r}" for i, t in offenders
    )


def test_public_structured_patient_allergies_translated(public_scenarios: list[dict[str, Any]]) -> None:
    """Allergies/comorbidities surfaced to clinicians must be either in the
    Korean dictionary or humanized English (underscore -> space). Raw
    snake_case enum strings are not allowed.
    """
    offenders: list[tuple[str, str, str]] = []
    for scenario in public_scenarios:
        structured = scenario.get("structured_patient") or {}
        for field in ("allergies", "comorbidities", "contraindications"):
            for term in structured.get(field, []) or []:
                if isinstance(term, str) and "_" in term:
                    offenders.append((scenario.get("id", "?"), field, term))
    assert not offenders, "Clinician-visible terms retain raw snake_case enum: " + ", ".join(
        f"{i}.{f}={t!r}" for i, f, t in offenders[:5]
    )


def test_public_no_qa_debug_keys(public_scenarios: list[dict[str, Any]]) -> None:
    """Private/underscored keys belong in scenario_data_full.json only."""
    offenders: list[str] = []
    for scenario in public_scenarios:
        for key in scenario.keys():
            if key.startswith("_"):
                offenders.append(f"{scenario.get('id')}.{key}")
    assert not offenders, "Private underscored keys leaked to public data: " + ", ".join(offenders[:5])


def test_public_scenario_count(public_scenarios: list[dict[str, Any]]) -> None:
    """Full sampling should yield 63 episodes (60 unique + 3 duplicate attention checks)."""
    assert len(public_scenarios) == 63, f"Expected 63 scenarios, got {len(public_scenarios)}"


# ---------------------------------------------------------------------------
# Research-side de-blinding invariants (full.json)
# ---------------------------------------------------------------------------


def test_full_preserves_scenario_id_for_deblinding(full_scenarios: list[dict[str, Any]]) -> None:
    """Research side needs scenario_id to join exported ratings back to the
    source YAML. analyze_validation.py reads ``s["scenario_id"]`` directly.
    """
    missing = [s.get("id") for s in full_scenarios if not s.get("scenario_id")]
    assert not missing, f"Research file missing scenario_id for: {missing}"


def test_full_no_double_encoded_scenario_id(full_scenarios: list[dict[str, Any]]) -> None:
    """Canonical key is scenario_id, not _scenario_id. analyze_validation.py
    and downstream tooling read the unprefixed form.
    """
    leftovers = [s.get("id") for s in full_scenarios if "_scenario_id" in s]
    assert not leftovers, f"Stale _scenario_id key found in: {leftovers[:5]}"


def test_full_id_to_scenario_id_is_bijective(full_scenarios: list[dict[str, Any]]) -> None:
    """Each SCN-XXX maps to exactly one scenario_id so the research team can
    reliably de-blind exports. Duplicates (attention checks) are allowed to
    share scenario_id but must have distinct SCN-XXX ids.
    """
    ui_ids = [s["id"] for s in full_scenarios]
    assert len(ui_ids) == len(set(ui_ids)), "Duplicate SCN-XXX ids in full.json"
    # Each ui_id -> one scenario_id
    mapping = {s["id"]: s["scenario_id"] for s in full_scenarios}
    assert len(mapping) == len(full_scenarios)


# ---------------------------------------------------------------------------
# Cross-file consistency
# ---------------------------------------------------------------------------


def test_public_and_full_ids_align(
    public_scenarios: list[dict[str, Any]],
    full_scenarios: list[dict[str, Any]],
) -> None:
    """Every SCN-XXX in public must exist in full.json (and vice versa)."""
    public_ids = {s["id"] for s in public_scenarios}
    full_ids = {s["id"] for s in full_scenarios}
    assert public_ids == full_ids, (
        f"id mismatch: public-only={sorted(public_ids - full_ids)[:5]}, full-only={sorted(full_ids - public_ids)[:5]}"
    )


def test_public_and_full_titles_match(
    public_scenarios: list[dict[str, Any]],
    full_scenarios: list[dict[str, Any]],
) -> None:
    """Blinded titles must be byte-identical across the two files — the full
    file is just public + research metadata.
    """
    full_by_id = {s["id"]: s for s in full_scenarios}
    mismatches: list[str] = []
    for p in public_scenarios:
        f = full_by_id.get(p["id"])
        if f is None:
            continue
        if p.get("title") != f.get("title"):
            mismatches.append(f"{p['id']}: public={p.get('title')!r} full={f.get('title')!r}")
    assert not mismatches, "Title divergence between public and full: " + ", ".join(mismatches[:3])
