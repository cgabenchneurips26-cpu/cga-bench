#!/usr/bin/env python3
"""EX-W8: Cross-Model Scaffold Replication — Aggregation

Aggregates results from the 3 models × 3 scaffolds = 9 cell W8 experiment.
Each cell targets 706 scenarios × 3 runs = 2,118 episodes.

Metrics per cell:
  - CGA compliance_score: mean ± SD
  - Per-evaluator pass rates: AC-Proxy, MAB-Proxy, C2, CGA-Bench
  - Verdict flip rate (≥1 evaluator pair disagrees)
  - FA rate (all-oblivious false accept)

Cross-cell metrics:
  - Cross-scaffold Jaccard: per-model, how similar are action sets across scaffolds
  - Cross-model Jaccard: per-scaffold, how similar are action sets across models
  - Defense ratio: verdict flip persistence across scaffolds

Outputs:
  evidence_pack/ex_w8_crossmodel/
    matrix.json           -- full results matrix
    summary.md            -- markdown report
    macros.tex            -- LaTeX macros for paper
    w8_table.tex          -- LaTeX booktabs table

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/aggregate_ex_w8_crossmodel.py
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

RESULTS_DIR = ROOT / "results" / "ex_w8_crossmodel"
OUTPUT_DIR = EVIDENCE_DIR / "ex_w8_crossmodel"

MODELS: dict[str, str] = {
    "qwen35b": "Qwen3.5-35B",
    "oss120b": "OSS-120B",
    "gemma31b": "Gemma4-31B",
}

SCAFFOLDS: list[str] = ["react", "direct", "checklist"]

# Map (model, scaffold) -> model_dir_name in results/
CELL_KEYS: dict[tuple[str, str], str] = {}
for model in MODELS:
    for scaffold in SCAFFOLDS:
        if scaffold == "react" and model in ("qwen35b", "oss120b"):
            # react variants use dedicated key
            CELL_KEYS[(model, scaffold)] = f"{model}_react"
        elif scaffold == "react" and model == "gemma31b":
            CELL_KEYS[(model, scaffold)] = "gemma31b_react"
        else:
            CELL_KEYS[(model, scaffold)] = f"{model}_{scaffold}"

AC_COVERAGE_THRESHOLD = 0.5
MAB_F1_THRESHOLD = 0.5
C2_THRESHOLD = 0.7
HARD_VIOL_TYPES: frozenset[str] = frozenset({"commission", "timing", "sequence"})


# ---------------------------------------------------------------------------
# Episode loading and scoring (mirrors exp_e21 / verdict_matrix_v5)
# ---------------------------------------------------------------------------


def _normalize_action(action_id: str) -> str:
    return action_id.strip().lower().replace("-", "_").replace(" ", "_")


def _classify_violation_type(raw_type: str) -> str:
    lower = raw_type.lower().strip()
    for canonical in ("omission", "commission", "timing", "sequence", "deviation"):
        if canonical in lower:
            return canonical
    return "unknown"


def load_cell_episodes(cell_dir_name: str) -> list[dict]:
    """Load all episode JSONs for a W8 cell, with dedup."""
    model_dir = RESULTS_DIR / cell_dir_name
    if not model_dir.exists():
        print(f"  WARNING: Cell dir not found: {model_dir}")
        return []

    episodes: list[dict] = []
    seen: set[str] = set()

    for f in sorted(model_dir.glob("*.json")):
        if f.name.startswith(("checkpoint", ".claim", "model_summary")):
            continue
        try:
            ep = json.loads(f.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        sid = ep.get("scenario_id", "")
        if not sid:
            continue
        run_idx = ep.get("run_index", 0)
        dedup_key = f"{sid}_{cell_dir_name}_r{run_idx}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        ep["_cell"] = cell_dir_name
        episodes.append(ep)

    return episodes


def score_episode(ep: dict) -> dict:
    """Compute evaluator verdicts for one episode."""
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

    coverage = len(performed & expected) / len(expected) if expected else 1.0
    tp = len(performed & expected)
    precision = tp / len(performed) if performed else 0.0
    recall = tp / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    c2_score = ep.get("compliance_score", 0.0) or 0.0

    has_hard = False
    for v in ep.get("violation_events", []):
        raw_type = str(v.get("violation_type", v.get("type", "")))
        if _classify_violation_type(raw_type) in HARD_VIOL_TYPES:
            has_hard = True
            break

    ac_proxy = coverage >= AC_COVERAGE_THRESHOLD
    mab_proxy = f1 >= MAB_F1_THRESHOLD
    c2_pass = c2_score >= C2_THRESHOLD
    cga_pass = not has_hard

    return {
        "scenario_id": ep.get("scenario_id", ""),
        "run_index": ep.get("run_index", 0),
        "performed": performed,
        "expected": expected,
        "coverage": round(coverage, 4),
        "f1": round(f1, 4),
        "c2_score": round(c2_score, 4),
        "ac_proxy": ac_proxy,
        "mab_proxy": mab_proxy,
        "c2_pass": c2_pass,
        "cga_pass": cga_pass,
        "v4_hard": has_hard,
    }


# ---------------------------------------------------------------------------
# Cross-cell Jaccard
# ---------------------------------------------------------------------------


def _scenario_action_sets(scored: list[dict]) -> dict[str, set[str]]:
    """Map scenario_id -> union of performed actions across runs."""
    result: dict[str, set[str]] = {}
    for s in scored:
        sid = s["scenario_id"]
        result.setdefault(sid, set()).update(s["performed"])
    return result


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


def compute_cross_jaccard(cell_scored: dict[str, list[dict]], group_keys: list[str]) -> float:
    """Average pairwise Jaccard across cells for shared scenarios."""
    action_maps = {k: _scenario_action_sets(cell_scored[k]) for k in group_keys}

    # Find shared scenarios
    shared = set.intersection(*(set(m.keys()) for m in action_maps.values()))
    if not shared:
        return 0.0

    jaccards: list[float] = []
    for k1, k2 in combinations(group_keys, 2):
        for sid in shared:
            jaccards.append(jaccard_similarity(action_maps[k1][sid], action_maps[k2][sid]))
    return float(np.mean(jaccards)) if jaccards else 0.0


# ---------------------------------------------------------------------------
# Main aggregation
# ---------------------------------------------------------------------------


def main() -> None:
    print("EX-W8: Cross-Model Scaffold Replication — Aggregation")
    print(f"Results dir: {RESULTS_DIR}")
    print()

    # Load and score all cells
    cell_scored: dict[str, list[dict]] = {}
    cell_raw: dict[str, list[dict]] = {}

    for (model, scaffold), cell_key in CELL_KEYS.items():
        eps = load_cell_episodes(cell_key)
        print(f"  {cell_key}: {len(eps)} episodes")
        scored = [score_episode(ep) for ep in eps]
        cell_scored[cell_key] = scored
        cell_raw[cell_key] = eps

    # --- Per-cell metrics ---
    matrix: dict[str, dict] = {}
    for (model, scaffold), cell_key in CELL_KEYS.items():
        scored = cell_scored.get(cell_key, [])
        n = len(scored)
        if n == 0:
            matrix[cell_key] = {
                "model": model,
                "scaffold": scaffold,
                "n_episodes": 0,
                "status": "no_data",
            }
            continue

        c2_scores = np.array([s["c2_score"] for s in scored])
        pass_rates = {
            "ac_proxy": np.mean([s["ac_proxy"] for s in scored]),
            "mab_proxy": np.mean([s["mab_proxy"] for s in scored]),
            "c2_pass": np.mean([s["c2_pass"] for s in scored]),
            "cga_pass": np.mean([s["cga_pass"] for s in scored]),
        }

        # Verdict flip: ≥1 evaluator pair disagrees
        verdicts_list = [(s["ac_proxy"], s["mab_proxy"], s["c2_pass"], s["cga_pass"]) for s in scored]
        flip_count = sum(1 for v in verdicts_list if len(set(v)) > 1)

        # All-oblivious FA: all non-CGA pass + hard violation
        fa_count = sum(1 for s in scored if s["ac_proxy"] and s["mab_proxy"] and s["c2_pass"] and s["v4_hard"])

        cga_mean = float(np.mean(c2_scores))
        cga_sd = float(np.std(c2_scores, ddof=1)) if n > 1 else 0.0
        ci_lo, ci_hi = bootstrap_ci(c2_scores, np.mean) if n > 10 else (cga_mean, cga_mean)

        matrix[cell_key] = {
            "model": model,
            "scaffold": scaffold,
            "n_episodes": n,
            "cga_mean": round(cga_mean, 4),
            "cga_sd": round(cga_sd, 4),
            "cga_ci_lo": round(ci_lo, 4),
            "cga_ci_hi": round(ci_hi, 4),
            "pass_rates": {k: round(v, 4) for k, v in pass_rates.items()},
            "verdict_flip_rate": round(flip_count / n, 4),
            "fa_rate": round(fa_count / n, 4),
        }

    # --- Cross-scaffold Jaccard (per model) ---
    cross_scaffold: dict[str, float] = {}
    for model in MODELS:
        keys = [CELL_KEYS[(model, s)] for s in SCAFFOLDS if CELL_KEYS[(model, s)] in cell_scored]
        if len(keys) >= 2:
            cross_scaffold[model] = round(compute_cross_jaccard(cell_scored, keys), 4)

    # --- Cross-model Jaccard (per scaffold) ---
    cross_model: dict[str, float] = {}
    for scaffold in SCAFFOLDS:
        keys = [CELL_KEYS[(m, scaffold)] for m in MODELS if CELL_KEYS[(m, scaffold)] in cell_scored]
        if len(keys) >= 2:
            cross_model[scaffold] = round(compute_cross_jaccard(cell_scored, keys), 4)

    # --- Defense ratio: scaffold-invariance of verdict flips ---
    defense: dict[str, dict] = {}
    for model in MODELS:
        flip_rates = []
        for scaffold in SCAFFOLDS:
            cell_key = CELL_KEYS[(model, scaffold)]
            if cell_key in matrix and matrix[cell_key].get("n_episodes", 0) > 0:
                flip_rates.append(matrix[cell_key]["verdict_flip_rate"])
        if len(flip_rates) >= 2:
            defense[model] = {
                "flip_rates": flip_rates,
                "flip_mean": round(float(np.mean(flip_rates)), 4),
                "flip_range": round(float(max(flip_rates) - min(flip_rates)), 4),
            }

    # --- Save results ---
    results = {
        "experiment": "EX-W8",
        "description": "Cross-Model Scaffold Replication (3×3 matrix)",
        "matrix": matrix,
        "cross_scaffold_jaccard": cross_scaffold,
        "cross_model_jaccard": cross_model,
        "defense_ratio": defense,
    }
    save_json(results, OUTPUT_DIR / "matrix.json")

    # --- Generate LaTeX table ---
    latex_lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{W8: Cross-model scaffold replication. CGA compliance mean $\pm$ SD "
        r"and verdict-flip rate across 3 scaffolds $\times$ 3 models.}",
        r"\label{tab:w8_crossmodel}",
        r"\begin{tabular}{ll rrr r}",
        r"\toprule",
        r"Model & Scaffold & $n$ & CGA $\mu\pm\sigma$ & Flip\% & FA\% \\",
        r"\midrule",
    ]
    for model, label in MODELS.items():
        for i, scaffold in enumerate(SCAFFOLDS):
            cell_key = CELL_KEYS[(model, scaffold)]
            m = matrix.get(cell_key, {})
            n = m.get("n_episodes", 0)
            if n == 0:
                latex_lines.append(f"  {label if i == 0 else ''} & {scaffold} & 0 & --- & --- & --- \\\\")
                continue
            cga = f"{m['cga_mean']:.3f}$\\pm${m['cga_sd']:.3f}"
            flip = f"{m['verdict_flip_rate'] * 100:.1f}"
            fa = f"{m['fa_rate'] * 100:.1f}"
            model_col = label if i == 0 else ""
            latex_lines.append(f"  {model_col} & {scaffold} & {n} & {cga} & {flip} & {fa} \\\\")
        latex_lines.append(r"\midrule")

    # Cross-scaffold Jaccard row
    latex_lines[-1] = r"\midrule"
    latex_lines.append(r"\multicolumn{6}{l}{\textit{Cross-scaffold Jaccard (per model):}} \\")
    for model, label in MODELS.items():
        j = cross_scaffold.get(model, 0.0)
        latex_lines.append(f"  {label} & & \\multicolumn{{4}}{{l}}{{{j:.3f}}} \\\\")

    latex_lines.append(r"\multicolumn{6}{l}{\textit{Cross-model Jaccard (per scaffold):}} \\")
    for scaffold in SCAFFOLDS:
        j = cross_model.get(scaffold, 0.0)
        latex_lines.append(f"  & {scaffold} & \\multicolumn{{4}}{{l}}{{{j:.3f}}} \\\\")

    latex_lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])

    table_tex = "\n".join(latex_lines)
    (OUTPUT_DIR / "w8_table.tex").parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "w8_table.tex", "w") as f:
        f.write(table_tex)
    print(f"  Saved: {OUTPUT_DIR / 'w8_table.tex'}")

    # --- Generate LaTeX macros ---
    macros: list[str] = []
    total_episodes = sum(m.get("n_episodes", 0) for m in matrix.values())
    macros.append(f"\\newcommand{{\\WEightTotalEpisodes}}{{{total_episodes}}}")
    macros.append(f"\\newcommand{{\\WEightNCells}}{{{len(CELL_KEYS)}}}")

    for (model, scaffold), cell_key in CELL_KEYS.items():
        m = matrix.get(cell_key, {})
        n = m.get("n_episodes", 0)
        prefix = f"WEight{model.replace('_', '').title()}{scaffold.title()}"
        macros.append(f"\\newcommand{{\\{prefix}N}}{{{n}}}")
        if n > 0:
            macros.append(f"\\newcommand{{\\{prefix}CGA}}{{{m['cga_mean']:.3f}}}")
            macros.append(f"\\newcommand{{\\{prefix}SD}}{{{m['cga_sd']:.3f}}}")
            macros.append(f"\\newcommand{{\\{prefix}Flip}}{{{m['verdict_flip_rate'] * 100:.1f}\\%}}")
            macros.append(f"\\newcommand{{\\{prefix}FA}}{{{m['fa_rate'] * 100:.1f}\\%}}")

    for model in MODELS:
        j = cross_scaffold.get(model, 0.0)
        mkey = model.replace("_", "").title()
        macros.append(f"\\newcommand{{\\WEight{mkey}ScaffoldJaccard}}{{{j:.3f}}}")

    for scaffold in SCAFFOLDS:
        j = cross_model.get(scaffold, 0.0)
        macros.append(f"\\newcommand{{\\WEight{scaffold.title()}ModelJaccard}}{{{j:.3f}}}")

    macros_tex = "\n".join(macros) + "\n"
    with open(OUTPUT_DIR / "macros.tex", "w") as f:
        f.write(macros_tex)
    print(f"  Saved: {OUTPUT_DIR / 'macros.tex'}")

    # --- Markdown summary ---
    md_lines = ["# EX-W8: Cross-Model Scaffold Replication\n"]
    md_lines.append(f"**Total episodes**: {total_episodes} across {len(CELL_KEYS)} cells\n")

    md_lines.append("## Per-Cell Results\n")
    md_lines.append("| Model | Scaffold | N | CGA μ±σ | Flip% | FA% |")
    md_lines.append("|-------|----------|---|---------|-------|-----|")
    for model, label in MODELS.items():
        for scaffold in SCAFFOLDS:
            cell_key = CELL_KEYS[(model, scaffold)]
            m = matrix.get(cell_key, {})
            n = m.get("n_episodes", 0)
            if n == 0:
                md_lines.append(f"| {label} | {scaffold} | 0 | --- | --- | --- |")
                continue
            md_lines.append(
                f"| {label} | {scaffold} | {n} "
                f"| {m['cga_mean']:.3f}±{m['cga_sd']:.3f} "
                f"| {m['verdict_flip_rate'] * 100:.1f}% "
                f"| {m['fa_rate'] * 100:.1f}% |"
            )

    md_lines.append("\n## Cross-Scaffold Jaccard (per model)\n")
    for model, label in MODELS.items():
        j = cross_scaffold.get(model, 0.0)
        md_lines.append(f"- **{label}**: {j:.3f}")

    md_lines.append("\n## Cross-Model Jaccard (per scaffold)\n")
    for scaffold in SCAFFOLDS:
        j = cross_model.get(scaffold, 0.0)
        md_lines.append(f"- **{scaffold}**: {j:.3f}")

    md_lines.append("\n## Defense Ratio (scaffold invariance)\n")
    for model, label in MODELS.items():
        d = defense.get(model, {})
        if d:
            md_lines.append(f"- **{label}**: flip mean={d['flip_mean']:.3f}, range={d['flip_range']:.3f}")

    save_markdown("\n".join(md_lines), OUTPUT_DIR / "summary.md")

    print(f"\nDone. {total_episodes} total episodes across {len(CELL_KEYS)} cells.")


if __name__ == "__main__":
    main()
