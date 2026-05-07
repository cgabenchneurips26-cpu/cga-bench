
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""c3_poster_child_detail.py.

Detailed analysis of the 9 "poster-child" episodes that pass ALL process-oblivious
evaluators (DxEM, AgentClinic-Proxy, MAB-Proxy, C2>=0.7, ACov>=0.5) but contain
hard violations detected by CGA-Bench.

Outputs
-------
results/poster_child/9_episodes_detail.md   -- full detail for all 9 episodes
results/poster_child/intro_examples.md      -- 2 selected cases for paper intro
evidence_pack/tables/poster_child_summary.tex
evidence_pack/analysis/c3_poster_child.json
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
import textwrap
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]

VERDICT_FILE = REPO_ROOT / "evidence_pack" / "analysis" / "v3_verdict_integration.json"
ARCHIVE_BASE = REPO_ROOT / "_archive" / "results" / "clean_slate_20260331_210910"
RESCORE_BASE = REPO_ROOT / "results" / "clean_slate_rescored"
SCENARIO_DIR = REPO_ROOT / "configs" / "scenarios"

OUT_DIR = REPO_ROOT / "results" / "poster_child"
TABLE_DIR = REPO_ROOT / "evidence_pack" / "tables"
ANALYSIS_DIR = REPO_ROOT / "evidence_pack" / "analysis"

# model label (from verdict JSON) -> archive/rescore subdirectory name
MODEL_DIR_MAP: dict[str, str] = {
    "Qwen3-4B": "qwen4b",
    "Qwen3.5-27B": "qwen27b",
    "Qwen3.5-35B": "qwen35b",
    "oss120b": "oss120b",
}

# Scenario id -> YAML filename (all scenario files in configs/scenarios/)
# Built lazily at runtime via _load_all_scenarios().
_SCENARIO_CACHE: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def _load_all_scenarios() -> None:
    """Populate _SCENARIO_CACHE from every YAML in SCENARIO_DIR."""
    if _SCENARIO_CACHE:
        return
    for yaml_path in sorted(SCENARIO_DIR.glob("*.yaml")):
        with open(yaml_path) as fh:
            doc = yaml.safe_load(fh)
        if not isinstance(doc, dict):
            continue
        for section_key in ("scenarios", "trap_scenarios"):
            section = doc.get(section_key)
            if not isinstance(section, dict):
                continue
            for scenario_id, scenario_data in section.items():
                if isinstance(scenario_data, dict):
                    _SCENARIO_CACHE[scenario_id] = scenario_data


def _get_scenario_info(scenario_id: str) -> dict[str, Any]:
    """Return scenario dict for scenario_id, or empty dict if not found."""
    _load_all_scenarios()
    return _SCENARIO_CACHE.get(scenario_id, {})


def _find_episode_file(base_dir: Path, scenario_id: str, run_index: int) -> Path | None:
    """Find an episode JSON file matching scenario_id and run_index."""
    pattern = str(base_dir / f"{scenario_id}_*_r{run_index}_*.json")
    matches = glob.glob(pattern)
    if matches:
        return Path(matches[0])
    # Fallback: search without run index suffix (some files use different naming)
    pattern2 = str(base_dir / f"{scenario_id}_*.json")
    for p in sorted(glob.glob(pattern2)):
        with open(p) as fh:
            try:
                d = json.load(fh)
            except json.JSONDecodeError:
                continue
        if d.get("run_index") == run_index:
            return Path(p)
    return None


def _load_json(path: Path) -> dict[str, Any]:
    with open(path) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Per-episode analysis
# ---------------------------------------------------------------------------


def _action_trace(actions: list[dict[str, Any]]) -> list[str]:
    """Format action list as chronological trace lines."""
    sorted_actions = sorted(actions, key=lambda a: a.get("timestamp", 0.0))
    return [f"T={a.get('timestamp', 0.0):.0f}min: {a.get('action_id', 'unknown')}" for a in sorted_actions]


