
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""Case Study Auto-Selection (Defense against Attack 1.2)

Selects episodes with maximum evaluator disagreement for case studies.
Ensures domain diversity and meaningful agent interaction.

Usage:
    PYTHONPATH=. python scripts/select_case_studies.py
"""

from __future__ import annotations

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
VERDICT_PATH = BASE_DIR / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
RESULTS_DIR = BASE_DIR / "results" / "clean_slate_rescored"
OUTPUT_DIR = BASE_DIR / "evidence_pack" / "case_studies"

EVALUATOR_KEYS = ["dxem", "ac_proxy", "mab_proxy", "c2_pass", "acov_pass", "v4_hard"]
EVALUATOR_LABELS = ["DxEM", "AC-Proxy", "MAB-Proxy", "C2", "ACov", "CGA-Bench"]

MODEL_DIR_MAP = {
    "4B": "qwen4b",
    "27B": "qwen27b",
    "35B": "qwen35b",
    "120B": "oss120b",
}


def load_per_episode() -> list[dict]:
    """Load per-episode data from verdict matrix."""
    with open(VERDICT_PATH) as f:
        data = json.load(f)
    return data["per_episode"]


def get_domain_from_scenario(scenario_id: str) -> str:
    """Extract clinical domain from scenario_id."""
    domain_prefixes = {
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
        "anaphylaxis": "anaphylaxis",
        "asthma": "asthma",
        "meningitis": "meningitis",
        "acls": "acls",
        "status_epilepticus": "epilepticus",
        "toxicology": "toxicology",
    }
    scenario_lower = scenario_id.lower()
    for prefix, domain in domain_prefixes.items():
        if scenario_lower.startswith(prefix):
            return domain
    return "other"


def find_episode_file(episode_id: str, model: str) -> Path | None:
    """Locate episode JSON file in results directory."""
    model_dir_name = MODEL_DIR_MAP.get(model)
    if not model_dir_name:
        return None

    model_dir = RESULTS_DIR / model_dir_name
    if not model_dir.exists():
        return None

    scenario_part = "_".join(episode_id.rsplit("_", 2)[:-2])
    for f in model_dir.glob("*.json"):
        if scenario_part in f.name:
            run_suffix = episode_id.rsplit("_", 1)[-1]
            if f"r{run_suffix}" in f.name or f"_{run_suffix}_" in f.name:
                return f

    for f in model_dir.glob(f"{scenario_part}*.json"):
        return f

    return None


def load_episode_details(path: Path) -> dict:
    """Load episode file and extract summary."""
    with open(path) as f:
        return json.load(f)


def format_violations(episode_data: dict) -> list[str]:
    """Format violation events into readable strings."""
    violations = episode_data.get("new_violation_events", [])
    summaries = []
    for v in violations[:10]:
        vtype = v.get("violation_type", "unknown")
        action = v.get("action_involved") or v.get("expected_action", "N/A")
        desc = v.get("description", "")
        summaries.append(f"  [{vtype.upper()}] {action}: {desc}")
    return summaries


def explain_disagreement(episode: dict) -> str:
    """Generate explanation of why evaluators disagree."""
    verdicts = episode["verdicts"]
    passers = [k for k, v in verdicts.items() if v == "PASS"]
    failers = [k for k, v in verdicts.items() if v == "FAIL"]

    lines = [
        f"PASS evaluators: {', '.join(passers)}",
        f"FAIL evaluators: {', '.join(failers)}",
    ]

    if "DxEM" in passers and "CGA-Bench" in failers:
        lines.append(
            "Key: DxEM passes (diagnosis correct) but CGA-Bench fails "
            "(constraint violations detected). This illustrates that "
            "correct diagnosis alone does not guarantee safe treatment."
        )
    if "MAB-Proxy" in failers and "AC-Proxy" in passers:
        lines.append(
            "AC-Proxy passes on coverage threshold but MAB-Proxy fails "
            "on F1, suggesting actions were taken but not precisely matched."
        )

    return "\n".join(lines)


def select_case_studies(n: int = 5) -> list[dict]:
    """Select top-N most-disagreed episodes with domain diversity.

    Args:
        n: Number of case studies to select.

    Returns:
        List of selected case study dicts.
    """
    episodes = load_per_episode()
    n_evaluators = len(EVALUATOR_KEYS)

    scored = []
    for ep in episodes:
        votes = [1 if ep.get(k, False) else 0 for k in EVALUATOR_KEYS]
        pass_count = sum(votes)
        fail_count = n_evaluators - pass_count
        disagreement = min(pass_count, fail_count) / n_evaluators

        verdicts = {}
        for key, label in zip(EVALUATOR_KEYS, EVALUATOR_LABELS):
            verdicts[label] = "PASS" if ep.get(key, False) else "FAIL"

        scored.append(
            {
                "episode_id": ep["episode_id"],
                "scenario_id": ep["scenario_id"],
                "model": ep.get("model", ""),
                "domain": get_domain_from_scenario(ep["scenario_id"]),
                "disagreement": disagreement,
                "pass_count": pass_count,
                "fail_count": fail_count,
                "verdicts": verdicts,
                "n_viols": ep.get("n_viols", 0),
                "c2_score": ep.get("c2_score", 0),
                "action_coverage": ep.get("action_coverage", 0),
                "mab_f1": ep.get("mab_f1", 0),
            }
        )

    scored.sort(key=lambda x: (-x["disagreement"], -x["n_viols"]))

    # Greedy selection with domain diversity
    selected = []
    seen_domains: set[str] = set()
    for ep in scored:
        if len(selected) >= n:
            break
        domain = ep["domain"]
        # Prefer unseen domains, but allow duplicates if needed
        if domain not in seen_domains or len(selected) >= len(seen_domains):
            selected.append(ep)
            seen_domains.add(domain)

    # If not enough diverse, fill from top disagreement
    if len(selected) < n:
        for ep in scored:
            if len(selected) >= n:
                break
            if ep not in selected:
                selected.append(ep)

    return selected


def main() -> None:
    """Generate case study materials."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    selected = select_case_studies(n=5)

    all_cases = []
    for i, case in enumerate(selected, 1):
        print(f"\n{'=' * 60}")
        print(f"Case Study #{i}: {case['episode_id']}")
        print(f"{'=' * 60}")
        print(f"Scenario: {case['scenario_id']}")
        print(f"Domain: {case['domain']}")
        print(f"Model: {case['model']}")
        print(f"Disagreement: {case['disagreement']:.2f} ({case['pass_count']} pass / {case['fail_count']} fail)")
        print("\nEvaluator Verdicts:")
        for label, verdict in case["verdicts"].items():
            print(f"  {label:12s}: {verdict}")

        print(f"\nScores: C2={case['c2_score']:.3f}, ACov={case['action_coverage']:.3f}, MAB-F1={case['mab_f1']:.3f}")

        print("\nKey Disagreement:")
        print(explain_disagreement(case))

        # Try to load episode details
        ep_file = find_episode_file(case["episode_id"], case["model"])
        episode_details = None
        if ep_file and ep_file.exists():
            episode_details = load_episode_details(ep_file)
            violations = format_violations(episode_details)
            if violations:
                print(f"\nViolations ({case['n_viols']}):")
                for v in violations:
                    print(v)

        case_output = {
            **case,
            "explanation": explain_disagreement(case),
            "episode_file": str(ep_file) if ep_file else None,
        }
        if episode_details:
            case_output["violations"] = episode_details.get("new_violation_events", [])[:10]
            case_output["actions_count"] = episode_details.get("actions_count", 0)

        all_cases.append(case_output)

        # Save individual case
        case_path = OUTPUT_DIR / f"case_{i}_{case['episode_id']}.json"
        with open(case_path, "w") as f:
            json.dump(case_output, f, indent=2, ensure_ascii=False)

    # Save summary
    summary_path = OUTPUT_DIR / "case_studies_summary.json"
    with open(summary_path, "w") as f:
        json.dump(all_cases, f, indent=2, ensure_ascii=False)
    print(f"\n\nSummary saved to {summary_path}")

    # Generate markdown summary
    md_lines = ["# Case Studies: Maximum Evaluator Disagreement\n"]
    for i, case in enumerate(all_cases, 1):
        md_lines.append(f"## Case {i}: {case['episode_id']}\n")
        md_lines.append(f"- **Scenario**: {case['scenario_id']}")
        md_lines.append(f"- **Domain**: {case['domain']}")
        md_lines.append(f"- **Model**: {case['model']}")
        md_lines.append(f"- **Disagreement**: {case['pass_count']} pass / {case['fail_count']} fail\n")
        md_lines.append("| Evaluator | Verdict |")
        md_lines.append("|-----------|---------|")
        for label, verdict in case["verdicts"].items():
            md_lines.append(f"| {label} | {verdict} |")
        md_lines.append(f"\n**Analysis**: {case['explanation']}\n")

    md_path = OUTPUT_DIR / "case_studies_summary.md"
    with open(md_path, "w") as f:
        f.write("\n".join(md_lines))
    print(f"Markdown summary saved to {md_path}")


if __name__ == "__main__":
    main()
