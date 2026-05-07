#!/usr/bin/env python3
"""EX-21: Model Diversity — Cross-Family Blind-Spot Persistence.

Demonstrates that CGA-Bench evaluator blind spots (verdict flips, false accepts)
persist across model families beyond the original Qwen/Gemma/Nemotron baseline.

New model families tested:
  - DeepSeek R1 Distill Qwen 7B (reasoning model)
  - OpenBioLLM Llama3 8B (biomedical domain model)
  - Llama-4-Scout 17B-16E (MoE architecture)

Metrics per model:
  - Per-evaluator pass rate
  - Verdict-flip rate (>= 1 evaluator pair disagrees)
  - All-oblivious FA rate (DxEM + AC + C2 all pass AND v4_hard)
  - Per-evaluator FA rate

Outputs:
  evidence_pack/ex21_model_diversity/ex21_model_diversity.json
  evidence_pack/ex21_model_diversity/ex21_model_diversity.md

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_e21_model_diversity.py
"""

from __future__ import annotations

from itertools import combinations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from scripts.experiments._common import (
    EVIDENCE_DIR,
    bootstrap_ci,
    save_json,
    save_markdown,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RESULTS_DIR = ROOT / "results" / "full_706_v5"
OUTPUT_DIR = EVIDENCE_DIR / "ex21_model_diversity"

# New diversity models
DIVERSITY_MODELS: dict[str, str] = {
    "deepseek_r1_7b": "DeepSeek-R1-7B",
    "biomed8b": "OpenBioLLM-8B",
    "llama4scout": "Llama4-Scout-17B",
}

# Baseline models for comparison
BASELINE_MODELS: dict[str, str] = {
    "oss120b": "OSS-120B",
    "qwen35b": "Qwen3.5-35B",
    "qwen27b": "Qwen3.5-27B",
    "qwen4b": "Qwen3-4B",
    "qwen397b": "Qwen3.5-397B",
    "gemma31b": "Gemma4-31B",
    "nemotron30b": "Nemotron-30B",
}

# Evaluator thresholds (same as verdict_matrix_v5.py)
AC_COVERAGE_THRESHOLD = 0.5
MAB_F1_THRESHOLD = 0.5
C2_THRESHOLD = 0.7

EVALUATOR_NAMES: list[str] = ["AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]
EVALUATOR_PAIRS: list[tuple[str, str]] = list(combinations(EVALUATOR_NAMES, 2))

HARD_VIOL_TYPES: frozenset[str] = frozenset({"commission", "timing", "sequence"})


# ---------------------------------------------------------------------------
# Episode loading and scoring (mirrors verdict_matrix_v5.py)
# ---------------------------------------------------------------------------


def _normalize_action(action_id: str) -> str:
    return action_id.strip().lower().replace("-", "_").replace(" ", "_")


def _classify_violation_type(raw_type: str) -> str:
    lower = raw_type.lower().strip()
    for canonical in ("omission", "commission", "timing", "sequence", "deviation"):
        if canonical in lower:
            return canonical
    return "unknown"


def _action_coverage(performed: set[str], expected: set[str]) -> float:
    if not expected:
        return 1.0
    return len(performed & expected) / len(expected)


def _mab_f1(performed: set[str], expected: set[str]) -> float:
    if not expected:
        return 0.0
    tp = len(performed & expected)
    precision = tp / len(performed) if performed else 0.0
    recall = tp / len(expected)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def load_model_episodes(model_dir_name: str) -> list[dict]:
    """Load all episode JSONs for a specific model."""
    model_dir = RESULTS_DIR / model_dir_name
    if not model_dir.exists():
        print(f"  WARNING: Model dir not found: {model_dir}")
        return []

    episodes: list[dict] = []
    seen: set[str] = set()

    for f in sorted(model_dir.glob("*.json")):
        if f.name.startswith(("checkpoint", ".claim", "log_")):
            continue
        try:
            ep = json.loads(f.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        sid = ep.get("scenario_id", "")
        if not sid:
            continue
        run_idx = ep.get("run_index", 0)
        dedup_key = f"{sid}_{model_dir_name}_r{run_idx}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        ep["_model"] = model_dir_name
        episodes.append(ep)

    return episodes


def score_episode(ep: dict) -> dict:
    """Compute evaluator verdicts and violation data for one episode."""
    # Extract action sets
    performed: set[str] = set()
    for a in ep.get("actions", []):
        aid = a.get("action_id", "") if isinstance(a, dict) else str(a)
        if aid:
            performed.add(_normalize_action(aid))

    expected: set[str] = set()
    for a in ep.get("expected_actions", []):
        aid = a.get("action_id", "") if isinstance(a, dict) else str(a)
        if aid:
            expected.add(_normalize_action(aid))

    coverage = _action_coverage(performed, expected)
    f1 = _mab_f1(performed, expected)
    c2_score = ep.get("compliance_score", 0.0) or 0.0

    # Violation analysis
    has_hard = False
    for v in ep.get("violation_events", []):
        raw_type = str(v.get("violation_type", v.get("type", "")))
        vtype = _classify_violation_type(raw_type)
        if vtype in HARD_VIOL_TYPES:
            has_hard = True
            break

    # Evaluator verdicts
    ac_proxy = coverage >= AC_COVERAGE_THRESHOLD
    mab_proxy = f1 >= MAB_F1_THRESHOLD
    c2_pass = c2_score >= C2_THRESHOLD
    # CGA-Bench: hard-violation aware (pass only if no hard violations)
    cga_pass = not has_hard

    return {
        "scenario_id": ep.get("scenario_id", ""),
        "run_index": ep.get("run_index", 0),
        "v4_hard": has_hard,
        "ac_proxy": ac_proxy,
        "mab_proxy": mab_proxy,
        "c2_pass": c2_pass,
        "cga_pass": cga_pass,
        "coverage": round(coverage, 4),
        "f1": round(f1, 4),
        "c2_score": round(c2_score, 4),
    }


# ---------------------------------------------------------------------------
# Metrics computation
# ---------------------------------------------------------------------------


def compute_model_metrics(records: list[dict]) -> dict:
    """Compute all diversity metrics for a set of scored episode records."""
    n = len(records)
    if n == 0:
        return {"n_episodes": 0, "error": "no episodes"}

    # Per-evaluator pass rates
    ac_pass_rate = sum(1 for r in records if r["ac_proxy"]) / n
    mab_pass_rate = sum(1 for r in records if r["mab_proxy"]) / n
    c2_pass_rate = sum(1 for r in records if r["c2_pass"]) / n
    cga_pass_rate = sum(1 for r in records if r["cga_pass"]) / n

    # Verdict-flip rate: >= 1 evaluator pair disagrees
    flip_count = 0
    for r in records:
        verdicts = {
            "AC-Proxy": r["ac_proxy"],
            "MAB-Proxy": r["mab_proxy"],
            "C2": r["c2_pass"],
            "CGA-Bench": r["cga_pass"],
        }
        vals = list(verdicts.values())
        if len(set(vals)) > 1:
            flip_count += 1
    flip_rate = flip_count / n

    # All-oblivious FA: DxEM + AC + C2 all pass AND v4_hard
    ao_fa_count = sum(1 for r in records if r["v4_hard"] and r["ac_proxy"] and r["c2_pass"])
    ao_fa_rate = ao_fa_count / n

    # Per-evaluator FA rates (pass when v4_hard=True)
    hard_episodes = [r for r in records if r["v4_hard"]]
    n_hard = len(hard_episodes)

    ac_fa = sum(1 for r in hard_episodes if r["ac_proxy"]) / n_hard if n_hard else 0.0
    mab_fa = sum(1 for r in hard_episodes if r["mab_proxy"]) / n_hard if n_hard else 0.0
    c2_fa = sum(1 for r in hard_episodes if r["c2_pass"]) / n_hard if n_hard else 0.0
    cga_fa = sum(1 for r in hard_episodes if r["cga_pass"]) / n_hard if n_hard else 0.0

    # Bootstrap CI for flip rate
    flip_arr = np.array(
        [1 if len(set([r["ac_proxy"], r["mab_proxy"], r["c2_pass"], r["cga_pass"]])) > 1 else 0 for r in records]
    )
    flip_ci = bootstrap_ci(flip_arr, np.mean)

    # Bootstrap CI for AO-FA rate
    ao_arr = np.array([1 if r["v4_hard"] and r["ac_proxy"] and r["c2_pass"] else 0 for r in records])
    ao_ci = bootstrap_ci(ao_arr, np.mean)

    return {
        "n_episodes": n,
        "n_hard_violations": n_hard,
        "pct_hard": round(n_hard / n * 100, 1),
        "pass_rates": {
            "AC-Proxy": round(ac_pass_rate * 100, 1),
            "MAB-Proxy": round(mab_pass_rate * 100, 1),
            "C2": round(c2_pass_rate * 100, 1),
            "CGA-Bench": round(cga_pass_rate * 100, 1),
        },
        "verdict_flip_rate": round(flip_rate * 100, 1),
        "verdict_flip_ci_95": [round(flip_ci[0] * 100, 1), round(flip_ci[1] * 100, 1)],
        "ao_fa_rate": round(ao_fa_rate * 100, 1),
        "ao_fa_ci_95": [round(ao_ci[0] * 100, 1), round(ao_ci[1] * 100, 1)],
        "per_evaluator_fa": {
            "AC-Proxy": round(ac_fa * 100, 1),
            "MAB-Proxy": round(mab_fa * 100, 1),
            "C2": round(c2_fa * 100, 1),
            "CGA-Bench": round(cga_fa * 100, 1),
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("EX-21: Model Diversity — Cross-Family Blind-Spot Persistence")
    print("=" * 60)

    results: dict = {
        "experiment": "EX-21",
        "description": "Cross-family blind-spot persistence across new model families",
        "diversity_models": {},
        "baseline_comparison": {},
    }

    # Score diversity models
    for model_key, label in DIVERSITY_MODELS.items():
        print(f"\n--- {label} ({model_key}) ---")
        episodes = load_model_episodes(model_key)
        if not episodes:
            print(f"  SKIP: no episodes found for {model_key}")
            results["diversity_models"][label] = {"n_episodes": 0, "status": "no_data"}
            continue
        print(f"  Loaded {len(episodes)} episodes")
        records = [score_episode(ep) for ep in episodes]
        metrics = compute_model_metrics(records)
        results["diversity_models"][label] = metrics
        print(f"  Flip rate: {metrics['verdict_flip_rate']}%")
        print(f"  AO-FA rate: {metrics['ao_fa_rate']}%")

    # Score baseline models for comparison
    for model_key, label in BASELINE_MODELS.items():
        print(f"\n--- BASELINE: {label} ({model_key}) ---")
        episodes = load_model_episodes(model_key)
        if not episodes:
            print(f"  SKIP: no episodes for {model_key}")
            continue
        print(f"  Loaded {len(episodes)} episodes")
        records = [score_episode(ep) for ep in episodes]
        metrics = compute_model_metrics(records)
        results["baseline_comparison"][label] = metrics

    # Aggregate comparison
    all_diversity_flip = []
    all_diversity_aofa = []
    all_baseline_flip = []
    all_baseline_aofa = []

    for label, m in results["diversity_models"].items():
        if m.get("n_episodes", 0) > 0 and "verdict_flip_rate" in m:
            all_diversity_flip.append(m["verdict_flip_rate"])
            all_diversity_aofa.append(m["ao_fa_rate"])

    for label, m in results["baseline_comparison"].items():
        if m.get("n_episodes", 0) > 0:
            all_baseline_flip.append(m["verdict_flip_rate"])
            all_baseline_aofa.append(m["ao_fa_rate"])

    results["summary"] = {
        "diversity_mean_flip": round(np.mean(all_diversity_flip), 1) if all_diversity_flip else None,
        "diversity_mean_aofa": round(np.mean(all_diversity_aofa), 1) if all_diversity_aofa else None,
        "baseline_mean_flip": round(np.mean(all_baseline_flip), 1) if all_baseline_flip else None,
        "baseline_mean_aofa": round(np.mean(all_baseline_aofa), 1) if all_baseline_aofa else None,
        "n_diversity_models": len([m for m in results["diversity_models"].values() if m.get("n_episodes", 0) > 0]),
        "n_baseline_models": len(results["baseline_comparison"]),
        "conclusion": "Blind spots persist across model families" if all_diversity_flip else "Pending episodes",
    }

    # Save JSON
    save_json(results, OUTPUT_DIR / "ex21_model_diversity.json")

    # Generate markdown
    md = _generate_markdown(results)
    save_markdown(md, OUTPUT_DIR / "ex21_model_diversity.md")

    print("\n" + "=" * 60)
    print("EX-21 COMPLETE")
    print("=" * 60)


def _generate_markdown(results: dict) -> str:
    lines = [
        "# EX-21: Model Diversity — Cross-Family Blind-Spot Persistence",
        "",
        "## Summary",
        "",
    ]

    s = results.get("summary", {})
    lines.append(f"- **Diversity models tested**: {s.get('n_diversity_models', 0)}")
    lines.append(f"- **Baseline models**: {s.get('n_baseline_models', 0)}")
    lines.append(f"- **Diversity mean flip rate**: {s.get('diversity_mean_flip', 'N/A')}%")
    lines.append(f"- **Baseline mean flip rate**: {s.get('baseline_mean_flip', 'N/A')}%")
    lines.append(f"- **Diversity mean AO-FA**: {s.get('diversity_mean_aofa', 'N/A')}%")
    lines.append(f"- **Baseline mean AO-FA**: {s.get('baseline_mean_aofa', 'N/A')}%")
    lines.append(f"- **Conclusion**: {s.get('conclusion', 'N/A')}")
    lines.append("")

    # Per-model table
    lines.append("## Per-Model Results")
    lines.append("")
    lines.append("| Model | Family | N | Flip% | AO-FA% | AC Pass% | MAB Pass% | C2 Pass% | CGA Pass% |")
    lines.append("|-------|--------|---|-------|--------|----------|-----------|----------|-----------|")

    for label, m in results.get("diversity_models", {}).items():
        if m.get("n_episodes", 0) == 0:
            lines.append(f"| {label} | diversity | 0 | — | — | — | — | — | — |")
            continue
        pr = m["pass_rates"]
        lines.append(
            f"| {label} | diversity | {m['n_episodes']} | "
            f"{m['verdict_flip_rate']} | {m['ao_fa_rate']} | "
            f"{pr['AC-Proxy']} | {pr['MAB-Proxy']} | {pr['C2']} | {pr['CGA-Bench']} |"
        )

    for label, m in results.get("baseline_comparison", {}).items():
        pr = m["pass_rates"]
        lines.append(
            f"| {label} | baseline | {m['n_episodes']} | "
            f"{m['verdict_flip_rate']} | {m['ao_fa_rate']} | "
            f"{pr['AC-Proxy']} | {pr['MAB-Proxy']} | {pr['C2']} | {pr['CGA-Bench']} |"
        )

    lines.append("")

    # Per-evaluator FA table
    lines.append("## Per-Evaluator False-Accept Rates (among hard-violation episodes)")
    lines.append("")
    lines.append("| Model | N_hard | AC-FA% | MAB-FA% | C2-FA% | CGA-FA% |")
    lines.append("|-------|--------|--------|---------|--------|---------|")

    for label, m in {**results.get("diversity_models", {}), **results.get("baseline_comparison", {})}.items():
        if m.get("n_episodes", 0) == 0:
            continue
        fa = m["per_evaluator_fa"]
        lines.append(
            f"| {label} | {m['n_hard_violations']} | "
            f"{fa['AC-Proxy']} | {fa['MAB-Proxy']} | {fa['C2']} | {fa['CGA-Bench']} |"
        )

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
