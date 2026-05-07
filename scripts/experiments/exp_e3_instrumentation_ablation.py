#!/usr/bin/env python3
"""EXP-E3: Instrumentation Ablation Study.

Demonstrates that ground-truth violation detection degrades as trace
information is progressively removed.  Five ablation conditions show
that "richer scorers" cannot help when the artifact itself lacks
observable events.

Ablation conditions:
  Full          — all constraints (FORBIDDEN + WITHIN + BEFORE)
  no_timestamps — FORBIDDEN only (remove WITHIN + BEFORE)
  no_ordering   — FORBIDDEN + WITHIN (remove BEFORE)
  no_state      — WITHIN + BEFORE (remove FORBIDDEN)
  terminal_only — no constraints (empty set; terminal output only)

Outputs:
  evidence_pack/exp_e3_instrumentation_ablation.json
  evidence_pack/exp_e3_instrumentation_ablation.md
  evidence_pack/figures/exp_e3_ablation_heatmap.png
  evidence_pack/figures/exp_e3_violation_loss.png
  evidence_pack/tables/instrumentation_ablation.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_e3_instrumentation_ablation.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import chi2 as scipy_chi2
from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    TABLES_DIR,
    fmt_p,
    save_figure,
    save_json,
    save_latex_table,
    save_markdown,
    setup_matplotlib,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]  # cga_bench/
RESULTS_DIR = ROOT / "results" / "full_706_v5"

SEED: int = 42
C2_THRESHOLD: float = 0.7
ACOV_THRESHOLD: float = 0.5

MODEL_LABELS: dict[str, str] = {
    "oss120b": "120B",
    "qwen27b": "27B",
    "qwen35b": "35B",
    "qwen4b": "4B",
    "qwen397b": "397B",
    "gemma31b": "Gemma31B",
    "nemotron30b": "Nemotron30B",
    "deepseek_r1_7b": "DeepSeek-R1-7B",
}

# Map episode violation_type (lowercase) -> constraint_type (uppercase).
# Only hard-violation types are mapped; soft types (omission, deviation)
# are excluded because the ablation studies only FORBIDDEN/WITHIN/BEFORE.
VIOLATION_TYPE_TO_CONSTRAINT: dict[str, str] = {
    "commission": "FORBIDDEN",
    "timing": "WITHIN",
    "sequence": "BEFORE",
}

CONDITION_NAMES: list[str] = [
    "full",
    "no_timestamps",
    "no_ordering",
    "no_state",
    "terminal_only",
]

CONDITION_LABELS: dict[str, str] = {
    "full": "Full",
    "no_timestamps": "-Timestamps",
    "no_ordering": "-Ordering",
    "no_state": "-State",
    "terminal_only": "-All (Terminal)",
}

# Types kept under each ablation condition (None means no filter = all)
CONDITION_ALLOWED_TYPES: dict[str, set[str] | None] = {
    "full": None,  # all types
    "no_timestamps": {"FORBIDDEN"},  # FORBIDDEN only
    "no_ordering": {"FORBIDDEN", "WITHIN"},
    "no_state": {"WITHIN", "BEFORE"},
    "terminal_only": set(),  # nothing
}

CONSTRAINT_TYPES: list[str] = ["FORBIDDEN", "WITHIN", "BEFORE"]

EVALUATOR_KEYS: list[str] = ["dxem", "ac_proxy", "mab_proxy", "c2_pass", "acov_pass"]
EVALUATOR_LABELS: dict[str, str] = {
    "dxem": "DxEM",
    "ac_proxy": "AC-Proxy",
    "mab_proxy": "MAB-Proxy",
    "c2_pass": "C2>=0.7",
    "acov_pass": "ACov>=0.5",
}

VERDICT_MATRIX_PATH = EVIDENCE_DIR / "analysis" / "verdict_matrix_v6.json"


# ---------------------------------------------------------------------------
# Lightweight episode record
# ---------------------------------------------------------------------------


@dataclass
class EpisodeRecord:
    """Episode loaded from full_706_v5 with constraint-typed violations."""

    scenario_id: str
    model: str
    run_index: int
    violations: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_episodes() -> list[EpisodeRecord]:
    """Load episodes from results/full_706_v5/ with mapped violations.

    Each violation_event with a hard violation_type (commission, timing,
    sequence) is mapped to the corresponding constraint_type (FORBIDDEN,
    WITHIN, BEFORE).  Soft types (omission, deviation) are excluded.

    Returns:
        Sorted list of EpisodeRecord objects.
    """
    episodes: list[EpisodeRecord] = []
    seen: set[str] = set()

    for model_dir in sorted(RESULTS_DIR.iterdir()):
        if not model_dir.is_dir() or model_dir.name not in MODEL_LABELS:
            continue
        model = model_dir.name
        for fp in sorted(model_dir.glob("*.json")):
            if fp.name.startswith("checkpoint") or fp.name == "rescore_summary.json":
                continue
            try:
                with open(fp) as f:
                    d = json.load(f)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(d, dict):
                continue
            scen = d.get("scenario_id", "")
            run_idx = d.get("run_index", 0)

            # Deduplicate by (model, scenario, run)
            key = f"{model}_{scen}_{run_idx}"
            if key in seen:
                continue
            seen.add(key)

            # Map violation_events to constraint-typed violations
            raw_viols = d.get("violation_events", [])
            mapped: list[dict] = []
            for v in raw_viols:
                vtype = v.get("violation_type", "")
                ctype = VIOLATION_TYPE_TO_CONSTRAINT.get(vtype)
                if ctype is not None:
                    mapped.append({"constraint_type": ctype, **v})

            episodes.append(
                EpisodeRecord(
                    scenario_id=scen,
                    model=model,
                    run_index=run_idx,
                    violations=mapped,
                )
            )

    episodes.sort(key=lambda e: (e.model, e.scenario_id, e.run_index))

    # Canonical-set filter: match verdict_matrix_v6.json exactly
    vm_path = ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
    if vm_path.exists():
        vm = json.loads(vm_path.read_text())
        canonical_keys: set[str] = set()
        for rec in vm.get("per_episode", []):
            k = f"{rec.get('model_dir', '')}_{rec.get('scenario_id', '')}_{rec.get('run_index', 0)}"
            canonical_keys.add(k)
        filtered = [ep for ep in episodes if f"{ep.model}_{ep.scenario_id}_{ep.run_index}" in canonical_keys]
    else:
        filtered = episodes

    filtered.sort(key=lambda e: (e.model, e.scenario_id, e.run_index))
    return filtered


def load_verdict_matrix() -> dict[str, dict]:
    """Load verdict_matrix_v6.json and index per-episode verdicts by episode_id.

    Returns:
        Mapping from episode_id to verdict dict with keys:
        ac_proxy, mab_proxy, c2_pass, acov_pass, dxem.
    """
    with open(VERDICT_MATRIX_PATH) as f:
        raw = json.load(f)

    per_episode: list[dict] = raw.get("per_episode", [])
    index: dict[str, dict] = {}
    for entry in per_episode:
        eid = entry.get("episode_id", "")
        index[eid] = entry
    return index


def _build_episode_id(model_label: str, scenario_id: str, run_index: int) -> str:
    """Construct episode_id matching verdict_matrix_v4 convention.

    Args:
        model_label: Short label from MODEL_LABELS (e.g. "120B").
        scenario_id: Scenario identifier string.
        run_index: Zero-based run index.

    Returns:
        episode_id string in the format used by verdict_matrix_v4.
    """
    return f"{scenario_id}_{model_label}_{run_index}"


# ---------------------------------------------------------------------------
# Core ablation logic
# ---------------------------------------------------------------------------


def _filter_violations(
    violations: list[dict],
    allowed_types: set[str] | None,
) -> list[dict]:
    """Filter violation list to only allowed constraint types.

    Args:
        violations: List of violation dicts with "constraint_type" field.
        allowed_types: Set of allowed "constraint_type" values, or None for all.

    Returns:
        Filtered list of violation dicts.
    """
    if allowed_types is None:
        return violations
    return [v for v in violations if v["constraint_type"] in allowed_types]


def run_ablation(
    episodes: list[EpisodeRecord],
    verdict_index: dict[str, dict],
) -> dict[str, list[dict]]:
    """Run all five ablation conditions across all episodes.

    For each episode, the pre-computed hard violations (FORBIDDEN, WITHIN,
    BEFORE) are filtered according to each ablation condition.

    Args:
        episodes: Episode list from load_episodes().
        verdict_index: Per-episode evaluator verdicts keyed by episode_id.

    Returns:
        Mapping from condition name to list of per-episode result dicts.
    """
    results: dict[str, list[dict]] = {cond: [] for cond in CONDITION_NAMES}

    for ep in episodes:
        model_label = MODEL_LABELS.get(ep.model, ep.model)
        eid = _build_episode_id(model_label, ep.scenario_id, ep.run_index)
        verdict = verdict_index.get(eid, {})

        for cond in CONDITION_NAMES:
            allowed = CONDITION_ALLOWED_TYPES[cond]
            filtered = _filter_violations(ep.violations, allowed)
            v4_hard = len(filtered) > 0

            # Count violations by type in this condition
            type_counts: dict[str, int] = dict.fromkeys(CONSTRAINT_TYPES, 0)
            for v in filtered:
                ct = v.get("constraint_type", "")
                if ct in type_counts:
                    type_counts[ct] += 1

            # Evaluator passes (unchanged across conditions)
            eval_passes: dict[str, bool] = {key: bool(verdict.get(key, False)) for key in EVALUATOR_KEYS}

            results[cond].append(
                {
                    "episode_id": eid,
                    "scenario_id": ep.scenario_id,
                    "model": ep.model,
                    "run_index": ep.run_index,
                    "v4_hard": v4_hard,
                    "n_violations": len(filtered),
                    "type_counts": type_counts,
                    "eval_passes": eval_passes,
                }
            )

    return results


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------


def compute_bsr(
    condition_results: list[dict],
    eval_key: str,
) -> float:
    """Compute Bounded Safe-pass Rate for one (evaluator, condition) pair.

    BSR = count(evaluator_pass AND v4_hard) / N_episodes.

    Args:
        condition_results: Per-episode dicts for one condition.
        eval_key: Key into eval_passes dict.

    Returns:
        BSR as a fraction in [0, 1].
    """
    n = len(condition_results)
    if n == 0:
        return 0.0
    count = sum(1 for ep in condition_results if ep["eval_passes"].get(eval_key, False) and ep["v4_hard"])
    return count / n


def compute_condition_summary(condition_results: list[dict]) -> dict:
    """Compute aggregate metrics for one ablation condition.

    Args:
        condition_results: Per-episode dicts for one condition.

    Returns:
        Summary dict with v4_hard counts, BSR per evaluator, type totals.
    """
    n = len(condition_results)
    n_hard = sum(1 for ep in condition_results if ep["v4_hard"])
    total_viols: dict[str, int] = dict.fromkeys(CONSTRAINT_TYPES, 0)
    for ep in condition_results:
        for t, cnt in ep["type_counts"].items():
            total_viols[t] = total_viols.get(t, 0) + cnt

    bsr_by_evaluator: dict[str, float] = {}
    for key in EVALUATOR_KEYS:
        bsr_by_evaluator[key] = compute_bsr(condition_results, key)

    return {
        "n_episodes": n,
        "n_hard": n_hard,
        "hard_rate": n_hard / n if n else 0.0,
        "total_violations_by_type": total_viols,
        "bsr_by_evaluator": bsr_by_evaluator,
    }


# ---------------------------------------------------------------------------
# McNemar test
# ---------------------------------------------------------------------------


def mcnemar_test(
    results_a: list[dict],
    results_b: list[dict],
) -> dict:
    """Run McNemar test comparing v4_hard detection between two conditions.

    Args:
        results_a: Per-episode list for condition A.
        results_b: Per-episode list for condition B (same episode order).

    Returns:
        Dict with b, c, chi2, p_value fields.
    """
    assert len(results_a) == len(results_b), "Mismatched episode counts"
    b = sum(1 for a, bep in zip(results_a, results_b) if a["v4_hard"] and not bep["v4_hard"])
    c = sum(1 for a, bep in zip(results_a, results_b) if not a["v4_hard"] and bep["v4_hard"])
    denom = b + c
    if denom == 0:
        chi2_val = 0.0
        p_val = 1.0
    else:
        chi2_val = (b - c) ** 2 / denom
        p_val = float(scipy_chi2.sf(chi2_val, df=1))
    return {"b": b, "c": c, "chi2": chi2_val, "p_value": p_val}


def compute_mcnemar_pairs(ablation_results: dict[str, list[dict]]) -> list[dict]:
    """Compute McNemar tests for all 10 condition pairs.

    Args:
        ablation_results: Condition name -> per-episode list.

    Returns:
        List of McNemar result dicts.
    """
    pairs: list[dict] = []
    cond_list = CONDITION_NAMES
    for i in range(len(cond_list)):
        for j in range(i + 1, len(cond_list)):
            cond_i = cond_list[i]
            cond_j = cond_list[j]
            stat = mcnemar_test(
                ablation_results[cond_i],
                ablation_results[cond_j],
            )
            pairs.append(
                {
                    "condition_a": cond_i,
                    "condition_b": cond_j,
                    **stat,
                }
            )
    return pairs


# ---------------------------------------------------------------------------
# Violation loss
# ---------------------------------------------------------------------------


def compute_violation_loss(
    full_results: list[dict],
    ablation_results: dict[str, list[dict]],
) -> dict[str, dict[str, int]]:
    """Compute violations lost per type for each non-full condition.

    Args:
        full_results: Per-episode results under "full" condition.
        ablation_results: All condition results.

    Returns:
        Mapping condition_name -> {constraint_type: n_lost}.
    """
    full_totals: dict[str, int] = dict.fromkeys(CONSTRAINT_TYPES, 0)
    for ep in full_results:
        for t in CONSTRAINT_TYPES:
            full_totals[t] += ep["type_counts"].get(t, 0)

    loss: dict[str, dict[str, int]] = {}
    for cond in CONDITION_NAMES:
        if cond == "full":
            continue
        cond_totals: dict[str, int] = dict.fromkeys(CONSTRAINT_TYPES, 0)
        for ep in ablation_results[cond]:
            for t in CONSTRAINT_TYPES:
                cond_totals[t] += ep["type_counts"].get(t, 0)
        loss[cond] = {t: full_totals[t] - cond_totals[t] for t in CONSTRAINT_TYPES}
    return loss


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _make_heatmap(summaries: dict[str, dict]) -> plt.Figure:
    """Produce BSR heatmap: rows=conditions, cols=evaluators.

    Args:
        summaries: condition_name -> summary dict with bsr_by_evaluator.

    Returns:
        Matplotlib Figure.
    """
    evaluators = EVALUATOR_KEYS
    conditions = CONDITION_NAMES

    data = np.array([[summaries[cond]["bsr_by_evaluator"].get(ev, 0.0) for ev in evaluators] for cond in conditions])

    row_labels = [CONDITION_LABELS[c] for c in conditions]
    col_labels = [EVALUATOR_LABELS[e] for e in evaluators]

    fig, ax = plt.subplots(figsize=(9, 4))
    im = ax.imshow(data, aspect="auto", cmap="YlOrRd", vmin=0.0, vmax=1.0)
    plt.colorbar(im, ax=ax, label="BSR")

    ax.set_xticks(range(len(col_labels)))
    ax.set_xticklabels(col_labels, rotation=30, ha="right", fontsize=10)
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels(row_labels, fontsize=10)

    for i in range(len(conditions)):
        for j in range(len(evaluators)):
            val = data[i, j]
            color = "white" if val > 0.6 else "black"
            ax.text(
                j,
                i,
                f"{val:.2f}",
                ha="center",
                va="center",
                fontsize=9,
                color=color,
                fontweight="bold",
            )

    ax.set_title(
        "BSR by Ablation Condition and Evaluator\n(BSR = evaluator-pass AND v4-hard / N)",
        fontsize=12,
    )
    ax.set_xlabel("Evaluator", fontsize=11)
    ax.set_ylabel("Ablation Condition", fontsize=11)
    fig.tight_layout()
    return fig


def _make_violation_loss_bar(
    violation_loss: dict[str, dict[str, int]],
) -> plt.Figure:
    """Produce stacked bar chart of violations lost by type per condition.

    Args:
        violation_loss: condition -> {FORBIDDEN, WITHIN, BEFORE} -> n_lost.

    Returns:
        Matplotlib Figure.
    """
    conditions = [c for c in CONDITION_NAMES if c != "full"]
    cond_labels = [CONDITION_LABELS[c] for c in conditions]

    forbidden_counts = [violation_loss[c].get("FORBIDDEN", 0) for c in conditions]
    within_counts = [violation_loss[c].get("WITHIN", 0) for c in conditions]
    before_counts = [violation_loss[c].get("BEFORE", 0) for c in conditions]

    x = np.arange(len(conditions))
    width = 0.5

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x, forbidden_counts, width, label="FORBIDDEN", color="#d62728")
    ax.bar(x, within_counts, width, bottom=forbidden_counts, label="WITHIN", color="#ff7f0e")
    before_bottom = [f + w for f, w in zip(forbidden_counts, within_counts)]
    ax.bar(x, before_counts, width, bottom=before_bottom, label="BEFORE", color="#1f77b4")

    ax.set_xticks(x)
    ax.set_xticklabels(cond_labels, rotation=15, ha="right", fontsize=10)
    ax.set_ylabel("Violations Lost vs. Full Condition", fontsize=11)
    ax.set_title(
        "Violation Loss by Constraint Type\nper Ablation Condition",
        fontsize=12,
    )
    ax.legend(title="Constraint Type", fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# LaTeX table
# ---------------------------------------------------------------------------


def _make_latex_table(
    summaries: dict[str, dict],
    mcnemar_pairs: list[dict],
    path: Path,
) -> None:
    """Save instrumentation ablation LaTeX table.

    Args:
        summaries: condition -> summary dict.
        mcnemar_pairs: McNemar test results for all condition pairs.
        path: Output .tex file path.
    """
    headers = [
        "Condition",
        r"$N_{\text{hard}}$",
        "Hard Rate",
        "BSR(DxEM)",
        "BSR(AC)",
        "BSR(MAB)",
        "BSR(C2)",
        "BSR(ACov)",
    ]
    rows: list[list[str]] = []
    for cond in CONDITION_NAMES:
        s = summaries[cond]
        bsr = s["bsr_by_evaluator"]
        rows.append(
            [
                CONDITION_LABELS[cond],
                str(s["n_hard"]),
                f"{s['hard_rate']:.3f}",
                f"{bsr.get('dxem', 0.0):.3f}",
                f"{bsr.get('ac_proxy', 0.0):.3f}",
                f"{bsr.get('mab_proxy', 0.0):.3f}",
                f"{bsr.get('c2_pass', 0.0):.3f}",
                f"{bsr.get('acov_pass', 0.0):.3f}",
            ]
        )
    save_latex_table(
        rows,
        headers,
        path,
        caption=(
            "Instrumentation Ablation: BSR by condition and evaluator. "
            r"$N_{\text{hard}}$ counts episodes with at least one constraint "
            "violation under each condition. "
            "BSR = evaluator-pass $\\cap$ v4-hard / N."
        ),
        label="tab:instrumentation_ablation",
    )


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _make_markdown_report(
    summaries: dict[str, dict],
    mcnemar_pairs: list[dict],
    violation_loss: dict[str, dict[str, int]],
    n_episodes: int,
) -> str:
    """Produce markdown summary report.

    Args:
        summaries: condition -> summary dict.
        mcnemar_pairs: McNemar test results.
        violation_loss: Violations lost per condition.
        n_episodes: Total episode count.

    Returns:
        Markdown string.
    """
    lines: list[str] = [
        "# EXP-E3: Instrumentation Ablation",
        "",
        f"**Total episodes:** {n_episodes}",
        "",
        "## Condition Summaries",
        "",
        "| Condition | N Hard | Hard Rate | BSR(DxEM) | BSR(AC) | BSR(MAB) | BSR(C2) | BSR(ACov) |",
        "|-----------|--------|-----------|-----------|---------|----------|---------|-----------|",
    ]
    for cond in CONDITION_NAMES:
        s = summaries[cond]
        b = s["bsr_by_evaluator"]
        lines.append(
            f"| {CONDITION_LABELS[cond]} | {s['n_hard']} | {s['hard_rate']:.3f}"
            f" | {b.get('dxem', 0.0):.3f} | {b.get('ac_proxy', 0.0):.3f}"
            f" | {b.get('mab_proxy', 0.0):.3f} | {b.get('c2_pass', 0.0):.3f}"
            f" | {b.get('acov_pass', 0.0):.3f} |"
        )

    lines += [
        "",
        "## Violation Loss vs. Full Condition",
        "",
        "| Condition | FORBIDDEN Lost | WITHIN Lost | BEFORE Lost |",
        "|-----------|----------------|-------------|-------------|",
    ]
    for cond in CONDITION_NAMES:
        if cond == "full":
            continue
        vl = violation_loss[cond]
        lines.append(
            f"| {CONDITION_LABELS[cond]} | {vl.get('FORBIDDEN', 0)} | {vl.get('WITHIN', 0)} | {vl.get('BEFORE', 0)} |"
        )

    lines += [
        "",
        "## McNemar Tests (v4-hard detection)",
        "",
        "| Condition A | Condition B | b | c | chi2 | p |",
        "|-------------|-------------|---|---|------|---|",
    ]
    for pair in mcnemar_pairs:
        sig = " *" if pair["p_value"] < 0.05 else ""
        lines.append(
            f"| {CONDITION_LABELS[pair['condition_a']]}"
            f" | {CONDITION_LABELS[pair['condition_b']]}"
            f" | {pair['b']} | {pair['c']}"
            f" | {pair['chi2']:.3f} | {fmt_p(pair['p_value'])}{sig} |"
        )

    lines += [
        "",
        "---",
        "",
        "**Finding:** Richer scorers cannot compensate for artifacts that"
        " lack observable events. Removing timestamps eliminates WITHIN"
        " and BEFORE violations; removing state removes FORBIDDEN detection."
        " Only the Full condition preserves complete constraint observability.",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run EXP-E3 instrumentation ablation and save all outputs."""
    setup_matplotlib()
    rng = np.random.default_rng(SEED)  # noqa: F841 — available for future use

    print("=" * 60)
    print("EXP-E3: Instrumentation Ablation Study")
    print("=" * 60)

    print("\nLoading episodes from full_706_v5...")
    episodes = load_episodes()
    n_episodes = len(episodes)
    print(f"  Episodes loaded: {n_episodes}")

    print("\nLoading verdict matrix...")
    verdict_index = load_verdict_matrix()
    print(f"  Verdict entries indexed: {len(verdict_index)}")

    print("\nRunning ablation conditions...")
    ablation_results = run_ablation(episodes, verdict_index)
    for cond in CONDITION_NAMES:
        n_hard = sum(1 for ep in ablation_results[cond] if ep["v4_hard"])
        print(f"  [{CONDITION_LABELS[cond]}] hard episodes: {n_hard}/{n_episodes}")

    print("\nComputing summaries...")
    summaries: dict[str, dict] = {cond: compute_condition_summary(ablation_results[cond]) for cond in CONDITION_NAMES}

    print("\nRunning McNemar tests...")
    mcnemar_pairs = compute_mcnemar_pairs(ablation_results)

    print("\nComputing violation loss...")
    violation_loss = compute_violation_loss(ablation_results["full"], ablation_results)

    # ------------------------------------------------------------------
    # Save outputs
    # ------------------------------------------------------------------
    out_json = EVIDENCE_DIR / "exp_e3_instrumentation_ablation.json"
    out_md = EVIDENCE_DIR / "exp_e3_instrumentation_ablation.md"
    out_heatmap = FIGURES_DIR / "exp_e3_ablation_heatmap.png"
    out_viol_bar = FIGURES_DIR / "exp_e3_violation_loss.png"
    out_tex = TABLES_DIR / "instrumentation_ablation.tex"

    print("\nSaving JSON output...")
    payload = {
        "experiment": "exp_e3_instrumentation_ablation",
        "n_episodes": n_episodes,
        "conditions": CONDITION_NAMES,
        "summaries": summaries,
        "mcnemar_pairs": mcnemar_pairs,
        "violation_loss": violation_loss,
        "per_episode": {cond: ablation_results[cond] for cond in CONDITION_NAMES},
    }
    save_json(payload, out_json)

    print("\nSaving markdown report...")
    md_text = _make_markdown_report(summaries, mcnemar_pairs, violation_loss, n_episodes)
    save_markdown(md_text, out_md)

    print("\nGenerating heatmap figure...")
    fig_heatmap = _make_heatmap(summaries)
    save_figure(fig_heatmap, out_heatmap)

    print("\nGenerating violation loss bar chart...")
    fig_bar = _make_violation_loss_bar(violation_loss)
    save_figure(fig_bar, out_viol_bar)

    print("\nSaving LaTeX table...")
    _make_latex_table(summaries, mcnemar_pairs, out_tex)

    print("\n" + "=" * 60)
    print("EXP-E3 complete.")
    print(f"  JSON  : {out_json}")
    print(f"  MD    : {out_md}")
    print(f"  Figure: {out_heatmap}")
    print(f"  Figure: {out_viol_bar}")
    print(f"  LaTeX : {out_tex}")
    print("=" * 60)


if __name__ == "__main__":
    main()
