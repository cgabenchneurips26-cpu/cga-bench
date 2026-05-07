
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""Action Annotation Sheet Generator (Defense against Attack 3.3)

Extracts agent actions from episode results and generates a CSV
for human annotation of action normalization accuracy.

Usage:
    PYTHONPATH=. python scripts/generate_action_annotation_sheet.py
"""

from __future__ import annotations

from collections import defaultdict
import csv
import json
from pathlib import Path
import random

BASE_DIR = Path(__file__).parent.parent
RESULTS_DIR = BASE_DIR / "results" / "clean_slate_rescored"
OUTPUT_DIR = BASE_DIR / "evidence_pack" / "annotation"
OUTPUT_FILE = OUTPUT_DIR / "action_annotation_sheet.csv"

TARGET_SAMPLE_SIZE = 100


def load_all_episodes() -> list[dict]:
    """Load all episode JSON files from results directory.

    Returns:
        List of episode dicts with source file path added.
    """
    episodes = []

    if not RESULTS_DIR.exists():
        print(f"Results directory not found: {RESULTS_DIR}")
        return episodes

    for model_dir in sorted(RESULTS_DIR.iterdir()):
        if not model_dir.is_dir():
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            if ep_file.name == "rescore_summary.json":
                continue
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                ep["_source_file"] = str(ep_file)
                ep["_model_dir"] = model_dir.name
                episodes.append(ep)
            except (json.JSONDecodeError, OSError):
                continue

    return episodes


def get_domain(scenario_id: str) -> str:
    """Extract domain from scenario_id for stratification."""
    domain_prefixes = {
        "septic_shock": "sepsis",
        "sepsis": "sepsis",
        "stemi": "chest_pain",
        "nstemi": "chest_pain",
        "chest_pain": "chest_pain",
        "stroke": "stroke",
        "hfref": "heart_failure",
        "adhf": "heart_failure",
        "aki": "aki",
        "contrast_aki": "aki",
        "dka": "dka",
        "af_": "atrial_fibrillation",
        "copd": "copd",
        "pe_": "pulmonary_embolism",
        "gi_bleed": "gi_bleeding",
        "cap_": "pneumonia",
        "hypertensive": "hypertensive_emergency",
        "anaphylaxis": "anaphylaxis",
        "asthma": "asthma",
        "meningitis": "meningitis",
        "acls": "acls",
        "status_epilepticus": "epilepticus",
        "toxicology": "toxicology",
    }
    scenario_lower = scenario_id.lower()
    for prefix, domain in domain_prefixes.items():
        if scenario_lower.startswith(prefix):
            return domain
    return "other"


def stratified_sample(
    episodes: list[dict],
    n: int = TARGET_SAMPLE_SIZE,
) -> list[dict]:
    """Stratified sampling by scenario domain.

    Args:
        episodes: All available episodes.
        n: Target sample size.

    Returns:
        Sampled episodes.
    """
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for ep in episodes:
        domain = get_domain(ep.get("scenario_id", ""))
        by_domain[domain].append(ep)

    n_domains = len(by_domain)
    if n_domains == 0:
        return []

    per_domain = max(1, n // n_domains)
    sampled = []

    random.seed(42)
    for domain in sorted(by_domain.keys()):
        pool = by_domain[domain]
        k = min(per_domain, len(pool))
        sampled.extend(random.sample(pool, k))

    # Fill remainder from largest domains
    if len(sampled) < n:
        remaining = [ep for ep in episodes if ep not in sampled]
        extra = min(n - len(sampled), len(remaining))
        sampled.extend(random.sample(remaining, extra))

    return sampled[:n]


def extract_action_rows(episode: dict) -> list[dict]:
    """Extract action rows from an episode for annotation.

    Args:
        episode: Episode dict.

    Returns:
        List of row dicts for the CSV.
    """
    rows = []
    violations = episode.get("new_violation_events", [])

    # Build violation map for cross-reference
    violation_map: dict[str, str] = {}
    for v in violations:
        action = v.get("action_involved") or v.get("expected_action", "")
        if action:
            violation_map[action] = v.get("violation_type", "")

    # Extract from violations (these have the most annotation value)
    for i, v in enumerate(violations):
        action = v.get("action_involved") or v.get("expected_action", "")
        rows.append(
            {
                "episode_id": episode.get("scenario_id", "") + "_" + episode.get("_model_dir", ""),
                "scenario_id": episode.get("scenario_id", ""),
                "model": episode.get("model_name", episode.get("_model_dir", "")),
                "step_number": i + 1,
                "raw_agent_output": v.get("description", "")[:200],
                "normalized_action": action,
                "violation_type": v.get("violation_type", ""),
                "harm_severity": v.get("harm_severity", ""),
                "matched_expected": v.get("expected_action", ""),
                "annotator_correct": "",
                "annotator_correct_action": "",
                "annotator_notes": "",
            }
        )

    return rows


def main() -> None:
    """Generate action annotation sheet."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    episodes = load_all_episodes()
    print(f"Loaded {len(episodes)} episodes from {RESULTS_DIR}")

    if not episodes:
        print("No episodes found. Generating template CSV.")
        fieldnames = [
            "episode_id",
            "scenario_id",
            "model",
            "step_number",
            "raw_agent_output",
            "normalized_action",
            "violation_type",
            "harm_severity",
            "matched_expected",
            "annotator_correct",
            "annotator_correct_action",
            "annotator_notes",
        ]
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
        print(f"Empty template saved to {OUTPUT_FILE}")
        return

    sampled = stratified_sample(episodes, n=TARGET_SAMPLE_SIZE)
    print(f"Stratified sample: {len(sampled)} episodes")

    all_rows = []
    for ep in sampled:
        rows = extract_action_rows(ep)
        all_rows.extend(rows)

    if not all_rows:
        print("No action rows extracted.")
        return

    fieldnames = list(all_rows[0].keys())
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    # Domain distribution of sample
    domain_dist = defaultdict(int)
    for ep in sampled:
        domain_dist[get_domain(ep.get("scenario_id", ""))] += 1

    print(f"\nGenerated annotation sheet: {len(all_rows)} rows from {len(sampled)} episodes")
    print(f"Saved to {OUTPUT_FILE}")
    print("\nDomain distribution of sample:")
    for domain, count in sorted(domain_dist.items(), key=lambda x: -x[1]):
        print(f"  {domain}: {count}")


if __name__ == "__main__":
    main()
