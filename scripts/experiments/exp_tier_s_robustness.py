#!/usr/bin/env python3
"""Tier S Subset Robustness Analysis.

Filters the 14,826 baseline episodes to the 17 Tier S CPGs (C1-C12
score >= 15) and recomputes all headline blind-spot metrics.  This
demonstrates that evaluation results are not driven by low-quality or
weakly formalized guidelines.

Metrics recomputed:
  1. Strict false-accept rate  (ao_fa)
  2. Per-evaluator false-accept rate
  3. Verdict flip rate
  4. eta2(evaluator) and eta2(run) + ratio
  5. BSR per evaluator (false-accept / total)
  6. Per-evaluator pass rates

Outputs:
  evidence_pack/tier_s/tier_s_robustness.json
  evidence_pack/tier_s/tier_s_macros.tex
  evidence_pack/tier_s/tier_s_comparison.md

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_tier_s_robustness.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from scripts.experiments._common import (
    EVIDENCE_DIR,
    canonical_graph_id,
    load_all_scenarios,
    save_json,
)
from scripts.experiments._episode_cache import (
    load_cached_verdicts,
)
from scripts.experiments.exp_cres_5_effect_size import (
    _build_verdict_matrix,
    _compute_eta2_evaluator,
    _compute_eta2_run,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTPUT_DIR = EVIDENCE_DIR / "tier_s"
SCORES_PATH = ROOT / "reports" / "cpg_scores_v2_full_124.json"
TIER_S_THRESHOLD = 15
N_BOOTSTRAP = 2000
SEED = 42

EVALUATOR_KEYS: list[str] = ["ac_proxy", "mab_proxy", "c2_pass", "cga_pass"]
EVALUATOR_LABELS: dict[str, str] = {
    "ac_proxy": "AC-Proxy",
    "mab_proxy": "MAB-Proxy",
    "c2_pass": "C2",
    "cga_pass": "CGA-Bench",
}


# ---------------------------------------------------------------------------
# Step 1: Build Tier S filter
# ---------------------------------------------------------------------------


def load_tier_s_graph_ids() -> set[str]:
    """Extract graph_ids of existing YAML CPGs that score >= 15."""
    with open(SCORES_PATH) as f:
        data = json.load(f)

    tier_s: set[str] = set()
    for entry in data["results"]:
        if entry.get("source") == "candidate":
            continue  # Skip expansion candidates — no YAML yet
        total = entry.get("axes", {}).get("total", 0)
        if total >= TIER_S_THRESHOLD:
            tier_s.add(entry["graph_id"])
    return tier_s


def build_scenario_filter(
    tier_s_graphs: set[str],
) -> tuple[set[str], dict[str, str]]:
    """Return (tier_s_scenario_ids, scenario_to_graph mapping)."""
    scenarios = load_all_scenarios(tag_source=False)
    tier_s_scenarios: set[str] = set()
    scenario_graph_map: dict[str, str] = {}

    for sc in scenarios:
        sid = sc.get("scenario_id", "")
        gid = canonical_graph_id(sc.get("guideline_graph", ""))
        scenario_graph_map[sid] = gid
        if gid in tier_s_graphs:
            tier_s_scenarios.add(sid)

    return tier_s_scenarios, scenario_graph_map


# ---------------------------------------------------------------------------
# Step 2: Metric computation helpers
# ---------------------------------------------------------------------------


def compute_basic_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute basic headline metrics from scored records."""
    n = len(records)
    if n == 0:
        return {}

    n_hard = sum(1 for r in records if r["v4_hard"])
    n_flip = sum(1 for r in records if r["verdict_flip"])
    n_ao_fa = sum(1 for r in records if r["ao_fa"])

    # Per-evaluator pass rates and false-accept counts
    eval_pass: dict[str, int] = dict.fromkeys(EVALUATOR_KEYS, 0)
    eval_fa: dict[str, int] = dict.fromkeys(EVALUATOR_KEYS, 0)

    for r in records:
        for key in EVALUATOR_KEYS:
            if r[key]:
                eval_pass[key] += 1
                if r["v4_hard"]:
                    eval_fa[key] += 1

    # eta2
    mat = _build_verdict_matrix(records)
    eta2_eval = _compute_eta2_evaluator(mat)
    eta2_run = _compute_eta2_run(records, mat)
    eta2_ratio = eta2_eval / eta2_run if eta2_run > 0 else float("inf")

    return {
        "n_episodes": n,
        "n_hard": n_hard,
        "pct_hard": round(n_hard / n * 100, 1),
        "strict_fa_rate": round(n_ao_fa / n * 100, 1),
        "strict_fa_count": n_ao_fa,
        "verdict_flip_rate": round(n_flip / n * 100, 1),
        "verdict_flip_count": n_flip,
        "eta2_evaluator": round(eta2_eval, 4),
        "eta2_run": round(eta2_run, 4),
        "eta2_ratio": round(eta2_ratio, 1),
        "eval_pass_rates": {EVALUATOR_LABELS[k]: round(eval_pass[k] / n * 100, 1) for k in EVALUATOR_KEYS},
        "eval_fa_rates": {EVALUATOR_LABELS[k]: round(eval_fa[k] / n * 100, 1) for k in EVALUATOR_KEYS},
        "eval_fa_counts": {EVALUATOR_LABELS[k]: eval_fa[k] for k in EVALUATOR_KEYS},
        "eval_bsr": {
            EVALUATOR_LABELS[k]: round(
                sum(1 for r in records if r[k] != (not r["v4_hard"])) / n,
                4,
            )
            for k in EVALUATOR_KEYS
        },
    }


