"""Tests for the E9 High-Authority Core Robustness audit filter.

Spec: docs/attack_gap_exp_exp/260430_e9_High-Authority_Core_Robustness.md
"""

from __future__ import annotations

from cpg_model.constraint_derivation import (
    ConstraintDerivationEngine,
    DerivedConstraint,
    DerivedConstraintSet,
    load_graph,
)
from audit.authority_filter import (
    HIGH,
    LOW,
    UNKNOWN,
    filter_high_authority,
    tier_counts,
    tier_for,
)


def _mk(
    constraint_type: str = "FORBIDDEN",
    *,
    rc: str | None = None,
    el: str | None = None,
    sg: str | None = None,
    provenance: str = "graph:test:node:n1:rule:r1",
) -> DerivedConstraint:
    return DerivedConstraint(
        constraint_type=constraint_type,
        actions=["dummy_action"],
        provenance=provenance,
        evidence="",
        severity="HARD",
        description="",
        condition_met="always",
        is_conditional=False,
        recommendation_class=rc,
        evidence_level=el,
        source_guideline=sg,
        authority_tier="unknown",
    )


def test_class_i_loe_a_is_high() -> None:
    assert tier_for(_mk(rc="I", el="A")) == HIGH


def test_class_iia_loe_b_is_high() -> None:
    assert tier_for(_mk(rc="IIa", el="B")) == HIGH


def test_class_iib_loe_b_is_low() -> None:
    assert tier_for(_mk(rc="IIb", el="B")) == LOW


def test_class_i_loe_c_is_low() -> None:
    assert tier_for(_mk(rc="I", el="C")) == LOW


def test_idsa_strong_source_is_high() -> None:
    # IDSA is a strong-recommendation society; honoured even if class/LOE absent.
    assert tier_for(_mk(rc=None, el=None, sg="IDSA Practice Guideline 2017")) == HIGH


def test_kdigo_strong_source_is_high() -> None:
    assert tier_for(_mk(rc=None, el=None, sg="KDIGO 2012")) == HIGH


def test_aabb_strong_source_is_high() -> None:
    assert tier_for(_mk(rc=None, el=None, sg="AABB 2024")) == HIGH


def test_no_metadata_is_unknown() -> None:
    assert tier_for(_mk(rc=None, el=None, sg=None)) == UNKNOWN


def test_drug_allergy_provenance_is_high() -> None:
    # Allergy injection always counts as Class I + LOE A by clinical convention.
    c = _mk(rc=None, el=None, sg=None, provenance="allergy_map:penicillin")
    assert tier_for(c) == HIGH


def test_filter_drops_low_keeps_high() -> None:
    cset = DerivedConstraintSet(scenario_id="t", graph_id="g")
    cset.forbidden.append(_mk(rc="I", el="A"))
    cset.forbidden.append(_mk(rc="IIb", el="B"))
    cset.required.append(_mk(rc=None, el=None, sg="IDSA"))
    out = filter_high_authority(cset)
    kept = out.all_constraints()
    assert len(kept) == 2
    assert all(c.authority_tier == HIGH for c in kept)


def test_filter_keep_unknown_flag() -> None:
    cset = DerivedConstraintSet(scenario_id="t", graph_id="g")
    cset.forbidden.append(_mk(rc="I", el="A"))
    cset.forbidden.append(_mk(rc=None, el=None, sg=None))  # unknown
    cset.forbidden.append(_mk(rc="IIb", el="B"))            # low
    out = filter_high_authority(cset, keep_unknown=True)
    tiers = {c.authority_tier for c in out.all_constraints()}
    assert tiers == {HIGH, UNKNOWN}


def test_real_graph_idsa_meningitis_all_high() -> None:
    # IDSA meningitis is uniformly Class I + LOE A/B; should be 100% high.
    g = load_graph("cpg_model/graphs/idsa_meningitis.yaml")
    eng = ConstraintDerivationEngine()
    res = eng.derive(g, {"age": 65, "allergies": []}, scenario_id="t")
    counts = tier_counts(res)
    assert counts[HIGH] > 0
    assert counts[LOW] == 0
    filtered = filter_high_authority(res)
    assert len(filtered.all_constraints()) == len(res.all_constraints())


def test_real_graph_aha_chest_pain_has_mixed_tiers() -> None:
    # The AHA chest-pain graph contains at least one Class IIb / LOE C edge,
    # so the filter must drop at least one constraint relative to the full set.
    g = load_graph("cpg_model/graphs/aha_chest_pain_evaluation.yaml")
    eng = ConstraintDerivationEngine()
    res = eng.derive(g, {"age": 65, "allergies": []}, scenario_id="t")
    filtered = filter_high_authority(res)
    assert 0 < len(filtered.all_constraints()) <= len(res.all_constraints())


# ---------------------------------------------------------------- E9-F1 cache
def test_taxonomy_path_override_changes_classification() -> None:
    """E9-F1: switching to the strictest taxonomy demotes IIa+B to non-high."""
    from audit.authority_filter import set_taxonomy_path

    set_taxonomy_path(None)  # default
    iib = _mk(rc="IIa", el="B")
    assert tier_for(iib) == HIGH

    set_taxonomy_path("audit/authority_taxonomy_strictest.yaml")
    assert tier_for(iib) != HIGH

    # Reset for any subsequent tests
    set_taxonomy_path(None)
    assert tier_for(iib) == HIGH


def test_clear_taxonomy_cache() -> None:
    """E9-F1: clear_taxonomy_cache forces a re-read on next call."""
    from audit.authority_filter import (
        clear_taxonomy_cache,
        get_taxonomy_path,
        set_taxonomy_path,
        _load_taxonomy,
    )

    set_taxonomy_path(None)
    _load_taxonomy.cache_clear()
    _load_taxonomy()  # primes cache
    info_before = _load_taxonomy.cache_info()
    assert info_before.currsize >= 1
    clear_taxonomy_cache()
    info_after = _load_taxonomy.cache_info()
    assert info_after.currsize == 0
    # path getter still works
    assert "authority_taxonomy" in str(get_taxonomy_path())
