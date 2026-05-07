#!/usr/bin/env python3
"""EX-29: Held-Out Per-Domain Breakdown — per-graph metrics for 5 held-out domains.

For each held-out graph, computes:
  1. Episode count
  2. Verdict-flip rate (any evaluator pair disagrees)
  3. FA rates: AC-Proxy, MAB-Proxy, C2, All-oblivious
  4. Violation type distribution (FORBIDDEN/WITHIN/BEFORE/MUST %)
  5. Cohen's d vs in-domain aggregate

Cross-domain consistency:
  - Spearman rho of per-domain FA ranking: held-out vs in-domain

Output: evidence_pack/ex29_heldout_domain/
Macros: heldoutNDomains, heldoutDomainFARange, heldoutDomainFlipRange, etc.

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_e29_heldout_domain.py
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._common import (
    HELD_OUT_GRAPH_IDS,
    bootstrap_ci,
    load_all_scenarios,
    save_json,
    save_markdown,
)

RESULTS_DIR = ROOT / "results" / "full_706_v5"
VM_PATH = ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
OUTPUT_DIR = ROOT / "evidence_pack" / "ex29_heldout_domain"

MODEL_LABELS: set[str] = {
    "oss120b",
    "qwen27b",
    "qwen35b",
    "qwen4b",
    "qwen397b",
    "gemma31b",
    "nemotron30b",
    "deepseek_r1_7b",
}

HARD_VIOL_TYPES = frozenset({"COMMISSION", "TIMING", "SEQUENCE"})

AC_THRESHOLD = 0.5
MAB_F1_THRESHOLD = 0.5
C2_THRESHOLD = 0.7
C2_TIMING_PENALTY = 0.05


# ---------------------------------------------------------------------------
# Episode loading (reuses exp_e18 pattern)
# ---------------------------------------------------------------------------


def _normalize_action(aid: str) -> str:
    return aid.strip().lower().replace("-", "_").replace(" ", "_")


def _extract_action_sets(ep: dict) -> tuple[set[str], set[str]]:
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
    return performed, expected


def _extract_viol_types(ep: dict) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for v in ep.get("violation_events", []):
        if not isinstance(v, dict):
            continue
        raw = str(v.get("violation_type", v.get("type", ""))).upper().strip()
        for canonical in ("OMISSION", "COMMISSION", "TIMING", "SEQUENCE", "DEVIATION"):
            if canonical in raw:
                counts[canonical] += 1
                break
    return dict(counts)


def _has_hard_violation(viol_types: dict[str, int]) -> bool:
    return any(viol_types.get(t, 0) > 0 for t in HARD_VIOL_TYPES)


def _coverage(performed: set[str], expected: set[str]) -> float:
    if not expected:
        return 1.0
    return len(performed & expected) / len(expected)


def _f1(performed: set[str], expected: set[str]) -> float:
    if not expected:
        return 0.0
    tp = len(performed & expected)
    prec = tp / len(performed) if performed else 0.0
    rec = tp / len(expected)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def load_episodes() -> list[dict]:
    """Load canonical episodes with graph annotation."""
    # Build scenario -> graph mapping
    scenarios = load_all_scenarios(tag_source=True)
    sid_to_graph: dict[str, str] = {}
    sid_to_source: dict[str, str] = {}
    for s in scenarios:
        sid = s.get("scenario_id", "")
        sid_to_graph[sid] = s.get("_canonical_graph_id", "")
        sid_to_source[sid] = s.get("source_type", "unknown")

    # Load canonical episode keys
    canonical_keys: set[str] = set()
    if VM_PATH.exists():
        vm = json.loads(VM_PATH.read_text())
        for rec in vm.get("per_episode", []):
            k = f"{rec.get('scenario_id', '')}_{rec.get('model_dir', '')}_{rec.get('run_index', 0)}"
            canonical_keys.add(k)

    episodes: list[dict] = []
    seen: set[str] = set()

    for model_dir in sorted(RESULTS_DIR.iterdir()):
        if not model_dir.is_dir() or model_dir.name not in MODEL_LABELS:
            continue
        model_name = model_dir.name
        for f in sorted(model_dir.glob("*.json")):
            if f.name.startswith(("checkpoint", ".claim", "log_")):
                continue
            try:
                ep = json.loads(f.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(ep, dict):
                continue
            sid = ep.get("scenario_id", "")
            if not sid:
                continue
            run_idx = ep.get("run_index", 0)
            dedup_key = f"{sid}_{model_name}_r{run_idx}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Canonical filter
            canon_key = f"{sid}_{model_name}_{run_idx}"
            if canonical_keys and canon_key not in canonical_keys:
                continue

            ep["_model"] = model_name
            ep["_graph_id"] = sid_to_graph.get(sid, "")
            ep["_source_type"] = sid_to_source.get(sid, "unknown")
            episodes.append(ep)

    return episodes


# ---------------------------------------------------------------------------
# Per-domain analysis
# ---------------------------------------------------------------------------


def compute_domain_metrics(eps: list[dict]) -> dict:
    """Compute all metrics for a set of episodes."""
    n = len(eps)
    if n == 0:
        return {"n_episodes": 0}

    # Pre-compute per-episode verdicts
    ac_pass_count = 0
    mab_pass_count = 0
    c2_pass_count = 0
    hard_count = 0
    all_oblivious_fa_count = 0

    viol_type_totals: Counter[str] = Counter()
    fa_ac_values: list[float] = []

    for ep in eps:
        performed, expected = _extract_action_sets(ep)
        vtypes = _extract_viol_types(ep)
        has_hard = _has_hard_violation(vtypes)

        cov = _coverage(performed, expected)
        f1_val = _f1(performed, expected)
        c2_score = cov - vtypes.get("TIMING", 0) * C2_TIMING_PENALTY

        v_ac = cov >= AC_THRESHOLD
        v_mab = f1_val >= MAB_F1_THRESHOLD
        v_c2 = c2_score >= C2_THRESHOLD

        if v_ac:
            ac_pass_count += 1
        if v_mab:
            mab_pass_count += 1
        if v_c2:
            c2_pass_count += 1
        if has_hard:
            hard_count += 1

        # All-oblivious FA: all proxies pass but has hard violation
        if v_ac and v_c2 and has_hard:
            all_oblivious_fa_count += 1

        # Violation type counts
        for vt, cnt in vtypes.items():
            viol_type_totals[vt] += cnt

        fa_ac_values.append(1.0 if (v_ac and has_hard) else 0.0)

    # Verdict flip: any evaluator pair disagrees
    flip_count = 0
    for ep in eps:
        performed, expected = _extract_action_sets(ep)
        vtypes = _extract_viol_types(ep)
        has_hard = _has_hard_violation(vtypes)
        cov = _coverage(performed, expected)
        f1_val = _f1(performed, expected)
        c2_score = cov - vtypes.get("TIMING", 0) * C2_TIMING_PENALTY

        verdicts = [
            cov >= AC_THRESHOLD,
            f1_val >= MAB_F1_THRESHOLD,
            c2_score >= C2_THRESHOLD,
            not has_hard,  # TCC
        ]
        if len(set(verdicts)) > 1:
            flip_count += 1

    # Violation distribution
    total_viols = sum(viol_type_totals.values())
    viol_dist: dict[str, float] = {}
    for vt in ("COMMISSION", "TIMING", "SEQUENCE", "OMISSION", "DEVIATION"):
        viol_dist[vt] = round(viol_type_totals.get(vt, 0) / max(total_viols, 1) * 100, 1)

    # Bootstrap CI for AC FA rate
    fa_arr = np.array(fa_ac_values)
    fa_ac_rate = float(np.mean(fa_arr)) * 100 if len(fa_arr) > 0 else 0.0
    ci_lo, ci_hi = bootstrap_ci(fa_arr, lambda x: float(np.mean(x)) * 100) if len(fa_arr) > 10 else (0.0, 0.0)

    return {
        "n_episodes": n,
        "hard_rate": round(hard_count / n * 100, 1),
        "verdict_flip_rate": round(flip_count / n * 100, 1),
        "fa_ac": round(
            (ac_pass_count > 0 and hard_count > 0 and sum(1 for ep in eps if _check_ac_fa(ep)) / n * 100) or 0, 1
        ),
        "fa_ac_rate": round(fa_ac_rate, 1),
        "fa_ac_ci": [round(ci_lo, 1), round(ci_hi, 1)],
        "fa_mab": round(_count_fa(eps, "mab") / n * 100, 1),
        "fa_c2": round(_count_fa(eps, "c2") / n * 100, 1),
        "all_oblivious_fa": round(all_oblivious_fa_count / n * 100, 1),
        "all_oblivious_fa_count": all_oblivious_fa_count,
        "ac_pass_rate": round(ac_pass_count / n * 100, 1),
        "mab_pass_rate": round(mab_pass_count / n * 100, 1),
        "c2_pass_rate": round(c2_pass_count / n * 100, 1),
        "tcc_pass_rate": round((n - hard_count) / n * 100, 1),
        "violation_distribution": viol_dist,
        "total_violations": total_viols,
    }


def _check_ac_fa(ep: dict) -> bool:
    """Check if episode is AC false accept (AC pass + hard violation)."""
    performed, expected = _extract_action_sets(ep)
    vtypes = _extract_viol_types(ep)
    return _coverage(performed, expected) >= AC_THRESHOLD and _has_hard_violation(vtypes)


def _count_fa(eps: list[dict], evaluator: str) -> int:
    """Count false accepts for given evaluator."""
    count = 0
    for ep in eps:
        performed, expected = _extract_action_sets(ep)
        vtypes = _extract_viol_types(ep)
        has_hard = _has_hard_violation(vtypes)
        if not has_hard:
            continue
        cov = _coverage(performed, expected)
        f1_val = _f1(performed, expected)
        c2_score = cov - vtypes.get("TIMING", 0) * C2_TIMING_PENALTY

        if (
            (evaluator == "ac" and cov >= AC_THRESHOLD)
            or (evaluator == "mab" and f1_val >= MAB_F1_THRESHOLD)
            or (evaluator == "c2" and c2_score >= C2_THRESHOLD)
        ):
            count += 1
    return count


def cohens_d(group1: list[float], group2: list[float]) -> float:
    """Compute Cohen's d between two groups."""
    n1, n2 = len(group1), len(group2)
    if n1 < 2 or n2 < 2:
        return 0.0
    m1, m2 = np.mean(group1), np.mean(group2)
    s1, s2 = np.std(group1, ddof=1), np.std(group2, ddof=1)
    pooled_std = math.sqrt(((n1 - 1) * s1**2 + (n2 - 1) * s2**2) / (n1 + n2 - 2))
    if pooled_std == 0:
        return 0.0
    return float((m1 - m2) / pooled_std)


