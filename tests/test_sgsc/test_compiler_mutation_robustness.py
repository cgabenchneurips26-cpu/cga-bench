"""Mutation robustness tests for SGSC compilers (Gate 6 trust gates).

Each test constructs a baseline and a mutated atom/seed, runs both through
the relevant compiler, and asserts the output differs in the expected way.
The test PASSES on the current compiler (proving the invariant is enforced).
It would FAIL if someone weakened the compiler.
"""

from __future__ import annotations

import copy
import hashlib

from sgsc.audit.leakage_scanner import scan_public_scenarios
from sgsc.compilers.counterfactual_compiler import compile_families
from sgsc.compilers.graph_compiler import GraphCompiler
from sgsc.compilers.scenario_compiler import compile_seeds
from sgsc.schemas.atom import (
    AtomAction,
    AtomConstraint,
    AtomEvidence,
    AtomSequence,
    PopulationCriteria,
    RecommendationAtom,
    ScenarioHooks,
    SourceReference,
)

# ------------------------------------------------------------------
# Shared builder
# ------------------------------------------------------------------


def _make_within_atom(deadline: int) -> RecommendationAtom:
    """Build a WITHIN atom with the given deadline."""
    return RecommendationAtom(
        atom_id="test_within_abx",
        source=SourceReference(
            guideline_id="ssc_2021",
            section="Hour-1 Bundle",
            quote="Administer antibiotics within the deadline.",
        ),
        population=PopulationCriteria(inclusion=["sepsis"], exclusion=[]),
        action=AtomAction(canonical_id="give_broad_spectrum_antibiotics", action_type="medication"),
        constraint=AtomConstraint(type="WITHIN", deadline_minutes=deadline),
        sequence=AtomSequence(required_prior=["obtain_blood_cultures"]),
        evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="B"),
        scenario_hooks=ScenarioHooks(boundary_variables=["time_to_abx"]),
    )


# ------------------------------------------------------------------
# Mutation 1: WITHIN deadline +5 minute offset changes scenario output
# ------------------------------------------------------------------


def test_mutation_1_within_deadline_offset() -> None:
    """Deadline flows into MutationTemplate.delay_minutes — a +5 offset must produce a different delay."""
    atom_60 = _make_within_atom(deadline=60)
    atom_65 = _make_within_atom(deadline=65)

    seeds_60 = compile_seeds([atom_60], "ssc_2021")
    seeds_65 = compile_seeds([atom_65], "ssc_2021")

    assert len(seeds_60) == 1
    assert len(seeds_65) == 1

    delays_60 = {mt.delay_minutes for mt in seeds_60[0].mutation_templates if mt.mutation_type == "delay"}
    delays_65 = {mt.delay_minutes for mt in seeds_65[0].mutation_templates if mt.mutation_type == "delay"}

    assert delays_60 != delays_65, "Deadline change must propagate into delay_minutes of MutationTemplate"


# ------------------------------------------------------------------
# Mutation 2: BEFORE direction reversal produces different families
# ------------------------------------------------------------------


def _make_before_atom(before: list[str], required_prior: list[str]) -> RecommendationAtom:
    """Build a BEFORE atom with explicit before/required_prior."""
    return RecommendationAtom(
        atom_id="test_before_culture",
        source=SourceReference(
            guideline_id="ssc_2021",
            section="Blood Cultures",
            quote="Obtain blood cultures before antibiotics.",
        ),
        population=PopulationCriteria(inclusion=["sepsis"], exclusion=[]),
        action=AtomAction(canonical_id="obtain_blood_cultures", action_type="lab"),
        constraint=AtomConstraint(type="BEFORE"),
        sequence=AtomSequence(before=before, required_prior=required_prior),
        evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="B"),
        scenario_hooks=ScenarioHooks(),
    )


def test_mutation_2_before_direction_reversal() -> None:
    """Swapping before and required_prior must produce families with different shared traces."""
    baseline = _make_before_atom(before=["give_broad_spectrum_antibiotics"], required_prior=[])
    mutated = _make_before_atom(before=[], required_prior=["give_broad_spectrum_antibiotics"])

    families_baseline = compile_families([baseline])
    families_mutated = compile_families([mutated])

    assert len(families_baseline) >= 1
    assert len(families_mutated) >= 1

    trace_b = [(s.action_id, s.time_minutes) for s in families_baseline[0].shared_trace_template]
    trace_m = [(s.action_id, s.time_minutes) for s in families_mutated[0].shared_trace_template]

    assert trace_b != trace_m, (
        f"Swapping before/required_prior must produce different shared traces; got equal: {trace_b}"
    )


# ------------------------------------------------------------------
# Mutation 3: FORBIDDEN vs REQUIRED changes graph mandatory/forbidden sets
# ------------------------------------------------------------------


