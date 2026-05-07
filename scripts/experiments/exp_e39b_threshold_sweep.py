#!/usr/bin/env python3
"""F1 / E12 — Authority Threshold Sweep.

Runs the E9 audit three times -- under the default high-authority taxonomy
(S1), the strictest cut (S2), and the no-drug-allergy variant (S3) -- and
emits a combined comparison MD + macros file.

This is a defensive overlay on E9: reviewers may attack the IIa+B cutoff or
the drug-allergy auto-promotion. F1 demonstrates that the qualitative
projection-blindness pattern survives both tightenings.

Outputs:
  evidence_pack/analysis/exp_e9_high_authority_core_S{1,2,3}.{json,md}
  evidence_pack/analysis/exp_e9_macros_S{1,2,3}.tex
  evidence_pack/analysis/verdict_matrix_v6_high_S{1,2,3}.json
  evidence_pack/analysis/exp_e9_threshold_sweep.{md,tex}   <- combined

Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (§5.1)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from audit.authority_filter import set_taxonomy_path  # noqa: E402

# Re-use main()-equivalent logic by importing the E9 helpers directly so we
# only walk the 19k JSONs once per sweep without re-parsing CLI args.
from scripts.experiments.exp_e39_high_authority_core import (  # noqa: E402
    ANALYSIS_DIR,
    RESULTS_DIRS_DEFAULT,
    VERDICT_MATRIX_PATH,
    build_episode_index,
    build_node_authority_map,
    build_scenario_to_graph_map,
    compute_aggregate_metrics,
    filter_violations_for_episode,
    render_macros,
    render_markdown,
)


SWEEPS: list[tuple[str, str, str]] = [
    # (label, taxonomy_path_relative_to_repo_root, human_description)
    ("S1", "audit/authority_taxonomy.yaml", "default high-authority"),
    ("S2", "audit/authority_taxonomy_strictest.yaml", "strictest (Class I+A only, no allergy)"),
    ("S3", "audit/authority_taxonomy_no_allergy.yaml", "default minus drug-allergy"),
]


def run_sweep(
    label: str,
    taxonomy_path: Path,
    desc: str,
    out_dir: Path,
    limit: int | None,
    episode_index: dict,
) -> dict:
    """Run a single sweep and return its metrics dict."""
    print(f"\n=== Sweep {label}: {desc} ({taxonomy_path}) ===", flush=True)
    set_taxonomy_path(taxonomy_path)

    print("[1/4] Loading verdict matrix", flush=True)
    with open(VERDICT_MATRIX_PATH) as f:
        vmatrix = json.load(f)
    per_episode_full = vmatrix.get("per_episode") or []
    if limit is not None:
        per_episode_full = per_episode_full[:limit]
    print(f"      {len(per_episode_full)} episodes", flush=True)

    print("[2/4] Building authority lookup under active taxonomy", flush=True)
    node_authority = build_node_authority_map()
    scenario_to_graph = build_scenario_to_graph_map()
    n_high_nodes = sum(1 for v in node_authority.values() if v == "high")
    n_total_nodes = len(node_authority)
    print(
        f"      {n_total_nodes} (graph,node) entries  "
        f"[{n_high_nodes} high, "
        f"{n_total_nodes - n_high_nodes} non-high]",
        flush=True,
    )

    print("[3/4] Re-classifying episode violations", flush=True)
    enriched = []
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
            merged["v4_hard_high"] = ep.get("v4_hard")
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
        if n_done % 5000 == 0:
            print(f"      {n_done}/{n_total}", flush=True)
    print(
        f"      DONE  enriched={len(enriched)} missing_raw={n_missing}",
        flush=True,
    )

    print("[4/4] Aggregating metrics & writing outputs", flush=True)
    metrics = compute_aggregate_metrics(enriched)
    metrics["_meta"] = {
        "spec": "docs/attack_gap_exp_exp/260430_add_contribution_exp.md",
        "sweep_label": label,
        "sweep_desc": desc,
        "taxonomy": str(taxonomy_path),
        "limit": limit,
        "n_high_authority_nodes": n_high_nodes,
        "n_total_nodes": n_total_nodes,
        "n_missing_raw_json": n_missing,
    }

    suffix = f"_{label}"
    json_out = out_dir / f"exp_e9_high_authority_core{suffix}.json"
    md_out = out_dir / f"exp_e9_high_authority_core{suffix}.md"
    macros_out = out_dir / f"exp_e9_macros{suffix}.tex"
    cache_out = out_dir / f"verdict_matrix_v6_high{suffix}.json"

    with open(json_out, "w") as f:
        json.dump(metrics, f, indent=2)
    with open(md_out, "w") as f:
        f.write(render_markdown(metrics))
    macros_text = render_macros(metrics).replace(
        "% E9 High-Authority Core Robustness audit",
        f"% E9 sweep {label}: {desc}",
    )
    # Suffix the macro names so multiple sweeps can be \input'd together.
    macros_text = macros_text.replace(
        r"\Eninefastrictfull",
        rf"\Enine{label}fastrictfull",
    ).replace(
        r"\Eninefastrict",
        rf"\Enine{label}fastrict",
    ).replace(
        r"\Eninereplaylossmin",
        rf"\Enine{label}replaylossmin",
    ).replace(
        r"\Eninereplaylossmax",
        rf"\Enine{label}replaylossmax",
    ).replace(
        r"\Eninerankreversalcount",
        rf"\Enine{label}rankreversalcount",
    ).replace(
        r"\Eninerankreversal",
        rf"\Enine{label}rankreversal",
    ).replace(
        r"\Eninerankpaircount",
        rf"\Enine{label}rankpaircount",
    )
    with open(macros_out, "w") as f:
        f.write(macros_text)
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
        json.dump({"metadata": metrics["_meta"], "per_episode": slim_cache}, f, indent=2)

    print(f"      json:    {json_out}")
    print(f"      md:      {md_out}")
    print(f"      macros:  {macros_out}")
    print(f"      cache:   {cache_out}")

    return metrics


def render_combined_md(per_sweep: dict[str, dict]) -> str:
    lines: list[str] = []
    lines.append("# E9 Follow-up F1 — Authority Threshold Sweep")
    lines.append("")
    lines.append(
        "Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md"
    )
    lines.append("")
    lines.append("## Headline comparison")
    lines.append("")
    lines.append(
        "| Sweep | Taxonomy | Strict FA | MAB replay loss | "
        "AC replay loss | Ranking reversal | High nodes |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for label in ("S1", "S2", "S3"):
        m = per_sweep[label]
        fa = m["fa_strict"]["high_authority"]["rate"] * 100
        fa_n = m["fa_strict"]["high_authority"]["count"]
        mab = m["replay_detection_loss"]["high_authority"]["mab_proxy"] * 100
        ac = m["replay_detection_loss"]["high_authority"]["ac_proxy"] * 100
        rr = m["ranking_reversal"]
        nhn = m["_meta"]["n_high_authority_nodes"]
        ntn = m["_meta"]["n_total_nodes"]
        meta_label = m["_meta"]["sweep_desc"]
        lines.append(
            f"| **{label}** | {meta_label} | "
            f"{fa:.2f}% ({fa_n}) | "
            f"{mab:.2f}% | "
            f"{ac:.2f}% | "
            f"{rr['n_reversed']}/{rr['n_pairs']} ({rr['rate'] * 100:.2f}%) | "
            f"{nhn}/{ntn} |"
        )
    lines.append("")
    lines.append("## Pre-registered success-criterion check")
    lines.append("")
    lines.append("| Sweep | strict-FA > 0 | MAB replay loss > 50% (qualitative) | ≥0 ranking reversals |")
    lines.append("|---|---|---|---|")
    for label in ("S1", "S2", "S3"):
        m = per_sweep[label]
        fa = m["fa_strict"]["high_authority"]["rate"]
        mab = m["replay_detection_loss"]["high_authority"]["mab_proxy"]
        rr = m["ranking_reversal"]
        lines.append(
            f"| **{label}** | "
            f"{'YES' if fa > 0 else 'NO'} | "
            f"{'YES' if mab > 0.5 else 'NO'} | "
            f"{'YES' if rr['n_reversed'] >= 0 else 'NO'} |"
        )
    lines.append("")
    lines.append("## Constraint-event drop rate per sweep")
    lines.append("")
    lines.append("| Sweep | Total events | Retained | Drop rate |")
    lines.append("|---|---|---|---|")
    for label in ("S1", "S2", "S3"):
        d = per_sweep[label]["violation_event_authority_split"]
        lines.append(
            f"| **{label}** | {d['total']} | {d['high_kept']} | "
            f"{d['drop_rate'] * 100:.2f}% |"
        )
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append(
        "* S1 is the published E9 headline. "
        "* S2 (Class I + LOE A only, no IIa, no allergy) is the strictest "
        "filter we believe a reviewer could reasonably demand. "
        "* S3 isolates the contribution of the drug-allergy auto-promotion."
    )
    return "\n".join(lines)


def render_combined_macros(per_sweep: dict[str, dict]) -> str:
    """Combine all per-sweep macros + add a sweep-summary table macro."""
    lines = [
        "% Auto-generated by scripts/experiments/exp_e39b_threshold_sweep.py",
        "% E9 Follow-up F1 -- Authority Threshold Sweep",
    ]
    for label in ("S1", "S2", "S3"):
        lines.append(f"% --- Sweep {label}: {per_sweep[label]['_meta']['sweep_desc']} ---")
        m = per_sweep[label]
        fa_h = m["fa_strict"]["high_authority"]["rate"] * 100
        fa_f = m["fa_strict"]["full_catalogue"]["rate"] * 100
        rl_h = m["replay_detection_loss"]["high_authority"]
        rr = m["ranking_reversal"]
        rl_min = (
            min(v for v in rl_h.values() if v > 0) * 100
            if any(rl_h.values())
            else 0.0
        )
        rl_max = max(rl_h.values()) * 100 if rl_h else 0.0
        lines.append(f"\\newcommand{{\\Enine{label}fastrictfull}}{{{fa_f:.2f}}}")
        lines.append(f"\\newcommand{{\\Enine{label}fastrict}}{{{fa_h:.2f}}}")
        lines.append(f"\\newcommand{{\\Enine{label}replaylossmin}}{{{rl_min:.2f}}}")
        lines.append(f"\\newcommand{{\\Enine{label}replaylossmax}}{{{rl_max:.2f}}}")
        lines.append(
            f"\\newcommand{{\\Enine{label}rankreversal}}{{{rr['rate'] * 100:.2f}}}"
        )
        lines.append(f"\\newcommand{{\\Enine{label}rankreversalcount}}{{{rr['n_reversed']}}}")
        lines.append(f"\\newcommand{{\\Enine{label}rankpaircount}}{{{rr['n_pairs']}}}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N episodes per sweep (dev mode).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ANALYSIS_DIR,
        help="Output directory.",
    )
    args = parser.parse_args()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Building shared episode index (one walk for all 3 sweeps)", flush=True)
    episode_index = build_episode_index(RESULTS_DIRS_DEFAULT)
    print(f"  {len(episode_index)} episodes indexed", flush=True)

    per_sweep: dict[str, dict] = {}
    for label, taxonomy_rel, desc in SWEEPS:
        taxonomy_path = _REPO_ROOT / taxonomy_rel
        if not taxonomy_path.exists():
            raise FileNotFoundError(f"Missing taxonomy: {taxonomy_path}")
        per_sweep[label] = run_sweep(
            label, taxonomy_path, desc, out_dir, args.limit, episode_index
        )

    combined_md = out_dir / "exp_e9_threshold_sweep.md"
    combined_tex = out_dir / "exp_e9_threshold_sweep.tex"
    with open(combined_md, "w") as f:
        f.write(render_combined_md(per_sweep))
    with open(combined_tex, "w") as f:
        f.write(render_combined_macros(per_sweep))
    print(f"\nCombined MD:     {combined_md}")
    print(f"Combined macros: {combined_tex}")

    print("\n=== Headline summary ===")
    for label in ("S1", "S2", "S3"):
        m = per_sweep[label]
        fa = m["fa_strict"]["high_authority"]["rate"] * 100
        mab = m["replay_detection_loss"]["high_authority"]["mab_proxy"] * 100
        rr = m["ranking_reversal"]
        print(
            f"  {label}: FA={fa:.2f}%  "
            f"MAB-loss={mab:.2f}%  "
            f"rev={rr['n_reversed']}/{rr['n_pairs']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
