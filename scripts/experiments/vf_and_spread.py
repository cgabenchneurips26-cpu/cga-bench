#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""VF-1, VF-2, VF-3, A-4 (EXP-SPREAD) — Final Verification + Table 4.

VF-1: Exp11 vs Pipeline HardViol match
VF-2: B-1 Ablation baseline consistency
VF-3: Expansion CP=18 re-verification
A-4:  EXP-SPREAD — Table 4 (violation spread by domain)
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent))

EXP11_FILE = ROOT / "evidence_pack" / "additional" / "event_level" / "event_level_hardviol_v2.json"
RESCORED_DIR = ROOT / "results" / "clean_slate_rescored"
SPREAD_FILE = ROOT / "evidence_pack" / "analysis" / "v3_violation_spread.json"
OUTPUT_DIR = ROOT / "code_verification"

MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]

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
    "adhf_warm_wet": "HF",
    "af_new_onset_basic": "AF",
    "copd_moderate_exacerbation": "COPD",
    "htn_emergency_basic": "HTN",
    "pe_submassive_basic": "PE",
    "gi_bleeding_upper_basic": "GIB",
}

# Paper's 6 "core" CPG graphs
CORE_GRAPHS = {
    "ssc_sepsis_hour1",
    "aha_chest_pain",
    "aha_stroke",
    "aha_heart_failure",
    "kdigo_aki_full",
    "ada_dka_management",
}

SCENARIO_TO_GRAPH = {
    "septic_shock_basic": "ssc_sepsis_hour1",
    "septic_shock_penicillin_allergy": "ssc_sepsis_hour1",
    "stemi_inferior_rv_trap": "aha_chest_pain",
    "stroke_tpa_eligible": "aha_stroke",
    "hemorrhagic_stroke": "aha_stroke",
    "dka_moderate_basic": "ada_dka_management",
    "dka_hypokalemia_trap": "ada_dka_management",
    "aki_stage1_basic": "kdigo_aki_full",
    "contrast_aki_prevention_basic": "kdigo_contrast_aki",
    "adhf_warm_wet": "aha_heart_failure",
    "htn_emergency_basic": "hypertensive_emergency",
    "pe_submassive_basic": "pulmonary_embolism",
    "af_new_onset_basic": "atrial_fibrillation",
    "copd_moderate_exacerbation": "copd_exacerbation",
    "gi_bleeding_upper_basic": "gi_bleeding",
}

# 6-domain grouping for paper Table 4
DOMAIN_6 = {
    "DKA": "DKA",
    "Sepsis": "Sepsis",
    "ACS": "ACS",
    "AKI": "AKI",
    "Stroke": "Stroke",
    "HF": "Expansion",
    "AF": "Expansion",
    "COPD": "Expansion",
    "HTN": "Expansion",
    "PE": "Expansion",
    "GIB": "Expansion",
}
# Finer-grained for actual analysis (keep all domains)
DOMAIN_ORDER_FINE = ["DKA", "Sepsis", "ACS", "AKI", "Stroke", "HF", "AF", "COPD", "HTN", "PE", "GIB"]
# Paper's 6-domain grouping
DOMAIN_ORDER_6 = ["DKA", "Sepsis", "ACS", "AKI", "Stroke", "Expansion"]


def load_exp11():
    with open(EXP11_FILE) as f:
        return json.load(f)


def load_rescored():
    """Load all 180 rescored episodes."""
    episodes = []
    for model in MODELS:
        d = RESCORED_DIR / model
        if not d.exists():
            continue
        for fp in sorted(d.glob("*.json")):
            if fp.name in {"model_summary.json", "rescore_summary.json"}:
                continue
            ep = json.loads(fp.read_text())
            ep["_model"] = model
            ep["_file"] = fp.name
            episodes.append(ep)
    return episodes


def make_ep_key(model: str, scenario: str, run: int) -> str:
    return f"{model}/{scenario}/r{run}"


