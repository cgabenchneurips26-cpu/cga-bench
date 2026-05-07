"""WS-6: Select Top-5 Poster-Child Case Studies.

Uses a multi-factor scoring algorithm to select the most illustrative
case studies for the paper:

  score = (
      0.30 * evaluator_disagreement_normalized +
      0.25 * clinical_severity_score +
      0.20 * model_diversity_score +
      0.15 * domain_novelty_bonus +
      0.10 * interpretability_score
  )

Output per selected case:
  - Scenario summary
  - Agent trace key actions
  - Each evaluator's verdict
  - What this case demonstrates

Usage:
    PYTHONPATH=. python scripts/experiments/ws6_select_poster_children.py
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from scripts.experiments._common import (
    EVIDENCE_DIR,
    RESULTS_DIR,
    save_json,
    save_markdown,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]
MODEL_LABELS: dict[str, str] = {
    "oss120b": "DeepSeek-V3 (120B)",
    "qwen27b": "R1-Distill (27B)",
    "qwen35b": "Qwen3.5 (35B)",
    "qwen4b": "Qwen3 (4B)",
}
MODEL_DIR_MAP: dict[str, str] = {
    "4B": "qwen4b",
    "27B": "qwen27b",
    "35B": "qwen35b",
    "120B": "oss120b",
}

EVALUATOR_KEYS = ["dxem", "ac_proxy", "mab_proxy", "c2_pass", "acov_pass", "v4_hard"]
EVALUATOR_LABELS = ["DxEM", "AC-Proxy", "MAB-Proxy", "C2", "ACov", "CGA-Bench"]

VERDICT_PATH = EVIDENCE_DIR / "analysis" / "verdict_matrix_v6.json"
CASE_STUDIES_DIR = EVIDENCE_DIR / "case_studies"

N_SELECT = 5

# Scoring weights
W_DISAGREEMENT = 0.30
W_SEVERITY = 0.25
W_MODEL_DIVERSITY = 0.20
W_DOMAIN_NOVELTY = 0.15
W_INTERPRETABILITY = 0.10

DOMAIN_PREFIXES: dict[str, str] = {
    "septic_shock": "sepsis",
    "sepsis": "sepsis",
    "stemi": "chest_pain",
    "nstemi": "chest_pain",
    "chest_pain": "chest_pain",
    "acs": "chest_pain",
    "stroke": "stroke",
    "tpa": "stroke",
    "hfref": "heart_failure",
    "adhf": "heart_failure",
    "aki": "aki",
    "contrast_aki": "aki",
    "dka": "dka",
    "af_": "atrial_fibrillation",
    "copd": "copd",
    "pe_": "pulmonary_embolism",
    "gi_bleed": "gi_bleeding",
    "cap_": "pneumonia",
    "hypertensive": "hypertensive_emergency",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_domain(scenario_id: str) -> str:
    """Extract clinical domain from scenario_id."""
    sid_lower = scenario_id.lower()
    for prefix, domain in DOMAIN_PREFIXES.items():
        if sid_lower.startswith(prefix):
            return domain
    return "other"


def load_verdict_episodes() -> list[dict]:
    """Load per-episode data from verdict matrix."""
    if not VERDICT_PATH.exists():
        return []
    with open(VERDICT_PATH) as f:
        data = json.load(f)
    return data.get("per_episode", [])


def find_episode_file(episode_id: str, model_key: str) -> Path | None:
    """Locate episode JSON in results directory."""
    model_dir_name = MODEL_DIR_MAP.get(model_key)
    if not model_dir_name:
        return None

    model_dir = RESULTS_DIR / model_dir_name
    if not model_dir.exists():
        return None

    # Parse episode_id: e.g. "adhf_warm_wet_120B_0"
    # Remove model key and run index to get scenario part
    parts = episode_id.rsplit("_", 2)
    if len(parts) >= 3:
        scenario_part = parts[0]
    else:
        scenario_part = episode_id.split("_" + model_key)[0] if model_key in episode_id else episode_id

    run_idx_str = episode_id.rsplit("_", 1)[-1]

    for fpath in model_dir.glob("*.json"):
        if fpath.name.endswith("model_summary.json"):
            continue
        if scenario_part in fpath.name and f"r{run_idx_str}" in fpath.name:
            return fpath

    # Fallback: broader match
    for fpath in model_dir.glob(f"{scenario_part}*.json"):
        if fpath.name.endswith("model_summary.json"):
            continue
        return fpath

    return None


def load_episode_details(path: Path) -> dict | None:
    """Load full episode data from file."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Scoring components
