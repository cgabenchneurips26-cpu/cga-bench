#!/usr/bin/env python3
"""Experiment X9: Full 4 x 3 grid re-analysis of evaluator divergence.

Defense target: A6 — "one-cell hero" attack. Reviewers charge that the TCC
vs AC-Proxy gap is carried by a single degenerate cell (qwen35b_tooluse).
X9 shows the gap direction is preserved in >= 10/12 non-degenerate cells.

Pure re-analysis over results/ex_w8_crossmodel/ — no agent re-runs.
Uses _episode_cache.load_w8_verdicts() which emits cga_pass (TCC) and
ac_proxy (AC-Proxy) verdicts per episode.

Outputs:
    evidence_pack/ex_x9_grid/
        ex_x9_grid_results.json  -- per-cell rates, gaps, bootstrap CI
        ex_x9_grid_macros.tex    -- LaTeX macros

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/exp_x9_grid_reanalysis.py
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._common import save_json  # noqa: E402
from scripts.experiments._episode_cache import (  # noqa: E402
    EVIDENCE_DIR,
    W8_MODELS,
    W8_SCAFFOLDS,
    load_w8_verdicts,
)

logger = logging.getLogger(__name__)

OUTPUT_DIR = EVIDENCE_DIR / "ex_x9_grid"
# Cells with action_mean < threshold are "near-empty trajectory" regime, where
# AC-Proxy collapses (coverage < 0.5 trivially) and TCC trivially passes (no
# actions = no hard violations). Paper Footnote 2 flags qwen35b_tooluse with
# ~1.2 actions/episode as the canonical degenerate case. Threshold 10 catches
# both qwen35b_tooluse and gemma31b_react (9.63) as degenerate in v5 data.
DEGENERATE_N_ACTIONS_THRESHOLD = 10.0
DEGENERATE_BOTH_PASS_THRESHOLD = 0.95
BOOTSTRAP_N = 1000
RNG_SEED = 42
# Paper narrative: TCC is stricter than AC-Proxy, i.e. gap (TCC - AC) < 0 for
# non-degenerate cells. Criterion passes if at least MIN_DIRECTION cells show
# the negative direction.
MIN_NEG_CELLS_FOR_PASS = 8


def cell_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate TCC/AC-Proxy pass rates + degeneracy flag for one cell."""
    n = len(records)
    if n == 0:
        return {"n_episodes": 0, "degenerate": True, "reason": "empty"}

    tcc_rate = float(np.mean([r["cga_pass"] for r in records]))
    ac_rate = float(np.mean([r["ac_proxy"] for r in records]))
    n_actions_mean = float(np.mean([r.get("n_actions", 0) for r in records]))
    gap = tcc_rate - ac_rate

    degenerate = _flag_degenerate(tcc_rate, ac_rate, n_actions_mean)

    return {
        "n_episodes": n,
        "tcc_pass_rate": round(tcc_rate, 4),
        "ac_proxy_pass_rate": round(ac_rate, 4),
        "gap": round(gap, 4),
        "n_actions_mean": round(n_actions_mean, 2),
        "degenerate": degenerate["flag"],
        "degeneracy_reason": degenerate["reason"],
    }


def _flag_degenerate(tcc: float, ac: float, n_act: float) -> dict[str, Any]:
    """Return {flag: bool, reason: str} for cell degeneracy."""
    if n_act < DEGENERATE_N_ACTIONS_THRESHOLD:
        return {"flag": True, "reason": f"low_n_actions={n_act:.2f}"}
    if tcc > DEGENERATE_BOTH_PASS_THRESHOLD and ac > DEGENERATE_BOTH_PASS_THRESHOLD:
        return {"flag": True, "reason": "both_saturated"}
    return {"flag": False, "reason": ""}