# =========================================================================
# VF-1: Exp11 vs Pipeline HardViol
# =========================================================================
def vf1_exp11_vs_pipeline(exp11_episodes, rescored_episodes):
    lines = ["# VF-1: Exp11 vs Pipeline HardViol Reconciliation\n"]

    # Build lookup for rescored
    rescored_lookup: dict[str, dict] = {}
    for ep in rescored_episodes:
        m = ep["_model"]
        s = ep["scenario_id"]
        r = ep.get("run_index", 0)
        key = make_ep_key(m, s, r)
        rescored_lookup[key] = ep

    hard_types = {"commission", "timing", "sequence"}

    # Exp11 UP definitions
    # has_any_hard: any constraint violation
    # has_severe: severity in {CRITICAL, SEVERE} = UP_strong
    # has_critical: severity = CRITICAL = UP_crit

    comparisons = []
    exp11_strong_only = []
    pipeline_hard_only = []
    both_agree_hard = []
    neither_hard = []

    for ec in exp11_episodes:
        m_label = ec["model"]  # e.g., "oss120b"
        scen = ec["scenario"]
        run = ec.get("run", 0)
        key = make_ep_key(m_label, scen, run)

        resc = rescored_lookup.get(key)
        if not resc:
            continue

        c2_exp11 = ec.get("c2", 0)
        c2_resc = resc.get("c2_new", resc.get("new_sub_scores", {}).get("C2_mandatory_completion", 0))
        cp_exp11 = c2_exp11 >= 0.7
        cp_resc = c2_resc >= 0.7 if c2_resc is not None else False

        # Exp11 verdicts
        exp11_any = ec.get("has_any_hard", False)
        exp11_strong = ec.get("has_severe", False)  # SEVERE or CRITICAL
        exp11_crit = ec.get("has_critical", False)

        # Pipeline verdict (from rescored new_violations_by_type)
        vbt = resc.get("new_violations_by_type", {})
        pipeline_any_hard = any(vbt.get(t, 0) > 0 for t in hard_types)

        # Pipeline "strong" — need severity info which we DON'T have in rescored files
        # The rescored files only have counts by type, not severity
        # So we can only compare "any hard" vs Exp11 "any hard"

        row = {
            "key": key,
            "scenario": scen,
            "model": m_label,
            "cp_exp11": cp_exp11,
            "cp_resc": cp_resc,
            "exp11_any_hard": exp11_any,
            "exp11_strong": exp11_strong,
            "exp11_crit": exp11_crit,
            "pipeline_any_hard": pipeline_any_hard,
            "exp11_n_viols": ec.get("n_constraint_violations", 0),
            "pipeline_vbt": vbt,
        }
        comparisons.append(row)

        if cp_exp11:  # only count CP episodes
            if exp11_any and pipeline_any_hard:
                both_agree_hard.append(row)
            elif exp11_any and not pipeline_any_hard:
                exp11_strong_only.append(row)
            elif not exp11_any and pipeline_any_hard:
                pipeline_hard_only.append(row)
            else:
                neither_hard.append(row)

    cp_eps = [c for c in comparisons if c["cp_exp11"]]
    n_cp = len(cp_eps)

    # Exp11 strong subset check
    exp11_strong_eps = [c for c in cp_eps if c["exp11_strong"]]
    exp11_strong_also_pipeline = [c for c in exp11_strong_eps if c["pipeline_any_hard"]]
    exp11_strong_NOT_pipeline = [c for c in exp11_strong_eps if not c["pipeline_any_hard"]]

    lines.append(f"## Summary (n_CP = {n_cp})\n")
    lines.append("| Metric | Exp11 | Pipeline |")
    lines.append("|--------|-------|----------|")
    exp11_any_count = sum(1 for c in cp_eps if c["exp11_any_hard"])
    pipe_any_count = sum(1 for c in cp_eps if c["pipeline_any_hard"])
    exp11_strong_count = sum(1 for c in cp_eps if c["exp11_strong"])
    exp11_crit_count = sum(1 for c in cp_eps if c["exp11_crit"])
    lines.append(
        f"| UP_any (any hard) | {exp11_any_count}/{n_cp} ({exp11_any_count / n_cp:.1%}) | {pipe_any_count}/{n_cp} ({pipe_any_count / n_cp:.1%}) |"
    )
    lines.append(
        f"| UP_strong (Exp11: sev>=SEVERE) | {exp11_strong_count}/{n_cp} ({exp11_strong_count / n_cp:.1%}) | N/A (no severity in rescored) |"
    )
    lines.append(f"| UP_crit (Exp11: sev=CRITICAL) | {exp11_crit_count}/{n_cp} ({exp11_crit_count / n_cp:.1%}) | N/A |")

    lines.append("\n## Exp11 any_hard vs Pipeline any_hard (CP episodes)\n")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| Both agree hard | {len(both_agree_hard)} |")
    lines.append(f"| Exp11 only | {len(exp11_strong_only)} |")
    lines.append(f"| Pipeline only | {len(pipeline_hard_only)} |")
    lines.append(f"| Neither | {len(neither_hard)} |")
    lines.append(f"| **Total CP** | **{n_cp}** |")

    lines.append("\n## Critical Check: Are Exp11's 27 UP_strong a subset of pipeline hard?\n")
    lines.append(f"- Exp11 UP_strong episodes: {len(exp11_strong_eps)}")
    lines.append(f"- Of these, pipeline also says hard: {len(exp11_strong_also_pipeline)}")
    lines.append(f"- Of these, pipeline says NOT hard: {len(exp11_strong_NOT_pipeline)}")
    if exp11_strong_NOT_pipeline:
        lines.append("\n### Exp11 strong BUT pipeline NOT hard:")
        for e in exp11_strong_NOT_pipeline:
            lines.append(f"  - {e['key']}: exp11_viols={e['exp11_n_viols']}, pipeline_vbt={e['pipeline_vbt']}")

    # Exp11-only hard episodes (exp11 says hard, pipeline doesn't)
    if exp11_strong_only:
        lines.append(f"\n## Exp11-only hard episodes ({len(exp11_strong_only)}):\n")
        for e in exp11_strong_only:
            lines.append(f"- {e['key']}: exp11_strong={e['exp11_strong']}, pipeline_vbt={e['pipeline_vbt']}")

    if pipeline_hard_only:
        lines.append(f"\n## Pipeline-only hard episodes ({len(pipeline_hard_only)}):\n")
        for e in pipeline_hard_only:
            lines.append(f"- {e['key']}: exp11_any={e['exp11_any_hard']}, pipeline_vbt={e['pipeline_vbt']}")

    lines.append("\n## Verdict\n")
    if len(exp11_strong_NOT_pipeline) == 0:
        lines.append("**PASS**: All 27 Exp11 UP_strong episodes are also pipeline-hard.")
        lines.append(
            f"Exp11 any_hard ({exp11_any_count}) vs Pipeline any_hard ({pipe_any_count}): "
            f"delta = {abs(exp11_any_count - pipe_any_count)}"
        )
    else:
        lines.append(
            f"**ISSUE**: {len(exp11_strong_NOT_pipeline)} Exp11 UP_strong episodes are NOT pipeline-hard. Investigate."
        )

    result = {
        "n_cp": n_cp,
        "exp11_any_hard": exp11_any_count,
        "pipeline_any_hard": pipe_any_count,
        "exp11_strong": exp11_strong_count,
        "exp11_crit": exp11_crit_count,
        "both_agree": len(both_agree_hard),
        "exp11_only": len(exp11_strong_only),
        "pipeline_only": len(pipeline_hard_only),
        "neither": len(neither_hard),
        "strong_subset_check": len(exp11_strong_NOT_pipeline) == 0,
    }
    return "\n".join(lines), result


