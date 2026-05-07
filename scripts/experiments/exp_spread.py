#!/usr/bin/env python3
"""EXP-SPREAD: Domain-level violation spread for Table 4.

Uses Exp11 canonical data to aggregate UP rates by domain.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP11_FILE = ROOT / "evidence_pack" / "additional" / "event_level" / "event_level_hardviol_v2.json"
SPREAD_FILE = ROOT / "evidence_pack" / "analysis" / "v3_violation_spread.json"
OUTPUT_DIR = ROOT / "tracking"

# Paper uses 6 domains. Map 15 scenarios:
SCENARIO_DOMAIN = {
    "dka_moderate_basic": "DKA",
    "dka_hypokalemia_trap": "DKA",
    "septic_shock_basic": "Sepsis",
    "septic_shock_penicillin_allergy": "Sepsis",
    "stemi_inferior_rv_trap": "ACS",
    "aki_stage1_basic": "AKI",
    "contrast_aki_prevention_basic": "AKI",
    "stroke_tpa_eligible": "Stroke",
    "hemorrhagic_stroke": "Stroke",
    "adhf_warm_wet": "Others",
    "af_new_onset_basic": "Others",
    "copd_moderate_exacerbation": "Others",
    "htn_emergency_basic": "Others",
    "pe_submassive_basic": "Others",
    "gi_bleeding_upper_basic": "Others",
}

DOMAIN_ORDER = ["DKA", "Sepsis", "ACS", "AKI", "Stroke", "Others"]

MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]


def main() -> None:
    # Load Exp11 per-episode data
    with open(EXP11_FILE) as f:
        exp11 = json.load(f)

    episodes = exp11["all_episode_constraints"]
    print(f"Loaded {len(episodes)} episodes from Exp11")

    # Load CGA spread for mean CGA per domain
    with open(SPREAD_FILE) as f:
        spread = json.load(f)

    # --- Step 1: Build episode lookup with C2 ---
    # We need C2 from the rescored episodes. Exp11 has c2 field.
    # Classify each episode
    domain_data: dict[str, dict] = {d: {
        "scenarios": set(),
        "episodes": [],
        "cp_episodes": [],
        "strong_scenarios": set(),
        "viol_types": set(),
    } for d in DOMAIN_ORDER}

    for ec in episodes:
        scen = ec["scenario"]
        domain = SCENARIO_DOMAIN.get(scen)
        if not domain:
            print(f"WARNING: no domain for {scen}")
            continue

        dd = domain_data[domain]
        dd["scenarios"].add(scen)
        dd["episodes"].append(ec)

        if ec["c2"] >= 0.7:
            dd["cp_episodes"].append(ec)

        # Track violation types from Exp11 constraint violations
        for v in ec.get("constraint_violations", []):
            ctype = v.get("constraint_type", "")
            if ctype == "FORBIDDEN":
                dd["viol_types"].add("Forbidden")
            elif ctype == "WITHIN":
                dd["viol_types"].add("Timing")
            elif ctype == "BEFORE":
                dd["viol_types"].add("Sequence")

        # Track scenarios with strong violations
        if ec["has_severe"]:  # has_severe = CRITICAL or SEVERE = UP_strong
            dd["strong_scenarios"].add(scen)

    # --- Step 2: Compute domain aggregates ---
    print("\n=== Domain Aggregation (Exp11 Canonical) ===\n")
    results = []
    total_strong_domains = 0
    total_strong_scenarios = 0
    timing_domains = 0

    for domain in DOMAIN_ORDER:
        dd = domain_data[domain]
        n_scen = len(dd["scenarios"])
        n_strong_scen = len(dd["strong_scenarios"])
        n_ep = len(dd["episodes"])
        n_cp = len(dd["cp_episodes"])
        n_up_strong = sum(1 for e in dd["cp_episodes"] if e["has_severe"])
        n_up_crit = sum(1 for e in dd["cp_episodes"] if e["has_critical"])
        up_strong_rate = n_up_strong / n_cp if n_cp > 0 else 0
        up_crit_rate = n_up_crit / n_cp if n_cp > 0 else 0
        viol_types = sorted(dd["viol_types"])

        if n_strong_scen > 0:
            total_strong_domains += 1
        total_strong_scenarios += n_strong_scen
        if "Timing" in dd["viol_types"]:
            timing_domains += 1

        row = {
            "domain": domain,
            "n_scenarios": n_scen,
            "n_strong_scenarios": n_strong_scen,
            "n_episodes": n_ep,
            "n_cp": n_cp,
            "up_strong_count": n_up_strong,
            "up_strong_rate": round(up_strong_rate, 3),
            "up_crit_count": n_up_crit,
            "up_crit_rate": round(up_crit_rate, 3),
            "viol_types": viol_types,
        }
        results.append(row)

        vtypes_str = ", ".join(viol_types) if viol_types else "---"
        print(f"{domain:8s}: {n_strong_scen}/{n_scen} scen, "
              f"UP_strong={n_up_strong}/{n_cp} ({up_strong_rate:.0%}), "
              f"UP_crit={n_up_crit}/{n_cp} ({up_crit_rate:.0%}), "
              f"types=[{vtypes_str}]")

    # --- Step 3: Domain mean CGA ---
    print("\n=== Domain Mean CGA (from V3/P6 spread) ===\n")
    cga_matrix = spread.get("heatmaps", {}).get("cga_matrix", {})

    domain_cga: dict[str, list[float]] = defaultdict(list)
    for scen, model_vals in cga_matrix.items():
        domain = SCENARIO_DOMAIN.get(scen, "Unknown")
        for m, val in model_vals.items():
            domain_cga[domain].append(val)

    domain_mean_cga = {}
    for d in DOMAIN_ORDER:
        vals = domain_cga.get(d, [])
        mean_cga = sum(vals) / len(vals) if vals else 0
        domain_mean_cga[d] = round(mean_cga, 3)
        print(f"  {d}: mean CGA = {mean_cga:.3f} (n={len(vals)} episode-model pairs)")

    # Sort by difficulty
    sorted_by_cga = sorted(domain_mean_cga.items(), key=lambda x: x[1])
    easiest = sorted_by_cga[-1]
    hardest = sorted_by_cga[0]

    # --- Step 4: Generate LaTeX ---
    print("\n=== LaTeX Table 4 ===\n")

    latex_lines = []
    for r in results:
        vtypes = ", ".join(r["viol_types"]) if r["viol_types"] else "---"
        rate_str = f'{r["up_strong_rate"]*100:.0f}\\%' if r["n_cp"] > 0 else "---"
        latex_lines.append(
            f'    {r["domain"]:<8s} & {r["n_strong_scenarios"]}/{r["n_scenarios"]}  '
            f'& {rate_str} & {vtypes} \\\\'
        )

    latex = f"""\\begin{{tabular}}{{lccl}}
  \\toprule
  \\textbf{{Domain}} & \\textbf{{Scen.\\ w/ viol.}}
    & $\\mathrm{{UP}}_{{\\mathrm{{strong}}}}$
    & \\textbf{{Violation types}} \\\\
  \\midrule
{chr(10).join(latex_lines)}
  \\bottomrule