def _extract_hard_violations(
    rescore_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return commission and severe/catastrophic violations from rescored data."""
    all_violations = rescore_data.get("new_violation_events", [])
    hard: list[dict[str, Any]] = []
    for v in all_violations:
        vtype = v.get("violation_type", "")
        severity = v.get("harm_severity", "")
        if vtype == "commission" or severity in ("severe", "catastrophic"):
            hard.append(v)
    # De-duplicate by action + type
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for v in hard:
        key = f"{v.get('violation_type')}|{v.get('action_involved')}"
        if key not in seen:
            seen.add(key)
            deduped.append(v)
    return deduped


def _evaluator_pass_reasons(entry: dict[str, Any], orig_data: dict[str, Any]) -> dict[str, str]:
    """Generate one-sentence explanation of why each evaluator passed."""
    scenario = entry.get("scenario", "")
    cov = entry.get("action_coverage", 0.0)
    jac = entry.get("jaccard", 0.0)
    c2 = entry.get("c2_score", 0.0)
    n_expected = orig_data.get("n_expected_actions", 0)

    # Diagnosis exact-match: passes because model stated correct diagnosis text
    dx_reason = (
        "DxEM passes because the model's free-text response contains the correct "
        f"diagnosis keyword for '{scenario}', which string-matches the reference label."
    )

    # AgentClinic proxy: checks action presence without ordering/timing context
    ac_reason = (
        f"AgentClinic-Proxy passes because {int(cov * 100)}% of expected actions appear "
        "in the agent's output (threshold 50%), ignoring action order and timing constraints."
    )

    # MAB F1 proxy: token-level F1 on action tokens, no sequence awareness
    mab_reason = (
        "MAB-F1-Proxy passes because token-level F1 between predicted and expected action "
        "sets is ≥0.5; it treats actions as an unordered bag-of-tokens with no timing check."
    )

    # C2 sub-score: mandatory completion ignores *why* an action is mandatory
    c2_reason = (
        f"C2 (mandatory-completion sub-score = {c2:.2f}) passes because the model performs "
        "most mandatory actions; C2 does not penalise performing a forbidden action that "
        "happens to also appear in the mandatory list."
    )

    # Action coverage
    acov_reason = (
        f"ACov passes ({cov:.0%} ≥ 50% threshold) because raw set-overlap of agent actions "
        f"with {n_expected} expected actions is high; no weight given to forbidden actions."
    )

    # Jaccard (fails in all near-miss cases — Jaccard_v=0 means score < threshold)
    jac_reason = (
        f"Jaccard similarity = {jac:.3f} falls below the 0.5 pass threshold, making this "
        "the only overlap metric that partially flags quality degradation — yet still "
        "misses the specific forbidden-action violation."
    )

    return {
        "DxEM": dx_reason,
        "AgentClinic": ac_reason,
        "MAB_F1": mab_reason,
        "C2": c2_reason,
        "ACov": acov_reason,
        "Jaccard": jac_reason,
    }


def _clinical_danger_sentence(scenario_id: str, violations: list[dict[str, Any]]) -> str:
    """Produce a one-sentence clinical danger summary."""
    if not violations:
        return "Timing and sequence violations expose the patient to avoidable harm."

    # Use the first commission violation description if available
    for v in violations:
        if v.get("violation_type") == "commission":
            action = v.get("action_involved", "unknown action")
            desc = v.get("description", "")
            severity = v.get("harm_severity", "unknown severity")
            # Build domain-specific danger statement
            if "insulin" in action and "dka" in scenario_id:
                return (
                    f"Administering insulin infusion ('{action}') before correcting "
                    "hypokalaemia risks fatal cardiac arrhythmia; ADA guidelines mandate "
                    "potassium ≥3.5 mEq/L verification *before* starting insulin in DKA."
                )
            return (
                f"Performing the forbidden action '{action}' ({severity} severity per CPG) "
                f"directly contravenes the guideline constraint: {desc}"
            )

    # Fallback for severe non-commission
    v = violations[0]
    return (
        f"The {v.get('violation_type')} violation on '{v.get('action_involved')}' "
        f"({v.get('harm_severity')} severity) represents a clinically dangerous "
        "deviation that process-oblivious metrics cannot detect."
    )


# ---------------------------------------------------------------------------
# Per-episode record builder
# ---------------------------------------------------------------------------


def analyse_episode(entry: dict[str, Any]) -> dict[str, Any]:
    """Build full analysis record for one near-miss episode entry."""
    model_label = entry["model"]
    model_dir = MODEL_DIR_MAP.get(model_label, model_label.lower())
    scenario_id = entry["scenario"]
    run_index = int(entry["run"])

    archive_dir = ARCHIVE_BASE / model_dir
    rescore_dir = RESCORE_BASE / model_dir

    orig_path = _find_episode_file(archive_dir, scenario_id, run_index)
    resc_path = _find_episode_file(rescore_dir, scenario_id, run_index)

    orig_data: dict[str, Any] = _load_json(orig_path) if orig_path else {}
    resc_data: dict[str, Any] = _load_json(resc_path) if resc_path else {}

    scenario_cfg = _get_scenario_info(scenario_id)
    patient = scenario_cfg.get("patient", {})

    actions = orig_data.get("actions", [])
    trace = _action_trace(actions)

    hard_viols = _extract_hard_violations(resc_data)
    pass_reasons = _evaluator_pass_reasons(entry, orig_data)
    danger = _clinical_danger_sentence(scenario_id, hard_viols)

    # Structured violation records
    violation_records: list[dict[str, Any]] = []
    for v in hard_viols:
        violation_records.append(
            {
                "type": v.get("violation_type", ""),
                "action": v.get("action_involved", ""),
                "severity": v.get("harm_severity", ""),
                "description": v.get("description", ""),
                "guideline_reference": v.get("guideline_reference", ""),
                "guideline_class": v.get("guideline_class", ""),
            }
        )

    return {
        "episode_id": entry["episode_id"],
        "model": model_label,
        "model_dir": model_dir,
        "scenario": scenario_id,
        "run": run_index,
        "orig_path": str(orig_path) if orig_path else None,
        "resc_path": str(resc_path) if resc_path else None,
        # Patient info
        "patient": {
            "age": patient.get("age", "N/A"),
            "sex": patient.get("sex", "N/A"),
            "chief_complaint": patient.get("chief_complaint", "N/A"),
            "working_diagnosis": patient.get("working_diagnosis", "N/A"),
            "vitals": patient.get("vitals", {}),
            "comorbidities": patient.get("comorbidities", []),
        },
        "scenario_description": scenario_cfg.get("description", ""),
        # Scores from verdict entry
        "cga_score": entry["cga_score"],
        "c2_score": entry["c2_score"],
        "action_coverage": entry["action_coverage"],
        "jaccard": entry["jaccard"],
        "hard_violation_types": entry["hard_violation_types"],
        "max_severity": entry["max_severity"],
        # Evaluator verdicts
        "evaluator_verdicts": {
            "DxEM": entry["DxEM"],
            "AgentClinic": entry["AgentClinic"],
            "MAB_F1": entry["MAB_F1"],
            "C2": entry["C2"],
            "ACov": entry["ACov"],
            "Jaccard_v": entry["Jaccard_v"],
            "CGA": entry["CGA"],
        },
        # Analysis
        "action_trace": trace,
        "hard_violations": violation_records,
        "evaluator_pass_reasons": pass_reasons,
        "clinical_danger": danger,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _vitals_line(vitals: dict[str, Any]) -> str:
    parts = []
    if "heart_rate" in vitals:
        parts.append(f"HR {vitals['heart_rate']} bpm")
    if "blood_pressure_systolic" in vitals and "blood_pressure_diastolic" in vitals:
        parts.append(f"BP {vitals['blood_pressure_systolic']}/{vitals['blood_pressure_diastolic']} mmHg")
    if "respiratory_rate" in vitals:
        parts.append(f"RR {vitals['respiratory_rate']}/min")
    if "oxygen_saturation" in vitals:
        parts.append(f"SpO₂ {vitals['oxygen_saturation']}%")
    if "temperature" in vitals:
        parts.append(f"T {vitals['temperature']}°C")
    if "map_mmhg" in vitals:
        parts.append(f"MAP {vitals['map_mmhg']} mmHg")
    return ", ".join(parts) if parts else "N/A"


def _render_episode_md(rec: dict[str, Any], index: int) -> str:
    """Render one episode record as a Markdown section."""
    lines: list[str] = []
    p = rec["patient"]
    verdict = rec["evaluator_verdicts"]

    lines.append(f"## Episode {index}: `{rec['episode_id']}`")
    lines.append("")
    lines.append(f"**Model:** {rec['model']} | **Scenario:** {rec['scenario']} | **Run:** {rec['run']}")
    lines.append("")

    # Patient
    lines.append("### Patient Presenting State")
    lines.append("")
    comorbid = ", ".join(p["comorbidities"]) if p["comorbidities"] else "none"
    lines.append(f"- **Age/Sex:** {p['age']} y/o {p['sex']}  ")
    lines.append(f"- **Chief Complaint:** {p['chief_complaint']}")
    lines.append(f"- **Working Diagnosis:** {p['working_diagnosis']}")
    lines.append(f"- **Vitals:** {_vitals_line(p['vitals'])}")
    lines.append(f"- **Comorbidities:** {comorbid}")
    if rec["scenario_description"]:
        lines.append(f"- **Scenario:** {rec['scenario_description']}")
    lines.append("")

    # Scores
    lines.append("### Scores")
    lines.append("")
    lines.append("| CGA Score | C2 Sub-score | Action Coverage | Jaccard | Max Severity |")
    lines.append("|-----------|-------------|----------------|---------|--------------|")
    lines.append(
        f"| {rec['cga_score']:.4f} | {rec['c2_score']:.2f} | "
        f"{rec['action_coverage']:.2f} | {rec['jaccard']:.4f} | {rec['max_severity']} |"
    )
    lines.append("")

    # Evaluator verdicts
    lines.append("### Evaluator Verdicts")
    lines.append("")
    lines.append("| Evaluator | Verdict |")
    lines.append("|-----------|---------|")
    verdict_map = {
        "DxEM": verdict["DxEM"],
        "AgentClinic (Proxy)": verdict["AgentClinic"],
        "MAB F1 (Proxy)": verdict["MAB_F1"],
        "C2 Sub-score": verdict["C2"],
        "Action Coverage": verdict["ACov"],
        "Jaccard": verdict["Jaccard_v"],
        "CGA-Bench": verdict["CGA"],
    }
    for ev_name, v_val in verdict_map.items():
        verdict_str = "PASS" if v_val == 1 else "FAIL"
        lines.append(f"| {ev_name} | {verdict_str} |")
    lines.append("")

    # Action trace
    lines.append("### Action Trace (chronological)")
    lines.append("")
    if rec["action_trace"]:
        for t in rec["action_trace"]:
            lines.append(f"- {t}")
    else:
        lines.append("_No actions recorded._")
    lines.append("")

    # Violated constraints
    lines.append("### Violated Constraints")
    lines.append("")
    if rec["hard_violations"]:
        for viol in rec["hard_violations"]:
            lines.append(f"- **[{viol['type'].upper()}]** `{viol['action']}` — Severity: {viol['severity']}")
            if viol["description"]:
                lines.append(f"  - {viol['description']}")
            if viol["guideline_reference"]:
                gl_cls = f" (Class {viol['guideline_class']})" if viol["guideline_class"] else ""
                lines.append(f"  - CPG Source: {viol['guideline_reference']}{gl_cls}")
    else:
        lines.append("_No hard violations extracted._")
    lines.append("")

    # Why each evaluator passed
    lines.append("### Why Each Evaluator Passed")
    lines.append("")
    reasons = rec["evaluator_pass_reasons"]
    for ev_name, reason in [
        ("DxEM", reasons["DxEM"]),
        ("AgentClinic (Proxy)", reasons["AgentClinic"]),
        ("MAB F1 (Proxy)", reasons["MAB_F1"]),
        ("C2 Sub-score", reasons["C2"]),
        ("Action Coverage", reasons["ACov"]),
        ("Jaccard", reasons["Jaccard"]),
    ]:
        wrapped = textwrap.fill(reason, width=100)
        lines.append(f"**{ev_name}:** {wrapped}")
        lines.append("")

    # Clinical danger
    lines.append("### Why This Is Clinically Dangerous")
    lines.append("")
    lines.append(rec["clinical_danger"])
    lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Representative case selection
# ---------------------------------------------------------------------------


def _select_intro_cases(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select 2 representative cases for paper intro.

    Preference:
    1. Different domains (DKA + non-DKA if possible).
    2. Among DKA, prefer highest max_severity or most evaluators passing.
    3. Among non-DKA, prefer highest max_severity.
    """
    dka = [r for r in records if "dka" in r["scenario"]]
    non_dka = [r for r in records if "dka" not in r["scenario"]]

    severity_order = {"catastrophic": 4, "severe": 3, "major": 2, "moderate": 1, "minor": 0}

    def severity_key(r: dict[str, Any]) -> int:
        return severity_order.get(r.get("max_severity", ""), 0)

    selected: list[dict[str, Any]] = []

    if dka:
        best_dka = max(dka, key=severity_key)
        selected.append(best_dka)

    if non_dka:
        best_non_dka = max(non_dka, key=severity_key)
        selected.append(best_non_dka)
    elif len(dka) > 1:
        # All are DKA — pick two with different models
        remaining = [r for r in dka if r["episode_id"] != selected[0]["episode_id"]]
        if remaining:
            selected.append(max(remaining, key=severity_key))

    # If still only one, pick the second-highest overall
    if len(selected) < 2:
        remaining = [r for r in records if r["episode_id"] != selected[0]["episode_id"]]
        if remaining:
            selected.append(max(remaining, key=severity_key))

    return selected[:2]


def _render_intro_md(cases: list[dict[str, Any]], all_records: list[dict[str, Any]]) -> str:
    """Render intro_examples.md with 2 selected cases and selection rationale."""
    lines: list[str] = []
    lines.append("# Poster-Child Episodes for Paper Introduction")
    lines.append("")
    lines.append(
        "Two representative episodes selected from the 9 near-miss cases where ALL "
        "process-oblivious evaluators pass (DxEM=Pass, AgentClinic-Proxy=Pass, "
        "MAB-F1-Proxy=Pass, C2≥0.7, ACov≥0.5) but CGA-Bench detects hard violations."
    )
    lines.append("")
    lines.append("## Selection Rationale")
    lines.append("")
    lines.append(
        "Cases were chosen to illustrate different clinical domains (DKA and non-DKA "
        "where available) and to maximise the contrast between apparent evaluator consensus "
        "(all Pass) and clinical danger (hard constraint violation). Cases with the highest "
        "severity violation were prioritised."
    )
    lines.append("")

    for i, rec in enumerate(cases, start=1):
        lines.append("---")
        lines.append("")
        lines.append(f"## Case {i} of 2")
        lines.append("")
        lines.append(_render_episode_md(rec, i))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LaTeX table
# ---------------------------------------------------------------------------


def _render_latex_table(records: list[dict[str, Any]]) -> str:
    """Render a compact LaTeX summary table."""
    lines: list[str] = []
    lines.append(r"\begin{table}[ht]")
    lines.append(r"\centering")
    lines.append(r"\small")
    lines.append(
        r"\caption{Poster-child near-miss episodes: all process-oblivious evaluators "
        r"pass while CGA-Bench detects hard violations. "
        r"DxEM=Diagnosis Exact Match, AC=AgentClinic-Proxy, MAB=MAB-F1-Proxy, "
        r"C2=mandatory-completion sub-score $\geq$0.7, ACov=action-coverage $\geq$0.5, "
        r"Jac=Jaccard$<$0.5 (fails), CGA=CGA-Bench (fails).}"
    )
    lines.append(r"\label{tab:poster_child}")
    lines.append(r"\begin{tabular}{@{}llccccccccc@{}}")
    lines.append(r"\toprule")
    lines.append(
        r"Episode & Model & Scenario & DxEM & AC & MAB & C2 & ACov & Jac & CGA & "
        r"Violation Type \\"
    )
    lines.append(r"\midrule")

    for rec in records:
        v = rec["evaluator_verdicts"]
        model_short = rec["model"].replace("Qwen3.5-", "Q3.5-").replace("Qwen3-", "Q3-")
        scenario_short = rec["scenario"].replace("_", r"\_")
        ep_idx = rec["episode_id"].split("_")[-1]  # run index suffix

        def fmt(val: int, invert: bool = False) -> str:
            passed = val == 1
            if invert:
                passed = not passed
            return r"\cmark" if passed else r"\xmark"

        viol_type = rec["hard_violation_types"].upper() if rec["hard_violation_types"] else "N/A"

        lines.append(
            f"{ep_idx} & {model_short} & {scenario_short} & "
            f"{fmt(v['DxEM'])} & {fmt(v['AgentClinic'])} & {fmt(v['MAB_F1'])} & "
            f"{fmt(v['C2'])} & {fmt(v['ACov'])} & "
            f"{fmt(v['Jaccard_v'], invert=True)} & "  # Jaccard_v=0 means FAIL
            f"\\xmark & {viol_type} \\\\"
        )

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run poster-child episode analysis and write all output files."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    # Load near-miss entries
    with open(VERDICT_FILE) as fh:
        verdict_data = json.load(fh)

    near_miss_entries: list[dict[str, Any]] = verdict_data["key_examples_near_miss"]
    print(f"Loaded {len(near_miss_entries)} near-miss episodes from {VERDICT_FILE.name}")

    # Analyse each episode
    records: list[dict[str, Any]] = []
    for entry in near_miss_entries:
        print(f"  Analysing: {entry['episode_id']} ...")
        rec = analyse_episode(entry)
        records.append(rec)
        missing = []
        if rec["orig_path"] is None:
            missing.append("ORIGINAL")
        if rec["resc_path"] is None:
            missing.append("RESCORED")
        if missing:
            print(f"    WARNING: missing files: {missing}")

    # Full detail markdown
    full_md_lines: list[str] = [
        "# 9 Poster-Child Episodes — Full Detail",
        "",
        (
            "Episodes that pass ALL process-oblivious evaluators "
            "(DxEM=Pass, AgentClinic-Proxy=Pass, MAB-F1-Proxy=Pass, C2≥0.7, ACov≥0.5) "
            "but are flagged by CGA-Bench for hard constraint violations."
        ),
        "",
        f"Source: `{VERDICT_FILE.relative_to(REPO_ROOT)}`",
        "",
        "---",
        "",
    ]
    for i, rec in enumerate(records, start=1):
        full_md_lines.append(_render_episode_md(rec, i))

    full_md_path = OUT_DIR / "9_episodes_detail.md"
    full_md_path.write_text("\n".join(full_md_lines))
    print(f"Written: {full_md_path}")

    # Select 2 intro cases
    intro_cases = _select_intro_cases(records)
    print("Selected intro cases: " + ", ".join(c["episode_id"] for c in intro_cases))

    intro_md = _render_intro_md(intro_cases, records)
    intro_md_path = OUT_DIR / "intro_examples.md"
    intro_md_path.write_text(intro_md)
    print(f"Written: {intro_md_path}")

    # LaTeX table
    latex = _render_latex_table(records)
    latex_path = TABLE_DIR / "poster_child_summary.tex"
    latex_path.write_text(latex)
    print(f"Written: {latex_path}")

    # JSON output — strip large patient vitals for brevity in JSON
    json_records = []
    for rec in records:
        json_records.append(
            {
                "episode_id": rec["episode_id"],
                "model": rec["model"],
                "scenario": rec["scenario"],
                "run": rec["run"],
                "patient_summary": {
                    "age": rec["patient"]["age"],
                    "sex": rec["patient"]["sex"],
                    "chief_complaint": rec["patient"]["chief_complaint"],
                    "working_diagnosis": rec["patient"]["working_diagnosis"],
                    "comorbidities": rec["patient"]["comorbidities"],
                },
                "scenario_description": rec["scenario_description"],
                "scores": {
                    "cga_score": rec["cga_score"],
                    "c2_score": rec["c2_score"],
                    "action_coverage": rec["action_coverage"],
                    "jaccard": rec["jaccard"],
                    "max_severity": rec["max_severity"],
                },
                "evaluator_verdicts": rec["evaluator_verdicts"],
                "action_trace": rec["action_trace"],
                "hard_violations": rec["hard_violations"],
                "evaluator_pass_reasons": rec["evaluator_pass_reasons"],
                "clinical_danger": rec["clinical_danger"],
                "is_intro_case": rec["episode_id"] in [c["episode_id"] for c in intro_cases],
            }
        )

    json_out = {
        "metadata": {
            "source": str(VERDICT_FILE.relative_to(REPO_ROOT)),
            "n_episodes": len(json_records),
            "intro_case_ids": [c["episode_id"] for c in intro_cases],
            "description": (
                "9 poster-child near-miss episodes: pass all process-oblivious evaluators "
                "but contain hard violations detected by CGA-Bench."
            ),
        },
        "episodes": json_records,
    }

    json_path = ANALYSIS_DIR / "c3_poster_child.json"
    with open(json_path, "w") as fh:
        json.dump(json_out, fh, indent=2)
    print(f"Written: {json_path}")

    print("\nDone. Summary:")
    print(f"  Episodes analysed : {len(records)}")
    print(f"  Intro cases       : {len(intro_cases)}")
    for c in intro_cases:
        print(f"    - {c['episode_id']}  ({c['scenario']}, {c['model']}, run {c['run']})")


if __name__ == "__main__":
    main()