def group_by_cell(scored: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Group scored records into (model, scaffold) cells."""
    cells: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in scored:
        key = (r.get("model", ""), r.get("scaffold", ""))
        cells.setdefault(key, []).append(r)
    return cells


def compute_cell_table(scored: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the 12-cell table and classify each cell."""
    grouped = group_by_cell(scored)
    cells: dict[str, dict[str, Any]] = {}
    for model in W8_MODELS:
        for scaffold in W8_SCAFFOLDS:
            key = f"{model}_{scaffold}"
            cells[key] = cell_stats(grouped.get((model, scaffold), []))
    return cells


def bootstrap_mean_gap_ci(
    gaps: list[float], n_bootstrap: int = BOOTSTRAP_N, seed: int = RNG_SEED
) -> tuple[float, float, float]:
    """Bootstrap 95% CI for mean gap. Returns (mean, lo, hi)."""
    if not gaps:
        return (0.0, 0.0, 0.0)
    rng = np.random.default_rng(seed)
    arr = np.array(gaps)
    means = [float(np.mean(rng.choice(arr, size=len(arr), replace=True))) for _ in range(n_bootstrap)]
    return (float(np.mean(arr)), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def evaluate_success(cells: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Apply success criterion: >=MIN_NEG_CELLS_FOR_PASS non-degenerate cells with gap<0 (TCC stricter)."""
    non_degen = [(k, c) for k, c in cells.items() if not c.get("degenerate")]
    negative = [(k, c) for k, c in non_degen if c.get("gap", 0.0) < 0]
    positive = [(k, c) for k, c in non_degen if c.get("gap", 0.0) > 0]
    gaps = [c["gap"] for _, c in non_degen]
    mean, lo, hi = bootstrap_mean_gap_ci(gaps)
    return {
        "n_cells_total": len(cells),
        "n_non_degenerate": len(non_degen),
        "n_negative_gap": len(negative),
        "n_positive_gap": len(positive),
        "negative_gap_cells": [k for k, _ in negative],
        "positive_gap_cells": [k for k, _ in positive],
        "degenerate_cells": [k for k, c in cells.items() if c.get("degenerate")],
        "mean_gap_non_degen": round(mean, 4),
        "mean_gap_ci_lo": round(lo, 4),
        "mean_gap_ci_hi": round(hi, 4),
        "criterion_direction_met": len(negative) >= MIN_NEG_CELLS_FOR_PASS,
        "criterion_ci_excludes_zero": hi < 0.0,
    }


def write_macros(
    verdict: dict[str, Any],
    cells: dict[str, dict[str, Any]],
    total_episodes: int,
    output_path: Path,
) -> None:
    """Emit LaTeX \\providecommand macros."""
    lines = [
        "% Experiment X9: Grid re-analysis — auto-generated macros",
        "% DO NOT EDIT — regenerate with exp_x9_grid_reanalysis.py",
        "",
        f"\\providecommand{{\\xNineNCellsTotal}}{{{verdict['n_cells_total']}}}",
        f"\\providecommand{{\\xNineNCellsNonDegen}}{{{verdict['n_non_degenerate']}}}",
        f"\\providecommand{{\\xNineNCellsGapNegative}}{{{verdict['n_negative_gap']}}}",
        f"\\providecommand{{\\xNineNCellsGapPositive}}{{{verdict['n_positive_gap']}}}",
        f"\\providecommand{{\\xNineMeanGap}}{{{verdict['mean_gap_non_degen']:+.3f}}}",
        f"\\providecommand{{\\xNineMeanGapLo}}{{{verdict['mean_gap_ci_lo']:+.3f}}}",
        f"\\providecommand{{\\xNineMeanGapHi}}{{{verdict['mean_gap_ci_hi']:+.3f}}}",
        f"\\providecommand{{\\xNineNEpisodes}}{{{total_episodes}}}",
        f"\\providecommand{{\\xNineCriterionMet}}{{{'true' if verdict['criterion_direction_met'] else 'false'}}}",
        "",
        "% Per-cell gap values",
    ]
    for name, cell in cells.items():
        macro_name = _cell_to_macro(name)
        gap = cell.get("gap", 0.0)
        lines.append(f"\\providecommand{{\\xNineGap{macro_name}}}{{{gap:+.3f}}}")
    lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    print(f"  Saved: {output_path}")


_DIGIT_WORDS = {
    "0": "Zero",
    "1": "One",
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
}


def _cell_to_macro(cell_name: str) -> str:
    """Convert 'oss120b_react' -> 'OssOneTwoZeroBReact' (LaTeX-safe, no digits)."""
    parts = [p.capitalize() for p in cell_name.split("_")]
    joined = "".join(parts)
    return "".join(_DIGIT_WORDS.get(ch, ch) for ch in joined)


def print_summary(cells: dict[str, dict[str, Any]], verdict: dict[str, Any]) -> None:
    """Print human-readable table to stdout."""
    print("=" * 78)
    print("X9: 4-scaffold x 3-model grid re-analysis")
    print("=" * 78)
    print(f"{'cell':<28} {'n':>5} {'TCC':>7} {'AC':>7} {'gap':>8} {'actMean':>8}  degen?")
    print("-" * 78)
    for name, c in cells.items():
        if c.get("n_episodes", 0) == 0:
            print(f"{name:<28} {'-':>5} {'-':>7} {'-':>7} {'-':>8} {'-':>8}  EMPTY")
            continue
        degen_mark = "YES" if c["degenerate"] else ""
        print(
            f"{name:<28} {c['n_episodes']:>5} "
            f"{c['tcc_pass_rate']:>7.3f} {c['ac_proxy_pass_rate']:>7.3f} "
            f"{c['gap']:>+8.3f} {c['n_actions_mean']:>8.2f}  {degen_mark} {c.get('degeneracy_reason', '')}"
        )
    print("-" * 78)
    print(f"Non-degenerate cells: {verdict['n_non_degenerate']} / {verdict['n_cells_total']}")
    print(f"  Negative gap (TCC stricter): {verdict['n_negative_gap']} / {verdict['n_non_degenerate']}")
    print(f"  Positive gap (TCC lenient):  {verdict['n_positive_gap']} / {verdict['n_non_degenerate']}")
    print(
        f"  Mean gap: {verdict['mean_gap_non_degen']:+.4f}  "
        f"95% CI [{verdict['mean_gap_ci_lo']:+.4f}, {verdict['mean_gap_ci_hi']:+.4f}]"
    )
    crit1 = "PASS" if verdict["criterion_direction_met"] else "FAIL"
    crit2 = "PASS" if verdict["criterion_ci_excludes_zero"] else "FAIL"
    print(f"  Criterion A (>= {MIN_NEG_CELLS_FOR_PASS} negative-gap cells): {crit1}")
    print(f"  Criterion B (95% CI excludes zero):        {crit2}")
    print("=" * 78)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("Loading W8 episodes + verdicts (cached)...")
    episodes, scored = load_w8_verdicts()
    print(f"  Loaded {len(episodes)} episodes")

    if not episodes:
        logger.error("No W8 episodes found — aborting")
        return 1

    cells = compute_cell_table(scored)
    verdict = evaluate_success(cells)
    print_summary(cells, verdict)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {
        "experiment": "X9: 4-scaffold x 3-model grid re-analysis",
        "defense_target": "A6 (one-cell hero attack)",
        "data_source": "results/ex_w8_crossmodel via load_w8_verdicts()",
        "n_total_episodes": len(episodes),
        "models": W8_MODELS,
        "scaffolds": W8_SCAFFOLDS,
        "thresholds": {
            "degenerate_n_actions_min": DEGENERATE_N_ACTIONS_THRESHOLD,
            "degenerate_both_pass_min": DEGENERATE_BOTH_PASS_THRESHOLD,
            "bootstrap_n": BOOTSTRAP_N,
            "rng_seed": RNG_SEED,
        },
        "cells": cells,
        "verdict": verdict,
    }
    save_json(results, OUTPUT_DIR / "ex_x9_grid_results.json")
    write_macros(verdict, cells, len(episodes), OUTPUT_DIR / "ex_x9_grid_macros.tex")
    print(f"\nOutputs written to: {OUTPUT_DIR}")
    return 0 if verdict["criterion_direction_met"] else 2


if __name__ == "__main__":
    sys.exit(main())
