"""WS-6: Error Taxonomy and Failure Distribution.

Classifies all violations across episodes into a structured taxonomy:
  Category 1 — Safety (COMMISSION): Forbidden action performed
    1a: Medication contraindication
    1b: Procedure contraindication
  Category 2 — Temporal (TIMING/SEQUENCE):
    2a: Sequence reversal
    2b: Deadline exceeded
  Category 3 — Omission: Required action not performed
    3a: Critical treatment omission
    3b: Monitoring omission
  Category 4 — Compound: Multiple violation types in single episode

Produces per-model and per-domain distributions.

Usage:
    PYTHONPATH=. python scripts/experiments/ws6_error_taxonomy.py
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    RESULTS_DIR,
    TABLES_DIR,
    save_figure,
    save_json,
    save_latex_table,
    save_markdown,
    setup_matplotlib,
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

MEDICATION_PATTERNS = re.compile(
    r"(medication|drug|dose|insulin|antibiotic|vasopressor|norepinephrine|heparin|"
    r"aspirin|nitroglycerin|alteplase|tpa|diuretic|beta.?blocker|ace.?inhibitor|"
    r"crystalloid|saline|epinephrine|amiodarone|enoxaparin|clopidogrel|ticagrelor)",
    re.IGNORECASE,
)

PROCEDURE_PATTERNS = re.compile(
    r"(procedure|intubat|catheter|cath.?lab|pci|thrombectomy|endoscop|surgery|"
    r"defibrillat|cardioversion|thoracotomy|chest.?tube|central.?line|"
    r"lumbar.?puncture|bronchoscopy|dialysis|niv|ventilat)",
    re.IGNORECASE,
)

MONITORING_PATTERNS = re.compile(
    r"(monitor|reassess|recheck|repeat|follow.?up|serial|interval|surveillance|"
    r"track|observe|ecg|ekg|telemetry|pulse.?ox|vital|abg|lactate.?repeat)",
    re.IGNORECASE,
)

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


def load_all_episodes() -> list[dict]:
    """Load all rescored episodes from RESULTS_DIR."""
    episodes: list[dict] = []
    for model in MODELS:
        model_dir = RESULTS_DIR / model
        if not model_dir.exists():
            continue
        for fpath in sorted(model_dir.glob("*.json")):
            if fpath.name.endswith("model_summary.json"):
                continue
            with open(fpath) as fh:
                ep = json.load(fh)
            ep["_model"] = model
            episodes.append(ep)
    return episodes


def classify_violation(violation: dict) -> str:
    """Classify a single violation into taxonomy sub-category.

    Returns one of: '1a', '1b', '2a', '2b', '3a', '3b'.
    """
    vtype = violation.get("violation_type", "").lower()
    action = violation.get("action_involved", "") or ""
    expected = violation.get("expected_action", "") or ""
    description = violation.get("description", "") or ""
    combined_text = f"{action} {expected} {description}"

    if vtype == "commission":
        if MEDICATION_PATTERNS.search(combined_text):
            return "1a"
        return "1b"

    if vtype == "sequence":
        return "2a"

    if vtype == "timing":
        return "2b"

    if vtype == "omission":
        if MONITORING_PATTERNS.search(combined_text):
            return "3b"
        return "3a"

    # deviation and other types: classify by content
    if MONITORING_PATTERNS.search(combined_text):
        return "3b"
    return "3a"


def classify_episode_compound(violation_categories: list[str]) -> bool:
    """Check if episode has violations spanning multiple top-level categories."""
    top_categories = {cat[0] for cat in violation_categories}
    return len(top_categories) >= 2


CATEGORY_NAMES: dict[str, str] = {
    "1a": "Safety: Medication Contraindication",
    "1b": "Safety: Procedure Contraindication",
    "2a": "Temporal: Sequence Reversal",
    "2b": "Temporal: Deadline Exceeded",
    "3a": "Omission: Critical Treatment",
    "3b": "Omission: Monitoring",
    "4": "Compound (Multi-Category)",
}

TOP_CATEGORY_NAMES: dict[str, str] = {
    "1": "Safety (COMMISSION)",
    "2": "Temporal (TIMING/SEQUENCE)",
    "3": "Omission",
    "4": "Compound",
}


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def run_taxonomy(episodes: list[dict]) -> dict:
    """Classify all violations and produce distributions."""
    # Per-violation classification
    all_cats: Counter[str] = Counter()
    per_model: dict[str, Counter[str]] = defaultdict(Counter)
    per_domain: dict[str, Counter[str]] = defaultdict(Counter)

    # Per-episode compound tracking
    episode_summaries: list[dict] = []
    n_compound_episodes = 0
    n_episodes_with_violations = 0

    for ep in episodes:
        model = ep["_model"]
        sid = ep.get("scenario_id", "unknown")
        domain = get_domain(sid)
        violations = ep.get("new_violation_events", [])

        if not violations:
            continue

        n_episodes_with_violations += 1
        ep_cats: list[str] = []

        for v in violations:
            cat = classify_violation(v)
            ep_cats.append(cat)
            all_cats[cat] += 1
            per_model[model][cat] += 1
            per_domain[domain][cat] += 1

        is_compound = classify_episode_compound(ep_cats)
        if is_compound:
            n_compound_episodes += 1
            all_cats["4"] += 1
            per_model[model]["4"] += 1
            per_domain[domain]["4"] += 1

        episode_summaries.append(
            {
                "scenario_id": sid,
                "model": model,
                "domain": domain,
                "n_violations": len(violations),
                "categories": dict(Counter(ep_cats)),
                "is_compound": is_compound,
            }
        )

    # Build distributions
    categories_ordered = ["1a", "1b", "2a", "2b", "3a", "3b", "4"]
    total_violations = sum(all_cats[c] for c in categories_ordered)

    overall_dist: dict[str, dict] = {}
    for cat in categories_ordered:
        count = all_cats[cat]
        overall_dist[cat] = {
            "name": CATEGORY_NAMES[cat],
            "count": count,
            "rate": round(count / total_violations, 4) if total_violations > 0 else 0.0,
        }

    model_dist: dict[str, dict[str, int]] = {}
    for model in MODELS:
        model_dist[model] = {cat: per_model[model][cat] for cat in categories_ordered}

    domain_dist: dict[str, dict[str, int]] = {}
    for domain in sorted(per_domain):
        domain_dist[domain] = {cat: per_domain[domain][cat] for cat in categories_ordered}

    return {
        "total_episodes": len(episodes),
        "episodes_with_violations": n_episodes_with_violations,
        "compound_episodes": n_compound_episodes,
        "total_violations_classified": total_violations,
        "overall_distribution": overall_dist,
        "per_model": model_dist,
        "per_domain": domain_dist,
        "categories_ordered": categories_ordered,
        "episode_summaries": episode_summaries,
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def plot_failure_distribution(taxonomy: dict, path: Path) -> None:
    """Grouped bar chart: per-model failure distribution by category."""
    setup_matplotlib()
    categories = taxonomy["categories_ordered"]
    cat_labels = [CATEGORY_NAMES[c] for c in categories]
    short_labels = [
        "Med\nContra",
        "Proc\nContra",
        "Seq\nReversal",
        "Deadline\nExceed",
        "Treat\nOmission",
        "Monitor\nOmission",
        "Compound",
    ]

    n_cats = len(categories)
    n_models = len(MODELS)
    x = np.arange(n_cats)
    width = 0.18
    colors = ["#2ecc71", "#3498db", "#9b59b6", "#e74c3c"]

    fig, ax = plt.subplots(figsize=(12, 6))

    for i, model in enumerate(MODELS):
        counts = [taxonomy["per_model"].get(model, {}).get(c, 0) for c in categories]
        offset = (i - n_models / 2 + 0.5) * width
        bars = ax.bar(
            x + offset,
            counts,
            width,
            label=MODEL_LABELS.get(model, model),
            color=colors[i],
            edgecolor="black",
            alpha=0.85,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(short_labels, fontsize=9)
    ax.set_ylabel("Number of Violations")
    ax.set_title("WS-6: Failure Distribution by Error Taxonomy")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    save_figure(fig, path)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def build_markdown(taxonomy: dict) -> str:
    """Build markdown report."""
    lines: list[str] = []
    lines.append("# WS-6: Error Taxonomy\n")
    lines.append(f"- Total episodes: {taxonomy['total_episodes']}")
    lines.append(f"- Episodes with violations: {taxonomy['episodes_with_violations']}")
    lines.append(f"- Compound episodes (multi-category): {taxonomy['compound_episodes']}")
    lines.append(f"- Total classified violations: {taxonomy['total_violations_classified']}")
    lines.append("")

    lines.append("## Overall Distribution\n")
    lines.append("| Category | Name | Count | Rate |")
    lines.append("|----------|------|------:|-----:|")
    for cat, info in taxonomy["overall_distribution"].items():
        lines.append(f"| {cat} | {info['name']} | {info['count']} | {info['rate']:.1%} |")
    lines.append("")

    lines.append("## Per-Model Distribution\n")
    cats = taxonomy["categories_ordered"]
    header = "| Model | " + " | ".join(CATEGORY_NAMES[c].split(": ")[-1] for c in cats) + " | Total |"
    sep = "|-------|" + "|".join(["------:" for _ in cats]) + "|------:|"
    lines.append(header)
    lines.append(sep)
    for model in MODELS:
        label = MODEL_LABELS.get(model, model)
        counts = [taxonomy["per_model"].get(model, {}).get(c, 0) for c in cats]
        total = sum(counts)
        row = f"| {label} | " + " | ".join(str(c) for c in counts) + f" | {total} |"
        lines.append(row)
    lines.append("")

    lines.append("## Per-Domain Distribution\n")
    header = "| Domain | " + " | ".join(CATEGORY_NAMES[c].split(": ")[-1] for c in cats) + " | Total |"
    lines.append(header)
    lines.append(sep)
    for domain in sorted(taxonomy["per_domain"]):
        counts = [taxonomy["per_domain"][domain].get(c, 0) for c in cats]
        total = sum(counts)
        row = f"| {domain} | " + " | ".join(str(c) for c in counts) + f" | {total} |"
        lines.append(row)
    lines.append("")

    return "\n".join(lines)


def build_latex_rows(taxonomy: dict) -> tuple[list[list[str]], list[str]]:
    """Build LaTeX table rows."""
    cats = taxonomy["categories_ordered"]
    headers = ["Model"] + [c for c in cats] + ["Total"]
    rows: list[list[str]] = []
    for model in MODELS:
        label = MODEL_LABELS.get(model, model)
        counts = [taxonomy["per_model"].get(model, {}).get(c, 0) for c in cats]
        total = sum(counts)
        rows.append([label] + [str(c) for c in counts] + [str(total)])
    return rows, headers


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run WS-6 error taxonomy analysis."""
    print("=" * 70)
    print("WS-6: Error Taxonomy")
    print("=" * 70)

    episodes = load_all_episodes()
    if not episodes:
        print("WARNING: No episode data found in", RESULTS_DIR)
        empty = {"error": "No episode data found", "results_dir": str(RESULTS_DIR)}
        save_json(empty, EVIDENCE_DIR / "ws6_error_taxonomy.json")
        save_markdown("# WS-6: Error Taxonomy\n\nNo data available.\n", EVIDENCE_DIR / "ws6_error_taxonomy.md")
        return

    print(f"Loaded {len(episodes)} episodes")

    taxonomy = run_taxonomy(episodes)

    print(f"\nEpisodes with violations: {taxonomy['episodes_with_violations']}")
    print(f"Compound episodes: {taxonomy['compound_episodes']}")
    print(f"Total classified violations: {taxonomy['total_violations_classified']}")
    print("\nOverall distribution:")
    for cat, info in taxonomy["overall_distribution"].items():
        print(f"  {cat} ({info['name']}): {info['count']} ({info['rate']:.1%})")

    # Save outputs
    print("\n--- Saving outputs ---")

    # Remove bulky episode_summaries from JSON (keep top-level stats)
    json_output = {k: v for k, v in taxonomy.items() if k != "episode_summaries"}
    json_output["n_episode_summaries"] = len(taxonomy["episode_summaries"])
    save_json(json_output, EVIDENCE_DIR / "ws6_error_taxonomy.json")

    md = build_markdown(taxonomy)
    save_markdown(md, EVIDENCE_DIR / "ws6_error_taxonomy.md")

    rows, headers = build_latex_rows(taxonomy)
    save_latex_table(
        rows,
        headers,
        TABLES_DIR / "ws6_error_taxonomy.tex",
        caption="WS-6: Error Taxonomy Distribution by Model",
        label="tab:ws6-error-taxonomy",
    )

    plot_failure_distribution(taxonomy, FIGURES_DIR / "ws6_failure_distribution.png")

    print("\nWS-6 complete.")


if __name__ == "__main__":
    main()
