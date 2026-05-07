"""Build canonical action-ID map from CPG graph YAML files.

Scans cpg_model/graphs/*.yaml, groups action IDs by canonical form using:
  1. Seed groups from root-cause doc §13 (18 explicit synonym groups)
  2. Prefix-stripping heuristic: strip order_lab_, order_, give_, etc.
  3. Auto-detection: Jaccard >= 0.75 within clinically-compatible buckets

Outputs:
  cpg_model/action_alias_map.yaml
    canonical_map: canonical_id -> [variant, ...]
    reverse_map:   variant        -> canonical_id

Usage:
    PYTHONPATH=. python scripts/tools/build_canonical_action_map.py
    PYTHONPATH=. python scripts/tools/build_canonical_action_map.py --output path/to/out.yaml
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed groups from root-cause doc §13.1 (18 explicit synonym groups)
# Canonical choice follows heuristics documented below.
# ---------------------------------------------------------------------------
SEED_SYNONYM_GROUPS: list[tuple[str, list[str]]] = [
    # [canonical, [variants...]]
    # Lab prefix synonyms
    ("order_lab_cbc", ["order_cbc", "order_lab_cbc"]),
    ("order_lab_creatinine", ["order_creatinine", "order_lab_creatinine"]),
    ("order_lab_urinalysis", ["order_urinalysis", "order_lab_urinalysis"]),
    ("order_lab_tsh", ["order_tsh", "order_lab_tsh"]),
    ("order_lab_cystatin_c", ["order_cystatin_c", "order_lab_cystatin_c"]),
    ("order_lab_type_and_crossmatch", ["order_type_and_crossmatch", "order_lab_type_and_crossmatch"]),
    ("order_lab_glucose", ["check_glucose", "order_lab_glucose"]),
    # Imaging prefix synonyms
    ("order_imaging_chest_xray", ["order_chest_xray", "order_imaging_chest_xray"]),
    ("order_imaging_ecg", ["obtain_ecg", "order_ecg", "order_imaging_ecg"]),
    ("order_imaging_echocardiogram", ["order_echocardiogram", "order_imaging_echocardiogram"]),
    ("order_imaging_ct_head", ["order_imaging_ct_head", "stat_ct_head"]),
    ("order_ct_angiography", ["obtain_ct_angiography", "order_ct_angiography"]),
    # Procedure verb synonyms
    ("perform_lumbar_puncture", ["order_lumbar_puncture", "perform_lumbar_puncture"]),
    ("assess_nihss", ["assess_nihss", "perform_nihss"]),
    ("assess_vital_signs", ["assess_vital_signs", "obtain_vital_signs"]),
    # Medication approach synonyms
    ("initiate_beta_blocker", ["consider_beta_blocker", "give_beta_blocker", "initiate_beta_blocker"]),
    ("initiate_ace_or_arb_or_arni", ["consider_ace_or_arb_or_arni", "initiate_ace_or_arb_or_arni"]),
    # Monitoring synonyms
    ("continuous_monitoring", ["continuous_monitoring", "start_continuous_monitoring"]),
    ("order_type_and_screen", ["order_type_and_screen", "type_and_screen"]),
    ("order_serial_ecg", ["order_serial_ecg", "serial_ecg"]),
    # Lab panel / complete-blood-count synonyms. CBC and BMP/CMP/lactate are
    # clinically distinct tests (different analytes, different panels) and
    # MUST NOT collapse into one canonical — an earlier seed at §13.4
    # attempted a "cross-domain initial workup" merge that aliased CBC,
    # lactate and continuous-monitoring all to BMP, corrupting any
    # benchmark scenario where the scorer distinguished these ids.
    # The groups below preserve per-test identity so the scorer still sees
    # what the agent actually ordered.
    (
        "order_lab_cbc",
        [
            "order_cbc",
            "order_lab_cbc",
            "order_lab_cbc_repeat",
        ],
    ),
    (
        "order_lab_basic_metabolic_panel",
        [
            "order_basic_metabolic_panel",
            "order_lab_basic_metabolic_panel",
            "order_lab_bmp",
        ],
    ),
    (
        "order_lab_comprehensive_metabolic_panel",
        [
            "order_comprehensive_metabolic_panel",
            "order_lab_comprehensive_metabolic_panel",
            "order_lab_cmp",
        ],
    ),
    (
        "order_lab_lactate",
        [
            "order_lactate",
            "order_lab_lactate",
        ],
    ),
    # Continuous vitals monitoring — a procedural monitoring action, not a
    # lab order. The former seed routed this id to BMP, which silently
    # dropped monitoring from episode logs on any model that emitted it.
    (
        "assess_vital_signs",
        [
            "assess_vital_signs",
            "obtain_vital_signs",
            "monitor_vital_signs",
            "monitor_vitals_continuously",
            "monitor_vitals_q15min",
            "monitor_vitals_q30min",
            "monitor_vitals_serially",
            "assess_bp",
        ],
    ),
    # High-frequency off-graph proposals from the 4-model 64-episode
    # dry-run catalog (scripts/analysis/extract_off_graph_actions.py)
    # that the models emit as clinical standards but the graphs used
    # slightly different ids. Only synonym-level merges here — actions
    # that are truly not in any graph (e.g. evaluate_reversible_causes,
    # calculate_parkland) should reach Tier 3 / Tier 4 instead of
    # being force-mapped to an unrelated canonical.
    (
        "monitor_urine_output",
        [
            "monitor_urine_output",
            "monitor_uo",
            "measure_urine_output",
        ],
    ),
    (
        "order_imaging_ecg",
        [
            "obtain_ecg",
            "order_ecg",
            "obtain_12_lead_ecg",
            "order_imaging_ecg",
            "order_12_lead_ecg",
        ],
    ),
    (
        "check_current_medications",
        [
            "check_current_medications",
            "review_medications",
            "review_current_medications",
            "medication_reconciliation",
        ],
    ),
    (
        "reassess_clinical_presentation",
        [
            "reassess_clinical_presentation",
            "reassess_patient",
            "reassess_clinical_status",
        ],
    ),
    (
        "measure_oxygen_saturation",
        [
            "measure_oxygen_saturation",
            "check_oxygen_saturation",
            "measure_spo2",
        ],
    ),
    # Near-dupe pairs from §13.2
    ("initiate_mra", ["consider_mra", "initiate_mra"]),
    ("give_epinephrine_nebulized", ["give_epinephrine_nebulized", "give_nebulized_epinephrine"]),
    ("neurosurgery_consult", ["consult_neurosurgery", "neurosurgery_consult"]),
    ("nephrology_consult", ["consult_nephrology", "nephrology_consult"]),
    ("endocrinology_consult", ["consult_endocrinology", "endocrinology_consult"]),
]

# Tokens that carry no clinical meaning — excluded from clinical-overlap check
TRIVIAL_TOKENS: frozenset[str] = frozenset(
    {
        "order",
        "lab",
        "give",
        "perform",
        "check",
        "assess",
        "obtain",
        "imaging",
        "initiate",
        "consider",
        "start",
        "stat",
        "serial",
        "continuous",
        "repeat",
        "monitor",
        "review",
        "the",
        "and",
        "or",
        "of",
        "without",
        "with",
    }
)


def _collect_all_action_ids(graphs_dir: Path) -> dict[str, set[str]]:
    """Return {graph_id: {action_id, ...}} from all YAML graph files."""
    result: dict[str, set[str]] = {}
    for graph_file in sorted(graphs_dir.glob("*.yaml")):
        with open(graph_file) as fh:
            data = yaml.safe_load(fh)
        graph_id = graph_file.stem
        ids: set[str] = set()
        for node in (data.get("nodes") or {}).values():
            for field in ("mandatory_actions", "allowed_actions", "forbidden_actions"):
                for action_id in node.get(field) or []:
                    ids.add(action_id)
        result[graph_id] = ids
    return result


def _jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity between two action IDs."""
    sa = set(a.split("_"))
    sb = set(b.split("_"))
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def _clinical_tokens(action_id: str) -> frozenset[str]:
    """Return clinically meaningful tokens from an action ID."""
    return frozenset(t for t in action_id.split("_") if t not in TRIVIAL_TOKENS and len(t) > 1)


