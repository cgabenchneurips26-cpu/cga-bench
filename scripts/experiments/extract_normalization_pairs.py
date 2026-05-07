#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""Extract action normalization pairs for human annotation.

Reads rescored and original episode files, extracts performed/expected action
pairs, identifies normalization matches and mismatches, and outputs a stratified
sample CSV ready for clinical annotator review.

Usage:
    PYTHONPATH=. python scripts/experiments/extract_normalization_pairs.py

Output:
    evidence_pack/sampling/action_norm_annotation_sample.csv
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import random

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RESCORED_DIR = "results/clean_slate_rescored"
ORIGINAL_DIR = "results/clean_slate_20260331_210910"
OUTPUT_CSV = "evidence_pack/sampling/action_norm_annotation_sample.csv"

MODEL_DIRS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]

SCENARIOS = [
    "adhf_warm_wet",
    "af_new_onset_basic",
    "aki_stage1_basic",
    "contrast_aki_prevention_basic",
    "copd_moderate_exacerbation",
    "dka_hypokalemia_trap",
    "dka_moderate_basic",
    "gi_bleeding_upper_basic",
    "hemorrhagic_stroke",
    "htn_emergency_basic",
    "pe_submassive_basic",
    "septic_shock_basic",
    "septic_shock_penicillin_allergy",
    "stemi_inferior_rv_trap",
    "stroke_tpa_eligible",
]

