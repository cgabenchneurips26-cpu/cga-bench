#!/usr/bin/env python3
"""P0-2 supplement: Compare v6 manual scenarios vs SGSC-generated scenarios.

For each of the 14 Pilot guidelines, identifies matching v6 scenarios in
configs/scenarios/ and compares expected_actions, forbidden_actions, and
constraint types to detect unintended verdict flips.

Usage:
    PYTHONPATH=. python scripts/sgsc/compare_old_new_verdicts.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = REPO_ROOT / "configs" / "sgsc" / "pilot_14_registry.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

logger = logging.getLogger("compare_verdicts")

# Map from guideline_id to domain patterns that match v6 scenario filenames
_GUIDELINE_DOMAIN_PATTERNS: dict[str, list[str]] = {
    "ssc_sepsis_hour1_bundle": ["sepsis", "septic_shock"],
    "pulmonary_embolism": ["pulmonary_embolism", "pe_"],
    "aabb_transfusion": ["transfusion", "aabb"],
    "acls_cardiac_arrest": ["cardiac_arrest", "acls"],
    "ada_dka_management": ["dka", "diabetic_ketoacidosis"],
    "aha_chest_pain_evaluation": ["chest_pain", "stemi", "nstemi", "acs_"],
    "aha_heart_failure_2022": ["heart_failure", "hf_", "chf_"],
    "idsa_meningitis": ["meningitis"],
    "pals_pediatric_emergency": ["pals", "pediatric"],
    "aha_stroke_2019": ["stroke", "tpa_"],
    "anaphylaxis_management": ["anaphylaxis"],
    "status_epilepticus": ["epilepticus", "seizure"],
    "kdigo_aki_full": ["aki_", "acute_kidney"],
    "gina_asthma_exacerbation": ["asthma", "exacerbation"],
}


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
    except Exception:
        return "unknown"


def _hash_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def load_v6_scenarios(config_dir: Path) -> dict[str, dict]:
    """Load all v6 scenario YAMLs from configs/scenarios/."""
    import yaml

    scenarios: dict[str, dict] = {}
    scenario_dir = config_dir / "scenarios"
    if not scenario_dir.is_dir():
        return scenarios

    for yaml_file in sorted(scenario_dir.glob("*.yaml")):
        try:
            content = yaml_file.read_text()
            docs = list(yaml.safe_load_all(content))
            for doc in docs:
                if isinstance(doc, dict):
                    sid = doc.get("scenario_id", yaml_file.stem)
                    scenarios[sid] = doc
        except Exception:
            pass

    return scenarios


def load_sgsc_scenarios(sgsc_dir: Path, guideline_id: str) -> dict[str, dict]:
    """Load SGSC private scenarios for a guideline (has expected_actions)."""
    scenarios: dict[str, dict] = {}
    guideline_dir = sgsc_dir / guideline_id

    if not guideline_dir.is_dir():
        return scenarios

    for priv_file in guideline_dir.glob("*_scenarios_private.json"):
        try:
            data = json.loads(priv_file.read_text())
            if isinstance(data, dict):
                scenarios.update(data)
        except (json.JSONDecodeError, OSError):
            pass

    return scenarios


def match_v6_to_guideline(
    v6_scenarios: dict[str, dict],
    guideline_id: str,
) -> dict[str, dict]:
    """Find v6 scenarios that match a guideline by domain patterns."""
    patterns = _GUIDELINE_DOMAIN_PATTERNS.get(guideline_id, [])
    if not patterns:
        return {}

    matched: dict[str, dict] = {}
    for sid, scenario in v6_scenarios.items():
        sid_lower = sid.lower()
        # Check domain match
        graph_file = str(scenario.get("graph_file", "")).lower()
        description = str(scenario.get("description", "")).lower()

        if any(p in sid_lower or p in graph_file or p in description for p in patterns):
            matched[sid] = scenario

    return matched


def compute_action_overlap(
    v6_actions: set[str],
    sgsc_actions: set[str],
) -> float:
    """Compute Jaccard overlap between two action sets."""
    if not v6_actions and not sgsc_actions:
        return 1.0
    union = v6_actions | sgsc_actions
    if not union:
        return 1.0
    return len(v6_actions & sgsc_actions) / len(union)


def compare_guideline(
    v6_matched: dict[str, dict],
    sgsc_scenarios: dict[str, dict],
    guideline_id: str,
) -> dict:
    """Compare v6 vs SGSC scenarios for one guideline."""
    # Collect v6 action sets
    v6_expected: set[str] = set()
    v6_forbidden: set[str] = set()
    for s in v6_matched.values():
        for a in s.get("expected_actions", []):
            if isinstance(a, str):
                v6_expected.add(a)
            elif isinstance(a, dict):
                v6_expected.add(a.get("action_id", ""))
        for a in s.get("forbidden_actions", []):
            if isinstance(a, str):
                v6_forbidden.add(a)

    # Collect SGSC action sets
    sgsc_expected: set[str] = set()
    sgsc_forbidden: set[str] = set()
    for s in sgsc_scenarios.values():
        for a in s.get("expected_actions", []):
            if isinstance(a, str):
                sgsc_expected.add(a)
            elif isinstance(a, dict):
                sgsc_expected.add(a.get("action_id", ""))
        for a in s.get("forbidden_actions", []):
            if isinstance(a, str):
                sgsc_forbidden.add(a)

    overlap = compute_action_overlap(v6_expected, sgsc_expected)

    # Detect additions/removals
    additions = sgsc_expected - v6_expected
    removals = v6_expected - sgsc_expected

    return {
        "guideline_id": guideline_id,
        "v6_scenario_count": len(v6_matched),
        "sgsc_scenario_count": len(sgsc_scenarios),
        "v6_expected_actions": len(v6_expected),
        "sgsc_expected_actions": len(sgsc_expected),
        "action_overlap": round(overlap, 4),
        "constraint_additions": len(additions),
        "constraint_removals": len(removals),
        "added_actions": sorted(additions)[:10],
        "removed_actions": sorted(removals)[:10],
    }


def run_comparison(sgsc_dir: Path, config_dir: Path) -> dict:
    """Run the full old-vs-new verdict comparison."""
    registry = json.loads(REGISTRY_PATH.read_text())
    guideline_ids = [g["guideline_id"] for g in registry["guidelines"]]

    v6_scenarios = load_v6_scenarios(config_dir)
    logger.info("Loaded %d v6 scenarios", len(v6_scenarios))

    input_files: list[Path] = []
    input_files.extend((config_dir / "scenarios").glob("*.yaml") if (config_dir / "scenarios").is_dir() else [])
    input_files.extend(sgsc_dir.rglob("*_scenarios_private.json"))

    per_guideline: list[dict] = []
    total_v6_matched = 0
    total_sgsc = 0
    total_additions = 0
    total_removals = 0
    overlap_sum = 0.0
    compared_count = 0

    for gid in guideline_ids:
        v6_matched = match_v6_to_guideline(v6_scenarios, gid)
        sgsc = load_sgsc_scenarios(sgsc_dir, gid)

        comparison = compare_guideline(v6_matched, sgsc, gid)
        per_guideline.append(comparison)

        total_v6_matched += comparison["v6_scenario_count"]
        total_sgsc += comparison["sgsc_scenario_count"]
        total_additions += comparison["constraint_additions"]
        total_removals += comparison["constraint_removals"]

        if comparison["v6_scenario_count"] > 0:
            overlap_sum += comparison["action_overlap"]
            compared_count += 1

    avg_overlap = overlap_sum / compared_count if compared_count > 0 else 0.0

    # Verdict flip candidates: guidelines where overlap < 50% and v6 has scenarios
    flip_candidates = sum(1 for p in per_guideline if p["v6_scenario_count"] > 0 and p["action_overlap"] < 0.5)

    status = "pass"
    failures: list[dict] = []
    if flip_candidates > 0:
        status = "warn"
        for p in per_guideline:
            if p["v6_scenario_count"] > 0 and p["action_overlap"] < 0.5:
                failures.append(
                    {
                        "guideline_id": p["guideline_id"],
                        "detail": f"Low action overlap ({p['action_overlap']:.1%}) — verdict flip risk",
                    }
                )

    report = {
        "check_name": "old_new_verdict_delta",
        "status": status,
        "commit": _git_commit(),
        "input_hash": _hash_files(input_files),
        "metrics": {
            "guidelines_compared": len(guideline_ids),
            "v6_scenarios_matched": total_v6_matched,
            "sgsc_scenarios_total": total_sgsc,
            "action_overlap_rate": round(avg_overlap, 4),
            "constraint_additions": total_additions,
            "constraint_removals": total_removals,
            "verdict_flip_candidates": flip_candidates,
        },
        "per_guideline": per_guideline,
        "failures": failures,
    }

    report_bytes = json.dumps(report, sort_keys=True).encode()
    report["output_hash"] = hashlib.sha256(report_bytes).hexdigest()

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P0-2 supplement: Compare old vs new verdicts")
    parser.add_argument("--sgsc-dir", default=str(REPO_ROOT / "sgsc_output"))
    parser.add_argument("--config-dir", default=str(REPO_ROOT / "configs"))
    parser.add_argument(
        "--output", default=str(REPO_ROOT / "evidence_pack" / "analysis" / "old_new_verdict_delta.json")
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    sgsc_dir = Path(args.sgsc_dir)
    config_dir = Path(args.config_dir)

    if not sgsc_dir.is_dir():
        logger.error("SGSC output dir not found: %s", sgsc_dir)
        return 1

    report = run_comparison(sgsc_dir, config_dir)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("Report written to %s", output_path)

    m = report["metrics"]
    print("\n=== Old vs New Verdict Delta ===")
    print(f"Status: {report['status'].upper()}")
    print(f"Guidelines compared: {m['guidelines_compared']}")
    print(f"V6 scenarios matched: {m['v6_scenarios_matched']}")
    print(f"SGSC scenarios total: {m['sgsc_scenarios_total']}")
    print(f"Action overlap rate: {m['action_overlap_rate']:.1%}")
    print(f"Constraint additions: {m['constraint_additions']}")
    print(f"Constraint removals: {m['constraint_removals']}")
    print(f"Verdict flip candidates: {m['verdict_flip_candidates']}")

    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
