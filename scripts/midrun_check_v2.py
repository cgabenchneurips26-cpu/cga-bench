#!/usr/bin/env python3
"""Mid-run quality check for full_690_v2 benchmark execution.

Checks:
1. Empty rate comparison (RAG improvement)
2. Existing domain regression
3. Per-model progress and speed
4. Error/crash analysis

Usage:
    PYTHONPATH=. python scripts/midrun_check_v2.py [results_dir]
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

RESULTS_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results/full_690_v2")
OLD_RESULTS_DIR = Path("results_old_rag_backup/full_690_20260403")
LOG_DIR = Path("results")

MODELS = ["oss120b", "qwen35b", "qwen27b", "qwen4b", "qwen397b"]

# Previously always-empty domains (274/690 = 39.7%)
PREV_EMPTY_DOMAINS = [
    "aki",
    "asthma",
    "caki",
    "meningitis",
    "dka",
    "acls",
    "burn",
    "obstetric",
    "toxicology",
    "anaphylaxis",
    "agitation",
    "af",
    "cap",
    "copd",
    "gi_bleeding",
    "hypertensive",
    "pals",
    "pe",
    "status_epilepticus",
]

# Previously working domains
PREV_WORKING_DOMAINS = ["sepsis", "chest_pain", "stroke", "heart_failure"]

TARGET_PER_MODEL = 2070  # 690 × 3


def load_episodes(results_dir: Path, model: str) -> list[dict[str, Any]]:
    """Load all episode JSON files for a model."""
    model_dir = results_dir / model
    if not model_dir.exists():
        return []
    episodes = []
    for f in model_dir.glob("*.json"):
        if f.name in ("checkpoint.json", "model_summary.json"):
            continue
        try:
            with open(f) as fh:
                episodes.append(json.load(fh))
        except (json.JSONDecodeError, OSError):
            continue
    return episodes


def extract_domain(scenario_id: str) -> str:
    """Extract domain from scenario_id."""
    domain_map = {
        "septic_shock": "sepsis",
        "sepsis": "sepsis",
        "stemi": "chest_pain",
        "nstemi": "chest_pain",
        "chest_pain": "chest_pain",
        "stroke": "stroke",
        "tpa": "stroke",
        "heart_failure": "heart_failure",
        "hfref": "heart_failure",
        "adhf": "heart_failure",
        "aki": "aki",
        "renal": "aki",
        "asthma": "asthma",
        "caki": "caki",
        "contrast": "caki",
        "meningitis": "meningitis",
        "dka": "dka",
        "diabetic_ketoacidosis": "dka",
        "acls": "acls",
        "cardiac_arrest": "acls",
        "burn": "burn",
        "obstetric": "obstetric",
        "hemorrhage": "obstetric",
        "toxicology": "toxicology",
        "overdose": "toxicology",
        "poisoning": "toxicology",
        "anaphylaxis": "anaphylaxis",
        "agitation": "agitation",
        "atrial_fibrillation": "af",
        "af_": "af",
        "cap_": "cap",
        "pneumonia": "cap",
        "copd": "copd",
        "gi_bleed": "gi_bleeding",
        "gi_bleeding": "gi_bleeding",
        "hypertensive": "hypertensive",
        "pals": "pals",
        "pediatric": "pals",
        "pe_": "pe",
        "pulmonary_embolism": "pe",
        "status_epilepticus": "status_epilepticus",
        "seizure": "status_epilepticus",
    }
    sid_lower = scenario_id.lower()
    for pattern, domain in domain_map.items():
        if pattern in sid_lower:
            return domain
    return "unknown"


def check_1_empty_rate(all_episodes: dict[str, list[dict]]) -> dict[str, Any]:
    """Check 1: Empty rate comparison."""
    logger.info("\n" + "=" * 70)
    logger.info("CHECK 1: Empty Rate Comparison (RAG Improvement)")
    logger.info("=" * 70)

    flat = [ep for eps in all_episodes.values() for ep in eps]
    if not flat:
        logger.info("  No episodes yet.")
        return {}

    total = len(flat)
    empty = sum(1 for ep in flat if ep.get("actions_count", 0) == 0)
    empty_rate = empty / total if total > 0 else 0

    logger.info(f"\n  Overall: {empty}/{total} empty = {empty_rate:.1%}")
    logger.info("  Previous run: 274/690 = 39.7% always-empty")
    logger.info(f"  Improvement: {39.7 - empty_rate * 100:+.1f}pp")

    # Per-domain breakdown for previously empty domains
    domain_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "empty": 0, "nonempty": 0})
    for ep in flat:
        domain = extract_domain(ep.get("scenario_id", ""))
        domain_stats[domain]["total"] += 1
        if ep.get("actions_count", 0) == 0:
            domain_stats[domain]["empty"] += 1
        else:
            domain_stats[domain]["nonempty"] += 1

    logger.info("\n  Previously-empty domains (key question: actions > 0?):")
    logger.info(f"  {'Domain':<25} {'Total':>6} {'Empty':>6} {'NonEmpty':>8} {'EmptyRate':>10}")
    logger.info(f"  {'-' * 55}")

    improved = 0
    still_empty = 0
    for domain in sorted(PREV_EMPTY_DOMAINS):
        stats = domain_stats.get(domain, {"total": 0, "empty": 0, "nonempty": 0})
        if stats["total"] == 0:
            continue
        rate = stats["empty"] / stats["total"]
        marker = " ★" if stats["nonempty"] > 0 else " ✗"
        logger.info(
            f"  {domain:<25} {stats['total']:>6} {stats['empty']:>6} {stats['nonempty']:>8} {rate:>9.1%}{marker}"
        )
        if stats["nonempty"] > 0:
            improved += 1
        else:
            still_empty += 1

    logger.info(f"\n  Improved domains (have non-empty episodes): {improved}")
    logger.info(f"  Still all-empty domains: {still_empty}")

    return {
        "total_episodes": total,
        "empty_episodes": empty,
        "empty_rate": round(empty_rate, 4),
        "prev_empty_rate": 0.397,
        "improved_domains": improved,
        "still_empty_domains": still_empty,
        "domain_stats": {k: dict(v) for k, v in domain_stats.items()},
    }


def check_2_regression(all_episodes: dict[str, list[dict]]) -> dict[str, Any]:
    """Check 2: Existing domain regression."""
    logger.info("\n" + "=" * 70)
    logger.info("CHECK 2: Existing Domain Regression")
    logger.info("=" * 70)

    flat = [ep for eps in all_episodes.values() for ep in eps]
    if not flat:
        logger.info("  No episodes yet.")
        return {}

    # Load old results for comparison
    old_scores: dict[str, list[float]] = defaultdict(list)
    for model in MODELS:
        for ep in load_episodes(OLD_RESULTS_DIR, model):
            domain = extract_domain(ep.get("scenario_id", ""))
            if domain in PREV_WORKING_DOMAINS and ep.get("actions_count", 0) > 0:
                old_scores[domain].append(ep.get("compliance_score", 0))

    # New scores
    new_scores: dict[str, list[float]] = defaultdict(list)
    for ep in flat:
        domain = extract_domain(ep.get("scenario_id", ""))
        if domain in PREV_WORKING_DOMAINS and ep.get("actions_count", 0) > 0:
            new_scores[domain].append(ep.get("compliance_score", 0))

    logger.info(
        f"\n  {'Domain':<20} {'Old Mean':>10} {'Old N':>6} {'New Mean':>10} {'New N':>6} {'Delta':>8} {'Status':>10}"
    )
    logger.info(f"  {'-' * 70}")

    results = {}
    for domain in PREV_WORKING_DOMAINS:
        old_vals = old_scores.get(domain, [])
        new_vals = new_scores.get(domain, [])
        old_mean = sum(old_vals) / len(old_vals) if old_vals else 0
        new_mean = sum(new_vals) / len(new_vals) if new_vals else 0
        delta = new_mean - old_mean
        status = "OK" if abs(delta) < 0.05 or new_mean >= old_mean else "REGRESS"
        if not new_vals:
            status = "NO_DATA"
        logger.info(
            f"  {domain:<20} {old_mean:>10.4f} {len(old_vals):>6} {new_mean:>10.4f} {len(new_vals):>6} {delta:>+8.4f} {status:>10}"
        )
        results[domain] = {
            "old_mean": round(old_mean, 4),
            "new_mean": round(new_mean, 4),
            "delta": round(delta, 4),
            "status": status,
        }

    return results


def check_3_progress(all_episodes: dict[str, list[dict]]) -> dict[str, Any]:
    """Check 3: Per-model progress and speed."""
    logger.info("\n" + "=" * 70)
    logger.info("CHECK 3: Per-Model Progress")
    logger.info("=" * 70)

    logger.info(f"\n  {'Model':<12} {'Episodes':>10} {'Target':>8} {'Progress':>10} {'Empty':>6} {'EmptyRate':>10}")
    logger.info(f"  {'-' * 56}")

    results = {}
    for model in MODELS:
        episodes = all_episodes.get(model, [])
        n = len(episodes)
        empty = sum(1 for ep in episodes if ep.get("actions_count", 0) == 0)
        pct = n / TARGET_PER_MODEL * 100
        erate = empty / n if n > 0 else 0
        logger.info(f"  {model:<12} {n:>10} {TARGET_PER_MODEL:>8} {pct:>9.1f}% {empty:>6} {erate:>9.1%}")
        results[model] = {"episodes": n, "progress_pct": round(pct, 1), "empty": empty, "empty_rate": round(erate, 4)}

    return results


def check_4_errors() -> dict[str, Any]:
    """Check 4: Error/crash analysis from logs."""
    logger.info("\n" + "=" * 70)
    logger.info("CHECK 4: Error/Crash Analysis")
    logger.info("=" * 70)

    results = {}
    for model in MODELS:
        log_path = LOG_DIR / f"log_{model}.txt"
        if not log_path.exists():
            logger.info(f"  {model}: No log file")
            results[model] = {"errors": 0, "none_lower": 0, "health_fail": 0}
            continue

        text = log_path.read_text(errors="replace")
        errors = len(re.findall(r"\[ERROR\]", text))
        none_lower = len(re.findall(r"NoneType.*lower|'NoneType'.*has no attribute.*'lower'", text))
        health_fails = len(re.findall(r"Health FAIL", text))
        fails = len(re.findall(r"^.*FAIL\s+\w+", text, re.MULTILINE))

        logger.info(
            f"  {model}: {errors} errors, {none_lower} NoneType.lower(), {health_fails} health fails, {fails} episode fails"
        )
        results[model] = {
            "errors": errors,
            "none_lower": none_lower,
            "health_fail": health_fails,
            "episode_fails": fails,
        }

    return results


def main() -> None:
    logger.info("=" * 70)
    logger.info(f"MID-RUN CHECK — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Results dir: {RESULTS_DIR}")
    logger.info("=" * 70)

    # Load all episodes
    all_episodes: dict[str, list[dict]] = {}
    for model in MODELS:
        all_episodes[model] = load_episodes(RESULTS_DIR, model)

    total = sum(len(v) for v in all_episodes.values())
    logger.info(f"\nTotal episodes loaded: {total}")

    r1 = check_1_empty_rate(all_episodes)
    r2 = check_2_regression(all_episodes)
    r3 = check_3_progress(all_episodes)
    r4 = check_4_errors()

    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "results_dir": str(RESULTS_DIR),
        "total_episodes": total,
        "check_1_empty_rate": r1,
        "check_2_regression": r2,
        "check_3_progress": r3,
        "check_4_errors": r4,
    }

    out_path = Path("evidence_pack/analysis/midrun_check_v2.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info(f"\nReport saved to {out_path}")


if __name__ == "__main__":
    main()