def spearman_rho(x: list[float], y: list[float]) -> float:
    """Compute Spearman rank correlation."""
    from scipy.stats import spearmanr

    if len(x) < 3:
        return float("nan")
    rho, _ = spearmanr(x, y)
    return float(rho)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 70)
    print("EX-29: HELD-OUT PER-DOMAIN BREAKDOWN")
    print("=" * 70)

    episodes = load_episodes()
    print(f"Loaded {len(episodes)} canonical episodes")

    # Split by domain type
    held_out_eps: dict[str, list[dict]] = defaultdict(list)
    in_domain_eps: list[dict] = []

    for ep in episodes:
        gid = ep.get("_graph_id", "")
        if gid in HELD_OUT_GRAPH_IDS:
            held_out_eps[gid].append(ep)
        else:
            in_domain_eps.append(ep)

    print(f"  In-domain: {len(in_domain_eps)} episodes")
    for gid in sorted(HELD_OUT_GRAPH_IDS):
        print(f"  Held-out {gid}: {len(held_out_eps.get(gid, []))} episodes")

    # Compute per-domain metrics
    domain_results: dict[str, dict] = {}
    for gid in sorted(HELD_OUT_GRAPH_IDS):
        eps = held_out_eps.get(gid, [])
        if not eps:
            print(f"  WARNING: No episodes for {gid}")
            continue
        domain_results[gid] = compute_domain_metrics(eps)

    # In-domain aggregate
    in_domain_metrics = compute_domain_metrics(in_domain_eps)

    # Cross-domain consistency: Spearman rho of FA ranking
    # Compare held-out FA rates per domain with in-domain aggregate
    held_out_fa_rates = [domain_results[g]["fa_ac_rate"] for g in sorted(domain_results)]
    held_out_flip_rates = [domain_results[g]["verdict_flip_rate"] for g in sorted(domain_results)]
    held_out_ao_rates = [domain_results[g]["all_oblivious_fa"] for g in sorted(domain_results)]

    # Cohen's d for each held-out domain vs in-domain
    in_domain_fa_per_ep = []
    for ep in in_domain_eps:
        in_domain_fa_per_ep.append(1.0 if _check_ac_fa(ep) else 0.0)

    for gid in sorted(domain_results):
        domain_fa_per_ep = [1.0 if _check_ac_fa(ep) else 0.0 for ep in held_out_eps[gid]]
        d = cohens_d(domain_fa_per_ep, in_domain_fa_per_ep)
        domain_results[gid]["cohens_d_vs_indomain"] = round(d, 3)

    # Count blind spots (any domain with all-oblivious FA > 0)
    n_blind_spot_domains = sum(1 for g in domain_results if domain_results[g]["all_oblivious_fa"] > 0)

    # FA range
    fa_range_min = min(held_out_fa_rates) if held_out_fa_rates else 0.0
    fa_range_max = max(held_out_fa_rates) if held_out_fa_rates else 0.0
    flip_range_min = min(held_out_flip_rates) if held_out_flip_rates else 0.0
    flip_range_max = max(held_out_flip_rates) if held_out_flip_rates else 0.0

    # Spearman: held-out FA vs in-domain FA (using per-domain in-domain breakdown)
    # For cross-domain rho, we compare held-out domain FA rank with in-domain domain FA rank
    # Since we only have 5 held-out domains, we compute rho of AO-FA vs flip-rate across those 5
    cross_rho = spearman_rho(held_out_ao_rates, held_out_flip_rates) if len(held_out_ao_rates) >= 3 else float("nan")

    # Assemble results
    results = {
        "n_held_out_domains": len(domain_results),
        "n_in_domain_episodes": len(in_domain_eps),
        "per_domain": domain_results,
        "in_domain_aggregate": in_domain_metrics,
        "cross_domain": {
            "fa_range": [round(fa_range_min, 1), round(fa_range_max, 1)],
            "flip_range": [round(flip_range_min, 1), round(flip_range_max, 1)],
            "ao_fa_rates": {g: domain_results[g]["all_oblivious_fa"] for g in sorted(domain_results)},
            "spearman_rho_ao_vs_flip": round(cross_rho, 3) if not math.isnan(cross_rho) else "N/A",
            "n_blind_spot_domains": n_blind_spot_domains,
        },
    }

    # Save outputs
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(results, OUTPUT_DIR / "heldout_domain_breakdown.json")

    md = _generate_markdown(results)
    save_markdown(md, OUTPUT_DIR / "heldout_domain_breakdown.md")

    macros = _generate_macros(results)
    macros_path = OUTPUT_DIR / "macros.tex"
    macros_path.write_text(macros)
    print(f"  Saved: {macros_path}")

    # Print summary
    print(f"\n  Held-out domains: {len(domain_results)}")
    for gid in sorted(domain_results):
        dm = domain_results[gid]
        print(
            f"    {gid}: n={dm['n_episodes']}, flip={dm['verdict_flip_rate']}%, "
            f"FA(AC)={dm['fa_ac_rate']}%, AO-FA={dm['all_oblivious_fa']}%, "
            f"d={dm.get('cohens_d_vs_indomain', 'N/A')}"
        )
    print(
        f"  In-domain aggregate: n={in_domain_metrics['n_episodes']}, "
        f"flip={in_domain_metrics['verdict_flip_rate']}%, FA(AC)={in_domain_metrics['fa_ac_rate']}%"
    )
    print(f"  FA range: {fa_range_min:.1f}--{fa_range_max:.1f}%")
    print(f"  Blind-spot domains: {n_blind_spot_domains}/{len(domain_results)}")
    print("=" * 70)


