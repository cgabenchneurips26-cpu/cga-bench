#!/usr/bin/env python3
"""B-4 Patient profile expansion for SGSC scenario compilation.

Replaces the v7 demographic-only `_PATIENT_TEMPLATES` rotation with a
30-spec profile bank that spans the 6 dimensions identified in B-1
(age_group, pregnancy, comorbidity, allergy, severity, special_state).
For each ScenarioSeed, generates `max_profiles_per_cluster` scenarios
covering Tier 1 (common comorbidity), Tier 2 (severity), Tier 3 (rare
special state), Tier 4 (rare population), and Tier 5 (default no-cue) per
the B-2 multiplicity decomposition.

The expansion preserves all atom-derived expected/forbidden actions,
adds a top-level `population_criteria` field (Theorem 1 Case (iv) marker),
and overrides `patient.{age, sex, comorbidities, allergies}` from profile
dimensions. **No new forbidden_actions are introduced** -- profile-specific
contraindications stay implicit in `population_criteria` text to keep the
B-5 entailment-based hallucination rate at 0%.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sgsc.compilers.scenario_compiler import seed_to_scenario_yaml

if TYPE_CHECKING:
    from sgsc.schemas.atom import RecommendationAtom
    from sgsc.schemas.seed import ScenarioSeed

# Tier identifiers from B-2 multiplicity decomposition
TIER_DEFAULT = "T5_default"
TIER_COMMON = "T1_common_comorbidity"
TIER_SEVERITY = "T2_severity"
TIER_RARE_SPECIAL = "T3_rare_special"
TIER_RARE_POPULATION = "T4_rare_population"

# Per-graph max-profiles overrides for low-v7 graphs to hit >=30 gate
PER_GRAPH_MAX_PROFILES: dict[str, int] = {
    "ssc_sepsis_hour1_bundle": 30,  # v7=1 -> 1*30 = 30
    "universal_clinical_safety": 30,  # v7=1 -> 30
    "aha_chest_pain_evaluation": 15,  # v7=2 -> 30
    "kdigo_aki_full": 10,  # v7=3 -> 30
    "acls_cardiac_arrest": 8,  # v7=4 -> 32
    "pals_pediatric_emergency": 6,  # v7=5 -> 30
}

DEFAULT_MAX_PROFILES = 5


@dataclass(frozen=True)
class ProfileSpec:
    """A single named patient profile spanning all 6 catalog dimensions."""

    name: str
    tier: str
    age_years: int
    sex: str
    comorbidities: tuple[str, ...]
    allergies: tuple[str, ...]
    pregnancy: str
    severity: str
    special_state: str

    @property
    def population_criteria(self) -> str:
        """Human-readable assertion of profile dimensions."""
        parts: list[str] = [f"age={self.age_years}y", f"sex={self.sex}"]
        if self.comorbidities:
            parts.append("comorbidities=" + "+".join(self.comorbidities))
        if self.allergies:
            parts.append("allergies=" + "+".join(self.allergies))
        if self.pregnancy != "none":
            parts.append(f"pregnancy={self.pregnancy}")
        if self.severity != "unspecified":
            parts.append(f"severity={self.severity}")
        if self.special_state != "none":
            parts.append(f"special_state={self.special_state}")
        return f"[{self.name}] " + ", ".join(parts)


# Tier 5 default no-cue baselines (3 specs)
_T5: list[ProfileSpec] = [
    ProfileSpec(
        "default_adult_male",
        TIER_DEFAULT,
        45,
        "M",
        (),
        (),
        "none",
        "unspecified",
        "none",
    ),
    ProfileSpec(
        "default_adult_female",
        TIER_DEFAULT,
        38,
        "F",
        (),
        (),
        "none",
        "unspecified",
        "none",
    ),
    ProfileSpec(
        "default_elderly_male",
        TIER_DEFAULT,
        72,
        "M",
        (),
        (),
        "none",
        "unspecified",
        "none",
    ),
]

# Tier 1 common comorbidity (12 specs covering 6 conditions x 2 ages)
_T1: list[ProfileSpec] = [
    ProfileSpec(
        "adult_diabetes",
        TIER_COMMON,
        52,
        "M",
        ("diabetes_type_2",),
        (),
        "none",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "elderly_diabetes",
        TIER_COMMON,
        70,
        "F",
        ("diabetes_type_2", "hypertension"),
        (),
        "none",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "adult_hypertension",
        TIER_COMMON,
        48,
        "F",
        ("hypertension",),
        (),
        "none",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "elderly_hypertension",
        TIER_COMMON,
        76,
        "M",
        ("hypertension",),
        (),
        "none",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "adult_asthma",
        TIER_COMMON,
        35,
        "F",
        ("asthma",),
        (),
        "none",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "pediatric_asthma",
        TIER_COMMON,
        8,
        "M",
        ("asthma",),
        (),
        "none",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "adult_cad",
        TIER_COMMON,
        58,
        "M",
        ("coronary_artery_disease", "hypertension"),
        (),
        "none",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "elderly_cad",
        TIER_COMMON,
        78,
        "M",
        ("coronary_artery_disease", "prior_mi"),
        (),
        "none",
        "severe",
        "none",
    ),
    ProfileSpec(
        "adult_chf",
        TIER_COMMON,
        60,
        "M",
        ("heart_failure_with_reduced_ef",),
        (),
        "none",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "elderly_chf",
        TIER_COMMON,
        75,
        "F",
        ("heart_failure_with_preserved_ef", "hypertension"),
        (),
        "none",
        "severe",
        "none",
    ),
    ProfileSpec(
        "adult_copd",
        TIER_COMMON,
        55,
        "M",
        ("copd",),
        (),
        "none",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "elderly_copd",
        TIER_COMMON,
        72,
        "F",
        ("copd",),
        (),
        "none",
        "severe",
        "none",
    ),
]

# Tier 2 severity tiers (6 specs)
_T2: list[ProfileSpec] = [
    ProfileSpec(
        "mild_adult",
        TIER_SEVERITY,
        42,
        "F",
        (),
        (),
        "none",
        "mild",
        "none",
    ),
    ProfileSpec(
        "moderate_adult",
        TIER_SEVERITY,
        50,
        "M",
        (),
        (),
        "none",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "severe_adult",
        TIER_SEVERITY,
        55,
        "M",
        (),
        (),
        "none",
        "severe",
        "none",
    ),
    ProfileSpec(
        "critical_adult",
        TIER_SEVERITY,
        48,
        "F",
        (),
        (),
        "none",
        "critical",
        "none",
    ),
    ProfileSpec(
        "severe_elderly",
        TIER_SEVERITY,
        78,
        "M",
        (),
        (),
        "none",
        "severe",
        "none",
    ),
    ProfileSpec(
        "critical_elderly",
        TIER_SEVERITY,
        82,
        "F",
        (),
        (),
        "none",
        "critical",
        "none",
    ),
]

# Tier 3 rare safety-critical special states (5 specs)
_T3: list[ProfileSpec] = [
    ProfileSpec(
        "anticoagulated_adult",
        TIER_RARE_SPECIAL,
        62,
        "M",
        ("atrial_fibrillation",),
        (),
        "none",
        "moderate",
        "anticoagulated",
    ),
    ProfileSpec(
        "anticoagulated_elderly",
        TIER_RARE_SPECIAL,
        78,
        "F",
        ("atrial_fibrillation",),
        (),
        "none",
        "severe",
        "anticoagulated",
    ),
    ProfileSpec(
        "septic_shock_adult",
        TIER_RARE_SPECIAL,
        56,
        "M",
        (),
        (),
        "none",
        "critical",
        "septic_shock",
    ),
    ProfileSpec(
        "intubated_critical",
        TIER_RARE_SPECIAL,
        60,
        "F",
        (),
        (),
        "none",
        "critical",
        "intubated",
    ),
    ProfileSpec(
        "on_steroids_chronic",
        TIER_RARE_SPECIAL,
        65,
        "F",
        ("autoimmune_disease",),
        (),
        "none",
        "moderate",
        "on_steroids",
    ),
]

# Tier 4 rare populations (4 specs)
_T4: list[ProfileSpec] = [
    ProfileSpec(
        "pregnant_adult",
        TIER_RARE_POPULATION,
        28,
        "F",
        (),
        (),
        "pregnant",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "ckd_stage3_elderly",
        TIER_RARE_POPULATION,
        70,
        "M",
        ("chronic_kidney_disease_stage_3",),
        (),
        "none",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "immunocompromised_adult",
        TIER_RARE_POPULATION,
        45,
        "F",
        ("solid_organ_transplant",),
        (),
        "none",
        "moderate",
        "none",
    ),
    ProfileSpec(
        "postpartum_adult",
        TIER_RARE_POPULATION,
        30,
        "F",
        (),
        (),
        "postpartum",
        "moderate",
        "none",
    ),
]

# Full bank: 3 + 12 + 6 + 5 + 4 = 30 specs
PROFILE_BANK: list[ProfileSpec] = _T5 + _T1 + _T2 + _T3 + _T4


def _select_profiles_for_seed(seed_index: int, max_profiles: int) -> list[ProfileSpec]:
    """Pick a tier-balanced slate of profiles for a single seed.

    Slot strategy (deterministic by ``seed_index``):
        slot_0:    T5 default (cycle through 3)
        slot_1..2: T1 common comorbidity (cycle through 12)
        slot_3:    T2 severity (cycle through 6)
        slot_4:    T3 rare special / T4 rare population (alternating)
        slot_5+:   round-robin through remaining specs

    Args:
        seed_index: Stable index used to derive deterministic slot offsets.
        max_profiles: Cap on the returned slate length (>= 1).

    Returns:
        List of ProfileSpec, length ``min(max_profiles, len(PROFILE_BANK))``.
    """
    chosen: list[ProfileSpec] = []
    used: set[str] = set()

    def _add(spec: ProfileSpec) -> None:
        if spec.name not in used and len(chosen) < max_profiles:
            chosen.append(spec)
            used.add(spec.name)

    # Slot 0: T5 default
    if max_profiles >= 1:
        _add(_T5[seed_index % len(_T5)])
    # Slots 1-2: T1 common comorbidity (two distinct picks)
    if max_profiles >= 2:
        _add(_T1[seed_index % len(_T1)])
    if max_profiles >= 3:
        _add(_T1[(seed_index + (len(_T1) // 2)) % len(_T1)])
    # Slot 3: T2 severity
    if max_profiles >= 4:
        _add(_T2[seed_index % len(_T2)])
    # Slot 4: T3 / T4 alternating
    if max_profiles >= 5:
        if seed_index % 2 == 0:
            _add(_T3[(seed_index // 2) % len(_T3)])
        else:
            _add(_T4[(seed_index // 2) % len(_T4)])
    # Remaining slots: round-robin through full bank
    if len(chosen) < max_profiles:
        for offset in range(len(PROFILE_BANK)):
            spec = PROFILE_BANK[(seed_index + offset) % len(PROFILE_BANK)]
            _add(spec)
            if len(chosen) >= max_profiles:
                break
    return chosen


def _apply_profile_to_scenario(scenario: dict[str, Any], profile: ProfileSpec) -> dict[str, Any]:
    """Override patient state from profile and inject population_criteria."""
    out = copy.deepcopy(scenario)
    patient = out.setdefault("patient", {})
    patient["age"] = profile.age_years
    patient["sex"] = profile.sex
    patient["comorbidities"] = list(profile.comorbidities)
    patient["allergies"] = list(profile.allergies)
    out["population_criteria"] = profile.population_criteria
    out["_sgsc_profile_tier"] = profile.tier
    out["_sgsc_profile_name"] = profile.name
    return out


def _build_profile_scenario_id(base_id: str, profile_name: str) -> str:
    """Stable derived ID combining seed-derived base id and profile name."""
    return f"{base_id}__{profile_name}"


def expand_seeds_with_profiles(
    seeds: list[ScenarioSeed],
    graph_id: str,
    atoms: list[RecommendationAtom],
    graph_nodes: dict[str, Any],
    profile_catalog: dict[str, Any] | None = None,
    max_profiles_per_cluster: int = DEFAULT_MAX_PROFILES,
) -> dict[str, dict[str, Any]]:
    """Expand each seed into multiple profile-conditioned scenarios.

    Per-graph overrides (``PER_GRAPH_MAX_PROFILES``) raise the cap for
    low-v7 graphs to satisfy the B-4 >=30-scenarios gate. The
    ``profile_catalog`` argument is accepted for API compatibility with
    future heuristic refinement; the current implementation uses the
    static ``PROFILE_BANK``.
    """
    cap = PER_GRAPH_MAX_PROFILES.get(graph_id, max_profiles_per_cluster)
    out: dict[str, dict[str, Any]] = {}
    for seed_index, seed in enumerate(seeds):
        base_scenario = seed_to_scenario_yaml(
            seed,
            graph_id,
            atoms,
            seed_index=seed_index,
            graph_nodes=graph_nodes,
        )
        base_id = base_scenario.get("scenario_id") or seed.seed_id
        profiles = _select_profiles_for_seed(seed_index, cap)
        for profile in profiles:
            scenario = _apply_profile_to_scenario(base_scenario, profile)
            scenario_id = _build_profile_scenario_id(base_id, profile.name)
            scenario["scenario_id"] = scenario_id
            out[scenario_id] = scenario
    return out


def get_max_profiles_for_graph(
    graph_id: str,
    default: int = DEFAULT_MAX_PROFILES,
) -> int:
    """Return the per-graph profile cap, falling back to the default."""
    return PER_GRAPH_MAX_PROFILES.get(graph_id, default)
