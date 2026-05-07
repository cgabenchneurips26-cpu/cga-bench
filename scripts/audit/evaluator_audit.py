#!/usr/bin/env python3
"""Evaluator audit runbook CLI — 6-step audit for any episode-level evaluator.

Steps:
  1. pi-class classification via separating pairs
  2. Blind-Spot Rate (BSR) vs CGA-Bench (v4_hard)
  3. Plug-in Bayes-error floor for the evaluator's pi-class
  4. Top-K false-accept witnesses
  5. Repair-distance correlation (rho(verdict, d_G) + monotonicity)
  6. Blindspot cluster grid (domain x constraint_type heatmap)

Usage:
    PYTHONPATH=. python scripts/audit/evaluator_audit.py --shim dxem --out-dir audit/reports
    PYTHONPATH=. python scripts/audit/evaluator_audit.py --evaluator my_module:MyEval --out-dir audit/reports
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audit.evaluator_base import Evaluator  # noqa: E402
from audit.separating_pairs import load_separating_pairs  # noqa: E402
from audit.shims import SHIM_REGISTRY  # noqa: E402
from audit.shims._verdict_cache import (  # noqa: E402
    get_all_episode_ids,
    get_verdict,
    load_w8_episodes,
)

# Bayes error values from evidence_pack/theorem_v2/bayes_error_macros.tex
BAYES_FLOOR: dict[str, float] = {
    "term": 0.436,
    "aset": 0.024,
    "nord": 0.003,
    "nctx": 0.003,
}

PI_CLASS_HIERARCHY = ["term", "aset", "nord", "nctx"]

# Map case -> pi-class being tested
CASE_TO_PI: dict[str, str] = {
    "case_i": "term",
    "case_ii": "aset",
    "case_iii": "nord",
    "case_iv": "nctx",
}

DEFAULT_TOP_K = 10


def _load_evaluator(spec: str) -> Evaluator:
    """Import and instantiate an evaluator from dotted path 'module:ClassName'."""
    if ":" not in spec:
        raise ValueError(f"Evaluator spec must be 'module:ClassName', got {spec!r}")
    mod_path, cls_name = spec.rsplit(":", 1)
    mod = importlib.import_module(mod_path)
    cls = getattr(mod, cls_name)
    return cls()


def _resolve_evaluator(shim_name: str | None, evaluator_spec: str | None) -> Evaluator:
    """Resolve either --shim or --evaluator to an Evaluator instance."""
    if shim_name:
        if shim_name not in SHIM_REGISTRY:
            raise ValueError(f"Unknown shim {shim_name!r}. Available: {sorted(SHIM_REGISTRY)}")
        return SHIM_REGISTRY[shim_name]()
    if evaluator_spec:
        return _load_evaluator(evaluator_spec)
    raise ValueError("One of --shim or --evaluator is required")


def step1_pi_class(evaluator: Evaluator) -> dict:
    """Classify the evaluator's projection class via separating pairs.

    For each case (i-iv), test whether the evaluator can distinguish
    the pair. If it can't, it's blind at that level.
    """
    pairs = load_separating_pairs()
    results_by_case: dict[str, dict] = {}

    for case_key in ["case_i", "case_ii", "case_iii", "case_iv"]:
        case_pairs = [p for p in pairs if p.case == case_key]
        distinguished = 0
        total = len(case_pairs)

        for pair in case_pairs:
            va = evaluator.verdict({"episode_id": pair.episode_a})
            vb = evaluator.verdict({"episode_id": pair.episode_b})
            if va != vb:
                distinguished += 1

        results_by_case[case_key] = {
            "total": total,
            "distinguished": distinguished,
            "blind": distinguished == 0,
        }

    # Determine finest non-collapsed pi-class
    # Walk from coarsest to finest: if evaluator is blind at level X,
    # it collapses to that projection
    pi_class = "nctx"  # finest by default
    for case_key, pi_name in CASE_TO_PI.items():
        if results_by_case[case_key]["blind"]:
            pi_class = pi_name
            break

    return {
        "pi_class": pi_class,
        "per_case": results_by_case,
    }


def step2_bsr(evaluator: Evaluator) -> dict:
    """Compute Blind-Spot Rate vs CGA-Bench (v4_hard) reference."""
    episode_ids = get_all_episode_ids()
    n_total = len(episode_ids)
    disagree = 0
    false_accept = 0
    false_reject = 0

    for ep_id in episode_ids:
        eval_v = evaluator.verdict({"episode_id": ep_id})
        ref_v = get_verdict(ep_id, "v4_hard")
        if eval_v != ref_v:
            disagree += 1
            if eval_v and not ref_v:
                false_accept += 1
            else:
                false_reject += 1

    bsr = disagree / n_total if n_total > 0 else 0.0
    return {
        "bsr": round(bsr, 4),
        "n_total": n_total,
        "n_disagree": disagree,
        "n_false_accept": false_accept,
        "n_false_reject": false_reject,
        "false_accept_rate": round(false_accept / n_total, 4) if n_total else 0.0,
        "false_reject_rate": round(false_reject / n_total, 4) if n_total else 0.0,
    }


def step3_bayes_floor(pi_class: str) -> dict:
    """Look up the plug-in Bayes-error floor for the given pi-class."""
    eps_star = BAYES_FLOOR.get(pi_class, -1.0)
    return {
        "pi_class": pi_class,
        "epsilon_star": eps_star,
        "all_floors": BAYES_FLOOR,
    }


def step4_false_accept_witnesses(evaluator: Evaluator, top_k: int = DEFAULT_TOP_K) -> dict:
    """Find top-K episodes where evaluator says PASS but v4_hard says FAIL."""
    episodes = load_w8_episodes()
    witnesses: list[dict] = []

    for ep_id, ep_data in episodes.items():
        eval_v = evaluator.verdict({"episode_id": ep_id})
        ref_v = get_verdict(ep_id, "v4_hard")
        if eval_v and not ref_v:
            witnesses.append(
                {
                    "episode_id": ep_id,
                    "scenario_id": ep_data.get("scenario_id", ""),
                    "model": ep_data.get("model", ""),
                    "n_viols": ep_data.get("n_viols", 0),
                    "viol_types": ep_data.get("viol_types", ""),
                }
            )

    # Sort by violation count descending (most dangerous false accepts first)
    witnesses.sort(key=lambda w: w.get("n_viols", 0), reverse=True)

    # Compute domain distribution
    scenario_domains: Counter[str] = Counter()
    for w in witnesses:
        domain = w["scenario_id"].split("_")[0] if w["scenario_id"] else "unknown"
        scenario_domains[domain] += 1

    return {
        "total_false_accepts": len(witnesses),
        "top_k": witnesses[:top_k],
        "domain_distribution": dict(scenario_domains.most_common(10)),
    }


def step5_repair_distance(evaluator: Evaluator, dg_cache_path: str | None = None) -> dict:
    """Compute d_G correlation and monotonicity violations.

    Uses n_viols as d_G proxy by default; reads ILP cache if available.
    """
    from audit.metrics.repair import (
        compliance_check,
        dg_correlation,
        load_dg_cache,
        monotonicity_violations,
    )

    cache = load_dg_cache(dg_cache_path)
    rho = dg_correlation(evaluator, cache)
    mono_viols, mono_total = monotonicity_violations(evaluator, cache)
    compliance = compliance_check(cache)

    return {
        "rho_dg": round(rho, 4),
        "mono_violations": mono_viols,
        "mono_total_pairs": mono_total,
        "mono_rate": round(mono_viols / mono_total, 4) if mono_total > 0 else 0.0,
        "compliance_pass": compliance["pass"],
        "dg_source": "ilp_cache" if dg_cache_path else "n_viols_proxy",
        "corpus_with_dg": len(cache),
    }


def step6_blindspot_grid(evaluator: Evaluator) -> dict:
    """Compute domain x constraint_type blindspot grid."""
    from audit.metrics.blindspot import (
        compute_blindspot_grid,
        count_red_cells,
        grid_marginal_bsr,
        render_grid_markdown,
    )

    episodes = load_w8_episodes()
    grid = compute_blindspot_grid(evaluator, episodes)
    n_red = count_red_cells(grid)
    marginal_bsr = grid_marginal_bsr(grid)

    return {
        "grid": grid,
        "n_red_cells": n_red,
        "n_cells": sum(len(row) for row in grid.values()),
        "n_domains": len(grid),
        "marginal_bsr": round(marginal_bsr, 4),
        "markdown": render_grid_markdown(grid),
    }


def run_audit(evaluator: Evaluator, out_dir: Path, top_k: int = DEFAULT_TOP_K) -> dict:
    """Execute the full 6-step audit runbook."""
    eval_name = evaluator.meta.name
    eval_family = evaluator.meta.family

    # Step 1: pi-class
    s1 = step1_pi_class(evaluator)

    # Step 2: BSR
    s2 = step2_bsr(evaluator)

    # Step 3: Bayes floor
    s3 = step3_bayes_floor(s1["pi_class"])

    # Step 4: witnesses
    s4 = step4_false_accept_witnesses(evaluator, top_k)

    # Step 5: repair distance correlation
    s5 = step5_repair_distance(evaluator)

    # Step 6: blindspot grid
    s6 = step6_blindspot_grid(evaluator)

    report = {
        "evaluator": {
            "name": eval_name,
            "family": eval_family,
            "version": evaluator.meta.version,
            "source": evaluator.meta.source,
            "observed_features": sorted(evaluator.observed_features()),
        },
        "timestamp": datetime.now(UTC).isoformat(),
        "corpus_size": s2["n_total"],
        "step1_pi_class": s1,
        "step2_bsr": s2,
        "step3_bayes_floor": s3,
        "step4_witnesses": s4,
        "step5_repair_distance": s5,
        "step6_blindspot_grid": s6,
    }

    # Write outputs
    eval_dir = out_dir / eval_name.lower().replace(" ", "_").replace("-", "_")
    eval_dir.mkdir(parents=True, exist_ok=True)

    json_path = eval_dir / "report.json"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    md_path = eval_dir / "report.md"
    md_path.write_text(_render_markdown(report))

    return report


def _render_markdown(report: dict) -> str:
    """Render a human-readable markdown summary."""
    ev = report["evaluator"]
    s1 = report["step1_pi_class"]
    s2 = report["step2_bsr"]
    s3 = report["step3_bayes_floor"]
    s4 = report["step4_witnesses"]

    lines = [
        f"# Evaluator Audit Report: {ev['name']}",
        "",
        f"**Family:** {ev['family']}  ",
        f"**Version:** {ev['version']}  ",
        f"**Source:** {ev['source'] or 'N/A'}  ",
        f"**Observed features:** {', '.join(ev['observed_features']) or 'none declared'}  ",
        f"**Corpus:** {report['corpus_size']:,} W8-filtered episodes  ",
        f"**Generated:** {report['timestamp']}",
        "",
        "## Step 1: Projection Class",
        "",
        f"**Classified pi-class: `{s1['pi_class']}`**",
        "",
        "| Case | Pairs | Distinguished | Blind? |",
        "|------|-------|---------------|--------|",
    ]

    for case_key in ["case_i", "case_ii", "case_iii", "case_iv"]:
        c = s1["per_case"][case_key]
        blind_str = "YES" if c["blind"] else "no"
        lines.append(f"| {case_key} | {c['total']} | {c['distinguished']} | {blind_str} |")

    lines.extend(
        [
            "",
            "## Step 2: Blind-Spot Rate (BSR)",
            "",
            f"**BSR = {s2['bsr']:.4f}** ({s2['n_disagree']:,}/{s2['n_total']:,} disagreements)",
            "",
            f"- False accepts: {s2['n_false_accept']:,} ({s2['false_accept_rate']:.4f})",
            f"- False rejects: {s2['n_false_reject']:,} ({s2['false_reject_rate']:.4f})",
            "",
            "## Step 3: Bayes-Error Floor",
            "",
            f"**epsilon_star({s3['pi_class']}) = {s3['epsilon_star']:.3f}**",
            "",
            "| Projection | Bayes Floor |",
            "|------------|-------------|",
        ]
    )

    for pi, val in s3["all_floors"].items():
        marker = " <--" if pi == s3["pi_class"] else ""
        lines.append(f"| {pi} | {val:.3f}{marker} |")

    lines.extend(
        [
            "",
            "## Step 4: False-Accept Witnesses",
            "",
            f"**Total false accepts:** {s4['total_false_accepts']:,}",
            "",
        ]
    )

    if s4["top_k"]:
        lines.extend(
            [
                f"**Top-{len(s4['top_k'])} witnesses (by violation count):**",
                "",
                "| Episode ID | Scenario | Model | N_viols | Types |",
                "|------------|----------|-------|---------|-------|",
            ]
        )
        for w in s4["top_k"]:
            lines.append(
                f"| `{w['episode_id'][:60]}` | {w['scenario_id'][:40]} | {w['model']} | {w['n_viols']} | {w['viol_types']} |"
            )
    else:
        lines.append("No false accepts found (perfect agreement with reference).")

    if s4["domain_distribution"]:
        lines.extend(
            [
                "",
                "**Domain distribution of false accepts:**",
                "",
            ]
        )
        for domain, count in s4["domain_distribution"].items():
            lines.append(f"- {domain}: {count}")

    # Step 5: Repair Distance
    s5 = report.get("step5_repair_distance")
    if s5:
        lines.extend(
            [
                "",
                "## Step 5: Repair-Distance Correlation",
                "",
                f"**rho(verdict, d_G) = {s5['rho_dg']:.4f}**  ",
                f"**Source:** {s5['dg_source']}  ",
                f"**Corpus with d_G:** {s5['corpus_with_dg']:,}  ",
                "",
                f"- Monotonicity violations: {s5['mono_violations']}/{s5['mono_total_pairs']}"
                f" (rate={s5['mono_rate']:.4f})",
                f"- Compliance invariant: {'PASS' if s5['compliance_pass'] else 'FAIL'}",
            ]
        )

    # Step 6: Blindspot Grid
    s6 = report.get("step6_blindspot_grid")
    if s6:
        lines.extend(
            [
                "",
                "## Step 6: Blindspot Cluster Grid",
                "",
                f"**Red cells (>20% BSR):** {s6['n_red_cells']}/{s6['n_cells']}  ",
                f"**Domains:** {s6['n_domains']}  ",
                f"**Marginal BSR:** {s6['marginal_bsr']:.4f}",
                "",
                s6["markdown"],
            ]
        )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="CGA-Bench Evaluator Audit Harness — 6-step runbook")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--shim", type=str, help=f"Built-in shim name: {sorted(SHIM_REGISTRY)}")
    group.add_argument("--evaluator", type=str, help="Dotted path 'module:ClassName'")
    parser.add_argument("--out-dir", type=str, default="audit/reports", help="Output directory")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Top-K false-accept witnesses")
    args = parser.parse_args()

    evaluator = _resolve_evaluator(args.shim, args.evaluator)
    out_dir = Path(args.out_dir)

    print(f"Auditing evaluator: {evaluator.meta.name} ({evaluator.meta.family})")
    report = run_audit(evaluator, out_dir, args.top_k)

    s1 = report["step1_pi_class"]
    s2 = report["step2_bsr"]
    s3 = report["step3_bayes_floor"]
    s4 = report["step4_witnesses"]
    s5 = report["step5_repair_distance"]
    s6 = report["step6_blindspot_grid"]

    print(f"  pi-class:      {s1['pi_class']}")
    print(f"  BSR:           {s2['bsr']:.4f} ({s2['n_disagree']}/{s2['n_total']})")
    print(f"  Bayes floor:   {s3['epsilon_star']:.3f}")
    print(f"  False accepts: {s4['total_false_accepts']}")
    print(f"  rho(d_G):      {s5['rho_dg']:.4f} (mono={s5['mono_violations']}/{s5['mono_total_pairs']})")
    print(f"  Red cells:     {s6['n_red_cells']}/{s6['n_cells']}")

    eval_dir = out_dir / evaluator.meta.name.lower().replace(" ", "_").replace("-", "_")
    print(f"  Report:        {eval_dir}/report.json")


if __name__ == "__main__":
    main()