# ---------------------------------------------------------------------------
# Step 3: Bootstrap CIs
# ---------------------------------------------------------------------------


def bootstrap_metric(
    records: list[dict[str, Any]],
    metric_fn: Any,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = SEED,
) -> tuple[float, float]:
    """Bootstrap CI for a metric function that takes records -> float."""
    rng = np.random.default_rng(seed)
    n = len(records)
    samples = np.zeros(n_bootstrap)
    indices = np.arange(n)

    for i in range(n_bootstrap):
        boot_idx = rng.choice(indices, size=n, replace=True)
        boot_records = [records[j] for j in boot_idx]
        samples[i] = metric_fn(boot_records)

    lo = float(np.percentile(samples, 2.5))
    hi = float(np.percentile(samples, 97.5))
    return (round(lo, 4), round(hi, 4))


def _strict_fa_fn(records: list[dict[str, Any]]) -> float:
    n = len(records)
    return sum(1 for r in records if r["ao_fa"]) / n * 100 if n else 0.0


def _flip_rate_fn(records: list[dict[str, Any]]) -> float:
    n = len(records)
    return sum(1 for r in records if r["verdict_flip"]) / n * 100 if n else 0.0


def _eta2_eval_fn(records: list[dict[str, Any]]) -> float:
    mat = _build_verdict_matrix(records)
    return _compute_eta2_evaluator(mat)


def _eta2_ratio_fn(records: list[dict[str, Any]]) -> float:
    mat = _build_verdict_matrix(records)
    e = _compute_eta2_evaluator(mat)
    r = _compute_eta2_run(records, mat)
    return e / r if r > 0 else 0.0


# ---------------------------------------------------------------------------
# Step 4: Output generation
# ---------------------------------------------------------------------------


def emit_latex_macros(
    tier_s_metrics: dict[str, Any],
    n_cpgs: int,
    n_scenarios: int,
    path: Path,
) -> None:
    """Write LaTeX macros using providecommand."""
    lines = [
        "% Tier S Robustness Analysis — auto-generated",
        f"% {n_cpgs} Tier S CPGs, {n_scenarios} scenarios, {tier_s_metrics['n_episodes']} episodes",
        "",
        f"\\providecommand{{\\tierSNCpgs}}{{{n_cpgs}}}",
        f"\\providecommand{{\\tierSNScenarios}}{{{n_scenarios}}}",
        f"\\providecommand{{\\tierSNEpisodes}}{{{tier_s_metrics['n_episodes']}}}",
        f"\\providecommand{{\\tierSStrictFA}}{{{tier_s_metrics['strict_fa_rate']}}}",
        f"\\providecommand{{\\tierSFlipRate}}{{{tier_s_metrics['verdict_flip_rate']}}}",
        f"\\providecommand{{\\tierSEtaTwo}}{{{tier_s_metrics['eta2_evaluator']}}}",
        f"\\providecommand{{\\tierSEtaRun}}{{{tier_s_metrics['eta2_run']}}}",
        f"\\providecommand{{\\tierSRatio}}{{{tier_s_metrics['eta2_ratio']}}}",
        f"\\providecommand{{\\tierSPctHard}}{{{tier_s_metrics['pct_hard']}}}",
    ]

    # Per-evaluator pass rates
    label_map = {"AC-Proxy": "AC", "MAB-Proxy": "MAB", "C2": "CTwo", "CGA-Bench": "CGA"}
    for label, short in label_map.items():
        pr = tier_s_metrics["eval_pass_rates"].get(label, 0)
        fa = tier_s_metrics["eval_fa_rates"].get(label, 0)
        bsr = tier_s_metrics["eval_bsr"].get(label, 0)
        lines.append(f"\\providecommand{{\\tierSPass{short}}}{{{pr}}}")
        lines.append(f"\\providecommand{{\\tierSFA{short}}}{{{fa}}}")
        lines.append(f"\\providecommand{{\\tierSBsr{short}}}{{{bsr}}}")

    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    print(f"  Saved: {path}")


