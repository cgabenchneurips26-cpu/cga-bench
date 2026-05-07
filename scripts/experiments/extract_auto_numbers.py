#!/usr/bin/env python3
"""Extract all E1–E5 numbers from JSON evidence packs and update auto_numbers.tex.

Reads:
    evidence_pack/exp_e1_verdict_flip.json
    evidence_pack/exp_e2_bsr.json
    evidence_pack/exp_e3_instrumentation_ablation.json
    evidence_pack/exp_e4_operating_point.json
    evidence_pack/exp_e5_evaluator_expansion.json

Writes:
    evidence_pack/extracted_numbers.json   — all values + provenance
    paper/auto_numbers.tex                 — updated LaTeX macros
"""

from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence_pack"
TEX_PATH = ROOT / "paper" / "auto_numbers.tex"

N_EPISODES: int = 0  # set dynamically from E1 JSON


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct(x: float) -> float:
    """Round percentage to 1 decimal."""
    return round(x * 100, 1)


def _r4(x: float) -> float:
    """Round to 4 decimals."""
    return round(x, 4)


def _r3(x: float) -> float:
    """Round to 3 decimals."""
    return round(x, 3)


def _r1(x: float) -> float:
    """Round to 1 decimal."""
    return round(x, 1)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract_all() -> dict[str, dict]:
    """Extract all numbers from E1–E5 JSONs.

    Returns:
        dict mapping macro_name -> {"value": ..., "source": "file.json > key.path"}
    """
    numbers: dict[str, dict] = {}

    def add(name: str, value: float | int | str, source: str) -> None:
        numbers[name] = {"value": value, "source": source}

    # === E1: Verdict-Flip ===
    global N_EPISODES
    with open(EVIDENCE / "exp_e1_verdict_flip.json") as f:
        e1 = json.load(f)
    N_EPISODES = e1["n_episodes"]

    flip = e1["flip_results"]
    fa = e1["false_accept_results"]
    med = e1["median_viols_in_fa_episodes"]

    add("verdictFlipRate", _r1(flip["flip_fraction"] * 100), "exp_e1 > flip_results.flip_fraction * 100")
    add("verdictFlipCount", flip["flip_count"], "exp_e1 > flip_results.flip_count")

    # Per-evaluator FA rates
    add(
        "faAC",
        _r1(fa["per_evaluator"]["AC-Proxy"]["fa_rate"] * 100),
        "exp_e1 > false_accept_results.per_evaluator.AC-Proxy.fa_rate * 100",
    )
    add(
        "faMAB",
        _r1(fa["per_evaluator"]["MAB-Proxy"]["fa_rate"] * 100),
        "exp_e1 > false_accept_results.per_evaluator.MAB-Proxy.fa_rate * 100",
    )
    add(
        "faCTwo",
        _r1(fa["per_evaluator"]["C2"]["fa_rate"] * 100),
        "exp_e1 > false_accept_results.per_evaluator.C2.fa_rate * 100",
    )
    add(
        "faCGA",
        _r1(fa["per_evaluator"]["CGA-Bench"]["fa_rate"] * 100),
        "exp_e1 > false_accept_results.per_evaluator.CGA-Bench.fa_rate * 100",
    )

    # Per-evaluator FA absolute counts
    add(
        "faNAC",
        fa["per_evaluator"]["AC-Proxy"]["fa_count"],
        "exp_e1 > false_accept_results.per_evaluator.AC-Proxy.fa_count",
    )
    add(
        "faNMAB",
        fa["per_evaluator"]["MAB-Proxy"]["fa_count"],
        "exp_e1 > false_accept_results.per_evaluator.MAB-Proxy.fa_count",
    )
    add("faNCTwo", fa["per_evaluator"]["C2"]["fa_count"], "exp_e1 > false_accept_results.per_evaluator.C2.fa_count")
    add(
        "faNCGA",
        fa["per_evaluator"]["CGA-Bench"]["fa_count"],
        "exp_e1 > false_accept_results.per_evaluator.CGA-Bench.fa_count",
    )

    # All-oblivious FA
    add(
        "faAllOblivious",
        _r1(fa["all_oblivious_fa_rate"] * 100),
        "exp_e1 > false_accept_results.all_oblivious_fa_rate * 100",
    )
    add("faAllObliviousCount", fa["all_oblivious_fa_count"], "exp_e1 > false_accept_results.all_oblivious_fa_count")

    # Median viols in FA
    add(
        "medianViolFalseAccept",
        med["AC-Proxy"]["median_n_viols"],
        "exp_e1 > median_viols_in_fa_episodes.AC-Proxy.median_n_viols",
    )
    add(
        "medViolFaMAB",
        med["MAB-Proxy"]["median_n_viols"],
        "exp_e1 > median_viols_in_fa_episodes.MAB-Proxy.median_n_viols",
    )
    add("medViolFaCTwo", med["C2"]["median_n_viols"], "exp_e1 > median_viols_in_fa_episodes.C2.median_n_viols")

    # Pairwise disagreement counts and rates
    pairs = flip["pair_disagreement_counts"]
    pair_map = {
        "vfACvsMAB": "AC-Proxy vs MAB-Proxy",
        "vfACvsCTwo": "AC-Proxy vs C2",
        "vfACvsCGA": "AC-Proxy vs CGA-Bench",
        "vfMABvsCTwo": "MAB-Proxy vs C2",
        "vfMABvsCGA": "MAB-Proxy vs CGA-Bench",
        "vfCTwovsCGA": "C2 vs CGA-Bench",
    }
    for macro, pair_key in pair_map.items():
        count = pairs[pair_key]
        add(macro, count, f"exp_e1 > flip_results.pair_disagreement_counts.{pair_key}")
        add(macro + "Pct", _r1(count / N_EPISODES * 100), f"computed: {pair_key} count / {N_EPISODES} * 100")

    add("pairDisagreeMax", max(pairs.values()), "exp_e1 > max(pair_disagreement_counts)")

    # === E2: BSR ===
    with open(EVIDENCE / "exp_e2_bsr.json") as f:
        e2 = json.load(f)

    bsr = e2["bsr_results"]
    bsr_ct = e2["bsr_by_constraint_type"]

    ev_macro_map = {
        "DxEM": "DxEM",
        "AC-Proxy": "AC",
        "MAB-Proxy": "MAB",
        "C2 (>=0.7)": "CTwo",
        "ACov (>=0.5)": "ACov",
        "CGA-Bench": "CGA",
    }
    for ev_key, macro_suffix in ev_macro_map.items():
        d = bsr[ev_key]
        add(f"bsr{macro_suffix}", _r1(d["bsr_rate"] * 100), f"exp_e2 > bsr_results.{ev_key}.bsr_rate * 100")
        add(f"bsrN{macro_suffix}", d["bsr_count"], f"exp_e2 > bsr_results.{ev_key}.bsr_count")
        add(f"medDg{macro_suffix}", d["median_n_viols"], f"exp_e2 > bsr_results.{ev_key}.median_n_viols")

    # Min BSR among process-oblivious (DxEM, AC, C2)
    oblivious_bsr = [
        bsr["DxEM"]["bsr_rate"],
        bsr["AC-Proxy"]["bsr_rate"],
        bsr["C2 (>=0.7)"]["bsr_rate"],
    ]
    add("bsrMinOblivious", _r1(min(oblivious_bsr) * 100), "computed: min(DxEM, AC, C2) BSR * 100")
    add("bsrMaxOblivious", _r1(max(oblivious_bsr) * 100), "computed: max(DxEM, AC, C2) BSR * 100")

    # === E3: Instrumentation Ablation ===
    with open(EVIDENCE / "exp_e3_instrumentation_ablation.json") as f:
        e3 = json.load(f)

    summ = e3["summaries"]
    vloss = e3["violation_loss"]

    full_hard = summ["full"]["n_hard"]
    add("instrFullHard", full_hard, "exp_e3 > summaries.full.n_hard")
    add("instrFullHardRate", _r1(summ["full"]["hard_rate"] * 100), "exp_e3 > summaries.full.hard_rate * 100")

    # Per-condition hard counts and loss rates
    cond_macro_map = {
        "no_timestamps": "NoTime",
        "no_ordering": "NoOrder",
        "no_state": "NoState",
        "terminal_only": "Terminal",
    }
    for cond_key, macro_suffix in cond_macro_map.items():
        n_hard_cond = summ[cond_key]["n_hard"]
        add(f"instrHard{macro_suffix}", n_hard_cond, f"exp_e3 > summaries.{cond_key}.n_hard")

        if full_hard > 0:
            loss_pct = _r1((full_hard - n_hard_cond) / full_hard * 100)
            retain_pct = _r1(n_hard_cond / full_hard * 100)
        else:
            loss_pct = 0.0
            retain_pct = 0.0
        add(f"instr{macro_suffix}Loss", loss_pct, f"computed: (full_hard - {cond_key}_hard) / full_hard * 100")
        add(f"instr{macro_suffix}Retain", retain_pct, f"computed: {cond_key}_hard / full_hard * 100")

    # Convenience aliases matching original spec names
    add("instrTimingLoss", numbers["instrNoTimeLoss"]["value"], "alias: instrNoTimeLoss")
    add("instrTimingRetain", numbers["instrNoTimeRetain"]["value"], "alias: instrNoTimeRetain")
    add("instrOrderLoss", numbers["instrNoOrderLoss"]["value"], "alias: instrNoOrderLoss")
    add("instrOrderRetain", numbers["instrNoOrderRetain"]["value"], "alias: instrNoOrderRetain")
    add("instrStateLoss", numbers["instrNoStateLoss"]["value"], "alias: instrNoStateLoss")
    add("instrStateRetain", numbers["instrNoStateRetain"]["value"], "alias: instrNoStateRetain")
    add("instrTerminalRetain", numbers["instrTerminalRetain"]["value"], "alias: instrTerminalRetain (should be 0)")

    # Violation counts lost per condition
    for cond_key, macro_suffix in cond_macro_map.items():
        vl = vloss[cond_key]
        for vtype in ["FORBIDDEN", "WITHIN", "BEFORE"]:
            add(
                f"instrViolLost{vtype.capitalize()}{macro_suffix}",
                vl.get(vtype, 0),
                f"exp_e3 > violation_loss.{cond_key}.{vtype}",
            )

    # Aggregate violation losses for no-timestamps (the main ablation)
    add("instrViolLostWithin", vloss["no_timestamps"]["WITHIN"], "exp_e3 > violation_loss.no_timestamps.WITHIN")
    add("instrViolLostBefore", vloss["no_timestamps"]["BEFORE"], "exp_e3 > violation_loss.no_timestamps.BEFORE")
    add("instrViolLostForbidden", vloss["no_state"]["FORBIDDEN"], "exp_e3 > violation_loss.no_state.FORBIDDEN")

    # BSR per condition per evaluator
    cond_eval_keys = ["dxem", "ac_proxy", "mab_proxy", "c2_pass", "acov_pass"]
    cond_eval_macros = ["DxEM", "AC", "MAB", "CTwo", "ACov"]
    for cond_key, cond_suffix in cond_macro_map.items():
        bsr_cond = summ[cond_key]["bsr_by_evaluator"]
        for eval_key, eval_suffix in zip(cond_eval_keys, cond_eval_macros):
            val = bsr_cond.get(eval_key, 0.0)
            add(
                f"bsr{cond_suffix}{eval_suffix}",
                _r1(val * 100),
                f"exp_e3 > summaries.{cond_key}.bsr_by_evaluator.{eval_key} * 100",
            )

    # === E4: Operating-Point Matched Disagreement ===
    with open(EVIDENCE / "exp_e4_operating_point.json") as f:
        e4 = json.load(f)

    op_names = {"0.3": "Thirty", "0.4": "Forty", "0.5": "Fifty"}
    for op_str, op_suffix in op_names.items():
        op = e4["operating_points"][op_str]
        add(
            f"fleissKappaMatched{op_suffix}",
            _r3(op["fleiss_kappa"]),
            f"exp_e4 > operating_points.{op_str}.fleiss_kappa",
        )
        add(
            f"verdictFlipRateMatched{op_suffix}",
            _r1(op["verdict_flip_rate"] * 100),
            f"exp_e4 > operating_points.{op_str}.verdict_flip_rate * 100",
        )

        # Pairwise kappas at each operating point
        pw = op["pairwise_kappa"]
        for pair_key, pair_macro in pair_map.items():
            latex_name = pair_key.replace("vf", "kappa") + f"Op{op_suffix}"
            pair_label = pair_macro  # e.g. "AC-Proxy vs MAB-Proxy"
            if pair_label in pw:
                add(latex_name, _r3(pw[pair_label]), f"exp_e4 > operating_points.{op_str}.pairwise_kappa.{pair_label}")

        # Actual pass rates
        for ev_name, ev_rate in op.get("actual_pass_rates", {}).items():
            ev_short = ev_name.replace("-Proxy", "").replace("-Bench", "").replace("-", "")
            add(
                f"opPassRate{ev_short}{op_suffix}",
                _r1(ev_rate * 100),
                f"exp_e4 > operating_points.{op_str}.actual_pass_rates.{ev_name} * 100",
            )

    add("clusterPreservedE4", e4["cluster_preserved"], "exp_e4 > cluster_preserved")

    # Representative values (OP 0.5 as default)
    add(
        "fleissKappaMatched",
        _r3(e4["operating_points"]["0.5"]["fleiss_kappa"]),
        "exp_e4 > operating_points.0.5.fleiss_kappa (representative)",
    )
    add(
        "verdictFlipRateMatched",
        _r1(e4["operating_points"]["0.5"]["verdict_flip_rate"] * 100),
        "exp_e4 > operating_points.0.5.verdict_flip_rate * 100 (representative)",
    )
    add(
        "kappaACvsCGAMatched",
        _r3(e4["operating_points"]["0.5"]["pairwise_kappa"]["AC-Proxy vs CGA-Bench"]),
        "exp_e4 > operating_points.0.5.pairwise_kappa.AC-Proxy vs CGA-Bench",
    )

    # === E5: Evaluator Expansion + Cluster Stability ===
    with open(EVIDENCE / "exp_e5_evaluator_expansion.json") as f:
        e5 = json.load(f)

    add("numEvaluatorsExpanded", len(e5["variants"]), "exp_e5 > len(variants)")
    add("numClusters", e5["optimal_clusters"], "exp_e5 > optimal_clusters")
    add("cophenetic", _r3(e5["cophenetic_correlation"]), "exp_e5 > cophenetic_correlation")
    add("silhouetteScore", _r3(float(e5["silhouette_scores"]["2"])), "exp_e5 > silhouette_scores.2")
    add("bootstrapARI", _r3(e5["bootstrap_ari"]["mean"]), "exp_e5 > bootstrap_ari.mean")
    add("bootstrapARILow", _r3(e5["bootstrap_ari"]["ci_95"][0]), "exp_e5 > bootstrap_ari.ci_95[0]")
    add("bootstrapARIHigh", _r3(e5["bootstrap_ari"]["ci_95"][1]), "exp_e5 > bootstrap_ari.ci_95[1]")
    add("clusterPreservedPct", _r1(e5["cluster_preserved_pct"]), "exp_e5 > cluster_preserved_pct")
    add("nBootstrap", e5["bootstrap_ari"]["n_bootstrap"], "exp_e5 > bootstrap_ari.n_bootstrap")

    # Per-variant pass rates
    def _latex_safe(raw: str) -> str:
        """Convert evaluator variant name to valid LaTeX macro suffix."""
        return raw.replace("@", "At").replace("-", "").replace("(", "").replace(")", "").replace(".", "p")

    for v in e5["variants"]:
        safe_name = _latex_safe(v["name"])
        add(f"passRate{safe_name}", _r1(v["pass_rate"] * 100), f"exp_e5 > variants[name={v['name']}].pass_rate * 100")

    # Cluster assignments
    for name, cluster in e5["cluster_assignments"].items():
        safe_name = _latex_safe(name)
        add(f"cluster{safe_name}", cluster, f"exp_e5 > cluster_assignments.{name}")

    return numbers