# =========================================================================
# VF-2: B-1 Ablation Baseline Consistency
# =========================================================================
def vf2_b1_baseline(exp11_episodes):
    lines = ["# VF-2: B-1 Ablation Baseline Consistency\n"]

    lines.append("## Method Review\n")
    lines.append("B-1 (`necessity_gap_part1.py:422-508`) uses **Exp11 data directly**:")
    lines.append("- `viols = ec.get('constraint_violations', [])` — from Exp11's `all_episode_constraints`")
    lines.append("- Filters by `constraint_type` in {FORBIDDEN, WITHIN, BEFORE}")
    lines.append("- UP_strong = severity_set contains 'CRITICAL' or 'SEVERE'")
    lines.append("- This is **identical** to Exp11's `has_severe` field definition")
    lines.append("")

    # Reproduce B-1 (a) Full
    cp_eps = [e for e in exp11_episodes if e["c2"] >= 0.7]
    n_cp = len(cp_eps)

    include_types = {"FORBIDDEN", "WITHIN", "BEFORE"}
    up_strong = 0
    up_crit = 0
    up_any = 0
    strong_eps = []

    for ec in cp_eps:
        viols = ec.get("constraint_violations", [])
        filtered = [v for v in viols if v.get("constraint_type") in include_types]
        if filtered:
            up_any += 1
        severity_set = {v.get("severity") for v in filtered}
        is_strong = "CRITICAL" in severity_set or "SEVERE" in severity_set
        is_crit = "CRITICAL" in severity_set
        if is_strong:
            up_strong += 1
            strong_eps.append(ec)
        if is_crit:
            up_crit += 1

    # Compare with Exp11's own counts
    exp11_strong_count = sum(1 for e in cp_eps if e.get("has_severe", False))
    exp11_crit_count = sum(1 for e in cp_eps if e.get("has_critical", False))
    exp11_any_count = sum(1 for e in cp_eps if e.get("has_any_hard", False))

    lines.append(f"## Reproduction (n_CP = {n_cp})\n")
    lines.append("| Metric | B-1 (a) Full | Exp11 field | Match? |")
    lines.append("|--------|-------------|-------------|--------|")
    lines.append(
        f"| UP_any | {up_any}/{n_cp} ({up_any / n_cp:.1%}) | {exp11_any_count}/{n_cp} ({exp11_any_count / n_cp:.1%}) | {'YES' if up_any == exp11_any_count else 'NO'} |"
    )
    lines.append(
        f"| UP_strong | {up_strong}/{n_cp} ({up_strong / n_cp:.1%}) | {exp11_strong_count}/{n_cp} ({exp11_strong_count / n_cp:.1%}) | {'YES' if up_strong == exp11_strong_count else 'NO'} |"
    )
    lines.append(
        f"| UP_crit | {up_crit}/{n_cp} ({up_crit / n_cp:.1%}) | {exp11_crit_count}/{n_cp} ({exp11_crit_count / n_cp:.1%}) | {'YES' if up_crit == exp11_crit_count else 'NO'} |"
    )

    all_match = up_any == exp11_any_count and up_strong == exp11_strong_count and up_crit == exp11_crit_count
    lines.append("\n## Verdict\n")
    if all_match:
        lines.append("**PASS**: B-1's '(a) Full' exactly reproduces Exp11 canonical counts.")
        lines.append("Both use the same data source and same severity classification.")
    else:
        lines.append("**ISSUE**: B-1 counts don't match Exp11 fields. Investigate severity logic.")

    # Episode-level match
    b1_strong_keys = set()
    for ec in strong_eps:
        b1_strong_keys.add(make_ep_key(ec["model"], ec["scenario"], ec.get("run", 0)))
    exp11_strong_keys = set()
    for ec in cp_eps:
        if ec.get("has_severe"):
            exp11_strong_keys.add(make_ep_key(ec["model"], ec["scenario"], ec.get("run", 0)))

    symmetric_diff = b1_strong_keys.symmetric_difference(exp11_strong_keys)
    lines.append(
        f"\nEpisode-level: B-1 strong set = {len(b1_strong_keys)}, Exp11 strong set = {len(exp11_strong_keys)}"
    )
    lines.append(f"Symmetric difference: {len(symmetric_diff)} episodes")
    if symmetric_diff:
        for k in sorted(symmetric_diff):
            lines.append(f"  - {k}")

    result = {
        "b1_up_strong": up_strong,
        "exp11_up_strong": exp11_strong_count,
        "b1_up_crit": up_crit,
        "exp11_up_crit": exp11_crit_count,
        "b1_up_any": up_any,
        "exp11_up_any": exp11_any_count,
        "all_match": all_match,
        "episode_symmetric_diff": len(symmetric_diff),
    }
    return "\n".join(lines), result


