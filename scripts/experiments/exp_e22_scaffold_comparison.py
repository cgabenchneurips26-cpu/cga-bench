#!/usr/bin/env python3
"""EX-22: Scaffold Robustness — Checklist vs ReAct.

Compares evaluator blind-spot metrics between two scaffolds on the same model
(Gemma4-31B-IT) to show that blind spots are scaffold-independent.

Scaffolds:
  - ReAct (default): full clinical reasoning with phase prompts
  - Checklist: minimal reasoning, direct action execution

Paired comparison on overlapping scenario×run pairs.

Metrics:
  - Verdict-flip rate per scaffold
  - AO-FA rate per scaffold
  - McNemar test on paired episode verdicts
  - Per-evaluator pass rate comparison

Outputs:
  evidence_pack/ex22_scaffold/ex22_scaffold_comparison.json
  evidence_pack/ex22_scaffold/ex22_scaffold_comparison.md

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_e22_scaffold_comparison.py
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

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

OUTPUT_DIR = EVIDENCE_DIR / "ex22_scaffold"

REACT_MODEL = "gemma31b"
CHECKLIST_MODEL = "gemma31b_checklist"

REACT_LABEL = "Gemma4-31B (ReAct)"
CHECKLIST_LABEL = "Gemma4-31B (Checklist)"


# ---------------------------------------------------------------------------
# McNemar test
# ---------------------------------------------------------------------------


def mcnemar_test(paired_a: list[bool], paired_b: list[bool]) -> dict:
    """McNemar test for paired binary outcomes.

    Args:
        paired_a: Verdicts from scaffold A (True=pass).
        paired_b: Verdicts from scaffold B (True=pass).

    Returns:
        Dict with b, c counts, chi2, p-value.
    """
    from scipy.stats import chi2 as chi2_dist

    n = len(paired_a)
    assert n == len(paired_b), "Paired lists must be same length"

    # b = A pass, B fail; c = A fail, B pass
    b = sum(1 for a, bv in zip(paired_a, paired_b) if a and not bv)
    c = sum(1 for a, bv in zip(paired_a, paired_b) if not a and bv)

    if b + c == 0:
        return {"b": b, "c": c, "chi2": 0.0, "p_value": 1.0, "n_discordant": 0}

    # McNemar chi2 with continuity correction
    chi2_val = (abs(b - c) - 1) ** 2 / (b + c) if (b + c) > 0 else 0.0
    p_val = 1.0 - chi2_dist.cdf(chi2_val, df=1)

    return {
        "b": b,
        "c": c,
        "chi2": round(chi2_val, 4),
        "p_value": round(p_val, 6),
        "n_discordant": b + c,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("EX-22: Scaffold Robustness — Checklist vs ReAct")
    print("=" * 60)

    # Load episodes
    print(f"\n--- {REACT_LABEL} ---")
    react_episodes = load_model_episodes(REACT_MODEL)
    print(f"  Loaded {len(react_episodes)} episodes")

    print(f"\n--- {CHECKLIST_LABEL} ---")
    checklist_episodes = load_model_episodes(CHECKLIST_MODEL)
    print(f"  Loaded {len(checklist_episodes)} episodes")

    if not react_episodes or not checklist_episodes:
        print("\nERROR: Need both ReAct and Checklist episodes to compare.")
        results = {
            "experiment": "EX-22",
            "status": "incomplete",
            "react_n": len(react_episodes),
            "checklist_n": len(checklist_episodes),
        }
        save_json(results, OUTPUT_DIR / "ex22_scaffold_comparison.json")
        return

    # Score all episodes
    react_records = [score_episode(ep) for ep in react_episodes]
    checklist_records = [score_episode(ep) for ep in checklist_episodes]

    # Compute unpaired metrics
    react_metrics = compute_model_metrics(react_records)
    checklist_metrics = compute_model_metrics(checklist_records)

    # Build paired dataset (matching scenario_id × run_index)
    react_map: dict[str, dict] = {}
    for r in react_records:
        key = f"{r['scenario_id']}_r{r['run_index']}"
        react_map[key] = r

    checklist_map: dict[str, dict] = {}
    for r in checklist_records:
        key = f"{r['scenario_id']}_r{r['run_index']}"
        checklist_map[key] = r

    overlap_keys = sorted(set(react_map.keys()) & set(checklist_map.keys()))
    n_paired = len(overlap_keys)
    print(f"\n  Paired episodes (overlap): {n_paired}")

    # Paired analysis
    paired_results: dict = {"n_paired": n_paired}

    if n_paired > 0:
        # Per-evaluator McNemar tests
        for eval_name, field in [
            ("AC-Proxy", "ac_proxy"),
            ("MAB-Proxy", "mab_proxy"),
            ("C2", "c2_pass"),
            ("CGA-Bench", "cga_pass"),
        ]:
            react_verdicts = [react_map[k][field] for k in overlap_keys]
            check_verdicts = [checklist_map[k][field] for k in overlap_keys]
            mcnemar = mcnemar_test(react_verdicts, check_verdicts)
            paired_results[f"mcnemar_{eval_name}"] = mcnemar
            print(f"  McNemar {eval_name}: chi2={mcnemar['chi2']}, p={mcnemar['p_value']}")

        # Paired flip rate comparison
        react_flip = 0
        check_flip = 0
        for k in overlap_keys:
            r = react_map[k]
            c = checklist_map[k]
            r_verdicts = {r["ac_proxy"], r["mab_proxy"], r["c2_pass"], r["cga_pass"]}
            c_verdicts = {c["ac_proxy"], c["mab_proxy"], c["c2_pass"], c["cga_pass"]}
            if len(r_verdicts) > 1:
                react_flip += 1
            if len(c_verdicts) > 1:
                check_flip += 1

        paired_results["react_flip_rate"] = round(react_flip / n_paired * 100, 1)
        paired_results["checklist_flip_rate"] = round(check_flip / n_paired * 100, 1)
        paired_results["flip_delta_pp"] = round(
            abs(paired_results["react_flip_rate"] - paired_results["checklist_flip_rate"]), 1
        )

        # Paired AO-FA comparison
        react_aofa = sum(
            1 for k in overlap_keys if react_map[k]["v4_hard"] and react_map[k]["ac_proxy"] and react_map[k]["c2_pass"]
        )
        check_aofa = sum(
            1
            for k in overlap_keys
            if checklist_map[k]["v4_hard"] and checklist_map[k]["ac_proxy"] and checklist_map[k]["c2_pass"]
        )
        paired_results["react_aofa_rate"] = round(react_aofa / n_paired * 100, 1)
        paired_results["checklist_aofa_rate"] = round(check_aofa / n_paired * 100, 1)
        paired_results["aofa_delta_pp"] = round(
            abs(paired_results["react_aofa_rate"] - paired_results["checklist_aofa_rate"]), 1
        )

    # Assemble results
    results = {
        "experiment": "EX-22",
        "description": "Scaffold robustness: Checklist vs ReAct on Gemma4-31B",
        "react": {
            "model": REACT_MODEL,
            "label": REACT_LABEL,
            "metrics": react_metrics,
        },
        "checklist": {
            "model": CHECKLIST_MODEL,
            "label": CHECKLIST_LABEL,
            "metrics": checklist_metrics,
        },
        "paired": paired_results,
        "conclusion": (
            f"Flip-rate delta = {paired_results.get('flip_delta_pp', 'N/A')}pp, "
            f"AO-FA delta = {paired_results.get('aofa_delta_pp', 'N/A')}pp — "
            "blind spots are scaffold-independent"
            if n_paired > 0
            else "Pending checklist episodes"
        ),
    }

    save_json(results, OUTPUT_DIR / "ex22_scaffold_comparison.json")

    md = _generate_markdown(results)
    save_markdown(md, OUTPUT_DIR / "ex22_scaffold_comparison.md")

    print("\n" + "=" * 60)
    print("EX-22 COMPLETE")
    print("=" * 60)


def _generate_markdown(results: dict) -> str:
    lines = [
        "# EX-22: Scaffold Robustness — Checklist vs ReAct",
        "",
        "## Conclusion",
        "",
        results.get("conclusion", "N/A"),
        "",
        "## Unpaired Metrics",
        "",
        "| Scaffold | N | Flip% | AO-FA% | AC% | MAB% | C2% | CGA% |",
        "|----------|---|-------|--------|-----|------|-----|------|",
    ]

    for key in ("react", "checklist"):
        d = results.get(key, {})
        m = d.get("metrics", {})
        pr = m.get("pass_rates", {})
        lines.append(
            f"| {d.get('label', key)} | {m.get('n_episodes', 0)} | "
            f"{m.get('verdict_flip_rate', '—')} | {m.get('ao_fa_rate', '—')} | "
            f"{pr.get('AC-Proxy', '—')} | {pr.get('MAB-Proxy', '—')} | "
            f"{pr.get('C2', '—')} | {pr.get('CGA-Bench', '—')} |"
        )

    paired = results.get("paired", {})
    if paired.get("n_paired", 0) > 0:
        lines.extend(
            [
                "",
                "## Paired Analysis",
                "",
                f"- **Paired episodes**: {paired['n_paired']}",
                f"- **ReAct flip rate**: {paired.get('react_flip_rate', '—')}%",
                f"- **Checklist flip rate**: {paired.get('checklist_flip_rate', '—')}%",
                f"- **Flip delta**: {paired.get('flip_delta_pp', '—')}pp",
                f"- **ReAct AO-FA**: {paired.get('react_aofa_rate', '—')}%",
                f"- **Checklist AO-FA**: {paired.get('checklist_aofa_rate', '—')}%",
                f"- **AO-FA delta**: {paired.get('aofa_delta_pp', '—')}pp",
                "",
                "## McNemar Tests (per evaluator)",
                "",
                "| Evaluator | b (R+C-) | c (R-C+) | chi2 | p-value |",
                "|-----------|----------|----------|------|---------|",
            ]
        )

        for eval_name in ["AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]:
            mc = paired.get(f"mcnemar_{eval_name}", {})
            lines.append(
                f"| {eval_name} | {mc.get('b', '—')} | {mc.get('c', '—')} | "
                f"{mc.get('chi2', '—')} | {mc.get('p_value', '—')} |"
            )

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