# ---------------------------------------------------------------------------
# LaTeX generation
# ---------------------------------------------------------------------------


def update_tex(numbers: dict[str, dict]) -> None:
    """Update auto_numbers.tex with all extracted numbers."""
    content = TEX_PATH.read_text()

    # Collect existing macro names
    existing = set(re.findall(r"\\newcommand\{\\(\w+)\}", content))

    # Build update and new blocks
    updated_count = 0
    new_macros: list[str] = []

    for name, info in sorted(numbers.items()):
        val = info["value"]
        # Format value
        if isinstance(val, bool):
            val_str = "true" if val else "false"
        elif isinstance(val, float) or isinstance(val, int):
            val_str = str(val)
        else:
            val_str = str(val)

        if name in existing:
            comment = info.get("source", "") or info.get("comment", "")
            comment_str = f"  % {comment}" if comment else ""
            pattern = re.compile(r"\\newcommand\{\\" + re.escape(name) + r"\}\{[^}]*\}(?:[ \t]*%[^\n]*)?")
            replacement = rf"\\newcommand{{\\{name}}}{{{val_str}}}{comment_str}"
            new_content = pattern.sub(replacement, content)
            if new_content != content:
                content = new_content
                updated_count += 1
        else:
            new_macros.append(name)

    # Append new macros at end if any
    if new_macros:
        lines = [
            "",
            "% ---------------------------------------------------------------------------",
            "% Auto-extracted from E1-E5 JSONs (extract_auto_numbers.py)",
            "% ---------------------------------------------------------------------------",
        ]
        # Group by prefix
        sections = {
            "E1: Verdict-Flip": ["verdictFlip", "fa", "med", "vf", "pair"],
            "E2: BSR": ["bsr", "medDg"],
            "E3: Instrumentation Ablation": ["instr"],
            "E4: Operating-Point": ["fleiss", "verdict", "kappa", "op", "cluster"],
            "E5: Evaluator Expansion": [
                "numEval",
                "numClust",
                "coph",
                "silhouette",
                "bootstrap",
                "nBoot",
                "passRate",
                "cluster",
            ],
        }

        added = set()
        for section_name, prefixes in sections.items():
            section_macros = []
            for name in new_macros:
                if name in added:
                    continue
                if any(name.startswith(p) for p in prefixes):
                    section_macros.append(name)
                    added.add(name)
            if section_macros:
                lines.append(f"\n% {section_name}")
                for name in sorted(section_macros):
                    info = numbers[name]
                    val = info["value"]
                    if isinstance(val, bool):
                        val_str = "true" if val else "false"
                    elif isinstance(val, float):
                        val_str = str(val)
                    else:
                        val_str = str(val)
                    lines.append(f"\\newcommand{{\\{name}}}{{{val_str}}}  % {info['source']}")

        # Any remaining
        remaining = [n for n in new_macros if n not in added]
        if remaining:
            lines.append("\n% Other")
            for name in sorted(remaining):
                info = numbers[name]
                val = info["value"]
                val_str = str(val) if not isinstance(val, bool) else ("true" if val else "false")
                lines.append(f"\\newcommand{{\\{name}}}{{{val_str}}}  % {info['source']}")

        content += "\n".join(lines) + "\n"

    TEX_PATH.write_text(content)
    print(f"  Updated {updated_count} existing macros")
    print(f"  Added {len(new_macros)} new macros")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Extract numbers and update auto_numbers.tex."""
    print("=" * 70)
    print("Extract Auto-Numbers from E1–E5 Evidence Packs")
    print("=" * 70)

    numbers = extract_all()
    print(f"\nExtracted {len(numbers)} values total")

    # Save extracted_numbers.json
    out_path = EVIDENCE / "extracted_numbers.json"
    with open(out_path, "w") as f:
        json.dump(numbers, f, indent=2, default=str)
    print(f"  Saved: {out_path}")

    # Update tex
    print("\nUpdating auto_numbers.tex...")
    update_tex(numbers)

    # Print all macros for verification
    print(f"\n{'=' * 70}")
    print("LaTeX macros (for copy-paste / verification):")
    print(f"{'=' * 70}")
    for name in sorted(numbers.keys()):
        info = numbers[name]
        val = info["value"]
        val_str = str(val) if not isinstance(val, bool) else ("true" if val else "false")
        print(f"  \\{name}{{{val_str}}}  % {info['source']}")


if __name__ == "__main__":
    main()
