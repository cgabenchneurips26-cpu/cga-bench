
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""D2: Parallel Order Analysis — Can Timing Violations Be Resolved by Parallelisation?

For each timing violation across the 180 rescored episodes, determines whether
the delay was:
  - Unavoidable (sequential clinical dependencies alone exhaust the deadline)
  - Agent-caused (off-protocol insertions pushed the violated action past deadline)
  - Parallelisable (agent performed only valid prior actions that could run
    concurrently, so zero-latency parallel ordering would resolve the violation)

Outputs
-------
  results/parallel_order/analysis.json           — full structured results
  results/parallel_order/analysis.csv            — per-violation detail rows
  evidence_pack/tables/parallel_order.tex        — LaTeX summary table
  evidence_pack/analysis/d2_parallel_order.json  — structured results
  evidence_pack/analysis/d2_parallel_order.md    — human-readable narrative

Run: PYTHONPATH=. python scripts/experiments/d2_parallel_order_analysis.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RESCORED_DIR = REPO_ROOT / "results" / "clean_slate_rescored"
ARCHIVE_DIR = REPO_ROOT / "_archive" / "results" / "clean_slate_20260331_210910"
OUTPUT_DIR = REPO_ROOT / "results" / "parallel_order"
ANALYSIS_DIR = REPO_ROOT / "evidence_pack" / "analysis"
TABLES_DIR = REPO_ROOT / "evidence_pack" / "tables"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODELS: list[str] = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]
MODEL_LABELS: dict[str, str] = {
    "oss120b": "DeepSeek-V3 (120B)",
    "qwen27b": "R1-Distill (27B)",
    "qwen35b": "Qwen3.5 (35B)",
    "qwen4b": "Qwen3 (4B)",
}

# Assumed sequential step duration when no concurrency is possible (minutes).
# Each prior action that is a hard dependency occupies one time-step before
# the violated action can legally start.
SEQ_STEP_MINUTES: float = 5.0

