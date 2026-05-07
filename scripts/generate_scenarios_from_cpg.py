"""Scenario Generator: CPG Graph YAML -> Scenario YAML files.

Reads one or more CPG graph YAMLs and auto-generates scenario configs by:
  1. Walking reachable nodes from entry_node to collect expected_actions
  2. Varying patient states to exercise conditional_next branches
  3. Injecting comorbidities/allergies to trigger conditional_rules
  4. Creating trap scenarios where forbidden actions are clinically tempting

Usage:
    # Single graph
    PYTHONPATH=. python scripts/generate_scenarios_from_cpg.py \
        --graph cpg_model/graphs/ssc_sepsis_hour1_bundle.yaml

    # All graphs in a directory
    PYTHONPATH=. python scripts/generate_scenarios_from_cpg.py \
        --graphs-dir cpg_model/graphs/auto/

    # Dry run (preview without writing)
    PYTHONPATH=. python scripts/generate_scenarios_from_cpg.py \
        --graphs-dir cpg_model/graphs/auto/ --dry-run
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import random
import re
from typing import Any

import yaml

logger = logging.getLogger("generate_scenarios")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "configs" / "scenarios" / "auto"

# ---------------------------------------------------------------------------
# Domain-specific patient templates
# ---------------------------------------------------------------------------

_VITALS_TEMPLATES: dict[str, dict[str, Any]] = {
    "stable": {
        "heart_rate": 80,
        "blood_pressure_systolic": 125,
        "blood_pressure_diastolic": 78,
        "respiratory_rate": 16,
        "temperature": 37.0,
        "oxygen_saturation": 97,
        "map_mmhg": 94,
    },
    "mild_abnormal": {
        "heart_rate": 100,
        "blood_pressure_systolic": 110,
        "blood_pressure_diastolic": 70,
        "respiratory_rate": 20,
        "temperature": 38.2,
        "oxygen_saturation": 94,
        "map_mmhg": 83,
    },
    "moderate_abnormal": {
        "heart_rate": 115,
        "blood_pressure_systolic": 95,
        "blood_pressure_diastolic": 58,
        "respiratory_rate": 24,
        "temperature": 38.8,
        "oxygen_saturation": 91,
        "map_mmhg": 70,
    },
    "severe_abnormal": {
        "heart_rate": 130,
        "blood_pressure_systolic": 80,
        "blood_pressure_diastolic": 45,
        "respiratory_rate": 28,
        "temperature": 39.5,
        "oxygen_saturation": 88,
        "map_mmhg": 57,
    },
    "critical": {
        "heart_rate": 145,
        "blood_pressure_systolic": 70,
        "blood_pressure_diastolic": 35,
        "respiratory_rate": 32,
        "temperature": 40.1,
        "oxygen_saturation": 84,
        "map_mmhg": 47,
    },
}

_DEMOGRAPHICS: list[dict[str, Any]] = [
    {"age": 35, "sex": "M", "weight_kg": 80},
    {"age": 45, "sex": "F", "weight_kg": 65},
    {"age": 55, "sex": "M", "weight_kg": 90},
    {"age": 65, "sex": "F", "weight_kg": 70},
    {"age": 72, "sex": "M", "weight_kg": 75},
    {"age": 78, "sex": "F", "weight_kg": 58},
    {"age": 28, "sex": "F", "weight_kg": 62},
    {"age": 50, "sex": "M", "weight_kg": 85},
]

# Population-specific demographics keyed by target_population.age_group
_DEMOGRAPHICS_BY_POPULATION: dict[str, list[dict[str, Any]]] = {
    "neonatal": [
        {"age": 0, "sex": "M", "weight_kg": 3.2},
        {"age": 0, "sex": "F", "weight_kg": 2.8},
        {"age": 0, "sex": "M", "weight_kg": 3.5},
        {"age": 0, "sex": "F", "weight_kg": 3.0},
    ],
    "pediatric": [
        {"age": 2, "sex": "M", "weight_kg": 12},
        {"age": 5, "sex": "F", "weight_kg": 18},
        {"age": 8, "sex": "M", "weight_kg": 25},
        {"age": 14, "sex": "F", "weight_kg": 50},
    ],
    "adult": _DEMOGRAPHICS,
    "all": _DEMOGRAPHICS,  # fallback; caller filters by sex if needed
}

# Age-appropriate vitals by population (same 5-severity structure)
_VITALS_TEMPLATES_NEONATAL: dict[str, dict[str, Any]] = {
    "stable": {
        "heart_rate": 140,
        "blood_pressure_systolic": 65,
        "blood_pressure_diastolic": 40,
        "respiratory_rate": 40,
        "temperature": 36.8,
        "oxygen_saturation": 96,
        "map_mmhg": 48,
    },
    "mild_abnormal": {
        "heart_rate": 160,
        "blood_pressure_systolic": 55,
        "blood_pressure_diastolic": 35,
        "respiratory_rate": 50,
        "temperature": 37.5,
        "oxygen_saturation": 93,
        "map_mmhg": 42,
    },
    "moderate_abnormal": {
        "heart_rate": 175,
        "blood_pressure_systolic": 48,
        "blood_pressure_diastolic": 30,
        "respiratory_rate": 60,
        "temperature": 38.0,
        "oxygen_saturation": 89,
        "map_mmhg": 36,
    },
    "severe_abnormal": {
        "heart_rate": 190,
        "blood_pressure_systolic": 40,
        "blood_pressure_diastolic": 25,
        "respiratory_rate": 70,
        "temperature": 38.5,
        "oxygen_saturation": 85,
        "map_mmhg": 30,
    },
    "critical": {
        "heart_rate": 60,
        "blood_pressure_systolic": 30,
        "blood_pressure_diastolic": 18,
        "respiratory_rate": 10,
        "temperature": 35.0,
        "oxygen_saturation": 70,
        "map_mmhg": 22,
    },
}
_VITALS_TEMPLATES_PEDIATRIC: dict[str, dict[str, Any]] = {
    "stable": {
        "heart_rate": 100,
        "blood_pressure_systolic": 100,
        "blood_pressure_diastolic": 65,
        "respiratory_rate": 22,
        "temperature": 37.0,
        "oxygen_saturation": 97,
        "map_mmhg": 77,
    },
    "mild_abnormal": {
        "heart_rate": 120,
        "blood_pressure_systolic": 90,
        "blood_pressure_diastolic": 58,
        "respiratory_rate": 28,
        "temperature": 38.2,
        "oxygen_saturation": 94,
        "map_mmhg": 69,
    },
    "moderate_abnormal": {
        "heart_rate": 140,
        "blood_pressure_systolic": 80,
        "blood_pressure_diastolic": 50,
        "respiratory_rate": 34,
        "temperature": 38.8,
        "oxygen_saturation": 91,
        "map_mmhg": 60,
    },
    "severe_abnormal": {
        "heart_rate": 160,
        "blood_pressure_systolic": 70,
        "blood_pressure_diastolic": 40,
        "respiratory_rate": 40,
        "temperature": 39.5,
        "oxygen_saturation": 87,
        "map_mmhg": 50,
    },
    "critical": {
        "heart_rate": 180,
        "blood_pressure_systolic": 55,
        "blood_pressure_diastolic": 30,
        "respiratory_rate": 50,
        "temperature": 40.0,
        "oxygen_saturation": 82,
        "map_mmhg": 38,
    },
}

_VITALS_BY_POPULATION: dict[str, dict[str, dict[str, Any]]] = {
    "neonatal": _VITALS_TEMPLATES_NEONATAL,
    "pediatric": _VITALS_TEMPLATES_PEDIATRIC,
    "adult": _VITALS_TEMPLATES,
    "all": _VITALS_TEMPLATES,
}

# Task 1: Clinically-bounded noise ranges (±max) per vital per population
_VITALS_NOISE_BOUNDS: dict[str, dict[str, float]] = {
    "adult": {
        "heart_rate": 15,
        "blood_pressure_systolic": 15,
        "blood_pressure_diastolic": 10,
        "respiratory_rate": 4,
        "temperature": 0.5,
        "oxygen_saturation": 3,
    },
    "pediatric": {
        "heart_rate": 12,
        "blood_pressure_systolic": 10,
        "blood_pressure_diastolic": 8,
        "respiratory_rate": 5,
        "temperature": 0.4,
        "oxygen_saturation": 3,
    },
    "neonatal": {
        "heart_rate": 10,
        "blood_pressure_systolic": 8,
        "blood_pressure_diastolic": 5,
        "respiratory_rate": 4,
        "temperature": 0.3,
        "oxygen_saturation": 3,
    },
}


def _perturb_vitals(
    template: dict[str, Any],
    rng: random.Random,
    age_group: str = "adult",
) -> dict[str, Any]:
    """Add clinically-bounded Gaussian noise to a vitals template.

    Each vital is perturbed by N(0, range/2) clamped to ±range, then
    clamped to physiological bounds.  MAP is recomputed from SBP/DBP.
    """
    bounds = _VITALS_NOISE_BOUNDS.get(age_group, _VITALS_NOISE_BOUNDS["adult"])
    result: dict[str, Any] = {}

    for key, base_val in template.items():
        if key == "map_mmhg":
            continue  # recompute below
        noise_range = bounds.get(key, 0)
        if noise_range > 0:
            noise = rng.gauss(0, noise_range / 2)
            noise = max(-noise_range, min(noise_range, noise))
            perturbed = base_val + noise
            if key == "oxygen_saturation":
                perturbed = max(40, min(100, round(perturbed)))
            elif key == "temperature":
                perturbed = round(max(32.0, min(42.0, perturbed)), 1)
            else:
                perturbed = max(1, round(perturbed))
            result[key] = perturbed
        else:
            result[key] = base_val

    sbp = result.get("blood_pressure_systolic", 120)
    dbp = result.get("blood_pressure_diastolic", 80)
    result["map_mmhg"] = round(dbp + (sbp - dbp) / 3)
    return result


def _get_demo_pool(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the demographics pool appropriate for the graph's target population."""
    pop = (graph.get("metadata") or {}).get("target_population") or {}
    age_group = pop.get("age_group", "adult")
    pool = list(_DEMOGRAPHICS_BY_POPULATION.get(age_group, _DEMOGRAPHICS))

    # Filter by sex constraint (e.g., female_only for maternal/breast-cancer)
    required_sex = pop.get("sex", "any")
    if required_sex == "female_only":
        pool = [d for d in pool if d["sex"] == "F"]
    elif required_sex == "male_only":
        pool = [d for d in pool if d["sex"] == "M"]

    # Filter by age bounds from target_population
    min_age = pop.get("min_age")
    max_age = pop.get("max_age")
    if min_age is not None or max_age is not None:
        pool = [
            d for d in pool if (min_age is None or d["age"] >= min_age) and (max_age is None or d["age"] <= max_age)
        ]

    # Safety: if filter emptied the pool, add a minimal valid entry
    if not pool:
        sex_char = "F" if required_sex == "female_only" else "M"
        safe_age = int((min_age or 0) + (max_age or 50)) // 2
        pool = [{"age": safe_age, "sex": sex_char, "weight_kg": 70}]

    return pool