# ---------------------------------------------------------------------------


def compute_evaluator_disagreement(ep: dict) -> float:
    """Normalized evaluator disagreement: 0 (unanimous) to 1 (3-3 split)."""
    n_evaluators = len(EVALUATOR_KEYS)
    votes = [1 if ep.get(k, False) else 0 for k in EVALUATOR_KEYS]
    pass_count = sum(votes)
    fail_count = n_evaluators - pass_count
    # Max disagreement is 0.5 (3-3 split), normalize to [0, 1]
    raw = min(pass_count, fail_count) / n_evaluators
    return raw / 0.5  # 0.5 -> 1.0


def compute_clinical_severity(ep: dict) -> float:
    """Severity score based on violation types present."""
    viol_types = ep.get("viol_types", [])
    viol_types_lower = [v.lower() for v in viol_types]

    # verdict_matrix viol_types vocabulary is {WITHIN, FORBIDDEN, BEFORE} (constraint-layer);
    # COMMISSION / TIMING / SEQUENCE are assessor-layer tokens that never appear in this field.
    # Fixed 2026-04-30 (N5 audit): has_sequence was "sequence" (dead) — corrected to "before".
    has_forbidden = "forbidden" in viol_types_lower
    has_timing = "within" in viol_types_lower
    has_sequence = "before" in viol_types_lower
    has_omission = "omission" in viol_types_lower  # not in viol_types vocabulary; reserved for future schema

    if has_forbidden:
        return 1.0
    if has_timing or has_sequence:
        return 0.6
    if has_omission:
        return 0.3
    return 0.1


def compute_model_diversity_index(
    scenario_id: str,
    scenario_failures: dict[str, set[str]],
) -> float:
    """How many different models fail on this scenario (0 to 1)."""
    failing_models = scenario_failures.get(scenario_id, set())
    return len(failing_models) / len(MODELS) if MODELS else 0.0


def compute_interpretability(ep: dict) -> float:
    """Fewer violations = more interpretable (easier to explain in paper)."""
    n_viols = ep.get("n_viols", 0)
    if n_viols == 0:
        return 1.0
    if n_viols <= 2:
        return 0.9
    if n_viols <= 5:
        return 0.6
    if n_viols <= 10:
        return 0.3
    return 0.1


# ---------------------------------------------------------------------------
# Selection algorithm
# ---------------------------------------------------------------------------


def select_poster_children(verdict_episodes: list[dict]) -> list[dict]:
    """Select top-N case studies using multi-factor scoring."""
    if not verdict_episodes:
        return []

    # Pre-compute scenario failure index
    scenario_failures: dict[str, set[str]] = defaultdict(set)
    for ep in verdict_episodes:
        sid = ep.get("scenario_id", "")
        model = ep.get("model", "")
        # Consider "fail" if majority of evaluators say fail
        votes = [1 if ep.get(k, False) else 0 for k in EVALUATOR_KEYS]
        if sum(votes) < len(EVALUATOR_KEYS) / 2:
            scenario_failures[sid].add(model)

    # Score every episode
    scored: list[dict] = []
    for ep in verdict_episodes:
        sid = ep.get("scenario_id", "")
        domain = get_domain(sid)

        disagreement = compute_evaluator_disagreement(ep)
        severity = compute_clinical_severity(ep)
        model_div = compute_model_diversity_index(sid, scenario_failures)
        interpretability = compute_interpretability(ep)

        # Domain novelty is computed during greedy selection (dynamic)
        base_score = (
            W_DISAGREEMENT * disagreement
            + W_SEVERITY * severity
            + W_MODEL_DIVERSITY * model_div
            + W_INTERPRETABILITY * interpretability
        )

        verdicts: dict[str, str] = {}
        for key, label in zip(EVALUATOR_KEYS, EVALUATOR_LABELS):
            verdicts[label] = "PASS" if ep.get(key, False) else "FAIL"

        scored.append(
            {
                "episode_id": ep.get("episode_id", ""),
                "scenario_id": sid,
                "model": ep.get("model", ""),
                "domain": domain,
                "base_score": round(base_score, 4),
                "disagreement": round(disagreement, 4),
                "severity": round(severity, 4),
                "model_diversity": round(model_div, 4),
                "interpretability": round(interpretability, 4),
                "verdicts": verdicts,
                "n_viols": ep.get("n_viols", 0),
                "viol_types": ep.get("viol_types", []),
                "c2_score": ep.get("c2_score", 0),
                "action_coverage": ep.get("action_coverage", 0),
                "mab_f1": ep.get("mab_f1", 0),
            }
        )

    # Greedy selection with domain novelty bonus
    scored.sort(key=lambda x: -x["base_score"])
    selected: list[dict] = []
    seen_domains: set[str] = set()

    # Multiple passes: prefer diverse domains first
    for candidate in scored:
        if len(selected) >= N_SELECT:
            break
        domain = candidate["domain"]
        novelty_bonus = W_DOMAIN_NOVELTY if domain not in seen_domains else 0.0
        candidate["domain_novelty"] = round(novelty_bonus, 4)
        candidate["final_score"] = round(candidate["base_score"] + novelty_bonus, 4)

        # Accept if domain unseen or if score is high enough
        if domain not in seen_domains:
            selected.append(candidate)
            seen_domains.add(domain)

    # Fill remaining slots from top scorers
    if len(selected) < N_SELECT:
        selected_ids = {s["episode_id"] for s in selected}
        for candidate in scored:
            if len(selected) >= N_SELECT:
                break
            if candidate["episode_id"] in selected_ids:
                continue
            domain = candidate["domain"]
            novelty_bonus = W_DOMAIN_NOVELTY if domain not in seen_domains else 0.0
            candidate["domain_novelty"] = round(novelty_bonus, 4)
            candidate["final_score"] = round(candidate["base_score"] + novelty_bonus, 4)
            selected.append(candidate)
            seen_domains.add(domain)

    # Re-sort selected by final score
    selected.sort(key=lambda x: -x["final_score"])
    return selected


