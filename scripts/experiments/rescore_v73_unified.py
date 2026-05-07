#!/usr/bin/env python3
"""Unified rescore of ALL v7.3 expanded episodes.

Ensures every episode uses identical scoring methodology:
1. Loads correct expected/forbidden from ScenarioLoader
2. Recomputes OMISSION violations (expected not performed)
3. Adds COMMISSION violations (forbidden performed)
4. Preserves existing TIMING/SEQUENCE/DEVIATION violations
5. Recomputes compliance_score, sub_scores, risk metrics

Unlike rescore_v73_capped.py, this does NOT skip native (post-fix) episodes.
All episodes are scored identically regardless of original scoring path.

Usage:
    PYTHONPATH=. python scripts/experiments/rescore_v73_unified.py --dry-run
    PYTHONPATH=. python scripts/experiments/rescore_v73_unified.py
    PYTHONPATH=. python scripts/experiments/rescore_v73_unified.py --model qwen397b
    PYTHONPATH=. python scripts/experiments/rescore_v73_unified.py --sample 100
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import logging
from pathlib import Path
import random
import uuid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = ROOT / "results" / "v73_expanded"
SGSC_DIR = ROOT / "configs" / "scenarios" / "sgsc_capped"
MODELS = [
    "qwen4b",
    "deepseek_r1_7b",
    "qwen27b",
    "qwen35b",
    "gemma31b",
    "nemotron30b",
    "qwen397b",
]

# --- Scorer config (must match full_v73_expanded_runner.py) ---
SEVERITY_WEIGHTS = {
    "minor": 0.1,
    "moderate": 0.3,
    "major": 0.6,
    "severe": 0.85,
    "catastrophic": 1.0,
}
GUIDELINE_STRENGTH_WEIGHTS = {
    "I": 1.0,
    "IIa": 0.75,
    "IIb": 0.5,
    "III": 0.25,
    None: 0.5,
}
VIOLATION_TYPE_WEIGHTS = {
    "omission": 0.8,
    "commission": 1.0,
    "timing": 0.7,
    "sequence": 0.6,
    "deviation": 0.4,
}


def load_scenario_ground_truth() -> dict[str, dict]:
    """Load correct expected/forbidden for every sgsc_capped scenario."""
    from cga_bench.eval_harness.scenario_loader import ScenarioLoader

    loader = ScenarioLoader(scenarios_dir=str(SGSC_DIR))
    all_scen = loader.load_all_scenarios()
    gt: dict[str, dict] = {}
    for sid, sdef in all_scen.items():
        gt[sid] = {
            "expected_actions": sdef.expected_actions or [],
            "forbidden_actions": sdef.forbidden_actions or [],
        }
    return gt


def build_normalizer():
    """Build ActionNormalizer for matching."""
    try:
        from cga_bench.assessor_core.action_normalizer import ActionNormalizer

        return ActionNormalizer()
    except Exception:
        logger.warning("ActionNormalizer unavailable, using exact matching only")
        return None


def actions_match(
    performed: str,
    required: str,
    normalizer,
    cpg_id: str | None = None,
) -> bool:
    """Replicate _action_satisfies_requirement matching (steps 1-3)."""
    if performed == required:
        return True
    if normalizer is not None:
        norm_p = normalizer.normalize(performed, cpg_id)
        norm_r = normalizer.normalize(required, cpg_id)
        if norm_p == norm_r:
            return True
        if normalizer.are_aliases(performed, required, cpg_id):
            return True
    return False


def compute_violation_weight(v: dict) -> float:
    """Compute weight x harm for a single violation event."""
    sev = v.get("harm_severity", "moderate")
    gc = v.get("guideline_class")
    prev = v.get("preventability", 1.0)
    vtype = v.get("violation_type", "omission")

    severity_w = SEVERITY_WEIGHTS.get(sev, 0.3)
    guideline_w = GUIDELINE_STRENGTH_WEIGHTS.get(gc, 0.5)
    type_w = VIOLATION_TYPE_WEIGHTS.get(vtype, 0.5)

    weight = severity_w * guideline_w * prev * type_w
    harm = severity_w
    return weight * harm


def compute_sub_scores(
    violations: list[dict],
    total_actions: int,
    mandatory_count: int,
) -> dict[str, float]:
    """Recompute C1-C6 sub-scores from violation list."""
    counts: dict[str, int] = defaultdict(int)
    for v in violations:
        counts[v.get("violation_type", "")] += 1

    denom_m = max(mandatory_count, 1)
    denom_a = max(total_actions, 1)

    c1 = max(0.0, (denom_a - counts["deviation"]) / denom_a) if total_actions > 0 else 1.0
    c2 = max(0.0, 1.0 - counts["omission"] / denom_m)
    c3 = 0.0 if counts["commission"] > 0 else 1.0
    c4 = max(0.0, 1.0 - counts["timing"] / denom_m)
    c5 = max(0.0, 1.0 - counts["sequence"] / denom_m)
    c6 = 0.0 if counts.get("conflict", 0) > 0 else 1.0

    return {
        "C1_path_selection": round(c1, 6),
        "C2_mandatory_completion": round(c2, 6),
        "C3_forbidden_avoidance": round(c3, 6),
        "C4_timing_compliance": round(c4, 6),
        "C5_sequence_integrity": round(c5, 6),
        "C6_conflict_avoidance": round(c6, 6),
    }


def rescore_episode(
    ep: dict,
    expected_actions: list[str],
    forbidden_actions: list[str],
    normalizer,
) -> dict:
    """Rescore a single episode with canonical expected/forbidden."""
    performed_ids = [a["action_id"] for a in ep.get("actions", [])]
    total_actions = len(performed_ids)

    scenario_id = ep.get("scenario_id", "")
    cpg_id = scenario_id.split("_c0")[0] if "_c0" in scenario_id else None

    # --- Preserve TIMING/SEQUENCE/DEVIATION violations (unchanged) ---
    old_violations = ep.get("violation_events", [])
    kept_violations = [v for v in old_violations if v.get("violation_type") not in ("omission", "commission")]

    # --- Recompute OMISSION violations from ground-truth expected_actions ---
    consumed: set[str] = set()
    new_omissions: list[dict] = []
    for req in expected_actions:
        matched = False
        for pid in performed_ids:
            if pid in consumed:
                continue
            if actions_match(pid, req, normalizer, cpg_id):
                matched = True
                consumed.add(pid)
                break
        if not matched:
            new_omissions.append(
                {
                    "violation_id": str(uuid.uuid4()),
                    "violation_type": "omission",
                    "timestamp_minutes": ep.get("total_duration_minutes", 120.0),
                    "action_involved": None,
                    "expected_action": req,
                    "expected_deadline": None,
                    "actual_time": None,
                    "state_at_violation": f"patient_{scenario_id}",
                    "node_at_violation": None,
                    "harm_severity": "moderate",
                    "guideline_class": None,
                    "preventability": 1.0,
                    "description": f"Mandatory action not performed: {req}",
                    "guideline_reference": None,
                    "source": "rescore_unified",
                    "conflict_provenance": None,
                }
            )

    # --- Recompute COMMISSION violations from ground-truth forbidden_actions ---
    new_commissions: list[dict] = []
    if forbidden_actions:
        forbidden_norm = set()
        for fa in forbidden_actions:
            norm_fa = normalizer.normalize(fa, cpg_id) if normalizer else fa
            forbidden_norm.add(norm_fa)
            forbidden_norm.add(fa)

        for pid in performed_ids:
            norm_pid = normalizer.normalize(pid, cpg_id) if normalizer else pid
            if pid in forbidden_norm or norm_pid in forbidden_norm:
                new_commissions.append(
                    {
                        "violation_id": str(uuid.uuid4()),
                        "violation_type": "commission",
                        "timestamp_minutes": next(
                            (a["timestamp_minutes"] for a in ep["actions"] if a["action_id"] == pid),
                            0.0,
                        ),
                        "action_involved": pid,
                        "expected_action": None,
                        "expected_deadline": None,
                        "actual_time": None,
                        "state_at_violation": f"patient_{scenario_id}",
                        "node_at_violation": None,
                        "harm_severity": "major",
                        "guideline_class": None,
                        "preventability": 1.0,
                        "description": f"Forbidden action performed: {pid}",
                        "guideline_reference": None,
                        "source": "rescore_unified",
                        "conflict_provenance": None,
                    }
                )

    # --- Assemble final violation set ---
    all_violations = kept_violations + new_omissions + new_commissions
    violation_count = len(all_violations)

    # --- Recompute scores ---
    mandatory_count = len(expected_actions) if expected_actions else 5
    compliance_denom = max(total_actions, mandatory_count, 1)
    compliance = max(0.0, 1.0 - violation_count / compliance_denom)

    weighted_scores = [compute_violation_weight(v) for v in all_violations]
    peak_risk = max(weighted_scores) if weighted_scores else 0.0
    aggregate_risk = sum(weighted_scores)

    violations_by_type: dict[str, int] = {}
    for v in all_violations:
        vt = v.get("violation_type", "unknown")
        violations_by_type[vt] = violations_by_type.get(vt, 0) + 1

    sub_scores = compute_sub_scores(all_violations, total_actions, mandatory_count)

    # --- Patch episode ---
    ep["expected_actions"] = expected_actions
    ep["forbidden_actions"] = forbidden_actions
    ep["n_expected_actions"] = len(expected_actions)
    ep["compliance_score"] = compliance
    ep["peak_risk"] = peak_risk
    ep["aggregate_risk"] = aggregate_risk
    ep["total_violations"] = violation_count
    ep["violations_by_type"] = violations_by_type
    ep["violation_events"] = all_violations
    ep["sub_scores"] = sub_scores
    ep["rescore_version"] = "rescore_unified_v1"

    return ep


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unified rescore: ALL v7.3 expanded episodes",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing")
    parser.add_argument("--model", type=str, default=None, help="Rescore single model only")
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Rescore a random sample of N episodes per model (for testing)",
    )
    args = parser.parse_args()

    models = [args.model] if args.model else MODELS

    logger.info("Loading scenario ground truth from ScenarioLoader...")
    gt = load_scenario_ground_truth()
    logger.info(f"Loaded {len(gt)} scenarios with ground truth")

    logger.info("Building ActionNormalizer...")
    normalizer = build_normalizer()

    total_rescored = 0
    total_skipped = 0
    total_unchanged = 0

    for model in models:
        model_dir = RESULTS_DIR / model
        if not model_dir.exists():
            logger.warning(f"Model dir not found: {model_dir}")
            continue

        files = sorted(
            [f for f in model_dir.glob("*.json") if not f.name.startswith(("checkpoint", ".claim", "model_summary"))]
        )

        if args.sample > 0:
            files = random.sample(files, min(args.sample, len(files)))

        logger.info(f"[{model}] Processing {len(files)} episode files")

        model_rescored = 0
        model_skipped = 0
        model_unchanged = 0
        delta_compliance: list[float] = []

        for fpath in files:
            try:
                with open(fpath) as fh:
                    ep = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(f"Skip unreadable {fpath.name}: {exc}")
                model_skipped += 1
                continue

            scenario_id = ep.get("scenario_id", "")

            if scenario_id not in gt:
                logger.debug(f"Scenario {scenario_id} not in ground truth, skipping")
                model_skipped += 1
                continue

            correct_expected = gt[scenario_id]["expected_actions"]
            correct_forbidden = gt[scenario_id]["forbidden_actions"]

            old_compliance = ep.get("compliance_score", 0.0)
            old_version = ep.get("rescore_version", "native")

            rescored = rescore_episode(ep, correct_expected, correct_forbidden, normalizer)

            new_compliance = rescored["compliance_score"]
            delta = new_compliance - old_compliance
            delta_compliance.append(delta)

            if abs(delta) < 1e-9:
                model_unchanged += 1

            if not args.dry_run:
                with open(fpath, "w") as fh:
                    json.dump(rescored, fh, indent=2, default=str)

            model_rescored += 1

        avg_delta = sum(delta_compliance) / len(delta_compliance) if delta_compliance else 0.0
        n_changed = sum(1 for d in delta_compliance if abs(d) > 1e-9)
        logger.info(
            f"[{model}] rescored={model_rescored}, skipped={model_skipped}, "
            f"unchanged={model_unchanged}, changed={n_changed}, "
            f"avg_delta={avg_delta:+.4f}"
        )

        total_rescored += model_rescored
        total_skipped += model_skipped
        total_unchanged += model_unchanged

    logger.info("=" * 60)
    logger.info(f"TOTAL: rescored={total_rescored}, unchanged={total_unchanged}, skipped={total_skipped}")
    if args.dry_run:
        logger.info("DRY RUN -- no files modified")


if __name__ == "__main__":
    main()