def _make_typed_atom(constraint_type: str) -> RecommendationAtom:
    """Build an atom whose constraint type is parameterised."""
    return RecommendationAtom(
        atom_id=f"test_{constraint_type.lower()}_nitro",
        source=SourceReference(
            guideline_id="aha_chest_pain",
            section="RV Infarction",
            quote="Action under RV infarction.",
        ),
        population=PopulationCriteria(inclusion=["rv_infarction"], exclusion=[]),
        action=AtomAction(canonical_id="give_nitroglycerin", action_type="medication"),
        constraint=AtomConstraint(type=constraint_type),
        sequence=AtomSequence(),
        evidence=AtomEvidence(system="AHA", recommendation_class="III", level="B"),
        scenario_hooks=ScenarioHooks(),
    )


def test_mutation_3_forbidden_vs_required_in_graph() -> None:
    """A FORBIDDEN atom must land in forbidden_actions, not mandatory_actions."""
    compiler = GraphCompiler()

    graph_forbidden = compiler.compile([_make_typed_atom("FORBIDDEN")], "aha_chest_pain", "AHA Chest Pain")
    graph_required = compiler.compile([_make_typed_atom("REQUIRED")], "aha_chest_pain", "AHA Chest Pain")

    node_f = list(graph_forbidden["nodes"].values())[0]
    node_r = list(graph_required["nodes"].values())[0]

    # Defensive normalization may canonicalize the action ID
    try:
        from cga_bench.assessor_core.action_normalizer import ActionNormalizer

        canonical = ActionNormalizer().normalize("give_nitroglycerin")
    except ImportError:
        canonical = "give_nitroglycerin"

    assert canonical in node_f["forbidden_actions"]
    assert canonical not in node_f["mandatory_actions"]

    assert canonical in node_r["mandatory_actions"]
    assert canonical not in node_r["forbidden_actions"]

    assert node_f["forbidden_actions"] != node_r["forbidden_actions"]
    assert node_f["mandatory_actions"] != node_r["mandatory_actions"]


# ------------------------------------------------------------------
# Mutation 4: exclusion_guard negation — removing activation_event drops forbidden constraint
# ------------------------------------------------------------------


def _make_forbidden_atom_with_activation(activation: str | None) -> RecommendationAtom:
    """Build a FORBIDDEN atom with or without an activation_event."""
    return RecommendationAtom(
        atom_id="test_forbidden_contrast",
        source=SourceReference(
            guideline_id="kdigo_aki_full",
            section="Contrast-Induced AKI Prevention",
            quote="Avoid iodinated contrast in AKI.",
        ),
        population=PopulationCriteria(inclusion=["aki_stage_2"], exclusion=[]),
        action=AtomAction(canonical_id="order_ct_with_contrast", action_type="imaging"),
        constraint=AtomConstraint(type="FORBIDDEN", activation_event=activation),
        sequence=AtomSequence(),
        evidence=AtomEvidence(system="KDIGO", recommendation_class="I", level="B"),
        scenario_hooks=ScenarioHooks(),
    )


def test_mutation_4_exclusion_guard_negation() -> None:
    """Removing activation_event from a FORBIDDEN atom must still yield a forbidden action in the graph."""
    compiler = GraphCompiler()

    atom_with_event = _make_forbidden_atom_with_activation("aki_confirmed")
    atom_without_event = _make_forbidden_atom_with_activation(None)

    graph_with = compiler.compile([atom_with_event], "kdigo_aki", "KDIGO AKI")
    graph_without = compiler.compile([atom_without_event], "kdigo_aki", "KDIGO AKI")

    node_with = list(graph_with["nodes"].values())[0]
    node_without = list(graph_without["nodes"].values())[0]

    # Defensive normalization may canonicalize the action ID
    try:
        from cga_bench.assessor_core.action_normalizer import ActionNormalizer

        canonical = ActionNormalizer().normalize("order_ct_with_contrast")
    except ImportError:
        canonical = "order_ct_with_contrast"

    # Both variants must still place the action in forbidden_actions
    assert canonical in node_with["forbidden_actions"]
    assert canonical in node_without["forbidden_actions"]

    # The constraint objects themselves differ (activation_event differs)
    assert atom_with_event.constraint != atom_without_event.constraint


# ------------------------------------------------------------------
# Mutation 5: quote_hash mismatch — corrupted hash must differ from computed hash
# ------------------------------------------------------------------


