"""Deterministic scenario compiler: atoms -> ScenarioSeeds -> scenario YAML.

Generates ``ScenarioSeed`` instances from atoms, then converts them to
scenario YAML entries compatible with ``ScenarioLoader.load_all_scenarios()``.

Track-4 (Option D structural enrichment) clusters atoms by source section so
each emitted seed represents a multi-action scenario.  Graph forbidden_actions
are aggregated across nodes and injected into the resulting scenario YAML.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sgsc.schemas.atom import RecommendationAtom

logger = logging.getLogger(__name__)
from sgsc.schemas.seed import (
    BoundarySpec,
    MutationTemplate,
    PrivateFields,
    ScenarioSeed,
)

# ------------------------------------------------------------------
# Track-4 cluster sizing
# ------------------------------------------------------------------

CLUSTER_MIN: int = 2
CLUSTER_MAX: int = 8
FORBIDDEN_ACTIONS_CAP: int = 15

# ------------------------------------------------------------------
# Default boundary values for common clinical variables
# ------------------------------------------------------------------

_DEFAULT_BOUNDARIES: dict[str, list[float | int]] = {
    "lactate": [1.9, 2.0, 2.1],
    "creatinine": [1.4, 1.5, 1.6],
    "inr": [1.6, 1.7, 1.8],
    "gfr": [29, 30, 31],
    "map_mmhg": [64, 65, 66],
    "heart_rate": [99, 100, 101],
    "temperature": [37.9, 38.0, 38.1],
    "oxygen_saturation": [93, 94, 95],
    "troponin": [0.03, 0.04, 0.05],
    "potassium": [5.4, 5.5, 5.6],
    "glucose": [249, 250, 251],
    "ph": [7.29, 7.30, 7.31],
    "pao2_fio2": [99, 100, 101],
    "time_to_abx": [55, 60, 65],
    "time_since_last_known_well": [265, 270, 275],
}


# ------------------------------------------------------------------
# Seed generation
# ------------------------------------------------------------------


def _make_mutation_templates(atom: RecommendationAtom) -> list[MutationTemplate]:
    """Generate mutation templates from an atom's constraint type."""
    templates: list[MutationTemplate] = []
    action_id = atom.action.canonical_id

    if atom.constraint.type in ("REQUIRED", "WITHIN"):
        templates.append(
            MutationTemplate(
                mutation_id=f"omit_{action_id}",
                mutation_type="omit",
                target_action=action_id,
                description=f"Omit mandatory action {action_id}",
            )
        )

    if atom.constraint.type == "WITHIN" and atom.constraint.deadline_minutes:
        delay_min = atom.constraint.deadline_minutes + 35
        templates.append(
            MutationTemplate(
                mutation_id=f"delay_{action_id}_{delay_min}min",
                mutation_type="delay",
                target_action=action_id,
                description=f"Delay {action_id} to {delay_min} minutes",
                delay_minutes=delay_min,
            )
        )

    if atom.constraint.type == "BEFORE" and atom.sequence.required_prior:
        templates.append(
            MutationTemplate(
                mutation_id=f"sequence_break_{action_id}",
                mutation_type="sequence_break",
                target_action=action_id,
                description=f"Perform {action_id} before its required priors",
            )
        )

    return templates