def _choose_canonical(variants: list[str]) -> str:
    """Choose canonical ID from a group of synonyms.

    Preference order (heuristic):
      1. Prefer ``order_lab_*`` for lab tests
      2. Prefer ``order_imaging_*`` for imaging
      3. Prefer ``initiate_*`` over ``consider_*``
      4. Prefer ``perform_*`` over ``order_*`` for procedures
      5. Prefer the lexicographically shortest ID as tiebreaker
    """
    lab_variants = [v for v in variants if v.startswith("order_lab_")]
    if lab_variants:
        return min(lab_variants)
    imaging_variants = [v for v in variants if v.startswith("order_imaging_")]
    if imaging_variants:
        return min(imaging_variants)
    initiate_variants = [v for v in variants if v.startswith("initiate_")]
    if initiate_variants:
        return min(initiate_variants)
    perform_variants = [v for v in variants if v.startswith("perform_")]
    if perform_variants:
        return min(perform_variants)
    return min(variants)


def _build_seed_groups() -> dict[str, set[str]]:
    """Build initial canonical->variants map from SEED_SYNONYM_GROUPS."""
    groups: dict[str, set[str]] = {}
    for canonical, variants in SEED_SYNONYM_GROUPS:
        if canonical not in groups:
            groups[canonical] = set()
        groups[canonical].update(variants)
    return groups