def emit_comparison_markdown(
    full: dict[str, Any],
    tier_s: dict[str, Any],
    n_cpgs: int,
    n_scenarios: int,
    path: Path,
) -> None:
    """Write side-by-side comparison table."""
    lines = [
        "# Tier S Robustness: Full vs Tier S Comparison",
        "",
        f"Tier S: {n_cpgs} CPGs (score >= {TIER_S_THRESHOLD}/19), "
        f"{n_scenarios} scenarios, {tier_s['n_episodes']} episodes",
        "",
        "| Metric | Full ({n_full}) | Tier S ({n_ts}) | Delta |".format(
            n_full=full["n_episodes"], n_ts=tier_s["n_episodes"]
        ),
        "| --- | :---: | :---: | :---: |",
    ]

    def _row(name: str, fk: str, fmt: str = "{}") -> str:
        fv = full[fk]
        tv = tier_s[fk]
        delta = tv - fv if isinstance(tv, (int, float)) else "—"
        d_str = f"{delta:+.1f}" if isinstance(delta, float) else str(delta)
        return f"| {name} | {fmt.format(fv)} | {fmt.format(tv)} | {d_str} |"

    lines.append(_row("Episodes", "n_episodes", "{}"))
    lines.append(_row("Hard violations (%)", "pct_hard", "{}%"))
    lines.append(_row("Strict FA rate", "strict_fa_rate", "{}%"))
    lines.append(_row("Verdict flip rate", "verdict_flip_rate", "{}%"))
    lines.append(_row("eta2(evaluator)", "eta2_evaluator", "{}"))
    lines.append(_row("eta2(run)", "eta2_run", "{}"))
    lines.append(_row("eta2 ratio", "eta2_ratio", "{}x"))

    lines.append("")
    lines.append("## Per-Evaluator Pass Rates")
    lines.append("")
    lines.append("| Evaluator | Full | Tier S | Delta |")
    lines.append("| --- | :---: | :---: | :---: |")
    for label in EVALUATOR_LABELS.values():
        fv = full["eval_pass_rates"][label]
        tv = tier_s["eval_pass_rates"][label]
        lines.append(f"| {label} | {fv}% | {tv}% | {tv - fv:+.1f}% |")

    lines.append("")
    lines.append("## Per-Evaluator False-Accept Rates (against v4_hard)")
    lines.append("")
    lines.append("| Evaluator | Full | Tier S | Delta |")
    lines.append("| --- | :---: | :---: | :---: |")
    for label in EVALUATOR_LABELS.values():
        fv = full["eval_fa_rates"][label]
        tv = tier_s["eval_fa_rates"][label]
        lines.append(f"| {label} | {fv}% | {tv}% | {tv - fv:+.1f}% |")

    lines.append("")
    lines.append("## Per-Evaluator BSR")
    lines.append("")
    lines.append("| Evaluator | Full | Tier S | Delta |")
    lines.append("| --- | :---: | :---: | :---: |")
    for label in EVALUATOR_LABELS.values():
        fv = full["eval_bsr"][label]
        tv = tier_s["eval_bsr"][label]
        lines.append(f"| {label} | {fv:.4f} | {tv:.4f} | {tv - fv:+.4f} |")

    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))
    print(f"  Saved: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("Tier S Subset Robustness Analysis")
    print("=" * 60)

    # Step 1: Build filter
    print("\n[Step 1] Building Tier S filter...")
    tier_s_graphs = load_tier_s_graph_ids()
    print(f"  Tier S graph_ids: {len(tier_s_graphs)}")
    for gid in sorted(tier_s_graphs):
        print(f"    - {gid}")

    tier_s_scenarios, _ = build_scenario_filter(tier_s_graphs)
    print(f"  Tier S scenarios: {len(tier_s_scenarios)}")

    # Step 2: Load and filter episodes
    print("\n[Step 2] Loading episodes...")
    _, all_scored = load_cached_verdicts()
    print(f"  Total scored records: {len(all_scored)}")

    tier_s_scored = [r for r in all_scored if r["scenario_id"] in tier_s_scenarios]
    rest_scored = [r for r in all_scored if r["scenario_id"] not in tier_s_scenarios]
    print(f"  Tier S episodes: {len(tier_s_scored)}")
    print(f"  Non-Tier-S episodes: {len(rest_scored)}")

    # Step 3: Compute metrics
    print("\n[Step 3] Computing metrics on full dataset...")
    full_metrics = compute_basic_metrics(all_scored)

    print("[Step 3] Computing metrics on Tier S subset...")
    tier_s_metrics = compute_basic_metrics(tier_s_scored)

    # Step 4: Bootstrap CIs for key metrics
    print("\n[Step 4] Bootstrap CIs (B=2000)...")
    ci_strict_fa = bootstrap_metric(tier_s_scored, _strict_fa_fn)
    ci_flip = bootstrap_metric(tier_s_scored, _flip_rate_fn)
    ci_eta2 = bootstrap_metric(tier_s_scored, _eta2_eval_fn)
    ci_ratio = bootstrap_metric(tier_s_scored, _eta2_ratio_fn)

    tier_s_metrics["ci_strict_fa"] = ci_strict_fa
    tier_s_metrics["ci_flip_rate"] = ci_flip
    tier_s_metrics["ci_eta2_evaluator"] = ci_eta2
    tier_s_metrics["ci_eta2_ratio"] = ci_ratio

    print(f"  Strict FA: {tier_s_metrics['strict_fa_rate']}% CI [{ci_strict_fa[0]}, {ci_strict_fa[1]}]")
    print(f"  Flip rate: {tier_s_metrics['verdict_flip_rate']}% CI [{ci_flip[0]}, {ci_flip[1]}]")
    print(f"  eta2(eval): {tier_s_metrics['eta2_evaluator']} CI [{ci_eta2[0]}, {ci_eta2[1]}]")
    print(f"  eta2 ratio: {tier_s_metrics['eta2_ratio']}x CI [{ci_ratio[0]}, {ci_ratio[1]}]")

    # Step 5: Emit outputs
    print("\n[Step 5] Writing outputs...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = {
        "metadata": {
            "tier_s_threshold": TIER_S_THRESHOLD,
            "n_tier_s_cpgs": len(tier_s_graphs),
            "n_tier_s_scenarios": len(tier_s_scenarios),
            "tier_s_graph_ids": sorted(tier_s_graphs),
            "n_bootstrap": N_BOOTSTRAP,
            "seed": SEED,
        },
        "full": full_metrics,
        "tier_s": tier_s_metrics,
        "comparison": {},
    }

    # Build comparison dict
    for key in [
        "strict_fa_rate",
        "verdict_flip_rate",
        "eta2_evaluator",
        "eta2_run",
        "eta2_ratio",
        "pct_hard",
    ]:
        fv = full_metrics.get(key, 0)
        tv = tier_s_metrics.get(key, 0)
        result["comparison"][key] = {
            "full": fv,
            "tier_s": tv,
            "delta": round(tv - fv, 4) if isinstance(tv, (int, float)) else None,
        }

    save_json(result, OUTPUT_DIR / "tier_s_robustness.json")

    emit_latex_macros(
        tier_s_metrics,
        len(tier_s_graphs),
        len(tier_s_scenarios),
        OUTPUT_DIR / "tier_s_macros.tex",
    )

    emit_comparison_markdown(
        full_metrics,
        tier_s_metrics,
        len(tier_s_graphs),
        len(tier_s_scenarios),
        OUTPUT_DIR / "tier_s_comparison.md",
    )

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"  Tier S CPGs: {len(tier_s_graphs)}/25")
    print(
        f"  Tier S episodes: {len(tier_s_scored)}/{len(all_scored)} ({len(tier_s_scored) / len(all_scored) * 100:.1f}%)"
    )
    print()
    print(f"  {'Metric':<25} {'Full':>10} {'Tier S':>10} {'Delta':>10}")
    print(f"  {'-' * 25} {'-' * 10} {'-' * 10} {'-' * 10}")
    for key, label in [
        ("strict_fa_rate", "Strict FA (%)"),
        ("verdict_flip_rate", "Flip rate (%)"),
        ("eta2_evaluator", "eta2(eval)"),
        ("eta2_ratio", "eta2 ratio"),
        ("pct_hard", "Hard viol (%)"),
    ]:
        fv = full_metrics[key]
        tv = tier_s_metrics[key]
        delta = tv - fv
        print(f"  {label:<25} {fv:>10} {tv:>10} {delta:>+10.1f}")

    print("\n  Per-evaluator pass rates:")
    for label in EVALUATOR_LABELS.values():
        fv = full_metrics["eval_pass_rates"][label]
        tv = tier_s_metrics["eval_pass_rates"][label]
        print(f"    {label:<12} {fv:>6.1f}% -> {tv:>6.1f}% ({tv - fv:+.1f}%)")

    print("\nDone.")


if __name__ == "__main__":
    main()
