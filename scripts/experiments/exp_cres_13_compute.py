#!/usr/bin/env python3
"""CRES-13: Compute & Carbon Disclosure.

Extracts computational cost data from 14,826 episode JSONs for the
reproducibility box in the NeurIPS paper. Reports total tokens, A100-hour
estimates, and carbon footprint using standard emission factors.

Compute model:
  - Per-model throughput estimates for vLLM on A100-80GB with TP=2.
    These are estimated lower bounds for batch inference; actual throughput
    may be lower under load or with longer prompts.
  - TP=2 factor: each token inference occupies 2 A100s simultaneously,
    so GPU-hours = token_seconds * 2.
  - A100 TDP: 400 W
  - Carbon intensity: 0.3 kgCO2/kWh (US average grid estimate)
  - kgCO2 = A100_hours * 0.4 kW * 0.3 kgCO2/kWh

Outputs:
  evidence_pack/cres_13/cres_13_results.json
  evidence_pack/cres_13/cres_13_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/exp_cres_13_compute.py
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from scripts.experiments._common import EVIDENCE_DIR, save_json
from scripts.experiments._episode_cache import (
    COMPLETE_MODELS,
    load_cached_episodes,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUTPUT_DIR = EVIDENCE_DIR / "cres_13"

# Compute constants
#
# Per-model throughput estimates (seconds per token) for vLLM on A100-80GB
# with TP=2 deployment. These are estimated lower bounds for batch inference;
# real throughput may be lower under load or with longer context windows.
SECONDS_PER_TOKEN_BY_MODEL: dict[str, float] = {
    "qwen4b": 0.00005,  # ~20,000 tok/s — small model, single GPU effective
    "qwen27b": 0.0002,  # ~5,000 tok/s
    "qwen35b": 0.0003,  # ~3,333 tok/s
    "gemma31b": 0.0003,  # ~3,333 tok/s
    "nemotron30b": 0.0003,  # ~3,333 tok/s
    "oss120b": 0.001,  # ~1,000 tok/s — 120B model, TP=2
    "qwen397b": 0.002,  # ~500 tok/s — 397B model, TP=2
}
SECONDS_PER_TOKEN_DEFAULT: float = 0.0005  # fallback for unknown models

# TP=2 means each token inference occupies 2 A100s simultaneously.
TP_FACTOR: int = 2

A100_POWER_KW: float = 0.400  # A100 TDP in kW
CARBON_INTENSITY_KG_PER_KWH: float = 0.3  # US average grid carbon intensity
SECONDS_PER_HOUR: float = 3600.0

MODEL_LABELS: dict[str, str] = {
    "oss120b": "OSS-120B",
    "qwen27b": "Qwen3.5-27B",
    "qwen35b": "Qwen3.5-35B",
    "qwen4b": "Qwen3-4B",
    "qwen397b": "Qwen3.5-397B",
    "gemma31b": "Gemma4-31B",
    "nemotron30b": "Nemotron-30B",
}


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------


def extract_episode_tokens(ep: dict[str, Any]) -> int:
    """Extract total token count from an episode dict.

    Tries multiple field locations:
      1. ep["total_tokens"]
      2. ep["token_usage"]["total"]
      3. ep["token_usage"]["total_tokens"]
      4. sum of ep["token_usage"]["prompt_tokens"] + ["completion_tokens"]
      5. 0 as fallback
    """
    # Direct field
    direct = ep.get("total_tokens")
    if isinstance(direct, (int, float)) and direct > 0:
        return int(direct)

    # Nested token_usage dict
    usage = ep.get("token_usage")
    if isinstance(usage, dict):
        total = usage.get("total") or usage.get("total_tokens")
        if isinstance(total, (int, float)) and total > 0:
            return int(total)
        # Sum prompt + completion
        prompt = usage.get("prompt_tokens", 0) or 0
        completion = usage.get("completion_tokens", 0) or 0
        if prompt + completion > 0:
            return int(prompt + completion)

    return 0


def extract_episode_actions(ep: dict[str, Any]) -> int:
    """Return the number of actions taken in an episode."""
    actions = ep.get("actions", [])
    return len(actions) if isinstance(actions, list) else 0


def extract_episode_duration(ep: dict[str, Any]) -> float:
    """Return wall-clock duration in seconds, or estimate from timestamps.

    Falls back to estimating from action timestamps if duration_seconds
    is not present.
    """
    # Direct field
    direct = ep.get("duration_seconds")
    if isinstance(direct, (int, float)) and direct > 0:
        return float(direct)

    # Estimate from action timestamps (max timestamp_minutes * 60)
    actions = ep.get("actions", [])
    if isinstance(actions, list) and actions:
        max_ts = 0.0
        for a in actions:
            if isinstance(a, dict):
                ts = a.get("timestamp_minutes", 0) or 0
                if isinstance(ts, (int, float)) and ts > max_ts:
                    max_ts = float(ts)
        if max_ts > 0:
            return max_ts * 60.0

    return 0.0


# ---------------------------------------------------------------------------
# Carbon accounting
# ---------------------------------------------------------------------------


def tokens_to_a100_hours(total_tokens: int, model: str = "") -> float:
    """Convert total inference tokens to A100-hours.

    Uses per-model throughput from SECONDS_PER_TOKEN_BY_MODEL and multiplies
    by TP_FACTOR=2 because each inference occupies 2 A100s simultaneously.
    """
    seconds_per_token = SECONDS_PER_TOKEN_BY_MODEL.get(model, SECONDS_PER_TOKEN_DEFAULT)
    a100_seconds = total_tokens * seconds_per_token * TP_FACTOR
    return a100_seconds / SECONDS_PER_HOUR


def a100_hours_to_kg_co2(a100_hours: float) -> float:
    """Convert A100-hours to kgCO2 using standard emission factors."""
    kwh = a100_hours * A100_POWER_KW
    return kwh * CARBON_INTENSITY_KG_PER_KWH


# ---------------------------------------------------------------------------
# Per-episode aggregation
# ---------------------------------------------------------------------------


def aggregate_episode_stats(
    episodes: list[dict[str, Any]],
    model: str = "",
) -> dict[str, Any]:
    """Compute token and compute statistics for a list of episodes.

    Args:
        episodes: Raw episode dicts (with _model tag).
        model: Model name used to look up per-model throughput. Pass empty
            string for a mixed-model aggregate (uses default rate).

    Returns:
        Aggregate stats dict.
    """
    total_tokens = 0
    total_actions = 0
    total_duration_sec = 0.0
    per_episode_tokens: list[int] = []
    per_episode_actions: list[int] = []
    zero_token_count = 0

    for ep in episodes:
        tokens = extract_episode_tokens(ep)
        actions = extract_episode_actions(ep)
        duration = extract_episode_duration(ep)

        total_tokens += tokens
        total_actions += actions
        total_duration_sec += duration
        per_episode_tokens.append(tokens)
        per_episode_actions.append(actions)
        if tokens == 0:
            zero_token_count += 1

    n = len(episodes)
    tokens_arr = np.array(per_episode_tokens, dtype=float)
    actions_arr = np.array(per_episode_actions, dtype=float)

    mean_tokens = float(np.mean(tokens_arr)) if n > 0 else 0.0
    median_tokens = float(np.median(tokens_arr)) if n > 0 else 0.0
    p95_tokens = float(np.percentile(tokens_arr, 95)) if n > 0 else 0.0
    mean_actions = float(np.mean(actions_arr)) if n > 0 else 0.0

    seconds_per_token = SECONDS_PER_TOKEN_BY_MODEL.get(model, SECONDS_PER_TOKEN_DEFAULT)
    a100_hours = tokens_to_a100_hours(total_tokens, model)
    kg_co2 = a100_hours_to_kg_co2(a100_hours)

    return {
        "n_episodes": n,
        "total_tokens": total_tokens,
        "mean_tokens_per_episode": round(mean_tokens, 1),
        "median_tokens_per_episode": round(median_tokens, 1),
        "p95_tokens_per_episode": round(p95_tokens, 1),
        "total_actions": total_actions,
        "mean_actions_per_episode": round(mean_actions, 2),
        "total_duration_seconds": round(total_duration_sec, 1),
        "a100_hours": round(a100_hours, 4),
        "kg_co2": round(kg_co2, 4),
        "zero_token_episodes": zero_token_count,
        "zero_token_pct": round(zero_token_count / n * 100, 1) if n > 0 else 0.0,
        "compute_assumptions": {
            "seconds_per_token": seconds_per_token,
            "tp_factor": TP_FACTOR,
            "a100_power_kw": A100_POWER_KW,
            "carbon_intensity_kg_per_kwh": CARBON_INTENSITY_KG_PER_KWH,
        },
    }


# ---------------------------------------------------------------------------
# LaTeX macros
# ---------------------------------------------------------------------------


def write_macros(results: dict[str, Any], output_dir: Path) -> None:
    """Write LaTeX macros file for CRES-13 results."""
    total = results["aggregate"]
    total_tokens = total["total_tokens"]
    a100_hours = total["a100_hours"]
    kg_co2 = total["kg_co2"]
    median_tokens = total["median_tokens_per_episode"]

    # Format large numbers with commas for readability
    def fmt_int(n: int) -> str:
        return f"{n:,}"

    lines = [
        "% CRES-13: Compute & Carbon Disclosure Macros",
        "% Auto-generated by exp_cres_13_compute.py",
        "",
        f"\\newcommand{{\\cresThirteenTotalTokens}}{{{fmt_int(total_tokens)}}}",
        f"\\newcommand{{\\cresThirteenA100Hours}}{{{a100_hours:.2f}}}",
        f"\\newcommand{{\\cresThirteenCO2Kg}}{{{kg_co2:.2f}}}",
        f"\\newcommand{{\\cresThirteenMedianTokensPerEp}}{{{median_tokens:.0f}}}",
        "",
    ]

    macro_path = output_dir / "cres_13_macros.tex"
    macro_path.parent.mkdir(parents=True, exist_ok=True)
    macro_path.write_text("\n".join(lines))
    print(f"  Saved: {macro_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("CRES-13: Compute & Carbon Disclosure")
    print("=" * 60)

    # Load all episodes (raw, not scored — we need token fields)
    print("\nLoading episodes...")
    episodes = load_cached_episodes()
    print(f"  Loaded {len(episodes)} episodes")

    # Per-model breakdown
    print("\nAggregating by model...")
    by_model: dict[str, list[dict[str, Any]]] = {}
    for ep in episodes:
        m = ep.get("_model", "")
        if m in COMPLETE_MODELS:
            by_model.setdefault(m, []).append(ep)

    per_model: dict[str, dict[str, Any]] = {}
    for model in sorted(by_model.keys()):
        model_eps = by_model[model]
        stats = aggregate_episode_stats(model_eps, model=model)
        per_model[model] = stats
        label = MODEL_LABELS.get(model, model)
        print(
            f"  {label}: {stats['n_episodes']} eps, "
            f"{stats['total_tokens']:,} tokens, "
            f"{stats['a100_hours']:.4f} A100-hrs, "
            f"{stats['kg_co2']:.4f} kgCO2, "
            f"zero-token: {stats['zero_token_pct']:.1f}%"
        )

    # Global aggregate
    print("\nComputing global aggregate...")
    global_stats = aggregate_episode_stats(episodes)

    print(f"\n  Total episodes:          {global_stats['n_episodes']:,}")
    print(f"  Total tokens:            {global_stats['total_tokens']:,}")
    print(f"  Mean tokens/episode:     {global_stats['mean_tokens_per_episode']:,.1f}")
    print(f"  Median tokens/episode:   {global_stats['median_tokens_per_episode']:,.1f}")
    print(f"  P95 tokens/episode:      {global_stats['p95_tokens_per_episode']:,.1f}")
    print(f"  Total A100-hours:        {global_stats['a100_hours']:.4f}")
    print(f"  Total CO2 (kg):          {global_stats['kg_co2']:.4f}")
    print(f"  Zero-token episodes:     {global_stats['zero_token_episodes']} ({global_stats['zero_token_pct']:.1f}%)")

    if global_stats["zero_token_pct"] > 50:
        print(
            "\n  NOTE: >50% of episodes have zero tokens. "
            "Token data may not be stored in episode JSONs. "
            "Compute estimates are lower bounds."
        )

    # Build output
    results: dict[str, Any] = {
        "experiment": "CRES-13",
        "description": "Compute and Carbon Disclosure for 14,826-episode benchmark",
        "aggregate": global_stats,
        "per_model": per_model,
        "models_included": sorted(by_model.keys()),
        "model_labels": MODEL_LABELS,
        "notes": [
            "Token counts extracted from episode JSONs (total_tokens or token_usage fields).",
            "Episodes with zero tokens may lack token logging; compute estimates are lower bounds.",
            "A100 compute model: per-model throughput estimates (see seconds_per_token_by_model); "
            f"default fallback {SECONDS_PER_TOKEN_DEFAULT}s/tok for unknown models.",
            f"TP=2 factor applied: each token inference occupies {TP_FACTOR} A100s simultaneously.",
            f"Carbon model: A100 {A100_POWER_KW * 1000:.0f}W TDP, "
            f"{CARBON_INTENSITY_KG_PER_KWH} kgCO2/kWh (US average grid).",
        ],
        "seconds_per_token_by_model": SECONDS_PER_TOKEN_BY_MODEL,
    }

    # Save outputs
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    save_json(results, output_dir / "cres_13_results.json")
    write_macros(results, output_dir)

    print("\n" + "=" * 60)
    print("CRES-13 COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