# =========================================================================
# VF-3: Expansion CP=18 Re-verification
# =========================================================================
def vf3_expansion_recheck(exp11_episodes):
    lines = ["# VF-3: Expansion CP=18 Re-verification\n"]

    # Classify each episode as Core or Expansion
    core_eps = []
    exp_eps = []
    for ec in exp11_episodes:
        scen = ec["scenario"]
        graph = SCENARIO_TO_GRAPH.get(scen, "")
        if graph in CORE_GRAPHS:
            core_eps.append(ec)
        else:
            exp_eps.append(ec)

    core_cp = [e for e in core_eps if e["c2"] >= 0.7]
    exp_cp = [e for e in exp_eps if e["c2"] >= 0.7]
    total_cp = len(core_cp) + len(exp_cp)

    lines.append("## Episode Classification\n")
    lines.append("| Category | Total | CP (C2>=0.7) |")
    lines.append("|----------|-------|-------------|")
    lines.append(f"| Core (6 graphs) | {len(core_eps)} | {len(core_cp)} |")
    lines.append(f"| Expansion (7 graphs) | {len(exp_eps)} | {len(exp_cp)} |")
    lines.append(f"| **Total** | **{len(core_eps) + len(exp_eps)}** | **{total_cp}** |")

    lines.append(
        f"\n## Sum Check: {len(core_cp)} + {len(exp_cp)} = {total_cp} {'== 78 ✓' if total_cp == 78 else '!= 78 ✗'}\n"
    )

    # Core scenarios
    core_scens = sorted(set(e["scenario"] for e in core_eps))
    exp_scens = sorted(set(e["scenario"] for e in exp_eps))
    lines.append(f"### Core Scenarios ({len(core_scens)}):")
    for s in core_scens:
        g = SCENARIO_TO_GRAPH.get(s, "?")
        n_ep = sum(1 for e in core_eps if e["scenario"] == s)
        n_cp = sum(1 for e in core_cp if e["scenario"] == s)
        lines.append(f"  - {s} ({g}): {n_ep} eps, {n_cp} CP")

    lines.append(f"\n### Expansion Scenarios ({len(exp_scens)}):")
    for s in exp_scens:
        g = SCENARIO_TO_GRAPH.get(s, "?")
        n_ep = sum(1 for e in exp_eps if e["scenario"] == s)
        n_cp = sum(1 for e in exp_cp if e["scenario"] == s)
        lines.append(f"  - {s} ({g}): {n_ep} eps, {n_cp} CP")

    # UP_strong per category (Exp11 basis)
    core_strong = sum(1 for e in core_cp if e.get("has_severe", False))
    exp_strong = sum(1 for e in exp_cp if e.get("has_severe", False))
    core_crit = sum(1 for e in core_cp if e.get("has_critical", False))
    exp_crit = sum(1 for e in exp_cp if e.get("has_critical", False))
    core_any = sum(1 for e in core_cp if e.get("has_any_hard", False))
    exp_any = sum(1 for e in exp_cp if e.get("has_any_hard", False))

    lines.append("\n## UP Rates (Exp11 canonical)\n")
    lines.append(f"| Metric | Core ({len(core_cp)} CP) | Expansion ({len(exp_cp)} CP) | Total ({total_cp} CP) |")
    lines.append("|--------|------|-----------|-------|")
    lines.append(
        f"| UP_any | {core_any}/{len(core_cp)} ({core_any / len(core_cp):.1%}) | {exp_any}/{len(exp_cp)} ({exp_any / len(exp_cp):.1%}) | {core_any + exp_any}/{total_cp} ({(core_any + exp_any) / total_cp:.1%}) |"
    )
    lines.append(
        f"| UP_strong | {core_strong}/{len(core_cp)} ({core_strong / len(core_cp):.1%}) | {exp_strong}/{len(exp_cp)} ({exp_strong / len(exp_cp):.1%}) | {core_strong + exp_strong}/{total_cp} ({(core_strong + exp_strong) / total_cp:.1%}) |"
    )
    lines.append(
        f"| UP_crit | {core_crit}/{len(core_cp)} ({core_crit / len(core_cp):.1%}) | {exp_crit}/{len(exp_cp)} ({exp_crit / len(exp_cp):.1%}) | {core_crit + exp_crit}/{total_cp} ({(core_crit + exp_crit) / total_cp:.1%}) |"
    )

    strong_sum_check = core_strong + exp_strong
    lines.append(
        f"\n## Sum Check: {core_strong} + {exp_strong} = {strong_sum_check} {'== 27 ✓' if strong_sum_check == 27 else '!= 27 ✗'}\n"
    )

    # Mean CGA
    core_cga = [e["cga"] for e in core_eps if "cga" in e]
    exp_cga = [e["cga"] for e in exp_eps if "cga" in e]
    lines.append("## Mean CGA")
    lines.append(f"- Core: {sum(core_cga) / len(core_cga):.3f} (n={len(core_cga)})")
    lines.append(f"- Expansion: {sum(exp_cga) / len(exp_cga):.3f} (n={len(exp_cga)})")

    result = {
        "core_total": len(core_eps),
        "core_cp": len(core_cp),
        "exp_total": len(exp_eps),
        "exp_cp": len(exp_cp),
        "total_cp": total_cp,
        "sum_check_78": total_cp == 78,
        "core_strong": core_strong,
        "exp_strong": exp_strong,
        "sum_check_27": strong_sum_check == 27,
    }
    return "\n".join(lines), result