def _merge_groups(groups: dict[str, set[str]]) -> dict[str, set[str]]:
    """Merge groups that share any member (union-find style)."""
    # Build variant->canonical reverse map
    variant_to_canonical: dict[str, str] = {}
    for canonical, variants in groups.items():
        for v in variants:
            variant_to_canonical[v] = canonical

    # Union-find: collapse groups that share members
    merged: dict[str, set[str]] = {}
    for canonical, variants in groups.items():
        # Find existing group for any variant
        existing_canonical = None
        for v in variants:
            if v in variant_to_canonical:
                ec = variant_to_canonical[v]
                if ec in merged:
                    existing_canonical = ec
                    break
        if existing_canonical:
            merged[existing_canonical].update(variants)
            # Update reverse map
            for v in variants:
                variant_to_canonical[v] = existing_canonical
        else:
            merged[canonical] = set(variants)
            for v in variants:
                variant_to_canonical[v] = canonical
    return merged


def _auto_detect_near_dupes(
    all_ids: set[str],
    existing_groups: dict[str, set[str]],
    jaccard_threshold: float = 0.75,
) -> dict[str, set[str]]:
    """Auto-detect near-duplicate pairs with Jaccard >= threshold.

    Only merges pairs that:
      - Share at least one non-trivial clinical token (clinical-bucket check)
      - Are not already in the same group
    """
    # Build reverse map of existing groups
    variant_to_canonical: dict[str, str] = {}
    for canonical, variants in existing_groups.items():
        for v in variants:
            variant_to_canonical[v] = canonical

    ids_list = sorted(all_ids)
    new_pairs: list[tuple[str, str]] = []

    for i, a in enumerate(ids_list):
        ct_a = _clinical_tokens(a)
        for b in ids_list[i + 1 :]:
            if _jaccard(a, b) < jaccard_threshold:
                continue
            ct_b = _clinical_tokens(b)
            if not (ct_a & ct_b):
                continue  # No clinical overlap — skip
            # Check if already in same group
            ca = variant_to_canonical.get(a)
            cb = variant_to_canonical.get(b)
            if ca and cb and ca == cb:
                continue  # Already grouped
            new_pairs.append((a, b))

    # Add new pairs into existing groups or create new ones
    groups = dict(existing_groups)  # shallow copy
    variant_to_canonical = {}
    for canonical, variants in groups.items():
        for v in variants:
            variant_to_canonical[v] = canonical

    for a, b in new_pairs:
        ca = variant_to_canonical.get(a)
        cb = variant_to_canonical.get(b)
        if ca and cb:
            if ca != cb:
                # Merge group cb into ca
                groups[ca].update(groups.pop(cb, set()))
                for v in groups[ca]:
                    variant_to_canonical[v] = ca
        elif ca:
            groups[ca].add(b)
            variant_to_canonical[b] = ca
        elif cb:
            groups[cb].add(a)
            variant_to_canonical[a] = cb
        else:
            # Create new group
            new_canonical = _choose_canonical([a, b])
            groups[new_canonical] = {a, b}
            variant_to_canonical[a] = new_canonical
            variant_to_canonical[b] = new_canonical

    return groups