# Sequential clinical dependencies: actions whose RESULT must be available
# before the target action may safely proceed.  Keys are the violated action;
# values are sets of action_id prefixes/exact names that constitute hard deps.
SEQUENTIAL_DEPS: dict[str, list[str]] = {
    # Culture specimen must be drawn before antibiotics (SSC 2021)
    "give_broad_spectrum_antibiotics": [
        "order_lab_blood_culture",
        "blood_culture",
    ],
    # Potassium must be checked/corrected before insulin (ADA 2024 §4.2)
    "give_insulin": [
        "check_potassium",
        "order_lab_potassium",
        "order_lab_bmp",
    ],
    "start_insulin_infusion": [
        "check_potassium",
        "order_lab_potassium",
        "order_lab_bmp",
    ],
    # NIHSS assessment + non-contrast CT required before tPA (AHA 2019)
    "give_alteplase_0.9mg_kg": [
        "assess_nihss",
        "calculate_nihss_score",
        "order_ct_head",
        "order_imaging_ct_head",
        "order_imaging_ct",
    ],
    # 12-lead ECG interpretation must precede cath lab activation (AHA 2021)
    "activate_cath_lab": [
        "obtain_12_lead_ecg",
        "order_imaging_ecg",
        "interpret_ecg",
    ],
    # Adequate fluid challenge before vasopressors (SSC 2021)
    "start_vasopressor_norepinephrine": [
        "give_crystalloid_30ml_kg",
        "give_crystalloid_fluid",
    ],
    "start_vasopressor_if_hypotensive": [
        "give_crystalloid_30ml_kg",
        "give_crystalloid_fluid",
    ],
    # Anticoagulation assessment before rate/rhythm control (ESC AF 2020)
    "give_rate_control_agent": [
        "assess_chadsvasc_score",
        "order_lab_tsh",
    ],
    # Haemodynamic stabilisation before endoscopy (ACG 2023)
    "perform_upper_endoscopy": [
        "give_crystalloid_fluid",
        "give_crystalloid_30ml_kg",
        "give_blood_transfusion",
    ],
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------
class ViolationRecord(NamedTuple):
    """One analysed timing violation."""

    model: str
    scenario_id: str
    run_index: int
    source_file: str
    violation_id: str
    action_involved: str
    actual_time: float
    expected_deadline: float
    margin_minutes: float  # actual_time - expected_deadline
    harm_severity: str
    prior_actions_count: int
    seq_dep_count: int
    agent_inserted_count: int
    parallelisable_count: int
    adjusted_time: float  # time if only seq deps counted
    category: str  # "unavoidable" | "agent_caused" | "parallelisable"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _action_matches(action_id: str, patterns: list[str]) -> bool:
    """Return True if action_id matches any pattern (exact or prefix)."""
    return any(action_id == pat or action_id.startswith(pat) for pat in patterns)


def _classify_prior_action(
    action_id: str,
    violated_action: str,
    expected_actions: set[str],
) -> str:
    """Classify a single prior action relative to the violated action.

    Returns one of:
      "seq_dep"       — hard sequential dependency
      "agent_inserted"— off-protocol action not in expected set
      "parallelisable"— expected/protocol action with no hard dependency
    """
    deps = SEQUENTIAL_DEPS.get(violated_action, [])
    if _action_matches(action_id, deps):
        return "seq_dep"
    if action_id not in expected_actions:
        return "agent_inserted"
    return "parallelisable"


def _adjusted_time(seq_dep_count: int) -> float:
    """Minimum time for violated action if only sequential deps must precede it.

    Each hard dep takes SEQ_STEP_MINUTES; the violated action itself takes
    one more step, so the earliest possible execution is at turn (N+1)*step
    where N = number of sequential deps.
    """
    return (seq_dep_count + 1) * SEQ_STEP_MINUTES


def _categorise(
    actual_time: float,
    expected_deadline: float,
    seq_dep_count: int,
    agent_inserted_count: int,
) -> str:
    """Assign one of three categories to a timing violation."""
    adj = _adjusted_time(seq_dep_count)
    if adj > expected_deadline:
        return "unavoidable"
    if agent_inserted_count > 0:
        return "agent_caused"
    return "parallelisable"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_rescored_episodes() -> list[dict]:
    """Load all 180 rescored episodes."""
    episodes: list[dict] = []
    for model in MODELS:
        model_dir = RESCORED_DIR / model
        if not model_dir.exists():
            continue
        for fpath in sorted(model_dir.glob("*.json")):
            with fpath.open() as fh:
                ep = json.load(fh)
            ep["_model"] = model
            ep["_rescored_path"] = str(fpath)
            episodes.append(ep)
    return episodes


def load_original_actions(model: str, source_file: str) -> list[dict]:
    """Return the actions list from the original (archive) episode file."""
    orig_path = ARCHIVE_DIR / model / source_file
    if not orig_path.exists():
        return []
    with orig_path.open() as fh:
        orig = json.load(fh)
    return orig.get("actions", [])


def load_original_expected_actions(model: str, source_file: str) -> list[str]:
    """Return expected_actions from the original episode file."""
    orig_path = ARCHIVE_DIR / model / source_file
    if not orig_path.exists():
        return []
    with orig_path.open() as fh:
        orig = json.load(fh)
    return orig.get("expected_actions", [])


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def analyse_timing_violation(
    model: str,
    ep: dict,
    violation: dict,
    orig_actions: list[dict],
    expected_set: set[str],
) -> ViolationRecord:
    """Analyse a single timing violation and produce a ViolationRecord."""
    violated_action = violation.get("action_involved", "")
    actual_time = float(violation.get("actual_time") or violation.get("timestamp_minutes") or 0.0)
    deadline = float(violation.get("expected_deadline") or 0.0)
    margin = actual_time - deadline

    # Actions performed strictly before the violated action (by timestamp)
    prior_actions = [
        a for a in orig_actions if float(a.get("timestamp", a.get("timestamp_minutes", 0.0))) < actual_time
    ]

    seq_dep_count = 0
    agent_inserted_count = 0
    parallelisable_count = 0

    for a in prior_actions:
        aid = a.get("action_id", "")
        cls = _classify_prior_action(aid, violated_action, expected_set)
        if cls == "seq_dep":
            seq_dep_count += 1
        elif cls == "agent_inserted":
            agent_inserted_count += 1
        else:
            parallelisable_count += 1

    adj = _adjusted_time(seq_dep_count)
    category = _categorise(actual_time, deadline, seq_dep_count, agent_inserted_count)

    return ViolationRecord(
        model=model,
        scenario_id=ep.get("scenario_id", ""),
        run_index=ep.get("run_index", 0),
        source_file=ep.get("source_file", ""),
        violation_id=violation.get("violation_id", ""),
        action_involved=violated_action,
        actual_time=actual_time,
        expected_deadline=deadline,
        margin_minutes=margin,
        harm_severity=violation.get("harm_severity", ""),
        prior_actions_count=len(prior_actions),
        seq_dep_count=seq_dep_count,
        agent_inserted_count=agent_inserted_count,
        parallelisable_count=parallelisable_count,
        adjusted_time=adj,
        category=category,
    )


def run_analysis() -> list[ViolationRecord]:
    """Run the full analysis over all rescored episodes."""
    episodes = load_rescored_episodes()
    records: list[ViolationRecord] = []

    for ep in episodes:
        model = ep["_model"]
        source_file = ep.get("source_file", "")
        violation_events = ep.get("new_violation_events", [])

        timing_violations = [v for v in violation_events if v.get("violation_type") == "timing"]
        if not timing_violations:
            continue

        orig_actions = load_original_actions(model, source_file)
        expected_actions = load_original_expected_actions(model, source_file)
        expected_set = set(expected_actions)

        for v in timing_violations:
            rec = analyse_timing_violation(model, ep, v, orig_actions, expected_set)
            records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate(records: list[ViolationRecord]) -> dict:
    """Compute summary counts and percentages."""
    total = len(records)
    if total == 0:
        return {"total": 0}

    counts: dict[str, int] = {
        "unavoidable": 0,
        "agent_caused": 0,
        "parallelisable": 0,
    }
    by_model: dict[str, dict[str, int]] = {
        m: {"unavoidable": 0, "agent_caused": 0, "parallelisable": 0} for m in MODELS
    }
    by_scenario: dict[str, dict[str, int]] = {}

    for r in records:
        counts[r.category] += 1
        if r.model in by_model:
            by_model[r.model][r.category] += 1
        sid = r.scenario_id
        if sid not in by_scenario:
            by_scenario[sid] = {"unavoidable": 0, "agent_caused": 0, "parallelisable": 0}
        by_scenario[sid][r.category] += 1

    def pct(n: int) -> float:
        return round(100.0 * n / total, 1) if total else 0.0

    summary = {
        "total_timing_violations": total,
        "unavoidable": {
            "count": counts["unavoidable"],
            "pct": pct(counts["unavoidable"]),
        },
        "agent_caused": {
            "count": counts["agent_caused"],
            "pct": pct(counts["agent_caused"]),
        },
        "parallelisable": {
            "count": counts["parallelisable"],
            "pct": pct(counts["parallelisable"]),
        },
        "by_model": {},
        "by_scenario": {},
    }

    for m, mc in by_model.items():
        mt = sum(mc.values())

        def mpct(n: int, t: int = mt) -> float:
            return round(100.0 * n / t, 1) if t else 0.0

        summary["by_model"][m] = {
            "label": MODEL_LABELS.get(m, m),
            "total": mt,
            "unavoidable": {"count": mc["unavoidable"], "pct": mpct(mc["unavoidable"])},
            "agent_caused": {"count": mc["agent_caused"], "pct": mpct(mc["agent_caused"])},
            "parallelisable": {"count": mc["parallelisable"], "pct": mpct(mc["parallelisable"])},
        }

    for sid, sc in sorted(by_scenario.items()):
        st = sum(sc.values())

        def spct(n: int, t: int = st) -> float:
            return round(100.0 * n / t, 1) if t else 0.0

        summary["by_scenario"][sid] = {
            "total": st,
            "unavoidable": {"count": sc["unavoidable"], "pct": spct(sc["unavoidable"])},
            "agent_caused": {"count": sc["agent_caused"], "pct": spct(sc["agent_caused"])},
            "parallelisable": {"count": sc["parallelisable"], "pct": spct(sc["parallelisable"])},
        }

    return summary


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def write_json(records: list[ViolationRecord], summary: dict) -> None:
    """Write results/parallel_order/analysis.json and evidence_pack copy."""
    payload = {
        "summary": summary,
        "violations": [r._asdict() for r in records],
    }
    for out in (OUTPUT_DIR / "analysis.json", ANALYSIS_DIR / "d2_parallel_order.json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w") as fh:
            json.dump(payload, fh, indent=2)
        print(f"Written: {out}")


def write_csv(records: list[ViolationRecord]) -> None:
    """Write per-violation CSV to results/parallel_order/analysis.csv."""
    out = OUTPUT_DIR / "analysis.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(ViolationRecord._fields)
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow(r._asdict())
    print(f"Written: {out}")


def write_tex(summary: dict) -> None:
    """Write LaTeX summary table to evidence_pack/tables/parallel_order.tex."""
    total = summary.get("total_timing_violations", 0)
    unav = summary.get("unavoidable", {})
    ag = summary.get("agent_caused", {})
    par = summary.get("parallelisable", {})

    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    out = TABLES_DIR / "parallel_order.tex"

    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Parallelisation Analysis of Timing Violations}",
        r"\label{tab:parallel_order}",
        r"\begin{tabular}{lrr}",
        r"\toprule",
        r"Category & Count & \% \\",
        r"\midrule",
        (f"Sequential dependency (unavoidable) & {unav.get('count', 0)} & {unav.get('pct', 0.0):.1f}\\% \\\\"),
        (f"Agent-inserted delay & {ag.get('count', 0)} & {ag.get('pct', 0.0):.1f}\\% \\\\"),
        (f"Parallelisable (resolvable) & {par.get('count', 0)} & {par.get('pct', 0.0):.1f}\\% \\\\"),
        r"\midrule",
        f"Total timing violations & {total} & 100.0\\% \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    with out.open("w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Written: {out}")