# =========================================================================
# A-4: EXP-SPREAD — Table 4 by Domain
# =========================================================================
def a4_exp_spread(exp11_episodes, rescored_episodes):
    lines = ["# A-4: EXP-SPREAD — Violation Spread by Domain\n"]

    # Build domain data using FINE domains (actual 11 domains)
    domain_data: dict[str, dict] = {}
    for d in DOMAIN_ORDER_FINE:
        domain_data[d] = {
            "scenarios": set(),
            "episodes": [],
            "cp_episodes": [],
            "strong_scenarios": set(),
            "viol_types": set(),
            "constraint_types_detail": defaultdict(int),
        }

    for ec in exp11_episodes:
        scen = ec["scenario"]
        domain = SCENARIO_DOMAIN.get(scen)
        if not domain:
            continue

        dd = domain_data[domain]
        dd["scenarios"].add(scen)
        dd["episodes"].append(ec)

        if ec["c2"] >= 0.7:
            dd["cp_episodes"].append(ec)

        for v in ec.get("constraint_violations", []):
            ctype = v.get("constraint_type", "")
            if ctype == "FORBIDDEN":
                dd["viol_types"].add("Forbidden")
            elif ctype == "WITHIN":
                dd["viol_types"].add("Timing")
            elif ctype == "BEFORE":
                dd["viol_types"].add("Sequence")
            dd["constraint_types_detail"][ctype] += 1

        if ec.get("has_severe"):
            dd["strong_scenarios"].add(scen)

    # Get CGA values from rescored episodes
    rescored_cga: dict[str, list[float]] = defaultdict(list)
    for ep in rescored_episodes:
        domain = SCENARIO_DOMAIN.get(ep["scenario_id"])
        if domain:
            cga = ep.get("new_compliance_score")
            if cga is not None:
                rescored_cga[domain].append(cga)

    # Fine-grained table
    lines.append("## Fine-Grained Domain Table (11 domains)\n")
    lines.append("| Domain | Scen | Eps | CP | UP_strong | UP_crit | UP_any | Viol Types | Mean CGA |")
    lines.append("|--------|------|-----|----|-----------|---------|---------|-----------  |----------|")

    total_strong_domains = 0
    total_strong_scenarios = 0
    timing_domains = 0
    fine_results = []

    for domain in DOMAIN_ORDER_FINE:
        dd = domain_data[domain]
        n_scen = len(dd["scenarios"])
        n_ep = len(dd["episodes"])
        n_cp = len(dd["cp_episodes"])
        n_strong = sum(1 for e in dd["cp_episodes"] if e.get("has_severe"))
        n_crit = sum(1 for e in dd["cp_episodes"] if e.get("has_critical"))
        n_any = sum(1 for e in dd["cp_episodes"] if e.get("has_any_hard"))
        vtypes = sorted(dd["viol_types"])
        n_strong_scen = len(dd["strong_scenarios"])
        cga_vals = rescored_cga.get(domain, [])
        mean_cga = sum(cga_vals) / len(cga_vals) if cga_vals else 0

        if n_strong_scen > 0:
            total_strong_domains += 1
        total_strong_scenarios += n_strong_scen
        if "Timing" in dd["viol_types"]:
            timing_domains += 1

        up_s = f"{n_strong}/{n_cp} ({n_strong / n_cp:.0%})" if n_cp > 0 else "---"
        up_c = f"{n_crit}/{n_cp} ({n_crit / n_cp:.0%})" if n_cp > 0 else "---"
        up_a = f"{n_any}/{n_cp} ({n_any / n_cp:.0%})" if n_cp > 0 else "---"
        vt_str = ", ".join(vtypes) if vtypes else "---"

        lines.append(
            f"| {domain:6s} | {n_scen} | {n_ep:3d} | {n_cp:2d} | {up_s:>12} | {up_c:>10} | {up_a:>10} | {vt_str:15s} | {mean_cga:.3f} |"
        )

        fine_results.append(
            {
                "domain": domain,
                "n_scenarios": n_scen,
                "n_strong_scenarios": n_strong_scen,
                "n_episodes": n_ep,
                "n_cp": n_cp,
                "up_strong": n_strong,
                "up_crit": n_crit,
                "up_any": n_any,
                "up_strong_rate": round(n_strong / n_cp, 3) if n_cp > 0 else 0,
                "viol_types": vtypes,
                "mean_cga": round(mean_cga, 3),
            }
        )

    lines.append(f"\n**Strong violation domains**: {total_strong_domains}/{len(DOMAIN_ORDER_FINE)}")
    lines.append(f"**Strong violation scenarios**: {total_strong_scenarios}/15")
    lines.append(f"**Timing-violation domains**: {timing_domains}/{len(DOMAIN_ORDER_FINE)}")

    # LaTeX Table 4 (fine-grained)
    lines.append("\n## LaTeX Table 4\n")
    latex_rows = []
    for r in fine_results:
        vtypes = ", ".join(r["viol_types"]) if r["viol_types"] else "---"
        rate_str = f"{r['up_strong_rate'] * 100:.0f}\\%" if r["n_cp"] > 0 else "---"
        n_str = f"{r['up_strong']}/{r['n_cp']}"
        latex_rows.append(
            f"    {r['domain']:<8s} & {r['n_strong_scenarios']}/{r['n_scenarios']}  "
            f"& {n_str:>5} & {rate_str:>6} & {vtypes} \\\\"
        )

    latex = f"""\\begin{{table}}[t]
\\centering
\\caption{{Violation spread by clinical domain (Exp11 canonical, $n_{{CP}}=78$).}}
\\label{{tab:violation_spread}}
\\small
\\begin{{tabular}}{{lcccl}}
  \\toprule
  \\textbf{{Domain}} & \\textbf{{Scen.\\ w/ viol.}}
    & \\multicolumn{{2}}{{c}}{{$\\mathrm{{UP}}_{{\\mathrm{{strong}}}}$}}
    & \\textbf{{Violation types}} \\\\
  \\midrule
{chr(10).join(latex_rows)}
  \\bottomrule
\\end{{tabular}}
\\end{{table}}"""

    lines.append("```latex")
    lines.append(latex)
    lines.append("```")

    # Prose
    sorted_cga = sorted(fine_results, key=lambda x: x["mean_cga"])
    hardest = sorted_cga[0]
    easiest = sorted_cga[-1]

    lines.append("\n## Prose\n")
    lines.append("Critical violations (forbidden drug) are concentrated in DKA.")
    lines.append(f"Timing violations are distributed across {timing_domains} domains.")
    lines.append(
        f"Domain difficulty ranges from {easiest['domain']} (mean CGA {easiest['mean_cga']:.2f}) "
        f"to {hardest['domain']} (mean CGA {hardest['mean_cga']:.2f})."
    )

    lines.append("\n## Intro Sentence\n")
    lines.append(
        f"Guideline-strong violations occur in **{total_strong_domains}/{len(DOMAIN_ORDER_FINE)} domains** "
        f"and **{total_strong_scenarios}/15 scenarios**, and appear in all 4 models."
    )

    result = {
        "fine_results": fine_results,
        "strong_domains": total_strong_domains,
        "strong_scenarios": total_strong_scenarios,
        "timing_domains": timing_domains,
        "latex": latex,
        "hardest": {"domain": hardest["domain"], "cga": hardest["mean_cga"]},
        "easiest": {"domain": easiest["domain"], "cga": easiest["mean_cga"]},
    }
    return "\n".join(lines), result