def _section_to_slug(section: str) -> str:
    """Convert a guideline section heading to a snake_case identifier."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", section).lower().split()
    return "_".join(cleaned[:5]) or "section"


def _cluster_atoms_for_multi_action(
    atoms: list[RecommendationAtom],
    *,
    cluster_max: int = CLUSTER_MAX,
) -> list[list[RecommendationAtom]]:
    """Group non-FORBIDDEN atoms by source section, then chunk by cluster_max.

    Each cluster becomes a single multi-action seed.  Sections that exceed
    ``cluster_max`` atoms are split into successive chunks; sections smaller
    than ``CLUSTER_MIN`` remain as a single sub-min cluster (we accept the
    smaller cluster rather than over-fragmenting at section boundaries).
    Cluster ordering is deterministic: section iteration order follows
    first-encounter order in ``atoms``; within a section, atoms preserve
    input order; chunks within a section are emitted in slice order.
    """
    clusters: list[list[RecommendationAtom]] = []
    by_section: dict[str, list[RecommendationAtom]] = {}
    section_order: list[str] = []
    for atom in atoms:
        if atom.constraint.type == "FORBIDDEN":
            continue
        section = atom.source.section.strip() or "General"
        if section not in by_section:
            by_section[section] = []
            section_order.append(section)
        by_section[section].append(atom)

    for section in section_order:
        section_atoms = by_section[section]
        if len(section_atoms) <= cluster_max:
            clusters.append(section_atoms)
        else:
            for start in range(0, len(section_atoms), cluster_max):
                clusters.append(section_atoms[start : start + cluster_max])

    return clusters


def _aggregate_population(
    atoms: list[RecommendationAtom],
) -> tuple[list[str], list[str]]:
    """Combine population criteria across a cluster.

    Inclusion: intersection across atoms (any criterion all atoms agree on).
    Exclusion: union across atoms (every contraindication anywhere applies).
    """
    if not atoms:
        return [], []
    inclusion_sets = [set(a.population.inclusion) for a in atoms]
    inclusion = inclusion_sets[0]
    for s in inclusion_sets[1:]:
        inclusion &= s
    exclusion: set[str] = set()
    for a in atoms:
        exclusion |= set(a.population.exclusion)
    # Preserve first-atom order when possible
    inclusion_ordered = [c for c in atoms[0].population.inclusion if c in inclusion]
    exclusion_ordered: list[str] = []
    seen_excl: set[str] = set()
    for a in atoms:
        for c in a.population.exclusion:
            if c not in seen_excl:
                seen_excl.add(c)
                exclusion_ordered.append(c)
    return inclusion_ordered, exclusion_ordered


def compile_seeds(
    atoms: list[RecommendationAtom],
    guideline_id: str,
    *,
    cluster_max: int = CLUSTER_MAX,
) -> list[ScenarioSeed]:
    """Generate multi-action ScenarioSeeds from atoms.

    Each cluster of atoms (grouped by source section, capped at ``cluster_max``)
    yields one seed.  The seed's ``source_atoms`` is the cluster atom-id list,
    so downstream ``seed_to_scenario_yaml`` produces a scenario with multiple
    ``expected_actions``.

    FORBIDDEN atoms remain seed-less; they contribute via counterfactual
    families and (Track-4-2) via the graph-level forbidden_actions injected
    in ``seed_to_scenario_yaml``.
    """
    clusters = _cluster_atoms_for_multi_action(atoms, cluster_max=cluster_max)
    seeds: list[ScenarioSeed] = []

    for cluster_idx, cluster in enumerate(clusters):
        first = cluster[0]
        section_slug = _section_to_slug(first.source.section)
        seed_id = f"{guideline_id}_{section_slug}_c{cluster_idx:03d}"

        # Boundaries: union (deduped) across atoms
        boundaries: list[BoundarySpec] = []
        seen_boundary: set[str] = set()
        for atom in cluster:
            for var in atom.scenario_hooks.boundary_variables:
                if var in _DEFAULT_BOUNDARIES and var not in seen_boundary:
                    boundaries.append(BoundarySpec(variable=var, values=_DEFAULT_BOUNDARIES[var]))
                    seen_boundary.add(var)

        # Mutations: concatenated across atoms (each atom contributes its own)
        mutations: list[MutationTemplate] = []
        for atom in cluster:
            mutations.extend(_make_mutation_templates(atom))

        # Coverage targets: aggregate constraint and boundary coverage
        constraint_targets: list[str] = []
        for atom in cluster:
            constraint_targets.append(f"{atom.constraint.type}({atom.action.canonical_id})")
            if atom.constraint.deadline_minutes is not None:
                constraint_targets.append(f"WITHIN({atom.action.canonical_id}, {atom.constraint.deadline_minutes})")
        coverage_targets: dict[str, list[str]] = {"constraints": constraint_targets}
        if boundaries:
            coverage_targets["boundaries"] = [b.variable for b in boundaries]

        # Activated constraint IDs: one per atom in the cluster
        activated_ids = [
            f"{guideline_id}_{atom.constraint.type.lower()}_{atom.action.canonical_id}" for atom in cluster
        ]

        seed = ScenarioSeed(
            seed_id=seed_id,
            source_atoms=[atom.atom_id for atom in cluster],
            coverage_targets=coverage_targets,
            boundaries=boundaries,
            patient_state_constraints={},
            mutation_templates=mutations,
            private_fields=PrivateFields(
                activated_constraint_ids=activated_ids,
                expected_trace_family=[f"{guideline_id}_compliant"],
            ),
        )
        seeds.append(seed)

    return seeds


# ------------------------------------------------------------------
# Seed -> scenario YAML
# ------------------------------------------------------------------


_PATIENT_TEMPLATES: list[dict[str, int | str]] = [
    {"age": 55, "sex": "M"},
    {"age": 68, "sex": "F"},
    {"age": 42, "sex": "M"},
    {"age": 75, "sex": "F"},
    {"age": 33, "sex": "M"},
    {"age": 61, "sex": "F"},
    {"age": 48, "sex": "M"},
    {"age": 80, "sex": "F"},
]


def _aggregate_graph_forbidden(
    graph_nodes: dict[str, dict[str, Any]] | None,
    cap: int,
) -> list[str]:
    """Collect deduplicated forbidden_actions across all graph nodes.

    Deterministic ordering: nodes are iterated in sorted ``node_id`` order,
    actions in the order they appear inside each node.  When the
    deduplicated list exceeds ``cap``, the first ``cap`` items are kept
    (deterministic prefix sample).  An empty mapping returns ``[]``.
    """
    if not graph_nodes:
        return []
    aggregated: list[str] = []
    seen: set[str] = set()
    for node_id in sorted(graph_nodes.keys()):
        node = graph_nodes[node_id]
        for action_id in node.get("forbidden_actions") or []:
            if action_id not in seen:
                seen.add(action_id)
                aggregated.append(action_id)
    if len(aggregated) > cap:
        aggregated = aggregated[:cap]
    return aggregated


def seed_to_scenario_yaml(
    seed: ScenarioSeed,
    graph_id: str,
    atoms: list[RecommendationAtom],
    seed_index: int = 0,
    *,
    graph_nodes: dict[str, dict[str, Any]] | None = None,
    forbidden_cap: int = FORBIDDEN_ACTIONS_CAP,
) -> dict[str, Any]:
    """Convert a ScenarioSeed into a scenario YAML entry.

    Output format matches ``ScenarioDefinition`` in ``eval_harness/scenario_loader.py``:
    scenario_id, description, guideline_graph, patient, ground_truth,
    expected_actions, forbidden_actions, max_duration_minutes, etc.

    Args:
        seed_index: Used for deterministic patient template rotation.
        graph_nodes: Optional graph-node mapping (e.g. ``compiled_graph["nodes"]``).
            When supplied, the union of all nodes' ``forbidden_actions`` is
            injected into the resulting scenario, capped at ``forbidden_cap``.
            Track-4-2 trap-loaded enrichment.
        forbidden_cap: Maximum forbidden_actions to include from graph nodes.
    """
    # Look up atoms referenced by this seed
    atom_map = {a.atom_id: a for a in atoms}
    seed_atoms = [atom_map[aid] for aid in seed.source_atoms if aid in atom_map]

    expected_actions: list[str] = []
    forbidden_actions: list[str] = []

    for a in seed_atoms:
        if a.constraint.type == "FORBIDDEN":
            forbidden_actions.append(a.action.canonical_id)
        else:
            expected_actions.append(a.action.canonical_id)

    # Track-4-2: graph-level forbidden_actions injection
    if graph_nodes:
        graph_forbidden = _aggregate_graph_forbidden(graph_nodes, forbidden_cap)
        for fa in graph_forbidden:
            if fa not in forbidden_actions:
                forbidden_actions.append(fa)

    # Build patient state with demographic diversity
    tmpl = _PATIENT_TEMPLATES[seed_index % len(_PATIENT_TEMPLATES)]
    patient: dict[str, Any] = {
        "age": tmpl["age"],
        "sex": tmpl["sex"],
        "chief_complaint": f"Clinical scenario for {graph_id}",
        "vitals": {
            "heart_rate": 90,
            "blood_pressure_systolic": 120,
            "blood_pressure_diastolic": 75,
            "respiratory_rate": 18,
            "temperature": 37.0,
            "oxygen_saturation": 96,
        },
        "allergies": [],
        "medical_history": [],
        "comorbidities": [],
        "contraindications": [],
    }

    # Apply patient_state_constraints
    for key, val in seed.patient_state_constraints.items():
        patient[key] = val

    # Determine max duration
    max_duration = 120
    for a in seed_atoms:
        if a.constraint.deadline_minutes is not None:
            max_duration = max(max_duration, a.constraint.deadline_minutes * 2)

    description_parts = [f"SGSC-generated scenario testing {', '.join(expected_actions)}"]
    if seed.boundaries:
        description_parts.append(f"with boundary values for {', '.join(b.variable for b in seed.boundaries)}")

    # Defensive normalization: ensure action IDs are canonical even if
    # atoms bypassed pipeline Step 2b (e.g. direct compiler calls).
    try:
        from cga_bench.assessor_core.action_normalizer import ActionNormalizer

        normalizer = ActionNormalizer()
        expected_actions = [normalizer.normalize(a) for a in expected_actions]
        forbidden_actions = [normalizer.normalize(a) for a in forbidden_actions]
        # Re-deduplicate post-normalization in case two raw forms collapsed
        seen_norm: set[str] = set()
        deduped_forbidden: list[str] = []
        for fa in forbidden_actions:
            if fa not in seen_norm:
                seen_norm.add(fa)
                deduped_forbidden.append(fa)
        forbidden_actions = deduped_forbidden
    except ImportError:
        pass

    return {
        "scenario_id": seed.seed_id,
        "description": " ".join(description_parts),
        "guideline_graph": graph_id,
        "patient": patient,
        "ground_truth": {
            "expected_actions": expected_actions,
            "forbidden_actions": forbidden_actions,
        },
        "expected_actions": expected_actions,
        "forbidden_actions": forbidden_actions,
        "optional_actions": [],
        "max_duration_minutes": max_duration,
        "passing_compliance_threshold": 0.7,
        "_sgsc_metadata": {
            "seed_id": seed.seed_id,
            "source_atoms": seed.source_atoms,
            "coverage_targets": seed.coverage_targets,
        },
    }


def seeds_to_scenario_yaml(
    seeds: list[ScenarioSeed],
    graph_id: str,
    atoms: list[RecommendationAtom],
    *,
    graph_nodes: dict[str, dict[str, Any]] | None = None,
    forbidden_cap: int = FORBIDDEN_ACTIONS_CAP,
) -> dict[str, dict[str, Any]]:
    """Convert all seeds to a scenarios dict keyed by scenario_id.

    Track-4-2: ``graph_nodes`` is forwarded to each ``seed_to_scenario_yaml``
    call so the union of graph forbidden_actions is injected into every
    scenario.
    """
    return {
        seed.seed_id: seed_to_scenario_yaml(
            seed,
            graph_id,
            atoms,
            seed_index=i,
            graph_nodes=graph_nodes,
            forbidden_cap=forbidden_cap,
        )
        for i, seed in enumerate(seeds)
    }


# ------------------------------------------------------------------
# Public/private scenario split
# ------------------------------------------------------------------

# Private fields that must not appear in public scenarios
_PRIVATE_KEYS: frozenset[str] = frozenset(
    {
        "ground_truth",
        "expected_actions",
        "forbidden_actions",
        "passing_compliance_threshold",
        "_sgsc_metadata",
    }
)

# Public fields that agents may see
_PUBLIC_KEYS: frozenset[str] = frozenset(
    {
        "scenario_id",
        "description",
        "guideline_graph",
        "patient",
        "optional_actions",
        "max_duration_minutes",
    }
)


def split_scenario_public_private(
    scenario: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split a full scenario into public (agent-visible) and private (scorer-only) dicts.

    Public: scenario_id, description, guideline_graph, patient, optional_actions, max_duration_minutes.
    Private: ground_truth, expected_actions, forbidden_actions, passing_compliance_threshold, _sgsc_metadata.
    """
    public: dict[str, Any] = {}
    private: dict[str, Any] = {"scenario_id": scenario.get("scenario_id", "")}

    for key, value in scenario.items():
        if key in _PRIVATE_KEYS:
            private[key] = value
        else:
            public[key] = value

    return public, private


def seeds_to_split_scenario_yaml(
    seeds: list[ScenarioSeed],
    graph_id: str,
    atoms: list[RecommendationAtom],
    *,
    graph_nodes: dict[str, dict[str, Any]] | None = None,
    forbidden_cap: int = FORBIDDEN_ACTIONS_CAP,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Generate both public and private scenario dicts.

    Returns:
        (scenarios_public, scenarios_private) — both keyed by scenario_id.

    Track-4-2: ``graph_nodes`` is forwarded so private scenarios receive
    the trap-loaded forbidden_actions list.
    """
    full = seeds_to_scenario_yaml(seeds, graph_id, atoms, graph_nodes=graph_nodes, forbidden_cap=forbidden_cap)
    public_all: dict[str, dict[str, Any]] = {}
    private_all: dict[str, dict[str, Any]] = {}

    for sid, scenario in full.items():
        pub, priv = split_scenario_public_private(scenario)
        public_all[sid] = pub
        private_all[sid] = priv

    return public_all, private_all
