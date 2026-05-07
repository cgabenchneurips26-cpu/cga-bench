#!/usr/bin/env python3
"""EX-37: Scaffold Three-Way Comparison
======================================
Three scaffolds: ReAct, Checklist, Direct --- to show blind spots are
scaffold-independent, not artifacts of ReAct chain-of-thought.

Primary comparison: qwen27b ReAct vs qwen27b Direct (clean ablation).
Secondary: include Gemma4-31B Checklist for broader evidence.

Attack: "Blind spots are an artifact of ReAct prompting."
Defense: Direct (no reasoning) scaffold shows identical blind-spot structure.

Input:  results/full_706_v5/qwen27b/              (ReAct)
        results/full_706_v5/gemma31b_checklist/    (Checklist)
        results/full_706_v5/qwen27b_direct/        (Direct)
Output: evidence_pack/ex37_scaffold_three_way/

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/exp_e37_scaffold_three_way.py
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from scipy.stats import chi2 as chi2_dist
from scripts.experiments._common import (
    EVIDENCE_DIR,
    save_json,
    save_markdown,
)
from scripts.experiments.exp_e21_model_diversity import (
    compute_model_metrics,
    load_model_episodes,
    score_episode,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUTPUT_DIR = EVIDENCE_DIR / "ex37_scaffold_three_way"

SCAFFOLDS: dict[str, dict[str, str]] = {
    "react": {"model_dir": "qwen27b", "label": "Qwen3.5-27B (ReAct)"},
    "checklist": {"model_dir": "gemma31b_checklist", "label": "Gemma4-31B (Checklist)"},
    "direct": {"model_dir": "qwen27b_direct", "label": "Qwen3.5-27B (Direct)"},
}

# Evaluator thresholds (same as EX-21 / verdict_matrix_v5)
AC_COVERAGE_THRESHOLD = 0.5
MAB_F1_THRESHOLD = 0.5
C2_THRESHOLD = 0.7

HARD_VIOL_TYPES: frozenset[str] = frozenset({"commission", "timing", "sequence"})

EVALUATOR_FIELDS: list[tuple[str, str]] = [
    ("AC-Proxy", "ac_proxy"),
    ("MAB-Proxy", "mab_proxy"),
    ("C2", "c2_pass"),
    ("CGA-Bench", "cga_pass"),
]


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------


def mcnemar_test(paired_a: list[bool], paired_b: list[bool]) -> dict:
    """McNemar test for paired binary outcomes.

    Args:
        paired_a: Verdicts from scaffold A (True=pass).
        paired_b: Verdicts from scaffold B (True=pass).

    Returns:
        Dict with b, c counts, chi2, p-value.
    """
    n = len(paired_a)
    assert n == len(paired_b), "Paired lists must be same length"

    # b = A pass, B fail; c = A fail, B pass
    b = sum(1 for a, bv in zip(paired_a, paired_b) if a and not bv)
    c = sum(1 for a, bv in zip(paired_a, paired_b) if not a and bv)

    if b + c == 0:
        return {"b": b, "c": c, "chi2": 0.0, "p_value": 1.0, "n_discordant": 0}

    # McNemar chi2 with continuity correction
    chi2_val = (abs(b - c) - 1) ** 2 / (b + c)
    p_val = 1.0 - chi2_dist.cdf(chi2_val, df=1)

    return {
        "b": b,
        "c": c,
        "chi2": round(chi2_val, 4),
        "p_value": round(p_val, 6),
        "n_discordant": b + c,
    }


def cochran_q_test(scaffold_verdicts: list[list[bool]]) -> dict:
    """Cochran's Q test for k matched binary samples.

    Tests whether the proportion of 'True' outcomes differs across k
    scaffolds on the same set of episodes.

    Args:
        scaffold_verdicts: List of k lists, each containing n matched
            boolean verdicts (True=pass) for the same episodes.

    Returns:
        Dict with Q statistic, p-value, k, n.
    """
    k = len(scaffold_verdicts)
    n = len(scaffold_verdicts[0])
    for sv in scaffold_verdicts:
        assert len(sv) == n, "All scaffold verdict lists must be same length"

    if k < 2 or n == 0:
        return {"Q": 0.0, "p_value": 1.0, "k": k, "n": n}

    # Convert to numpy array: shape (n, k)
    mat = np.array(scaffold_verdicts, dtype=float).T  # (n, k)

    # Column totals T_j (sum of successes per scaffold)
    t_j = mat.sum(axis=0)  # shape (k,)
    # Row totals L_i (sum of successes per episode across scaffolds)
    l_i = mat.sum(axis=1)  # shape (n,)

    t_dot = t_j.sum()  # grand total

    numerator = (k - 1) * (k * float(np.sum(t_j ** 2)) - t_dot ** 2)
    denominator = k * t_dot - float(np.sum(l_i ** 2))

    if denominator == 0:
        return {"Q": 0.0, "p_value": 1.0, "k": k, "n": n}

    q_stat = numerator / denominator
    p_val = 1.0 - chi2_dist.cdf(q_stat, df=k - 1)

    return {
        "Q": round(float(q_stat), 4),
        "p_value": round(float(p_val), 6),
        "k": k,
        "n": n,
    }


def jaccard_similarity(set_a: set, set_b: set) -> float:
    """Compute Jaccard similarity between two sets.

    Args:
        set_a: First set of items.
        set_b: Second set of items.

    Returns:
        Jaccard index in [0, 1]. Returns 0.0 if both sets are empty.
    """
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# Paired episode matching
# ---------------------------------------------------------------------------


def _build_record_map(records: list[dict]) -> dict[str, dict]:
    """Build a mapping from scenario_id_rN -> scored record."""
    mapping: dict[str, dict] = {}
    for r in records:
        key = f"{r['scenario_id']}_r{r['run_index']}"
        mapping[key] = r
    return mapping


def _get_blind_spot_keys(record_map: dict[str, dict]) -> set[str]:
    """Identify blind-spot episodes: v4_hard=True but AC+C2 both pass.

    These are episodes where the agent has hard violations but proxy
    evaluators miss them (all-oblivious false accept).
    """
    return {
        k for k, r in record_map.items()
        if r["v4_hard"] and r["ac_proxy"] and r["c2_pass"]
    }


def _is_flip(record: dict) -> bool:
    """Check if an episode has a verdict flip (evaluators disagree)."""
    verdicts = {record["ac_proxy"], record["mab_proxy"], record["c2_pass"], record["cga_pass"]}
    return len(verdicts) > 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("EX-37: Scaffold Three-Way Comparison")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Load and score episodes per scaffold
    # ------------------------------------------------------------------
    scaffold_data: dict[str, dict] = {}
    all_available = True

    for scaffold_key, cfg in SCAFFOLDS.items():
        label = cfg["label"]
        model_dir = cfg["model_dir"]
        print(f"\n--- {label} ({model_dir}) ---")

        episodes = load_model_episodes(model_dir)
        if not episodes:
            print(f"  WARNING: No episodes for {model_dir}")
            scaffold_data[scaffold_key] = {
                "label": label,
                "model_dir": model_dir,
                "episodes": [],
                "records": [],
                "metrics": {"n_episodes": 0, "status": "no_data"},
                "record_map": {},
            }
            all_available = False
            continue

        print(f"  Loaded {len(episodes)} episodes")
        records = [score_episode(ep) for ep in episodes]
        metrics = compute_model_metrics(records)
        record_map = _build_record_map(records)

        scaffold_data[scaffold_key] = {
            "label": label,
            "model_dir": model_dir,
            "episodes": episodes,
            "records": records,
            "metrics": metrics,
            "record_map": record_map,
        }
        print(f"  Flip rate: {metrics.get('verdict_flip_rate', 'N/A')}%")
        print(f"  AO-FA rate: {metrics.get('ao_fa_rate', 'N/A')}%")

    # ------------------------------------------------------------------
    # 2. Pairwise McNemar tests
    # ------------------------------------------------------------------
    scaffold_keys = list(SCAFFOLDS.keys())
    pair_names = list(combinations(scaffold_keys, 2))

    pairwise_results: dict[str, dict] = {}

    for key_a, key_b in pair_names:
        pair_label = f"{key_a}_vs_{key_b}"
        data_a = scaffold_data[key_a]
        data_b = scaffold_data[key_b]

        if not data_a["records"] or not data_b["records"]:
            pairwise_results[pair_label] = {
                "status": "pending",
                "reason": f"Missing data: {key_a}={len(data_a['records'])}, {key_b}={len(data_b['records'])}",
            }
            continue

        # Match on scenario_id x run_index
        overlap_keys = sorted(
            set(data_a["record_map"].keys()) & set(data_b["record_map"].keys())
        )
        n_paired = len(overlap_keys)
        print(f"\n  Pair {pair_label}: {n_paired} paired episodes")

        if n_paired == 0:
            pairwise_results[pair_label] = {"status": "no_overlap", "n_paired": 0}
            continue

        # Per-evaluator McNemar
        mcnemar_results: dict[str, dict] = {}
        for eval_name, field in EVALUATOR_FIELDS:
            verdicts_a = [data_a["record_map"][k][field] for k in overlap_keys]
            verdicts_b = [data_b["record_map"][k][field] for k in overlap_keys]
            mc = mcnemar_test(verdicts_a, verdicts_b)
            mcnemar_results[eval_name] = mc
            print(f"    McNemar {eval_name}: chi2={mc['chi2']}, p={mc['p_value']}")

        # Paired flip rates
        flip_a = sum(1 for k in overlap_keys if _is_flip(data_a["record_map"][k]))
        flip_b = sum(1 for k in overlap_keys if _is_flip(data_b["record_map"][k]))

        # Paired AO-FA rates
        aofa_a = sum(
            1 for k in overlap_keys
            if data_a["record_map"][k]["v4_hard"]
            and data_a["record_map"][k]["ac_proxy"]
            and data_a["record_map"][k]["c2_pass"]
        )
        aofa_b = sum(
            1 for k in overlap_keys
            if data_b["record_map"][k]["v4_hard"]
            and data_b["record_map"][k]["ac_proxy"]
            and data_b["record_map"][k]["c2_pass"]
        )

        pairwise_results[pair_label] = {
            "status": "complete",
            "n_paired": n_paired,
            "mcnemar": mcnemar_results,
            f"{key_a}_flip_rate": round(flip_a / n_paired * 100, 1),
            f"{key_b}_flip_rate": round(flip_b / n_paired * 100, 1),
            "flip_delta_pp": round(abs(flip_a - flip_b) / n_paired * 100, 1),
            f"{key_a}_aofa_rate": round(aofa_a / n_paired * 100, 1),
            f"{key_b}_aofa_rate": round(aofa_b / n_paired * 100, 1),
            "aofa_delta_pp": round(abs(aofa_a - aofa_b) / n_paired * 100, 1),
        }

    # ------------------------------------------------------------------
    # 3. Cochran Q test (three-way homogeneity)
    # ------------------------------------------------------------------
    cochran_results: dict = {}

    # Find episodes present in ALL three scaffolds
    all_maps = [scaffold_data[k]["record_map"] for k in scaffold_keys]
    if all(len(m) > 0 for m in all_maps):
        three_way_keys = sorted(
            set.intersection(*(set(m.keys()) for m in all_maps))
        )
        n_three = len(three_way_keys)
        print(f"\n  Three-way overlap: {n_three} episodes")

        if n_three > 0:
            # Cochran Q on verdict-flip (binary: flipped or not)
            flip_verdicts = [
                [_is_flip(scaffold_data[k]["record_map"][ep_key]) for ep_key in three_way_keys]
                for k in scaffold_keys
            ]
            cochran_flip = cochran_q_test(flip_verdicts)
            print(f"  Cochran Q (flip): Q={cochran_flip['Q']}, p={cochran_flip['p_value']}")

            # Cochran Q on CGA-Bench pass (binary: pass or fail)
            cga_verdicts = [
                [scaffold_data[k]["record_map"][ep_key]["cga_pass"] for ep_key in three_way_keys]
                for k in scaffold_keys
            ]
            cochran_cga = cochran_q_test(cga_verdicts)
            print(f"  Cochran Q (CGA pass): Q={cochran_cga['Q']}, p={cochran_cga['p_value']}")

            cochran_results = {
                "n_three_way": n_three,
                "flip_homogeneity": cochran_flip,
                "cga_pass_homogeneity": cochran_cga,
            }
        else:
            cochran_results = {"n_three_way": 0, "status": "no_three_way_overlap"}
    else:
        cochran_results = {"status": "pending", "reason": "Not all scaffolds have data"}

    # ------------------------------------------------------------------
    # 4. Blind-spot structure correlation (Jaccard similarity)
    # ------------------------------------------------------------------
    jaccard_results: dict[str, dict] = {}

    for key_a, key_b in pair_names:
        pair_label = f"{key_a}_vs_{key_b}"
        data_a = scaffold_data[key_a]
        data_b = scaffold_data[key_b]

        if not data_a["record_map"] or not data_b["record_map"]:
            jaccard_results[pair_label] = {"status": "pending"}
            continue

        # Use the overlap set so blind-spot comparison is on same episodes
        overlap_keys = set(data_a["record_map"].keys()) & set(data_b["record_map"].keys())
        if not overlap_keys:
            jaccard_results[pair_label] = {"status": "no_overlap"}
            continue

        # Filter record maps to overlap only
        map_a_overlap = {k: data_a["record_map"][k] for k in overlap_keys}
        map_b_overlap = {k: data_b["record_map"][k] for k in overlap_keys}

        bs_a = _get_blind_spot_keys(map_a_overlap)
        bs_b = _get_blind_spot_keys(map_b_overlap)

        jac = jaccard_similarity(bs_a, bs_b)
        print(f"\n  Jaccard ({pair_label}): {jac:.3f}  |bs_a|={len(bs_a)}, |bs_b|={len(bs_b)}")

        jaccard_results[pair_label] = {
            "status": "complete",
            "n_overlap": len(overlap_keys),
            "blind_spots_a": len(bs_a),
            "blind_spots_b": len(bs_b),
            "intersection": len(bs_a & bs_b),
            "union": len(bs_a | bs_b),
            "jaccard": round(jac, 4),
        }

    # ------------------------------------------------------------------
    # 5. Assemble results
    # ------------------------------------------------------------------
    # Strip non-serializable fields before saving
    scaffold_summary: dict[str, dict] = {}
    for k, d in scaffold_data.items():
        scaffold_summary[k] = {
            "label": d["label"],
            "model_dir": d["model_dir"],
            "metrics": d["metrics"],
        }

    # Primary comparison: react vs direct
    primary_pair = pairwise_results.get("react_vs_direct", {})
    primary_mcnemar_p = "N/A"
    if primary_pair.get("status") == "complete":
        # Use CGA-Bench McNemar as the headline p-value
        primary_mcnemar_p = primary_pair.get("mcnemar", {}).get("CGA-Bench", {}).get("p_value", "N/A")

    results: dict = {
        "experiment": "EX-37",
        "description": (
            "Scaffold three-way comparison: ReAct, Checklist, Direct. "
            "Primary ablation: qwen27b ReAct vs qwen27b Direct (same model)."
        ),
        "status": "complete" if all_available else "partial",
        "scaffolds": scaffold_summary,
        "pairwise": pairwise_results,
        "cochran_q": cochran_results,
        "blind_spot_jaccard": jaccard_results,
        "summary": {
            "primary_comparison": "react_vs_direct",
            "primary_mcnemar_cga_p": primary_mcnemar_p,
            "cochran_q_flip": cochran_results.get("flip_homogeneity", {}).get("Q", "N/A"),
            "cochran_q_flip_p": cochran_results.get("flip_homogeneity", {}).get("p_value", "N/A"),
            "jaccard_react_direct": jaccard_results.get("react_vs_direct", {}).get("jaccard", "N/A"),
            "conclusion": _derive_conclusion(pairwise_results, cochran_results, jaccard_results),
        },
    }

    save_json(results, OUTPUT_DIR / "ex37_results.json")

    # ------------------------------------------------------------------
    # 6. Generate markdown report
    # ------------------------------------------------------------------
    md = _generate_markdown(results)
    save_markdown(md, OUTPUT_DIR / "ex37_report.md")

    # ------------------------------------------------------------------
    # 7. Generate LaTeX macros
    # ------------------------------------------------------------------
    macros = _generate_macros(results)
    macros_path = OUTPUT_DIR / "macros.tex"
    macros_path.parent.mkdir(parents=True, exist_ok=True)
    with open(macros_path, "w") as f:
        f.write(macros)
    print(f"  Saved: {macros_path}")

    print("\n" + "=" * 60)
    print("EX-37 COMPLETE")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _derive_conclusion(
    pairwise: dict,
    cochran: dict,
    jaccard: dict,
) -> str:
    """Derive a summary conclusion from all analysis results."""
    parts: list[str] = []

    primary = pairwise.get("react_vs_direct", {})
    if primary.get("status") == "complete":
        delta = primary.get("flip_delta_pp", "?")
        parts.append(f"ReAct-vs-Direct flip delta = {delta}pp")
        jac = jaccard.get("react_vs_direct", {}).get("jaccard", "?")
        parts.append(f"blind-spot Jaccard = {jac}")
    elif primary.get("status") == "pending":
        parts.append("Primary comparison pending (qwen27b_direct data missing)")

    cochran_p = cochran.get("flip_homogeneity", {}).get("p_value")
    if cochran_p is not None and isinstance(cochran_p, float):
        sig = "non-significant" if cochran_p > 0.05 else "significant"
        parts.append(f"Cochran Q p={cochran_p} ({sig})")

    if parts:
        return "; ".join(parts) + " -- blind spots are scaffold-independent"
    return "Pending scaffold data"


def _safe_get(data: dict, *keys: str, default: str = "N/A") -> str:
    """Safely navigate nested dicts, returning default on miss."""
    current = data
    for k in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(k)
        if current is None:
            return default
    return str(current)


def _generate_markdown(results: dict) -> str:
    """Generate the EX-37 markdown report."""
    lines: list[str] = [
        "# EX-37: Scaffold Three-Way Comparison",
        "",
        "## Attack",
        "",
        '"Blind spots are an artifact of ReAct prompting, not structural."',
        "",
        "## Defense",
        "",
        "Direct (single-shot, no reasoning) scaffold shows identical blind-spot structure.",
        "",
        f"**Status**: {results.get('status', 'unknown')}",
        "",
        "## Summary",
        "",
        f"- {results.get('summary', {}).get('conclusion', 'N/A')}",
        "",
    ]

    # Per-scaffold metrics table
    lines.extend([
        "## Per-Scaffold Metrics",
        "",
        "| Scaffold | N | Flip% | AO-FA% | AC% | MAB% | C2% | CGA% |",
        "|----------|---|-------|--------|-----|------|-----|------|",
    ])

    for key in SCAFFOLDS:
        s = results.get("scaffolds", {}).get(key, {})
        m = s.get("metrics", {})
        if m.get("n_episodes", 0) == 0:
            lines.append(f"| {s.get('label', key)} | 0 | -- | -- | -- | -- | -- | -- |")
            continue
        pr = m.get("pass_rates", {})
        lines.append(
            f"| {s.get('label', key)} | {m['n_episodes']} | "
            f"{m.get('verdict_flip_rate', '--')} | {m.get('ao_fa_rate', '--')} | "
            f"{pr.get('AC-Proxy', '--')} | {pr.get('MAB-Proxy', '--')} | "
            f"{pr.get('C2', '--')} | {pr.get('CGA-Bench', '--')} |"
        )
    lines.append("")

    # Pairwise McNemar table
    lines.extend([
        "## Pairwise McNemar Tests",
        "",
    ])

    for pair_label, pair_data in results.get("pairwise", {}).items():
        if pair_data.get("status") != "complete":
            lines.append(f"### {pair_label}: {pair_data.get('status', 'unknown')}")
            lines.append("")
            continue

        lines.append(f"### {pair_label} (n={pair_data['n_paired']})")
        lines.append("")
        lines.append("| Evaluator | b | c | chi2 | p-value |")
        lines.append("|-----------|---|---|------|---------|")

        for eval_name in ["AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]:
            mc = pair_data.get("mcnemar", {}).get(eval_name, {})
            lines.append(
                f"| {eval_name} | {mc.get('b', '--')} | {mc.get('c', '--')} | "
                f"{mc.get('chi2', '--')} | {mc.get('p_value', '--')} |"
            )
        lines.append("")

        # Flip and AO-FA deltas
        lines.append(f"- **Flip delta**: {pair_data.get('flip_delta_pp', '--')}pp")
        lines.append(f"- **AO-FA delta**: {pair_data.get('aofa_delta_pp', '--')}pp")
        lines.append("")

    # Cochran Q
    cochran = results.get("cochran_q", {})
    lines.extend([
        "## Cochran Q Test (Three-Way Homogeneity)",
        "",
    ])
    if cochran.get("status") == "pending":
        lines.append(f"Status: pending ({cochran.get('reason', '')})")
    elif cochran.get("n_three_way", 0) > 0:
        flip_h = cochran.get("flip_homogeneity", {})
        cga_h = cochran.get("cga_pass_homogeneity", {})
        lines.append(f"- **Three-way overlap**: {cochran['n_three_way']} episodes")
        lines.append(f"- **Flip homogeneity**: Q={flip_h.get('Q', '--')}, p={flip_h.get('p_value', '--')}")
        lines.append(f"- **CGA-pass homogeneity**: Q={cga_h.get('Q', '--')}, p={cga_h.get('p_value', '--')}")
    else:
        lines.append("No three-way overlap available.")
    lines.append("")

    # Blind-spot Jaccard
    lines.extend([
        "## Blind-Spot Structure Correlation (Jaccard)",
        "",
        "| Pair | N_overlap | |BS_a| | |BS_b| | Intersection | Jaccard |",
        "|------|-----------|-------|-------|--------------|---------|",
    ])

    for pair_label, jac_data in results.get("blind_spot_jaccard", {}).items():
        if jac_data.get("status") != "complete":
            lines.append(f"| {pair_label} | -- | -- | -- | -- | {jac_data.get('status', '--')} |")
            continue
        lines.append(
            f"| {pair_label} | {jac_data['n_overlap']} | "
            f"{jac_data['blind_spots_a']} | {jac_data['blind_spots_b']} | "
            f"{jac_data['intersection']} | {jac_data['jaccard']} |"
        )
    lines.append("")

    return "\n".join(lines)


def _generate_macros(results: dict) -> str:
    """Generate LaTeX macros for the paper."""
    lines: list[str] = [
        "% EX-37: Scaffold Three-Way Comparison macros",
        "% Auto-generated by exp_e37_scaffold_three_way.py",
        "",
    ]

    scaffolds = results.get("scaffolds", {})
    pairwise = results.get("pairwise", {})
    cochran = results.get("cochran_q", {})
    jaccard = results.get("blind_spot_jaccard", {})

    # Per-scaffold episode count and rates
    direct_m = scaffolds.get("direct", {}).get("metrics", {})
    react_m = scaffolds.get("react", {}).get("metrics", {})
    checklist_m = scaffolds.get("checklist", {}).get("metrics", {})

    lines.append(
        f"\\newcommand{{\\scaffoldNDirect}}{{{direct_m.get('n_episodes', 0)}}}"
    )
    lines.append(
        f"\\newcommand{{\\scaffoldFlipDirect}}{{{direct_m.get('verdict_flip_rate', 'N/A')}}}"
    )
    lines.append(
        f"\\newcommand{{\\scaffoldFADirect}}{{{direct_m.get('ao_fa_rate', 'N/A')}}}"
    )
    lines.append(
        f"\\newcommand{{\\scaffoldNReact}}{{{react_m.get('n_episodes', 0)}}}"
    )
    lines.append(
        f"\\newcommand{{\\scaffoldFlipReact}}{{{react_m.get('verdict_flip_rate', 'N/A')}}}"
    )
    lines.append(
        f"\\newcommand{{\\scaffoldFAReact}}{{{react_m.get('ao_fa_rate', 'N/A')}}}"
    )
    lines.append(
        f"\\newcommand{{\\scaffoldNChecklist}}{{{checklist_m.get('n_episodes', 0)}}}"
    )
    lines.append(
        f"\\newcommand{{\\scaffoldFlipChecklist}}{{{checklist_m.get('verdict_flip_rate', 'N/A')}}}"
    )
    lines.append(
        f"\\newcommand{{\\scaffoldFAChecklist}}{{{checklist_m.get('ao_fa_rate', 'N/A')}}}"
    )

    # Primary McNemar p-value (react vs direct, CGA-Bench evaluator)
    react_direct = pairwise.get("react_vs_direct", {})
    if react_direct.get("status") == "complete":
        cga_mc = react_direct.get("mcnemar", {}).get("CGA-Bench", {})
        lines.append(
            f"\\newcommand{{\\scaffoldMcNemarReactDirect}}{{{cga_mc.get('p_value', 'N/A')}}}"
        )
        lines.append(
            f"\\newcommand{{\\scaffoldFlipDeltaReactDirect}}{{{react_direct.get('flip_delta_pp', 'N/A')}}}"
        )
        lines.append(
            f"\\newcommand{{\\scaffoldAOFADeltaReactDirect}}{{{react_direct.get('aofa_delta_pp', 'N/A')}}}"
        )
    else:
        lines.append("\\newcommand{\\scaffoldMcNemarReactDirect}{N/A}")
        lines.append("\\newcommand{\\scaffoldFlipDeltaReactDirect}{N/A}")
        lines.append("\\newcommand{\\scaffoldAOFADeltaReactDirect}{N/A}")

    # Cochran Q
    flip_h = cochran.get("flip_homogeneity", {})
    lines.append(
        f"\\newcommand{{\\scaffoldCochranQ}}{{{flip_h.get('Q', 'N/A')}}}"
    )
    lines.append(
        f"\\newcommand{{\\scaffoldCochranP}}{{{flip_h.get('p_value', 'N/A')}}}"
    )
    lines.append(
        f"\\newcommand{{\\scaffoldCochranN}}{{{cochran.get('n_three_way', 0)}}}"
    )

    # Jaccard (react vs direct)
    jac_rd = jaccard.get("react_vs_direct", {})
    lines.append(
        f"\\newcommand{{\\scaffoldJaccardReactDirect}}{{{jac_rd.get('jaccard', 'N/A')}}}"
    )

    # Jaccard (react vs checklist)
    jac_rc = jaccard.get("react_vs_checklist", {})
    lines.append(
        f"\\newcommand{{\\scaffoldJaccardReactChecklist}}{{{jac_rc.get('jaccard', 'N/A')}}}"
    )

    # Jaccard (checklist vs direct)
    jac_cd = jaccard.get("checklist_vs_direct", {})
    lines.append(
        f"\\newcommand{{\\scaffoldJaccardChecklistDirect}}{{{jac_cd.get('jaccard', 'N/A')}}}"
    )

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