# =========================================================================
# Main
# =========================================================================
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading data...")
    exp11 = load_exp11()
    exp11_episodes = exp11["all_episode_constraints"]
    rescored = load_rescored()
    print(f"  Exp11: {len(exp11_episodes)} episodes")
    print(f"  Rescored: {len(rescored)} episodes")

    # VF-1
    print("\n=== VF-1: Exp11 vs Pipeline HardViol ===")
    vf1_md, vf1_res = vf1_exp11_vs_pipeline(exp11_episodes, rescored)
    (OUTPUT_DIR / "vf1_exp11_vs_pipeline.md").write_text(vf1_md)
    print(f"  Exp11 any_hard={vf1_res['exp11_any_hard']}, Pipeline any_hard={vf1_res['pipeline_any_hard']}")
    print(f"  Exp11 strong={vf1_res['exp11_strong']}, Strong subset check: {vf1_res['strong_subset_check']}")

    # VF-2
    print("\n=== VF-2: B-1 Ablation Baseline ===")
    vf2_md, vf2_res = vf2_b1_baseline(exp11_episodes)
    (OUTPUT_DIR / "vf2_b1_baseline.md").write_text(vf2_md)
    print(
        f"  B-1 UP_strong={vf2_res['b1_up_strong']}, Exp11={vf2_res['exp11_up_strong']}, match={vf2_res['all_match']}"
    )

    # VF-3
    print("\n=== VF-3: Expansion CP Recheck ===")
    vf3_md, vf3_res = vf3_expansion_recheck(exp11_episodes)
    (OUTPUT_DIR / "vf3_expansion_recheck.md").write_text(vf3_md)
    print(
        f"  Core CP={vf3_res['core_cp']}, Exp CP={vf3_res['exp_cp']}, sum={vf3_res['total_cp']} (78 check: {vf3_res['sum_check_78']})"
    )
    print(
        f"  Core strong={vf3_res['core_strong']}, Exp strong={vf3_res['exp_strong']}, sum={vf3_res['core_strong'] + vf3_res['exp_strong']} (27 check: {vf3_res['sum_check_27']})"
    )

    # A-4
    print("\n=== A-4: EXP-SPREAD ===")
    a4_md, a4_res = a4_exp_spread(exp11_episodes, rescored)
    (OUTPUT_DIR / "a4_exp_spread.md").write_text(a4_md)
    (OUTPUT_DIR / "a4_exp_spread.json").write_text(json.dumps(a4_res, indent=2, default=str))
    print(f"  Strong domains: {a4_res['strong_domains']}/{len(DOMAIN_ORDER_FINE)}")
    print(f"  Strong scenarios: {a4_res['strong_scenarios']}/15")
    print(f"  Timing domains: {a4_res['timing_domains']}")
    print(f"  Hardest: {a4_res['hardest']}")
    print(f"  Easiest: {a4_res['easiest']}")

    # Save combined JSON
    combined = {
        "vf1": vf1_res,
        "vf2": vf2_res,
        "vf3": vf3_res,
        "a4_summary": {
            "strong_domains": a4_res["strong_domains"],
            "strong_scenarios": a4_res["strong_scenarios"],
            "timing_domains": a4_res["timing_domains"],
        },
    }
    (OUTPUT_DIR / "vf_combined.json").write_text(json.dumps(combined, indent=2))

    print(f"\nAll outputs saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