def build_canonical_map(graphs_dir: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Build and return (canonical_map, reverse_map).

    canonical_map: canonical_id -> sorted list of variants (includes canonical itself)
    reverse_map:   variant       -> canonical_id
    """
    # 1. Collect all action IDs from graphs
    graph_to_ids = _collect_all_action_ids(graphs_dir)
    all_ids: set[str] = set()
    for ids in graph_to_ids.values():
        all_ids.update(ids)

    logger.info("Collected %d unique action IDs from %d graphs", len(all_ids), len(graph_to_ids))

    # 2. Start with seed groups
    groups = _build_seed_groups()

    # 3. Restrict seed groups to IDs that actually exist in graphs
    #    (keeps map clean; seed may reference ids not yet in any graph)
    # We keep seed entries even if not in graphs — they may appear at runtime

    # 4. Auto-detect near-dupes
    groups = _auto_detect_near_dupes(all_ids, groups, jaccard_threshold=0.75)

    # 5. Re-choose canonicals, but respect seed canonicals that still own their
    #    group. The seed encodes a clinical preference (e.g. ``assess_vital_signs``
    #    beats the alphabetical min ``assess_bp``); blindly re-running
    #    ``_choose_canonical`` here would silently demote the seed to whichever
    #    variant sorts first.
    seed_canonicals = {c for c, _ in SEED_SYNONYM_GROUPS}
    final_groups: dict[str, set[str]] = {}
    for _canonical, variants in groups.items():
        seed_owners = [v for v in variants if v in seed_canonicals]
        if seed_owners:
            # Prefer the seed canonical that was registered for this concept.
            # If multiple seed canonicals merged into one group (should be
            # rare — indicates seeds overlap), pick the one that still starts
            # the canonical group name via the existing heuristic.
            best_canonical = seed_owners[0] if len(seed_owners) == 1 else _choose_canonical(sorted(seed_owners))
        else:
            best_canonical = _choose_canonical(sorted(variants))
        if best_canonical in final_groups:
            final_groups[best_canonical].update(variants)
        else:
            final_groups[best_canonical] = set(variants)

    # 6. Build canonical_map and reverse_map
    canonical_map: dict[str, list[str]] = {}
    reverse_map: dict[str, str] = {}
    for canonical, variants in sorted(final_groups.items()):
        all_variants = sorted(variants)
        canonical_map[canonical] = all_variants
        for v in all_variants:
            if v in reverse_map and reverse_map[v] != canonical:
                logger.warning(
                    "Variant '%s' maps to both '%s' and '%s'; keeping first",
                    v,
                    reverse_map[v],
                    canonical,
                )
            else:
                reverse_map[v] = canonical

    logger.info(
        "Canonical map: %d groups, %d total variants, avg %.1f variants/group",
        len(canonical_map),
        len(reverse_map),
        len(reverse_map) / max(len(canonical_map), 1),
    )
    return canonical_map, reverse_map


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Build canonical action-ID alias map from CPG graphs")
    parser.add_argument(
        "--graphs-dir",
        default=None,
        help="Path to cpg_model/graphs/ (auto-detected from repo root if omitted)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output YAML path (default: cpg_model/action_alias_map.yaml)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    # Resolve paths relative to this script's repo root
    repo_root = Path(__file__).resolve().parents[2]  # scripts/tools/ -> cga_bench/
    graphs_dir = Path(args.graphs_dir) if args.graphs_dir else repo_root / "cpg_model" / "graphs"
    output_path = Path(args.output) if args.output else repo_root / "cpg_model" / "action_alias_map.yaml"

    if not graphs_dir.is_dir():
        raise SystemExit(f"Graphs directory not found: {graphs_dir}")

    canonical_map, reverse_map = build_canonical_map(graphs_dir)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as fh:
        yaml.dump(
            {
                "canonical_map": canonical_map,
                "reverse_map": reverse_map,
            },
            fh,
            default_flow_style=False,
            sort_keys=True,
            allow_unicode=True,
        )

    print(f"Wrote {len(canonical_map)} canonical groups ({len(reverse_map)} variants) -> {output_path}")

    # Print a sample for quick sanity check
    print("\nSample groups:")
    for canonical, variants in list(canonical_map.items())[:10]:
        print(f"  {canonical}: {variants}")


if __name__ == "__main__":
    main()