\\end{{tabular}}"""

    print(latex)

    # --- Step 5: Generate prose ---
    print("\n=== Prose for Table 4 caption area ===\n")

    prose = (
        f"Critical violations (forbidden drug) are concentrated in DKA.\n"
        f"Timing violations are distributed across {timing_domains}~domains.\n"
        f"Domain difficulty ranges from {easiest[0]} (mean CGA {easiest[1]:.2f}) to\n"
        f"{hardest[0]} (mean CGA {hardest[1]:.2f}).\n"
        f"The benchmark is strongest for time-critical acute-care scenarios\n"
        f"with dense constraint specifications."
    )
    print(prose)

    print("\n=== Intro values (B12, B13) ===\n")
    print(f"Guideline-strong violations occur in {total_strong_domains}/6~domains "
          f"and {total_strong_scenarios}/15~scenarios")

    # --- Save ---
    output = {
        "domain_results": results,
        "domain_mean_cga": domain_mean_cga,
        "summary": {
            "strong_domains": total_strong_domains,
            "strong_scenarios": total_strong_scenarios,
            "timing_domains": timing_domains,
            "easiest_domain": easiest,
            "hardest_domain": hardest,
        },
        "latex_table4": latex,
        "prose": prose,
        "intro_b12_b13": f"{total_strong_domains}/6 domains, {total_strong_scenarios}/15 scenarios",
    }

    out_file = OUTPUT_DIR / "exp_spread_results.json"
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved: {out_file}")


if __name__ == "__main__":
    main()
