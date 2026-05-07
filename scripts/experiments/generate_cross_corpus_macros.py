#!/usr/bin/env python3
"""Generate paper/auto_numbers_cross_corpus.tex reproducibly from source JSONs.

Modes:
  Default: generate paper/auto_numbers_cross_corpus.tex (overwrite)
  --verify: compare generated output against existing file, report discrepancies
  --dry-run: print stats without writing

Usage:
    PYTHONPATH=. python scripts/experiments/generate_cross_corpus_macros.py
    PYTHONPATH=. python scripts/experiments/generate_cross_corpus_macros.py --verify
    PYTHONPATH=. python scripts/experiments/generate_cross_corpus_macros.py --dry-run
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence_pack" / "analysis"
OUTPUT = ROOT / "paper" / "auto_numbers_cross_corpus.tex"

V73_RESULTS = ROOT / "results" / "v73_full_with_allmh"
V6_RESULTS = ROOT / "results" / "full_v6a_706"
V6B_RESULTS = ROOT / "results" / "full_v6b"

V73_CGA_PATH = EVIDENCE / "cga_s_clean_v7_3_sgsc.json"
V6_CGA_PATH = EVIDENCE / "cga_s_clean_v6_706_manual.json"
V6B_CGA_PATH = EVIDENCE / "cga_s_clean_v6_phase_b.json"
V73_VERDICT_PATH = EVIDENCE / "verdict_matrix_v7_3_with_allmh_typed_mandfix.json"
V6_VERDICT_PATH = EVIDENCE / "verdict_matrix_v6_706_with_allmh_typed_mandfix.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODEL_TEX: dict[str, str] = {
    "nemotron30b": "Nemo",
    "qwen27b": "Qtwentyseven",
    "qwen35b": "Qthirtyfive",
    "qwen4b": "Qfour",
    "qwen397b": "Qthreenine",
    "gemma31b": "Gemma",
    "llama4scout": "Llama",
    "oss120b": "OSS",
    "allm_h": "ALLMH",
    "deepseek_r1_7b": "DS",
}

MODELS_10: list[str] = sorted(MODEL_TEX)
MODELS_9_V6B: list[str] = [m for m in MODELS_10 if m != "llama4scout"]

N_RUNS = 3
BB_HF_SCENARIOS_V73 = 23
BB_HF_EPISODES_V73 = BB_HF_SCENARIOS_V73 * N_RUNS  # 69
BB_HF_SCENARIOS_V6B = 9
BB_HF_EPISODES_V6B = BB_HF_SCENARIOS_V6B * N_RUNS  # 27

# Models excluded from BB balanced accuracy (not in V6b or no data)
BB_BA_EXCLUDE = {"llama4scout", "allm_h"}

# BB-mandatory V6b scenario IDs (9 total: 8 initiate + 1 bradycardia)
BB_V6B_INITIATE_SIDS: frozenset[str] = frozenset(
    {
        "aha_he_pathway_hfref_classific_adhf_management_adhf_warm_wet_adhf_cold_wet_",
        "aha_he_pathway_hfref_classific_adhf_warm_wet_adhf_cold_wet_adhf_cold_dry_di",
        "aha_he_pathway_hfref_classific_device_therapy__adhf_warm_wet_adhf_cold_wet_",
        "aha_heart_fa_pathway_adhf_warm_wet",
        "aha_heart_fa_pathway_cardiogenic_shock",
        "aha_heart_fa_pathway_hfref_stable",
        "hfref_hyperkalemia_arni_trap",
        "hfref_new_diagnosis",
    }
)
BB_V6B_BRADY_SID = "hfref_bradycardia_bb_trap"
BB_V6B_ALL_SIDS: frozenset[str] = BB_V6B_INITIATE_SIDS | {BB_V6B_BRADY_SID}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def emit(name: str, value: str) -> str:
    r"""Emit a \providecommand line."""
    return f"\\providecommand{{\\{name}}}{{{value}}}"


def fmt_s(v: float) -> str:
    """Format as .3f score."""
    return f"{v:.3f}"


def fmt_pct(v: float) -> str:
    """Format as .1f percentage."""
    return f"{v:.1f}"


def fmt_delta(v: float) -> str:
    """Format as +.3f delta."""
    return f"{v:+.3f}"


def fmt_2f(v: float) -> str:
    """Format as .2f."""
    return f"{v:.2f}"


def spearman(x: list[float], y: list[float]) -> float:
    """Spearman rank correlation (no-tie version matching compute_cga_s_clean.py)."""
    n = len(x)
    if n < 2:
        return 0.0
    rx = {v: i + 1 for i, v in enumerate(sorted(x, reverse=True))}
    ry = {v: i + 1 for i, v in enumerate(sorted(y, reverse=True))}
    d2 = sum((rx[xi] - ry[yi]) ** 2 for xi, yi in zip(x, y, strict=True))
    return 1 - 6 * d2 / (n * (n * n - 1))


def rank_desc(values: dict[str, float]) -> dict[str, int]:
    """Rank models descending (highest value = rank 1)."""
    ordered = sorted(values, key=lambda m: values[m], reverse=True)
    return {m: i + 1 for i, m in enumerate(ordered)}


def rank_asc(values: dict[str, float]) -> dict[str, int]:
    """Rank models ascending (lowest value = rank 1)."""
    ordered = sorted(values, key=lambda m: values[m])
    return {m: i + 1 for i, m in enumerate(ordered)}


def sorted_models_desc(
    values: dict[str, float],
    models: list[str] | None = None,
) -> list[str]:
    """Return models sorted by value descending (best first for higher-is-better)."""
    pool = models or list(values)
    return sorted(pool, key=lambda m: values.get(m, 0), reverse=True)


def sorted_models_asc(
    values: dict[str, float],
    models: list[str] | None = None,
) -> list[str]:
    """Return models sorted by value ascending (best first for lower-is-better)."""
    pool = models or list(values)
    return sorted(pool, key=lambda m: values.get(m, 0))


def load_json(path: Path) -> dict:
    """Load JSON file."""
    with open(path) as f:
        return json.load(f)


def is_hf_scenario(scenario_id: str) -> bool:
    """Check if scenario belongs to heart failure domain (BB case study)."""
    sid = scenario_id.lower()
    return "heart_fail" in sid or "cardiogenic" in sid


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_cga_clean() -> tuple[dict, dict, dict]:
    """Load the 3 CGA-S clean JSONs."""
    return load_json(V73_CGA_PATH), load_json(V6_CGA_PATH), load_json(V6B_CGA_PATH)


def load_verdict_matrices() -> tuple[dict, dict]:
    """Load V73 and V6 verdict matrices."""
    return load_json(V73_VERDICT_PATH), load_json(V6_VERDICT_PATH)


def load_raw_episodes(
    results_dir: Path,
    models: list[str],
) -> dict[str, list[dict]]:
    """Load raw episode JSONs. Returns {model: [episodes]}."""
    out: dict[str, list[dict]] = {m: [] for m in models}
    for mdl in models:
        mdl_dir = results_dir / mdl
        if not mdl_dir.exists():
            continue
        for jp in mdl_dir.glob("*.json"):
            if jp.name.startswith(("_", ".")):
                continue
            try:
                with open(jp) as f:
                    ep = json.load(f)
                if "scenario_id" in ep and "run_index" in ep:
                    out[mdl].append(ep)
            except (json.JSONDecodeError, OSError):
                continue
    return out


def load_hf_episodes_v6b(models: list[str]) -> dict[str, list[dict]]:
    """Load BB-mandatory HF episodes from V6b by scenario_id matching."""
    out: dict[str, list[dict]] = {m: [] for m in models}
    for mdl in models:
        mdl_dir = V6B_RESULTS / mdl
        if not mdl_dir.exists():
            continue
        for jp in mdl_dir.glob("*.json"):
            if jp.name.startswith(("_", ".")):
                continue
            try:
                with open(jp) as f:
                    ep = json.load(f)
                sid = ep.get("scenario_id", "")
                if sid in BB_V6B_ALL_SIDS:
                    out[mdl].append(ep)
            except (json.JSONDecodeError, OSError):
                continue
    return out


def load_hf_episodes_v73(models: list[str]) -> dict[str, list[dict]]:
    """Load HF episodes from V73 (for BB commission case study)."""
    out: dict[str, list[dict]] = {m: [] for m in models}
    for mdl in models:
        mdl_dir = V73_RESULTS / mdl
        if not mdl_dir.exists():
            continue
        for jp in list(mdl_dir.glob("*heart_fail*")) + list(mdl_dir.glob("*cardiogenic*")):
            try:
                with open(jp) as f:
                    ep = json.load(f)
                if "scenario_id" in ep:
                    out[mdl].append(ep)
            except (json.JSONDecodeError, OSError):
                continue
    return out


# ---------------------------------------------------------------------------
# Section 1: Corpus-Level Summary
# ---------------------------------------------------------------------------
def section_1(v73_meta: dict, v6_meta: dict) -> list[str]:
    """Generate Section 1 macros."""
    n_scen_v73 = v73_meta["n_per_model"] // N_RUNS
    n_scen_v6 = v6_meta["n_per_model"] // N_RUNS
    return [
        "% =========================================================",
        "%  Section 1: Corpus-Level Summary",
        "% =========================================================",
        "",
        emit("crossNModels", str(v73_meta["n_models"])),
        emit("crossVSevenNScen", str(n_scen_v73)),
        emit("crossVSevenNEps", f"{v73_meta['n_total']:,}".replace(",", "{,}")),
        emit("crossVSixNScen", str(n_scen_v6)),
        emit("crossVSixNEps", f"{v6_meta['n_total']:,}".replace(",", "{,}")),
        emit("crossNRuns", str(N_RUNS)),
    ]


# ---------------------------------------------------------------------------
# Sections 2-7: CGA-S, TCC, CwT, Gate, Pass — from cga_s_clean JSONs
# ---------------------------------------------------------------------------
def _per_model_metric(
    v73_pm: dict,
    v6_pm: dict,
    field: str,
    prefix_v7: str,
    prefix_v6: str,
    fmt_fn: callable,
    *,
    delta_prefix: str = "",
    higher_is_better: bool = True,
) -> list[str]:
    """Generic per-model metric section with optional deltas."""
    v73_vals = {m: v73_pm[m][field] for m in MODELS_10 if m in v73_pm}
    v6_vals = {m: v6_pm[m][field] for m in MODELS_10 if m in v6_pm}

    sort_fn = sorted_models_desc if higher_is_better else sorted_models_asc

    lines: list[str] = []
    # V73 values
    for m in sort_fn(v73_vals, MODELS_10):
        lines.append(emit(f"{prefix_v7}{MODEL_TEX[m]}", fmt_fn(v73_vals[m])))
    lines.append("")

    # V6 values
    for m in sort_fn(v6_vals, MODELS_10):
        lines.append(emit(f"{prefix_v6}{MODEL_TEX[m]}", fmt_fn(v6_vals[m])))

    # Deltas (V73 - V6, ordered by V73 rank)
    if delta_prefix:
        lines.append("")
        for m in sort_fn(v73_vals, MODELS_10):
            if m in v73_vals and m in v6_vals:
                delta = v73_vals[m] - v6_vals[m]
                lines.append(emit(f"{delta_prefix}{MODEL_TEX[m]}", fmt_delta(delta)))

    return lines


def _rank_section(
    v73_pm: dict,
    v6_pm: dict,
    field: str,
    prefix_v7: str,
    prefix_v6: str,
    *,
    higher_is_better: bool = True,
) -> list[str]:
    """Generate rank macros for a metric."""
    v73_vals = {m: v73_pm[m][field] for m in MODELS_10 if m in v73_pm}
    v6_vals = {m: v6_pm[m][field] for m in MODELS_10 if m in v6_pm}

    rank_fn = rank_desc if higher_is_better else rank_asc
    v73_ranks = rank_fn(v73_vals)
    v6_ranks = rank_fn(v6_vals)

    sort_fn = sorted_models_desc if higher_is_better else sorted_models_asc

    lines: list[str] = []
    for m in sort_fn(v73_vals, MODELS_10):
        lines.append(emit(f"{prefix_v7}{MODEL_TEX[m]}", str(v73_ranks[m])))
    lines.append("")
    for m in sort_fn(v6_vals, MODELS_10):
        lines.append(emit(f"{prefix_v6}{MODEL_TEX[m]}", str(v6_ranks[m])))
    return lines


def section_2(v73_pm: dict, v6_pm: dict) -> list[str]:
    """Section 2: CGA-S per model."""
    header = [
        "% =========================================================",
        "%  Section 2: CGA-S (Clean, A3 design) — Per Model",
        "% =========================================================",
        "",
        "% --- V73 SGSC CGA-S ---",
    ]
    body = _per_model_metric(
        v73_pm,
        v6_pm,
        "cga_s_mean",
        "crossVSevenCGA",
        "crossVSixCGA",
        fmt_s,
        delta_prefix="crossDeltaCGA",
    )
    # Insert comment before V6 block and delta block
    result: list[str] = header
    v73_end = body.index("")
    result.extend(body[:v73_end])
    result.append("")
    result.append("% --- V6 706 CGA-S ---")
    rest = body[v73_end + 1 :]
    if "" in rest:
        v6_end = rest.index("")
        result.extend(rest[:v6_end])
        result.append("")
        result.append("% --- CGA-S Delta (V73 - V6) ---")
        result.extend(rest[v6_end + 1 :])
    else:
        result.extend(rest)
    return result


def section_3(v73_pm: dict, v6_pm: dict) -> list[str]:
    """Section 3: CGA-S Ranks."""
    header = [
        "% =========================================================",
        "%  Section 3: CGA-S Ranks",
        "% =========================================================",
        "",
        "% --- V73 CGA-S Rank (1=best) ---",
    ]
    body = _rank_section(
        v73_pm,
        v6_pm,
        "cga_s_mean",
        "crossVSevenRankCGA",
        "crossVSixRankCGA",
    )
    result = header + body[:10]  # V73 ranks
    result.append("")
    result.append("% --- V6 CGA-S Rank (1=best) ---")
    result.extend(body[11:])  # skip blank, add V6 ranks
    return result


def _metric_section_full(
    v73_pm: dict,
    v6_pm: dict,
    field: str,
    section_num: int,
    title: str,
    prefix_v7: str,
    prefix_v6: str,
    fmt_fn: callable,
    delta_prefix: str,
    rank_prefix_v7: str,
    rank_prefix_v6: str,
    label_v7: str,
    label_v6: str,
    label_delta: str,
    label_rank_v7: str,
    label_rank_v6: str,
    *,
    higher_is_better: bool = True,
) -> list[str]:
    """Full metric section: values + deltas + ranks."""
    lines = [
        "% =========================================================",
        f"%  Section {section_num}: {title}",
        "% =========================================================",
        "",
        f"% --- {label_v7} ---",
    ]

    metric = _per_model_metric(
        v73_pm,
        v6_pm,
        field,
        prefix_v7,
        prefix_v6,
        fmt_fn,
        delta_prefix=delta_prefix,
        higher_is_better=higher_is_better,
    )
    ranks = _rank_section(
        v73_pm,
        v6_pm,
        field,
        rank_prefix_v7,
        rank_prefix_v6,
        higher_is_better=higher_is_better,
    )

    # Split metric into v73 / v6 / delta blocks
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in metric:
        if line == "":
            blocks.append(current)
            current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)

    lines.extend(blocks[0])  # V73 values
    lines.append("")
    lines.append(f"% --- {label_v6} ---")
    if len(blocks) > 1:
        lines.extend(blocks[1])  # V6 values
    if len(blocks) > 2:
        lines.append("")
        lines.append(f"% --- {label_delta} ---")
        lines.extend(blocks[2])  # deltas

    # Ranks
    rank_blocks: list[list[str]] = []
    current = []
    for line in ranks:
        if line == "":
            rank_blocks.append(current)
            current = []
        else:
            current.append(line)
    if current:
        rank_blocks.append(current)

    lines.append("")
    lines.append(f"% --- {label_rank_v7} ---")
    lines.extend(rank_blocks[0])
    if len(rank_blocks) > 1:
        lines.append("")
        lines.append(f"% --- {label_rank_v6} ---")
        lines.extend(rank_blocks[1])

    return lines


def section_4(v73_pm: dict, v6_pm: dict) -> list[str]:
    """Section 4: TCC."""
    return _metric_section_full(
        v73_pm,
        v6_pm,
        "tcc",
        4,
        "TCC (Temporal Compliance Category)",
        "crossVSevenTCC",
        "crossVSixTCC",
        fmt_s,
        "crossDeltaTCC",
        "crossVSevenRankTCC",
        "crossVSixRankTCC",
        "V73 TCC",
        "V6 TCC",
        "TCC Delta (V73 - V6)",
        "V73 TCC Rank",
        "V6 TCC Rank",
    )


def section_5(v73_pm: dict, v6_pm: dict) -> list[str]:
    """Section 5: CwT."""
    return _metric_section_full(
        v73_pm,
        v6_pm,
        "cwt",
        5,
        "CwT (Compliance without Type — excludes DEVIATION)",
        "crossVSevenCwT",
        "crossVSixCwT",
        fmt_s,
        "crossDeltaCwT",
        "crossVSevenRankCwT",
        "crossVSixRankCwT",
        "V73 CwT",
        "V6 CwT",
        "CwT Delta (V73 - V6)",
        "V73 CwT Rank",
        "V6 CwT Rank",
    )


def section_6(v73_pm: dict, v6_pm: dict) -> list[str]:
    """Section 6: Safety Gate Failure Rate."""
    lines = [
        "% =========================================================",
        "%  Section 6: Safety Gate Failure Rate (compliance_score < 0.5)",
        "% =========================================================",
        "",
        "% --- V73 Gate Fail ---",
    ]
    v73_vals = {m: v73_pm[m]["gate_fail"] * 100 for m in MODELS_10 if m in v73_pm}
    v6_vals = {m: v6_pm[m]["gate_fail"] * 100 for m in MODELS_10 if m in v6_pm}

    for m in sorted_models_asc(v73_vals, MODELS_10):
        lines.append(emit(f"crossVSevenGate{MODEL_TEX[m]}", fmt_pct(v73_vals[m])))
    lines.append("")
    lines.append("% --- V6 Gate Fail ---")
    for m in sorted_models_asc(v6_vals, MODELS_10):
        lines.append(emit(f"crossVSixGate{MODEL_TEX[m]}", fmt_pct(v6_vals[m])))
    return lines


def section_7(v73_pm: dict, v6_pm: dict) -> list[str]:
    """Section 7: Pass Rate >= 0.7."""
    lines = [
        "% =========================================================",
        "%  Section 7: Pass Rate >= 0.7",
        "% =========================================================",
        "",
        "% --- V73 Pass>=0.7 ---",
    ]
    v73_vals = {m: v73_pm[m]["pass_7"] * 100 for m in MODELS_10 if m in v73_pm}
    v6_vals = {m: v6_pm[m]["pass_7"] * 100 for m in MODELS_10 if m in v6_pm}

    for m in sorted_models_desc(v73_vals, MODELS_10):
        lines.append(emit(f"crossVSevenPass{MODEL_TEX[m]}", fmt_pct(v73_vals[m])))
    lines.append("")
    lines.append("% --- V6 Pass>=0.7 ---")
    for m in sorted_models_desc(v6_vals, MODELS_10):
        lines.append(emit(f"crossVSixPass{MODEL_TEX[m]}", fmt_pct(v6_vals[m])))
    return lines


# ---------------------------------------------------------------------------
# Section 8: Evaluator Pass Rates — from verdict matrix per_model
# ---------------------------------------------------------------------------
def section_8(v73_vm: dict, v6_vm: dict) -> list[str]:
    """Section 8: AC, MAB, C2 pass rates."""
    lines = [
        "% =========================================================",
        "%  Section 8: Evaluator Pass Rates (AC>=0.5, MAB>=0.5, C2>=0.7)",
        "% =========================================================",
    ]
    v73_pm = v73_vm["per_model"]
    v6_pm = v6_vm["per_model"]

    for metric, prefix, label in [
        ("ac_pass_rate", "AC", "AC Pass Rate"),
        ("mab_pass_rate", "MAB", "MAB Pass Rate"),
        ("c2_pass_rate", "CTwo", "C2>=0.7 Pass Rate"),
    ]:
        v73_vals = {m: v73_pm[m][metric] * 100 for m in MODELS_10 if m in v73_pm}
        v6_vals = {m: v6_pm[m][metric] * 100 for m in MODELS_10 if m in v6_pm}

        lines.append("")
        lines.append(f"% --- V73 {label} ---")
        for m in sorted_models_asc(v73_vals, MODELS_10):
            lines.append(emit(f"crossVSeven{prefix}{MODEL_TEX[m]}", fmt_pct(v73_vals[m])))

        lines.append("")
        lines.append(f"% --- V6 {label} ---")
        for m in sorted_models_asc(v6_vals, MODELS_10):
            lines.append(emit(f"crossVSix{prefix}{MODEL_TEX[m]}", fmt_pct(v6_vals[m])))

    return lines


# ---------------------------------------------------------------------------
# Section 9: Sub-Construct Scores (C1-C5) — from raw episodes
# ---------------------------------------------------------------------------
def section_9(
    v73_episodes: dict[str, list[dict]],
    v6_episodes: dict[str, list[dict]],
) -> list[str]:
    """Section 9: C1-C5 sub-scores from raw episodes (unbalanced)."""
    lines = [
        "% =========================================================",
        "%  Section 9: Sub-Construct Scores (C1-C5) — Raw Means",
        "% =========================================================",
    ]

    sub_keys = [
        ("C1_path_selection", "COne", "C1 Path Selection"),
        ("C2_mandatory_completion", "CTwoMean", "C2 Mandatory Completion"),
        ("C3_forbidden_avoidance", "CThree", "C3 Forbidden Avoidance"),
        ("C4_timing_compliance", "CFour", "C4 Timing Compliance"),
        ("C5_sequence_integrity", "CFive", "C5 Sequence Integrity"),
    ]

    for sk, macro_infix, label in sub_keys:
        lines.append("")
        lines.append(f"% --- {label} ---")

        for _corpus_tag, prefix, episodes in [
            ("V73", "crossVSeven", v73_episodes),
            ("V6", "crossVSix", v6_episodes),
        ]:
            vals: dict[str, float] = {}
            for m in MODELS_10:
                scores = [ep.get("sub_scores", {}).get(sk, 0.0) for ep in episodes.get(m, []) if "sub_scores" in ep]
                if scores:
                    vals[m] = sum(scores) / len(scores)

            for m in MODELS_10:
                if m in vals:
                    lines.append(emit(f"{prefix}{macro_infix}{MODEL_TEX[m]}", fmt_s(vals[m])))
            lines.append("")

        # C2 aggregate means (cross-model)
        if sk == "C2_mandatory_completion":
            for _corpus_tag, prefix, episodes in [
                ("V73", "crossVSeven", v73_episodes),
                ("V6", "crossVSix", v6_episodes),
            ]:
                vals_list: list[float] = []
                for m in MODELS_10:
                    scores = [ep.get("sub_scores", {}).get(sk, 0.0) for ep in episodes.get(m, []) if "sub_scores" in ep]
                    if scores:
                        vals_list.append(sum(scores) / len(scores))

                if vals_list:
                    mean_all = sum(vals_list) / len(vals_list)
                    mn, mx = min(vals_list), max(vals_list)
                    lines.append("% --- C2 Aggregate Means ---")
                    lines.append(
                        emit(f"{prefix}CTwoMeanAll", fmt_s(mean_all)) + f"  % mean across {len(vals_list)} models"
                    )
                    lines.append(emit(f"{prefix}CTwoRange", f"{fmt_s(mn)}--{fmt_s(mx)}"))
                    lines.append("")

    return lines


# ---------------------------------------------------------------------------
# Section 10: Violation Rates — from raw episodes
# ---------------------------------------------------------------------------
def section_10(
    v73_episodes: dict[str, list[dict]],
    v6_episodes: dict[str, list[dict]],
) -> tuple[list[str], dict, dict]:
    """Section 10: Violation rates per episode. Also returns rate dicts for Section 14."""
    lines = [
        "% =========================================================",
        "%  Section 10: Violation Rates (mean per episode)",
        "% =========================================================",
    ]

    viol_types = [
        ("omission", "Omit", "Omission", ".2f"),
        ("commission", "Comm", "Commission", ".3f"),
        ("timing", "Timing", "Timing", ".2f"),
    ]

    # Store rates for Section 14
    v73_rates: dict[str, dict[str, float]] = defaultdict(dict)
    v6_rates: dict[str, dict[str, float]] = defaultdict(dict)

    for vtype, macro_infix, label, fmt_spec in viol_types:
        lines.append("")
        lines.append(f"% --- V73 {label} per episode ---")

        for corpus_tag, prefix, episodes, rates_out in [
            ("V73", "crossVSeven", v73_episodes, v73_rates),
            ("V6", "crossVSix", v6_episodes, v6_rates),
        ]:
            for m in MODELS_10:
                eps = episodes.get(m, [])
                if not eps:
                    continue
                vbt_counts = [_count_viol_type(ep, vtype) for ep in eps]
                mean_rate = sum(vbt_counts) / len(vbt_counts)
                rates_out[m][vtype] = mean_rate
                lines.append(
                    emit(
                        f"{prefix}{macro_infix}{MODEL_TEX[m]}",
                        f"{mean_rate:{fmt_spec}}",
                    )
                )

            lines.append("")
            if corpus_tag == "V73":
                lines.append(f"% --- V6 {label} per episode ---")

    return lines, dict(v73_rates), dict(v6_rates)


def _count_viol_type(ep: dict, vtype: str) -> int:
    """Count violations of a specific type in an episode."""
    vbt = ep.get("violations_by_type") or {}
    count = vbt.get(vtype, 0)
    # Also check variant keys (e.g., 'within', 'before' count as timing)
    if vtype == "timing":
        count += vbt.get("within", 0) + vbt.get("before", 0)
    elif vtype == "commission":
        count += vbt.get("forbidden", 0)
    return count


# ---------------------------------------------------------------------------
# Section 11: Spearman Correlations
# ---------------------------------------------------------------------------
def section_11(v73_pm: dict, v6_pm: dict) -> list[str]:
    """Section 11: Cross-corpus Spearman rank correlations."""
    lines = [
        "% =========================================================",
        "%  Section 11: Rank Stability — Spearman Correlations",
        "% =========================================================",
        "",
    ]
    for field, macro in [
        ("cga_s_mean", "crossSpearmanCGA"),
        ("tcc", "crossSpearmanTCC"),
        ("cwt", "crossSpearmanCwT"),
    ]:
        v73_vec = [v73_pm[m][field] for m in MODELS_10 if m in v73_pm]
        v6_vec = [v6_pm[m][field] for m in MODELS_10 if m in v6_pm]
        rho = spearman(v73_vec, v6_vec)
        lines.append(emit(macro, fmt_s(rho)))
    return lines


# ---------------------------------------------------------------------------
# Section 12: Rank Shifts
# ---------------------------------------------------------------------------
def section_12(v73_pm: dict, v6_pm: dict) -> list[str]:
    """Section 12: Biggest CGA-S rank shifts."""
    lines = [
        "% =========================================================",
        "%  Section 12: Biggest Rank Shifts (CGA-S)",
        "% =========================================================",
        "",
        "% Format: model, V73 rank, V6 rank, shift magnitude",
    ]

    v73_cga = {m: v73_pm[m]["cga_s_mean"] for m in MODELS_10 if m in v73_pm}
    v6_cga = {m: v6_pm[m]["cga_s_mean"] for m in MODELS_10 if m in v6_pm}
    v73_ranks = rank_desc(v73_cga)
    v6_ranks = rank_desc(v6_cga)

    shifts = {m: v6_ranks[m] - v73_ranks[m] for m in MODELS_10}

    # Positive shift = dropped in V6 (worse rank number); emit as "Up" = got worse
    # Negative shift = improved in V6; emit as "Down"
    big_shifts = sorted(shifts.items(), key=lambda x: abs(x[1]), reverse=True)

    for m, shift in big_shifts:
        if abs(shift) < 2:
            continue
        direction = "Up" if shift > 0 else "Down"
        tex = MODEL_TEX[m]
        comment = f"  % V73#{v73_ranks[m]} -> V6#{v6_ranks[m]}, {'+' if shift > 0 else ''}{shift} ranks"
        lines.append(emit(f"crossShift{tex}{direction}", str(abs(shift))) + comment)

    # TCC extreme shifts
    lines.append("")
    lines.append("% TCC extreme rank shift")
    v73_tcc = {m: v73_pm[m]["tcc"] for m in MODELS_10 if m in v73_pm}
    v6_tcc = {m: v6_pm[m]["tcc"] for m in MODELS_10 if m in v6_pm}
    v73_tcc_ranks = rank_desc(v73_tcc)
    v6_tcc_ranks = rank_desc(v6_tcc)
    tcc_shifts = {m: v6_tcc_ranks[m] - v73_tcc_ranks[m] for m in MODELS_10}
    tcc_big = sorted(tcc_shifts.items(), key=lambda x: abs(x[1]), reverse=True)

    for m, shift in tcc_big[:2]:
        direction = "Up" if shift > 0 else "Down"
        comment = f" % V73#{v73_tcc_ranks[m]} -> V6#{v6_tcc_ranks[m]}"
        lines.append(emit(f"crossShiftTCC{MODEL_TEX[m]}{direction}", str(abs(shift))) + comment)

    return lines


# ---------------------------------------------------------------------------
# Section 13: BB Commission Case Study
# ---------------------------------------------------------------------------
def section_13(
    v73_hf_episodes: dict[str, list[dict]],
    v6b_hf_episodes: dict[str, list[dict]] | None = None,
) -> list[str]:
    """Section 13: BB commission from raw V73 HF episodes + V6b cross-validation."""
    lines = [
        "% =========================================================",
        "%  Section 13: BB Commission Case Study",
        "% =========================================================",
        "",
        emit("crossBBNHFScenarios", str(BB_HF_SCENARIOS_V73)),
        emit("crossBBNHFEpisodesPerModel", str(BB_HF_EPISODES_V73)),
    ]

    # --- V73 BB commission counts from raw episode violation_events ---
    bb_comm: dict[str, int] = defaultdict(int)
    bb_runs: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))

    for m in MODELS_10:
        for ep in v73_hf_episodes.get(m, []):
            sid = ep.get("scenario_id", "")
            has_bb_comm = _has_bb_commission(ep)
            if has_bb_comm:
                bb_comm[m] += 1
            bb_runs[m][sid].append(has_bb_comm)

    lines.append("")
    lines.append("% BB commission counts (V73, forbidden context)")
    for m in sorted(MODELS_10, key=lambda x: bb_comm.get(x, 0), reverse=True):
        lines.append(emit(f"crossBBComm{MODEL_TEX[m]}", str(bb_comm.get(m, 0))))

    # --- Determinism ---
    lines.append("")
    lines.append("% BB determinism (%)")
    for m in sorted(MODELS_10, key=lambda x: bb_comm.get(x, 0), reverse=True):
        runs = bb_runs.get(m, {})
        n_scen = len(runs)
        n_det = sum(1 for outcomes in runs.values() if len(outcomes) == N_RUNS and len(set(outcomes)) == 1)
        det_pct = (n_det / n_scen * 100) if n_scen > 0 else 0
        # Format as integer when exact (100 not 100.0)
        if det_pct == int(det_pct):
            lines.append(emit(f"crossBBDet{MODEL_TEX[m]}", str(int(det_pct))))
        else:
            lines.append(emit(f"crossBBDet{MODEL_TEX[m]}", fmt_pct(det_pct)))

    # --- Balanced Accuracy (V73 withhold + V6b prescribe) ---
    lines.append("")
    lines.append("% BB cross-validation balanced accuracy (V73 forbidden + V6b mandatory)")

    bb_ba: dict[str, float] = {}
    best_ba = 0.0
    best_model = ""

    for m in MODELS_10:
        if m in BB_BA_EXCLUDE:
            continue

        withhold_rate = 1.0 - (bb_comm.get(m, 0) / BB_HF_EPISODES_V73)

        # V6b prescribe rate from actions
        prescribe_rate = _compute_v6b_prescribe_rate(m, v6b_hf_episodes)
        if prescribe_rate is None:
            continue

        ba = (withhold_rate + prescribe_rate) / 2
        bb_ba[m] = ba
        if ba > best_ba:
            best_ba = ba
            best_model = m

    for m in MODELS_10:
        if m in bb_ba:
            lines.append(emit(f"crossBBBA{MODEL_TEX[m]}", fmt_s(bb_ba[m])))

    if best_model:
        lines.append(emit("crossBBBABest", fmt_s(best_ba)))
        display = MODEL_DISPLAY.get(best_model, MODEL_TEX[best_model])
        lines.append(emit("crossBBBABestModel", display))

    return lines


MODEL_DISPLAY: dict[str, str] = {
    "qwen27b": "Qwen3.5-27B",
    "nemotron30b": "Nemotron-3-30B",
    "qwen35b": "Qwen3.5-35B",
    "qwen4b": "Qwen3-4B",
    "qwen397b": "Qwen3.5-397B",
    "gemma31b": "Gemma-4-31B",
    "llama4scout": "Llama-4-Scout",
    "oss120b": "GPT-oss-120B",
    "allm_h": "ALLM.H",
    "deepseek_r1_7b": "DeepSeek-R1-7B",
}


def _has_bb_commission(ep: dict) -> bool:
    """Check if episode has a BB-specific commission violation."""
    for ve in ep.get("violation_events", []):
        if ve.get("violation_type") == "commission":
            action = (ve.get("action_involved") or "").lower()
            if "beta_blocker" in action:
                return True
    return False


def _compute_v6b_prescribe_rate(
    model: str,
    v6b_hf_episodes: dict[str, list[dict]] | None,
) -> float | None:
    """Compute BB prescribe rate from V6b BB-mandatory episodes.

    Uses agent actions array: for initiate scenarios, checks if any action
    contains 'beta_blocker'; for bradycardia scenario, correct behavior
    is withholding (no BB action).
    """
    if v6b_hf_episodes is None:
        return None
    eps = v6b_hf_episodes.get(model, [])
    if not eps:
        return None

    correct = 0
    for ep in eps:
        sid = ep.get("scenario_id", "")
        actions = ep.get("actions", [])
        has_bb_action = any("beta_blocker" in (a.get("action_id") or "").lower() for a in actions)
        if sid == BB_V6B_BRADY_SID:
            # Bradycardia: correct = withhold BB
            if not has_bb_action:
                correct += 1
        else:
            # Initiate scenarios: correct = prescribe BB
            if has_bb_action:
                correct += 1

    return correct / len(eps)


# ---------------------------------------------------------------------------
# Section 14: Typed Violation Ratio
# ---------------------------------------------------------------------------
def section_14(
    v73_rates: dict[str, dict[str, float]],
    v6_rates: dict[str, dict[str, float]],
) -> list[str]:
    """Section 14: Ratio of typed violations (V73/V6)."""
    lines = [
        "% =========================================================",
        "%  Section 14: Typed Violation Ratio (V73/V6)",
        "% =========================================================",
        "% Total typed violations = omission + commission + timing (per episode)",
        "",
    ]
    for m in MODELS_10:
        v73_total = sum(v73_rates.get(m, {}).get(t, 0) for t in ["omission", "commission", "timing"])
        v6_total = sum(v6_rates.get(m, {}).get(t, 0) for t in ["omission", "commission", "timing"])
        ratio = v73_total / v6_total if v6_total > 0 else 0
        lines.append(emit(f"crossTypedRatio{MODEL_TEX[m]}", fmt_2f(ratio)))
    return lines


# ---------------------------------------------------------------------------
# Section 15: Gate-fail substrate stability rho
# ---------------------------------------------------------------------------
def section_15(
    v73_pm: dict,
    v6_pm: dict,
    v6b_pm: dict,
) -> list[str]:
    """Section 15: Cross-corpus Spearman rho on gate_fail rate."""
    lines = [
        "% =========================================================",
        "%  Section 15: Gate-Fail Substrate Stability (Spearman rho)",
        "% =========================================================",
        "",
    ]

    # V6 <-> V73 (n=10)
    v73_gf = [v73_pm[m]["gate_fail"] for m in MODELS_10 if m in v73_pm]
    v6_gf = [v6_pm[m]["gate_fail"] for m in MODELS_10 if m in v6_pm]
    rho_v6_v73 = spearman(v73_gf, v6_gf)
    lines.append(emit("crossGateRhoVSixVSeven", fmt_s(rho_v6_v73)))

    # V6 <-> V6b (n=9, no llama4scout)
    v6_gf_9 = [v6_pm[m]["gate_fail"] for m in MODELS_9_V6B if m in v6_pm]
    v6b_gf_9 = [v6b_pm[m]["gate_fail"] for m in MODELS_9_V6B if m in v6b_pm]
    rho_v6_v6b = spearman(v6_gf_9, v6b_gf_9)
    lines.append(emit("crossGateRhoVSixPB", fmt_s(rho_v6_v6b)))

    # V6b <-> V73 (n=9)
    v73_gf_9 = [v73_pm[m]["gate_fail"] for m in MODELS_9_V6B if m in v73_pm]
    rho_v6b_v73 = spearman(v6b_gf_9, v73_gf_9)
    lines.append(emit("crossGateRhoPBVSeven", fmt_s(rho_v6b_v73)))

    mean_rho = (rho_v6_v73 + rho_v6_v6b + rho_v6b_v73) / 3
    lines.append(emit("crossGateRhoMean", fmt_s(mean_rho)))

    return lines


# ---------------------------------------------------------------------------
# Section 16: Pass >= 0.5
# ---------------------------------------------------------------------------
def section_16(v73_pm: dict, v6_pm: dict) -> list[str]:
    """Section 16: Pass rate >= 0.5 from cga_s_clean JSONs."""
    lines = [
        "% =========================================================",
        "%  Section 16: Pass Rate >= 0.5",
        "% =========================================================",
        "",
        "% --- V73 Pass>=0.5 ---",
    ]
    v73_vals = {m: v73_pm[m]["pass_5"] * 100 for m in MODELS_10 if m in v73_pm}
    v6_vals = {m: v6_pm[m]["pass_5"] * 100 for m in MODELS_10 if m in v6_pm}

    for m in sorted_models_desc(v73_vals, MODELS_10):
        lines.append(emit(f"crossVSevenPassFive{MODEL_TEX[m]}", fmt_pct(v73_vals[m])))
    lines.append("")
    lines.append("% --- V6 Pass>=0.5 ---")
    for m in sorted_models_desc(v6_vals, MODELS_10):
        lines.append(emit(f"crossVSixPassFive{MODEL_TEX[m]}", fmt_pct(v6_vals[m])))
    return lines


# ---------------------------------------------------------------------------
# Section 17: Domain-Localized Commission %
# ---------------------------------------------------------------------------
DOMAIN_PREFIXES: list[tuple[str, str]] = [
    ("ssc_sepsis", "Sepsis"),
    ("septic_shock", "Sepsis"),
    ("aha_chest_pain", "ChestPain"),
    ("stemi_", "ChestPain"),
    ("aha_stroke", "Stroke"),
    ("aha_heart_failure", "HeartFailure"),
    ("aha_heart_fa", "HeartFailure"),
    ("hfref_", "HeartFailure"),
    ("cardiogenic", "HeartFailure"),
    ("kdigo_aki", "AKI"),
    ("kdigo_contrast", "AKI"),
    ("ada_dka", "DKA"),
    ("atrial_fib", "AtrialFib"),
    ("esc_af", "AtrialFib"),
    ("cap_pneumonia", "Pneumonia"),
    ("copd", "COPD"),
    ("gi_bleeding", "GIBleed"),
    ("gib_trap", "GIBleed"),
    ("hypertensive", "HyperEmerg"),
    ("pulmonary_embolism", "PE"),
    ("acls", "CardiacArrest"),
    ("anaphylaxis", "Anaphylaxis"),
    ("aabb", "Transfusion"),
    ("asthma", "Asthma"),
    ("meningitis", "Meningitis"),
    ("status_epilepticus", "Epilepticus"),
]


def detect_domain(scenario_id: str) -> str:
    """Detect clinical domain from scenario_id using longest prefix match."""
    sid = scenario_id.lower()
    best_match = ""
    best_domain = "Other"
    for prefix, domain in DOMAIN_PREFIXES:
        if sid.startswith(prefix) and len(prefix) > len(best_match):
            best_match = prefix
            best_domain = domain
    return best_domain


def section_17(v73_vm: dict, v6_vm: dict) -> list[str]:
    """Section 17: Domain-localized commission rate + counts heatmap + JSON."""
    lines = [
        "% =========================================================",
        "%  Section 17: Domain-Localized Commission Rate (%) + Counts",
        "% =========================================================",
        "",
    ]

    heatmap_json: dict[str, dict] = {}

    for corpus_tag, vm, corpus_key in [
        ("VSeven", v73_vm, "V73"),
        ("VSix", v6_vm, "V6"),
    ]:
        # {domain: {model: [has_commission_bool]}}
        dom_model: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
        for ep in vm["per_episode"]:
            sid = ep["scenario_id"]
            mdl = ep["model_dir"]
            domain = detect_domain(sid)
            has_comm = "FORBIDDEN" in ep.get("viol_types", "")
            dom_model[domain][mdl].append(has_comm)

        comm_counts: dict[str, dict[str, int]] = {}
        total_counts: dict[str, dict[str, int]] = {}
        comm_rates: dict[str, dict[str, float]] = {}

        lines.append(f"% --- {corpus_tag} Commission by Domain ---")
        for domain in sorted(dom_model):
            comm_counts[domain] = {}
            total_counts[domain] = {}
            comm_rates[domain] = {}
            for m in MODELS_10:
                bools = dom_model[domain].get(m, [])
                if not bools:
                    continue
                n_comm = sum(bools)
                n_total = len(bools)
                rate = n_comm / n_total * 100
                comm_counts[domain][m] = n_comm
                total_counts[domain][m] = n_total
                comm_rates[domain][m] = round(rate, 1)
                lines.append(emit(f"cross{corpus_tag}DomComm{domain}{MODEL_TEX[m]}", fmt_pct(rate)))
                lines.append(emit(f"cross{corpus_tag}DomCommN{domain}{MODEL_TEX[m]}", str(n_comm)))
                lines.append(emit(f"cross{corpus_tag}DomTotal{domain}{MODEL_TEX[m]}", str(n_total)))
            # Domain total across models
            all_bools = [b for mdl_bools in dom_model[domain].values() for b in mdl_bools]
            if all_bools:
                total_rate = sum(all_bools) / len(all_bools) * 100
                lines.append(emit(f"cross{corpus_tag}DomComm{domain}All", fmt_pct(total_rate)))
            lines.append("")

        heatmap_json[corpus_key] = {
            "domains": sorted(dom_model),
            "models": MODELS_10,
            "commission_counts": comm_counts,
            "total_counts": total_counts,
            "commission_rates": comm_rates,
        }

    lines.append(emit("crossDomNDomainsVSeven", str(len(heatmap_json.get("V73", {}).get("domains", [])))))
    lines.append(emit("crossDomNDomainsVSix", str(len(heatmap_json.get("V6", {}).get("domains", [])))))

    # Save canonical JSON
    json_path = EVIDENCE / "domain_commission_heatmap.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(heatmap_json, f, indent=2)
    print(f"  saved → {json_path}")

    return lines


# ---------------------------------------------------------------------------
# Section 18: Dual-Substrate Vocabulary Alignment
# ---------------------------------------------------------------------------
def section_18(
    v73_episodes: dict[str, list[dict]],
    v6_episodes: dict[str, list[dict]],
) -> list[str]:
    """Section 18: Per-model action vocabulary overlap between V73 and V6."""
    lines = [
        "% =========================================================",
        "%  Section 18: Dual-Substrate Vocabulary Alignment",
        "% =========================================================",
        "",
    ]

    common_models = [m for m in MODELS_10 if v73_episodes.get(m) and v6_episodes.get(m)]

    per_model: dict[str, dict[str, float]] = {}
    jaccards: list[float] = []

    for m in common_models:
        v73_vocab: set[str] = set()
        for ep in v73_episodes[m]:
            for a in ep.get("actions", []):
                aid = a.get("action_id")
                if aid:
                    v73_vocab.add(aid)

        v6_vocab: set[str] = set()
        for ep in v6_episodes[m]:
            for a in ep.get("actions", []):
                aid = a.get("action_id")
                if aid:
                    v6_vocab.add(aid)

        union = v73_vocab | v6_vocab
        inter = v73_vocab & v6_vocab
        jaccard = len(inter) / len(union) if union else 0.0
        overlap_v73 = len(inter) / len(v73_vocab) if v73_vocab else 0.0
        overlap_v6 = len(inter) / len(v6_vocab) if v6_vocab else 0.0

        tex = MODEL_TEX[m]
        lines.append(emit(f"crossVocabJaccard{tex}", fmt_s(jaccard)))
        lines.append(emit(f"crossVocabOverlapVSeven{tex}", fmt_s(overlap_v73)))
        lines.append(emit(f"crossVocabOverlapVSix{tex}", fmt_s(overlap_v6)))
        lines.append(emit(f"crossVocabSizeVSeven{tex}", str(len(v73_vocab))))
        lines.append(emit(f"crossVocabSizeVSix{tex}", str(len(v6_vocab))))

        per_model[m] = {
            "jaccard": round(jaccard, 4),
            "overlap_v73": round(overlap_v73, 4),
            "overlap_v6": round(overlap_v6, 4),
            "v73_vocab_size": len(v73_vocab),
            "v6_vocab_size": len(v6_vocab),
            "intersection_size": len(inter),
            "union_size": len(union),
        }
        jaccards.append(jaccard)

    lines.append("")
    if jaccards:
        mean_j = sum(jaccards) / len(jaccards)
        lines.append(emit("crossVocabMeanJaccard", fmt_s(mean_j)))
    lines.append(emit("crossVocabNModels", str(len(common_models))))

    # Save canonical JSON
    json_path = EVIDENCE / "dual_substrate_vocabulary_alignment.json"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(
            {
                "description": "Per-model action vocabulary overlap between V73 and V6",
                "models": common_models,
                "per_model": per_model,
                "mean_jaccard": round(sum(jaccards) / len(jaccards), 4) if jaccards else 0.0,
            },
            f,
            indent=2,
        )
    print(f"  saved → {json_path}")

    return lines


# ---------------------------------------------------------------------------
# Verify mode
# ---------------------------------------------------------------------------
MACRO_RE = re.compile(r"\\providecommand\{\\(\w+)\}\{([^}]*)\}")


def parse_macros(text: str) -> dict[str, str]:
    r"""Parse all \providecommand macros from TeX text."""
    macros: dict[str, str] = {}
    for line in text.splitlines():
        m = MACRO_RE.search(line)
        if m:
            macros[m.group(1)] = m.group(2)
    return macros


def verify(generated: str, existing_path: Path) -> int:
    """Compare generated macros against existing file. Returns exit code."""
    if not existing_path.exists():
        print(f"ERROR: existing file not found: {existing_path}")
        return 1

    existing_text = existing_path.read_text()
    gen_macros = parse_macros(generated)
    old_macros = parse_macros(existing_text)

    mismatches: list[str] = []
    new_macros: list[str] = []
    missing_macros: list[str] = []

    all_names = sorted(set(gen_macros) | set(old_macros))
    for name in all_names:
        if name in gen_macros and name in old_macros:
            if gen_macros[name] != old_macros[name]:
                mismatches.append(f"  MISMATCH {name}: old={old_macros[name]} gen={gen_macros[name]}")
        elif name in gen_macros:
            new_macros.append(f"  NEW {name}: {gen_macros[name]}")
        else:
            missing_macros.append(f"  MISSING {name}: {old_macros[name]}")

    print("\n=== Verification Report ===")
    print(f"Old macros: {len(old_macros)}")
    print(f"Generated macros: {len(gen_macros)}")
    print(f"Matches: {len(all_names) - len(mismatches) - len(new_macros) - len(missing_macros)}")

    if mismatches:
        print(f"\nMISMATCHES ({len(mismatches)}):")
        for line in mismatches:
            print(line)

    if new_macros:
        print(f"\nNEW ({len(new_macros)}):")
        for line in new_macros:
            print(line)

    if missing_macros:
        print(f"\nMISSING ({len(missing_macros)}):")
        for line in missing_macros:
            print(line)

    if not mismatches and not missing_macros:
        print("\nAll existing macros reproduced correctly.")
        if new_macros:
            print(f"  ({len(new_macros)} new macros added)")
        return 0

    return 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Generate cross-corpus TeX macros")
    parser.add_argument("--verify", action="store_true", help="Compare against existing file")
    parser.add_argument("--dry-run", action="store_true", help="Print stats, don't write")
    args = parser.parse_args()

    print("Loading CGA-S clean JSONs...")
    v73_cga, v6_cga, v6b_cga = load_cga_clean()
    v73_pm = v73_cga["per_model"]
    v6_pm = v6_cga["per_model"]

    print("Loading verdict matrices...")
    v73_vm, v6_vm = load_verdict_matrices()

    print("Loading raw episodes (V73 + V6) for Sections 9-10...")
    v73_raw = load_raw_episodes(V73_RESULTS, MODELS_10)
    v6_raw = load_raw_episodes(V6_RESULTS, MODELS_10)
    for tag, raw in [("V73", v73_raw), ("V6", v6_raw)]:
        total = sum(len(eps) for eps in raw.values())
        print(f"  {tag}: {total} episodes loaded")

    print("Loading V73 HF episodes for BB commission...")
    v73_hf = load_hf_episodes_v73(MODELS_10)
    v73_hf_total = sum(len(eps) for eps in v73_hf.values())
    print(f"  V73 HF: {v73_hf_total} episodes loaded")

    print("Loading V6b BB-mandatory episodes for BB balanced accuracy...")
    v6b_hf = load_hf_episodes_v6b(MODELS_9_V6B)
    v6b_hf_total = sum(len(eps) for eps in v6b_hf.values())
    print(f"  V6b BB: {v6b_hf_total} episodes loaded")

    # --- Generate all sections ---
    print("\nGenerating sections...")
    all_lines: list[str] = [
        "% Auto-generated cross-corpus comparison macros",
        f"% V73 SGSC ({v73_cga['metadata']['n_per_model'] // N_RUNS} scen"
        f" x {v73_cga['metadata']['n_models']} models"
        f" x {N_RUNS} runs = {v73_cga['metadata']['n_total']:,} eps)"
        f"  vs  V6 706 ({v6_cga['metadata']['n_per_model'] // N_RUNS} scen"
        f" x {v6_cga['metadata']['n_models']} models"
        f" x {N_RUNS} runs = {v6_cga['metadata']['n_total']:,} eps)",
        "% Source: evidence_pack/analysis/cga_s_clean_v7_3_sgsc.json, cga_s_clean_v6_706_manual.json",
        "%         verdict_matrix_v7_3_with_allmh_typed_mandfix.json,"
        " verdict_matrix_v6_706_with_allmh_typed_mandfix.json",
        "%         Raw sub-scores computed from results/v73_full_with_allmh/ and results/full_v6b/",
        "% Generated: 2026-05-06",
        "% Design: A3 clean+balanced scoring; typed CwT excludes DEVIATION; mandfix AC/MAB",
    ]

    sections = [
        ("1", section_1(v73_cga["metadata"], v6_cga["metadata"])),
        ("2", section_2(v73_pm, v6_pm)),
        ("3", section_3(v73_pm, v6_pm)),
        ("4", section_4(v73_pm, v6_pm)),
        ("5", section_5(v73_pm, v6_pm)),
        ("6", section_6(v73_pm, v6_pm)),
        ("7", section_7(v73_pm, v6_pm)),
        ("8", section_8(v73_vm, v6_vm)),
    ]

    # Sections 9-10 from raw episodes
    s9 = section_9(v73_raw, v6_raw)
    s10_lines, v73_rates, v6_rates = section_10(v73_raw, v6_raw)
    sections.append(("9", s9))
    sections.append(("10", s10_lines))

    # Section 11: Spearman
    sections.append(("11", section_11(v73_pm, v6_pm)))

    # Section 12: Rank shifts
    sections.append(("12", section_12(v73_pm, v6_pm)))

    # Section 13: BB commission (raw V73 HF episodes + V6b BB-mandatory)
    sections.append(("13", section_13(v73_hf, v6b_hf)))

    # Section 14: Typed ratio
    sections.append(("14", section_14(v73_rates, v6_rates)))

    # Section 15: Gate-fail substrate rho
    v6b_pm = v6b_cga["per_model"]
    sections.append(("15", section_15(v73_pm, v6_pm, v6b_pm)))

    # Section 16: Pass >= 0.5
    sections.append(("16", section_16(v73_pm, v6_pm)))

    # Section 17: Domain-localized commission + heatmap JSON
    sections.append(("17", section_17(v73_vm, v6_vm)))

    # Section 18: Dual-substrate vocabulary alignment
    sections.append(("18", section_18(v73_raw, v6_raw)))

    for _num, sec_lines in sections:
        all_lines.append("")
        all_lines.extend(sec_lines)

    # Ensure file ends with newline
    output_text = "\n".join(all_lines) + "\n"

    n_macros = len(parse_macros(output_text))
    print(f"\nTotal macros: {n_macros}")
    print(f"Total lines: {len(all_lines)}")

    if args.dry_run:
        print("\n[DRY RUN] Not writing file.")
        return 0

    if args.verify:
        return verify(output_text, OUTPUT)

    OUTPUT.write_text(output_text)
    print(f"\nWritten: {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
