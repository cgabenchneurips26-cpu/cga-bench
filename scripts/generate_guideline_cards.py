"""Generate comprehensive guideline card YAML from all CPG graph YAML files.

Reads all 25 CPG graph YAML files from cpg_model/graphs/ and produces a
structured summary at evidence_pack/guideline_cards.yaml.

Usage:
    python scripts/generate_guideline_cards.py

Output:
    evidence_pack/guideline_cards.yaml
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
GRAPHS_DIR = REPO_ROOT / "cpg_model" / "graphs"
OUTPUT_PATH = REPO_ROOT / "evidence_pack" / "guideline_cards.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify_to_name(graph_id: str) -> str:
    """Derive a human-readable guideline name from a graph_id slug."""
    words = graph_id.replace("_", " ").split()
    # common acronym tokens that should stay uppercase
    acronyms = {
        "aha",
        "ada",
        "aki",
        "acls",
        "acog",
        "aba",
        "apa",
        "aabb",
        "kdigo",
        "ssc",
        "gina",
        "idsa",
        "pals",
        "ats",
        "esc",
    }
    result = []
    for w in words:
        result.append(w.upper() if w.lower() in acronyms else w.title())
    return " ".join(result)


def _collect_node_values(nodes: dict[str, Any], key: str) -> list[str]:
    """Collect unique non-empty string values for *key* across all nodes."""
    seen: set[str] = set()
    out: list[str] = []
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        val = node.get(key)
        if val and isinstance(val, str) and val not in seen:
            seen.add(val)
            out.append(val)
    return out


def _collect_list_union(nodes: dict[str, Any], key: str) -> list[str]:
    """Union of all action lists for *key* across all nodes (deduplicated)."""
    seen: set[str] = set()
    out: list[str] = []
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        items = node.get(key, []) or []
        for item in items:
            if item and item not in seen:
                seen.add(item)
                out.append(item)
    return out


def _collect_before_constraints(nodes: dict[str, Any]) -> list[str]:
    """Extract BEFORE constraints from required_prior_actions mappings.

    Each node may have required_prior_actions: {action: prior_action}.
    We express them as "prior_action BEFORE action" strings.
    """
    seen: set[str] = set()
    out: list[str] = []
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        rpa = node.get("required_prior_actions") or {}
        if not isinstance(rpa, dict):
            continue
        for action, prior in rpa.items():
            if not action or not prior:
                continue
            constraint = f"{prior} BEFORE {action}"
            if constraint not in seen:
                seen.add(constraint)
                out.append(constraint)
    return out


def _collect_within_constraints(nodes: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract WITHIN (deadline) constraints from node deadlines fields."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        deadlines = node.get("deadlines") or {}
        if not isinstance(deadlines, dict):
            continue
        for action, minutes in deadlines.items():
            key = f"{action}:{minutes}"
            if key not in seen:
                seen.add(key)
                out.append({"action": action, "within_minutes": minutes})
    return out


def _most_common_evidence_level(nodes: dict[str, Any]) -> str:
    """Return the most frequent evidence_level across nodes, or 'N/A'."""
    counts: Counter = Counter()
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        ev = node.get("evidence_level")
        if ev and isinstance(ev, str):
            counts[ev.strip()] += 1
    if not counts:
        return "N/A"
    return counts.most_common(1)[0][0]


def _derive_scope(graph_id: str, metadata: dict[str, Any]) -> str:
    """Derive clinical scope from graph_id and metadata description."""
    desc = metadata.get("description", "")
    if desc:
        return desc
    # Fallback: transform graph_id into a readable scope string
    return _slugify_to_name(graph_id) + " management"


def _derive_target_population(graph_id: str, metadata: dict[str, Any], nodes: dict[str, Any]) -> str:
    """Derive target population from available metadata fields."""
    # Some graphs have explicit population fields
    for field in ("target_population", "population", "patient_population"):
        val = metadata.get(field)
        if val and isinstance(val, str):
            return val

    # Heuristic mapping based on graph_id patterns
    patterns: list[tuple[str, str]] = [
        ("sepsis", "Adult patients with suspected sepsis or septic shock"),
        ("chest_pain", "Adult patients presenting with chest pain"),
        ("aki", "Adult patients with or at risk for acute kidney injury"),
        ("dka", "Adult patients with diabetic ketoacidosis"),
        ("stroke", "Adult patients with acute ischemic stroke symptoms"),
        ("heart_failure", "Adult patients with acute decompensated heart failure"),
        ("cardiac_arrest", "Patients in cardiac arrest (all ages)"),
        ("pediatric", "Pediatric patients requiring emergency care"),
        ("pals", "Pediatric patients requiring emergency resuscitation"),
        ("burn", "Adult and pediatric burn patients"),
        ("obstetric", "Pregnant and postpartum patients with hemorrhage"),
        ("transfusion", "Patients requiring blood product transfusion"),
        ("anaphylaxis", "Patients experiencing anaphylaxis or severe allergic reaction"),
        ("agitation", "Adult patients with acute agitation"),
        ("atrial_fibrillation", "Adult patients with atrial fibrillation"),
        ("pneumonia", "Adult patients with community-acquired pneumonia"),
        ("copd", "Adult patients with COPD exacerbation"),
        ("gi_bleeding", "Adult patients with acute gastrointestinal bleeding"),
        ("asthma", "Adult and pediatric patients with asthma exacerbation"),
        ("hypertensive", "Adult patients with hypertensive emergency"),
        ("meningitis", "Adult patients with suspected bacterial meningitis"),
        ("pulmonary_embolism", "Adult patients with suspected pulmonary embolism"),
        ("epilepticus", "Adult and pediatric patients with status epilepticus"),
        ("toxicology", "Adult patients with acute toxic exposure or overdose"),
        ("universal", "All patients across clinical settings"),
    ]
    gid = graph_id.lower()
    for pattern, population in patterns:
        if pattern in gid:
            return population
    return "Adult patients in acute care settings"


def _derive_known_limitations(
    graph_id: str,
    nodes: dict[str, Any],
    forbidden_actions: list[str],
    before_constraints: list[str],
    within_constraints: list[dict[str, Any]],
) -> list[str]:
    """Derive structural known limitations from graph properties."""
    limitations: list[str] = []
    node_count = len(nodes)

    if node_count <= 2:
        limitations.append("Single-node or minimal graph — limited state-transition coverage")
    if not forbidden_actions:
        limitations.append("No forbidden actions defined — commission violations cannot be evaluated")
    if not within_constraints:
        limitations.append("No deadline constraints defined — timing violations cannot be evaluated")
    if not before_constraints:
        limitations.append("No sequence constraints defined — ordering violations cannot be evaluated")

    # Graph-specific known limitations
    specific: dict[str, list[str]] = {
        "universal_clinical_safety": [
            "Domain-independent fallback — lower specificity than disease-specific graphs",
            "No patient simulation; designed for static external benchmark evaluation",
        ],
        "ada_dka_management": [
            "Pediatric DKA dosing not covered — adult protocol only",
        ],
        "ssc_sepsis_hour1_bundle": [
            "Covers Hour-1 bundle only; post-resuscitation care not modelled",
        ],
        "aha_chest_pain_evaluation": [
            "Does not model outpatient or observation-unit discharge pathways",
        ],
        "kdigo_aki_full": [
            "CKD staging and chronic management pathways not included",
        ],
        "kdigo_contrast_aki": [
            "Contrast AKI prevention only; does not cover post-contrast monitoring",
        ],
        "pals_pediatric_emergency": [
            "Weight-based dosing variability not modelled at graph level",
        ],
        "acls_cardiac_arrest": [
            "Post-ROSC care and targeted temperature management not modelled",
        ],
    }
    limitations.extend(specific.get(graph_id, []))

    return limitations


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------


def extract_card(filepath: Path) -> dict[str, Any]:
    """Parse one graph YAML file and return a guideline card dict."""
    with filepath.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    graph_id: str = raw.get("graph_id", filepath.stem)
    metadata: dict[str, Any] = raw.get("metadata", {}) or {}

    # Top-level fields may also carry guideline_name / version directly
    guideline_name: str = raw.get("guideline_name") or metadata.get("guideline_name") or _slugify_to_name(graph_id)
    version: str = str(raw.get("version", metadata.get("version", "N/A")))

    # Source
    source_candidates = [
        metadata.get("source"),
        metadata.get("citation"),
        raw.get("source"),
    ]
    source: str = next((s for s in source_candidates if s), "N/A")

    nodes: dict[str, Any] = raw.get("nodes", {}) or {}

    # Constraint extraction
    forbidden_actions = _collect_list_union(nodes, "forbidden_actions")
    mandatory_actions = _collect_list_union(nodes, "mandatory_actions")
    before_constraints = _collect_before_constraints(nodes)
    within_constraints = _collect_within_constraints(nodes)

    total_constraints = (
        len(forbidden_actions) + len(mandatory_actions) + len(before_constraints) + len(within_constraints)
    )

    # Evidence level
    evidence_level = _most_common_evidence_level(nodes)
    # Also accept top-level evidence_level field
    if evidence_level == "N/A":
        evidence_level = str(raw.get("evidence_level", "N/A"))

    # Source guideline citations (unique values from nodes)
    source_guidelines = _collect_node_values(nodes, "source_guideline")

    # Scope and population
    scope = _derive_scope(graph_id, metadata)
    target_population = _derive_target_population(graph_id, metadata, nodes)

    # Known limitations
    known_limitations = _derive_known_limitations(
        graph_id, nodes, forbidden_actions, before_constraints, within_constraints
    )

    card: dict[str, Any] = {
        "graph_id": graph_id,
        "guideline_name": guideline_name,
        "source": source,
        "version": version,
        "scope": scope,
        "target_population": target_population,
        "node_count": len(nodes),
        "source_guidelines_cited": source_guidelines,
        "evidence_level": evidence_level,
        "constraint_summary": {
            "forbidden_action_count": len(forbidden_actions),
            "forbidden_actions": forbidden_actions,
            "required_action_count": len(mandatory_actions),
            "required_actions": mandatory_actions,
            "before_constraint_count": len(before_constraints),
            "before_constraints": before_constraints,
            "within_constraint_count": len(within_constraints),
            "within_constraints": within_constraints,
        },
        "total_constraints": total_constraints,
        "known_limitations": known_limitations,
    }
    return card


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Read all graph YAML files and write guideline_cards.yaml."""
    graph_files = sorted(p for p in GRAPHS_DIR.glob("*.yaml") if not p.name.startswith("_"))
    print(f"Found {len(graph_files)} graph YAML files in {GRAPHS_DIR}")

    cards: list[dict[str, Any]] = []
    for fp in graph_files:
        try:
            card = extract_card(fp)
            cards.append(card)
            print(
                f"  [{card['graph_id']}] "
                f"nodes={card['node_count']} "
                f"forbidden={card['constraint_summary']['forbidden_action_count']} "
                f"required={card['constraint_summary']['required_action_count']} "
                f"before={card['constraint_summary']['before_constraint_count']} "
                f"within={card['constraint_summary']['within_constraint_count']} "
                f"total={card['total_constraints']}"
            )
        except Exception as exc:
            print(f"  ERROR processing {fp.name}: {exc}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    output: dict[str, Any] = {
        "meta": {
            "description": "Comprehensive guideline cards for all CGA-Bench CPG graphs",
            "generated_by": "scripts/generate_guideline_cards.py",
            "total_graphs": len(cards),
        },
        "guideline_cards": cards,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
        yaml.dump(
            output,
            fh,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )

    print(f"\nWrote {len(cards)} guideline cards -> {OUTPUT_PATH}")

    # Summary statistics
    total_forbidden = sum(c["constraint_summary"]["forbidden_action_count"] for c in cards)
    total_required = sum(c["constraint_summary"]["required_action_count"] for c in cards)
    total_before = sum(c["constraint_summary"]["before_constraint_count"] for c in cards)
    total_within = sum(c["constraint_summary"]["within_constraint_count"] for c in cards)
    grand_total = sum(c["total_constraints"] for c in cards)
    print("\nAggregate constraint summary:")
    print(f"  Forbidden actions : {total_forbidden}")
    print(f"  Required actions  : {total_required}")
    print(f"  Before constraints: {total_before}")
    print(f"  Within constraints: {total_within}")
    print(f"  Grand total       : {grand_total}")


if __name__ == "__main__":
    main()