def _generate_markdown(results: dict) -> str:
    lines = [
        "# EX-29: Held-Out Per-Domain Breakdown",
        "",
        f"**Held-out domains:** {results['n_held_out_domains']}",
        f"**In-domain episodes:** {results['n_in_domain_episodes']}",
        "",
        "## Per-Domain Metrics",
        "",
        "| Domain | N | Flip% | FA(AC)% | FA(MAB)% | FA(C2)% | AO-FA% | d |",
        "|--------|---|-------|---------|----------|---------|--------|---|",
    ]
    for gid, dm in sorted(results["per_domain"].items()):
        lines.append(
            f"| {gid} | {dm['n_episodes']} | {dm['verdict_flip_rate']} | "
            f"{dm['fa_ac_rate']} | {dm['fa_mab']} | {dm['fa_c2']} | "
            f"{dm['all_oblivious_fa']} | {dm.get('cohens_d_vs_indomain', 'N/A')} |"
        )

    idm = results["in_domain_aggregate"]
    lines.append(
        f"| **In-domain** | {idm['n_episodes']} | {idm['verdict_flip_rate']} | "
        f"{idm['fa_ac_rate']} | {idm['fa_mab']} | {idm['fa_c2']} | "
        f"{idm['all_oblivious_fa']} | ref |"
    )

    lines.extend(
        [
            "",
            "## Violation Type Distribution",
            "",
            "| Domain | COMMISSION | TIMING | SEQUENCE | OMISSION | DEVIATION |",
            "|--------|-----------|--------|----------|----------|-----------|",
        ]
    )
    for gid, dm in sorted(results["per_domain"].items()):
        vd = dm["violation_distribution"]
        lines.append(
            f"| {gid} | {vd.get('COMMISSION', 0)}% | {vd.get('TIMING', 0)}% | "
            f"{vd.get('SEQUENCE', 0)}% | {vd.get('OMISSION', 0)}% | {vd.get('DEVIATION', 0)}% |"
        )

    cd = results["cross_domain"]
    lines.extend(
        [
            "",
            "## Cross-Domain Consistency",
            "",
            f"- FA range: {cd['fa_range'][0]}--{cd['fa_range'][1]}%",
            f"- Flip range: {cd['flip_range'][0]}--{cd['flip_range'][1]}%",
            f"- Spearman rho (AO-FA vs flip): {cd['spearman_rho_ao_vs_flip']}",
            f"- Domains with blind spots: {cd['n_blind_spot_domains']}/{results['n_held_out_domains']}",
        ]
    )

    return "\n".join(lines)


def _generate_macros(results: dict) -> str:
    cd = results["cross_domain"]
    rho = cd["spearman_rho_ao_vs_flip"]
    rho_str = f"{rho}" if isinstance(rho, (int, float)) else rho

    lines = [
        "",
        "% ---------------------------------------------------------------------------",
        "% EX-29: Held-Out Per-Domain Breakdown",
        "% ---------------------------------------------------------------------------",
        f"\\newcommand{{\\heldoutNDomainsEXXIX}}{{{results['n_held_out_domains']}}}",
        f"\\newcommand{{\\heldoutDomainFARange}}{{{cd['fa_range'][0]}--{cd['fa_range'][1]}}}",
        f"\\newcommand{{\\heldoutDomainFlipRange}}{{{cd['flip_range'][0]}--{cd['flip_range'][1]}}}",
        f"\\newcommand{{\\heldoutCrossDomainRho}}{{{rho_str}}}",
        f"\\newcommand{{\\heldoutAllDomainsBlindSpot}}{{{cd['n_blind_spot_domains']}/{results['n_held_out_domains']}}}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