def write_md(records: list[ViolationRecord], summary: dict) -> None:
    """Write human-readable narrative to evidence_pack/analysis/d2_parallel_order.md."""
    total = summary.get("total_timing_violations", 0)
    unav = summary.get("unavoidable", {})
    ag = summary.get("agent_caused", {})
    par = summary.get("parallelisable", {})

    lines = [
        "# D2: Parallel Order Analysis",
        "",
        "## Question",
        "",
        "Can timing violations in the clean-slate experiment be resolved by",
        "parallelising independent actions (ordering labs and imaging",
        "simultaneously rather than sequentially)?",
        "",
        "## Methodology",
        "",
        "For each timing violation in the 180 rescored episodes we:",
        "",
        "1. Identified all actions performed **before** the violated action.",
        "2. Classified each prior action as:",
        "   - **Sequential dependency** — clinically required before the violated",
        "     action (e.g., blood culture before antibiotics).",
        "   - **Agent-inserted** — off-protocol action not in the expected set.",
        "   - **Parallelisable** — expected/protocol action with no hard dependency.",
        "3. Computed the *adjusted timestamp*: minimum time assuming only sequential",
        f"   dependencies precede the violated action ({SEQ_STEP_MINUTES:.0f} min each).",
        "4. Categorised the violation:",
        "   - **Unavoidable** — adjusted time still exceeds the deadline.",
        "   - **Agent-caused** — agent-inserted actions pushed the action late.",
        "   - **Parallelisable** — would resolve with zero-latency parallel ordering.",
        "",
        "## Results",
        "",
        "| Category | Count | % |",
        "|---|---:|---:|",
        (f"| Sequential dependency (unavoidable) | {unav.get('count', 0)} | {unav.get('pct', 0.0):.1f}% |"),
        (f"| Agent-inserted delay | {ag.get('count', 0)} | {ag.get('pct', 0.0):.1f}% |"),
        (f"| Parallelisable (resolvable) | {par.get('count', 0)} | {par.get('pct', 0.0):.1f}% |"),
        f"| **Total timing violations** | **{total}** | **100%** |",
        "",
        "## Per-Model Breakdown",
        "",
        "| Model | Total | Unavoidable | Agent-caused | Parallelisable |",
        "|---|---:|---:|---:|---:|",
    ]

    for m in MODELS:
        bm = summary.get("by_model", {}).get(m, {})
        label = bm.get("label", m)
        mt = bm.get("total", 0)
        u = bm.get("unavoidable", {})
        a = bm.get("agent_caused", {})
        p = bm.get("parallelisable", {})
        lines.append(
            f"| {label} | {mt} | "
            f"{u.get('count', 0)} ({u.get('pct', 0.0):.0f}%) | "
            f"{a.get('count', 0)} ({a.get('pct', 0.0):.0f}%) | "
            f"{p.get('count', 0)} ({p.get('pct', 0.0):.0f}%) |"
        )

    # Compute marginal insertion stats
    marginal_count = sum(1 for r in records if r.agent_inserted_count <= 2)
    marginal_pct = round(100.0 * marginal_count / total, 1) if total > 0 else 0.0
    strong_count = total - marginal_count
    strong_pct = round(100.0 * strong_count / total, 1) if total > 0 else 0.0

    lines += [
        "",
        "## Interpretation",
        "",
    ]

    par_pct = par.get("pct", 0.0)
    unav_pct = unav.get("pct", 0.0)
    ag_pct = ag.get("pct", 0.0)

    if par_pct >= 50.0:
        interpretation = (
            f"A majority ({par_pct:.1f}%) of timing violations are parallelisable — "
            "they would disappear if the agent issued independent orders concurrently. "
            "This suggests the primary bottleneck is sequential thinking rather than "
            "intrinsic clinical infeasibility."
        )
    elif par_pct >= 25.0:
        interpretation = (
            f"A substantial minority ({par_pct:.1f}%) of timing violations are "
            "parallelisable. Parallel ordering would reduce timing violations by "
            f"roughly one quarter, while {unav_pct:.1f}% remain unavoidable due to "
            "hard clinical dependencies."
        )
    else:
        interpretation = (
            f"Most timing violations ({unav_pct:.1f}% unavoidable + "
            f"{ag_pct:.1f}% agent-caused = "
            f"{unav_pct + ag_pct:.1f}%) cannot be resolved by parallelisation alone. "
            f"Only {par_pct:.1f}% would benefit from concurrent ordering."
        )

    lines.append(interpretation)
    lines.append("")

    lines += [
        "## Insertion Strength Analysis",
        "",
        "Not all agent-caused violations have equal attribution confidence.",
        "We stratify by insertion count (number of off-protocol prior actions):",
        "",
        "| Insertion strength | Count | % | Description |",
        "|---|---:|---:|---|",
        f"| Strong (>2 insertions) | {strong_count} | {strong_pct:.1f}% | Multiple unnecessary actions clearly caused the delay |",
        f"| Marginal (<=2 insertions) | {marginal_count} | {marginal_pct:.1f}% | Few insertions; delay may partly reflect sequential ordering |",
        f"| **Total** | **{total}** | **100%** | |",
        "",
        f"Of the {total} agent-caused violations, **{strong_count} ({strong_pct:.1f}%)** have "
        f"strong attribution (>2 off-protocol insertions before the deadline miss), "
        f"while **{marginal_count} ({marginal_pct:.1f}%)** are marginal cases where only "
        "1-2 insertions preceded the target action. In marginal cases, the delay "
        "could partly reflect sequential dependencies rather than pure agent error.",
        "",
    ]

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    out = ANALYSIS_DIR / "d2_parallel_order.md"
    with out.open("w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"Written: {out}")


def print_table(summary: dict) -> None:
    """Print the summary table to stdout."""
    total = summary.get("total_timing_violations", 0)
    unav = summary.get("unavoidable", {})
    ag = summary.get("agent_caused", {})
    par = summary.get("parallelisable", {})

    print()
    print("=" * 60)
    print("D2 Parallel Order Analysis — Summary")
    print("=" * 60)
    print(f"{'Category':<42} {'Count':>6}  {'%':>6}")
    print("-" * 60)
    print(f"{'Sequential dependency (unavoidable)':<42} {unav.get('count', 0):>6}  {unav.get('pct', 0.0):>5.1f}%")
    print(f"{'Agent-inserted delay':<42} {ag.get('count', 0):>6}  {ag.get('pct', 0.0):>5.1f}%")
    print(f"{'Parallelisable (resolvable)':<42} {par.get('count', 0):>6}  {par.get('pct', 0.0):>5.1f}%")
    print("-" * 60)
    print(f"{'Total timing violations':<42} {total:>6}  100.0%")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point: run analysis and write all outputs."""
    print("Loading and analysing timing violations ...")
    records = run_analysis()
    summary = aggregate(records)

    print_table(summary)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json(records, summary)
    write_csv(records)
    write_tex(summary)
    write_md(records, summary)

    print(f"\nDone. {len(records)} timing violations analysed across {len(MODELS)} models.")


if __name__ == "__main__":
    main()