CSV_COLUMNS = [
    "episode_id",
    "scenario_id",
    "model_name",
    "raw_action",
    "normalized_action",
    "matched_expected",
    "violation_type",
    "annotator_judgment",
    "annotator_reasoning",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class NormPair:
    """A single normalization annotation row."""

    episode_id: str
    scenario_id: str
    model_name: str
    raw_action: str
    normalized_action: str
    matched_expected: str  # which expected action it matched, or "NONE"
    violation_type: str  # omission, commission, deviation, timing, sequence, or ""
    category: str = ""  # internal: "omission", "commission", "deviation", "matched", "unmatched"


@dataclass
class EpisodePair:
    """Paired original + rescored data for one episode."""

    episode_id: str
    scenario_id: str
    model_name: str
    # From original episode
    raw_actions: list[dict] = field(default_factory=list)
    expected_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    # From rescored episode
    violation_events: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# File matching
# ---------------------------------------------------------------------------


def find_original_file(original_dir: Path, model_dir: str, rescored_filename: str) -> Path | None:
    """Find the matching original episode file for a rescored file.

    Rescored and original files share the same basename.
    """
    candidate = original_dir / model_dir / rescored_filename
    if candidate.exists():
        return candidate
    return None


def derive_episode_id(scenario_id: str, model_name: str, run_index: int) -> str:
    """Create a human-readable episode identifier."""
    return f"{scenario_id}_{model_name}_r{run_index}"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_episode_pairs(
    base_dir: Path,
    rescored_dir_name: str,
    original_dir_name: str,
) -> list[EpisodePair]:
    """Load all paired episode data."""
    rescored_base = base_dir / rescored_dir_name
    original_base = base_dir / original_dir_name
    pairs: list[EpisodePair] = []

    for model_dir in MODEL_DIRS:
        rescored_model_dir = rescored_base / model_dir
        if not rescored_model_dir.is_dir():
            logger.warning("Rescored dir missing: %s", rescored_model_dir)
            continue

        for rescored_file in sorted(rescored_model_dir.glob("*.json")):
            if rescored_file.name == "rescore_summary.json":
                continue

            try:
                rescored_data = json.loads(rescored_file.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read rescored file %s: %s", rescored_file, exc)
                continue

            original_file = find_original_file(original_base, model_dir, rescored_file.name)
            if original_file is None:
                logger.warning("No matching original file for %s", rescored_file.name)
                continue

            try:
                original_data = json.loads(original_file.read_text())
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to read original file %s: %s", original_file, exc)
                continue

            scenario_id = rescored_data.get("scenario_id", original_data.get("scenario_id", "unknown"))
            model_name = rescored_data.get("model_name", original_data.get("model_name", model_dir))
            run_index = rescored_data.get("run_index", original_data.get("run_index", 0))

            episode_id = derive_episode_id(scenario_id, model_dir, run_index)

            pair = EpisodePair(
                episode_id=episode_id,
                scenario_id=scenario_id,
                model_name=model_name,
                raw_actions=original_data.get("actions", []),
                expected_actions=original_data.get("expected_actions", []),
                forbidden_actions=original_data.get("forbidden_actions", []),
                violation_events=rescored_data.get("new_violation_events", []),
            )
            pairs.append(pair)

    return pairs


# ---------------------------------------------------------------------------
# Pair extraction
# ---------------------------------------------------------------------------


def extract_pairs_from_episode(ep: EpisodePair) -> list[NormPair]:
    """Extract normalization pairs from a single episode.

    Produces rows for:
    1. Each violation event (omission, commission, deviation, timing, sequence)
    2. Each performed action that matched an expected action (implicit match)
    3. Each performed action that did not match any expected action and has no
       violation event (unmatched/extra actions)
    """
    rows: list[NormPair] = []
    expected_set = set(ep.expected_actions)
    forbidden_set = set(ep.forbidden_actions)

    # Track which performed actions appear in violations
    violation_action_ids: set[str] = set()
    # Track which expected actions appear in omission violations
    omitted_expected: set[str] = set()

    # --- Process violation events ---
    for viol in ep.violation_events:
        vtype = viol.get("violation_type", "")
        action_involved = viol.get("action_involved", "") or ""
        expected_action = viol.get("expected_action", "") or ""

        if vtype == "omission":
            # Agent did NOT perform this expected action
            omitted_expected.add(expected_action)
            rows.append(
                NormPair(
                    episode_id=ep.episode_id,
                    scenario_id=ep.scenario_id,
                    model_name=ep.model_name,
                    raw_action="",  # not performed
                    normalized_action="",
                    matched_expected=expected_action,
                    violation_type="omission",
                    category="omission",
                )
            )
        elif vtype == "commission":
            # Agent performed a forbidden action
            violation_action_ids.add(action_involved)
            rows.append(
                NormPair(
                    episode_id=ep.episode_id,
                    scenario_id=ep.scenario_id,
                    model_name=ep.model_name,
                    raw_action=action_involved,
                    normalized_action=action_involved,
                    matched_expected="NONE",
                    violation_type="commission",
                    category="commission",
                )
            )
        elif vtype == "deviation":
            # Agent performed an off-protocol action
            violation_action_ids.add(action_involved)
            rows.append(
                NormPair(
                    episode_id=ep.episode_id,
                    scenario_id=ep.scenario_id,
                    model_name=ep.model_name,
                    raw_action=action_involved,
                    normalized_action=action_involved,
                    matched_expected="NONE",
                    violation_type="deviation",
                    category="deviation",
                )
            )
        elif vtype in ("timing", "sequence"):
            # Action was performed but with timing/sequence issue
            violation_action_ids.add(action_involved)
            # These actions DID match an expected action (otherwise they
            # wouldn't have timing/sequence violations)
            matched = expected_action if expected_action else "NONE"
            rows.append(
                NormPair(
                    episode_id=ep.episode_id,
                    scenario_id=ep.scenario_id,
                    model_name=ep.model_name,
                    raw_action=action_involved,
                    normalized_action=action_involved,
                    matched_expected=matched,
                    violation_type=vtype,
                    category="matched",
                )
            )

    # --- Process performed actions not already covered by violations ---
    for act in ep.raw_actions:
        action_id = act.get("action_id", "")
        if not action_id:
            continue
        if action_id in violation_action_ids:
            continue

        # Determine if this action matched an expected action
        if action_id in expected_set:
            matched = action_id
            cat = "matched"
        else:
            # Check if it might be a normalized form that matched
            matched = "NONE"
            cat = "unmatched"

        rows.append(
            NormPair(
                episode_id=ep.episode_id,
                scenario_id=ep.scenario_id,
                model_name=ep.model_name,
                raw_action=action_id,
                normalized_action=action_id,
                matched_expected=matched,
                violation_type="",
                category=cat,
            )
        )

    return rows


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def stratified_sample(
    all_pairs: list[NormPair],
    pairs_per_scenario: int = 10,
    seed: int = 42,
) -> list[NormPair]:
    """Apply stratified sampling to produce a balanced annotation set.

    Strategy:
    - ALL omission violations (false-negative candidates)
    - ALL commission violations (safety-critical)
    - ALL deviation violations (normalizer artifact candidates)
    - Stratified random sample of matched/unmatched pairs per scenario
    - Deduplication by (raw_action, normalized_action, matched_expected) triple
    """
    rng = random.Random(seed)

    # Separate by category
    must_include: list[NormPair] = []
    matched_by_scenario: dict[str, list[NormPair]] = defaultdict(list)
    unmatched_by_scenario: dict[str, list[NormPair]] = defaultdict(list)

    for pair in all_pairs:
        if pair.category in ("omission", "commission", "deviation"):
            must_include.append(pair)
        elif pair.category == "matched":
            matched_by_scenario[pair.scenario_id].append(pair)
        else:
            unmatched_by_scenario[pair.scenario_id].append(pair)

    # Deduplicate must_include by (raw_action, normalized_action, matched_expected, violation_type)
    seen_triples: set[tuple[str, str, str, str]] = set()
    deduped_must: list[NormPair] = []
    for pair in must_include:
        key = (pair.raw_action, pair.normalized_action, pair.matched_expected, pair.violation_type)
        if key not in seen_triples:
            seen_triples.add(key)
            deduped_must.append(pair)

    # Stratified sample of matched pairs
    sampled_matched: list[NormPair] = []
    for scenario_id in SCENARIOS:
        pool = matched_by_scenario.get(scenario_id, [])
        # Deduplicate within scenario
        seen_local: set[tuple[str, str, str]] = set()
        unique_pool: list[NormPair] = []
        for p in pool:
            key = (p.raw_action, p.normalized_action, p.matched_expected)
            if key not in seen_local:
                seen_local.add(key)
                unique_pool.append(p)

        take = min(pairs_per_scenario // 2, len(unique_pool))
        if take > 0:
            sampled_matched.extend(rng.sample(unique_pool, take))

    # Stratified sample of unmatched pairs (not already in must_include)
    sampled_unmatched: list[NormPair] = []
    for scenario_id in SCENARIOS:
        pool = unmatched_by_scenario.get(scenario_id, [])
        seen_local: set[tuple[str, str, str]] = set()
        unique_pool: list[NormPair] = []
        for p in pool:
            key = (p.raw_action, p.normalized_action, p.matched_expected)
            if key not in seen_local:
                seen_local.add(key)
                unique_pool.append(p)

        take = min(pairs_per_scenario // 2, len(unique_pool))
        if take > 0:
            sampled_unmatched.extend(rng.sample(unique_pool, take))

    # Combine
    result = deduped_must + sampled_matched + sampled_unmatched

    # Final dedup across all selected pairs
    final_seen: set[tuple[str, str, str, str, str]] = set()
    final: list[NormPair] = []
    for pair in result:
        key = (
            pair.raw_action,
            pair.normalized_action,
            pair.matched_expected,
            pair.violation_type,
            pair.scenario_id,
        )
        if key not in final_seen:
            final_seen.add(key)
            final.append(pair)

    # Sort for readability: by scenario, then violation_type, then raw_action
    final.sort(key=lambda p: (p.scenario_id, p.violation_type, p.raw_action))
    return final


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def write_csv(pairs: list[NormPair], output_path: Path) -> None:
    """Write annotation pairs to CSV."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for pair in pairs:
            writer.writerow(
                {
                    "episode_id": pair.episode_id,
                    "scenario_id": pair.scenario_id,
                    "model_name": pair.model_name,
                    "raw_action": pair.raw_action,
                    "normalized_action": pair.normalized_action,
                    "matched_expected": pair.matched_expected,
                    "violation_type": pair.violation_type,
                    "annotator_judgment": "",
                    "annotator_reasoning": "",
                }
            )


def print_summary(all_pairs: list[NormPair], sampled: list[NormPair]) -> None:
    """Print extraction and sampling statistics."""
    print("=" * 70)
    print("ACTION NORMALIZATION PAIR EXTRACTION SUMMARY")
    print("=" * 70)

    # Total extracted
    print(f"\nTotal extracted pairs (before sampling): {len(all_pairs)}")

    # Per-category breakdown (all)
    cat_counts: dict[str, int] = defaultdict(int)
    for p in all_pairs:
        cat_counts[p.category] += 1
    print("\nAll pairs by category:")
    for cat in sorted(cat_counts):
        print(f"  {cat:20s}: {cat_counts[cat]:5d}")

    # Per-scenario breakdown (all)
    scen_counts: dict[str, int] = defaultdict(int)
    for p in all_pairs:
        scen_counts[p.scenario_id] += 1
    print("\nAll pairs by scenario:")
    for scen in sorted(scen_counts):
        print(f"  {scen:45s}: {scen_counts[scen]:5d}")

    print(f"\n{'=' * 70}")
    print(f"SAMPLED PAIRS (for annotation): {len(sampled)}")
    print(f"{'=' * 70}")

    # Sampled per-category
    scat_counts: dict[str, int] = defaultdict(int)
    for p in sampled:
        scat_counts[p.category] += 1
    print("\nSampled by category:")
    for cat in sorted(scat_counts):
        print(f"  {cat:20s}: {scat_counts[cat]:5d}")

    # Sampled per-scenario
    sscen_counts: dict[str, int] = defaultdict(int)
    for p in sampled:
        sscen_counts[p.scenario_id] += 1
    print("\nSampled by scenario:")
    for scen in sorted(sscen_counts):
        print(f"  {scen:45s}: {sscen_counts[scen]:5d}")

    # Sampled per-violation-type
    sviol_counts: dict[str, int] = defaultdict(int)
    for p in sampled:
        vtype = p.violation_type if p.violation_type else "(no violation)"
        sviol_counts[vtype] += 1
    print("\nSampled by violation type:")
    for vt in sorted(sviol_counts):
        print(f"  {vt:20s}: {sviol_counts[vt]:5d}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract action normalization pairs for annotation.")
    parser.add_argument(
        "--base-dir",
        type=str,
        default=".",
        help="CGA-Bench root directory (default: current directory)",
    )
    parser.add_argument(
        "--rescored-dir",
        type=str,
        default=RESCORED_DIR,
        help=f"Rescored episodes directory relative to base-dir (default: {RESCORED_DIR})",
    )
    parser.add_argument(
        "--original-dir",
        type=str,
        default=ORIGINAL_DIR,
        help=f"Original episodes directory relative to base-dir (default: {ORIGINAL_DIR})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=OUTPUT_CSV,
        help=f"Output CSV path relative to base-dir (default: {OUTPUT_CSV})",
    )
    parser.add_argument(
        "--pairs-per-scenario",
        type=int,
        default=10,
        help="Target matched/unmatched pairs per scenario (default: 10)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for sampling (default: 42)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    base_dir = Path(args.base_dir).resolve()
    output_path = base_dir / args.output

    # Load all episode pairs
    logger.info("Loading episode pairs from %s ...", base_dir)
    episode_pairs = load_episode_pairs(base_dir, args.rescored_dir, args.original_dir)
    logger.info("Loaded %d episode pairs.", len(episode_pairs))

    if not episode_pairs:
        logger.error(
            "No episode pairs found. Check that %s and %s exist under %s",
            args.rescored_dir,
            args.original_dir,
            base_dir,
        )
        return

    # Extract all normalization pairs
    all_pairs: list[NormPair] = []
    for ep in episode_pairs:
        all_pairs.extend(extract_pairs_from_episode(ep))

    logger.info("Extracted %d total normalization pairs.", len(all_pairs))

    # Stratified sampling
    sampled = stratified_sample(
        all_pairs,
        pairs_per_scenario=args.pairs_per_scenario,
        seed=args.seed,
    )
    logger.info("Sampled %d pairs for annotation.", len(sampled))

    # Write CSV
    write_csv(sampled, output_path)
    logger.info("Wrote annotation CSV to %s", output_path)

    # Print summary
    print_summary(all_pairs, sampled)

    print(f"\nOutput: {output_path}")
    print("Annotation columns 'annotator_judgment' and 'annotator_reasoning' are empty.")
    print("See docs/ANNOTATION_GUIDE_ACTION_NORMALIZATION.md for annotation instructions.")


if __name__ == "__main__":
    main()