def _get_vitals_templates(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the vitals template set appropriate for the graph's target population."""
    pop = (graph.get("metadata") or {}).get("target_population") or {}
    age_group = pop.get("age_group", "adult")
    return _VITALS_BY_POPULATION.get(age_group, _VITALS_TEMPLATES)


# ---------------------------------------------------------------------------
# Graph analysis helpers
# ---------------------------------------------------------------------------


def load_graph(path: Path) -> dict[str, Any] | None:
    """Load a CPG graph YAML. Returns None on error."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "nodes" in data:
            return data
        return None
    except Exception as e:
        logger.warning("Failed to load %s: %s", path.name, e)
        return None


def _extract_domain(graph: dict[str, Any]) -> str:
    """Extract domain from graph metadata or graph_id.

    Uses token-based matching (splitting on '_' / '-') to avoid
    substring false-positives such as ``"pe"`` matching
    ``"sccm_pediatric_septic_shock"``.
    """
    meta = graph.get("metadata") or {}
    domain = meta.get("domain", "")
    if domain:
        return domain
    gid = graph.get("graph_id", "")
    tokens = set(gid.lower().replace("-", "_").split("_"))

    # Order matters: more specific tokens first to avoid shadowing.
    _TOKEN_TO_DOMAIN: list[tuple[str, str]] = [
        # Population-specific (checked first so pediatric sepsis → pediatric)
        ("neonatal", "neonatal"),
        ("pediatric", "pediatric"),
        ("maternal", "maternal"),
        ("obstetric", "obstetric"),
        # Core clinical domains
        ("sepsis", "sepsis"),
        ("stroke", "stroke"),
        ("aki", "aki"),
        ("dka", "dka"),
        ("copd", "copd"),
        ("pneumonia", "cap"),
        ("anaphylaxis", "anaphylaxis"),
        ("burn", "burn"),
        ("meningitis", "meningitis"),
        ("epilepticus", "status_epilepticus"),
        # Cardiology / vascular
        ("coronary", "cardiology"),
        ("valvular", "cardiology_valvular"),
        ("endocarditis", "cardiology_endocarditis"),
        ("amyloidosis", "cardiology_amyloidosis"),
        ("aortic", "vascular"),
        ("peripheral", "vascular"),
        # Oncology
        ("breast", "oncology_breast"),
        ("melanoma", "oncology"),
        ("colorectal", "oncology"),
        ("pancreatic", "oncology"),
        # Other
        ("hyperkalemia", "electrolyte"),
        ("hemorrhage", "hemorrhage"),
        ("transfusion", "transfusion"),
        ("appendicitis", "surgery"),
        ("peptic", "surgery"),
        # Trauma / neuro
        ("tbi", "tbi"),
        ("trauma", "tbi"),
        # Oncology (tumor lysis, etc.)
        ("tls", "oncology"),
        ("tumor", "oncology"),
        # Environmental
        ("hypothermia", "hypothermia"),
        ("hyperthermia", "hypothermia"),
        # GI / hepatology
        ("varices", "gi_bleeding"),
        ("variceal", "gi_bleeding"),
        ("cirrhosis", "gi_bleeding"),
        # Addiction / toxicology
        ("withdrawal", "addiction"),
        ("alcohol", "addiction"),
        ("toxicology", "toxicology"),
        ("overdose", "toxicology"),
        ("poisoning", "toxicology"),
        # Infectious
        ("hiv", "infectious"),
        ("antimicrobial", "infectious"),
        # Respiratory
        ("asthma", "asthma"),
        ("pneumothorax", "respiratory"),
    ]

    for token, dom in _TOKEN_TO_DOMAIN:
        if token in tokens:
            return dom

    # Chest pain: require "chest" token (not just substring)
    if "chest" in tokens:
        return "chest_pain"

    # Heart failure: require "heart" + "failure" tokens
    if "heart" in tokens and "failure" in tokens:
        return "heart_failure"

    # Pulmonary embolism: require BOTH tokens (never bare "pe")
    if "pulmonary" in tokens and "embolism" in tokens:
        return "pulmonary_embolism"
    # Accept known graph_id patterns that use the abbreviation
    if gid.lower() in ("pulmonary_embolism", "esc_pe_2019"):
        return "pulmonary_embolism"

    return "general"


def walk_reachable_path(
    graph: dict[str, Any],
    working_diagnosis: str | None = None,
    return_node_ids: bool = False,
) -> list[str] | tuple[list[str], list[str]]:
    """Walk from entry_node and collect mandatory_actions along the path.

    For conditional_next branching, selects the branch matching
    working_diagnosis if provided, otherwise follows each branch.

    Args:
        graph: CPG graph dict.
        working_diagnosis: Optional diagnosis to select branch.
        return_node_ids: If True, also return list of visited node IDs.

    Returns:
        list of mandatory action IDs, or (actions, node_ids) if
        return_node_ids is True.
    """
    nodes = graph.get("nodes") or {}
    entry = graph.get("entry_node", "")
    if not entry or entry not in nodes:
        return ([], []) if return_node_ids else []

    visited: set[str] = set()
    visited_ordered: list[str] = []
    queue: list[str] = [entry]
    mandatory: list[str] = []
    seen_actions: set[str] = set()

    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        visited_ordered.append(nid)
        node = nodes.get(nid)
        if not node or not isinstance(node, dict):
            continue

        for action in node.get("mandatory_actions") or []:
            if action not in seen_actions:
                mandatory.append(action)
                seen_actions.add(action)

        # Determine next nodes
        cond_next = node.get("conditional_next") or {}
        next_nodes = list(node.get("next_nodes") or [])

        if cond_next and working_diagnosis:
            # Try to match the working_diagnosis against conditions
            matched = False
            for cond, target in cond_next.items():
                if working_diagnosis in cond or cond == "True" or cond == "'True'":
                    if not matched:
                        queue.append(target)
                        matched = True
                elif cond == "True":
                    # Default fallback
                    if not matched:
                        queue.append(target)
            if not matched and cond_next:
                # No match: take the first branch
                first_target = next(iter(cond_next.values()))
                queue.append(first_target)
        elif cond_next:
            # No working_diagnosis: follow all branches
            for target in cond_next.values():
                queue.append(target)

        for nxt in next_nodes:
            queue.append(nxt)

    if return_node_ids:
        return mandatory, visited_ordered
    return mandatory


def extract_branch_diagnoses(graph: dict[str, Any]) -> list[str]:
    """Extract working_diagnosis values from conditional_next conditions."""
    diagnoses: list[str] = []
    for node in (graph.get("nodes") or {}).values():
        if not isinstance(node, dict):
            continue
        for cond in node.get("conditional_next") or {}:
            # Parse patterns like: state.working_diagnosis == 'septic_shock'
            match = re.search(r"working_diagnosis\s*==\s*['\"](\w+)['\"]", str(cond))
            if match:
                diagnoses.append(match.group(1))
    return list(dict.fromkeys(diagnoses))  # Deduplicate preserving order


def extract_conditional_triggers(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract comorbidity/allergy triggers from conditional_rules.

    Returns a list of trigger dicts, each with:
      - allergies: list[str]
      - comorbidities: list[str]
      - forbidden_actions: list[str]  (from the rule effect)
      - description: str
    """
    triggers: list[dict[str, Any]] = []
    seen: set[str] = set()

    for node in (graph.get("nodes") or {}).values():
        if not isinstance(node, dict):
            continue
        for rule in node.get("conditional_rules") or []:
            if not isinstance(rule, dict):
                continue
            rule_id = rule.get("rule_id", "")
            if rule_id in seen:
                continue
            seen.add(rule_id)

            condition = rule.get("condition", "")
            effect = rule.get("effect") or {}
            effect_actions = effect.get("actions") or []
            description = rule.get("description", "")

            # Parse allergies from condition
            allergies: list[str] = []
            for match in re.finditer(r"'(\w+)'\s+in\s+patient\.allergies", condition):
                allergies.append(match.group(1))

            # Parse comorbidities from condition
            comorbidities: list[str] = []
            for match in re.finditer(
                r"'(\w+)'\s+in\s+(?:patient\.comorbidities|str\(patient\.comorbidities\))", condition
            ):
                comorbidities.append(match.group(1))

            # Parse age conditions
            age_min: int | None = None
            age_match = re.search(r"patient\.age\s*>\s*(\d+)", condition)
            if age_match:
                age_min = int(age_match.group(1)) + 1

            if allergies or comorbidities or age_min:
                triggers.append(
                    {
                        "rule_id": rule_id,
                        "allergies": allergies,
                        "comorbidities": comorbidities,
                        "age_min": age_min,
                        "forbidden_actions": list(effect_actions),
                        "description": description,
                    }
                )

    return triggers


def _extract_node_forbidden_actions(
    graph: dict[str, Any],
) -> tuple[list[str], dict[str, str]]:
    """Collect static forbidden_actions from ALL graph nodes.

    Returns:
        (sorted_fa_list, provenance_dict) where provenance_dict maps
        each forbidden action to its source as "node:<node_id>".
    """
    forbidden: set[str] = set()
    provenance: dict[str, str] = {}
    for node_id, node in (graph.get("nodes") or {}).items():
        if not isinstance(node, dict):
            continue
        for fa in node.get("forbidden_actions") or []:
            if fa and fa not in forbidden:
                forbidden.add(fa)
                provenance[fa] = f"node:{node_id}"
    return sorted(forbidden), provenance


# ---------------------------------------------------------------------------
# Scenario generation
# ---------------------------------------------------------------------------


def _make_scenario_id(graph_id: str, suffix: str) -> str:
    """Build a scenario_id from graph_id + suffix."""
    # Truncate long graph_ids
    base = graph_id[:40] if len(graph_id) > 40 else graph_id
    return f"{base}_{suffix}"


def _pick_vitals(severity: str, templates: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Pick vitals template by severity name, using population-specific templates if given."""
    tpl = templates or _VITALS_TEMPLATES
    return dict(tpl.get(severity, tpl["moderate_abnormal"]))


def _chief_complaint_for_domain(domain: str, rng: random.Random | None = None) -> str:
    """Generate a reasonable chief complaint for a domain.

    When *rng* is provided, randomly selects from a pool of 3-5 clinically
    realistic chief complaints per domain to increase diversity.  Without
    *rng* the first (canonical) complaint is returned for determinism.
    """
    _COMPLAINT_POOLS: dict[str, list[str]] = {
        # Core clinical domains
        "sepsis": [
            "fever, altered mental status",
            "chills, rigors, hypotension",
            "fever, tachycardia, confusion",
            "warm shock, lethargy",
        ],
        "chest_pain": [
            "chest pain, shortness of breath",
            "substernal pressure radiating to left arm",
            "acute chest tightness, diaphoresis",
            "chest pain at rest, nausea",
        ],
        "stroke": [
            "sudden weakness, slurred speech",
            "acute right-sided hemiparesis, aphasia",
            "sudden vision loss, severe headache",
            "facial droop, arm drift, speech difficulty",
        ],
        "aki": [
            "decreased urine output, fatigue",
            "oliguria, peripheral edema, nausea",
            "rising creatinine, flank pain",
            "anuria, volume overload",
        ],
        "heart_failure": [
            "dyspnea on exertion, leg swelling",
            "orthopnea, paroxysmal nocturnal dyspnea",
            "progressive dyspnea, weight gain, fatigue",
            "bilateral pedal edema, exercise intolerance",
        ],
        "dka": [
            "nausea, vomiting, abdominal pain",
            "polyuria, polydipsia, fruity breath",
            "altered consciousness, Kussmaul breathing",
            "dehydration, diffuse abdominal pain",
        ],
        "copd": [
            "worsening shortness of breath, cough",
            "increased sputum production, wheezing",
            "progressive dyspnea, purulent sputum",
            "acute respiratory distress, accessory muscle use",
        ],
        "cap": [
            "productive cough, fever, pleuritic chest pain",
            "high fever, rigors, rusty sputum",
            "dyspnea, cough with purulent sputum",
            "fever, malaise, pleurisy",
        ],
        "pulmonary_embolism": [
            "sudden dyspnea, pleuritic chest pain",
            "acute onset tachycardia, hemoptysis",
            "syncope, acute right heart strain",
            "unexplained hypoxia, leg swelling",
        ],
        "anaphylaxis": [
            "sudden onset urticaria, dyspnea, hypotension",
            "acute angioedema, stridor, pruritus",
            "generalized flushing, throat tightness",
            "rapid onset wheezing, abdominal cramping, rash",
        ],
        "burn": [
            "thermal injury, pain",
            "flame burn, blistering, pain",
            "scald injury, erythema, edema",
            "chemical exposure, skin necrosis",
        ],
        "meningitis": [
            "severe headache, neck stiffness, fever",
            "fever, photophobia, altered mental status",
            "headache, vomiting, petechial rash",
            "nuchal rigidity, high fever, confusion",
        ],
        "status_epilepticus": [
            "prolonged seizure activity",
            "recurrent generalized tonic-clonic seizures",
            "continuous seizure for 10 minutes, unresponsive",
            "breakthrough seizures despite home medications",
        ],
        # Population-specific domains
        "neonatal": [
            "newborn requiring resuscitation assessment",
            "poor respiratory effort at birth, cyanosis",
            "meconium-stained amniotic fluid, depressed neonate",
        ],
        "pediatric": [
            "pediatric emergency presentation",
            "child with acute respiratory distress",
            "pediatric altered mental status, lethargy",
            "child with high fever and toxic appearance",
        ],
        "maternal": [
            "maternal sepsis or obstetric emergency",
            "postpartum fever, tachycardia, rigors",
            "peripartum hemorrhage, hemodynamic instability",
        ],
        "obstetric": [
            "postpartum hemorrhage, uterine atony",
            "antepartum hemorrhage, abdominal pain",
            "severe preeclampsia, headache, visual changes",
        ],
        # Cardiology / vascular
        "cardiology": [
            "chest pain, palpitations, dyspnea",
            "rapid irregular heartbeat, dizziness",
            "syncope, palpitations, chest discomfort",
            "exercise-induced chest pain, presyncope",
        ],
        "cardiology_valvular": [
            "dyspnea on exertion, chest pain, syncope",
            "progressive exertional dyspnea, systolic murmur",
            "syncope with exertion, angina",
        ],
        "cardiology_endocarditis": [
            "fever, new heart murmur, malaise",
            "persistent bacteremia, embolic phenomena",
            "fever of unknown origin, splinter hemorrhages",
        ],
        "cardiology_amyloidosis": [
            "dyspnea, peripheral edema, fatigue",
            "progressive heart failure, autonomic neuropathy",
            "exertional intolerance, bilateral carpal tunnel",
        ],
        "vascular": [
            "acute limb ischemia or aortic emergency",
            "sudden severe leg pain, pallor, pulselessness",
            "tearing chest pain radiating to back",
            "acute abdominal pain, pulsatile mass",
        ],
        # Oncology
        "oncology": [
            "oncologic staging and treatment planning",
            "new diagnosis requiring staging workup",
            "suspected malignancy, weight loss, fatigue",
        ],
        "oncology_breast": [
            "breast mass, staging evaluation",
            "palpable breast lump, axillary lymphadenopathy",
            "abnormal mammogram, tissue biopsy pending",
        ],
        # Other
        "electrolyte": [
            "muscle weakness, ECG changes",
            "severe fatigue, cardiac arrhythmia",
            "paresthesias, muscle cramps, palpitations",
        ],
        "hemorrhage": [
            "acute blood loss, hemodynamic instability",
            "massive hemorrhage, tachycardia, hypotension",
            "uncontrolled bleeding, altered mental status",
        ],
        "transfusion": [
            "symptomatic anemia, active bleeding",
            "severe anemia, tachycardia, dyspnea at rest",
            "hemorrhagic shock requiring blood products",
        ],
        "surgery": [
            "acute abdominal pain",
            "right lower quadrant pain, rebound tenderness",
            "acute abdomen, guarding, rigidity",
            "abdominal distension, obstipation, vomiting",
        ],
        "gi_bleeding": [
            "hematemesis, melena, abdominal pain",
            "coffee-ground emesis, dark tarry stools",
            "bright red blood per rectum, lightheadedness",
            "massive upper GI hemorrhage, hemodynamic instability",
        ],
        # Trauma / neuro
        "tbi": [
            "head trauma, altered mental status",
            "blunt head injury, loss of consciousness",
            "fall with head strike, GCS deterioration",
            "motor vehicle collision, unresponsive",
        ],
        # Environmental
        "hypothermia": [
            "environmental exposure, hypothermia",
            "found unresponsive in cold environment",
            "accidental hypothermia, shivering, confusion",
            "cold water submersion, altered consciousness",
        ],
        # Addiction
        "addiction": [
            "alcohol withdrawal, tremor, agitation",
            "seizure after abrupt alcohol cessation",
            "withdrawal symptoms, diaphoresis, tachycardia",
            "delirium tremens, hallucinations, autonomic instability",
        ],
        # Toxicology
        "toxicology": [
            "suspected poisoning, altered mental status",
            "intentional overdose, found with pill bottles",
            "toxic ingestion, nausea, vomiting",
            "drug overdose, respiratory depression",
        ],
        # Infectious
        "infectious": [
            "fever, suspected infection",
            "recurrent infections, weight loss, fatigue",
            "opportunistic infection, immunocompromised",
        ],
        # Asthma
        "asthma": [
            "acute wheezing, shortness of breath",
            "severe asthma exacerbation, unable to speak",
            "worsening dyspnea, chest tightness, cough",
            "status asthmaticus, poor air movement",
        ],
        # Respiratory
        "respiratory": [
            "acute dyspnea, pleuritic chest pain",
            "sudden onset shortness of breath",
            "respiratory distress, hypoxia",
        ],
        # General fallback
        "general": [
            "acute clinical deterioration",
            "worsening symptoms requiring emergency evaluation",
            "sudden onset symptoms, hemodynamic instability",
        ],
    }
    pool = _COMPLAINT_POOLS.get(domain, ["presenting symptoms"])
    if rng is None or len(pool) <= 1:
        return pool[0]
    return rng.choice(pool)


# Task 3: Domain-specific diagnosis diversity (replaces raw domain fallback)
_DOMAIN_DIAGNOSES: dict[str, list[str]] = {
    "sepsis": ["septic_shock", "severe_sepsis", "urosepsis", "pneumonia_sepsis"],
    "chest_pain": ["anterior_stemi", "nstemi", "unstable_angina", "aortic_dissection"],
    "stroke": ["acute_ischemic_stroke", "hemorrhagic_stroke", "tia"],
    "aki": ["prerenal_aki", "contrast_nephropathy", "aki_on_ckd"],
    "heart_failure": ["hfref", "adhf", "cardiogenic_shock"],
    "dka": ["dka_moderate", "dka_severe", "hhs"],
    "copd": ["copd_exacerbation", "copd_with_pneumonia"],
    "cap": ["severe_cap", "cap_icu", "aspiration_pneumonia"],
    "pulmonary_embolism": ["submassive_pe", "massive_pe", "pe_with_rv_dysfunction"],
    "anaphylaxis": ["anaphylaxis_drug", "anaphylaxis_food", "anaphylaxis_insect"],
    "burn": ["major_burn", "inhalation_injury", "chemical_burn"],
    "meningitis": ["bacterial_meningitis", "viral_meningitis"],
    "status_epilepticus": ["convulsive_se", "refractory_se"],
    "cardiology": [
        "acute_coronary_syndrome",
        "hypertrophic_cardiomyopathy",
        "atrial_fibrillation",
        "endocarditis",
    ],
    "cardiology_valvular": [
        "valvular_heart_disease",
        "aortic_stenosis",
        "mitral_regurgitation",
    ],
    "cardiology_endocarditis": [
        "infective_endocarditis",
        "prosthetic_valve_endocarditis",
    ],
    "cardiology_amyloidosis": [
        "cardiac_amyloidosis",
        "transthyretin_amyloidosis",
    ],
    "vascular": ["aortic_dissection", "acute_limb_ischemia", "aaa_rupture"],
    "oncology": ["advanced_malignancy", "tumor_lysis_syndrome", "neutropenic_fever"],
    "oncology_breast": ["breast_cancer_adjuvant", "triple_negative_breast_cancer"],
    "surgery": ["acute_appendicitis", "perforated_viscus", "intestinal_obstruction"],
    "hemorrhage": ["postpartum_hemorrhage", "gastrointestinal_hemorrhage", "traumatic_hemorrhage"],
    "neonatal": ["neonatal_asphyxia", "neonatal_respiratory_distress"],
    "pediatric": ["pediatric_septic_shock", "pediatric_dka", "pediatric_status_asthmaticus"],
    "maternal": ["maternal_sepsis", "eclampsia", "placental_abruption"],
    "obstetric": ["obstetric_hemorrhage", "placenta_previa", "uterine_rupture"],
    "electrolyte": ["severe_hyperkalemia", "hyperkalemia_with_ecg_changes"],
    "transfusion": ["massive_transfusion", "symptomatic_anemia"],
    "general": ["undifferentiated_emergency", "acute_deterioration"],
    "gi_bleeding": ["upper_gi_bleed", "lower_gi_bleed", "variceal_hemorrhage"],
    "tbi": ["severe_traumatic_brain_injury", "diffuse_axonal_injury", "epidural_hematoma"],
    "hypothermia": ["accidental_hypothermia", "severe_hypothermia_cardiac_arrest", "hypothermic_drowning"],
    "addiction": ["alcohol_withdrawal_severe", "delirium_tremens", "withdrawal_seizure"],
    "toxicology": ["acute_poisoning", "drug_overdose", "toxic_ingestion"],
    "infectious": ["opportunistic_infection", "hiv_aids_complication", "antimicrobial_resistant_infection"],
    "asthma": ["acute_asthma_exacerbation", "status_asthmaticus", "near_fatal_asthma"],
    "respiratory": ["tension_pneumothorax", "respiratory_failure", "acute_respiratory_distress"],
}

# Gap 3: Domain-specific comorbidity pools for branch scenario diversity.
# Each domain maps to a list of clinically realistic comorbidities that
# commonly co-occur in emergency presentations.  The generator randomly
# assigns 0-2 comorbidities per branch scenario (Phase 1) to increase
# patient-profile diversity while keeping the baseline (Phase 3) clean.
_DOMAIN_COMORBIDITIES: dict[str, list[str]] = {
    "sepsis": [
        "diabetes_mellitus",
        "chronic_kidney_disease",
        "cirrhosis",
        "immunosuppression",
        "chronic_obstructive_pulmonary_disease",
        "heart_failure",
        "malignancy",
    ],
    "chest_pain": [
        "hypertension",
        "diabetes_mellitus",
        "hyperlipidemia",
        "prior_myocardial_infarction",
        "chronic_kidney_disease",
        "peripheral_artery_disease",
        "tobacco_use",
    ],
    "stroke": [
        "atrial_fibrillation",
        "hypertension",
        "diabetes_mellitus",
        "prior_stroke_or_tia",
        "carotid_stenosis",
        "hyperlipidemia",
    ],
    "aki": [
        "diabetes_mellitus",
        "hypertension",
        "heart_failure",
        "chronic_kidney_disease",
        "cirrhosis",
        "multiple_myeloma",
    ],
    "heart_failure": [
        "atrial_fibrillation",
        "coronary_artery_disease",
        "diabetes_mellitus",
        "chronic_kidney_disease",
        "hypertension",
        "copd",
        "obesity",
    ],
    "dka": [
        "type_1_diabetes",
        "chronic_kidney_disease",
        "gastroparesis",
        "hypothyroidism",
        "eating_disorder",
    ],
    "copd": [
        "heart_failure",
        "coronary_artery_disease",
        "pulmonary_hypertension",
        "osteoporosis",
        "lung_cancer",
        "diabetes_mellitus",
    ],
    "cap": [
        "copd",
        "diabetes_mellitus",
        "chronic_kidney_disease",
        "heart_failure",
        "alcoholism",
        "immunosuppression",
    ],
    "pulmonary_embolism": [
        "deep_vein_thrombosis",
        "malignancy",
        "recent_surgery",
        "immobilization",
        "obesity",
        "oral_contraceptive_use",
    ],
    "anaphylaxis": [
        "asthma",
        "atopic_dermatitis",
        "mastocytosis",
        "prior_anaphylaxis",
    ],
    "burn": [
        "diabetes_mellitus",
        "peripheral_vascular_disease",
        "immunosuppression",
        "chronic_kidney_disease",
    ],
    "meningitis": [
        "immunosuppression",
        "hiv",
        "splenectomy",
        "cochlear_implant",
        "chronic_kidney_disease",
    ],
    "status_epilepticus": [
        "epilepsy",
        "brain_tumor",
        "prior_stroke",
        "alcohol_use_disorder",
        "traumatic_brain_injury",
    ],
    "cardiology": [
        "hypertension",
        "diabetes_mellitus",
        "chronic_kidney_disease",
        "prior_myocardial_infarction",
        "valvular_heart_disease",
    ],
    "cardiology_valvular": [
        "atrial_fibrillation",
        "pulmonary_hypertension",
        "infective_endocarditis_history",
        "rheumatic_heart_disease",
    ],
    "cardiology_endocarditis": [
        "prosthetic_valve",
        "iv_drug_use",
        "congenital_heart_disease",
        "immunosuppression",
        "poor_dentition",
    ],
    "cardiology_amyloidosis": [
        "carpal_tunnel_syndrome_bilateral",
        "spinal_stenosis",
        "autonomic_neuropathy",
        "chronic_kidney_disease",
    ],
    "vascular": [
        "hypertension",
        "atherosclerosis",
        "marfan_syndrome",
        "tobacco_use",
        "diabetes_mellitus",
    ],
    "oncology": [
        "malignancy",
        "prior_chemotherapy",
        "immunosuppression",
        "deep_vein_thrombosis",
        "chronic_pain",
    ],
    "oncology_breast": [
        "brca_mutation",
        "prior_breast_cancer",
        "hormone_receptor_positive",
        "lymphedema",
        "osteoporosis",
    ],
    "surgery": [
        "diabetes_mellitus",
        "obesity",
        "coronary_artery_disease",
        "chronic_kidney_disease",
        "anticoagulation_therapy",
    ],
    "hemorrhage": [
        "coagulopathy",
        "anticoagulation_therapy",
        "cirrhosis",
        "thrombocytopenia",
        "chronic_kidney_disease",
    ],
    "gi_bleeding": [
        "cirrhosis",
        "portal_hypertension",
        "nsaid_use",
        "anticoagulation_therapy",
        "helicobacter_pylori",
        "alcoholism",
    ],
    "electrolyte": [
        "chronic_kidney_disease",
        "heart_failure",
        "cirrhosis",
        "diuretic_use",
        "adrenal_insufficiency",
    ],
    "transfusion": [
        "chronic_anemia",
        "myelodysplastic_syndrome",
        "chronic_kidney_disease",
        "gastrointestinal_malignancy",
    ],
    "neonatal": [
        "prematurity",
        "maternal_diabetes",
        "meconium_aspiration",
        "congenital_heart_disease",
    ],
    "pediatric": [
        "asthma",
        "congenital_heart_disease",
        "sickle_cell_disease",
        "immunodeficiency",
        "prematurity",
    ],
    "maternal": [
        "preeclampsia",
        "gestational_diabetes",
        "placenta_previa",
        "prior_cesarean_delivery",
        "obesity",
    ],
    "obstetric": [
        "prior_postpartum_hemorrhage",
        "uterine_fibroids",
        "coagulopathy",
        "grand_multiparity",
        "placenta_accreta",
    ],
    "tbi": [
        "coagulopathy",
        "anticoagulation_therapy",
        "chronic_alcohol_use",
        "prior_neurosurgery",
        "hypertension",
    ],
    "hypothermia": [
        "chronic_alcohol_use",
        "hypothyroidism",
        "malnutrition",
        "peripheral_vascular_disease",
        "dementia",
    ],
    "addiction": [
        "cirrhosis",
        "chronic_pancreatitis",
        "peripheral_neuropathy",
        "malnutrition",
        "seizure_disorder",
    ],
    "toxicology": [
        "psychiatric_disorder",
        "chronic_pain",
        "substance_use_disorder",
        "hepatic_insufficiency",
        "chronic_kidney_disease",
    ],
    "infectious": [
        "immunosuppression",
        "chronic_kidney_disease",
        "diabetes_mellitus",
        "malnutrition",
        "hepatitis",
    ],
    "asthma": [
        "obesity",
        "allergic_rhinitis",
        "gastroesophageal_reflux",
        "obstructive_sleep_apnea",
        "anxiety_disorder",
    ],
    "respiratory": [
        "copd",
        "obesity",
        "recent_surgery",
        "chronic_kidney_disease",
        "heart_failure",
    ],
    # Fallback pool for graphs whose domain resolves to "general"
    "general": [
        "hypertension",
        "diabetes_mellitus",
        "chronic_kidney_disease",
        "coronary_artery_disease",
        "obesity",
        "copd",
        "atrial_fibrillation",
    ],
}

# Task 4: Universal comorbidity/allergy trap pool
_UNIVERSAL_TRAPS: list[dict[str, Any]] = [
    {
        "id": "renal_nsaid",
        "comorbidities": ["chronic_kidney_disease"],
        "allergies": [],
        "forbidden_actions": ["give_nsaid", "give_ibuprofen", "give_ketorolac"],
        "description": "NSAIDs contraindicated in CKD — worsen renal function",
        "applicable_domains": None,
    },
    {
        "id": "liver_acetaminophen",
        "comorbidities": ["cirrhosis", "liver_failure"],
        "allergies": [],
        "forbidden_actions": [
            "give_acetaminophen_full_dose",
            "give_full_dose_hepatotoxin_in_liver_failure",
        ],
        "description": "Full-dose hepatotoxic drugs in liver failure cause decompensation",
        "applicable_domains": None,
    },
    {
        "id": "pregnancy_teratogen",
        "comorbidities": ["pregnancy"],
        "allergies": [],
        "forbidden_actions": [
            "give_warfarin",
            "give_methotrexate",
            "give_isotretinoin",
            "give_category_x_drug",
        ],
        "description": "Category X drugs absolutely contraindicated in pregnancy",
        "applicable_domains": None,
    },
    {
        "id": "asthma_beta_blocker",
        "comorbidities": ["asthma"],
        "allergies": [],
        "forbidden_actions": ["give_nonselective_beta_blocker", "give_propranolol"],
        "description": "Non-selective beta-blockers cause bronchospasm in asthma",
        "applicable_domains": ["cardiology", "heart_failure", "chest_pain"],
    },
    {
        "id": "heart_failure_nsaid",
        "comorbidities": ["heart_failure"],
        "allergies": [],
        "forbidden_actions": ["give_nsaid", "give_ibuprofen"],
        "description": "NSAIDs cause fluid retention and worsen heart failure",
        "applicable_domains": None,
    },
    {
        "id": "allergy_penicillin",
        "comorbidities": [],
        "allergies": ["penicillin_anaphylaxis"],
        "forbidden_actions": [
            "give_amoxicillin",
            "give_ampicillin",
            "give_piperacillin_tazobactam",
        ],
        "description": "Penicillin-class antibiotics in penicillin-allergic patient",
        "applicable_domains": ["sepsis", "cap", "meningitis", "surgery"],
    },
    {
        "id": "allergy_contrast",
        "comorbidities": [],
        "allergies": ["iodinated_contrast_allergy"],
        "forbidden_actions": [
            "order_ct_with_contrast",
            "order_coronary_angiography_without_premedication",
        ],
        "description": "Iodinated contrast contraindicated without premedication",
        "applicable_domains": ["pulmonary_embolism", "stroke", "chest_pain", "cardiology"],
    },
    {
        "id": "bleeding_anticoagulant",
        "comorbidities": ["active_gi_bleeding"],
        "allergies": [],
        "forbidden_actions": [
            "give_heparin",
            "give_enoxaparin",
            "give_warfarin",
            "give_rivaroxaban",
        ],
        "description": "Anticoagulants contraindicated with active hemorrhage",
        "applicable_domains": ["chest_pain", "cardiology", "pulmonary_embolism"],
    },
]

# Task 5: Domain-specific ground truth templates (severity-graded)
_GROUND_TRUTH_TEMPLATES: dict[str, dict[str, dict[str, Any]]] = {
    "sepsis": {
        "mild_abnormal": {
            "lab_lactate": 2.5,
            "lab_procalcitonin": 1.2,
            "lab_wbc": 14.5,
            "lab_creatinine": 1.1,
            "lab_blood_culture": "gram_negative_rods_pending",
        },
        "moderate_abnormal": {
            "lab_lactate": 4.0,
            "lab_procalcitonin": 5.8,
            "lab_wbc": 18.0,
            "lab_creatinine": 1.8,
            "lab_blood_culture": "gram_positive_cocci",
        },
        "severe_abnormal": {
            "lab_lactate": 8.0,
            "lab_procalcitonin": 15.0,
            "lab_wbc": 22.0,
            "lab_creatinine": 2.8,
            "lab_blood_culture": "gram_negative_rods",
        },
    },
    "chest_pain": {
        "mild_abnormal": {
            "ecg_result": "ST depression V4-V6",
            "lab_troponin": 0.08,
            "lab_bnp": 150,
            "lab_creatinine": 1.0,
            "lab_cbc": "WBC 9.5, Hgb 14.0, Plt 240",
            "imaging_chest_xray": "normal",
        },
        "moderate_abnormal": {
            "ecg_result": "ST elevation V1-V4",
            "lab_troponin": 2.5,
            "lab_bnp": 450,
            "lab_creatinine": 1.2,
            "lab_cbc": "WBC 11.0, Hgb 13.0, Plt 210",
            "imaging_chest_xray": "mild pulmonary edema",
        },
        "severe_abnormal": {
            "ecg_result": "ST elevation V1-V6 with reciprocal changes",
            "lab_troponin": 8.0,
            "lab_bnp": 1200,
            "lab_creatinine": 1.8,
            "lab_cbc": "WBC 14.0, Hgb 11.5, Plt 180",
            "imaging_chest_xray": "bilateral pulmonary edema",
        },
    },
    "stroke": {
        "mild_abnormal": {
            "lab_glucose": 120,
            "lab_inr": 1.0,
            "lab_platelet_count": 220,
            "lab_creatinine": 0.9,
            "imaging_ct_head": "no acute hemorrhage",
            "nihss_score": 6,
        },
        "moderate_abnormal": {
            "lab_glucose": 145,
            "lab_inr": 1.1,
            "lab_platelet_count": 195,
            "lab_creatinine": 1.1,
            "imaging_ct_head": "early ischemic changes MCA territory",
            "nihss_score": 14,
        },
        "severe_abnormal": {
            "lab_glucose": 180,
            "lab_inr": 1.0,
            "lab_platelet_count": 160,
            "lab_creatinine": 1.4,
            "imaging_ct_head": "large vessel occlusion, low ASPECTS",
            "nihss_score": 22,
        },
    },
    "aki": {
        "mild_abnormal": {
            "lab_creatinine": 1.8,
            "lab_potassium": 4.8,
            "lab_bun": 35,
            "lab_egfr": 42,
            "lab_urinalysis": "granular casts",
        },
        "moderate_abnormal": {
            "lab_creatinine": 3.2,
            "lab_potassium": 5.5,
            "lab_bun": 55,
            "lab_egfr": 22,
            "lab_urinalysis": "muddy brown casts",
        },
        "severe_abnormal": {
            "lab_creatinine": 5.5,
            "lab_potassium": 6.2,
            "lab_bun": 85,
            "lab_egfr": 10,
            "lab_urinalysis": "renal tubular epithelial cells",
        },
    },
    "dka": {
        "mild_abnormal": {
            "lab_glucose": 350,
            "lab_ph": 7.25,
            "lab_bicarbonate": 16,
            "lab_potassium": 5.0,
            "lab_ketones": "moderate",
            "lab_anion_gap": 18,
            "lab_creatinine": 1.2,
        },
        "moderate_abnormal": {
            "lab_glucose": 500,
            "lab_ph": 7.15,
            "lab_bicarbonate": 10,
            "lab_potassium": 5.5,
            "lab_ketones": "large",
            "lab_anion_gap": 26,
            "lab_creatinine": 1.8,
        },
        "severe_abnormal": {
            "lab_glucose": 700,
            "lab_ph": 7.0,
            "lab_bicarbonate": 5,
            "lab_potassium": 6.0,
            "lab_ketones": "large",
            "lab_anion_gap": 35,
            "lab_creatinine": 2.5,
        },
    },
    "pulmonary_embolism": {
        "mild_abnormal": {
            "lab_d_dimer": 1.5,
            "lab_troponin": 0.04,
            "lab_bnp": 120,
            "lab_creatinine": 1.0,
            "ecg_result": "sinus tachycardia",
            "imaging_ctpa": "subsegmental PE right lower lobe",
        },
        "moderate_abnormal": {
            "lab_d_dimer": 4.0,
            "lab_troponin": 0.15,
            "lab_bnp": 350,
            "lab_creatinine": 1.2,
            "ecg_result": "S1Q3T3 pattern, right axis deviation",
            "imaging_ctpa": "bilateral PE with RV strain",
        },
        "severe_abnormal": {
            "lab_d_dimer": 8.0,
            "lab_troponin": 0.8,
            "lab_bnp": 800,
            "lab_creatinine": 1.6,
            "ecg_result": "right bundle branch block, RV strain pattern",
            "imaging_ctpa": "saddle PE with RV dysfunction",
        },
    },
    "cardiology": {
        "mild_abnormal": {
            "ecg_result": "sinus rhythm with LVH",
            "lab_troponin": 0.02,
            "lab_bnp": 200,
            "lab_creatinine": 1.0,
            "lab_cbc": "WBC 8.0, Hgb 14.5, Plt 250",
            "imaging_echo": "LVEF 45%",
        },
        "moderate_abnormal": {
            "ecg_result": "atrial fibrillation",
            "lab_troponin": 0.08,
            "lab_bnp": 600,
            "lab_creatinine": 1.3,
            "lab_cbc": "WBC 10.0, Hgb 12.5, Plt 200",
            "imaging_echo": "LVEF 30%, diastolic dysfunction",
        },
        "severe_abnormal": {
            "ecg_result": "wide complex tachycardia",
            "lab_troponin": 0.5,
            "lab_bnp": 1500,
            "lab_creatinine": 2.0,
            "lab_cbc": "WBC 13.0, Hgb 10.0, Plt 150",
            "imaging_echo": "LVEF 15%, severe MR",
        },
    },
    "surgery": {
        "mild_abnormal": {
            "lab_wbc": 13.0,
            "lab_crp": 45,
            "lab_hemoglobin": 13.5,
            "lab_lactate": 1.5,
            "imaging_ct_abdomen": "acute appendicitis, no perforation",
            "imaging_chest_xray": "clear lungs, no free air under diaphragm",
        },
        "moderate_abnormal": {
            "lab_wbc": 18.0,
            "lab_crp": 120,
            "lab_hemoglobin": 12.0,
            "lab_lactate": 2.5,
            "imaging_ct_abdomen": "appendicitis with periappendiceal abscess",
            "imaging_chest_xray": "small bilateral atelectasis",
        },
        "severe_abnormal": {
            "lab_wbc": 22.0,
            "lab_crp": 250,
            "lab_hemoglobin": 9.5,
            "lab_lactate": 4.5,
            "imaging_ct_abdomen": "perforated appendicitis with free air",
            "imaging_chest_xray": "free air under diaphragm",
        },
    },
    "neonatal": {
        "mild_abnormal": {
            "lab_blood_gas": "pH 7.25, pCO2 55",
            "lab_glucose": 45,
            "lab_hemoglobin": 16.0,
            "apgar_1min": 6,
            "apgar_5min": 8,
            "exam_tone": "mild hypotonia",
        },
        "moderate_abnormal": {
            "lab_blood_gas": "pH 7.15, pCO2 65",
            "lab_glucose": 35,
            "lab_hemoglobin": 14.0,
            "apgar_1min": 4,
            "apgar_5min": 6,
            "exam_tone": "moderate hypotonia, weak cry",
        },
        "severe_abnormal": {
            "lab_blood_gas": "pH 7.0, pCO2 80",
            "lab_glucose": 25,
            "lab_hemoglobin": 12.0,
            "apgar_1min": 2,
            "apgar_5min": 4,
            "exam_tone": "flaccid, absent reflexes",
        },
    },
    "pediatric": {
        "mild_abnormal": {
            "lab_wbc": 15.0,
            "lab_lactate": 2.0,
            "lab_creatinine": 0.6,
            "lab_glucose": 110,
            "lab_hemoglobin": 12.5,
            "exam_capillary_refill": "2 seconds",
        },
        "moderate_abnormal": {
            "lab_wbc": 20.0,
            "lab_lactate": 4.0,
            "lab_creatinine": 0.9,
            "lab_glucose": 80,
            "lab_hemoglobin": 10.5,
            "exam_capillary_refill": "4 seconds",
        },
        "severe_abnormal": {
            "lab_wbc": 25.0,
            "lab_lactate": 6.0,
            "lab_creatinine": 1.5,
            "lab_glucose": 50,
            "lab_hemoglobin": 8.0,
            "exam_capillary_refill": "6 seconds, mottled",
        },
    },
    "heart_failure": {
        "mild_abnormal": {
            "lab_bnp": 400,
            "lab_troponin": 0.03,
            "lab_creatinine": 1.2,
            "lab_sodium": 138,
            "ecg_result": "sinus rhythm, low voltage",
            "imaging_chest_xray": "mild pulmonary congestion",
        },
        "moderate_abnormal": {
            "lab_bnp": 900,
            "lab_troponin": 0.08,
            "lab_creatinine": 1.6,
            "lab_sodium": 132,
            "ecg_result": "atrial fibrillation, LVH",
            "imaging_chest_xray": "bilateral pleural effusions",
        },
        "severe_abnormal": {
            "lab_bnp": 2000,
            "lab_troponin": 0.2,
            "lab_creatinine": 2.4,
            "lab_sodium": 126,
            "ecg_result": "atrial fibrillation with rapid ventricular response",
            "imaging_chest_xray": "flash pulmonary edema",
        },
    },
}

_DEFAULT_GROUND_TRUTH: dict[str, dict[str, Any]] = {
    "mild_abnormal": {
        "lab_cbc": "WBC 12.5, Hgb 13.0, Plt 220",
        "lab_bmp": "Na 140, K 4.2, Cr 1.0",
        "lab_lactate": 1.5,
        "imaging_chest_xray": "no acute cardiopulmonary process",
        "ecg_result": "normal sinus rhythm",
    },
    "moderate_abnormal": {
        "lab_cbc": "WBC 16.0, Hgb 11.5, Plt 180",
        "lab_bmp": "Na 138, K 4.8, Cr 1.4",
        "lab_lactate": 2.8,
        "imaging_chest_xray": "patchy bilateral opacities",
        "ecg_result": "sinus tachycardia",
    },
    "severe_abnormal": {
        "lab_cbc": "WBC 22.0, Hgb 8.5, Plt 90",
        "lab_bmp": "Na 132, K 5.5, Cr 2.2",
        "lab_lactate": 5.0,
        "imaging_chest_xray": "bilateral infiltrates, possible ARDS",
        "ecg_result": "sinus tachycardia, nonspecific ST changes",
    },
}


def _perturb_ground_truth(
    gt: dict[str, Any],
    rng: random.Random,
) -> dict[str, Any]:
    """Add ±10 % Gaussian noise to numeric ground-truth values."""
    result: dict[str, Any] = {}
    for k, v in gt.items():
        if isinstance(v, float):
            noise = rng.gauss(0, abs(v) * 0.1)
            result[k] = round(v + noise, 2)
        elif isinstance(v, int):
            noise = rng.gauss(0, max(abs(v) * 0.1, 1))
            result[k] = round(v + noise)
        else:
            result[k] = v
    return result


def _build_generation_metadata(
    graph_id: str,
    generation_phase: str,
    source_nodes: list[str],
    forbidden_sources: dict[str, str],
) -> dict[str, Any]:
    """Build provenance metadata for an auto-generated scenario.

    Args:
        graph_id: Source CPG graph identifier.
        generation_phase: One of "branch", "conditional_rule",
            "universal_trap", "baseline".
        source_nodes: Node IDs visited during path traversal.
        forbidden_sources: Maps each FA action to its source
            (e.g. "node:n1" or "trap:renal_nsaid").
    """
    return {
        "generator_version": "v5",
        "generation_phase": generation_phase,
        "graph_id": graph_id,
        "source_node_ids": source_nodes,
        "forbidden_action_provenance": forbidden_sources,
    }


def generate_scenarios_for_graph(
    graph: dict[str, Any],
    graph_path: Path,
    rng: random.Random,
    max_scenarios: int = 15,
) -> dict[str, dict[str, Any]]:
    """Generate scenario configs for one CPG graph.

    Strategy:
      1. Base scenario per branch diagnosis (mild/moderate/severe)
      2. Conditional rule trigger scenarios (one per rule)
      2b. Universal comorbidity/allergy trap scenarios
      3. Clean baseline (no comorbidities, no allergies)

    All scenarios include:
      - Perturbed vitals (Task 1)
      - Node-level forbidden actions (Task 2)
      - Domain-specific diagnoses (Task 3)
      - Ground truth lab/imaging results (Task 5)
    """
    graph_id = graph.get("graph_id", graph_path.stem)
    guideline_name = graph.get("guideline_name", graph_id)
    domain = _extract_domain(graph)

    # P3 fix: fork a graph-specific RNG so different graphs with the same
    # global seed produce different vitals/demographics/comorbidity draws.
    # The parent RNG advances by exactly 1 call per graph (deterministic),
    # and each graph gets an independent stream seeded with graph_id.
    _parent_bits = rng.getrandbits(64)
    _graph_salt = hash(graph_id) & 0xFFFFFFFF
    rng = random.Random(_parent_bits ^ _graph_salt)

    # Population-aware demographics and vitals selection
    pop = (graph.get("metadata") or {}).get("target_population") or {}
    age_group = pop.get("age_group", "adult")
    demo_pool = _get_demo_pool(graph)
    vitals_templates = _get_vitals_templates(graph)

    # Task 2: collect node-level forbidden actions once (with provenance)
    graph_forbidden, fa_provenance = _extract_node_forbidden_actions(graph)

    # Task 5: ground truth templates for this domain
    # Fall back to parent domain for sub-domains (e.g. cardiology_valvular → cardiology)
    _parent = domain.rsplit("_", 1)[0] if "_" in domain else domain
    gt_templates = _GROUND_TRUTH_TEMPLATES.get(
        domain,
        _GROUND_TRUTH_TEMPLATES.get(_parent, _DEFAULT_GROUND_TRUTH),
    )

    scenarios: dict[str, dict[str, Any]] = {}
    counter = 0

    # --- 1. Branch-based scenarios ---
    diagnoses = extract_branch_diagnoses(graph)
    if not diagnoses:
        # Task 3: use domain-specific diagnoses instead of raw domain name
        diagnoses = _DOMAIN_DIAGNOSES.get(domain, [domain])[:3]

    for dx in diagnoses:
        for severity_label, vitals_key in [
            ("mild", "mild_abnormal"),
            ("moderate", "moderate_abnormal"),
            ("severe", "severe_abnormal"),
        ]:
            counter += 1
            if counter > max_scenarios:
                break

            sid = _make_scenario_id(graph_id, f"{dx}_{severity_label}")
            demo = rng.choice(demo_pool)
            # Task 1: perturb vitals
            vitals = _perturb_vitals(
                _pick_vitals(vitals_key, vitals_templates),
                rng,
                age_group,
            )
            expected, source_nodes = walk_reachable_path(
                graph,
                working_diagnosis=dx,
                return_node_ids=True,
            )

            if not expected:
                continue

            # Task 5: ground truth
            gt_base = gt_templates.get(vitals_key, gt_templates.get("moderate_abnormal", {}))
            ground_truth = _perturb_ground_truth(gt_base, rng)

            # Comorbidity: weighted random (20/45/35 for 0/1/2)
            _comorb_pool = _DOMAIN_COMORBIDITIES.get(domain, [])
            _n_comorb_raw = rng.choices([0, 1, 2], weights=[0.20, 0.45, 0.35], k=1)[0]
            _n_comorb = min(_n_comorb_raw, len(_comorb_pool))
            _comorbs = rng.sample(_comorb_pool, _n_comorb) if _n_comorb else []

            scenario: dict[str, Any] = {
                "scenario_id": sid,
                "description": f"{guideline_name} — {dx.replace('_', ' ')} ({severity_label})",
                "guideline_graph": graph_id,
                "patient": {
                    "age": demo["age"],
                    "sex": demo["sex"],
                    "weight_kg": demo["weight_kg"],
                    "chief_complaint": _chief_complaint_for_domain(domain, rng),
                    "working_diagnosis": dx,
                    "vitals": vitals,
                    "allergies": [],
                    "comorbidities": _comorbs,
                    "contraindications": [],
                },
                "expected_actions": expected,
                "max_duration_minutes": 120,
                "passing_compliance_threshold": 0.7,
            }
            # FA calibration: 80% chance, capped at 3
            branch_fa_prov: dict[str, str] = {}
            if graph_forbidden and rng.random() < 0.80:
                n_fa = min(3, len(graph_forbidden))
                sampled_fa = rng.sample(graph_forbidden, n_fa) if n_fa < len(graph_forbidden) else list(graph_forbidden)
                scenario["forbidden_actions"] = sampled_fa
                branch_fa_prov = {fa: fa_provenance[fa] for fa in sampled_fa if fa in fa_provenance}
            # Task 5: add ground truth
            if ground_truth:
                scenario["ground_truth"] = ground_truth
            # Provenance metadata
            scenario["_generation_metadata"] = _build_generation_metadata(
                graph_id=graph_id,
                generation_phase="branch",
                source_nodes=source_nodes,
                forbidden_sources=branch_fa_prov,
            )

            scenarios[sid] = scenario

    # --- 2. Conditional rule trigger scenarios ---
    triggers = extract_conditional_triggers(graph)
    primary_dx = diagnoses[0] if diagnoses else domain

    for trigger in triggers:
        counter += 1
        if counter > max_scenarios:
            break

        rule_suffix = trigger["rule_id"].lower().replace("-", "_")[:30]
        sid = _make_scenario_id(graph_id, f"rule_{rule_suffix}")
        demo = rng.choice(demo_pool)

        age = demo["age"]
        if trigger.get("age_min"):
            age = max(age, trigger["age_min"])

        # Task 1: perturb vitals
        vitals = _perturb_vitals(
            _pick_vitals("moderate_abnormal", vitals_templates),
            rng,
            age_group,
        )
        expected, rule_source_nodes = walk_reachable_path(
            graph,
            working_diagnosis=primary_dx,
            return_node_ids=True,
        )

        if not expected:
            continue

        # Merge graph-level + rule-specific forbidden actions with provenance
        rule_fa_prov: dict[str, str] = dict(fa_provenance)
        all_forbidden = list(graph_forbidden) + list(trigger.get("forbidden_actions") or [])
        for rfa in trigger.get("forbidden_actions") or []:
            if rfa not in rule_fa_prov:
                rule_fa_prov[rfa] = f"rule:{trigger['rule_id']}"
        # Deduplicate preserving order
        seen_fa: set[str] = set()
        deduped_forbidden: list[str] = []
        for fa in all_forbidden:
            if fa not in seen_fa:
                deduped_forbidden.append(fa)
                seen_fa.add(fa)

        # Task 5: ground truth
        gt_base = gt_templates.get("moderate_abnormal", {})
        ground_truth = _perturb_ground_truth(gt_base, rng)

        scenario = {
            "scenario_id": sid,
            "description": f"{guideline_name} — {trigger['description'][:80]}",
            "guideline_graph": graph_id,
            "patient": {
                "age": age,
                "sex": demo["sex"],
                "weight_kg": demo["weight_kg"],
                "chief_complaint": _chief_complaint_for_domain(domain, rng),
                "working_diagnosis": primary_dx,
                "vitals": vitals,
                "allergies": list(trigger.get("allergies") or []),
                "comorbidities": list(trigger.get("comorbidities") or []),
                "contraindications": [],
            },
            "expected_actions": expected,
            "forbidden_actions": deduped_forbidden,
            "trap_scenario": True,
            "trap_description": trigger["description"],
            "max_duration_minutes": 120,
            "passing_compliance_threshold": 0.7,
        }
        if ground_truth:
            scenario["ground_truth"] = ground_truth
        # Provenance metadata
        deduped_prov = {fa: rule_fa_prov.get(fa, "unknown") for fa in deduped_forbidden}
        scenario["_generation_metadata"] = _build_generation_metadata(
            graph_id=graph_id,
            generation_phase="conditional_rule",
            source_nodes=rule_source_nodes,
            forbidden_sources=deduped_prov,
        )

        scenarios[sid] = scenario

    # --- 2b. Universal comorbidity/allergy trap scenarios (Task 4) ---
    path_actions, trap_source_nodes = walk_reachable_path(
        graph,
        working_diagnosis=primary_dx,
        return_node_ids=True,
    )

    for trap in _UNIVERSAL_TRAPS:
        if counter >= max_scenarios:
            break
        # Filter by applicable domains
        applicable = trap.get("applicable_domains")
        if applicable is not None and domain not in applicable:
            continue

        trap_id = _make_scenario_id(graph_id, trap["id"])
        # Skip if we'd collide with an existing scenario id
        if trap_id in scenarios:
            continue

        counter += 1
        demo = rng.choice(demo_pool)
        vitals = _perturb_vitals(
            _pick_vitals("moderate_abnormal", vitals_templates),
            rng,
            age_group,
        )

        if not path_actions:
            continue

        # Merge graph + trap forbidden actions with provenance
        trap_fa_prov: dict[str, str] = dict(fa_provenance)
        trap_forbidden = list(graph_forbidden) + list(trap.get("forbidden_actions") or [])
        for tfa in trap.get("forbidden_actions") or []:
            if tfa not in trap_fa_prov:
                trap_fa_prov[tfa] = f"trap:{trap['id']}"
        seen_fa2: set[str] = set()
        deduped_trap_fa: list[str] = []
        for fa in trap_forbidden:
            if fa not in seen_fa2:
                deduped_trap_fa.append(fa)
                seen_fa2.add(fa)

        gt_base = gt_templates.get("moderate_abnormal", {})
        ground_truth = _perturb_ground_truth(gt_base, rng)

        scenario = {
            "scenario_id": trap_id,
            "description": f"{guideline_name} — {trap['description'][:80]}",
            "guideline_graph": graph_id,
            "patient": {
                "age": demo["age"],
                "sex": demo["sex"],
                "weight_kg": demo["weight_kg"],
                "chief_complaint": _chief_complaint_for_domain(domain, rng),
                "working_diagnosis": primary_dx,
                "vitals": vitals,
                "allergies": list(trap.get("allergies") or []),
                "comorbidities": list(trap.get("comorbidities") or []),
                "contraindications": [],
            },
            "expected_actions": list(path_actions),
            "forbidden_actions": deduped_trap_fa,
            "trap_scenario": True,
            "trap_description": trap["description"],
            "max_duration_minutes": 120,
            "passing_compliance_threshold": 0.7,
        }
        if ground_truth:
            scenario["ground_truth"] = ground_truth
        # Provenance metadata
        deduped_trap_prov = {fa: trap_fa_prov.get(fa, "unknown") for fa in deduped_trap_fa}
        scenario["_generation_metadata"] = _build_generation_metadata(
            graph_id=graph_id,
            generation_phase="universal_trap",
            source_nodes=trap_source_nodes,
            forbidden_sources=deduped_trap_prov,
        )

        scenarios[trap_id] = scenario

    # --- 3. Clean baseline scenario (no FA, no comorbidities) ---
    if counter < max_scenarios:
        counter += 1
        sid = _make_scenario_id(graph_id, "baseline_clean")
        demo = demo_pool[0]
        vitals = _perturb_vitals(
            _pick_vitals("moderate_abnormal", vitals_templates),
            rng,
            age_group,
        )
        expected, baseline_nodes = walk_reachable_path(
            graph,
            working_diagnosis=primary_dx,
            return_node_ids=True,
        )

        if expected:
            gt_base = gt_templates.get("moderate_abnormal", {})
            ground_truth = _perturb_ground_truth(gt_base, rng)

            scenario = {
                "scenario_id": sid,
                "description": f"{guideline_name} — baseline (no comorbidities)",
                "guideline_graph": graph_id,
                "patient": {
                    "age": demo["age"],
                    "sex": demo["sex"],
                    "weight_kg": demo["weight_kg"],
                    "chief_complaint": _chief_complaint_for_domain(domain, rng),
                    "working_diagnosis": primary_dx,
                    "vitals": vitals,
                    "allergies": [],
                    "comorbidities": [],
                    "contraindications": [],
                },
                "expected_actions": expected,
                "max_duration_minutes": 120,
                "passing_compliance_threshold": 0.8,
            }
            # Baseline: NO forbidden actions (clean happy-path test)
            if ground_truth:
                scenario["ground_truth"] = ground_truth
            # Provenance metadata
            scenario["_generation_metadata"] = _build_generation_metadata(
                graph_id=graph_id,
                generation_phase="baseline",
                source_nodes=baseline_nodes,
                forbidden_sources={},
            )

            scenarios[sid] = scenario

    return scenarios


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate scenario YAML files from CPG graph YAMLs.",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--graph", type=Path, help="Single CPG graph YAML.")
    g.add_argument("--graphs-dir", type=Path, help="Directory of CPG graph YAMLs.")

    p.add_argument("--output-dir", type=Path, default=None, help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}).")
    p.add_argument("--max-per-graph", type=int, default=15, help="Max scenarios per graph (default: 15).")
    p.add_argument("--seed", type=int, default=42, help="Random seed (default: 42).")
    p.add_argument("--dry-run", action="store_true", help="Preview without writing files.")
    p.add_argument("--verbose", "-v", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    rng = random.Random(args.seed)
    output_dir = args.output_dir or DEFAULT_OUTPUT_DIR

    # Collect graph files
    if args.graph:
        graph_files = [args.graph]
    else:
        graph_files = sorted(args.graphs_dir.glob("*.yaml"))
        if not graph_files:
            logger.error("No YAML files found in %s", args.graphs_dir)
            return 2

    total_scenarios = 0

    for gf in graph_files:
        graph = load_graph(gf)
        if not graph:
            logger.warning("Skipping %s", gf.name)
            continue

        graph_id = graph.get("graph_id", gf.stem)
        scenarios = generate_scenarios_for_graph(graph, gf, rng, args.max_per_graph)

        if not scenarios:
            logger.warning("No scenarios generated for %s", graph_id)
            continue

        logger.info("Generated %d scenarios for %s", len(scenarios), graph_id)
        total_scenarios += len(scenarios)

        if not args.dry_run:
            output_dir.mkdir(parents=True, exist_ok=True)
            out_path = output_dir / f"{graph_id}_scenarios.yaml"
            out_data = {"scenarios": scenarios}
            out_path.write_text(
                yaml.safe_dump(out_data, sort_keys=False, allow_unicode=True, width=120),
                encoding="utf-8",
            )
            logger.info("  Wrote %s", out_path)
        else:
            logger.info("  [DRY RUN] Would write %d scenarios to %s", len(scenarios), graph_id)
            for sid in list(scenarios.keys())[:3]:
                s = scenarios[sid]
                logger.info(
                    "    - %s: %s (%d expected_actions)", sid, s["description"][:60], len(s["expected_actions"])
                )

    logger.info("Total: %d scenarios from %d graphs", total_scenarios, len(graph_files))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