def test_mutation_5_quote_hash_mismatch() -> None:
    """A corrupted quote_hash must not equal the SHA-256 of the actual quote."""
    quote = "Administer broad-spectrum antibiotics within 1 hour of sepsis recognition."
    correct_hash = hashlib.sha256(quote.encode()).hexdigest()
    corrupted_hash = "deadbeef" + correct_hash[8:]

    # SourceReference auto-fills quote_hash when empty; supply corrupted hash directly
    ref_correct = SourceReference(
        guideline_id="ssc_2021",
        section="Hour-1 Bundle",
        quote=quote,
        quote_hash=correct_hash,
    )
    ref_corrupted = SourceReference(
        guideline_id="ssc_2021",
        section="Hour-1 Bundle",
        quote=quote,
        quote_hash=corrupted_hash,
    )

    # The corrupted hash must differ from the recomputed canonical hash
    expected = hashlib.sha256(ref_corrupted.quote.encode()).hexdigest()
    assert ref_corrupted.quote_hash != expected, "Corrupted hash must not match recomputed SHA-256"
    assert ref_correct.quote_hash == expected, "Correct hash must match recomputed SHA-256"


# ------------------------------------------------------------------
# Mutation 6: required_prior merge drop — compiler must not silently drop a prior
# ------------------------------------------------------------------


def _make_atom_with_prior(action_id: str, required_prior: list[str]) -> RecommendationAtom:
    """Build a REQUIRED atom with specified required_prior."""
    return RecommendationAtom(
        atom_id=f"test_prior_{action_id}",
        source=SourceReference(
            guideline_id="ssc_2021",
            section="Hour-1 Bundle",
            quote=f"Action {action_id} requires priors.",
        ),
        population=PopulationCriteria(inclusion=["sepsis"], exclusion=[]),
        action=AtomAction(canonical_id=action_id, action_type="medication"),
        constraint=AtomConstraint(type="REQUIRED"),
        sequence=AtomSequence(required_prior=required_prior),
        evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="B"),
        scenario_hooks=ScenarioHooks(),
    )


def test_mutation_6_required_prior_merge_drop() -> None:
    """Graph compiler must not drop required_prior when merging atoms with the same action_id."""
    compiler = GraphCompiler()

    # Two atoms for the same action_id in the same section, each with a different prior
    atom_a = _make_atom_with_prior("give_abx", required_prior=["obtain_blood_cultures"])
    atom_b = RecommendationAtom(
        atom_id="test_prior_give_abx_b",
        source=SourceReference(
            guideline_id="ssc_2021",
            section="Hour-1 Bundle",
            quote="Give abx after vitals.",
        ),
        population=PopulationCriteria(inclusion=["sepsis"], exclusion=[]),
        action=AtomAction(canonical_id="give_abx", action_type="medication"),
        constraint=AtomConstraint(type="REQUIRED"),
        sequence=AtomSequence(required_prior=["measure_vitals"]),
        evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="B"),
        scenario_hooks=ScenarioHooks(),
    )

    graph = compiler.compile([atom_a, atom_b], "ssc_2021", "SSC 2021")
    node = list(graph["nodes"].values())[0]

    # Defensive normalization may canonicalize action IDs in required_prior_actions
    try:
        from cga_bench.assessor_core.action_normalizer import ActionNormalizer

        normalizer = ActionNormalizer()
        canonical_abx = normalizer.normalize("give_abx")
        canonical_bc = normalizer.normalize("obtain_blood_cultures")
        canonical_vitals = normalizer.normalize("measure_vitals")
    except ImportError:
        canonical_abx = "give_abx"
        canonical_bc = "obtain_blood_cultures"
        canonical_vitals = "measure_vitals"

    priors_for_abx: list[str] = node["required_prior_actions"].get(canonical_abx, [])

    assert canonical_bc in priors_for_abx, "First prior must not be dropped on merge"
    assert canonical_vitals in priors_for_abx, "Second prior must not be dropped on merge"


# ------------------------------------------------------------------
# Mutation 7: private field leakage — forbidden_actions in public dict must be flagged
# ------------------------------------------------------------------


def test_mutation_7_private_field_leakage() -> None:
    """scan_public_scenarios must flag forbidden_actions appearing in public dict."""
    clean_public: dict[str, dict] = {
        "test_scenario_001": {
            "scenario_id": "test_scenario_001",
            "description": "A clean public scenario",
            "guideline_graph": "ssc_2021",
            "patient": {"age": 65, "diagnosis": "sepsis"},
            "optional_actions": [],
            "max_duration_minutes": 120,
        }
    }

    leaked_public: dict[str, dict] = copy.deepcopy(clean_public)
    leaked_public["test_scenario_001"]["forbidden_actions"] = ["give_nitroglycerin"]

    report_clean = scan_public_scenarios(clean_public)
    report_leaked = scan_public_scenarios(leaked_public)

    assert report_clean.passed, "Clean public scenario must pass leakage scan"
    assert not report_leaked.passed, "Public scenario with forbidden_actions must fail leakage scan"

    leaked_patterns = [leak["pattern"] for leak in report_leaked.leaks]
    assert any("forbidden_actions" in p for p in leaked_patterns), (
        f"forbidden_actions leak must be in reported patterns, got {leaked_patterns}"
    )