# ---------------------------------------------------------------------------
# Case study detail generation
# ---------------------------------------------------------------------------


def generate_case_narrative(case: dict, ep_details: dict | None) -> str:
    """Generate narrative for a single case study."""
    lines: list[str] = []
    sid = case["scenario_id"]
    domain = case["domain"]
    model_label = case["model"]

    # Scenario summary
    lines.append("### Scenario Summary\n")
    lines.append(
        f"Scenario **{sid}** (domain: {domain}) evaluated with model {model_label}. "
        f"This episode had {case['n_viols']} violation(s) with types: "
        f"{', '.join(case['viol_types']) if case['viol_types'] else 'none'}."
    )
    lines.append("")

    # Evaluator verdicts
    lines.append("### Evaluator Verdicts\n")
    lines.append("| Evaluator | Verdict |")
    lines.append("|-----------|---------|")
    for label, verdict in case["verdicts"].items():
        lines.append(f"| {label} | {verdict} |")
    lines.append("")

    passers = [k for k, v in case["verdicts"].items() if v == "PASS"]
    failers = [k for k, v in case["verdicts"].items() if v == "FAIL"]
    lines.append(f"**PASS**: {', '.join(passers) if passers else 'none'}")
    lines.append(f"**FAIL**: {', '.join(failers) if failers else 'none'}")
    lines.append("")

    # Agent trace
    lines.append("### Agent Trace (Key Actions)\n")
    if ep_details:
        violations = ep_details.get("new_violation_events", [])
        if violations:
            for i, v in enumerate(violations[:8], 1):
                vtype = v.get("violation_type", "unknown").upper()
                action = v.get("action_involved") or v.get("expected_action", "N/A")
                desc = v.get("description", "")[:120]
                severity = v.get("harm_severity", "")
                lines.append(f"{i}. **[{vtype}]** `{action}` (severity: {severity})")
                if desc:
                    lines.append(f"   {desc}")
            if len(violations) > 8:
                lines.append(f"   ... and {len(violations) - 8} more violations")
        else:
            lines.append("No violations recorded in episode details.")

        # Scores
        sub = ep_details.get("new_sub_scores", {})
        if sub:
            lines.append("\n**Sub-construct scores:**")
            for k, v in sub.items():
                lines.append(f"- {k}: {v:.3f}")
    else:
        lines.append("Episode details not available (file not found).")
    lines.append("")

    # What this demonstrates
    lines.append("### What This Case Demonstrates\n")
    demonstrations: list[str] = []

    if case["disagreement"] >= 0.8:
        demonstrations.append(
            "High evaluator disagreement reveals that different evaluation criteria "
            "capture fundamentally different aspects of clinical quality."
        )
    if case["severity"] >= 0.8:
        demonstrations.append(
            "Safety-critical violation (forbidden action) that some evaluators miss, "
            "highlighting the importance of constraint-based evaluation."
        )
    if case["model_diversity"] >= 0.5:
        demonstrations.append(
            "Multiple models fail on this scenario, suggesting inherent difficulty rather than model-specific weakness."
        )
    if "DxEM" in passers and "CGA-Bench" in failers:
        demonstrations.append(
            "Correct diagnosis (DxEM passes) does not guarantee safe treatment "
            "(CGA-Bench fails), demonstrating that accuracy metrics alone are insufficient."
        )
    if not demonstrations:
        demonstrations.append(
            "Illustrates the gap between aggregate metrics and fine-grained clinical guideline adherence evaluation."
        )

    for d in demonstrations:
        lines.append(f"- {d}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run WS-6 poster children selection."""
    print("=" * 70)
    print("WS-6: Select Poster-Child Case Studies")
    print("=" * 70)

    verdict_episodes = load_verdict_episodes()
    if not verdict_episodes:
        print("WARNING: No verdict matrix data found at", VERDICT_PATH)
        empty = {"error": "No verdict matrix found", "path": str(VERDICT_PATH)}
        save_json(empty, EVIDENCE_DIR / "ws6_poster_children.json")
        save_markdown("# WS-6: Poster Children\n\nNo data available.\n", EVIDENCE_DIR / "ws6_poster_children.md")
        return

    print(f"Loaded {len(verdict_episodes)} verdict episodes")

    selected = select_poster_children(verdict_episodes)
    print(f"Selected {len(selected)} case studies")

    # Enrich with episode details and generate narratives
    CASE_STUDIES_DIR.mkdir(parents=True, exist_ok=True)
    all_cases: list[dict] = []

    for i, case in enumerate(selected, 1):
        print(f"\n--- Case {i}: {case['episode_id']} ---")
        print(
            f"  Score: {case['final_score']:.3f} (disagree={case['disagreement']:.2f}, "
            f"severity={case['severity']:.2f}, diversity={case['model_diversity']:.2f})"
        )
        print(f"  Domain: {case['domain']}, Model: {case['model']}")

        # Load episode details
        ep_file = find_episode_file(case["episode_id"], case["model"])
        ep_details = load_episode_details(ep_file) if ep_file else None
        if ep_details:
            print(f"  Loaded episode details from {ep_file.name}")
        else:
            print("  Episode details file not found")

        narrative = generate_case_narrative(case, ep_details)

        case_output = {
            **case,
            "episode_file": str(ep_file) if ep_file else None,
            "narrative": narrative,
        }
        if ep_details:
            case_output["violations_detail"] = ep_details.get("new_violation_events", [])[:10]
            case_output["sub_scores"] = ep_details.get("new_sub_scores", {})
            case_output["actions_count"] = ep_details.get("actions_count", 0)

        all_cases.append(case_output)

        # Save individual case markdown
        case_md_path = CASE_STUDIES_DIR / f"ws6_case_{i}.md"
        case_md = f"# Case Study {i}: {case['episode_id']}\n\n{narrative}\n"
        save_markdown(case_md, case_md_path)

    # Save combined JSON
    save_json(all_cases, EVIDENCE_DIR / "ws6_poster_children.json")

    # Build combined markdown
    md_lines: list[str] = ["# WS-6: Top-5 Poster-Child Case Studies\n"]
    md_lines.append("## Selection Criteria\n")
    md_lines.append("Cases selected by multi-factor scoring:\n")
    md_lines.append(f"- Evaluator disagreement weight: {W_DISAGREEMENT}")
    md_lines.append(f"- Clinical severity weight: {W_SEVERITY}")
    md_lines.append(f"- Model diversity weight: {W_MODEL_DIVERSITY}")
    md_lines.append(f"- Domain novelty weight: {W_DOMAIN_NOVELTY}")
    md_lines.append(f"- Interpretability weight: {W_INTERPRETABILITY}")
    md_lines.append("")

    md_lines.append("## Summary Table\n")
    md_lines.append("| # | Episode | Domain | Model | Score | Disagree | Severity |")
    md_lines.append("|---|---------|--------|-------|------:|---------:|---------:|")
    for i, case in enumerate(all_cases, 1):
        md_lines.append(
            f"| {i} | {case['episode_id']} | {case['domain']} | {case['model']} "
            f"| {case['final_score']:.3f} | {case['disagreement']:.2f} "
            f"| {case['severity']:.2f} |"
        )
    md_lines.append("")

    for i, case in enumerate(all_cases, 1):
        md_lines.append(f"---\n\n## Case {i}: {case['episode_id']}\n")
        md_lines.append(case.get("narrative", "No narrative available."))
        md_lines.append("")

    save_markdown("\n".join(md_lines), EVIDENCE_DIR / "ws6_poster_children.md")

    print(f"\nWS-6 poster children complete. {len(all_cases)} cases written.")


if __name__ == "__main__":
    main()
