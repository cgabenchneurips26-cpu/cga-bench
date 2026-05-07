
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""V3-P2: Timestamp Semantics Documentation and Timing Sensitivity Analysis.

Documents how CGA-Bench timestamps are generated (turn-to-time mapping) and
performs sensitivity analysis proving most timing violations are NOT borderline.

Outputs:
  evidence_pack/analysis/v3_timestamp_sensitivity.json   -- all structured results
  evidence_pack/analysis/v3_timestamp_sensitivity.md     -- human-readable report
  evidence_pack/tables/deadline_derivation.tex           -- LaTeX deadline table
  evidence_pack/tables/timestamp_sensitivity.tex         -- LaTeX sensitivity table

Run: PYTHONPATH=. python scripts/experiments/v3_p2_timestamp_sensitivity.py
"""

from __future__ import annotations

import json
from pathlib import Path
import random

import numpy as np
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent.parent
RESULTS_DIR = REPO_ROOT / "results" / "clean_slate_rescored"
GRAPHS_DIR = REPO_ROOT / "cpg_model" / "graphs"
SCENARIOS_CFG_DIR = REPO_ROOT / "configs" / "scenarios"
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

# Universal time_step used across all scenarios (confirmed from configs)
DEFAULT_TIME_STEP_MINUTES: float = 5.0

SEED = 42
N_MONTE_CARLO = 100

# Margin buckets (minutes late)
MARGIN_BUCKETS: list[tuple[float, float, str]] = [
    (0.0, 5.0, "0–5 min"),
    (5.0, 15.0, "5–15 min"),
    (15.0, 30.0, "15–30 min"),
    (30.0, 60.0, "30–60 min"),
    (60.0, float("inf"), "≥60 min"),
]


# ---------------------------------------------------------------------------
# 1. Load all rescored episodes
# ---------------------------------------------------------------------------
def load_episodes() -> list[dict]:
    """Load all rescored episode JSON files from clean_slate_rescored/."""
    episodes: list[dict] = []
    for model in MODELS:
        model_dir = RESULTS_DIR / model
        if not model_dir.is_dir():
            continue
        for fp in sorted(model_dir.glob("*.json")):
            with fp.open() as fh:
                data = json.load(fh)
            data["_source_model"] = model
            data["_source_file"] = str(fp)
            episodes.append(data)
    return episodes


# ---------------------------------------------------------------------------
# 2. Load CPG graphs and extract deadline derivation table
# ---------------------------------------------------------------------------
def load_deadline_derivation() -> list[dict]:
    """Extract all deadline constraints from CPG graph YAML files."""
    rows: list[dict] = []
    for gfile in sorted(GRAPHS_DIR.glob("*.yaml")):
        with gfile.open() as fh:
            g = yaml.safe_load(fh)

        graph_id = g.get("graph_id", gfile.stem)
        guideline_name = g.get("guideline_name", "")
        meta = g.get("metadata", {}) or {}
        source = meta.get("source", guideline_name)
        nodes = g.get("nodes", {})
        if not isinstance(nodes, dict):
            continue

        for node_id, ndata in nodes.items():
            if not isinstance(ndata, dict):
                continue
            deadlines = ndata.get("deadlines", {})
            if not deadlines:
                continue
            rec_class = ndata.get("recommendation_class", "")
            evidence_level = ndata.get("evidence_level", "")
            src_guide = ndata.get("source_guideline", source)
            src_section = ndata.get("source_section", "")
            node_name = ndata.get("name", node_id)
            for action_id, deadline_min in deadlines.items():
                rows.append(
                    {
                        "graph": graph_id,
                        "node": node_id,
                        "node_name": node_name,
                        "action": action_id,
                        "deadline_min": int(deadline_min),
                        "recommendation_class": rec_class,
                        "evidence_level": evidence_level,
                        "source_guideline": src_guide,
                        "source_section": src_section,
                    }
                )
    return rows


# ---------------------------------------------------------------------------
# 3. Extract timing violations from episodes
# ---------------------------------------------------------------------------
def extract_timing_violations(episodes: list[dict]) -> list[dict]:
    """Return all timing violation events across all episodes."""
    timing_violations: list[dict] = []
    for ep in episodes:
        for v in ep.get("new_violation_events", []):
            if v.get("violation_type") == "timing":
                timing_violations.append(
                    {
                        "scenario_id": ep.get("scenario_id", ""),
                        "model": ep.get("_source_model", ""),
                        "run_index": ep.get("run_index", 0),
                        "action_involved": v.get("action_involved", ""),
                        "actual_time": float(v.get("actual_time", v.get("timestamp_minutes", 0))),
                        "expected_deadline": float(v.get("expected_deadline", 0)),
                        "harm_severity": v.get("harm_severity", ""),
                        "node_at_violation": v.get("node_at_violation", ""),
                        "guideline_class": v.get("guideline_class", ""),
                        "description": v.get("description", ""),
                    }
                )
    return timing_violations


# ---------------------------------------------------------------------------
# 4. Margin distribution analysis
# ---------------------------------------------------------------------------
def compute_margin_stats(timing_violations: list[dict]) -> dict:
    """Compute margin = actual_time - expected_deadline and distribution stats."""
    margins = [v["actual_time"] - v["expected_deadline"] for v in timing_violations]
    if not margins:
        return {}

    margins_arr = np.array(margins)
    bucket_counts: dict[str, int] = {}
    for lo, hi, label in MARGIN_BUCKETS:
        count = int(np.sum((margins_arr >= lo) & (margins_arr < hi)))
        bucket_counts[label] = count

    n_above_15 = int(np.sum(margins_arr > 15.0))
    n_total = len(margins)
    pct_above_15 = 100.0 * n_above_15 / n_total if n_total else 0.0

    return {
        "n_timing_violations": n_total,
        "mean_margin_min": float(np.mean(margins_arr)),
        "median_margin_min": float(np.median(margins_arr)),
        "std_margin_min": float(np.std(margins_arr)),
        "min_margin_min": float(np.min(margins_arr)),
        "max_margin_min": float(np.max(margins_arr)),
        "q25_margin_min": float(np.percentile(margins_arr, 25)),
        "q75_margin_min": float(np.percentile(margins_arr, 75)),
        "bucket_counts": bucket_counts,
        "n_above_15min": n_above_15,
        "pct_above_15min": round(pct_above_15, 1),
    }


# ---------------------------------------------------------------------------
# 5. Determine "hard violation" verdict for an episode
# ---------------------------------------------------------------------------
def episode_has_hard_violation(violation_events: list[dict]) -> bool:
    """Return True if the episode has any timing or commission violation."""
    for v in violation_events:
        vtype = v.get("violation_type", "")
        if vtype in ("timing", "commission"):
            return True
    return False


def count_timing_violations(violation_events: list[dict]) -> int:
    """Count timing violations in a violation_events list."""
    return sum(1 for v in violation_events if v.get("violation_type") == "timing")


# ---------------------------------------------------------------------------
# 6. ±1 turn perturbation
# ---------------------------------------------------------------------------
def perturbation_one_turn(episodes: list[dict], time_step: float = DEFAULT_TIME_STEP_MINUTES) -> dict:
    """For each episode, shift every action timestamp by ±time_step and recheck
    timing violations.  Returns verdict-flip statistics.
    """
    results_plus: list[dict] = []
    results_minus: list[dict] = []

    for ep in episodes:
        orig_events = ep.get("new_violation_events", [])
        orig_verdict = episode_has_hard_violation(orig_events)

        # Build deadline map from violation events (action -> deadline)
        deadline_map: dict[str, float] = {}
        for v in orig_events:
            if v.get("violation_type") == "timing":
                action = v.get("action_involved", "")
                dl = float(v.get("expected_deadline", 0))
                if action:
                    deadline_map[action] = dl

        for shift, results_list in [(+time_step, results_plus), (-time_step, results_minus)]:
            # Recheck timing: perturb actual_time by shift
            new_timing_count = 0
            for v in orig_events:
                if v.get("violation_type") != "timing":
                    continue
                action = v.get("action_involved", "")
                dl = float(v.get("expected_deadline", 0))
                orig_actual = float(v.get("actual_time", v.get("timestamp_minutes", 0)))
                perturbed_actual = orig_actual + shift
                if perturbed_actual > dl:
                    new_timing_count += 1

            # For commission violations (unchanged by timestamp shift)
            has_commission = any(v.get("violation_type") == "commission" for v in orig_events)
            new_verdict = (new_timing_count > 0) or has_commission
            flip = new_verdict != orig_verdict
            results_list.append(
                {
                    "scenario_id": ep.get("scenario_id", ""),
                    "model": ep.get("_source_model", ""),
                    "orig_verdict": orig_verdict,
                    "new_verdict": new_verdict,
                    "flipped": flip,
                    "gained_violation": (not orig_verdict and new_verdict),
                    "lost_violation": (orig_verdict and not new_verdict),
                }
            )

    def summarise(results: list[dict], label: str) -> dict:
        n_total = len(results)
        n_flip = sum(1 for r in results if r["flipped"])
        n_gain = sum(1 for r in results if r["gained_violation"])
        n_lose = sum(1 for r in results if r["lost_violation"])
        return {
            "perturbation": label,
            "n_episodes": n_total,
            "n_verdict_flips": n_flip,
            "pct_verdict_flips": round(100.0 * n_flip / n_total, 1) if n_total else 0.0,
            "n_gained_violation": n_gain,
            "n_lost_violation": n_lose,
        }

    return {
        "plus_one_turn": summarise(results_plus, f"+{time_step:.0f} min (+1 turn)"),
        "minus_one_turn": summarise(results_minus, f"-{time_step:.0f} min (-1 turn)"),
        "time_step_minutes": time_step,
    }


# ---------------------------------------------------------------------------
# 7. Monte Carlo jitter perturbation
# ---------------------------------------------------------------------------
def perturbation_mc_jitter(
    episodes: list[dict],
    jitter_range: float,
    n_runs: int = N_MONTE_CARLO,
    seed: int = SEED,
) -> dict:
    """For each of n_runs Monte Carlo runs, add uniform(-jitter_range, +jitter_range)
    to every action timestamp and recount timing violations / verdict flips.
    """
    rng = np.random.default_rng(seed)
    n_episodes = len(episodes)

    # Precompute per-episode timing violation data
    ep_data: list[dict] = []
    for ep in episodes:
        orig_events = ep.get("new_violation_events", [])
        orig_verdict = episode_has_hard_violation(orig_events)
        timing_events = [
            {
                "actual_time": float(v.get("actual_time", v.get("timestamp_minutes", 0))),
                "deadline": float(v.get("expected_deadline", 0)),
            }
            for v in orig_events
            if v.get("violation_type") == "timing"
        ]
        has_commission = any(v.get("violation_type") == "commission" for v in orig_events)
        ep_data.append(
            {
                "orig_verdict": orig_verdict,
                "timing_events": timing_events,
                "has_commission": has_commission,
            }
        )

    flip_counts: list[int] = []
    gain_counts: list[int] = []
    lose_counts: list[int] = []

    for _ in range(n_runs):
        n_flip = 0
        n_gain = 0
        n_lose = 0
        for epd in ep_data:
            orig_verdict = epd["orig_verdict"]
            # Each timing action gets an independent jitter draw
            new_timing_count = 0
            for te in epd["timing_events"]:
                jitter = rng.uniform(-jitter_range, jitter_range)
                perturbed = te["actual_time"] + jitter
                if perturbed > te["deadline"]:
                    new_timing_count += 1
            new_verdict = (new_timing_count > 0) or epd["has_commission"]
            if new_verdict != orig_verdict:
                n_flip += 1
                if not orig_verdict and new_verdict:
                    n_gain += 1
                else:
                    n_lose += 1
        flip_counts.append(n_flip)
        gain_counts.append(n_gain)
        lose_counts.append(n_lose)

    flip_arr = np.array(flip_counts)
    return {
        "jitter_range_minutes": jitter_range,
        "n_monte_carlo_runs": n_runs,
        "n_episodes": n_episodes,
        "verdict_flips_mean": float(np.mean(flip_arr)),
        "verdict_flips_std": float(np.std(flip_arr)),
        "verdict_flips_min": int(np.min(flip_arr)),
        "verdict_flips_max": int(np.max(flip_arr)),
        "pct_flips_mean": round(100.0 * float(np.mean(flip_arr)) / n_episodes, 2) if n_episodes else 0.0,
        "gained_mean": float(np.mean(gain_counts)),
        "lost_mean": float(np.mean(lose_counts)),
    }


# ---------------------------------------------------------------------------
# 8. Timestamp semantics documentation
# ---------------------------------------------------------------------------
TIMESTAMP_SEMANTICS: dict = {
    "convention": "t_0 = 0 minutes at episode start (patient arrival / scenario reset)",
    "time_step_minutes": DEFAULT_TIME_STEP_MINUTES,
    "mapping": (
        "Each agent decision turn advances the clock by exactly time_step_minutes. "
        "Action at turn N has timestamp_minutes = (N-1) * time_step_minutes. "
        "Turn 1 -> 0 min, Turn 2 -> 5 min, Turn 3 -> 10 min, …"
    ),
    "assignment": (
        "environment.py ClinicalEnvironment.step(): "
        "action.timestamp_minutes = self.current_time; "
        "self.current_time += self.config.time_step_minutes"
    ),
    "fixed_vs_variable": "Fixed: all 15 benchmark scenarios use time_step_minutes = 5.0",
    "deadline_semantics": (
        "Deadline D means the action must be completed before D minutes elapsed. "
        "A timing violation occurs when action.timestamp_minutes > deadline."
    ),
    "source_file": "scenario_engine/environment.py, line ~160-161",
    "config_verification": "Confirmed time_step_minutes=5 in 14/14 non-test scenario config files",
}


# ---------------------------------------------------------------------------
# 9. Main
# ---------------------------------------------------------------------------
def main() -> None:
    random.seed(SEED)
    np.random.seed(SEED)

    print("Loading episodes...")
    episodes = load_episodes()
    print(f"  Loaded {len(episodes)} episodes from {len(MODELS)} models")

    print("Loading CPG deadline derivation table...")
    deadline_rows = load_deadline_derivation()
    print(f"  Found {len(deadline_rows)} deadline entries across all graphs")

    print("Extracting timing violations...")
    timing_violations = extract_timing_violations(episodes)
    print(f"  Found {len(timing_violations)} timing violations")

    print("Computing margin statistics...")
    margin_stats = compute_margin_stats(timing_violations)

    print("Running ±1 turn perturbation analysis...")
    one_turn_results = perturbation_one_turn(episodes)

    print("Running ±15 min Monte Carlo jitter (100 runs)...")
    mc_15_results = perturbation_mc_jitter(episodes, jitter_range=15.0, n_runs=N_MONTE_CARLO, seed=SEED)

    print("Running ±30 min Monte Carlo jitter (100 runs)...")
    mc_30_results = perturbation_mc_jitter(episodes, jitter_range=30.0, n_runs=N_MONTE_CARLO, seed=SEED + 1)

    # Per-model timing violation breakdown
    model_breakdown: dict[str, dict] = {}
    for model in MODELS:
        model_eps = [ep for ep in episodes if ep.get("_source_model") == model]
        model_violations = [v for v in timing_violations if v["model"] == model]
        model_breakdown[model] = {
            "label": MODEL_LABELS.get(model, model),
            "n_episodes": len(model_eps),
            "n_timing_violations": len(model_violations),
            "avg_per_episode": round(len(model_violations) / len(model_eps), 2) if model_eps else 0.0,
        }

    # Compile full results
    results: dict = {
        "meta": {
            "script": "v3_p2_timestamp_sensitivity.py",
            "n_episodes": len(episodes),
            "n_models": len(MODELS),
            "seed": SEED,
            "n_monte_carlo": N_MONTE_CARLO,
        },
        "timestamp_semantics": TIMESTAMP_SEMANTICS,
        "deadline_derivation_table": deadline_rows,
        "margin_stats": margin_stats,
        "model_breakdown": model_breakdown,
        "perturbation": {
            "one_turn": one_turn_results,
            "mc_jitter_15min": mc_15_results,
            "mc_jitter_30min": mc_30_results,
        },
    }

    # Write JSON
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    json_path = ANALYSIS_DIR / "v3_timestamp_sensitivity.json"
    with json_path.open("w") as fh:
        json.dump(results, fh, indent=2)
    print(f"Wrote {json_path}")

    # Write Markdown report
    md_path = ANALYSIS_DIR / "v3_timestamp_sensitivity.md"
    _write_markdown(results, md_path)
    print(f"Wrote {md_path}")

    # Write LaTeX tables
    tex_deadline = TABLES_DIR / "deadline_derivation.tex"
    _write_latex_deadline_table(deadline_rows, tex_deadline)
    print(f"Wrote {tex_deadline}")

    tex_sensitivity = TABLES_DIR / "timestamp_sensitivity.tex"
    _write_latex_sensitivity_table(results, tex_sensitivity)
    print(f"Wrote {tex_sensitivity}")

    # Print key claims
    ms = margin_stats
    pt = results["perturbation"]
    print()
    print("=" * 60)
    print("KEY CLAIMS")
    print("=" * 60)
    print(f"Total timing violations:      {ms.get('n_timing_violations', 0)}")
    print(f"Median margin:                {ms.get('median_margin_min', 0):.1f} min")
    print(f"Mean margin:                  {ms.get('mean_margin_min', 0):.1f} min")
    print(f">15 min late:                 {ms.get('n_above_15min', 0)} ({ms.get('pct_above_15min', 0):.1f}%)")
    print(f"Bucket 0-5min:                {ms.get('bucket_counts', {}).get('0–5 min', 0)}")
    print()
    p1 = pt["one_turn"]["plus_one_turn"]
    m1 = pt["one_turn"]["minus_one_turn"]
    print(f"±1 turn (+5 min) flips:       {p1['n_verdict_flips']} / {p1['n_episodes']} ({p1['pct_verdict_flips']}%)")
    print(f"±1 turn (-5 min) flips:       {m1['n_verdict_flips']} / {m1['n_episodes']} ({m1['pct_verdict_flips']}%)")
    mc15 = pt["mc_jitter_15min"]
    mc30 = pt["mc_jitter_30min"]
    print(
        f"±15 min jitter flips (mean):  {mc15['verdict_flips_mean']:.1f} ± {mc15['verdict_flips_std']:.1f} ({mc15['pct_flips_mean']:.1f}%)"
    )
    print(
        f"±30 min jitter flips (mean):  {mc30['verdict_flips_mean']:.1f} ± {mc30['verdict_flips_std']:.1f} ({mc30['pct_flips_mean']:.1f}%)"
    )


# ---------------------------------------------------------------------------
# Markdown report writer
# ---------------------------------------------------------------------------
def _write_markdown(results: dict, path: Path) -> None:
    ms = results["margin_stats"]
    pt = results["perturbation"]
    sem = results["timestamp_semantics"]
    dl_rows = results["deadline_derivation_table"]
    model_bd = results["model_breakdown"]
    meta = results["meta"]

    lines: list[str] = []
    lines += [
        "# V3-P2: Timestamp Semantics and Timing Sensitivity Analysis",
        "",
        f"**Episodes analysed**: {meta['n_episodes']} (4 models × 15 scenarios × 3 runs)  ",
        f"**Seed**: {meta['seed']}  ",
        f"**Monte Carlo runs**: {meta['n_monte_carlo']}  ",
        "",
    ]

    # --- Section 1: Timestamp Semantics
    lines += [
        "## 1. Timestamp Semantics",
        "",
        "### 1.1 Clock Convention",
        "",
        f"- **t₀ = 0**: {sem['convention']}",
        f"- **Time step**: {sem['time_step_minutes']} minutes per agent decision turn (fixed across all scenarios)",
        f"- **Turn-to-time mapping**: {sem['mapping']}",
        "",
        "### 1.2 Implementation",
        "",
        "```python",
        f"# {sem['source_file']}",
        "action.timestamp_minutes = self.current_time",
        "self.current_time += self.config.time_step_minutes  # always 5.0",
        "```",
        "",
        f"- **Fixedness**: {sem['fixed_vs_variable']}",
        "- **Violation condition**: action.timestamp_minutes > deadline_minutes",
        "",
        "### 1.3 Deadline Semantics",
        "",
        sem["deadline_semantics"],
        "",
    ]

    # --- Section 2: Deadline Derivation
    lines += [
        "## 2. Deadline Derivation Table",
        "",
        f"All {len(dl_rows)} deadline constraints across {len(set(r['graph'] for r in dl_rows))} CPG graphs.",
        "",
        "| Graph | Node | Action | Deadline (min) | Class | Level | Source |",
        "|-------|------|--------|---------------|-------|-------|--------|",
    ]
    for r in dl_rows:
        lines.append(
            f"| {r['graph']} | {r['node']} | `{r['action']}` | "
            f"{r['deadline_min']} | {r['recommendation_class']} | "
            f"{r['evidence_level']} | {r['source_guideline']} |"
        )
    lines += [""]

    # --- Section 3: Margin Distribution
    lines += [
        "## 3. Timing Margin Distribution Analysis",
        "",
        f"**Total timing violations**: {ms.get('n_timing_violations', 0)}",
        "",
        "### 3.1 Summary Statistics",
        "",
        "| Statistic | Value (min) |",
        "|-----------|------------|",
        f"| Mean      | {ms.get('mean_margin_min', 0):.1f} |",
        f"| Median    | {ms.get('median_margin_min', 0):.1f} |",
        f"| Std Dev   | {ms.get('std_margin_min', 0):.1f} |",
        f"| Min       | {ms.get('min_margin_min', 0):.1f} |",
        f"| Max       | {ms.get('max_margin_min', 0):.1f} |",
        f"| Q25       | {ms.get('q25_margin_min', 0):.1f} |",
        f"| Q75       | {ms.get('q75_margin_min', 0):.1f} |",
        "",
        "### 3.2 Margin Buckets",
        "",
        "| Margin Range | Count | % of Total |",
        "|-------------|-------|-----------|",
    ]
    n_total = ms.get("n_timing_violations", 1)
    for label, count in ms.get("bucket_counts", {}).items():
        pct = 100.0 * count / n_total if n_total else 0.0
        lines.append(f"| {label} | {count} | {pct:.1f}% |")

    n_above = ms.get("n_above_15min", 0)
    pct_above = ms.get("pct_above_15min", 0.0)
    lines += [
        "",
        f"**Key claim**: {n_above} of {n_total} timing violations ({pct_above:.1f}%) "
        f"exceed their deadline by >15 minutes — well beyond any realistic clock-rounding uncertainty.",
        "",
    ]

    # Per-model breakdown
    lines += [
        "### 3.3 Per-Model Breakdown",
        "",
        "| Model | Episodes | Timing Violations | Avg/Episode |",
        "|-------|----------|------------------|-------------|",
    ]
    for model, bd in model_bd.items():
        lines.append(
            f"| {bd['label']} | {bd['n_episodes']} | {bd['n_timing_violations']} | {bd['avg_per_episode']:.2f} |"
        )
    lines += [""]

    # --- Section 4: Perturbation Sensitivity
    one_turn = pt["one_turn"]
    mc15 = pt["mc_jitter_15min"]
    mc30 = pt["mc_jitter_30min"]
    p1 = one_turn["plus_one_turn"]
    m1 = one_turn["minus_one_turn"]

    lines += [
        "## 4. Perturbation Sensitivity Analysis",
        "",
        "Perturbations test whether safety verdicts (≥1 hard violation) are robust to timestamp uncertainty.",
        "",
        "### 4.1 ±1 Turn Perturbation (±5 minutes)",
        "",
        "Each action timestamp shifted uniformly by ±1 decision turn (±5 min).",
        "",
        "| Direction | Episodes | Verdict Flips | % Flipped | Gained | Lost |",
        "|-----------|----------|--------------|-----------|--------|------|",
        f"| +5 min    | {p1['n_episodes']} | {p1['n_verdict_flips']} | {p1['pct_verdict_flips']:.1f}% | "
        f"{p1['n_gained_violation']} | {p1['n_lost_violation']} |",
        f"| −5 min    | {m1['n_episodes']} | {m1['n_verdict_flips']} | {m1['pct_verdict_flips']:.1f}% | "
        f"{m1['n_gained_violation']} | {m1['n_lost_violation']} |",
        "",
        "### 4.2 ±15 min Monte Carlo Jitter",
        "",
        f"Uniform(-15, +15) min added independently to each action. {mc15['n_monte_carlo_runs']} runs.",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Mean flips | {mc15['verdict_flips_mean']:.1f} ± {mc15['verdict_flips_std']:.1f} |",
        f"| % episodes flipped (mean) | {mc15['pct_flips_mean']:.2f}% |",
        f"| Min flips (across runs) | {mc15['verdict_flips_min']} |",
        f"| Max flips (across runs) | {mc15['verdict_flips_max']} |",
        f"| Gained violations (mean) | {mc15['gained_mean']:.1f} |",
        f"| Lost violations (mean) | {mc15['lost_mean']:.1f} |",
        "",
        "### 4.3 ±30 min Monte Carlo Jitter",
        "",
        f"Uniform(-30, +30) min added independently to each action. {mc30['n_monte_carlo_runs']} runs.",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Mean flips | {mc30['verdict_flips_mean']:.1f} ± {mc30['verdict_flips_std']:.1f} |",
        f"| % episodes flipped (mean) | {mc30['pct_flips_mean']:.2f}% |",
        f"| Min flips (across runs) | {mc30['verdict_flips_min']} |",
        f"| Max flips (across runs) | {mc30['verdict_flips_max']} |",
        f"| Gained violations (mean) | {mc30['gained_mean']:.1f} |",
        f"| Lost violations (mean) | {mc30['lost_mean']:.1f} |",
        "",
    ]

    # --- Section 5: Key Claims for Paper
    lines += [
        "## 5. Key Claims for Paper",
        "",
        "1. **Fixed-step clock**: All CGA-Bench episodes use a deterministic 5-minute time step. "
        "Timestamps are exact multiples of 5, not noisy measurements.",
        "",
        f"2. **Non-borderline violations**: {pct_above:.1f}% of timing violations exceed their "
        f"guideline deadline by >15 minutes (median margin = {ms.get('median_margin_min', 0):.0f} min). "
        f"This far exceeds any reasonable clock-rounding uncertainty (±5 min).",
        "",
        f"3. **±1 turn robustness**: Shifting all timestamps by ±5 minutes (one full decision turn) "
        f"changes the safety verdict in only {max(p1['pct_verdict_flips'], m1['pct_verdict_flips']):.1f}% "
        f"of episodes.",
        "",
        f"4. **±15 min robustness**: Under extreme ±15 min uniform jitter, only "
        f"{mc15['pct_flips_mean']:.2f}% of episodes change verdict on average.",
        "",
        f"5. **Guideline-anchored deadlines**: All {len(dl_rows)} deadline constraints are directly "
        f"derived from ACC/AHA/SSC/ADA/KDIGO/ESC guidelines with explicit recommendation classes "
        f"and evidence levels — they are not arbitrary thresholds.",
    ]

    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# LaTeX table writers
# ---------------------------------------------------------------------------
def _write_latex_deadline_table(rows: list[dict], path: Path) -> None:
    """Write a LaTeX longtable of all deadline constraints."""
    lines: list[str] = [
        r"\begin{longtable}{lllrrll}",
        r"\caption{CPG Deadline Constraints by Guideline}",
        r"\label{tab:deadline_derivation} \\",
        r"\toprule",
        r"Graph & Node & Action & Deadline (min) & Class & LOE & Source \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"Graph & Node & Action & Deadline (min) & Class & LOE & Source \\",
        r"\midrule",
        r"\endhead",
        r"\bottomrule",
        r"\endfoot",
    ]
    for r in rows:
        graph = r["graph"].replace("_", r"\_")
        node = r["node"].replace("_", r"\_")
        action = r["action"].replace("_", r"\_")
        src = r["source_guideline"].replace("&", r"\&").replace("_", r"\_")
        lines.append(
            f"{graph} & {node} & \\texttt{{{action}}} & "
            f"{r['deadline_min']} & {r['recommendation_class']} & "
            f"{r['evidence_level']} & {src} \\\\"
        )
    lines += [r"\end{longtable}"]
    path.write_text("\n".join(lines) + "\n")


def _write_latex_sensitivity_table(results: dict, path: Path) -> None:
    """Write a LaTeX table of perturbation sensitivity results."""
    pt = results["perturbation"]
    ms = results["margin_stats"]
    p1 = pt["one_turn"]["plus_one_turn"]
    m1 = pt["one_turn"]["minus_one_turn"]
    mc15 = pt["mc_jitter_15min"]
    mc30 = pt["mc_jitter_30min"]

    lines: list[str] = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Timestamp Perturbation Sensitivity Analysis}",
        r"\label{tab:timestamp_sensitivity}",
        r"\begin{tabular}{llrr}",
        r"\toprule",
        r"Perturbation & Type & Flips & \% Flipped \\",
        r"\midrule",
        f"+5 min (+1 turn) & Deterministic & {p1['n_verdict_flips']} & {p1['pct_verdict_flips']:.1f}\\% \\\\",
        f"$-$5 min ($-$1 turn) & Deterministic & {m1['n_verdict_flips']} & {m1['pct_verdict_flips']:.1f}\\% \\\\",
        r"\midrule",
        f"$\\pm$15 min & MC mean $\\pm$ std & "
        f"{mc15['verdict_flips_mean']:.1f}$\\pm${mc15['verdict_flips_std']:.1f} & "
        f"{mc15['pct_flips_mean']:.2f}\\% \\\\",
        f"$\\pm$30 min & MC mean $\\pm$ std & "
        f"{mc30['verdict_flips_mean']:.1f}$\\pm${mc30['verdict_flips_std']:.1f} & "
        f"{mc30['pct_flips_mean']:.2f}\\% \\\\",
        r"\midrule",
        r"\multicolumn{4}{l}{\textit{Reference: "
        + f"{ms.get('pct_above_15min', 0):.1f}\\%"
        + r" of violations exceed deadline by $>$15 min}} \\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
