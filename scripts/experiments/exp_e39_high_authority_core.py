#!/usr/bin/env python3
"""E9: High-Authority Core Robustness Audit.

Restricts the TCC reference catalogue to **high-authority** clinical
recommendations (AHA Class I/IIa + LOE A/B; IDSA / KDIGO / AABB strong;
GRADE 1A/1B; drug-allergy contraindications) and recomputes the four
audit numbers that drive the reviewer-defense narrative:

1. FA_strict_high  -- ASC ∩ CwT ∩ PAF pass and TCC_high fails
2. replay_loss_high -- detection loss for MAB / AC under TCC_high
3. ranking_reversal_high -- per-pair model ranking flips under TCC_high
4. per-type breakdown -- FORBIDDEN / WITHIN / BEFORE / MUST counts

The experiment is **audit-side only** -- no model inference, no scenario
re-run. Inputs:

- ``evidence_pack/analysis/verdict_matrix_v6.json``  (ASC/CwT/PAF reference)
- ``cpg_model/graphs/*.yaml``                        (authority taxonomy source)
- ``configs/scenarios/*.yaml``                       (scenario -> graph_id)
- ``results/full_v6{a,b,*}/<model>/*.json``          (raw violation_events)

Outputs:

- ``evidence_pack/analysis/exp_e9_high_authority_core.json``
- ``evidence_pack/analysis/exp_e9_high_authority_core.md``
- ``evidence_pack/analysis/exp_e9_macros.tex``
- ``evidence_pack/analysis/verdict_matrix_v6_high.json``  (per-episode cache)

Spec: docs/attack_gap_exp_exp/260430_e9_High-Authority_Core_Robustness.md
Convention: filename ``exp_e39_*`` slots into the existing
``scripts/experiments/exp_eN_*`` numbering; the spec calls this experiment
"E9" so the in-paper citations and JSON/MD output filenames keep the
``exp_e9_`` prefix.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

import yaml

# Allow direct execution: ``python scripts/experiments/exp_e39_high_authority_core.py``
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cpg_model.constraint_derivation import (  # noqa: E402
    DerivedConstraint,
    _classify_authority,
)
from audit.authority_filter import tier_for  # noqa: E402

# -------------------------------------------------------------------- paths
GRAPHS_DIR = _REPO_ROOT / "cpg_model" / "graphs"
SCENARIOS_DIR = _REPO_ROOT / "configs" / "scenarios"
RESULTS_DIRS_DEFAULT = [
    _REPO_ROOT / "results" / "full_v6a_706",
    _REPO_ROOT / "results" / "full_v6b",
    _REPO_ROOT / "results" / "full_v6b_llama4scout",
]
VERDICT_MATRIX_PATH = (
    _REPO_ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
)
ANALYSIS_DIR = _REPO_ROOT / "evidence_pack" / "analysis"

# -------------------------------------------------------------------- constants
HARD_VIOLATION_TYPES = {"commission", "timing", "sequence"}  # matches v4_hard def
TYPE_TO_DISPLAY = {
    "commission": "FORBIDDEN",
    "timing": "WITHIN",
    "sequence": "BEFORE",
    "omission": "MUST",
    "deviation": "DEVIATION",
}


# =====================================================================
# Stage 1: build authority lookup
# =====================================================================
def _node_tier(node: dict[str, Any]) -> str:
    """Classify a node's authority via the *active* taxonomy.

    Builds a synthetic ``DerivedConstraint`` so the result respects whichever
    taxonomy YAML ``audit.authority_filter.set_taxonomy_path`` last selected.
    """
    synthetic = DerivedConstraint(
        constraint_type="FORBIDDEN",
        actions=["__synthetic__"],
        provenance=f"synthetic:node:{node.get('node_id', 'unknown')}",
        evidence="",
        severity="HARD",
        description="",
        condition_met="",
        is_conditional=False,
        recommendation_class=node.get("recommendation_class"),
        evidence_level=node.get("evidence_level"),
        source_guideline=node.get("source_guideline"),
        authority_tier="unknown",
    )
    return tier_for(synthetic)


def build_node_authority_map() -> dict[tuple[str, str], str]:
    """Return ``(graph_id, node_id) -> authority_tier`` for all graphs."""
    out: dict[tuple[str, str], str] = {}
    for path in sorted(GRAPHS_DIR.rglob("*.yaml")):
        try:
            with open(path) as f:
                graph = yaml.safe_load(f) or {}
        except yaml.YAMLError:
            continue
        graph_id = graph.get("graph_id") or path.stem
        nodes = graph.get("nodes") or {}
        if not isinstance(nodes, dict):
            continue
        for node_id, node in nodes.items():
            if not isinstance(node, dict):
                continue
            tier = _node_tier(node)
            out[(graph_id, node_id)] = tier
            # Also key by graph filename stem for safety, since
            # scenario configs sometimes reference the file basename.
            out[(path.stem, node_id)] = tier
    return out


def build_scenario_to_graph_map() -> dict[str, str]:
    """Return ``scenario_id -> graph_id`` from configs/scenarios/*.yaml."""
    mapping: dict[str, str] = {}
    for path in sorted(SCENARIOS_DIR.rglob("*.yaml")):
        try:
            with open(path) as f:
                blob = yaml.safe_load(f) or {}
        except yaml.YAMLError:
            continue
        scenarios = blob.get("scenarios") or {}
        if not isinstance(scenarios, dict):
            continue
        for sid, sc in scenarios.items():
            if not isinstance(sc, dict):
                continue
            g = sc.get("guideline_graph") or sc.get("graph_id")
            if g:
                mapping[sid] = g
    return mapping


# =====================================================================
# Stage 2: index raw episode JSONs
# =====================================================================
def build_episode_index(
    results_dirs: list[Path],
    limit: int | None = None,
) -> dict[tuple[str, str, int], Path]:
    """Walk results/* and index raw JSONs by ``(scenario_id, model_dir, run_index)``."""
    idx: dict[tuple[str, str, int], Path] = {}
    n_seen = 0
    for root in results_dirs:
        if not root.exists():
            continue
        for json_path in root.rglob("*.json"):
            # Skip archive / log / aggregator junk
            parts = set(json_path.parts)
            if any(p.startswith("_") for p in parts):
                continue
            try:
                with open(json_path) as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue
            sid = data.get("scenario_id")
            run_idx = data.get("run_index")
            if not isinstance(sid, str) or not isinstance(run_idx, int):
                continue
            # model_dir = parent directory name (e.g. "deepseek_r1_7b")
            model_dir = json_path.parent.name
            key = (sid, model_dir, run_idx)
            # Prefer the first hit; later duplicates get archived elsewhere.
            idx.setdefault(key, json_path)
            n_seen += 1
            if limit is not None and n_seen >= limit:
                return idx
    return idx


# =====================================================================
# Stage 3: filter per-episode violations to high-authority
# =====================================================================
def filter_violations_for_episode(
    json_path: Path,
    scenario_to_graph: dict[str, str],
    node_authority: dict[tuple[str, str], str],
) -> dict[str, Any] | None:
    """Re-classify an episode's violations under the high-authority subset.

    Returns a dict with keys
    ``{n_hard_high, n_hard_full, viol_types_high, viol_types_full,
       v4_hard_high, kept_node_count, total_node_count}``,
    or ``None`` if the JSON cannot be parsed.
    """
    try:
        with open(json_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    sid = data.get("scenario_id", "")
    graph_id = scenario_to_graph.get(sid)
    events = data.get("violation_events") or []

    n_hard_full = 0
    n_hard_high = 0
    types_full: set[str] = set()
    types_high: set[str] = set()
    kept = 0
    total = 0

    for ev in events:
        vt = (ev.get("violation_type") or "").lower()
        node_id = ev.get("node_at_violation") or ""
        total += 1
        is_hard = vt in HARD_VIOLATION_TYPES
        disp = TYPE_TO_DISPLAY.get(vt, vt.upper())
        if is_hard:
            n_hard_full += 1
            types_full.add(disp)

        # Look up authority of the originating node
        tier = "unknown"
        if graph_id and node_id:
            tier = node_authority.get((graph_id, node_id), "unknown")
            if tier == "unknown":
                # Fallback: try the path stem variant (some scenarios reference
                # graph by filename stem rather than canonical graph_id).
                tier = node_authority.get((graph_id, node_id), "unknown")

        if tier == "high":
            kept += 1
            if is_hard:
                n_hard_high += 1
                types_high.add(disp)

    return {
        "n_hard_full": n_hard_full,
        "n_hard_high": n_hard_high,
        "viol_types_full": sorted(types_full),
        "viol_types_high": sorted(types_high),
        "v4_hard_high": (n_hard_high == 0),
        "v4_hard_full_recomputed": (n_hard_full == 0),
        "kept_violation_events": kept,
        "total_violation_events": total,
    }


# =====================================================================
# Stage 4: aggregate audit metrics
# =====================================================================
def compute_aggregate_metrics(
    enriched: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate FA / replay / ranking / per-type under high-authority TCC.

    Convention notes:
    - The cached ``v4_hard`` field uses ``True == has_hard_violation == FAIL``
      (i.e., ``v4_hard=true`` means TCC rejected the trace).
    - The other proxy fields (``ac_proxy``, ``mab_proxy``, ``c2_pass``,
      ``acov_pass``, ``dxem``) use ``True == PASS``.
    - Our recomputed ``v4_hard_high`` follows the proxy convention:
      ``True == PASS == no high-authority hard violations``.
    """
    n_total = len(enriched)
    if n_total == 0:
        return {"error": "no episodes enriched"}

    def tcc_full_pass(ep: dict[str, Any]) -> bool:
        # cached v4_hard is "has hard violation" -> invert
        return ep.get("v4_hard") is False

    def tcc_high_pass(ep: dict[str, Any]) -> bool:
        return ep.get("v4_hard_high") is True

    # ----- Strict false-accept (ASC ∩ CwT ∩ PAF pass, TCC fail) -----
    fa_strict_full = 0
    fa_strict_high = 0
    rejected_full = 0
    rejected_high = 0
    for ep in enriched:
        asc = ep.get("ac_proxy") is True
        cwt = ep.get("c2_pass") is True
        paf = ep.get("mab_proxy") is True
        if asc and cwt and paf:
            if not tcc_full_pass(ep):
                fa_strict_full += 1
            if not tcc_high_pass(ep):
                fa_strict_high += 1
        if not tcc_full_pass(ep):
            rejected_full += 1
        if not tcc_high_pass(ep):
            rejected_high += 1

    # ----- Replay-detection loss for MAB / AC under TCC -----
    # detection loss = of episodes the TCC reference rejected (fail),
    # what fraction did the proxy still call "pass"?
    def _replay_loss(proxy_field: str, tcc_pass_fn: Any) -> float:
        denom = sum(1 for ep in enriched if not tcc_pass_fn(ep))
        if denom == 0:
            return 0.0
        num = sum(
            1
            for ep in enriched
            if not tcc_pass_fn(ep) and ep.get(proxy_field) is True
        )
        return num / denom

    replay_loss_high = {
        "mab_proxy": _replay_loss("mab_proxy", tcc_high_pass),
        "ac_proxy": _replay_loss("ac_proxy", tcc_high_pass),
        "c2_pass": _replay_loss("c2_pass", tcc_high_pass),
        "acov_pass": _replay_loss("acov_pass", tcc_high_pass),
    }
    replay_loss_full = {
        "mab_proxy": _replay_loss("mab_proxy", tcc_full_pass),
        "ac_proxy": _replay_loss("ac_proxy", tcc_full_pass),
        "c2_pass": _replay_loss("c2_pass", tcc_full_pass),
        "acov_pass": _replay_loss("acov_pass", tcc_full_pass),
    }

    # ----- Ranking reversal under TCC_high (per-model fail rates) -----
    by_model_full_fail: dict[str, list[bool]] = defaultdict(list)
    by_model_high_fail: dict[str, list[bool]] = defaultdict(list)
    for ep in enriched:
        m = ep.get("model_dir") or "unknown"
        by_model_full_fail[m].append(not tcc_full_pass(ep))
        by_model_high_fail[m].append(not tcc_high_pass(ep))

    rank_full = {
        m: (sum(v) / len(v)) if v else 0.0
        for m, v in by_model_full_fail.items()
    }
    rank_high = {
        m: (sum(v) / len(v)) if v else 0.0
        for m, v in by_model_high_fail.items()
    }
    by_model_full = by_model_full_fail
    by_model_high = by_model_high_fail
    models = sorted(by_model_full.keys())
    pair_total = 0
    pair_reversed = 0
    for a, b in combinations(models, 2):
        order_full = rank_full[a] - rank_full[b]
        order_high = rank_high[a] - rank_high[b]
        if order_full == 0 or order_high == 0:
            continue
        pair_total += 1
        if (order_full > 0) != (order_high > 0):
            pair_reversed += 1

    ranking_reversal_high = pair_reversed / pair_total if pair_total else 0.0

    # ----- Per-violation-type breakdown -----
    type_counts_full: Counter[str] = Counter()
    type_counts_high: Counter[str] = Counter()
    for ep in enriched:
        for t in ep.get("viol_types_full") or []:
            type_counts_full[t] += 1
        for t in ep.get("viol_types_high") or []:
            type_counts_high[t] += 1

    # ----- Constraint count drop (informational) -----
    kept_total = sum(ep.get("kept_violation_events", 0) for ep in enriched)
    seen_total = sum(ep.get("total_violation_events", 0) for ep in enriched)

    return {
        "n_episodes": n_total,
        "fa_strict": {
            "full_catalogue": {
                "count": fa_strict_full,
                "rate": fa_strict_full / n_total,
            },
            "high_authority": {
                "count": fa_strict_high,
                "rate": fa_strict_high / n_total,
            },
        },
        "tcc_fail_count": {
            "full_catalogue": rejected_full,
            "high_authority": rejected_high,
        },
        "replay_detection_loss": {
            "full_catalogue": replay_loss_full,
            "high_authority": replay_loss_high,
        },
        "ranking_reversal": {
            "n_pairs": pair_total,
            "n_reversed": pair_reversed,
            "rate": ranking_reversal_high,
            "per_model_fail_rate_full": rank_full,
            "per_model_fail_rate_high": rank_high,
        },
        "violation_type_breakdown": {
            "full_catalogue": dict(type_counts_full),
            "high_authority": dict(type_counts_high),
        },
        "violation_event_authority_split": {
            "high_kept": kept_total,
            "total": seen_total,
            "drop_rate": (
                1.0 - (kept_total / seen_total) if seen_total else 0.0
            ),
        },
    }


# =====================================================================
# Stage 5: render outputs
# =====================================================================
def render_markdown(metrics: dict[str, Any]) -> str:
    fa = metrics["fa_strict"]
    rl = metrics["replay_detection_loss"]
    rr = metrics["ranking_reversal"]
    vb = metrics["violation_type_breakdown"]
    drop = metrics["violation_event_authority_split"]
    n = metrics["n_episodes"]

    lines: list[str] = []
    lines.append("# E9: High-Authority Core Robustness Audit")
    lines.append("")
    lines.append(
        "Spec: docs/attack_gap_exp_exp/260430_e9_High-Authority_Core_Robustness.md"
    )
    lines.append("")
    lines.append(f"**Episodes evaluated**: {n}")
    lines.append("")
    lines.append("## Headline metrics")
    lines.append("")
    lines.append("| Metric | Full catalogue | High-authority subset |")
    lines.append("|---|---|---|")
    lines.append(
        "| Strict FA (ASC ∩ CwT ∩ PAF pass, TCC fail) | "
        f"{fa['full_catalogue']['rate'] * 100:.2f}% "
        f"({fa['full_catalogue']['count']}) | "
        f"{fa['high_authority']['rate'] * 100:.2f}% "
        f"({fa['high_authority']['count']}) |"
    )
    lines.append(
        "| Replay loss (MAB-proxy under TCC) | "
        f"{rl['full_catalogue']['mab_proxy'] * 100:.2f}% | "
        f"{rl['high_authority']['mab_proxy'] * 100:.2f}% |"
    )
    lines.append(
        "| Replay loss (AC-proxy under TCC) | "
        f"{rl['full_catalogue']['ac_proxy'] * 100:.2f}% | "
        f"{rl['high_authority']['ac_proxy'] * 100:.2f}% |"
    )
    lines.append(
        "| Replay loss (C2 under TCC) | "
        f"{rl['full_catalogue']['c2_pass'] * 100:.2f}% | "
        f"{rl['high_authority']['c2_pass'] * 100:.2f}% |"
    )
    lines.append(
        "| Ranking reversal (high-authority TCC vs cached TCC) | "
        f"-- | {rr['rate'] * 100:.2f}% ({rr['n_reversed']}/{rr['n_pairs']}) |"
    )
    lines.append("")
    lines.append("## Pre-registered success criterion")
    lines.append("")
    lines.append(
        "* strict-FA stays non-zero: "
        f"**{'YES' if fa['high_authority']['rate'] > 0 else 'NO'}** "
        f"({fa['high_authority']['rate'] * 100:.2f}%)"
    )
    lines.append(
        "* replay loss > 50%: "
        f"**{'YES' if rl['high_authority']['mab_proxy'] > 0.5 else 'NO'}** "
        f"(MAB={rl['high_authority']['mab_proxy'] * 100:.2f}%)"
    )
    lines.append(
        "* >= 1 ranking reversal persists: "
        f"**{'YES' if rr['n_reversed'] >= 1 else 'NO'}** "
        f"({rr['n_reversed']} of {rr['n_pairs']} model pairs)"
    )
    lines.append("")
    lines.append("## Per-violation-type breakdown (count per episode-type)")
    lines.append("")
    lines.append("| Type | Full | High-authority |")
    lines.append("|---|---|---|")
    for t in sorted(set(vb["full_catalogue"]) | set(vb["high_authority"])):
        lines.append(
            f"| {t} | {vb['full_catalogue'].get(t, 0)} | "
            f"{vb['high_authority'].get(t, 0)} |"
        )
    lines.append("")
    lines.append("## Constraint-count drop")
    lines.append("")
    lines.append(
        f"Total violation events: {drop['total']}, "
        f"high-authority retained: {drop['high_kept']} "
        f"(drop rate {drop['drop_rate'] * 100:.2f}%)"
    )
    lines.append("")
    lines.append("## Per-model fail rate (TCC pass = no hard violations)")
    lines.append("")
    lines.append("| Model | Full TCC fail rate | High-authority TCC fail rate |")
    lines.append("|---|---|---|")
    for m in sorted(rr["per_model_fail_rate_full"]):
        lines.append(
            f"| {m} | "
            f"{rr['per_model_fail_rate_full'][m] * 100:.2f}% | "
            f"{rr['per_model_fail_rate_high'][m] * 100:.2f}% |"
        )
    lines.append("")
    return "\n".join(lines)


def render_macros(metrics: dict[str, Any]) -> str:
    fa_h = metrics["fa_strict"]["high_authority"]["rate"]
    fa_f = metrics["fa_strict"]["full_catalogue"]["rate"]
    rl_h = metrics["replay_detection_loss"]["high_authority"]
    rr = metrics["ranking_reversal"]

    rl_min = min(v for v in rl_h.values() if v > 0) if any(rl_h.values()) else 0.0
    rl_max = max(rl_h.values()) if rl_h else 0.0

    lines = [
        "% Auto-generated by scripts/experiments/exp_e39_high_authority_core.py",
        "% E9 High-Authority Core Robustness audit",
        f"\\newcommand{{\\Eninefastrictfull}}{{{fa_f * 100:.2f}}}",
        f"\\newcommand{{\\Eninefastrict}}{{{fa_h * 100:.2f}}}",
        f"\\newcommand{{\\Eninereplaylossmin}}{{{rl_min * 100:.2f}}}",
        f"\\newcommand{{\\Eninereplaylossmax}}{{{rl_max * 100:.2f}}}",
        f"\\newcommand{{\\Eninerankreversal}}{{{rr['rate'] * 100:.2f}}}",
        f"\\newcommand{{\\Eninerankreversalcount}}{{{rr['n_reversed']}}}",
        f"\\newcommand{{\\Eninerankpaircount}}{{{rr['n_pairs']}}}",
    ]
    return "\n".join(lines) + "\n"


# =====================================================================
# main
# =====================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N episodes (dev mode).",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        action="append",
        default=None,
        help="Override default result roots (repeat to add multiple).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ANALYSIS_DIR,
        help="Output directory for JSON / MD / macros.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use a tiny limit (=30) and skip writing the verdict-matrix cache.",
    )
    parser.add_argument(
        "--taxonomy",
        type=Path,
        default=None,
        help=(
            "Override the active authority taxonomy YAML "
            "(default: audit/authority_taxonomy.yaml). "
            "Used by F1 threshold sweep."
        ),
    )
    parser.add_argument(
        "--out-suffix",
        type=str,
        default="",
        help=(
            "Suffix appended to output filenames "
            "(e.g. '_S2' -> exp_e9_high_authority_core_S2.json). "
            "Empty by default."
        ),
    )
    args = parser.parse_args()

    limit = args.limit
    if args.dry_run and limit is None:
        limit = 30

    # Activate alternate taxonomy if requested -- must happen before the
    # node-authority map is rebuilt so per-graph classification picks it up.
    if args.taxonomy is not None:
        from audit.authority_filter import set_taxonomy_path
        set_taxonomy_path(args.taxonomy)
        print(f"[0/5] Active taxonomy: {args.taxonomy}", flush=True)

    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = args.out_suffix or ""

    print(f"[1/5] Loading verdict matrix from {VERDICT_MATRIX_PATH}", flush=True)
    with open(VERDICT_MATRIX_PATH) as f:
        vmatrix = json.load(f)
    per_episode_full = vmatrix.get("per_episode") or []
    if limit is not None:
        per_episode_full = per_episode_full[:limit]
    print(f"      {len(per_episode_full)} episode rows loaded", flush=True)

    print("[2/5] Building authority lookup from cpg_model/graphs/*.yaml", flush=True)
    node_authority = build_node_authority_map()
    scenario_to_graph = build_scenario_to_graph_map()
    n_nodes = len(node_authority)
    n_high_nodes = sum(1 for v in node_authority.values() if v == "high")
    print(
        f"      {n_nodes} (graph,node) entries  "
        f"[{n_high_nodes} high]",
        flush=True,
    )
    print(
        f"      {len(scenario_to_graph)} scenario_id -> graph_id mappings",
        flush=True,
    )

    print("[3/5] Indexing raw episode JSONs", flush=True)
    results_dirs = args.results_dir or RESULTS_DIRS_DEFAULT
    episode_index = build_episode_index(results_dirs)
    print(f"      {len(episode_index)} (scenario, model_dir, run_index) keys indexed",
          flush=True)

    print("[4/5] Re-classifying violations under high-authority subset", flush=True)
    enriched: list[dict[str, Any]] = []
    n_missing = 0
    n_done = 0
    n_total = len(per_episode_full)
    for ep in per_episode_full:
        sid = ep.get("scenario_id", "")
        m = ep.get("model_dir", "")
        r = ep.get("run_index", -1)
        path = episode_index.get((sid, m, r))
        merged = dict(ep)
        if path is None:
            n_missing += 1
            merged["v4_hard_high"] = ep.get("v4_hard")  # fall back to cached
            merged["viol_types_high"] = ep.get("viol_types") or []
            merged["viol_types_full"] = ep.get("viol_types") or []
            merged["kept_violation_events"] = 0
            merged["total_violation_events"] = ep.get("n_viols", 0)
            merged["_e9_status"] = "raw_json_missing"
        else:
            extra = filter_violations_for_episode(
                path, scenario_to_graph, node_authority
            )
            if extra is None:
                n_missing += 1
                merged["v4_hard_high"] = ep.get("v4_hard")
                merged["viol_types_high"] = ep.get("viol_types") or []
                merged["viol_types_full"] = ep.get("viol_types") or []
                merged["kept_violation_events"] = 0
                merged["total_violation_events"] = ep.get("n_viols", 0)
                merged["_e9_status"] = "raw_json_unreadable"
            else:
                merged.update(extra)
                merged["_e9_status"] = "ok"
        enriched.append(merged)
        n_done += 1
        if n_done % 1000 == 0:
            print(f"      {n_done}/{n_total} processed", flush=True)
    print(
        f"      DONE  enriched={len(enriched)} missing_raw={n_missing}",
        flush=True,
    )

    print("[5/5] Aggregating metrics & writing outputs", flush=True)
    metrics = compute_aggregate_metrics(enriched)
    from audit.authority_filter import get_taxonomy_path
    metrics["_meta"] = {
        "spec": "docs/attack_gap_exp_exp/260430_e9_High-Authority_Core_Robustness.md",
        "results_dirs": [str(p) for p in results_dirs],
        "limit": limit,
        "n_missing_raw_json": n_missing,
        "n_node_authority_entries": n_nodes,
        "n_high_authority_nodes": n_high_nodes,
        "verdict_matrix": str(VERDICT_MATRIX_PATH),
        "taxonomy": str(get_taxonomy_path()),
        "out_suffix": suffix,
    }

    json_out = out_dir / f"exp_e9_high_authority_core{suffix}.json"
    md_out = out_dir / f"exp_e9_high_authority_core{suffix}.md"
    macros_out = out_dir / f"exp_e9_macros{suffix}.tex"

    with open(json_out, "w") as f:
        json.dump(metrics, f, indent=2)
    with open(md_out, "w") as f:
        f.write(render_markdown(metrics))
    with open(macros_out, "w") as f:
        f.write(render_macros(metrics))

    if not args.dry_run:
        cache_out = out_dir / f"verdict_matrix_v6_high{suffix}.json"
        slim_cache = [
            {
                "episode_id": ep.get("episode_id"),
                "scenario_id": ep.get("scenario_id"),
                "model_dir": ep.get("model_dir"),
                "run_index": ep.get("run_index"),
                "v4_hard_full": ep.get("v4_hard"),
                "v4_hard_high": ep.get("v4_hard_high"),
                "viol_types_high": ep.get("viol_types_high"),
                "n_hard_high": ep.get("n_hard_high"),
                "n_hard_full": ep.get("n_hard_full"),
                "_e9_status": ep.get("_e9_status"),
            }
            for ep in enriched
        ]
        with open(cache_out, "w") as f:
            json.dump(
                {
                    "metadata": metrics["_meta"],
                    "per_episode": slim_cache,
                },
                f,
                indent=2,
            )
        print(f"      cache:   {cache_out}", flush=True)

    print(f"      json:    {json_out}", flush=True)
    print(f"      md:      {md_out}", flush=True)
    print(f"      macros:  {macros_out}", flush=True)

    fa_h = metrics["fa_strict"]["high_authority"]["rate"]
    rl_h = metrics["replay_detection_loss"]["high_authority"]["mab_proxy"]
    rr_n = metrics["ranking_reversal"]["n_reversed"]
    print()
    print(f"FA_strict_high     = {fa_h * 100:.2f}%")
    print(f"replay_loss_high   = {rl_h * 100:.2f}% (MAB)")
    print(f"ranking_reversed   = {rr_n} model pairs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
